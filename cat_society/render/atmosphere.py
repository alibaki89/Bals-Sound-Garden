"""Painters for the ambient air critters and petals defined in
:mod:`cat_society.entities.critters` and
:mod:`cat_society.entities.particles`."""

import math

import pygame

from .. import config
from ..utils import ri, lerp_color
from ..palette import *


def draw_cloud(surf, x, y, s, palette=None):
    x, y = ri(x), ri(y)
    w = ri(40 * s)
    h = ri(14 * s)
    puffs = [(-w * 0.34, 3, w * 0.36, h * 0.85),
             (-w * 0.06, 1, w * 0.34, h * 0.95),
             (w * 0.04, -2, w * 0.42, h * 1.05),
             (w * 0.36, 2, w * 0.32, h * 0.82)]
    palette = palette or {}
    cloud_lo = palette.get("cloud_lo", CLOUD_LO)
    cloud = palette.get("cloud_body", CLOUD)
    cloud_hi = palette.get("cloud_hi", CLOUD_HI)
    # soft cool underside shadow (sits a touch lower for a rounded base)
    for dx, dy, pw, pyh in puffs:
        pygame.draw.ellipse(surf, cloud_lo, (x + ri(dx), y + ri(dy) + 2, max(2, ri(pw)), max(2, ri(pyh))))
    # body
    for dx, dy, pw, pyh in puffs:
        pygame.draw.ellipse(surf, cloud, (x + ri(dx), y + ri(dy), max(2, ri(pw)), max(2, ri(pyh))))
    # warm sunlit crown (the sun sits up and to the right), then a couple of
    # cooler-white highlights, so the cloud reads as a soft lit volume rather
    # than a flat blob
    warm = lerp_color(cloud_hi, CLOUD_WARM, 0.7)
    pygame.draw.ellipse(surf, warm, (x + ri(w * 0.02), y - ri(3), max(2, ri(w * 0.40)), max(2, ri(h * 0.55))))
    pygame.draw.ellipse(surf, cloud_hi, (x + ri(w * 0.16), y - ri(2), max(2, ri(w * 0.24)), max(2, ri(h * 0.42))))
    pygame.draw.ellipse(surf, cloud_hi, (x - ri(w * 0.14), y - ri(1), max(2, ri(w * 0.18)), max(2, ri(h * 0.36))))


def draw_bird(surf, b, t):
    x, y = ri(b.x), ri(b.y)
    flap = math.sin(t * b.flap + b.phase)
    w = max(2, ri(4 * b.s))
    up = ri((1.6 + flap * 1.8) * b.s)
    c = (94, 92, 110)
    pygame.draw.line(surf, c, (x - w, y - up), (x, y), max(1, ri(1.4 * b.s)))
    pygame.draw.line(surf, c, (x, y), (x + w, y - up), max(1, ri(1.4 * b.s)))


def draw_butterfly(surf, sx, sy, s, flap, col):
    sx, sy = ri(sx), ri(sy)
    if s <= 0:
        return
    wfull = max(2, ri(5 * s))
    wnow = max(1, ri((2 + 3 * abs(flap)) * s))
    wh = max(1, ri(3 * s))
    dark = lerp_color(col, (60, 50, 70), 0.4)
    # left + right wings
    pygame.draw.ellipse(surf, col, (sx - wnow, sy - wh, wnow, wh + wh))
    pygame.draw.ellipse(surf, col, (sx, sy - wh, wnow, wh + wh))
    pygame.draw.line(surf, dark, (sx, sy - wh), (sx, sy + wh), max(1, ri(1 * s)))


def draw_petal(surf, p):
    x, y = ri(p.x), ri(p.y)
    if 0 <= x < config.W and 0 <= y < config.H:
        if p.size == 1:
            surf.set_at((x, y), p.col)
        else:
            pygame.draw.rect(surf, p.col, (x, y, 2, 1))
            surf.set_at((x, y + 1), lerp_color(p.col, (255, 255, 255), 0.3))
