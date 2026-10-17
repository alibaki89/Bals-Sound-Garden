"""Sound sprouts: the garden as a playable, plantable sequencer.

Every collected component can be planted into the world as a small living
emitter -- a *sprout*.  When Bal (or any wandering animal) steps into a
sprout's soil ring, it rings: the trigger is quantized to the shared garden
clock, so a row of sprouts crossed at a walk comes out as a phrase, not a
clatter.  Each sprout then rests for a fixed number of beats before it can
ring again, which is what turns *layouts* into *rhythms*:

* percussion sprouts rest 1 beat  -> dense ticking rows
* note sprouts rest 2 beats       -> melodic steps
* loop / rhythm sprouts rest 4    -> phrase markers
* chord / bass sprouts rest 4     -> harmonic pillars
* ambience sprouts rest 8         -> washes you plant sparsely

So the player composes twice: once on the step grid in the Music Maker, and
once *spatially*, by deciding where sounds live and which routes cross them.
Walking is performing.  Animals wandering through your rows play them too,
which makes a well-planted garden quietly perform itself.

Everything persists in ``save/world.json`` through
:class:`cat_society.world.state.WorldState`.
"""

import math
import time

from ..components import catalog
from ..projection import project_cull
from ..render.sprouts import draw_sprout
from ..audio.engine import hearing

# the shared garden clock: every trigger snaps to the next eighth of this.
GARDEN_BPM = 104
_BEAT = 60.0 / GARDEN_BPM            # quarter note, seconds
_EIGHTH = _BEAT * 0.5

# soil-ring trigger radius by component type (world units)
RADII = {
    "drum": 70.0, "rhythm": 95.0, "note": 90.0, "chord": 110.0,
    "bass": 105.0, "loop": 120.0, "ambience": 140.0,
}
# rest time between rings, in beats, by type (this is the sequencing rule)
REST_BEATS = {
    "drum": 1, "rhythm": 4, "note": 2, "chord": 4,
    "bass": 4, "loop": 4, "ambience": 8,
}

# how loudly each family speaks in the mix (drums crisp, washes polite)
TYPE_GAIN = {"drum": 0.95, "rhythm": 0.95, "note": 1.0, "chord": 0.85,
             "bass": 0.9, "loop": 0.85, "ambience": 0.72}

MAX_SPROUTS = 160                    # plenty of garden, no runaway saves
PLANT_GAP = 34.0                     # sprouts keep a little personal soil


def plantable(comp):
    """Effects shape tracks in the Maker; everything else can live outdoors."""
    return comp is not None and comp.get("type") in RADII


class Sprout:
    __slots__ = ("comp_id", "x", "z", "planted_t",
                 "next_ok_beat", "pulse", "sway")

    def __init__(self, comp_id, x, z, planted_t=None):
        self.comp_id = comp_id
        self.x = x
        self.z = z
        self.planted_t = planted_t if planted_t is not None else time.time()
        self.next_ok_beat = 0.0      # garden-beat count when it may ring again
        self.pulse = 99.0            # seconds since last ring (drives the bloom)
        self.sway = (hash(comp_id) % 628) / 100.0

    @property
    def comp(self):
        return catalog.get(self.comp_id)


class SproutManager:
    """Owns every planted sprout: clock, triggers, drawing, saving, surveys."""

    def __init__(self, state, engine, clock=time.time):
        self.state = state
        self.engine = engine
        self.clock = clock           # injectable for tests
        self._t0 = clock()           # garden clock epoch
        self._pending = []           # (ring_at_beat, sprout) quantize queue
        self.sprouts = []
        for rec in state.data_list("sprouts"):
            try:
                s = Sprout(rec["c"], float(rec["x"]), float(rec["z"]),
                           rec.get("t"))
                if catalog.get(s.comp_id) is not None:
                    self.sprouts.append(s)
            except (KeyError, TypeError, ValueError):
                continue

    # -- the garden clock ---------------------------------------------------
    def beat(self):
        """Continuous beat count since the garden woke up this session."""
        return (self.clock() - self._t0) / _BEAT

    def beat_phase(self):
        return self.beat() % 1.0

    def shift_clock(self, seconds):
        """Exclude a real-time pause from the shared garden beat."""
        if seconds > 0:
            self._t0 += float(seconds)

    # -- persistence -----------------------------------------------------------
    def _save(self):
        return self.state.set_data_list(
            "sprouts",
            [{"c": s.comp_id, "x": round(s.x, 1), "z": round(s.z, 1),
              "t": s.planted_t} for s in self.sprouts])

    # -- planting / uprooting ---------------------------------------------------
    def can_plant_here(self, x, z):
        if len(self.sprouts) >= MAX_SPROUTS:
            return False, "The garden is full. Uproot a sprout before planting another one."
        for s in self.sprouts:
            if (s.x - x) ** 2 + (s.z - z) ** 2 < PLANT_GAP ** 2:
                return False, "A little too close to another sprout."
        return True, ""

    def plant(self, comp_id, x, z):
        ok, why = self.can_plant_here(x, z)
        if not ok:
            return None, why
        s = Sprout(comp_id, x, z)
        self.sprouts.append(s)
        if not self._save():
            self.sprouts.remove(s)
            return None, "The garden could not save that sprout. Please try again."
        return s, ""

    def nearest(self, x, z, max_dist=60.0):
        best, bd = None, max_dist * max_dist
        for s in self.sprouts:
            d2 = (s.x - x) ** 2 + (s.z - z) ** 2
            if d2 < bd:
                best, bd = s, d2
        return best

    def uproot(self, sprout):
        if sprout in self.sprouts:
            index = self.sprouts.index(sprout)
            self.sprouts.remove(sprout)
            if self._save():
                return True
            self.sprouts.insert(index, sprout)
            return False
        return False

    def count(self):
        return len(self.sprouts)

    # -- triggering -----------------------------------------------------------
    def _walkers(self, game):
        """Yield (key, kind, x, z) for everyone who can ring a sprout."""
        yield "cat", "cat", game.cat.x, game.cat.z
        for a in game.animals.animals():
            yield id(a), "animal", a.x, a.z

    def update(self, dt, game, muted=False):
        """Ring sprouts whose soil someone is standing in, on the grid."""
        now_b = self.beat()
        # remember where everyone was last frame, for doppler + attraction
        prev, self._last_pos = getattr(self, "_last_pos", {}), {}
        # fire anything whose quantize moment arrived
        still = []
        for ring_at, s, pan, dop, kind in self._pending:
            if now_b >= ring_at:
                comp = s.comp
                if comp is not None and not muted:
                    d = math.hypot(s.x - game.cat.x, s.z - game.cat.z)
                    vol = hearing(d) * TYPE_GAIN.get(comp.get("type"), 1.0)
                    if vol > 0.02:      # far rings spend no voice at all
                        self.engine.trigger_sprout(comp, vol=vol,
                                                   bpm=GARDEN_BPM,
                                                   pan=pan, doppler=dop)
                s.pulse = 0.0
                s.next_ok_beat = ring_at + REST_BEATS.get(comp.get("type"), 2)
                self._after_ring(game, s, kind)
            else:
                still.append((ring_at, s, pan, dop, kind))
        self._pending = still

        for s in self.sprouts:
            s.pulse += dt
            if now_b < s.next_ok_beat or any(p[1] is s for p in self._pending):
                continue
            comp = s.comp
            if comp is None:
                continue
            r2 = RADII.get(comp.get("type"), 90.0) ** 2
            for key, kind, wx, wz in self._walkers(game):
                self._last_pos[key] = (wx, wz)
                if (s.x - wx) ** 2 + (s.z - wz) ** 2 <= r2:
                    # snap to the next eighth so overlaps stay musical
                    next_eighth = math.ceil(now_b / 0.5 + 1e-6) * 0.5
                    # pan: where the sprout sits relative to Bal's ears
                    pan = 0.5 + max(-0.38, min(0.38,
                                               (s.x - game.cat.x) / 700.0))
                    # doppler: is the walker moving toward Bal or away?
                    dop = 0
                    if kind != "cat" and key in prev and dt > 0:
                        px, pz = prev[key]
                        d_now = math.hypot(wx - game.cat.x, wz - game.cat.z)
                        d_was = math.hypot(px - game.cat.x, pz - game.cat.z)
                        v_rad = (d_was - d_now) / dt   # + means approaching
                        if v_rad > 42.0:
                            dop = 1
                        elif v_rad < -42.0:
                            dop = -1
                    self._pending.append((next_eighth, s, pan, dop, kind))
                    s.next_ok_beat = next_eighth   # claim it now
                    break

    def _after_ring(self, game, s, kind):
        """A sprout just rang: keep the little ledgers and pull the garden in."""
        if kind == "animal":
            # distinct sprouts animals have played, for the animal-band work
            key = "%d_%d_%s" % (round(s.x), round(s.z), s.comp_id)
            played = self.state.data_dict("counters").setdefault("animal_rings", [])
            if key not in played:
                played.append(key)
                if len(played) > 40:
                    del played[:len(played) - 40]
                self.state.touch()
        # music pulls gently: a nearby idle animal may wander toward the ring
        for a in game.animals.animals():
            if getattr(a, "ai_state", "") in ("listen", "flee"):
                continue
            d2 = (a.x - s.x) ** 2 + (a.z - s.z) ** 2
            if 90.0 ** 2 < d2 < 340.0 ** 2 and (hash(id(a)) + int(s.pulse)) % 3 == 0:
                a.tx = s.x + (a.x - s.x) * 0.25
                a.tz = s.z + (a.z - s.z) * 0.25

    def animal_ring_count(self):
        return len(self.state.data_dict("counters").get("animal_rings", []))

    # -- drawing -----------------------------------------------------------------
    def world_drawables(self, cam, t, planning=False):
        out = []
        bp = self.beat_phase()
        for s in self.sprouts:
            pr = project_cull(s.x, s.z, cam)
            if pr is None:
                continue
            sx, sy, scale, fade = pr
            comp = s.comp
            if comp is None:
                continue

            resting = self.beat() < s.next_ok_beat

            def draw(surf, _s=s, _c=comp, _sx=sx, _sy=sy, _sc=scale,
                     _fd=fade, _bp=bp, _r=resting, _pl=planning):
                draw_sprout(surf, _sx, _sy, _sc, _fd, t, _c, _s.pulse,
                            _s.sway, _bp, resting=_r, planning=_pl)

            out.append((sy, 40, draw))
        return out

    # -- surveys: the readable geometry checks Garden Works use ---------------
    def by_pred(self, pred):
        out = []
        for s in self.sprouts:
            c = s.comp
            if c is not None and pred(c):
                out.append(s)
        return out

    def count_pred(self, pred):
        return len(self.by_pred(pred))

    def cluster(self, pred, radius, need):
        """Is there a spot where >= need matching sprouts sit within radius?
        (checked around each matching sprout -- readable and cheap)"""
        pts = self.by_pred(pred)
        r2 = radius * radius
        for a in pts:
            n = sum(1 for b in pts
                    if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= r2)
            if n >= need:
                return True
        return False

    def chain(self, pred, link_dist, need):
        """Longest chain of matching sprouts where each link is within
        link_dist of the next -- the 'plant a row you can walk' check."""
        pts = self.by_pred(pred)
        if not pts:
            return 0
        l2 = link_dist * link_dist
        best = 1
        adj = {i: [] for i in range(len(pts))}
        for i, a in enumerate(pts):
            for j in range(i + 1, len(pts)):
                b = pts[j]
                if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= l2:
                    adj[i].append(j)
                    adj[j].append(i)

        def walk(i, seen):
            top = len(seen)
            for j in adj[i]:
                if j not in seen:
                    top = max(top, walk(j, seen | {j}))
            return top

        for i in range(len(pts)):
            best = max(best, walk(i, {i}))
            if best >= need:
                break
        return best

    def loop_of(self, pred, link_dist, need):
        """True if a closed circuit of >= need matching sprouts exists
        (each within link_dist of the next, last linking back to first)."""
        pts = self.by_pred(pred)
        n = len(pts)
        if n < need:
            return False
        l2 = link_dist * link_dist
        adj = {i: set() for i in range(n)}
        for i in range(n):
            for j in range(i + 1, n):
                a, b = pts[i], pts[j]
                if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= l2:
                    adj[i].add(j)
                    adj[j].add(i)

        def cycle(start, cur, seen):
            if len(seen) >= need and start in adj[cur]:
                return True
            for j in adj[cur]:
                if j not in seen:
                    if cycle(start, j, seen | {j}):
                        return True
            return False

        return any(cycle(i, i, {i}) for i in range(n))
