"""Procedural meadow generation: scattered props in deterministic chunks.

Everything is derived from a per-launch world seed (see :mod:`config`) so a
given seed always rebuilds the exact same meadow.  Water carving is handled
separately in :mod:`cat_society.world.water`; :func:`land_allowed` is the rule
for whether a meadow prop is allowed to stand at a spot with a given water
depth."""

import random

from .. import config
from ..config import *
from ..utils import seed_hash


class Placed:
    __slots__ = ("kind", "x", "z")

    def __init__(self, kind, x, z):
        self.kind = kind
        self.x = x
        self.z = z


def land_allowed(kind, depth):
    """True if a normal meadow prop of this kind may stand here.

    depth is 0 on dry land and climbs toward 1 in deep water.  Trees and
    bushes stay out of any water, small props hug the dry edge, and shoreline
    stones may sit in the shallows."""
    if depth <= 0.0:
        return True
    if kind in ("tree", "bush"):
        return False
    if kind in ("stone", "pebble"):
        return depth < 0.22
    return depth < 0.12


class World:
    def __init__(self):
        self.scn = {}
        self.gcov = {}
        self.placed = {}

    def scenery(self, gx, gz):
        key = (gx, gz)
        cached = self.scn.get(key)
        if cached is not None:
            return cached

        # --- gameplay scenery: seeded from WORLD_SEED so the whole layout
        #     reshuffles each launch but stays stable within one run ---
        rng = random.Random(seed_hash(gx, gz, 0x5CE))
        items = []
        for _ in range(rng.randint(1, 3)):
            wx = gx * CHUNK + rng.uniform(0, CHUNK)
            wz = gz * CHUNK + rng.uniform(0, CHUNK)
            r = rng.random()
            if r < 0.60:
                kind = "tuft"
            elif r < 0.80:
                kind = "flower"
            elif r < 0.92:
                kind = "bush"
            elif r < 0.985:
                kind = "tree"
            else:
                kind = "stone"
            items.append((kind, wx, wz, rng.random()))

        # --- purely decorative dressing on a separate RNG, so it never disturbs
        #     the gameplay items above. all of these are passable (radius 0) ---
        drng = random.Random(seed_hash(gx, gz, 0xDEC0))
        for _ in range(drng.randint(0, 1)):
            wx = gx * CHUNK + drng.uniform(0, CHUNK)
            wz = gz * CHUNK + drng.uniform(0, CHUNK)
            r = drng.random()
            if r < 0.50:
                kind = "flower"
            elif r < 0.82:
                kind = "tuft"
            else:
                kind = "mushroom"
            items.append((kind, wx, wz, drng.random()))

        self.scn[key] = items
        return items

    def ground_cover(self, gx, gz):
        # dense passable grass + small blooms, kept in its own cache and only
        # gathered for nearby rows (see gather), so the meadow floor is lush up
        # close without paying to process thousands of specks at the horizon
        key = (gx, gz)
        cached = self.gcov.get(key)
        if cached is not None:
            return cached
        rng = random.Random(seed_hash(gx, gz, 0x6A55))
        items = []
        for _ in range(rng.randint(1, 3)):
            wx = gx * CHUNK + rng.uniform(0, CHUNK)
            wz = gz * CHUNK + rng.uniform(0, CHUNK)
            items.append(("tuft", wx, wz, rng.random()))
        # blooms come as a small coherent patch (one colour, clustered) instead
        # of lone multicolour specks, so they read as a designed flower bed
        if rng.random() < 0.38:
            px = gx * CHUNK + rng.uniform(0, CHUNK)
            pz = gz * CHUNK + rng.uniform(0, CHUNK)
            hue = rng.random()
            for _ in range(rng.randint(2, 3)):
                fx = px + rng.uniform(-22, 22)
                fz = pz + rng.uniform(-16, 16)
                items.append(("flower", fx, fz, hue))
        self.gcov[key] = items
        return items

    def place(self, kind, x, z):
        key = (int(x // CHUNK), int(z // CHUNK))
        obj = Placed(kind, x, z)
        self.placed.setdefault(key, []).append(obj)
        return obj

    def remove_near(self, x, z, reach=55.0):
        best = None
        best_key = None
        best_dd = reach * reach
        gx0 = int((x - reach) // CHUNK)
        gx1 = int((x + reach) // CHUNK)
        gz0 = int((z - reach) // CHUNK)
        gz1 = int((z + reach) // CHUNK)
        for gx in range(gx0, gx1 + 1):
            for gz in range(gz0, gz1 + 1):
                lst = self.placed.get((gx, gz))
                if not lst:
                    continue
                for obj in lst:
                    dd = (obj.x - x) ** 2 + (obj.z - z) ** 2
                    if dd < best_dd:
                        best_dd, best, best_key = dd, obj, (gx, gz)
        if best is not None:
            self.placed[best_key].remove(best)
            return True
        return False

    def gather(self, cam):
        scenery = []
        placed = []
        # gather out to where props fully dissolve into the haze (plus margin),
        # so the visible range matches the cull and nothing pops at the front
        draw_z = FOCAL * (1.0 / FADE_S_LO - 1.0)
        grass_z = FOCAL * (1.0 / GRASS_MIN_S - 1.0)
        gz0 = int((cam.z - 2 * CHUNK) // CHUNK)
        gz1 = int((cam.z + draw_z + 2 * CHUNK) // CHUNK)
        gz1_grass = int((cam.z + grass_z) // CHUNK)
        edge = 0.5 * config.W + int(config.W * 0.45) + 48      # screen half-width + draw margin
        cap = edge / max(0.03, FADE_S_LO * config.SC)
        grass_edge = 0.5 * config.W + 64                # tighter span for the grass layer
        max_xhalf = 0.0
        for gz in range(gz0, gz1 + 1):
            far_dz = (gz + 1) * CHUNK - cam.z
            d = far_dz + FOCAL
            scale = FOCAL / d if d > MIN_D else FOCAL / MIN_D
            xhalf = min(edge / max(0.03, scale * config.SC), cap)
            if xhalf > max_xhalf:
                max_xhalf = xhalf
            gx0 = int((cam.x - xhalf) // CHUNK)
            gx1 = int((cam.x + xhalf) // CHUNK)
            for gx in range(gx0, gx1 + 1):
                scenery.extend(self.scenery(gx, gz))
                p = self.placed.get((gx, gz))
                if p:
                    placed.extend(p)
            if gz <= gz1_grass:
                gxh = min(xhalf, grass_edge / max(0.03, scale * config.SC))
                for gx in range(int((cam.x - gxh) // CHUNK), int((cam.x + gxh) // CHUNK) + 1):
                    scenery.extend(self.ground_cover(gx, gz))
        if len(self.scn) > 4000:
            bound = max_xhalf + 2 * CHUNK
            self.scn = {(gx, gz): v for (gx, gz), v in self.scn.items()
                        if gz0 - 2 <= gz <= gz1 + 2 and abs(gx * CHUNK - cam.x) <= bound}
        if len(self.gcov) > 3000:
            gb = grass_edge / max(0.03, GRASS_MIN_S * config.SC) + 2 * CHUNK
            self.gcov = {(gx, gz): v for (gx, gz), v in self.gcov.items()
                         if gz0 - 2 <= gz <= gz1_grass + 2 and abs(gx * CHUNK - cam.x) <= gb}
        return scenery, placed

    def solids_near(self, x, z):
        out = []
        gx0 = int((x - COLLIDE_REACH) // CHUNK)
        gx1 = int((x + COLLIDE_REACH) // CHUNK)
        gz0 = int((z - COLLIDE_REACH) // CHUNK)
        gz1 = int((z + COLLIDE_REACH) // CHUNK)
        for gx in range(gx0, gx1 + 1):
            for gz in range(gz0, gz1 + 1):
                for kind, wx, wz, _ in self.scenery(gx, gz):
                    r = SOLID_R.get(kind, 0.0)
                    if r > 0.0:
                        out.append((r, wx, wz))
                lst = self.placed.get((gx, gz))
                if lst:
                    for obj in lst:
                        r = PLACED_R.get(obj.kind, 0.0)
                        if r > 0.0:
                            out.append((r, obj.x, obj.z))
        return out
