"""The water biome: rivers, ponds, lakes and the sea, plus the cat's wading
and swimming response to them.

This module owns the *geometry and behaviour* of water (where it is, how deep
it is, where bridges and boats sit, what is dry land).  The matching *drawing*
lives in :mod:`cat_society.render.water` (in-water sprites) and
:mod:`cat_society.render.structures` (bridges, boats, wells, fountains).  The
animated water surface is drawn by :meth:`WaterWorld.draw_surface`, which is
kept here because it is tightly coupled to the depth field above it."""

import math
import random

from .. import config
from ..config import *
from ..utils import seed_hash, _h01, clamp, smooth01, lerp_color, ground_color_at, ri
from ..palette import *
from ..projection import project, project_cull


# Rivers march across x in fixed lanes; this constant offsets the whole set so
# the world is not symmetric about x=0.  It needs the world seed, so it is the
# one derived water value that lives here rather than in config.
RIVER_OFF = RIVER_LANE * 0.5 + (seed_hash(404) % 480) - 240.0


def lane_half(k):
    """Half-width of river lane k.  Some lanes are thin streams, most are
    proper wide rivers, and the width varies lane to lane."""
    r = _h01(k, 0x5717)
    if r < 0.30:
        return 17.0 + 11.0 * _h01(k, 0x2A)      # thin stream  ~17-28
    return 48.0 + 70.0 * _h01(k, 0x9C)          # wide river    ~48-118


def lane_cx(k, z):
    """Centre-x of river lane k at depth z.  A big slow term tilts the river
    diagonally, smaller terms add gentle meander.  Stays inside its lane so
    neighbouring rivers never merge."""
    home = k * RIVER_LANE + RIVER_OFF
    ph = _h01(k, 7) * 6.2832
    a1 = 210.0 + 250.0 * _h01(k, 11)            # diagonal sweep amplitude
    meander = (a1 * math.sin(z * 0.00034 + ph)
               + 90.0 * math.sin(z * 0.00120 + ph * 1.7)
               + 32.0 * math.sin(z * 0.00330 + ph * 0.5))
    # keep the channel comfortably within its lane
    limit = RIVER_LANE * 0.5 - lane_half(k) - 40.0
    if limit < 0.0:
        limit = 0.0
    return home + clamp(meander, -limit, limit)


def lanes_near_x(x):
    """The handful of river lanes whose channels could touch this x."""
    k0 = int(math.floor((x - RIVER_OFF) / RIVER_LANE))
    return (k0 - 1, k0, k0 + 1, k0 + 2)


def rivers_depth(x, z):
    """0 on land, climbing toward 1 at a river's centre.  Rivers fade out once
    they reach the sea so they don't fight the coastline."""
    if z > COAST_Z + 160.0:
        return 0.0
    best = 0.0
    for k in lanes_near_x(x):
        hw = lane_half(k)
        d = abs(x - lane_cx(k, z))
        if d < hw:
            t = 1.0 - d / hw
            # shallow at the banks, deep in the middle
            dep = 0.30 + 0.70 * smooth01(t)
            if dep > best:
                best = dep
    return best


def coast_z_at(x):
    """World-z of the shoreline at this x (sea is beyond)."""
    p = _h01(900) * 6.2832
    return (COAST_Z
            + COAST_AMP * 0.66 * math.sin(x * 0.00085 + p)
            + COAST_AMP * 0.25 * math.sin(x * 0.0023 + p * 1.7)
            + COAST_AMP * 0.09 * math.sin(x * 0.0060 + p * 0.5))


class WaterProp:
    __slots__ = ("kind", "x", "z", "spark", "facing", "t", "occupied")

    def __init__(self, kind, x, z):
        self.kind = kind
        self.x = x
        self.z = z
        self.spark = 0.0
        self.facing = 1
        self.t = 0.0
        self.occupied = False


class WaterWorld:
    def __init__(self):
        # ponds and lakes are generated per-cell on demand and cached here, so
        # water keeps appearing as the player explores the endless world
        self.basin_cells = {}     # (cx, cz) -> list of (x, z, a, b, seed, kind)
        self.wprops = {}          # chunk -> list of WaterProp decorations
        self.boats = []           # boats only exist once the player makes one (B)
        self._depth_memo = {}     # (int x, int z) -> (depth, type), bounded

        # two cozy set pieces near spawn, nudged onto dry ground for any seed
        self.interactives = [
            WaterProp("well", -150.0, -60.0),
            WaterProp("fountain", 150.0, 80.0),
        ]
        for ob in self.interactives:
            ob.x, ob.z = self.nearest_dry(ob.x, ob.z)

    # ---- core field query: returns (depth 0..1, type or None) ----
    def depth_at(self, x, z):
        key = (int(x), int(z))
        cached = self._depth_memo.get(key)
        if cached is not None:
            return cached
        if len(self._depth_memo) > 30000:
            self._depth_memo.clear()
        res = self._depth_calc(x, z)
        self._depth_memo[key] = res
        return res

    def _depth_calc(self, x, z):
        depth = 0.0
        typ = None

        # rivers (tiled lanes across x)
        dr = rivers_depth(x, z)
        if dr > depth:
            depth = dr
            typ = "river"

        # sea beyond the curving shoreline (only check when we're near/past it)
        if z > COAST_Z - COAST_AMP:
            cz = coast_z_at(x)
            if z > cz:
                ds = clamp((z - cz) / SEA_DEEP_DIST, 0.0, 1.0)
                ds = max(ds, 0.06)
                if ds > depth:
                    depth = ds
                    typ = "sea"

        # ponds and lakes from the surrounding cells
        for (cx, cz2, a, b, sd, kind) in self.basins_near(x, z):
            rx = (x - cx) / a
            rz = (z - cz2) / b
            r2 = rx * rx + rz * rz
            if r2 < 1.0:
                dp = smooth01(1.0 - math.sqrt(r2))
                if dp > depth:
                    depth = dp
                    typ = kind

        return depth, typ

    # ---- ponds & lakes generated per cell (so water fills the whole world) --
    def _cell_basins(self, cx, cz):
        key = (cx, cz)
        cached = self.basin_cells.get(key)
        if cached is not None:
            return cached
        rng = random.Random(seed_hash(cx, cz, 0xBA51))
        out = []
        bx0 = cx * REGION
        bz0 = cz * REGION
        # ponds
        if rng.random() < POND_CHANCE:
            for _ in range(rng.randint(1, 2)):
                px = bx0 + rng.uniform(REGION * 0.18, REGION * 0.82)
                pz = bz0 + rng.uniform(REGION * 0.18, REGION * 0.82)
                a = rng.uniform(72.0, 132.0)
                b = a * rng.uniform(0.60, 0.86)
                # don't drop a pond on top of a river
                if rivers_depth(px, pz) > 0.25 or pz > COAST_Z - 120.0:
                    continue
                out.append((px, pz, a, b, rng.random() * 9.0, "pond"))
        # the occasional bigger lake
        if rng.random() < LAKE_CHANCE:
            px = bx0 + rng.uniform(REGION * 0.25, REGION * 0.75)
            pz = bz0 + rng.uniform(REGION * 0.25, REGION * 0.75)
            a = rng.uniform(200.0, 300.0)
            b = a * rng.uniform(0.58, 0.80)
            if not (rivers_depth(px, pz) > 0.20 or pz > COAST_Z - 200.0):
                out.append((px, pz, a, b, rng.random() * 9.0, "lake"))
        self.basin_cells[key] = out
        return out

    def basins_near(self, x, z):
        # ponds and lakes are always smaller than a cell and placed well inside
        # it, so a point can only be inside a basin from its own cell
        cx = int(math.floor(x / REGION))
        cz = int(math.floor(z / REGION))
        return self._cell_basins(cx, cz)

    def _render_basins(self, cam, far_x, far_z):
        """All pond/lake ellipses that could be on screen this frame."""
        cx0 = int(math.floor((cam.x - far_x) / REGION)) - 1
        cx1 = int(math.floor((cam.x + far_x) / REGION)) + 1
        cz0 = int(math.floor((cam.z - REGION) / REGION)) - 1
        cz1 = int(math.floor(far_z / REGION)) + 1
        out = []
        for cx in range(cx0, cx1 + 1):
            for cz in range(cz0, cz1 + 1):
                out.extend(self._cell_basins(cx, cz))
        return out

    # ---- finding dry land / floatable water (spiral search) ----
    def nearest_dry(self, x, z):
        if self.depth_at(x, z)[0] <= 0.02:
            return x, z
        for r in range(20, 900, 18):
            for a in range(0, 360, 18):
                ang = math.radians(a)
                px = x + math.cos(ang) * r
                pz = z + math.sin(ang) * r
                if self.depth_at(px, pz)[0] <= 0.02:
                    return px, pz
        return x, z

    def nearest_water(self, x, z, want=0.28):
        """Closest point that's deep enough to float a boat but next to a bank
        the cat can reach.  Returns None if there's no water nearby."""
        for r in range(24, 1100, 18):
            for a in range(0, 360, 14):
                ang = math.radians(a)
                px = x + math.cos(ang) * r
                pz = z + math.sin(ang) * r
                if self.depth_at(px, pz)[0] >= want:
                    return px, pz
        return None

    def spawn_boat(self, x, z):
        bo = WaterProp("row", x, z)
        self.boats.append(bo)
        # keep only a few test boats around, preferring any in use
        if len(self.boats) > 4:
            keep = [b for b in self.boats if b.occupied]
            rest = [b for b in self.boats if not b.occupied]
            self.boats = (keep + rest)[-4:]
        return bo

    def boat_water(self, x, z):
        return self.depth_at(x, z)[0] > 0.12

    def _near_water(self, x, z, reach):
        for dx, dz in ((reach, 0), (-reach, 0), (0, reach), (0, -reach),
                       (reach * 0.7, reach * 0.7), (-reach * 0.7, -reach * 0.7)):
            d, t = self.depth_at(x + dx, z + dz)
            if d > 0.05:
                return True, t
        return False, None

    # ---- bridges (one set of crossings per river lane) ----
    def _lane_bridge_zs(self, k, z0, z1):
        """z positions of bridges on river lane k between z0 and z1."""
        if lane_half(k) < BRIDGE_MIN_HALF:
            return []                       # thin streams just get hopped/swum
        ph = _h01(k, 21) * BRIDGE_SPACING
        out = []
        i0 = int(math.floor((z0 - ph) / BRIDGE_SPACING))
        i1 = int(math.ceil((z1 - ph) / BRIDGE_SPACING))
        for i in range(i0, i1 + 1):
            zb = i * BRIDGE_SPACING + ph
            if zb > COAST_Z - 220.0:
                continue                    # no bridges out in the sea delta
            out.append(zb)
        return out

    def _bridge_under(self, x, z):
        """Return (k, zb, half) of the bridge the point sits on, or None.

        half is the walkable half-span across the river (river half-width plus
        the bit of deck that reaches onto each bank)."""
        for k in lanes_near_x(x):
            for zb in self._lane_bridge_zs(k, z - DECK_Z, z + DECK_Z):
                if abs(z - zb) <= DECK_Z * 0.5:
                    half = lane_half(k) + BRIDGE_OVERHANG
                    if abs(x - lane_cx(k, zb)) <= half:
                        return (k, zb, half)
        return None

    def on_bridge(self, x, z):
        return self._bridge_under(x, z) is not None

    def bridge_arch_at(self, x, z):
        """World-height of the arch at this point, 0 if not on a bridge.

        Progress runs 0..1 from one bank to the other; the deck humps up in a
        smooth sine so the cat rises toward the middle and settles at each end.
        The same BRIDGE_ARCH drives the drawn bridge, so they always agree."""
        b = self._bridge_under(x, z)
        if b is None:
            return 0.0
        k, zb, half = b
        cx = lane_cx(k, zb)
        progress = clamp((x - (cx - half)) / (2.0 * half), 0.0, 1.0)
        return BRIDGE_ARCH * math.sin(progress * math.pi)

    # ---- one clean place to ask "what is the water like here?" ----
    def water_mode_at(self, x, z):
        """Returns (depth, type, mode) where mode is one of
        'land' / 'shallow' / 'medium' / 'deep'.  Everything that cares about
        water (movement, submersion, ripples, decorations) reads this."""
        depth, typ = self.depth_at(x, z)
        if typ is None or depth <= 0.05:
            mode = "land"
        elif depth <= SHALLOW_MAX:
            mode = "shallow"
        elif depth <= MEDIUM_MAX:
            mode = "medium"
        else:
            mode = "deep"
        return depth, typ, mode

    @staticmethod
    def submerge_for_depth(depth):
        """Map water depth (0..1) to how submerged the cat looks (0..1).

        Stays low while wading at the edge, then rises smoothly so deep water
        leaves only the head and shoulders showing."""
        if depth <= 0.05:
            return 0.0
        if depth <= SHALLOW_MAX:
            # 0.05..SHALLOW_MAX -> 0.12..0.34  (feet / lower legs in the water)
            t = (depth - 0.05) / max(1e-3, SHALLOW_MAX - 0.05)
            return 0.12 + 0.22 * t
        if depth <= MEDIUM_MAX:
            # SHALLOW_MAX..MEDIUM_MAX -> 0.34..0.66  (body sitting lower)
            t = (depth - SHALLOW_MAX) / max(1e-3, MEDIUM_MAX - SHALLOW_MAX)
            return 0.34 + 0.32 * t
        # MEDIUM_MAX..1 -> 0.66..1.0  (swimming, only head / upper body)
        t = (depth - MEDIUM_MAX) / max(1e-3, 1.0 - MEDIUM_MAX)
        return 0.66 + 0.34 * clamp(t, 0.0, 1.0)

    def bridges_for(self, cam):
        draw_z = FOCAL * (1.0 / FADE_S_LO - 1.0)
        z0 = cam.z - 2 * CHUNK
        z1 = cam.z + draw_z
        out = []
        kmin = int(math.floor((cam.x - 1800.0 - RIVER_OFF) / RIVER_LANE))
        kmax = int(math.ceil((cam.x + 1800.0 - RIVER_OFF) / RIVER_LANE))
        for k in range(kmin, kmax + 1):
            for zb in self._lane_bridge_zs(k, z0, z1):
                out.append((k, zb))
        return out

    # ---- nearest-object helpers ----
    def nearest_boat(self, x, z, reach):
        best = None
        bd = reach * reach
        for bo in self.boats:
            if bo.occupied:
                continue
            dd = (bo.x - x) ** 2 + (bo.z - z) ** 2
            if dd < bd:
                bd = dd
                best = bo
        return best

    def nearest_interactive(self, x, z, reach):
        best = None
        bd = reach * reach
        for ob in self.interactives:
            dd = (ob.x - x) ** 2 + (ob.z - z) ** 2
            if dd < bd:
                bd = dd
                best = ob
        return best

    def nearest_shore(self, x, z):
        return self.nearest_dry(x, z)

    # (the old walking constraint was removed: deep water is now swimmable,
    #  so nothing blocks the cat from entering it.)

    def update(self, dt, cat):
        for ob in self.interactives:
            if ob.spark > 0.0:
                ob.spark = max(0.0, ob.spark - dt)

    # ---- one shaded scanline of freshwater ----
    def _fw_row(self, surf, sy, xl, xr, fade, wz, t, shallow=False):
        a = int(math.floor(xl))
        b = int(math.ceil(xr))
        if a < 0:
            a = 0
        if b > config.W - 1:
            b = config.W - 1
        if b < a:
            return
        width = b - a + 1

        def hz(c):
            return lerp_color(c, HAZE, fade * WATER_HAZE)

        # Soft, broken foam along the bank instead of a hard dashed edge: only
        # some rows foam, and the foam tone eases between water and a calm
        # waterline so the bank reads as a gentle wet line, not a row of dots.
        def soft_edge(px, phase):
            if px < 0 or px >= config.W:
                return
            lit = 0.5 + 0.5 * math.sin(wz * 0.10 + phase + t * 1.4)
            if lit > 0.58:
                f = (lit - 0.58) / 0.42
                surf.set_at((px, sy), hz(lerp_color(FW_SHALLOW, FOAM, 0.30 + 0.55 * f * SHORE_FOAM)))
            else:
                surf.set_at((px, sy), hz(lerp_color(FW_SHALLOW, FW_MID, 0.30)))

        if shallow or width <= 3:
            surf.fill(hz(FW_SHALLOW), (a, sy, width, 1))
            if width > 2:
                soft_edge(a, 0.0)
                soft_edge(b, 1.7)
            if a - 1 >= 0:
                surf.set_at((a - 1, sy), lerp_color(ground_color_at(sy), WET_BANK, 0.35))
            if b + 1 < config.W:
                surf.set_at((b + 1, sy), lerp_color(ground_color_at(sy), WET_BANK, 0.35))
            return

        # ART: a smooth shallow->deep->shallow cross-section with a gentle
        # ripple-driven core, soft foam banks, a broad drifting light sheen and
        # an occasional soft tinted glint (never stark white).
        rip = 0.5 + 0.5 * math.sin(wz * 0.05 + t * 1.4)
        x1 = a + int(width * 0.16)
        x2 = a + int(width * 0.34)
        x3 = a + int(width * 0.66)
        x4 = a + int(width * 0.84)
        surf.fill(hz(FW_SHALLOW), (a, sy, max(1, x1 - a), 1))
        surf.fill(hz(lerp_color(FW_SHALLOW, FW_MID, 0.6)), (x1, sy, max(1, x2 - x1), 1))
        deep = lerp_color(FW_DEEP, FW_DEEPEST, 0.32 + 0.34 * rip)
        surf.fill(hz(deep), (x2, sy, max(1, x3 - x2), 1))
        surf.fill(hz(lerp_color(FW_SHALLOW, FW_MID, 0.6)), (x3, sy, max(1, x4 - x3), 1))
        surf.fill(hz(FW_SHALLOW), (x4, sy, max(1, b - x4 + 1), 1))

        # broad surface sheen: a soft lighter sweep over the core that drifts
        # slowly, so the water has a reflective sheen instead of a flat fill
        if WATER_SHEEN > 0:
            sweep = 0.5 + 0.5 * math.sin(wz * 0.018 - t * 0.5)
            if sweep > 0.55:
                amt = clamp((sweep - 0.55) / 0.45 * WATER_SHEEN, 0.0, 0.55)
                shx0 = max(a, a + int(width * 0.36))
                shx1 = min(b, a + int(width * 0.60))
                if shx1 >= shx0:
                    surf.fill(hz(lerp_color(deep, FW_GLINT, amt)), (shx0, sy, shx1 - shx0 + 1, 1))

        # soft broken foam at both banks
        soft_edge(a, 0.0)
        soft_edge(b, 1.7)

        # occasional soft tinted sparkle on the surface
        if WATER_GLINT > 0 and (0.5 + 0.5 * math.sin(wz * 0.13 - t * 0.9)) > 0.92:
            sp = a + int(width * (0.4 + 0.2 * rip))
            if 0 <= sp < config.W:
                surf.set_at((sp, sy), hz(lerp_color(FW_SHALLOW, FW_GLINT, 0.7)))
                if sp + 1 < config.W:
                    surf.set_at((sp + 1, sy), hz(lerp_color(FW_MID, FW_GLINT, 0.4)))

        # damp bank just outside the water
        if a - 1 >= 0:
            surf.set_at((a - 1, sy), lerp_color(ground_color_at(sy), WET_BANK, 0.45))
        if b + 1 < config.W:
            surf.set_at((b + 1, sy), lerp_color(ground_color_at(sy), WET_BANK, 0.45))

    # ---- the ground-integrated water surface pass ----
    def draw_surface(self, surf, cam, t):
        GYH = config.GROUND_Y - config.MEADOW_HORIZON
        if GYH <= 0:
            return
        sy_start = int(config.MEADOW_HORIZON + GYH * FADE_S_LO) + 1
        half = config.W * 0.5

        # how far out the bottom row sees, so we know which water cells matter
        far_d = FOCAL / max(FADE_S_LO, 1e-3)
        far_z = cam.z + far_d
        far_x = abs((config.W - half)) * (1.0 / (FADE_S_LO * config.SC)) + 200.0
        basins = self._render_basins(cam, far_x, far_z)

        # coastline lookup table: sample coast_z_at across the visible x-range
        # once per frame instead of calling sin() for every pixel of every row
        lut_x0 = cam.x - far_x
        lut_step = 10.0
        lut_n = int(far_x * 2.0 / lut_step) + 2
        coast_lut = [coast_z_at(lut_x0 + i * lut_step) for i in range(lut_n)]

        def coast_at(wx):
            fi = (wx - lut_x0) / lut_step
            i = int(fi)
            if i < 0:
                return coast_lut[0]
            if i >= lut_n - 1:
                return coast_lut[-1]
            f = fi - i
            return coast_lut[i] * (1.0 - f) + coast_lut[i + 1] * f

        for sy in range(sy_start, config.H):
            scale = (sy - config.MEADOW_HORIZON) / GYH
            if scale <= 0:
                continue
            k = scale * config.SC
            if k <= 0:
                continue
            inv = 1.0 / k
            d = FOCAL / scale
            wz = cam.z + d - FOCAL
            fade = (FADE_S_HI - scale) / (FADE_S_HI - FADE_S_LO) if scale < FADE_S_HI else 0.0
            if fade < 0:
                fade = 0.0
            elif fade > 1:
                fade = 1.0

            # ---- sea (everything beyond the curving coastline) ----
            dsea = wz - COAST_Z
            if dsea > COAST_AMP:
                d_sea = clamp((wz - COAST_Z) / SEA_DEEP_DIST, 0.0, 1.0)
                base = lerp_color(SEA_MID, SEA_DEEPEST, smooth01(d_sea))
                # far rows fade to a pale sea-horizon mist so the open water
                # melts softly into the skyline instead of ending on a hard edge
                sea_haze = lerp_color(SEA_HORIZON, SKY_HORIZON, 0.30)
                c = lerp_color(base, sea_haze, fade)
                surf.fill(c, (0, sy, config.W, 1))
                # gentle horizontal swell: only some rows lighten, softly and
                # in broken segments, so it reads as calm water, not static
                band = math.sin(wz * 0.020 + t * 0.6)
                if band > 0.45:
                    amt = 0.16 * (band - 0.45) / 0.55
                    cc = lerp_color(c, lerp_color(SEA_SHALLOW, FOAM, 0.4), amt)
                    seg = max(3, ri(11 * k))
                    gap = max(9, ri(34 * k))
                    off = int((wz * 1.6 + t * 16.0) % (seg + gap))
                    xx = -off
                    while xx < config.W:
                        if xx >= 0:
                            surf.fill(cc, (xx, sy, seg, 1))
                        xx += seg + gap
                # a rare, soft, tinted glint (never stark white), and only on
                # the nearer, un-hazed rows so the far sea stays calm in motion
                if WATER_GLINT > 0 and fade < 0.45 and math.sin(wz * 0.45 + t * 0.9) > 0.95:
                    gx = int((wz * 5.0 + t * 40.0) % config.W)
                    surf.set_at((gx, sy), lerp_color(c, FW_GLINT, 0.5))
            elif dsea < -COAST_AMP:
                pass
            else:
                # shoreline band: classify each column as sea / beach / land
                prev = -1
                start = 0
                spans = []
                for px in range(0, config.W):
                    wx = cam.x + (px - half) * inv
                    czx = coast_at(wx)
                    if wz > czx:
                        typ = 2
                    elif czx - wz < BEACH_W:
                        typ = 1
                    else:
                        typ = 0
                    if typ != prev:
                        if prev == 2 or prev == 1:
                            spans.append((prev, start, px - 1))
                        prev = typ
                        start = px
                if prev == 2 or prev == 1:
                    spans.append((prev, start, config.W - 1))
                for typ, x0, x1 in spans:
                    if typ == 2:
                        c = lerp_color(SEA_SHALLOW, SEA_MID, 0.45)
                        c = lerp_color(c, lerp_color(SEA_HORIZON, SKY_HORIZON, 0.30), fade)
                        surf.fill(c, (x0, sy, x1 - x0 + 1, 1))
                        # soft rolling foam along both shore edges of the band
                        if SHORE_FOAM > 0:
                            fcol = lerp_color(FOAM, HAZE, fade)
                            if math.sin(wz * 0.12 + x0 * 0.05 + t * 2.0) > -0.15:
                                surf.set_at((x0, sy), fcol)
                                if x0 + 1 <= x1:
                                    surf.set_at((x0 + 1, sy), lerp_color(c, fcol, 0.5))
                            if math.sin(wz * 0.12 + x1 * 0.05 + t * 2.0 + 1.3) > -0.15:
                                surf.set_at((x1, sy), fcol)
                    else:
                        # sun-warmed sand: a soft wet/dry blend with a faint lit
                        # crest so the beach catches a little light
                        c = lerp_color(WET_SAND, DRY_SAND, 0.45)
                        c = lerp_color(c, SAND_LIT, 0.22 * (1.0 - fade))
                        surf.fill(c, (x0, sy, x1 - x0 + 1, 1))
                        surf.set_at((x0, sy), lerp_color(WET_SAND, c, 0.35))
                        surf.set_at((x1, sy), lerp_color(c, SAND_LIT, 0.5))

            # ---- rivers on top (only the lanes that can reach this row) ----
            if wz < COAST_Z + 160.0:
                kmin = int(math.floor((cam.x - far_x - RIVER_OFF) / RIVER_LANE))
                kmax = int(math.ceil((cam.x + far_x - RIVER_OFF) / RIVER_LANE))
                for lk in range(kmin, kmax + 1):
                    hw = lane_half(lk)
                    cxr = lane_cx(lk, wz)
                    xl = half + (cxr - hw - cam.x) * k
                    xr = half + (cxr + hw - cam.x) * k
                    if xr >= 0 and xl <= config.W:
                        self._fw_row(surf, sy, xl, xr, fade, wz, t, shallow=(hw < 30.0))

            # ---- ponds & lakes ----
            for (cx, cz, a, b, sd, kind) in basins:
                dz = wz - cz
                if -b < dz < b:
                    wob = 1.0 + 0.10 * math.sin(wz * 0.05 + sd) + 0.05 * math.sin(wz * 0.12 + sd * 2.0)
                    hh = a * math.sqrt(max(0.0, 1.0 - (dz / b) * (dz / b))) * wob
                    xl = half + ((cx - hh) - cam.x) * k
                    xr = half + ((cx + hh) - cam.x) * k
                    if xr >= 0 and xl <= config.W:
                        self._fw_row(surf, sy, xl, xr, fade, wz, t)

    # ---- chunked water decorations (reeds, lilies, fish, frogs, stones) ----
    def water_props(self, gx, gz):
        key = (gx, gz)
        c = self.wprops.get(key)
        if c is not None:
            return c
        rng = random.Random(seed_hash(gx, gz, 0x7A7E))
        items = []
        for _ in range(rng.randint(1, 3)):
            wx = gx * CHUNK + rng.uniform(0, CHUNK)
            wz = gz * CHUNK + rng.uniform(0, CHUNK)
            depth, typ = self.depth_at(wx, wz)
            r = rng.random()
            if typ is None:
                # only freshwater banks get reeds / edge flowers / tufts;
                # the sandy sea beach stays clean
                nearw, nt = self._near_water(wx, wz, 28.0)
                if not nearw or nt == "sea":
                    continue
                kind = "reed" if r < 0.42 else ("flower" if r < 0.72 else ("wstone" if r < 0.88 else "tuft"))
                items.append((kind, wx, wz, rng.random()))
            elif typ == "sea":
                # open sea stays calm; only a rare rock in the shallows
                if depth < 0.30 and r < 0.18:
                    items.append(("wstone", wx, wz, rng.random()))
            elif typ in ("pond", "lake"):
                if depth < 0.40:
                    if r < 0.34:
                        kind = "lily"
                    elif r < 0.52:
                        kind = "frog"
                    elif r < 0.74:
                        kind = "fish"
                    elif r < 0.88:
                        kind = "reed"
                    else:
                        kind = "wstone"
                else:
                    kind = "lily" if r < 0.16 else "fish"
                items.append((kind, wx, wz, rng.random()))
            else:  # river
                if depth < 0.40:
                    kind = "wstone" if r < 0.50 else ("reed" if r < 0.80 else "fish")
                    items.append((kind, wx, wz, rng.random()))
                elif r < 0.45:
                    items.append(("fish", wx, wz, rng.random()))
        self.wprops[key] = items
        return items

    # ---- feed every water object into the shared depth-sort list ----
    def gather_drawables(self, cam, t, add, cat, clear_zone=None):
        deco_z = FOCAL * (1.0 / 0.20 - 1.0)
        gz0 = int((cam.z - CHUNK) // CHUNK)
        gz1 = int((cam.z + deco_z) // CHUNK)
        edge = 0.5 * config.W + int(config.W * 0.45) + 32
        for gz in range(gz0, gz1 + 1):
            far_dz = (gz + 1) * CHUNK - cam.z
            dd = far_dz + FOCAL
            scale = FOCAL / dd if dd > MIN_D else FOCAL / MIN_D
            xhalf = min(edge / max(0.04, scale * config.SC), 6000.0)
            gx0 = int((cam.x - xhalf) // CHUNK)
            gx1 = int((cam.x + xhalf) // CHUNK)
            for gx in range(gx0, gx1 + 1):
                for kind, wx, wz, seed in self.water_props(gx, gz):
                    if clear_zone is not None and clear_zone(wx, wz):
                        continue
                    pc = project_cull(wx, wz, cam)
                    if pc is None:
                        continue
                    sx, sy, sc, fd = pc
                    add((sy, 9, kind, sx, sy, sc, fd, seed))

        for (lk, zb) in self.bridges_for(cam):
            c = lane_cx(lk, zb)
            hw = lane_half(lk)
            pc = project(c, zb, cam)
            if pc is None:
                continue
            csx, csy, cscale = pc
            if csx < -int(config.W * 0.5) or csx > config.W + int(config.W * 0.5):
                continue
            if cscale <= FADE_S_LO:
                continue
            fade = (FADE_S_HI - cscale) / (FADE_S_HI - FADE_S_LO) if cscale < FADE_S_HI else 0.0
            fade = clamp(fade, 0.0, 1.0)
            # carry world params; draw_bridge projects per-slice for stability
            add((csy, 15, (c, hw, zb, fade), _h01(lk, 5)))

        for bo in self.boats:
            if clear_zone is not None and clear_zone(bo.x, bo.z):
                continue
            if bo is cat.boat:
                continue                      # drawn together with the cat
            pc = project_cull(bo.x, bo.z, cam)
            if pc is None:
                continue
            sx, sy, sc, fd = pc
            add((sy, 16, (bo.kind, bo), sx, sy, sc, fd, 0))

        for ob in self.interactives:
            if clear_zone is not None and clear_zone(ob.x, ob.z):
                continue
            pc = project_cull(ob.x, ob.z, cam)
            if pc is None:
                continue
            sx, sy, sc, fd = pc
            near = 1 if ((ob.x - cat.x) ** 2 + (ob.z - cat.z) ** 2) < USE_REACH * USE_REACH else 0
            tag = 17 if ob.kind == "well" else 18
            add((sy, tag, ob, sx, sy, sc, fd, near))

        if len(self.wprops) > 2500:
            self.wprops = {(gx, gz): v for (gx, gz), v in self.wprops.items()
                           if gz0 - 2 <= gz <= gz1 + 2}
        if len(self.basin_cells) > 600:
            ccx = int(math.floor(cam.x / REGION))
            ccz = int(math.floor(cam.z / REGION))
            self.basin_cells = {(cx, cz): v for (cx, cz), v in self.basin_cells.items()
                                if abs(cx - ccx) <= 4 and abs(cz - ccz) <= 4}
