"""The garden's working fixtures: stump, windmill seed bed, gramophones.

* **Notice Stump** -- the hub.  Stands near spawn; E opens the Garden Works
  board; performing a saved song beside it submits it against the active
  commission.

* **Windmill seed bed** -- one honest sound machine with a readable rule:
  *drummed music within earshot pumps water*.  While a live performance or a
  nearby gramophone with drums is playing, the blades spin at the song's
  tempo and the bed's meter fills.  A full meter grows a rare seed pod which
  Bal harvests with E.  No timers, no decay -- the meter only ever fills.

* **Gramophones** -- plant one of your *saved songs* into the world.  The
  nearest gramophone within earshot actually loops its record (rendered by
  the same engine as the WAV export), with volume by distance, so zones of
  the garden run on your music -- and machines can be powered by records you
  leave behind instead of standing there performing.

Positions settle deterministically onto dry, open ground for the save's
seed.  All state persists through :class:`WorldState`.
"""

import math
import time

from ..components import catalog
from ..music import store, profile as profile_mod
from ..audio import export
from ..projection import project_cull
from ..render.garden_objects import (draw_stump, draw_windmill, draw_seedbed,
                                     draw_gramophone, draw_bloom)

STUMP_REACH = 120.0          # E opens the board / P submits within this
POWER_REACH = 430.0          # music within this powers the windmill
GRAMO_EARSHOT = 560.0        # the nearest gramophone inside this plays
METER_FULL = 24.0            # seconds of drummed music to fill the bed
HARVEST = ["gift_fountain_arp", "gift_deer_bell"]


def _settle(world, water, ang, dist, clearance=70.0):
    """Deterministic dry, open spot near a designed polar position."""
    bx = math.cos(ang) * dist
    bz = math.sin(ang) * dist + 700.0
    for i in range(14):
        a = ang + i * 0.9
        r = i * 120.0
        cx, cz = water.nearest_dry(bx + math.cos(a) * r, bz + math.sin(a) * r)
        if all((sx - cx) ** 2 + (sz - cz) ** 2 >= (sr + clearance) ** 2
               for sr, sx, sz in world.solids_near(cx, cz)):
            return cx, cz
    return water.nearest_dry(bx, bz)


class Gramophone:
    __slots__ = ("song_id", "name", "x", "z", "tags", "has_drums",
                 "tempo", "_buf")

    def __init__(self, rec):
        self.song_id = rec["p"]
        self.name = rec.get("n", "a record")
        self.x = float(rec["x"])
        self.z = float(rec["z"])
        self.tags = set(rec.get("tags", ()))
        self.has_drums = bool(rec.get("dr"))
        self.tempo = int(rec.get("bpm", 100))
        self._buf = None             # rendered lazily, once, when first heard

    def rec(self):
        return {"p": self.song_id, "n": self.name,
                "x": round(self.x, 1), "z": round(self.z, 1),
                "tags": sorted(self.tags), "dr": self.has_drums,
                "bpm": self.tempo}

    def buffer(self):
        if self._buf is None:
            try:
                proj = store.load(self.song_id)
                self._buf = export.render_project(proj, loop=True, samples={})
            except Exception:
                self._buf = []
        return self._buf


class GardenFixtures:
    """Places and runs the stump, the windmill bed and every gramophone."""

    def __init__(self, world, water, state, engine, works):
        self.state = state
        self.engine = engine
        self.works = works
        self.water = water
        self.stump = _settle(world, water, 0.6, 360.0)
        self.mill = _settle(world, water, 2.8, 1450.0)
        self.bed = (self.mill[0] + 95.0, self.mill[1] + 55.0)
        self.blade_a = 0.0
        self.spin = 0.0              # current blade speed (rad/s), eased
        self._powered = False
        self._bp = 0.0
        self.just_powered = False    # rising edge, consumed by the screen
        self._power_note_cd = 0.0
        self._gramo_pan = 0.5
        self._playing = None         # gramophone currently on the channel
        self.gramophones = [Gramophone(r)
                            for r in state.data_list("gramophones")]
        self._events = []

    # -- persistence -----------------------------------------------------------
    def _save_gramos(self):
        return self.state.set_data_list("gramophones",
                                 [g.rec() for g in self.gramophones])

    def _mill_rec(self):
        d = self.state.data_dict("machines").setdefault(
            "windmill", {"meter": 0.0, "grown": False, "claimed": False})
        return d

    # -- gramophones -------------------------------------------------------------
    def plant_gramophone(self, project, x, z):
        prof = profile_mod.analyze(project)
        g = Gramophone({"p": project.id, "n": project.name, "x": x, "z": z,
                        "tags": sorted(prof.tags), "dr": prof.has_drums,
                        "bpm": prof.tempo})
        self.gramophones.append(g)
        if not self._save_gramos():
            self.gramophones.remove(g)
            return None
        return g

    def nearest_gramophone(self, x, z, max_dist=60.0):
        best, bd = None, max_dist * max_dist
        for g in self.gramophones:
            d2 = (g.x - x) ** 2 + (g.z - z) ** 2
            if d2 < bd:
                best, bd = g, d2
        return best

    def remove_gramophone(self, g):
        if g in self.gramophones:
            if self._playing is g:
                self.engine.gramo_stop()
                self._playing = None
            index = self.gramophones.index(g)
            self.gramophones.remove(g)
            if not self._save_gramos():
                self.gramophones.insert(index, g)
                return False
            return True

    def pond_scored(self):
        """Score-the-pond check: a watery-record gramophone near real water."""
        best_hint = ("Plant a gramophone (from the seed tray, F) loaded "
                     "with one of your watery songs, close to the water.")
        for g in self.gramophones:
            near_water = any(
                self.water.depth_at(g.x + math.cos(a) * d,
                                    g.z + math.sin(a) * d)[0] > 0.0
                for d in (110.0, 240.0)
                for a in (k * math.tau / 8 for k in range(8)))
            if near_water and "watery" in g.tags:
                return True, ""
            if near_water:
                best_hint = ("That record is by the water, but the pond "
                             "listens for watery sounds in it.")
            elif "watery" in g.tags:
                best_hint = "A watery record -- now plant it nearer the water."
        return False, best_hint

    # -- the windmill: drummed music pumps water ---------------------------------
    def mill_meter(self):
        return float(self._mill_rec().get("meter", 0.0))

    def mill_grown(self):
        return bool(self._mill_rec().get("grown"))

    def mill_claimed(self):
        return bool(self._mill_rec().get("claimed"))

    def harvest(self, collection):
        rec = self._mill_rec()
        if not rec.get("grown") or rec.get("claimed"):
            return []
        rec["claimed"] = True
        self.state.touch()
        out = []
        for cid in HARVEST:
            comp = catalog.get(cid)
            if comp is not None and not collection.owns(cid):
                collection.collect(cid)
                out.append(comp)
        return out

    def update(self, dt, perf, cat_x, cat_z, beat_phase=0.0):
        self._bp = beat_phase
        # which gramophone should be on the channel?  the nearest in earshot,
        # silenced while Bal performs live so songs never fight
        near = None
        if not perf.active:
            bd = GRAMO_EARSHOT ** 2
            for g in self.gramophones:
                d2 = (g.x - cat_x) ** 2 + (g.z - cat_z) ** 2
                if d2 < bd:
                    near, bd = g, d2
        if near is not self._playing:
            self.engine.gramo_stop()
            self._playing = None
            if near is not None and self.engine.gramo_play(near.buffer()):
                self._playing = near
        if self._playing is not None:
            d = math.hypot(self._playing.x - cat_x, self._playing.z - cat_z)
            pan = 0.5 + max(-0.4, min(0.4, (self._playing.x - cat_x) / 720.0))
            self._gramo_pan += (pan - self._gramo_pan) * min(1.0, dt * 6.0)
            from ..audio.engine import hearing
            self.engine.gramo_volume(hearing(d) * 0.95, pan=self._gramo_pan)

        # is drummed music playing within the windmill's earshot?
        powered, tempo = False, 100
        if perf.active and perf.profile is not None and perf.profile.has_drums:
            if math.hypot(perf.x - self.mill[0],
                          perf.z - self.mill[1]) < POWER_REACH:
                powered, tempo = True, perf.profile.tempo
        if not powered and self._playing is not None and self._playing.has_drums:
            if math.hypot(self._playing.x - self.mill[0],
                          self._playing.z - self.mill[1]) < POWER_REACH:
                powered, tempo = True, self._playing.tempo

        self._power_note_cd = max(0.0, self._power_note_cd - dt)
        if powered and not self._powered and self._power_note_cd <= 0.0 \
                and not self.mill_grown():
            self.just_powered = True
            self._power_note_cd = 25.0
        self._powered = powered
        target = (tempo / 60.0) * math.pi if powered else 0.0
        self.spin += (target - self.spin) * min(1.0, dt * 2.2)
        self.blade_a += self.spin * dt

        if powered and (not perf.active) and self._playing is not None:
            c = self.state.data_dict("counters")
            c["record_power_s"] = min(60.0, c.get("record_power_s", 0.0) + dt)
            if int(c["record_power_s"]) != int(c["record_power_s"] - dt):
                self.state.touch()
        rec = self._mill_rec()
        if powered and not rec.get("grown"):
            rec["meter"] = min(METER_FULL, rec.get("meter", 0.0) + dt)
            if int(rec["meter"]) != int(rec["meter"] - dt):
                self.state.touch()       # save on whole seconds only
            if rec["meter"] >= METER_FULL:
                rec["grown"] = True
                self.state.touch()
                if self.works is not None:
                    self.works.complete("w_windmill")

    def record_powered_s(self):
        return float(self.state.data_dict("counters").get("record_power_s", 0.0))

    # -- celebration blooms: completed works leave flowers in the world -------
    def add_bloom(self, x, z):
        blooms = self.state.data_list("blooms")
        blooms.append({"x": round(float(x), 1), "z": round(float(z), 1)})
        self.state.set_data_list("blooms", blooms[-60:])

    # -- drawing -------------------------------------------------------------------
    def solids_near(self, x, z):
        out = []
        for (px, pz), r in ((self.stump, 24.0), (self.mill, 34.0)):
            if abs(px - x) < 160 and abs(pz - z) < 160:
                out.append((r, px, pz))
        for g in self.gramophones:
            if abs(g.x - x) < 140 and abs(g.z - z) < 140:
                out.append((13.0, g.x, g.z))
        return out

    def world_drawables(self, cam, t, works_open_count, chapters_done=0,
                        blooming=False):
        out = []
        pr = project_cull(*self.stump, cam)
        if pr is not None:
            sx, sy, sc, fd = pr

            def d_stump(surf, _a=(sx, sy, sc, fd)):
                draw_stump(surf, *_a, t, works_open_count,
                           garlands=chapters_done)
            out.append((sy, 40, d_stump))
        pr = project_cull(*self.mill, cam)
        if pr is not None:
            sx, sy, sc, fd = pr
            ba, pw, bp = self.blade_a, self._powered, self._bp

            def d_mill(surf, _a=(sx, sy, sc, fd), _b=ba, _p=pw, _bp=bp):
                draw_windmill(surf, *_a, _b, powered=_p, beat_phase=_bp)
            out.append((sy, 40, d_mill))
        pr = project_cull(*self.bed, cam)
        if pr is not None:
            sx, sy, sc, fd = pr
            frac = self.mill_meter() / METER_FULL
            grown = self.mill_grown() and not self.mill_claimed()
            pw = self._powered and not self.mill_grown()

            def d_bed(surf, _a=(sx, sy, sc, fd), _f=frac, _g=grown, _p=pw):
                draw_seedbed(surf, *_a, t, _f, _g, watering=_p)
            out.append((sy, 40, d_bed))
        for g in self.gramophones:
            pr = project_cull(g.x, g.z, cam)
            if pr is None:
                continue
            sx, sy, sc, fd = pr
            live = g is self._playing

            def d_gr(surf, _a=(sx, sy, sc, fd), _live=live):
                draw_gramophone(surf, *_a, t, _live, bloom=blooming)
            out.append((sy, 40, d_gr))
        for i, b in enumerate(self.state.data_list("blooms")):
            pr = project_cull(b["x"], b["z"], cam)
            if pr is None:
                continue
            sx, sy, sc, fd = pr

            def d_bl(surf, _a=(sx, sy, sc, fd), _i=i):
                draw_bloom(surf, *_a, t, _i)
            out.append((sy, 40, d_bl))
        return out
