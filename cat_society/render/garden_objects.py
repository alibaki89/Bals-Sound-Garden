"""Painters for the garden's working fixtures.

Same rules as every other prop: soft shapes, one up-left highlight, warm
outline colours, contact shade from the ground ramp, ``_haze(fade)`` into the
distance.  The stump wears real posted notes; the windmill's blades take
their angle from the live simulation; the seed bed shows its water as a
darkening of the soil (information as gardening, not as bars)."""

import math

import pygame

from .. import config
from ..utils import ri, clamp, lerp_color, ground_color_at
from ..palette import GROUND_DEEP, HAZE, FW_SHALLOW

WOOD = (168, 128, 92)
WOOD_D = (134, 98, 70)
WOOD_L = (196, 158, 118)
PAPER = (247, 240, 224)
PAPER_D = (224, 210, 184)
PIN = (216, 120, 110)
STONE = (176, 172, 168)
STONE_D = (136, 132, 130)
SAIL = (238, 230, 210)
SAIL_D = (204, 192, 168)
BRASS = (222, 178, 110)
BRASS_D = (176, 134, 78)
SOIL_WET = (104, 82, 64)
SOIL_DRY = (150, 124, 96)
SPARK = (255, 240, 190)


def _haze(fade):
    def col(c):
        return lerp_color(c, HAZE, fade * 0.85)
    return col


def _contact(surf, sx, sy, w, fade):
    pygame.draw.ellipse(
        surf, lerp_color(ground_color_at(sy), GROUND_DEEP, 0.4 * (1.0 - fade)),
        (sx - w, sy - max(1, w // 3), w * 2, max(2, ri(w * 0.66))))


def draw_stump(surf, sx, sy, scale, fade, t, notes, garlands=0):
    """The Notice Stump: a broad cut trunk with commissions pinned to it."""
    s = scale * config.SC * 1.35
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    if s < 0.4:
        pygame.draw.rect(surf, col(WOOD), (sx - 2, sy - 4, 4, 4))
        return
    _contact(surf, sx, sy, ri(12 * s), fade)
    bw = ri(11 * s)
    bh = ri(9 * s)
    pygame.draw.rect(surf, col(WOOD_D), (sx - bw, sy - bh, bw * 2, bh))
    pygame.draw.rect(surf, col(WOOD), (sx - bw, sy - bh, ri(bw * 1.4), bh))
    # the cut top, with two growth rings
    pygame.draw.ellipse(surf, col(WOOD_L), (sx - bw, sy - bh - ri(3 * s),
                                            bw * 2, max(2, ri(6 * s))))
    for rr in (0.62, 0.3):
        pygame.draw.ellipse(surf, col(WOOD),
                            (sx - ri(bw * rr), sy - bh - ri(3 * s) + ri(1 * s),
                             ri(bw * rr * 2), max(1, ri(4.5 * s * rr))), 1)
    # a root flare on each side
    for dx in (-1, 1):
        pygame.draw.ellipse(surf, col(WOOD_D),
                            (sx + dx * bw - ri(3 * s), sy - ri(2.5 * s),
                             ri(6 * s), ri(3 * s)))
    # a little garland: one flower on the rim per finished chapter
    for gI in range(max(0, min(int(garlands), 5))):
        ga = 2.4 + gI * 0.75
        gx = sx + ri(math.cos(ga) * bw * 0.95)
        gy = sy - bh - ri(2.5 * s) + ri(math.sin(ga) * 2.5 * s)
        pc = ((238, 180, 190), (240, 214, 140), (186, 208, 236),
              (214, 186, 226), (196, 226, 186))[gI]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surf.set_at((clamp(gx + dx, 0, config.W - 1),
                         clamp(gy + dy, 0, config.H - 1)), col(pc))
        surf.set_at((clamp(gx, 0, config.W - 1), clamp(gy, 0, config.H - 1)),
                    col((255, 250, 232)))
    # pinned notices: one leaf per open work (capped), fluttering slightly
    n = max(1, min(int(notes), 3))
    for i in range(n):
        px = sx - ri(6 * s) + i * ri(6 * s)
        py = sy - bh + ri(1.5 * s) + (i % 2) * ri(1.5 * s)
        fl = math.sin(t * 2.0 + i * 1.7) * 0.6 * s
        pw = max(3, ri(4.5 * s))
        ph = max(4, ri(6 * s))
        pygame.draw.rect(surf, col(PAPER_D), (px + 1, py + 1 + ri(fl * 0.4), pw, ph))
        pygame.draw.rect(surf, col(PAPER), (px, py + ri(fl * 0.4), pw, ph))
        surf.set_at((clamp(px + pw // 2, 0, config.W - 1),
                     clamp(py + ri(fl * 0.4), 0, config.H - 1)), col(PIN))
        if s >= 0.8:
            for ln in range(2):
                pygame.draw.line(surf, col(PAPER_D),
                                 (px + 1, py + 2 + ln * 2 + ri(fl * 0.4)),
                                 (px + pw - 2, py + 2 + ln * 2 + ri(fl * 0.4)))


def draw_windmill(surf, sx, sy, scale, fade, blade_a, powered=False,
                  beat_phase=0.0):
    """A small stone windmill.  Blade angle comes straight from the sim, so
    it visibly spins at the tempo of whatever drummed music powers it."""
    s = scale * config.SC * 1.7
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    if s < 0.4:
        pygame.draw.rect(surf, col(STONE), (sx - 2, sy - 8, 4, 8))
        return
    _contact(surf, sx, sy, ri(11 * s), fade)
    th = ri(26 * s)
    tw_b = ri(8 * s)
    tw_t = ri(5 * s)
    pygame.draw.polygon(surf, col(STONE),
                        [(sx - tw_b, sy), (sx + tw_b, sy),
                         (sx + tw_t, sy - th), (sx - tw_t, sy - th)])
    pygame.draw.polygon(surf, col(STONE_D),
                        [(sx + ri(tw_b * 0.2), sy), (sx + tw_b, sy),
                         (sx + tw_t, sy - th), (sx + ri(tw_t * 0.2), sy - th)])
    # cap and door
    pygame.draw.ellipse(surf, col(WOOD_D), (sx - tw_t - 1, sy - th - ri(3 * s),
                                            (tw_t + 1) * 2, max(2, ri(5 * s))))
    dw = max(2, ri(3 * s))
    pygame.draw.rect(surf, col(WOOD_D), (sx - dw // 2, sy - ri(6 * s), dw, ri(6 * s)))
    # four sails around the hub
    hx, hy = sx, sy - th
    L = ri(14 * s)
    for k in range(4):
        a = blade_a + k * (math.tau / 4)
        ex = hx + math.cos(a) * L
        ey = hy + math.sin(a) * L * 0.86
        px = -math.sin(a) * 2.4 * s
        py = math.cos(a) * 2.0 * s
        pygame.draw.polygon(surf, col(SAIL),
                            [(hx, hy), (ri(ex + px), ri(ey + py)),
                             (ri(ex - px), ri(ey - py))])
        pygame.draw.line(surf, col(SAIL_D), (hx, hy), (ri(ex), ri(ey)), 1)
    pygame.draw.circle(surf, col(WOOD_D), (hx, hy), max(2, ri(1.8 * s)))
    if powered:
        # the hub winks on every garden beat -- it can hear the drums
        if beat_phase < 0.18:
            pygame.draw.circle(surf, col(SPARK), (hx, hy), max(1, ri(0.9 * s)))
        # a note glyph climbing off the cap now and then
        ph = (beat_phase * 0.5 + 0.25) % 1.0
        ny = hy - ri((4 + ph * 10) * s)
        nx = hx + ri(math.sin(ph * 5.0) * 2 * s)
        if ph < 0.8:
            surf.set_at((clamp(nx, 0, config.W - 1),
                         clamp(ny, 0, config.H - 1)), col(SPARK))
            surf.set_at((clamp(nx, 0, config.W - 1),
                         clamp(ny - 1, 0, config.H - 1)), col(SPARK))


def draw_seedbed(surf, sx, sy, scale, fade, t, water_frac, grown,
                 watering=False):
    """The windmill's bed: soil darkens as it drinks; a full bed grows a
    glowing seed pod Bal can harvest."""
    s = scale * config.SC * 1.2
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    if s < 0.4:
        return
    w = ri(13 * s)
    h = max(3, ri(6 * s))
    soil = lerp_color(SOIL_DRY, SOIL_WET, max(0.0, min(1.0, water_frac)))
    pygame.draw.ellipse(surf, col(lerp_color(soil, (60, 46, 36), 0.3)),
                        (sx - w, sy - h // 2, w * 2, h))
    pygame.draw.ellipse(surf, col(soil), (sx - w, sy - h // 2 - 1, w * 2, h))
    # three little mounds
    for i, dx in enumerate((-7.0, 0.0, 7.0)):
        mx = sx + ri(dx * s)
        pygame.draw.ellipse(surf, col(lerp_color(soil, (255, 244, 210), 0.18)),
                            (mx - ri(2.5 * s), sy - ri(2.2 * s) - (i % 2),
                             ri(5 * s), max(2, ri(2.4 * s))))
    # while drums power the mill, droplets fall onto the bed
    if watering and s >= 0.5:
        for k in range(2):
            ph = (t * 1.6 + k * 0.5) % 1.0
            dx2 = ri((k * 7 - 3) * s)
            dy2 = ri((1.0 - ph) * -9 * s)
            surf.set_at((clamp(sx + dx2, 0, config.W - 1),
                         clamp(sy - h // 2 + dy2, 0, config.H - 1)),
                        col(FW_SHALLOW))
    # three little moisture glints as the bed fills (thirds)
    for i in range(3):
        if water_frac >= (i + 1) / 3.0 - 1e-6:
            gx2 = sx + ri((i - 1) * 8 * s)
            gy2 = sy + ri(1 * s)
            if (t * 1.2 + i * 0.4) % 1.0 < 0.7:
                surf.set_at((clamp(gx2, 0, config.W - 1),
                             clamp(gy2, 0, config.H - 1)),
                            col(lerp_color(FW_SHALLOW, (255, 255, 255), 0.3)))
    # a shy green tip appears as the bed drinks
    if 0.25 < water_frac and not grown:
        tip = ri(2 + water_frac * 4 * s)
        pygame.draw.line(surf, col((96, 150, 92)), (sx, sy - ri(1 * s)),
                         (sx, sy - ri(1 * s) - tip), 1)
    if grown:
        hh = ri(9 * s) + ri(math.sin(t * 2.2) * 1.2 * s)
        pygame.draw.line(surf, col((96, 150, 92)), (sx, sy), (sx, sy - hh), 1)
        pod = (255, 214, 130)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surf.set_at((clamp(sx + dx, 0, config.W - 1),
                         clamp(sy - hh + dy, 0, config.H - 1)), col(pod))
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - hh, 0, config.H - 1)),
                    col((255, 250, 232)))
        if (t * 2.0) % 1.0 < 0.5:
            surf.set_at((clamp(sx + ri(3 * s), 0, config.W - 1),
                         clamp(sy - hh - ri(2 * s), 0, config.H - 1)), col(SPARK))


def draw_gramophone(surf, sx, sy, scale, fade, t, playing, bloom=False):
    """A planted record-flower: wooden base grown with vines, a big brass
    horn-blossom tilted at the sky, petals when the garden has its First
    Garden Song.  It should read as the proudest plant in any bed."""
    s = scale * config.SC * 1.55
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    if s < 0.4:
        pygame.draw.rect(surf, col(BRASS), (sx - 2, sy - 5, 4, 5))
        return
    _contact(surf, sx, sy, ri(8 * s), fade)
    sway = math.sin(t * 1.2) * 0.8 * s if playing else 0.0

    # the rooted wooden base, with a vine and two leaves climbing it
    bw = max(4, ri(5.5 * s))
    bh = max(4, ri(5 * s))
    pygame.draw.rect(surf, col(WOOD_D), (sx - bw, sy - bh, bw * 2, bh))
    pygame.draw.rect(surf, col(WOOD), (sx - bw, sy - bh, bw + 1, bh))
    pygame.draw.line(surf, col((96, 150, 92)), (sx - bw, sy),
                     (sx - bw + ri(2 * s), sy - bh - ri(1 * s)), 1)
    for lx, ly in ((sx - bw + ri(1 * s), sy - ri(2 * s)),
                   (sx + bw - ri(2 * s), sy - bh + ri(1 * s))):
        pygame.draw.ellipse(surf, col((74, 124, 76)),
                            (lx, ly, max(2, ri(3 * s)), max(1, ri(1.6 * s))))

    # the disc on top, dot orbiting while it plays
    dr = max(3, ri(3.4 * s))
    pygame.draw.ellipse(surf, col((64, 58, 66)),
                        (sx - dr, sy - bh - ri(2 * s), dr * 2, max(2, ri(2.8 * s))))
    if playing:
        a = t * 5.0
        px = sx + ri(math.cos(a) * dr * 0.55)
        py = sy - bh - ri(0.8 * s) + ri(math.sin(a) * dr * 0.3)
        surf.set_at((clamp(px, 0, config.W - 1), clamp(py, 0, config.H - 1)),
                    col((236, 232, 226)))

    # the horn: a tall brass stem opening into a flower-bell
    hx = sx - ri(1.5 * s)
    hy = sy - bh - ri(2 * s)
    ex = hx - ri(6.5 * s + sway)
    ey = hy - ri(11 * s)
    mx = hx - ri(2.5 * s + sway * 0.5)
    my = hy - ri(6 * s)
    pygame.draw.line(surf, col(BRASS_D), (hx, hy), (mx, my), max(1, ri(1.6 * s)))
    pygame.draw.line(surf, col(BRASS_D), (mx, my), (ex, ey), max(1, ri(1.8 * s)))
    r = max(3, ri(5.2 * s))
    pygame.draw.circle(surf, col(BRASS), (ex, ey), r)
    pygame.draw.circle(surf, col(BRASS_D), (ex, ey), r, 1)
    pygame.draw.circle(surf, col(lerp_color(BRASS, (255, 255, 255), 0.45)),
                       (ex - r // 3, ey - r // 3), max(1, ri(r * 0.4)))
    pygame.draw.circle(surf, col((72, 58, 48)), (ex - r // 4, ey), max(1, r // 3))

    # petals around the bell -- shy before the First Garden Song, open after
    n_pet = 6 if bloom else 3
    for k in range(n_pet):
        pa = t * (0.5 if playing else 0.15) + k * (math.tau / n_pet)
        pxx = ex + ri(math.cos(pa) * (r + 2))
        pyy = ey + ri(math.sin(pa) * (r + 2) * 0.8)
        pc = (238, 180, 190) if bloom else (224, 206, 160)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surf.set_at((clamp(pxx + dx, 0, config.W - 1),
                         clamp(pyy + dy, 0, config.H - 1)), col(pc))
        surf.set_at((clamp(pxx, 0, config.W - 1), clamp(pyy, 0, config.H - 1)),
                    col((255, 246, 224)))
    if playing and (t * 1.6) % 1.0 < 0.5:
        surf.set_at((clamp(ex - r - 1, 0, config.W - 1),
                     clamp(ey - r - 2, 0, config.H - 1)), col(SPARK))


def draw_bloom(surf, sx, sy, scale, fade, t, seed=0):
    """A small tuft of celebration flowers left where a work was finished."""
    s = scale * config.SC
    if s < 0.45:
        return
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    _contact(surf, sx, sy, max(2, ri(3 * s)), fade)
    cols = ((238, 180, 190), (240, 214, 140), (186, 208, 236))
    for k in range(3):
        a = seed * 1.7 + k * 2.1
        fx = sx + ri(math.cos(a) * 3.5 * s)
        hh = ri((5 + (k % 2) * 2) * s) + ri(math.sin(t * 1.6 + a) * 0.8 * s)
        pygame.draw.line(surf, col((96, 150, 92)), (fx, sy), (fx, sy - hh), 1)
        pc = cols[(seed + k) % 3]
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surf.set_at((clamp(fx + dx, 0, config.W - 1),
                         clamp(sy - hh + dy, 0, config.H - 1)), col(pc))
        surf.set_at((clamp(fx, 0, config.W - 1),
                     clamp(sy - hh, 0, config.H - 1)), col((255, 250, 232)))
