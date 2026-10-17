"""Decides where animals live and keeps the live ones tidy.

The world is huge, so we cannot keep every animal alive at once.  Instead the
map is cut into big square *cells*.  Each cell has a fixed, seeded recipe for
what spawns there (same idea the scenery uses), so the wildlife near a spot is
consistent for the whole play session.  As the cat walks, cells nearby wake up
and spawn their animals, and cells far behind go quiet again.

The manager also does the per-frame chores the individual animals cannot do on
their own: it knows where the trees, stones and cat are, so it pushes animals
out of things they should not stand inside, and it tells water animals how deep
they are wading.
"""

import math
import random

from .. import config
from ..config import CHUNK, CAT_R
from ..utils import seed_hash, clamp
from ..entities.animals import Animal, SPECIES


# --- tuning knobs -----------------------------------------------------------
ANIMAL_CELL = CHUNK * 3          # ~780 world units per spawn cell (sparse)
SPAWN_RADIUS = ANIMAL_CELL * 2.2   # cells this close to the cat are populated
DESPAWN_RADIUS = ANIMAL_CELL * 3.0  # cells past this are dropped
MAX_ANIMALS = 26                 # hard ceiling on live creatures
PER_CELL_MAX = 2                 # most a single cell will ever hold
_SALT = 0xA17A1                  # keeps animal seeds away from scenery seeds

# water depth gates (kept loose; the exact bank thresholds live in water.py)
_DRY = 0.04                      # land animals want their feet on this
_WADE_OK = 0.5                   # how deep a water animal will happily go
_WET = 0.06                      # past this counts as "in the water"

# species grouped by where they belong, so a patch of land can pick a fitting
# resident instead of dropping a cow in the forest
_OPEN_POOL = [k for k, s in SPECIES.items() if s.habitat in ("meadow", "farm")]
_FOREST_POOL = [k for k, s in SPECIES.items() if s.habitat == "forest"]
_RARE_POOL = [k for k, s in SPECIES.items() if s.habitat == "rare_forest"]
_WATER_POOL = [k for k, s in SPECIES.items() if s.habitat == "water_edge"]


def _weighted(rng, pool):
    """Pick one species key from a pool, biased by its spawn weight."""
    if not pool:
        return None
    total = sum(SPECIES[k].weight for k in pool)
    r = rng.uniform(0.0, total)
    upto = 0.0
    for k in pool:
        upto += SPECIES[k].weight
        if r <= upto:
            return k
    return pool[-1]


class AnimalManager:
    """Spawns, updates, and hands out the world's animals."""

    def __init__(self, world, water, seed=0):
        self.world = world
        self.water = water
        self.seed = seed
        self.cells = {}          # cell_key -> list[Animal]

    # -- terrain helpers ---------------------------------------------------
    def _tree_count(self, x, z, reach=150.0):
        """How many trees sit near a point (forest-ness of a spot)."""
        n = 0
        gx0 = int((x - reach) // CHUNK)
        gx1 = int((x + reach) // CHUNK)
        gz0 = int((z - reach) // CHUNK)
        gz1 = int((z + reach) // CHUNK)
        rr = reach * reach
        for gx in range(gx0, gx1 + 1):
            for gz in range(gz0, gz1 + 1):
                for kind, wx, wz, _r in self.world.scenery(gx, gz):
                    if kind == "tree" and (wx - x) ** 2 + (wz - z) ** 2 < rr:
                        n += 1
        return n

    def _water_near(self, x, z, reach=130.0):
        """True if there is reachable water within ``reach`` of a point."""
        for r in (40, 80, reach):
            for a in range(0, 360, 45):
                ang = math.radians(a)
                if self.water.depth_at(x + math.cos(ang) * r,
                                       z + math.sin(ang) * r)[0] > 0.12:
                    return True
        return False

    # -- spawn recipe for one cell ----------------------------------------
    def _populate_cell(self, cx, cz):
        rng = random.Random(seed_hash(cx, cz, _SALT))
        animals = []

        roll = rng.random()
        if roll < 0.42:
            count = 0
        elif roll < 0.85:
            count = 1
        else:
            count = PER_CELL_MAX

        for _ in range(count):
            x = cx * ANIMAL_CELL + rng.uniform(0, ANIMAL_CELL)
            z = cz * ANIMAL_CELL + rng.uniform(0, ANIMAL_CELL)

            # the spot must be standable land (animals wade in on their own)
            if self.water.depth_at(x, z)[0] > _DRY:
                continue

            # classify the ground and pick a fitting resident
            if self._water_near(x, z):
                pool = _WATER_POOL + _OPEN_POOL
            else:
                trees = self._tree_count(x, z)
                if trees >= 2 and rng.random() < 0.5:
                    pool = _FOREST_POOL + _RARE_POOL
                elif trees >= 1:
                    pool = _FOREST_POOL
                else:
                    pool = _OPEN_POOL

            key = _weighted(rng, pool)
            if key is None:
                continue
            animals.append(Animal(key, x, z, random.Random(rng.random() * 1e9)))

        return animals

    # -- per-frame update --------------------------------------------------
    def update(self, dt, cat, song=None, night=0.0, minutes=720.0,
               exclusion_zones=None):
        cat_x, cat_z = cat.x, cat.z
        water = self.water
        exclusion_zones = tuple(exclusion_zones or ())

        def excluded(x, z):
            for cx, cz, rx, rz in exclusion_zones:
                if rx > 0.0 and rz > 0.0 and (((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 <= 1.0):
                    return True
            return False

        # shared context handed to every animal's brain this frame
        def valid(x, z, aquatic):
            # every creature may cross water now; the timid ones simply
            # prefer not to *aim* for the deep end
            d = water.depth_at(x, z)[0]
            return d <= (_WADE_OK if aquatic else _WADE_OK * 0.8)

        def in_water(x, z):
            return water.depth_at(x, z)[0] > _WET

        ctx = {"cat_x": cat_x, "cat_z": cat_z, "valid": valid,
               "depth": lambda px, pz: self.water.depth_at(px, pz)[0],
               "in_water": in_water, "song": song,
               "night": float(night), "minutes": float(minutes)}

        # wake up nearby cells
        cell_cx = int(cat_x // ANIMAL_CELL)
        cell_cz = int(cat_z // ANIMAL_CELL)
        span = int(SPAWN_RADIUS // ANIMAL_CELL) + 1
        for dcx in range(-span, span + 1):
            for dcz in range(-span, span + 1):
                key = (cell_cx + dcx, cell_cz + dcz)
                if key in self.cells:
                    continue
                ccx = (key[0] + 0.5) * ANIMAL_CELL
                ccz = (key[1] + 0.5) * ANIMAL_CELL
                if math.hypot(ccx - cat_x, ccz - cat_z) <= SPAWN_RADIUS:
                    self.cells[key] = [a for a in self._populate_cell(*key)
                                       if not excluded(a.x, a.z)]

        # retire distant cells
        for key in list(self.cells.keys()):
            ccx = (key[0] + 0.5) * ANIMAL_CELL
            ccz = (key[1] + 0.5) * ANIMAL_CELL
            if math.hypot(ccx - cat_x, ccz - cat_z) > DESPAWN_RADIUS:
                del self.cells[key]

        if exclusion_zones:
            for key in list(self.cells):
                self.cells[key] = [a for a in self.cells[key] if not excluded(a.x, a.z)]

        # keep the population under the ceiling (drop the farthest first)
        total = sum(len(v) for v in self.cells.values())
        if total > MAX_ANIMALS:
            ranked = sorted(
                self.cells.keys(),
                key=lambda k: math.hypot((k[0] + 0.5) * ANIMAL_CELL - cat_x,
                                         (k[1] + 0.5) * ANIMAL_CELL - cat_z),
                reverse=True,
            )
            for key in ranked:
                if total <= MAX_ANIMALS:
                    break
                total -= len(self.cells[key])
                del self.cells[key]

        # advance + de-collide every live animal
        live = self.animals()
        for a in live:
            a.update(dt, ctx)
            self._resolve_solids(a)
            self._resolve_cat(a, cat, dt)
            # anyone standing in water sinks to match how deep it is --
            # semi-aquatics look at home, everyone else paddles gamely
            depth = water.depth_at(a.x, a.z)[0]
            a.swim = water.submerge_for_depth(depth) if depth > 0.0 else 0.0
        self._separate(live)
        # spacing animals apart can re-nudge one into Bal: settle that too,
        # so the frame always ends with nobody standing inside anybody
        for a in live:
            self._resolve_cat(a, cat, dt)

    # -- collision helpers -------------------------------------------------
    def _resolve_solids(self, a):
        for r, wx, wz in self.world.solids_near(a.x, a.z):
            if r <= 0:
                continue
            dx = a.x - wx
            dz = a.z - wz
            dd = dx * dx + dz * dz
            reach = r + a.spec.radius
            if dd < reach * reach and dd > 1e-6:
                dist = math.sqrt(dd)
                push = (reach - dist)
                a.x += dx / dist * push
                a.z += dz / dist * push

    # Everything here is drawn side-on: long from nose to tail (world x),
    # thin front-to-back (world z).  A round footprint matches only the
    # torso, so heads and tails ghost through each other while passing.
    # These are half-lengths of an OVAL footprint instead, tuned to the
    # sprites.  LEN is the nose-to-tail half-reach, SIDE the depth one.
    CAT_LEN = 30.0
    CAT_SIDE = 15.0
    LEN_FIT = 1.85          # animal half-length  = radius * LEN_FIT
    SIDE_FIT = 1.15         # animal half-depth   = radius * SIDE_FIT
    # kept for the test-suite / tuning conversation: the torso-only reach
    CAT_BODY = 24.0
    BODY_FIT = 1.6

    @staticmethod
    def _oval_push(dx, dz, ax, az):
        """Penetration vector for an oval of half-axes (ax, az).

        Work in a squashed space where the oval is a unit circle, find how
        far outside the point must move along its ray, map back.  Returns
        (px, pz) -- the world-space vector that carries the offset onto the
        oval's rim -- or None when already clear."""
        u = dx / ax
        v = dz / az
        m = math.hypot(u, v)
        if m >= 1.0:
            return None
        if m < 1e-6:
            return (ax, 0.0)
        f = 1.0 / m - 1.0
        return (dx * f, dz * f)

    def _resolve_cat(self, a, cat, dt=1.0 / 60.0):
        """Soft in *feel*, solid in *fact*.

        The overlap is fully separated every frame -- Bal genuinely cannot
        stand inside an animal, however fast he presses in.  The coziness
        comes from who yields (small creatures scoot, heavy ones stand
        their ground and Bal slides) and from a sideways shear that turns
        head-on meetings into a polite step around each other."""
        dx = a.x - cat.x
        dz = a.z - cat.z
        # bodies block at their DRAWN size and SHAPE: an oval long enough
        # to cover nose and tail, thin enough that side-by-side passing in
        # depth still feels easy
        ax = self.CAT_LEN + a.spec.radius * self.LEN_FIT
        az = self.CAT_SIDE + a.spec.radius * self.SIDE_FIT
        pv = self._oval_push(dx, dz, ax, az)
        if pv is None:
            return
        px, pz = pv
        push = math.hypot(px, pz)               # resolve ALL of it, now
        nx, nz = px / push, pz / push
        # who yields: tiny animals mostly scoot, heavy ones mostly stand,
        # so a cow feels like a cow and a bird feels like a bird
        k = max(0.0, min(1.0, (a.spec.radius - 6.0) / 14.0))
        animal_share = 0.85 - 0.55 * k          # bird .85 .. cow .30
        a.x += nx * push * animal_share
        a.z += nz * push * animal_share
        cat.x -= nx * push * (1.0 - animal_share)
        cat.z -= nz * push * (1.0 - animal_share)
        # everyone passes on the right: the animal steps to one side of the
        # contact, Bal drifts to the other, and the meeting flows past
        # itself instead of becoming a shoving match
        slip = push * 0.5
        a.x += -nz * slip
        a.z += nx * slip
        cat.x += -nz * push * 0.22 * -1.0
        cat.z += nx * push * 0.22 * -1.0

    def _separate(self, live):
        # gentle nudge so animals do not pile into one blob
        n = len(live)
        for i in range(n):
            a = live[i]
            for j in range(i + 1, n):
                b = live[j]
                dx = a.x - b.x
                dz = a.z - b.z
                # same side-view oval as Bal's: long nose-to-tail, thin in
                # depth, so grazing herds stop overlapping at the ends
                ax = (a.spec.radius + b.spec.radius) * self.LEN_FIT * 0.8
                az = (a.spec.radius + b.spec.radius) * self.SIDE_FIT * 0.8
                pv = self._oval_push(dx, dz, ax, az)
                if pv is not None:
                    a.x += pv[0] * 0.5
                    a.z += pv[1] * 0.5
                    b.x -= pv[0] * 0.5
                    b.z -= pv[1] * 0.5

    # -- access ------------------------------------------------------------
    def animals(self):
        out = []
        for v in self.cells.values():
            out.extend(v)
        return out
