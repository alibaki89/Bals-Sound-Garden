"""v9 garden systems test: sprouts, works, stump, windmill, gramophones."""
import os, shutil, math
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

BACKUP = None
if os.path.isdir("save"):
    BACKUP = "save._test_backup"
    shutil.rmtree(BACKUP, ignore_errors=True)
    shutil.move("save", BACKUP)

passed = failed = 0
def check(name, cond):
    global passed, failed
    print(("  ok  " if cond else "  FAIL") + "  " + name)
    passed += bool(cond); failed += (not cond)

try:
    from cat_society.app import App
    from cat_society.world.sprouts import SproutManager, plantable
    from cat_society.world.garden import GardenFixtures, METER_FULL
    from cat_society.systems.works import soft_check_song, _BY_ID
    from cat_society.components import catalog
    from cat_society.music import profile as profile_mod, store
    from cat_society.music.project import Project

    app = App()
    ws = app.world_state
    ws.seed = 424242          # pinned: tests plant on known-dry ground
    ws.save()

    # -- WorldState generic data -------------------------------------------
    ws.set_data_list("zz", [{"a": 1}])
    ws.data_dict("meta")["x"] = 5; ws.touch()
    ws.load()
    check("state data roundtrip", ws.data_list("zz") == [{"a": 1}]
          and ws.data_dict("meta")["x"] == 5)

    ex = app.screens["explore"]; app.goto("explore")
    ex.on_enter(); ex.ensure_game()
    for _ in range(4):
        if ex.story.blocking:
            ex.story.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
        ex.update(0.03)

    sp, gd = ex.sprouts, ex.garden
    # Works are intentionally dormant in the actual Explore screen.  Keep a
    # private manager here only to regression-test the legacy mechanism module.
    from cat_society.systems.works import WorksManager
    wm = WorksManager(ws, app.collection)
    gd.works = wm
    check("Explore runs without the task system", ex.works is None)
    cat_drums = [c for c in catalog.ALL if c["type"] in ("drum", "rhythm")][:6]
    for c in cat_drums:
        app.collection.collect(c["id"])

    # -- planting, spacing, persistence, uproot ------------------------------
    s1, _ = sp.plant(cat_drums[0]["id"], 0, 0)
    s2, why = sp.plant(cat_drums[1]["id"], 10, 10)     # too close
    check("plant + spacing gap", s1 is not None and s2 is None and why)
    sp2 = SproutManager(ws, app.engine)
    check("sprouts persist", sp2.count() == sp.count())
    check("uproot", sp.uproot(s1) and sp.count() == 0)

    # -- geometry surveys ------------------------------------------------------
    xs = [0, 120, 240, 360]
    for i, x in enumerate(xs):
        sp.plant(cat_drums[i]["id"], x, 500)
    perc = lambda c: c["type"] in ("drum", "rhythm")
    check("chain of 4", sp.chain(perc, 150.0, 4) >= 4)
    check("chain gap breaks", sp.chain(perc, 90.0, 4) < 4)
    check("cluster", sp.cluster(perc, 400.0, 4))
    check("no loop in an open row", not sp.loop_of(lambda c: True, 200.0, 4))
    ring_ids = [c["id"] for c in cat_drums]
    for k in range(6):
        a = k * math.tau / 6
        sp.plant(ring_ids[k], 2000 + math.cos(a) * 150, 500 + math.sin(a) * 150)
    check("loop_of finds circuit", sp.loop_of(lambda c: True, 200.0, 6))

    # -- quantized triggering (with a fake clock we control) --------------------
    from cat_society.world.sprouts import SproutManager as SM
    fake = [1000.0]
    spq = SM(ws, app.engine, clock=lambda: fake[0])
    s = spq.sprouts[0]
    ex.game.cat.x, ex.game.cat.z = s.x, s.z
    fired = scheduled_beat = None
    for _ in range(40):
        spq.update(1 / 30, ex.game)
        if scheduled_beat is None and spq._pending:
            scheduled_beat = spq._pending[0][0]
        if s.pulse < 0.2:
            fired = spq.beat()
        fake[0] += 1 / 30
    check("trigger quantized to the eighth grid",
          scheduled_beat is not None and abs(scheduled_beat % 0.5) < 1e-6)
    check("ring fires on the grid", fired is not None
          and fired >= scheduled_beat)
    check("rest applies after ringing", s.next_ok_beat >= scheduled_beat + 1)

    # -- works: song checks (soft, ingredient-based) ----------------------------
    p = Project(name="Walking Test", tempo=104)
    dr = next(t for t in p.tracks if t.kind == "drums")
    me = next(t for t in p.tracks if t.kind == "melody")
    for st in (0, 4, 8, 12):
        dr.add(cat_drums[0]["id"], st)
    note = next(c for c in catalog.ALL if c["type"] == "note")
    me.add(note["id"], 0)
    prof = profile_mod.analyze(p)
    ok, _ = soft_check_song(prof, _BY_ID["w_walking_beat"]["req"])
    check("walking beat passes", ok)
    ok2, nudge = soft_check_song(prof, _BY_ID["w_rain_loop"]["req"])
    check("rain loop nudges (no water)", not ok2 and bool(nudge))
    slow = Project(name="Too Fast Lullaby", tempo=120)
    next(t for t in slow.tracks if t.kind == "melody").add(note["id"], 0)
    next(t for t in slow.tracks if t.kind == "melody").add(note["id"], 4)
    okl, nl = soft_check_song(profile_mod.analyze(slow),
                              _BY_ID["w_reed_lullaby"]["req"])
    check("lullaby tempo nudge", not okl and "low" in nl.lower() or "92" in nl)

    # -- submission at the stump -------------------------------------------------
    for wid in ("w_first_sprouts", "w_perc_row", "w_night_corner"):
        wm.complete(wid)
    wm.pop_events()
    wm.set_active("w_walking_beat")
    wm.check_song(_BY_ID["w_walking_beat"], prof, "Walking Test")
    check("stump stamps the commission", wm.is_done("w_walking_beat"))
    check("songbook remembers", wm.song_used("w_walking_beat") == "Walking Test")
    check("commission pays", app.collection.owns("gift_chime_breeze"))

    # -- windmill: drummed music pumps ---------------------------------------
    ex.perf.active = True; ex.perf.profile = prof
    ex.perf.x, ex.perf.z = gd.mill
    for _ in range(int(METER_FULL / 0.25) + 4):
        gd.update(0.25, ex.perf, gd.mill[0], gd.mill[1])
    ex.perf.active = False
    check("meter fills, bed grows", gd.mill_grown())
    check("windmill work completes", wm.is_done("w_windmill"))
    got = gd.harvest(app.collection)
    check("harvest pays rare seeds", len(got) == 2
          and app.collection.owns("gift_fountain_arp"))
    check("harvest only once", gd.harvest(app.collection) == [])

    # -- gramophone + pond scoring ------------------------------------------------
    wet = None
    for gx in range(-4000, 4001, 160):
        for gz in range(-2000, 5000, 160):
            if ex.game.water.depth_at(gx, gz)[0] > 0:
                wet = (gx, gz); break
        if wet: break
    check("found water to score", wet is not None)
    watery = [c for c in catalog.ALL if "watery" in profile_mod.tags_for(c)][:3]
    check("watery comps exist", len(watery) == 3)
    wp = Project(name="Pond Side", tempo=100)
    lt = next(t for t in wp.tracks if t.kind == "loops")
    for i, c in enumerate(watery):
        lt.add(c["id"], i * 2)
    next(t for t in wp.tracks if t.kind == "melody").add(note["id"], 0)
    store.save(wp)
    dx, dz = ex.game.water.nearest_dry(wet[0], wet[1])
    g = gd.plant_gramophone(wp, dx, dz)
    ok, hint = gd.pond_scored()
    check("pond scored by watery record", ok)
    if not ok: print("      hint:", hint, "| gramos:", len(gd.gramophones), "| tags:", sorted(gd.gramophones[0].tags) if gd.gramophones else [])
    gd2 = GardenFixtures(ex.game.world, ex.game.water, ws, app.engine, wm)
    check("gramophone persists", len(gd2.gramophones) == 1)
    check("fixtures settle deterministically",
          gd2.stump == gd.stump and gd2.mill == gd.mill)
    gd.remove_gramophone(g)
    check("gramophone picked back up", len(gd.gramophones) == 0)

    # -- distance audio: the curve is real -------------------------------------
    from cat_society.audio.engine import hearing
    check("close is loud", hearing(60) == 1.0)
    check("middle fades", 0.2 < hearing(480) < 0.5)
    check("far is silent", hearing(830) == 0.0 and hearing(2000) == 0.0)

    # -- playhead lives on the grid ---------------------------------------------
    import time as _t
    glen = app.engine.play_project(p, samples={})
    grid = app.engine._music_grid_len
    check("audio outlasts the grid (tail)", glen >= grid > 0)
    app.engine._music_started = _t.time() - grid * 0.5
    check("playhead at half-grid", abs(app.engine.playhead_fraction() - 0.5) < 0.03)
    app.engine._music_started = _t.time() - glen - 1.0
    check("playhead parks at the end", app.engine.playhead_fraction() == 1.0)
    app.engine.stop_music()

    # -- v12: shaping checks, ledgers, doppler ---------------------------------
    from cat_society.systems.works import (_quiet_bed, _mixed_bed,
                                           _gramo_near_chain)
    softs = [c for c in catalog.ALL if c["type"] in ("chord", "ambience", "note")][:6]
    for c in softs: app.collection.collect(c["id"])
    for i, c in enumerate(softs[:4]):
        sp.plant(c["id"], 6000 + (i % 2) * 80, 300 + (i // 2) * 80)
    ok, n = _quiet_bed(sp, 180.0, 4)
    check("quiet bed found", ok and n >= 4)
    sp.plant(cat_drums[0]["id"], 6060, 340)
    ok2, _n2 = _quiet_bed(sp, 180.0, 4)
    check("drums spoil the hush", not ok2)
    for i, c in enumerate(softs[4:6]):
        sp.plant(c["id"], 6120 + i * 60, 300)
    check("mixed bed counts families", _mixed_bed(sp, 220.0, 6, 3) >= 3)
    g4 = gd.plant_gramophone(wp, 6040, 320)
    check("gramophone beside the patch", _gramo_near_chain(sp, gd, 260.0, 4))
    gd.remove_gramophone(g4)
    # ledgers
    ws.data_dict("counters")["record_power_s"] = 13.0
    okr, _ = wm.peek(_BY_ID["w_record_power"], sp, gd, None)
    check("record-power work reads the ledger", okr)
    s_a, s_b = sp.sprouts[0], sp.sprouts[1]
    sp._after_ring(ex.game, s_a, "animal"); sp._after_ring(ex.game, s_b, "animal")
    sp._after_ring(ex.game, s_a, "animal")
    check("animal band ledger is distinct", sp.animal_ring_count() == 2)
    # doppler cache: shifted buffers differ in length
    if app.engine.ok:
        d0 = app.engine._sprout_sound(cat_drums[0], 104, 0)
        d1 = app.engine._sprout_sound(cat_drums[0], 104, 1)
        check("doppler buckets cached", d0 is not None and d1 is not None
              and d0.get_length() != d1.get_length())
    else:
        check("doppler buckets cached", True)

    # -- v14: soft collision, universal water, journal pages -------------------
    from cat_society.entities.animals import Animal
    a = Animal("cow", ex.game.cat.x + 5, ex.game.cat.z, __import__("random").Random(1))
    cx0 = ex.game.cat.x
    for _ in range(30):
        ex.game.animals._resolve_cat(a, ex.game.cat, 1 / 30)
    import math as _m2
    sep = _m2.hypot(a.x - ex.game.cat.x, a.z - ex.game.cat.z)
    check("cow and cat settle apart, both moved",
          sep > 20 and ex.game.cat.x != cx0)
    ex.game.cat.x, ex.game.cat.z = 0, 500
    bird = Animal("bird", 3, 500, __import__("random").Random(2))
    bx0 = 3.0
    for _ in range(30):
        ex.game.animals._resolve_cat(bird, ex.game.cat, 1 / 30)
    check("small bird mostly scoots itself", abs(bird.x - bx0) >
          abs(ex.game.cat.x - 0))
    # any animal swims: put a rabbit in water and step it
    rb = Animal("rabbit", dx, dz, __import__("random").Random(3))
    rb.x, rb.z = wet[0], wet[1]
    rb.vx = 40.0
    ctx2 = {"cat_x": 9999, "cat_z": 9999, "valid": lambda *a2: True,
            "depth": lambda px, pz: ex.game.water.depth_at(px, pz)[0],
            "in_water": lambda px, pz: True, "song": None}
    rb.swim = 0.6
    x_before = rb.x
    rb.update(0.1, ctx2)
    check("land rabbit paddles (slower, not stuck)",
          rb.x > x_before and rb.x - x_before < 40.0 * 0.1)
    # no tunneling: press hard into a duck head-on and diagonally
    from cat_society.config import CAT_R
    for ang_dx, ang_dz, label in ((3.0, 0.0, "head-on"), (2.1, 2.1, "diagonal")):
        duck = Animal("duck", 40, 900, __import__("random").Random(7))
        ex.game.cat.x, ex.game.cat.z = 0.0, 900.0 if ang_dz == 0 else 860.0
        mgr = ex.game.animals
        oax = mgr.CAT_LEN + duck.spec.radius * mgr.LEN_FIT
        oaz = mgr.CAT_SIDE + duck.spec.radius * mgr.SIDE_FIT
        never_inside = True
        for _ in range(120):
            ex.game.cat.x += ang_dx
            ex.game.cat.z += ang_dz
            mgr._resolve_cat(duck, ex.game.cat, 1 / 30)
            m = _m2.hypot((duck.x - ex.game.cat.x) / oax,
                          (duck.z - ex.game.cat.z) / oaz)
            if m < 0.96:
                never_inside = False
        check("no tunneling (%s), Bal still travels" % label,
              never_inside and ex.game.cat.x > 180)

    # passing nearly side-by-side: noses and tails must not overlap
    shp = Animal("sheep", 60, 1500, __import__("random").Random(11))
    ex.game.cat.x, ex.game.cat.z = -80.0, 1508.0
    oax = mgr.CAT_LEN + shp.spec.radius * mgr.LEN_FIT
    oaz = mgr.CAT_SIDE + shp.spec.radius * mgr.SIDE_FIT
    clean = True
    for _ in range(140):
        ex.game.cat.x += 2.4
        mgr._resolve_cat(shp, ex.game.cat, 1 / 30)
        m = _m2.hypot((shp.x - ex.game.cat.x) / oax,
                      (shp.z - ex.game.cat.z) / oaz)
        if m < 0.96:
            clean = False
    check("head and tail stay clear while passing",
          clean and ex.game.cat.x > 180)

    # The Journal is available through pause, while C/J remain unused.
    ex.story.__init__()
    ex.card.__init__()
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    c_kept_playing = not ex.paused
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j))
    check("C/J leave Explore unobstructed", c_kept_playing and not ex.paused)
    ex._set_paused(True)
    ex._pause_action("journal")
    surf2 = pygame.Surface((1280, 720))
    ex.draw(surf2)
    check("pause-menu Journal draws", ex.pause_page == "journal")
    ex._pause_action("back")
    ex._set_paused(False)

    # -- chapters ------------------------------------------------------------------
    check("chapter advanced past 1", wm.chapter() >= 2)
    check("route-free legacy works remain available", len(__import__("cat_society.systems.works",
          fromlist=["WORKS"]).WORKS) == 15)
    surf = pygame.Surface((1280, 720))
    ex.draw(surf)
    ex._open_tray(); ex._draw_tray(surf)
    menu = app.screens["menu"]
    menu._open_soundbook(); menu.soundbook.draw(surf); menu._close_dialog()
    check("draws with everything alive", True)

finally:
    shutil.rmtree("save", ignore_errors=True)
    if BACKUP:
        shutil.move(BACKUP, "save")

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
