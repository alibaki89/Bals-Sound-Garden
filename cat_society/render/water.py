"""Painters for the small things that live *in* the water: reeds, lily pads,
wet stones, fish and frogs, plus the :func:`draw_water_obj` dispatcher.

The water surface itself and the built structures (bridges, boats, wells,
fountains) are drawn elsewhere - see :mod:`cat_society.world.water` and
:mod:`cat_society.render.structures`."""

import math

import pygame

from .. import config
from ..config import *
from ..utils import ri, clamp, lerp_color
from ..palette import *
from .props import _haze, draw_prop


def draw_reed(surf, sx, sy, scale, fade, seed, t):
    s = scale * config.SC
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    n = 3 + int(seed * 3)
    base = (74, 150, 92)
    base_d = (58, 128, 78)
    tip_c = (126, 194, 124)
    sway = math.sin(t * 1.6 + seed * 6.0)
    for i in range(n):
        off = (i - (n - 1) / 2.0)
        bx = sx + ri(off * 2.6 * s)
        hh = ri((17 + (i % 2) * 6 + seed * 7) * s)
        if hh < 2:
            surf.set_at((clamp(bx, 0, config.W - 1), clamp(sy - 1, 0, config.H - 1)), col(base))
            continue
        tipx = bx + ri(sway * 3.0 * s * (0.5 + 0.18 * i))
        tipy = sy - hh
        # shaded back-stroke then the lit blade for a touch of depth
        pygame.draw.line(surf, col(base_d), (bx + 1, sy), (tipx + 1, tipy), max(1, ri(1.4 * s)))
        pygame.draw.line(surf, col(base), (bx, sy), (tipx, tipy), max(1, ri(1.4 * s)))
        surf.set_at((clamp(tipx, 0, config.W - 1), clamp(tipy, 0, config.H - 1)), col(tip_c))
    # a cattail on some clumps
    if seed < 0.45 and ri(16 * s) >= 2:
        cyt = sy - ri(19 * s)
        pygame.draw.ellipse(surf, col((150, 96, 60)),
                            (sx - ri(1.6 * s), cyt, max(1, ri(3 * s)), max(2, ri(7 * s))))
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(cyt, 0, config.H - 1)), col((182, 130, 88)))


def draw_lily(surf, sx, sy, scale, fade, seed, t):
    s = scale * config.SC
    col = _haze(fade)
    bob = math.sin(t * 1.4 + seed * 6.0) * 1.0 * s
    sx, sy = ri(sx), ri(sy + bob)
    r = ri(7 * s)
    if r < 1:
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy, 0, config.H - 1)), col((86, 168, 108)))
        return
    # rounded pad: dark rim, rich body, a lit upper crescent and a soft glint
    pygame.draw.ellipse(surf, col((46, 122, 84)), (sx - r, sy - ri(r * 0.6), r * 2, max(1, ri(r * 1.2))))
    pygame.draw.ellipse(surf, col((92, 176, 116)), (sx - r + 1, sy - ri(r * 0.6) + 1,
                                                    r * 2 - 2, max(1, ri(r * 1.2) - 2)))
    pygame.draw.ellipse(surf, col((126, 200, 138)), (sx - r + ri(2 * s), sy - ri(r * 0.6) + 1,
                                                     max(1, ri(r * 1.1)), max(1, ri(r * 0.6))))
    surf.set_at((clamp(sx - ri(2 * s), 0, config.W - 1), clamp(sy - ri(2 * s), 0, config.H - 1)), col((160, 218, 158)))
    # the radial notch that reads "lily pad"
    pygame.draw.line(surf, col((46, 122, 84)), (sx, sy), (sx + r, sy - ri(1 * s)), 1)
    # a bloom on some pads: a pink waterlily, or a rarer creamy-white one
    if seed > 0.62:
        if seed > 0.82:
            pets, ctr = (250, 250, 244), (255, 224, 128)     # white waterlily
        else:
            pets, ctr = (255, 200, 224), (255, 240, 120)     # pink waterlily
        bx, by = sx + ri(2 * s), sy - ri(2 * s)
        pygame.draw.circle(surf, col(pets), (bx, by), max(1, ri(2 * s)))
        for dx, dy in ((-1, 0), (1, 0), (0, -1)):
            surf.set_at((clamp(bx + dx, 0, config.W - 1), clamp(by + dy, 0, config.H - 1)), col(pets))
        surf.set_at((clamp(bx, 0, config.W - 1), clamp(by, 0, config.H - 1)), col(ctr))


def draw_wstone(surf, sx, sy, scale, fade, seed, t):
    s = scale * config.SC
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    r = ri(6 * s)
    if r < 1:
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy, 0, config.H - 1)), col((150, 150, 160)))
        return
    pygame.draw.ellipse(surf, col((110, 110, 124)), (sx - r, sy - ri(r * 0.9), r * 2, max(1, ri(r * 1.1))))
    pygame.draw.ellipse(surf, col((150, 150, 162)), (sx - r + 1, sy - ri(r * 0.9), r * 2 - 2, max(1, ri(r * 0.7))))
    pygame.draw.ellipse(surf, col((184, 184, 194)), (sx - r + ri(2 * s), sy - ri(r * 0.85),
                                                     max(1, ri(r * 0.9)), max(1, ri(r * 0.4))))
    # a little wet waterline ring at the base
    pygame.draw.line(surf, col(FOAM), (sx - r, sy + ri(1 * s)), (sx + r, sy + ri(1 * s)), 1)


def draw_fish(surf, sx, sy, scale, fade, seed, t):
    s = scale * config.SC
    col = _haze(fade)
    ph = t * 1.1 + seed * 6.28
    drift = math.sin(ph) * 10.0 * s
    jump = max(0.0, math.sin(t * 0.7 + seed * 5.0) - 0.86) * 9.0
    sx = ri(sx + drift)
    sy = ri(sy - jump * s)
    facing = 1 if math.cos(ph) >= 0 else -1
    body_l = ri(6 * s)
    body_h = ri(3 * s)
    fc = [(232, 150, 96), (236, 196, 120), (150, 170, 210), (122, 142, 174)][int(seed * 4) % 4]
    if body_l < 2:
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy, 0, config.H - 1)), col(fc))
        return
    pygame.draw.ellipse(surf, col(fc), (sx - body_l, sy - body_h, body_l * 2, body_h * 2))
    # a lit belly stripe for a glossy fish
    pygame.draw.ellipse(surf, col(lerp_color(fc, (255, 255, 255), 0.3)),
                        (sx - body_l + max(1, ri(1 * s)), sy - body_h, max(1, ri(body_l * 1.2)), max(1, body_h)))
    tx = sx - facing * body_l
    pygame.draw.polygon(surf, col(fc), [(tx, sy),
                                        (tx - facing * ri(4 * s), sy - ri(3 * s)),
                                        (tx - facing * ri(4 * s), sy + ri(3 * s))])
    surf.set_at((clamp(sx + facing * ri(3 * s), 0, config.W - 1), clamp(sy - ri(1 * s), 0, config.H - 1)), (40, 40, 50))
    if jump <= 0.02:
        pygame.draw.line(surf, col(FOAM), (sx - body_l, sy + body_h + ri(1 * s)),
                         (sx + body_l, sy + body_h + ri(1 * s)), 1)
    else:
        for k in range(2):
            surf.set_at((clamp(sx + ri((k - 0) * 2 * s), 0, config.W - 1),
                         clamp(sy + body_h + ri(2 * s), 0, config.H - 1)), col(FOAM))


def draw_frog(surf, sx, sy, scale, fade, seed, t):
    s = scale * config.SC
    col = _haze(fade)
    air = max(0.0, math.sin(t * 1.3 + seed * 4.0) - 0.82) * 11.0
    sx = ri(sx)
    sy = ri(sy - air * s)
    bw = ri(7 * s)
    bh = ri(5 * s)
    green = (98, 176, 96)
    green_d = (70, 140, 76)
    green_l = (152, 206, 134)
    if bw < 2:
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy, 0, config.H - 1)), col(green))
        return
    pygame.draw.ellipse(surf, col(green_d), (sx - bw, sy - bh, bw * 2, bh * 2))
    pygame.draw.ellipse(surf, col(green), (sx - bw + 1, sy - bh + 1, bw * 2 - 2, bh * 2 - 2))
    pygame.draw.ellipse(surf, col(green_l), (sx - ri(3 * s), sy - ri(1 * s), max(2, ri(6 * s)), max(1, ri(3 * s))))
    pygame.draw.line(surf, col(green_d), (sx - bw + 1, sy + bh - 1),
                     (sx - bw - ri(2 * s), sy + bh + ri(1 * s)), max(1, ri(1.4 * s)))
    pygame.draw.line(surf, col(green_d), (sx + bw - 1, sy + bh - 1),
                     (sx + bw + ri(2 * s), sy + bh + ri(1 * s)), max(1, ri(1.4 * s)))
    ex = ri(3 * s)
    ey = sy - bh
    blink = math.sin(t * 0.9 + seed * 7.0) > 0.95
    for sgn in (-1, 1):
        pygame.draw.circle(surf, col(green), (sx + sgn * ex, ey), max(1, ri(2 * s)))
        if blink:
            surf.set_at((clamp(sx + sgn * ex, 0, config.W - 1), clamp(ey, 0, config.H - 1)), col(green_d))
        else:
            surf.set_at((clamp(sx + sgn * ex, 0, config.W - 1), clamp(ey, 0, config.H - 1)), (30, 34, 40))
    pygame.draw.line(surf, col(green_d), (sx - ri(2 * s), sy + ri(1 * s)),
                     (sx + ri(2 * s), sy + ri(1 * s)), 1)


def draw_water_obj(surf, kind, sx, sy, scale, seed, fade, t):
    if kind == "reed":
        draw_reed(surf, sx, sy, scale, fade, seed, t)
    elif kind == "lily":
        draw_lily(surf, sx, sy, scale, fade, seed, t)
    elif kind == "wstone":
        draw_wstone(surf, sx, sy, scale, fade, seed, t)
    elif kind == "fish":
        draw_fish(surf, sx, sy, scale, fade, seed, t)
    elif kind == "frog":
        draw_frog(surf, sx, sy, scale, fade, seed, t)
    elif kind == "flower":
        draw_prop(surf, "flower", sx, sy, scale, seed, fade)
    elif kind == "tuft":
        draw_prop(surf, "tuft", sx, sy, scale, seed, fade)
