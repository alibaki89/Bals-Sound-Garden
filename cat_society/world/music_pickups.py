"""Endless, chunk-based musical component pickups.

Pickups belong to the *world*, not to the spawn point.  The infinite meadow is
divided into large cells; for every cell we deterministically decide -- from a
hash of ``(cell_x, cell_z, slot, GLOBAL_SEED)`` -- whether it holds a component
and where.  As the cat explores, the cells around it are generated on demand and
far cells are released, so musical things appear all over the endless world
forever.  Walk in any direction long enough and you keep finding new sounds.

Only a small handful of starter pickups sit near spawn; a clear zone keeps every
other pickup out of the immediate start area.  Curated (designed) components are
scattered across the world at fixed cells; every other occupied cell grows an
infinite procedural component.  Collected pickups are remembered by a stable
instance id (``pickup:cell_x:cell_z:slot``) so they never respawn.
"""

import math
import random

import pygame

from .. import config
from ..projection import project, project_cull
from ..components import catalog
from ..components import procedural
from ..components import rarity as _rarity
from ..ui.icons import draw_icon

COLLECT_RADIUS = 52.0       # walk this close (world units) -> auto-collect
GRAB_RADIUS = 120.0         # press E within this -> collect nearest
NEAR_GLOW_RADIUS = 240.0    # start sparkling when the cat is roughly this close

GLOBAL_SEED = 0x9114E5      # change -> a different (but still deterministic) world


class Pickup:
    __slots__ = ("comp", "x", "z", "phase", "iid")

    def __init__(self, comp, x, z, phase, iid):
        self.comp = comp
        self.x = x
        self.z = z
        self.phase = phase
        self.iid = iid


def _hash(*vals):
    """A stable 64-bit hash of integers (not Python's salted hash)."""
    h = 1469598103934665603
    for v in vals:
        v = int(v) & 0xFFFFFFFFFFFFFFFF
        h ^= (v + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        h = (h * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def _rand01(*vals):
    return (_hash(*vals) % 1_000_003) / 1_000_003.0


class PickupManager:
    """Generates and owns the pickups around the cat in the endless world."""

    CELL = 950.0                # pickup cell size (world units)
    R_START = 2000.0           # clear zone: only starters live inside this
    N_STARTERS = 5             # starter pickups near spawn (3-6)
    GEN_CELLS = 4              # generate cells within this many cells of the cat
    DROP_CELLS = 7             # release cells beyond this many cells
    MIN_DIST = 420.0           # strong minimum distance between pickups
    SOLID_MARGIN = 46.0        # keep this clear of tree / prop collision radius
    P0 = 450                   # /1000 chance a cell's main slot has a component
    P1 = 95                    # /1000 chance a cell also has a (rare) second
    R_CURATED_MAX = 14000.0    # curated components scatter within this radius

    def __init__(self, world, water, collection):
        self.world = world
        self.water = water
        self.collection = collection
        self._cells = {}                       # (cx,cz) -> [Pickup, ...]
        # (cx, cz, slot) -> curated component.  Slots 0/1 are the legacy
        # world layout; Sound Atlas additions live in slots 2/3 so old pickup
        # instance ids and already-explored saves remain stable.
        self._curated_at = {}
        self._starters = []                    # always-active near-spawn pickups
        self._assign_curated()
        self._place_starters()

    # -- one-time layout ----------------------------------------------------
    def _assign_curated(self):
        """Scatter curated components while preserving the original layout.

        The original hand-written catalog keeps its exact slot-0 algorithm so
        existing save files do not see old sounds move around.  The much larger
        Sound Atlas uses two additional deterministic slots per cell.  Those
        slots never existed in older builds, so they cannot collide with a
        procedural pickup the player already collected.
        """
        placed = catalog.placed_components()
        commons = [c for c in placed if c.get("rarity") == "common"]
        starter_pool = commons[:self.N_STARTERS]
        self._starter_pool = starter_pool
        starter_ids = {id(c) for c in starter_pool}
        rest = [c for c in placed if id(c) not in starter_ids]

        legacy = [c for c in rest if c.get("pack") != "sound_atlas"]
        atlas = [c for c in rest if c.get("pack") == "sound_atlas"]

        # Preserve the old one-component-per-cell mapping byte-for-byte.
        used_cells = set()
        used_slots = set()
        for i, comp in enumerate(legacy):
            rng = random.Random(_hash(i, 0xC07A7ED, GLOBAL_SEED))
            lo, hi = _rarity.band_units(comp.get("rarity", "common"))
            lo = max(lo, self.R_START)
            r2lo, r2hi = lo * lo, hi * hi
            cell = None
            for _ in range(80):
                rad = math.sqrt(rng.uniform(r2lo, r2hi))
                ang = rng.uniform(0, math.tau)
                cx = int(math.floor(math.cos(ang) * rad / self.CELL))
                cz = int(math.floor(math.sin(ang) * rad / self.CELL))
                if (cx, cz) in used_cells:
                    continue
                cell = (cx, cz)
                break
            if cell is None:
                cell = (i + 3, i % 7 + 3)
            used_cells.add(cell)
            used_slots.add((cell[0], cell[1], 0))
            self._curated_at[(cell[0], cell[1], 0)] = comp

        # Atlas discoveries use one additional slot in one unique cell each.
        # The wider nested bands are deliberate: thousands of authored sounds
        # should unfold over a very long exploration, not create dense piles or
        # appear all at once near the beginning.  Cells are restricted to the
        # landward side of the procedural coastline; otherwise a large arc of
        # each rarity ring would be deep ocean and finite authored sounds could
        # become permanently unreachable.
        atlas_bands = {
            "common": (2_000.0, 9_000.0),
            "uncommon": (6_000.0, 20_000.0),
            "rare": (14_000.0, 36_000.0),
            "secret": (28_000.0, 60_000.0),
        }
        for i, comp in enumerate(atlas):
            rng = random.Random(_hash(i, 0xA71A5, GLOBAL_SEED))
            lo, hi = atlas_bands.get(comp.get("rarity", "common"),
                                     atlas_bands["common"])
            lo = max(lo, self.R_START)
            r2lo, r2hi = lo * lo, hi * hi
            cell = None
            for _ in range(1800):
                rad = math.sqrt(rng.uniform(r2lo, r2hi))
                ang = rng.uniform(0, math.tau)
                cx = int(math.floor(math.cos(ang) * rad / self.CELL))
                cz = int(math.floor(math.sin(ang) * rad / self.CELL))
                if (cx, cz) in used_cells:
                    continue
                ccx = (cx + 0.5) * self.CELL
                ccz = (cz + 0.5) * self.CELL
                if ccx * ccx + ccz * ccz < (self.R_START + 180.0) ** 2:
                    continue
                if not self._atlas_cell_is_landward(cx, cz):
                    continue
                cell = (cx, cz)
                break

            if cell is None:
                # Deterministic expanding perimeter.  Every Atlas sound gets a
                # unique cell even if a future expansion outgrows a rarity band.
                ring = int(math.ceil(hi / self.CELL)) + 1
                while cell is None:
                    edge = max(1, ring * 2)
                    perimeter = edge * 4
                    offset = _hash(i, ring, GLOBAL_SEED) % perimeter
                    for n in range(perimeter):
                        k = (offset + n) % perimeter
                        side, pos = divmod(k, edge)
                        if side == 0:
                            candidate = (-ring + pos, -ring)
                        elif side == 1:
                            candidate = (ring, -ring + pos)
                        elif side == 2:
                            candidate = (ring - pos, ring)
                        else:
                            candidate = (-ring, ring - pos)
                        if (candidate not in used_cells
                                and self._atlas_cell_is_landward(*candidate)):
                            cell = candidate
                            break
                    ring += 1

            used_cells.add(cell)
            key = (cell[0], cell[1], 2)
            used_slots.add(key)
            self._curated_at[key] = comp


    @classmethod
    def _atlas_cell_is_landward(cls, cx, cz):
        """Return True when Atlas slot 2 is safely before the open sea.

        The coastline bends between ``COAST_Z - COAST_AMP`` and
        ``COAST_Z + COAST_AMP``.  Slot 2 samples the first 40% of a cell on
        the z axis, so keeping that entire sampling strip before the minimum
        shoreline guarantees that an authored discovery is never assigned to
        deep ocean.  Rivers, ponds and props are handled later by
        :meth:`_find_in_cell`.
        """
        atlas_strip_far_z = cz * cls.CELL + 0.40 * cls.CELL
        return atlas_strip_far_z <= config.COAST_Z - config.COAST_AMP

    def _place_starters(self):
        """A few curated commons just outside the very centre so the player
        finds something quickly, then the world takes over."""
        pool = list(getattr(self, "_starter_pool", []))
        n = max(3, min(6, self.N_STARTERS))
        for i in range(min(n, len(pool))):
            comp = pool[i]
            spot = None
            for attempt in range(40):
                ang = (i / max(1, n)) * math.tau + _rand01(i, attempt, 5) * 1.2
                rad = 650.0 + _rand01(i, attempt, 9) * (self.R_START - 800.0)
                x = math.cos(ang) * rad
                z = math.sin(ang) * rad
                if self.water.depth_at(x, z)[0] > 0.0:
                    continue
                if self._on_solid(x, z):
                    continue
                if self._too_close(x, z, self._starters, self.MIN_DIST):
                    continue
                spot = (x, z)
                break
            if spot is None:
                spot = self.water.nearest_dry(math.cos(i) * 900, math.sin(i) * 900)
            iid = "pickup:start:%d" % i
            if self.collection.pickup_collected(iid):
                continue
            self._starters.append(Pickup(comp, spot[0], spot[1],
                                         _rand01(i, 7) * math.tau, iid))

    # -- validation ---------------------------------------------------------
    def _on_solid(self, x, z):
        for (r, wx, wz) in self.world.solids_near(x, z):
            rr = r + self.SOLID_MARGIN
            if (x - wx) * (x - wx) + (z - wz) * (z - wz) < rr * rr:
                return True
        return False

    @staticmethod
    def _too_close(x, z, pickups, min_dist):
        md2 = min_dist * min_dist
        for p in pickups:
            if (p.x - x) * (p.x - x) + (p.z - z) * (p.z - z) < md2:
                return True
        return False

    # -- chunk generation ---------------------------------------------------
    def _cell_of(self, x, z):
        return int(math.floor(x / self.CELL)), int(math.floor(z / self.CELL))

    def _ensure_near(self, cat):
        ccx, ccz = self._cell_of(cat.x, cat.z)
        for dx in range(-self.GEN_CELLS, self.GEN_CELLS + 1):
            for dz in range(-self.GEN_CELLS, self.GEN_CELLS + 1):
                key = (ccx + dx, ccz + dz)
                if key not in self._cells:
                    self._cells[key] = self._gen_cell(key)
        if len(self._cells) > (2 * self.DROP_CELLS + 1) ** 2 + 8:
            for key in list(self._cells):
                if abs(key[0] - ccx) > self.DROP_CELLS or abs(key[1] - ccz) > self.DROP_CELLS:
                    del self._cells[key]

    def _gen_cell(self, key):
        cx, cz = key
        out = []

        # Run the historical slot-0/1 loop first and in exactly the original
        # order.  That preserves procedural pickup existence, coordinates,
        # spacing and instance ids for old saves, even when the same cell now
        # also contains a Sound Atlas discovery.
        for slot in range(2):
            curated = self._curated_at.get((cx, cz, slot))
            if curated is not None:
                comp = curated
            else:
                chance = self.P0 if slot == 0 else self.P1
                if _hash(cx, cz, slot, 0xB175, GLOBAL_SEED) % 1000 >= chance:
                    continue
                comp = None
            iid = "pickup:%d:%d:%d" % (cx, cz, slot)
            if self.collection.pickup_collected(iid):
                continue
            spot = self._find_in_cell(cx, cz, slot, out)
            if spot is None:
                continue
            if comp is None:
                seed = _hash(cx, cz, slot, 0x9D0, GLOBAL_SEED) & 0x7FFFFFFF
                comp = procedural.generate(seed)
            out.append(Pickup(comp, spot[0], spot[1],
                              _rand01(cx, cz, slot, 7) * math.tau, iid))

        # New authored discoveries use reserved slots after the old world has
        # made its choices.  Their fallback logic guarantees reachability even
        # in a cell that already contains one or two legacy pickups.
        for slot in (2, 3):
            comp = self._curated_at.get((cx, cz, slot))
            if comp is None:
                continue
            iid = "pickup:%d:%d:%d" % (cx, cz, slot)
            if self.collection.pickup_collected(iid):
                continue
            spot = self._find_in_cell(cx, cz, slot, out)
            if spot is None:
                continue
            out.append(Pickup(comp, spot[0], spot[1],
                              _rand01(cx, cz, slot, 7) * math.tau, iid))
        return out

    def _find_in_cell(self, cx, cz, slot, placed_here):
        """Deterministic attempts for a readable spot inside this cell: dry land,
        clear of solids, outside the spawn clear zone, spaced from neighbours."""
        bx = cx * self.CELL
        bz = cz * self.CELL
        # Preserve the exact legacy slot-0/1 position formula.  Atlas slots
        # occupy the two unused opposite quadrants, giving a four-slot cell
        # enough visual and collection spacing without moving old pickups.
        r2_start = self.R_START * self.R_START
        attempts = 8 if slot < 2 else 20
        readable_fallback = None
        for attempt in range(attempts):
            if slot < 2:
                fx = 0.18 + 0.64 * _rand01(cx, cz, slot, attempt, 11)
                fz_lo = 0.12 if slot == 0 else 0.62
                fz = fz_lo + 0.26 * _rand01(cx, cz, slot, attempt, 23)
            elif slot == 2:             # upper-right
                fx = 0.62 + 0.26 * _rand01(cx, cz, slot, attempt, 11)
                fz = 0.12 + 0.26 * _rand01(cx, cz, slot, attempt, 23)
            else:                       # lower-left
                fx = 0.12 + 0.26 * _rand01(cx, cz, slot, attempt, 11)
                fz = 0.62 + 0.26 * _rand01(cx, cz, slot, attempt, 23)
            x = bx + fx * self.CELL
            z = bz + fz * self.CELL
            if x * x + z * z < r2_start:
                continue
            if self.water.depth_at(x, z)[0] > 0.0:
                continue
            if self._on_solid(x, z):
                continue
            if slot >= 2 and readable_fallback is None:
                readable_fallback = (x, z)
            min_dist = self.MIN_DIST if slot < 2 else 250.0
            if self._too_close(x, z, placed_here, min_dist):
                continue
            return (x, z)
        # Atlas discoveries are finite authored content: if a crowded cell has
        # dry, obstacle-free ground but cannot satisfy the preferred spacing,
        # keep the sound reachable instead of silently deleting it.  If the
        # whole quadrant is wet, ask the water system for nearby dry land and
        # validate a small ring around it.  Legacy slots retain their old strict
        # behavior and therefore their exact historical layout.
        if slot >= 2:
            if readable_fallback is not None:
                return readable_fallback
            tx = bx + (0.75 if slot == 2 else 0.25) * self.CELL
            tz = bz + (0.25 if slot == 2 else 0.75) * self.CELL
            nx, nz = self.water.nearest_dry(tx, tz)
            for radius in (0.0, 70.0, 140.0, 220.0):
                for turn in range(8):
                    ang = turn * math.tau / 8.0
                    x = nx + math.cos(ang) * radius
                    z = nz + math.sin(ang) * radius
                    if x * x + z * z < r2_start:
                        continue
                    if self.water.depth_at(x, z)[0] > 0.0 or self._on_solid(x, z):
                        continue
                    return (x, z)
        return None

    # -- active pickup iteration -------------------------------------------
    def _active(self):
        """Yield every currently-loaded uncollected pickup (starters + cells)."""
        for p in self._starters:
            if not self.collection.owns(p.comp["id"]):
                yield p
        for lst in self._cells.values():
            for p in lst:
                if not self.collection.owns(p.comp["id"]):
                    yield p

    # -- collection ---------------------------------------------------------
    def update(self, dt, cat):
        """Generate nearby cells, then auto-collect any pickup the cat reached.

        Returns the components newly collected this frame.
        """
        self._ensure_near(cat)
        found = []
        cx, cz = cat.x, cat.z
        for p in self._active():
            if abs(p.x - cx) > COLLECT_RADIUS or abs(p.z - cz) > COLLECT_RADIUS:
                continue
            if math.hypot(p.x - cx, p.z - cz) <= COLLECT_RADIUS:
                if self._take(p):
                    found.append(p.comp)
        return found

    def _take(self, pickup):
        """Mark a pickup collected: add its component to the library and record
        its instance id so it never respawns."""
        self.collection.mark_pickup(pickup.iid)
        comp = pickup.comp
        if comp.get("starter"):
            return True                         # already owned, just consumed
        return self.collection.collect(comp["id"]) or True

    def grab_nearest(self, cat):
        cx, cz = cat.x, cat.z
        best, best_d = None, GRAB_RADIUS
        for p in self._active():
            d = math.hypot(p.x - cx, p.z - cz)
            if d <= best_d:
                best_d, best = d, p
        if best is not None and self._take(best):
            return best.comp
        return None

    def nearest_comp(self, cat):
        """The nearest uncollected pickup's component within grab range (for the
        on-screen 'press E' prompt)."""
        cx, cz = cat.x, cat.z
        best, best_d = None, GRAB_RADIUS
        for p in self._active():
            d = math.hypot(p.x - cx, p.z - cz)
            if d <= best_d:
                best_d, best = d, p.comp
        return best

    def remaining(self):
        return sum(1 for _ in self._active())

    # -- rendering (depth-sorted into the world) ---------------------------
    def world_drawables(self, cam, t, cat):
        """Return ``(sort_y, 40, draw_fn)`` entries for every visible pickup.

        The sort key is the pickup's projected *ground* screen-y, so the pickup
        occludes / is occluded by trees, props, animals and the cat exactly like
        a real world object.  Pickups fade out with distance the same way world
        props do, so far ones stay small, low and subtle instead of floating.
        """
        self._ensure_near(cat)
        cx, cz = cat.x, cat.z
        out = []
        for p in self._active():
            pr = project_cull(p.x, p.z, cam)
            if pr is None:
                continue
            sx, sy, scale, haze = pr            # haze: 0 near .. 1 far
            vis = 1.0 - haze                    # how visible / opaque it should be
            if vis <= 0.06:
                continue
            out.append((sy, 40,
                        (lambda surf, sx=sx, sy=sy, sc=scale, vv=vis, pp=p:
                         self._draw_one(surf, sx, sy, sc, pp, t, cx, cz, vv))))
        return out

    def _draw_one(self, surf, sx, sy, scale, p, t, cx, cz, vis=1.0):
        comp = p.comp
        color = tuple(comp.get("color", (230, 220, 180)))
        # icon size comes straight from the projection scale -- no forced minimum
        # that would bloat a distant pickup into a floating beacon
        size = 13.5 * scale * config.SC
        dist = math.hypot(p.x - cx, p.z - cz)
        near = dist < NEAR_GLOW_RADIUS
        near_frac = max(0.0, min(1.0, 1.0 - dist / NEAR_GLOW_RADIUS))
        if near:
            size = max(size, 4.5 * near_frac)   # a tiny readability floor, only up close
        if size < 1.0:
            return
        rarity = comp.get("rarity", "common")
        glow_boost = {"common": 0.0, "uncommon": 0.3, "rare": 0.7, "secret": 1.1}.get(rarity, 0.0)
        pulse = 0.5 + 0.5 * math.sin(t * 3.0 + p.phase)
        # hover + bob shrink with the projection, so far pickups sit on the ground
        hfac = min(1.0, scale / 0.55)
        hover = size * 2.4 * hfac
        bob = math.sin(t * 2.1 + p.phase) * size * 0.4 * hfac
        iy = sy - hover + bob

        # ground shadow (fades out with distance)
        sa = int(70 * vis)
        if sa > 4 and size >= 1.5:
            shadow = pygame.Surface((int(size * 2.6), int(size * 1.3)), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (40, 36, 30, sa), shadow.get_rect())
            surf.blit(shadow, (int(sx - size * 1.3), int(sy - size * 0.65)))

        # rare/secret light beam: only strong when reasonably near, gone far away
        if glow_boost >= 0.7 and near_frac > 0.05:
            beam_str = near_frac * vis
            beam_h = int(size * (4.0 + 2.0 * pulse))
            bw = max(2, int(size * 1.4))
            if beam_h > 2 and beam_str > 0.02:
                beam = pygame.Surface((bw, beam_h), pygame.SRCALPHA)
                for k in range(beam_h):
                    a = int((1.0 - k / beam_h) * (24 + 16 * glow_boost) * beam_str)
                    if a > 0:
                        pygame.draw.line(beam, (*color, a), (bw // 2 - 1, k), (bw // 2 + 1, k))
                surf.blit(beam, (int(sx - bw // 2), int(iy - beam_h)))

        # glow halo: scales with projection, alpha fades with distance and nearness
        glow_r = int(size * (2.0 + glow_boost) + pulse * size * 0.6 * near_frac)
        if glow_r > 0 and vis > 0.1:
            base_a = (40 + 54 * glow_boost) * vis * (0.45 + 0.55 * near_frac)
            a1 = int(base_a + 28 * pulse * near_frac)
            if a1 > 3:
                glow = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*color, min(130, a1)), (glow_r, glow_r), glow_r)
                pygame.draw.circle(glow, (*color, min(170, a1 + 30)), (glow_r, glow_r), int(glow_r * 0.6))
                pygame.draw.circle(glow, (*_light(color), min(190, a1 + 40)),
                                   (glow_r, glow_r), int(glow_r * 0.32))
                surf.blit(glow, (int(sx - glow_r), int(iy - glow_r)))

        # the icon itself -- fade by distance via a temp surface when not full opacity
        if vis >= 0.985:
            draw_icon(surf, sx, iy, size, color, comp.get("icon", "note"), t)
        else:
            dim = int(size * 2) + 16
            tmp = pygame.Surface((dim, dim), pygame.SRCALPHA)
            draw_icon(tmp, dim // 2, dim // 2, size, color, comp.get("icon", "note"), t)
            tmp.set_alpha(int(255 * vis))
            surf.blit(tmp, (int(sx - dim // 2), int(iy - dim // 2)))

        # orbiting motes -- only up close, and faded with distance
        if near and size >= 2.0:
            for k in range(4):
                a = t * 2.4 + p.phase + k * (math.tau / 4)
                rr = size * (1.5 + 0.45 * math.sin(t * 4 + k))
                mx = sx + math.cos(a) * rr
                my = iy + math.sin(a) * rr * 0.7
                ms = max(1, int(size * 0.16))
                if vis >= 0.99:
                    pygame.draw.circle(surf, (255, 250, 232), (int(mx), int(my)), ms)
                else:
                    dot = pygame.Surface((ms * 2 + 2, ms * 2 + 2), pygame.SRCALPHA)
                    pygame.draw.circle(dot, (255, 250, 232), (ms + 1, ms + 1), ms)
                    dot.set_alpha(int(255 * vis))
                    surf.blit(dot, (int(mx - ms - 1), int(my - ms - 1)))


def _light(c):
    return tuple(min(255, int(v + 55)) for v in c)
