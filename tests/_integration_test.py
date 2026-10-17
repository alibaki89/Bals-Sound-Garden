"""Headless end-to-end smoke test for Bal's Sound Garden.

Drives the real App + screens with dummy SDL drivers: menu -> explore ->
collect a component -> music maker -> place clips -> play -> save -> your
music -> export WAV.  Prints PASS/FAIL per stage and exits non-zero on any
failure.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
import traceback
import pygame

FAILS = []

def check(label, cond):
    tag = "PASS" if cond else "FAIL"
    print(f"[{tag}] {label}")
    if not cond:
        FAILS.append(label)

def stage(label):
    print(f"\n--- {label} ---")


def fake_key(key, unicode=""):
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode=unicode, mod=0)


def main():
    from cat_society.app import App
    from cat_society import paths

    stage("Boot App (headless)")
    app = App()
    check("app constructed", app is not None)
    check("window exists", app.window is not None)
    check("starts on menu", app.current_name() == "menu")
    check("collection loaded", app.collection is not None)
    check("engine present (silent ok in headless)", app.engine is not None)

    # a few menu frames
    for _ in range(3):
        app.current.update(1/60)
        app.current.draw(app.window)
    check("menu renders without crash", True)

    stage("Enter Explore")
    app.goto("explore")
    check("on explore", app.current_name() == "explore")
    ex = app.current
    check("game built", ex.game is not None)
    check("pickups built", ex.pickups is not None)
    # chunk-based: ensure cells around spawn are generated, then count active
    ex.pickups._ensure_near(ex.game.cat)
    n_pickups = len(list(ex.pickups._active()))
    check("pickups generated around spawn", n_pickups > 0)
    print(f"      active pickups near spawn: {n_pickups}")

    # run some explore frames (turning the page on any story cards, the way
    # a player would -- the garden's intro whisper pauses the world)
    for i in range(600):
        ex.update(1/60)
        ex.draw(app.window)
        if ex.story.blocking and i % 20 == 19:
            ex.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                               key=pygame.K_SPACE))
        if not ex.story.blocking:
            break
    check("explore renders without crash", True)
    check("story cards dismissed", not ex.story.blocking)

    stage("Collect a component")
    owned_before = app.collection.num_found()
    # teleport the cat onto the nearest not-yet-owned pickup, then grab it
    ex.pickups._ensure_near(ex.game.cat)
    target = None
    for p in ex.pickups._active():
        target = p
        break
    check("found an uncollected pickup", target is not None)
    if target is not None:
        ex.game.cat.x = target.x
        ex.game.cat.z = target.z
        # use the E-key path through handle_event
        ex.handle_event(fake_key(pygame.K_e))
        got = app.collection.owns(target.comp["id"])
        check("component now owned", got)
        check("collection total grew", app.collection.num_found() == owned_before + 1)
        check("discovery card is animating", ex.card.busy())
        print(f"      collected: {target.comp['name']} ({target.comp['type']})")
        # let the card animate through a bunch of frames
        for _ in range(40):
            ex.update(1/30)
            ex.draw(app.window)
        check("card animation completes without crash", True)

    # persistence check: save + reload collection
    app.collection.save()
    from cat_society.components.collection import Collection
    reloaded = Collection(); reloaded.load()
    if target is not None:
        check("collected component persists after reload",
              reloaded.owns(target.comp["id"]))

    stage("Enter Music Maker")
    app.goto("maker")
    check("on maker", app.current_name() == "maker")
    mk = app.current
    check("maker has a project", mk.project is not None)
    proj = mk.project
    print(f"      project: {proj.name}  tempo={proj.tempo}  bars={proj.bars}")

    for _ in range(3):
        mk.update(1/60)
        mk.draw(app.window)
    check("maker renders without crash", True)

    stage("Place clips from owned components")
    placed = 0
    for tr in proj.tracks:
        # find an owned component this track accepts
        for comp in app.collection.owned_components():
            if tr.accepts(comp):
                step = (placed % 4) * 8     # spread along the grid
                tr.add(comp["id"], step)
                placed += 1
                break
        if placed >= 4:
            break
    proj.touch()
    check("placed at least 3 clips", proj.clip_count() >= 3)
    print(f"      clips placed: {proj.clip_count()}  on tracks used: {len(proj.components_used())}")

    stage("Play the arrangement")
    mk._toggle_play()
    for _ in range(5):
        mk.update(1/60)
        mk.draw(app.window)
    mk._toggle_play()  # stop
    check("play/stop without crash", True)

    stage("Save the project")
    name = "Smoke Test Song"
    proj.name = name
    before = len(app.refresh_projects())
    mk._save()
    after = len(app.refresh_projects())
    check("project count increased", after == before + 1)
    saved = [p for p in app.project_list if p.name == name]
    check("saved project is listed", len(saved) == 1)

    stage("Enter Your Music")
    app.goto("your_music")
    check("on your_music", app.current_name() == "your_music")
    ym = app.current
    for _ in range(3):
        ym.update(1/60)
        ym.draw(app.window)
    check("your_music renders without crash", True)
    check("your_music shows the saved song", any(p.name == name for p in app.project_list))

    stage("Export WAV")
    target_proj = saved[0] if saved else proj
    out = app.projects.load(target_proj.id) if saved else proj
    from cat_society.audio import export
    path = export.export_wav(out, samples=app.samples.buffers())
    exists = path and os.path.exists(path)
    check("WAV file written to disk", bool(exists))
    if exists:
        size = os.path.getsize(path)
        check("WAV is non-empty", size > 1000)
        print(f"      exported: {path}  ({size} bytes)")

    stage("Round-trip reload of saved project")
    rl = app.projects.load(target_proj.id)
    check("project reloads from disk", rl is not None)
    if rl is not None:
        check("reloaded clips match", rl.clip_count() == out.clip_count())
        check("reloaded tempo matches", rl.tempo == out.tempo)

    # cleanup the test artifacts so we don't ship them
    stage("Cleanup test artifacts")
    try:
        app.projects.delete(target_proj.id)
    except Exception:
        pass
    try:
        if exists and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    check("cleanup ran", True)

    app._shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n!!! UNCAUGHT EXCEPTION !!!")
        traceback.print_exc()
        FAILS.append("uncaught exception")

    print("\n" + "=" * 50)
    if FAILS:
        print(f"RESULT: {len(FAILS)} FAILURE(S)")
        for f in FAILS:
            print("  - " + f)
        sys.exit(1)
    else:
        print("RESULT: ALL STAGES PASSED")
        sys.exit(0)
