"""Painters for the built landmarks that sit on or over the water: the arched
bridge, the boats (hull, body and trim), the well and the fountain.

Where these things *are* and how the cat rides a boat is decided in
:mod:`cat_society.world.water`; this module only draws them."""

import math

import pygame

from .. import config
from ..config import *
from ..utils import ri, clamp, lerp_color, ground_color_at
from ..palette import *
from ..projection import project
from .props import _haze


def draw_bridge(surf, c, hw, zb, fade, cam, woodseed, t):
    """Stable, world-space arched bridge.  Every point across the span is a real
    world position projected on its own, and the arch is a world-height lift, so
    the bridge no longer balloons or 'opens like a gate' as the camera passes.
    The same BRIDGE_ARCH drives the cat's traversal, so deck and cat agree."""
    col = _haze(fade)
    halfspan = hw + BRIDGE_OVERHANG
    z_near = zb - DECK_Z * 0.5          # nearer the camera -> lower on screen
    z_far = zb + DECK_Z * 0.5
    # size everything from the STABLE bridge-centre scale (never an edge scale,
    # which is what used to blow up as the camera approached)
    pcz = project(c, zb, cam)
    if pcz is None:
        return
    _, _, cscale = pcz
    s = cscale * config.SC
    if s <= 0:
        return
    deck = (184, 134, 84)
    deck_d = (132, 90, 52)
    deck_l = (212, 168, 112)
    face = (148, 102, 60)
    rail = (166, 118, 72)
    post = (120, 84, 48)
    thick = max(2.0, 5.0 * s)
    railh = 11.0 * s

    def slice_pt(f, zedge):
        wx = c + (2.0 * f - 1.0) * halfspan
        p = project(wx, zedge, cam)
        if p is None:
            return None
        sx, sy, sc = p
        lift = BRIDGE_ARCH * math.sin(math.pi * f) * sc * config.SC   # world-Y lift
        return (sx, sy - lift)

    nsl = int(clamp(halfspan * 2.0 * s / 2.0, 10, 64))
    near, far = [], []
    for i in range(nsl + 1):
        f = i / nsl
        pn = slice_pt(f, z_near)
        pf = slice_pt(f, z_far)
        if pn is None or pf is None:
            return                         # off the front of the camera; skip
        near.append(pn)
        far.append(pf)

    # ---- shadow on the water under the near edge ----
    midx = sum(p[0] for p in near) / len(near)
    ny = max(p[1] for p in near)
    swid = ri(abs(near[-1][0] - near[0][0]) + 6)
    shh = max(2, ri(4 * s))
    if swid >= 2:
        shs = pygame.Surface((swid, shh), pygame.SRCALPHA)
        pygame.draw.ellipse(shs, (28, 58, 78, 90), (0, 0, swid, shh))
        surf.blit(shs, (ri(midx) - swid // 2, ri(ny) - shh // 2))

    # ---- deck top surface (far edge -> near edge) ----
    poly = [(ri(px), ri(py)) for (px, py) in far] + \
           [(ri(px), ri(py)) for (px, py) in reversed(near)]
    if len(poly) >= 3:
        pygame.draw.polygon(surf, col(deck), poly)

    # ---- front face under the near edge (gives thickness) ----
    face_poly = [(ri(px), ri(py)) for (px, py) in near] + \
                [(ri(px), ri(py + thick)) for (px, py) in reversed(near)]
    if len(face_poly) >= 3:
        pygame.draw.polygon(surf, col(face), face_poly)

    # ---- plank seams (perpendicular to the span) ----
    nplanks = max(6, int(abs(near[-1][0] - near[0][0]) / max(3.0, 6.0 * s)))
    for k in range(1, nplanks):
        f = k / nplanks
        i = int(f * nsl)
        pygame.draw.line(surf, col(deck_d), (ri(far[i][0]), ri(far[i][1])),
                         (ri(near[i][0]), ri(near[i][1])), 1)

    # ---- sunlit near lip ----
    if len(near) >= 2:
        pygame.draw.lines(surf, col(deck_l), False, [(ri(px), ri(py)) for px, py in near], max(1, ri(1.4 * s)))

    # ---- two arched railings with posts ----
    for pts in (near, far):
        railpts = [(ri(px), ri(py - railh)) for (px, py) in pts]
        if len(railpts) >= 2:
            pygame.draw.lines(surf, col(rail), False, railpts, max(1, ri(1.6 * s)))
        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            i = int(f * nsl)
            px, py = pts[i]
            pygame.draw.line(surf, col(post), (ri(px), ri(py)),
                             (ri(px), ri(py - railh)), max(1, ri(1.5 * s)))


def _boat_metrics(scale):
    """One place for boat proportions, so size is easy to tune (see BOAT_*)."""
    s = scale * config.SC
    return s, {
        "L":   82.0 * s,    # half-length to the squared ends (clearly > the cat)
        "bow": 26.0 * s,    # how far the bow point juts past L
        "top": 22.0 * s,    # gunwale height above the waterline (freeboard)
        "bot": 14.0 * s,    # how far the keel sits below the waterline
    }


def boat_seat_lift(scale):
    """How far above the waterline the cat's feet sit when it is aboard."""
    return 5.0 * scale * config.SC


def _ellipse_pt(cx, cy, rx, ry, a):
    return (cx + rx * math.cos(a), cy + ry * math.sin(a))


def _boat_surface(scale, kind):
    """Local drawing surface with the bow pointing RIGHT, plus the frame.

    Returns (surface, ox, oy, s, m) where (ox, oy) is the boat centre at the
    waterline.  Drawing in this fixed frame keeps the geometry simple; the
    caller just flips the finished surface for a left-facing boat."""
    s, m = _boat_metrics(scale)
    L, bow, top, bot = m["L"], m["bow"], m["top"], m["bot"]
    pad = ri(10 * s) + 3
    mast_h = ri(62 * s) if kind == "sail" else 0
    surfW = ri(2 * L + bow) + 2 * pad
    surfH = ri(top + bot + mast_h) + 2 * pad
    bs = pygame.Surface((surfW, surfH), pygame.SRCALPHA)
    ox = pad + ri(L)
    oy = pad + mast_h + ri(top)
    return bs, ox, oy, s, m


def _boat_blit(surf, bs, ox, sx, sy, oy, facing):
    if facing < 0:
        bs = pygame.transform.flip(bs, True, False)
        ox = bs.get_width() - 1 - ox
    surf.blit(bs, (ri(sx - ox), ri(sy - oy)))


def _boat_hull_pts(X, Y, m):
    L, bow, top, bot = m["L"], m["bow"], m["top"], m["bot"]
    return [
        (X + (L + bow),        Y - top * 0.48),   # bow tip (raised, sharper)
        (X + L,                Y - top),          # bow gunwale
        (X - L,                Y - top * 0.92),   # stern gunwale
        (X - (L + bow * 0.32), Y - top * 0.10),   # rounded stern
        (X - L * 0.86,         Y + bot),          # stern bottom
        (X - L * 0.10,         Y + bot * 1.06),   # keel (deepest)
        (X + L * 0.66,         Y + bot * 0.66),   # keel rising
        (X + L * 0.98,         Y - bot * 0.05),   # toward the bow
    ]


def _boat_mouth(X, Y, m, s):
    L, top = m["L"], m["top"]
    return (X - L * 0.06, Y - top + 3.0 * s, L * 1.55, top * 0.40)


def draw_boat_body(surf, kind, boat, sx, sy, scale, fade, t):
    """Hull, interior and seat: everything BEHIND the cat."""
    col = _haze(fade)
    s0 = scale * config.SC
    bob = math.sin(t * 1.6 + boat.x * 0.01) * 1.6 * s0
    bs, X, Y, s, m = _boat_surface(scale, kind)
    L, bow, top, bot = m["L"], m["bow"], m["top"], m["bot"]
    if L < 7:   # far away: a soft wooden lozenge straight onto the scene
        pygame.draw.ellipse(surf, col(BOAT_WOOD),
                            (ri(sx) - ri(L + bow), ri(sy + bob) - 2,
                             ri((L + bow) * 2), max(2, ri(bot * 2 + 4))))
        return
    sy_b = sy + bob

    # ---- soft shadow on the water (straight to the scene) ----
    shw = ri((L + bow) * 2.0 + 6)
    shh = max(2, ri(6 * s))
    shs = pygame.Surface((shw, shh), pygame.SRCALPHA)
    pygame.draw.ellipse(shs, (26, 58, 82, 95), (0, 0, shw, shh))
    surf.blit(shs, (ri(sx) - shw // 2, ri(sy_b + bot) - shh // 2))

    # ---- hull silhouette + underwater strake ----
    hull = _boat_hull_pts(X, Y, m)
    pygame.draw.polygon(bs, col(BOAT_WOOD_D), [(ri(px), ri(py)) for px, py in hull])
    pygame.draw.line(bs, col(lerp_color(BOAT_WOOD_D, (70, 96, 110), 0.35)),
                     (ri(X - L * 0.84), ri(Y + bot * 0.45)),
                     (ri(X + L * 0.84), ri(Y + bot * 0.30)), max(1, ri(2.0 * s)))

    # ---- mouth opening: rim ring, dark interior, shaded floor ----
    mcx, mcy, mw, mry = _boat_mouth(X, Y, m, s)
    rim_rect = (ri(mcx - mw / 2), ri(mcy - mry), ri(mw), max(3, ri(mry * 2)))
    pygame.draw.ellipse(bs, col(BOAT_RIM), rim_rect)
    inset = (rim_rect[0] + max(1, ri(2.2 * s)), rim_rect[1] + max(1, ri(1.8 * s)),
             max(3, rim_rect[2] - max(2, ri(4.4 * s))), max(3, rim_rect[3] - max(2, ri(3.4 * s))))
    pygame.draw.ellipse(bs, col(BOAT_INSIDE), inset)
    pygame.draw.ellipse(bs, col(BOAT_INSIDE_D),
                        (inset[0], inset[1] + inset[3] // 2, inset[2], max(1, inset[3] // 2)))

    # ---- far (back) gunwale rim, behind the cat ----
    far = [_ellipse_pt(mcx, mcy, mw / 2, mry, math.pi + math.pi * i / 12.0) for i in range(13)]
    pygame.draw.lines(bs, col(BOAT_WOOD_L), False,
                      [(ri(px), ri(py)) for px, py in far], max(1, ri(1.8 * s)))

    # ---- seat plank ----
    seat_y = ri(mcy - mry * 0.10)
    pygame.draw.line(bs, col(BOAT_WOOD_L), (ri(mcx - mw * 0.22), seat_y),
                     (ri(mcx + mw * 0.22), seat_y), max(1, ri(2.6 * s)))

    if kind == "sail":
        mast_x = ri(X - L * 0.04)
        mast_top = ri(Y - top - 44.0 * s)
        pygame.draw.line(bs, col(BOAT_WOOD_D), (mast_x, ri(Y - top)), (mast_x, mast_top), max(1, ri(2.2 * s)))
        sail = [(mast_x, mast_top + ri(3 * s)), (mast_x, ri(Y - top - 6 * s)),
                (ri(mast_x + 30 * s), ri(Y - top - 16 * s))]
        pygame.draw.polygon(bs, col((246, 242, 232)), sail)
        pygame.draw.polygon(bs, col((214, 206, 192)), sail, 1)

    _boat_blit(surf, bs, X, sx, sy_b, Y, boat.facing)


def draw_boat_trim(surf, kind, boat, sx, sy, scale, fade, t):
    """The near (front) wall and oar: the bits IN FRONT of the cat."""
    col = _haze(fade)
    s0 = scale * config.SC
    bob = math.sin(t * 1.6 + boat.x * 0.01) * 1.6 * s0
    bs, X, Y, s, m = _boat_surface(scale, kind)
    L, bow, top, bot = m["L"], m["bow"], m["top"], m["bot"]
    if L < 7:
        return
    sy_b = sy + bob

    mcx, mcy, mw, mry = _boat_mouth(X, Y, m, s)
    # near rim (front, lower half of the mouth), bow-side -> stern-side
    rim = [_ellipse_pt(mcx, mcy, mw / 2, mry, math.pi * i / 12.0) for i in range(13)]
    wall_bottom = [
        (X - L * 0.86, Y + bot),         # stern bottom (left)
        (X - L * 0.10, Y + bot * 1.06),
        (X + L * 0.66, Y + bot * 0.66),
        (X + L * 0.98, Y - bot * 0.05),  # bow bottom (right)
    ]
    wall = rim + wall_bottom             # simple, non-crossing outline
    pygame.draw.polygon(bs, col(BOAT_WOOD), [(ri(px), ri(py)) for px, py in wall])
    # two plank lines across the front wall for a bit of woodgrain
    pygame.draw.line(bs, col(BOAT_WOOD_D),
                     (ri(X - L * 0.78), ri(Y + bot * 0.30)),
                     (ri(X + L * 0.88), ri(Y + bot * 0.05)), max(1, ri(1.4 * s)))
    pygame.draw.line(bs, col(lerp_color(BOAT_WOOD, BOAT_WOOD_L, 0.5)),
                     (ri(X - L * 0.80), ri(Y - bot * 0.05)),
                     (ri(X + L * 0.90), ri(Y - bot * 0.28)), max(1, ri(1.2 * s)))
    # bright gunwale along the near rim
    pygame.draw.lines(bs, col(BOAT_WOOD_L), False, [(ri(px), ri(py)) for px, py in rim], max(1, ri(2.0 * s)))
    pygame.draw.lines(bs, col(BOAT_RIM), False, [(ri(px), ri(py)) for px, py in rim], max(1, ri(1.0 * s)))

    if kind != "sail":
        # an oar dipping over the near side toward the stern
        pygame.draw.line(bs, col(BOAT_WOOD_L),
                         (ri(X - L * 0.32), ri(Y - top * 0.30)),
                         (ri(X - (L + bow * 0.7)), ri(Y + 7 * s)), max(1, ri(2.0 * s)))
        pygame.draw.ellipse(bs, col(BOAT_WOOD),
                            (ri(X - (L + bow * 0.95)), ri(Y + 5 * s),
                             max(2, ri(8 * s)), max(2, ri(4 * s))))

    _boat_blit(surf, bs, X, sx, sy_b, Y, boat.facing)


def draw_boat(surf, kind, boat, sx, sy, scale, fade, t):
    """A complete (empty) boat: body then trim."""
    draw_boat_body(surf, kind, boat, sx, sy, scale, fade, t)
    draw_boat_trim(surf, kind, boat, sx, sy, scale, fade, t)


def draw_well(surf, obj, sx, sy, scale, fade, near, t):
    s = scale * config.SC * WELL_SCALE
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    stone = (152, 152, 162)
    stone_d = (116, 116, 128)
    stone_l = (188, 188, 198)
    wood = (150, 104, 62)
    wood_d = (116, 80, 48)
    roof = (182, 122, 74)
    bw = ri(20 * s)
    bh = ri(14 * s)
    if bw < 4:
        pygame.draw.rect(surf, col(stone), (sx - 2, sy - 5, 4, 5))
        return
    pygame.draw.ellipse(surf, lerp_color(ground_color_at(sy), GROUND_DEEP, 0.4 * (1.0 - fade)),
                        (sx - bw, sy - ri(3 * s), bw * 2, max(2, ri(6 * s))))
    pygame.draw.rect(surf, col(stone_d), (sx - bw, sy - bh, bw * 2, bh))
    for k in (-1, 0, 1):
        pygame.draw.line(surf, col(stone_l), (sx + ri(k * 8 * s), sy - bh + 1), (sx + ri(k * 8 * s), sy - 1), 1)
    pygame.draw.ellipse(surf, col(stone), (sx - bw, sy - bh - ri(4 * s), bw * 2, max(2, ri(8 * s))))
    pygame.draw.ellipse(surf, col(FW_DEEP), (sx - bw + ri(3 * s), sy - bh - ri(2 * s),
                                             bw * 2 - ri(6 * s), max(1, ri(5 * s))))
    shim = math.sin(t * 2.0)
    surf.set_at((clamp(sx + ri(shim * 3 * s), 0, config.W - 1), clamp(sy - bh, 0, config.H - 1)), col(FOAM))
    px = bw - ri(2 * s)
    roof_y = sy - bh - ri(20 * s)
    pygame.draw.line(surf, col(wood_d), (sx - px, sy - bh), (sx - px, roof_y), max(1, ri(2 * s)))
    pygame.draw.line(surf, col(wood_d), (sx + px, sy - bh), (sx + px, roof_y), max(1, ri(2 * s)))
    pygame.draw.polygon(surf, col(roof), [(sx - bw - ri(3 * s), roof_y), (sx + bw + ri(3 * s), roof_y),
                                          (sx, roof_y - ri(12 * s))])
    pygame.draw.polygon(surf, col(lerp_color(roof, (255, 255, 255), 0.2)),
                        [(sx - bw - ri(3 * s), roof_y), (sx, roof_y - ri(12 * s)), (sx - ri(3 * s), roof_y)])
    pygame.draw.line(surf, col(wood_d), (sx, roof_y - ri(2 * s)), (sx, sy - bh - ri(6 * s)), 1)
    pygame.draw.rect(surf, col(wood), (sx - ri(2 * s), sy - bh - ri(6 * s), max(2, ri(4 * s)), max(2, ri(4 * s))))
    if near or obj.spark > 0.01:
        for i in range(3):
            a = (t * 3.0 + i * 2.1) % 2.0
            surf.set_at((clamp(sx + ri((i - 1) * 4 * s), 0, config.W - 1),
                         clamp(sy - bh - ri((4 + a * 6) * s), 0, config.H - 1)), (255, 255, 255))



def draw_fountain(surf, obj, sx, sy, scale, fade, near, t):
    s = scale * config.SC * FOUNTAIN_SCALE
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    stone = (186, 186, 196)
    stone_d = (142, 142, 154)
    stone_l = (214, 214, 224)
    bw = ri(22 * s)
    bh = ri(8 * s)
    if bw < 4:
        pygame.draw.rect(surf, col(stone), (sx - 2, sy - 4, 4, 4))
        return
    pygame.draw.ellipse(surf, lerp_color(ground_color_at(sy), GROUND_DEEP, 0.4 * (1.0 - fade)),
                        (sx - bw, sy - ri(2 * s), bw * 2, max(2, ri(5 * s))))
    pygame.draw.ellipse(surf, col(stone_d), (sx - bw, sy - bh, bw * 2, max(2, ri(bh * 1.6))))
    pygame.draw.ellipse(surf, col(stone), (sx - bw, sy - bh - ri(2 * s), bw * 2, max(2, ri(bh * 1.3))))
    pygame.draw.ellipse(surf, col(FW_MID), (sx - bw + ri(3 * s), sy - bh - ri(1 * s),
                                            bw * 2 - ri(6 * s), max(1, ri(bh * 0.9))))
    rr = ri((2 + (math.sin(t * 3.0) * 0.5 + 0.5) * 3) * s)
    if rr >= 1:
        pygame.draw.ellipse(surf, col(FW_SHALLOW), (sx - rr, sy - bh - ri(0.5 * s), rr * 2, max(1, ri(rr * 0.8))), 1)
    pygame.draw.rect(surf, col(stone), (sx - ri(2 * s), sy - bh - ri(12 * s), max(2, ri(4 * s)), ri(12 * s)))
    pygame.draw.ellipse(surf, col(stone_l), (sx - ri(7 * s), sy - bh - ri(15 * s), max(2, ri(14 * s)), max(2, ri(6 * s))))
    for i in range(5):
        ph = t * 4.0 + i * 1.0
        spx = sx + ri(math.sin(ph) * 8 * s)
        for k in range(4):
            yy = sy - bh - ri((15 + k * 3) * s) - ri(abs(math.sin(ph)) * 2 * s)
            surf.set_at((clamp(spx + (k - 1), 0, config.W - 1), clamp(yy, 0, config.H - 1)),
                        col(FW_SHALLOW if k % 2 else FOAM))
    for i in range(3):
        a = (t * 3.0 + i * 0.9) % 1.0
        dx = ri((i - 1) * 6 * s)
        yy = sy - bh - ri(13 * s) + ri(a * 13 * s)
        surf.set_at((clamp(sx + dx, 0, config.W - 1), clamp(yy, 0, config.H - 1)), col(FW_SHALLOW))
    if near or obj.spark > 0.01:
        for i in range(3):
            a = (t * 4.0 + i * 2.0) % 2.0
            surf.set_at((clamp(sx + ri((i - 1) * 5 * s), 0, config.W - 1),
                         clamp(sy - bh - ri((16 + a * 5) * s), 0, config.H - 1)), (255, 255, 255))
