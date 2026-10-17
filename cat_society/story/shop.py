"""Bal's hand-built music shop and its construction animation."""

import math
import random

import pygame

from .. import config
from ..palette import GROUND_DEEP
from ..projection import project
from ..utils import clamp, lerp_color, ri


WOOD = (144, 96, 58)
WOOD_D = (91, 64, 45)
WOOD_L = (199, 145, 88)
ROOF = (192, 112, 92)
ROOF_L = (235, 157, 131)
AWNING = (238, 210, 164)
PAPER = (249, 239, 210)
INK = (68, 61, 58)
GOLD = (240, 189, 91)
GREEN = (96, 139, 103)


class Shop:
    def __init__(self, x=None, z=None, built=1.0):
        self.x = x
        self.z = z
        self.build = float(built)
        self.building = False
        self.t = 0.0
        self._dust = []
        self._rng = random.Random(1887)

    @property
    def placed(self):
        return self.x is not None and self.z is not None

    @property
    def ready(self):
        return self.placed and self.build >= 1.0 and not self.building

    def start_build(self, x, z):
        self.x, self.z = float(x), float(z)
        self.build = 0.0
        self.building = True
        self.t = 0.0
        self._dust = []

    def update(self, dt):
        self.t += dt
        if self.building:
            self.build = min(1.0, self.build + dt / 2.15)
            if self._rng.random() < dt * 18.0:
                self._dust.append([
                    self._rng.uniform(-28, 28),
                    self._rng.uniform(-2, 8),
                    self._rng.uniform(-13, 13),
                    self._rng.uniform(14, 30),
                    self._rng.uniform(0.45, 0.95),
                    0.0,
                ])
            if self.build >= 1.0:
                self.building = False
        for p in self._dust:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] -= 32 * dt
            p[5] += dt
        self._dust = [p for p in self._dust if p[5] < p[4]]

    def valid_at(self, game, x, z):
        # The shop needs a genuinely dry, open patch, not merely a dry centre.
        for dx, dz in ((0, 0), (-75, 0), (75, 0), (0, -55), (0, 65),
                       (-60, 45), (60, 45)):
            if game.water.depth_at(x + dx, z + dz)[0] > 0.02:
                return False, "The shop needs a little more dry ground."
        for r, wx, wz in game.world.solids_near(x, z):
            if r > 0 and math.hypot(wx - x, wz - z) < r + 86.0:
                return False, "A tree or stone is too close to build here."
        for ob in game.water.interactives:
            if math.hypot(ob.x - x, ob.z - z) < 130.0:
                return False, "Leave a little room around the old landmark."
        return True, "A lovely place for a music shop."

    def solids_near(self, x, z):
        if not self.ready or math.hypot(x - self.x, z - self.z) > 220.0:
            return []
        # Back wall and side posts; the counter remains approachable.
        return [(32.0, self.x - 48.0, self.z + 18.0),
                (32.0, self.x + 48.0, self.z + 18.0),
                (34.0, self.x, self.z + 45.0)]

    def world_drawables(self, game, preview=None):
        out = []
        if self.placed:
            pr = project(self.x, self.z, game.cam)
            if pr is not None:
                sx, sy, sc = pr
                sc *= 1.34
                progress = self.build
                t = game.time
                out.append((sy, 40, lambda surf, a=(sx, sy, sc, progress, t):
                            draw_shop(surf, a[0], a[1], a[2], a[3], a[4], False)))
                if self._dust:
                    dust = [tuple(p) for p in self._dust]
                    out.append((sy + 1, 40, lambda surf, a=(sx, sy, sc, dust):
                                draw_build_dust(surf, a[0], a[1], a[2], a[3])))
        if preview is not None:
            x, z, ok = preview
            pr = project(x, z, game.cam)
            if pr is not None:
                sx, sy, sc = pr
                sc *= 1.34
                out.append((sy, 40, lambda surf, a=(sx, sy, sc, ok, game.time):
                            draw_shop(surf, a[0], a[1], a[2], 0.72, a[4], True, a[3])))
        return out


def _shadow(surf, sx, sy, s, alpha=100):
    pad = max(2, ri(65 * s))
    sh = pygame.Surface((pad * 2, max(2, ri(22 * s))), pygame.SRCALPHA)
    pygame.draw.ellipse(sh, (45, 50, 38, alpha), sh.get_rect())
    surf.blit(sh, (sx - pad, sy - sh.get_height() // 2))


def draw_shop(surf, sx, sy, scale, progress, t, preview=False, valid=True):
    """Draw the complete shop or its translucent placement ghost."""
    s = scale * config.SC
    if s <= 0.07:
        return
    sx, sy = ri(sx), ri(sy)
    alpha = 155 if preview else 255
    tint = (100, 170, 115) if valid else (205, 105, 100)
    p = clamp(progress, 0.0, 1.0)
    rise = (1.0 - p) * 35.0 * s
    sy2 = sy + ri(rise)

    layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    _shadow(layer, sx, sy, s, 65 if preview else 92)

    # Foundation, front deck and counter.
    deck_w, deck_h = ri(74 * s), max(2, ri(12 * s))
    pygame.draw.polygon(layer, (*WOOD_D, alpha), [
        (sx - deck_w, sy2), (sx + deck_w, sy2),
        (sx + ri(60 * s), sy2 - deck_h), (sx - ri(60 * s), sy2 - deck_h)])
    for k in range(-5, 6):
        x = sx + ri(k * 11 * s)
        pygame.draw.line(layer, (*WOOD_L, alpha), (x, sy2 - deck_h + 1),
                         (x + ri(2 * s), sy2 - 1), max(1, ri(s)))

    wall_y = sy2 - ri(70 * s * p)
    wall = pygame.Rect(sx - ri(57 * s), wall_y, ri(114 * s), ri(62 * s * p))
    if wall.h > 1:
        pygame.draw.rect(layer, (*AWNING, alpha), wall)
        pygame.draw.rect(layer, (*WOOD_D, alpha), wall, max(1, ri(2 * s)))
        for k in range(1, 6):
            yy = wall.y + k * wall.h // 6
            pygame.draw.line(layer, (*lerp_color(AWNING, WOOD_L, 0.24), alpha),
                             (wall.x + 1, yy), (wall.right - 1, yy), max(1, ri(s)))

    # Open shop window/counter.
    opening = pygame.Rect(sx - ri(42 * s), sy2 - ri(55 * s * p),
                          ri(84 * s), ri(34 * s * p))
    if opening.h > 1:
        pygame.draw.rect(layer, (*WOOD_D, alpha), opening)
        back = opening.inflate(-max(2, ri(5 * s)), -max(2, ri(5 * s)))
        pygame.draw.rect(layer, (*(46, 52, 54), alpha), back)
        # little jars and instrument shapes on the back shelf
        shelf_y = back.bottom - ri(7 * s)
        pygame.draw.line(layer, (*WOOD_L, alpha), (back.x, shelf_y),
                         (back.right, shelf_y), max(1, ri(2 * s)))
        for i, col in enumerate(((234, 153, 129), (125, 184, 164), (236, 194, 105), (142, 169, 210))):
            bx = back.x + ri((12 + i * 18) * s)
            pygame.draw.rect(layer, (*col, alpha),
                             (bx, shelf_y - ri((5 + i % 2 * 3) * s),
                              max(2, ri(6 * s)), max(2, ri((5 + i % 2 * 3) * s))))
    counter_y = sy2 - ri(18 * s)
    pygame.draw.rect(layer, (*WOOD, alpha),
                     (sx - ri(48 * s), counter_y, ri(96 * s), max(2, ri(9 * s))))
    pygame.draw.line(layer, (*WOOD_L, alpha), (sx - ri(48 * s), counter_y),
                     (sx + ri(48 * s), counter_y), max(1, ri(2 * s)))

    # Roof, awning and striped scallops.
    roof_y = sy2 - ri(76 * s * p)
    roof_pts = [(sx - ri(70 * s), roof_y + ri(12 * s)),
                (sx, roof_y - ri(24 * s)),
                (sx + ri(70 * s), roof_y + ri(12 * s))]
    pygame.draw.polygon(layer, (*ROOF, alpha), roof_pts)
    pygame.draw.line(layer, (*ROOF_L, alpha), roof_pts[0], roof_pts[1], max(1, ri(3 * s)))
    aw_y = sy2 - ri(45 * s * p)
    pygame.draw.polygon(layer, (*PAPER, alpha), [
        (sx - ri(53 * s), aw_y), (sx + ri(53 * s), aw_y),
        (sx + ri(47 * s), aw_y + ri(15 * s)), (sx - ri(47 * s), aw_y + ri(15 * s))])
    for k in range(-4, 5):
        x0 = sx + ri(k * 12 * s)
        pygame.draw.polygon(layer, (*((ROOF_L if k % 2 else PAPER)), alpha), [
            (x0 - ri(6 * s), aw_y), (x0 + ri(6 * s), aw_y),
            (x0 + ri(5 * s), aw_y + ri(14 * s)), (x0 - ri(5 * s), aw_y + ri(14 * s))])

    # Hanging sign and bell animate even when the shop is idle.
    sign_x = sx - ri(78 * s)
    pygame.draw.line(layer, (*WOOD_D, alpha), (sx - ri(55 * s), roof_y + ri(6 * s)),
                     (sign_x, roof_y + ri(6 * s)), max(1, ri(2 * s)))
    pygame.draw.line(layer, (*WOOD_D, alpha), (sign_x, roof_y + ri(6 * s)),
                     (sign_x, roof_y + ri(25 * s)), max(1, ri(2 * s)))
    sign = pygame.Rect(sign_x - ri(21 * s), roof_y + ri(23 * s), ri(42 * s), ri(20 * s))
    pygame.draw.rect(layer, (*PAPER, alpha), sign, border_radius=max(1, ri(3 * s)))
    pygame.draw.rect(layer, (*WOOD_D, alpha), sign, max(1, ri(2 * s)),
                     border_radius=max(1, ri(3 * s)))
    # Music-note mark, readable even at small scale.
    cx, cy = sign.center
    pygame.draw.circle(layer, (*INK, alpha), (cx - ri(3 * s), cy + ri(4 * s)), max(1, ri(3 * s)))
    pygame.draw.line(layer, (*INK, alpha), (cx, cy + ri(3 * s)),
                     (cx, cy - ri(6 * s)), max(1, ri(2 * s)))
    pygame.draw.line(layer, (*INK, alpha), (cx, cy - ri(6 * s)),
                     (cx + ri(7 * s), cy - ri(3 * s)), max(1, ri(2 * s)))
    bell_x = sx + ri(42 * s)
    bell_y = aw_y + ri(18 * s) + ri(math.sin(t * 2.3) * 0.6 * s)
    pygame.draw.line(layer, (*WOOD_D, alpha), (bell_x, aw_y + ri(4 * s)),
                     (bell_x, bell_y), max(1, ri(s)))
    pygame.draw.circle(layer, (*GOLD, alpha), (bell_x, bell_y), max(2, ri(4 * s)))

    if preview:
        # A readable footprint ring: green means yes, rose means no.
        ring = pygame.Surface((max(4, ri(180 * s)), max(3, ri(48 * s))), pygame.SRCALPHA)
        pygame.draw.ellipse(ring, (*tint, 110), ring.get_rect(), max(1, ri(3 * s)))
        layer.blit(ring, (sx - ring.get_width() // 2, sy - ring.get_height() // 2))

    surf.blit(layer, (0, 0))


def draw_build_dust(surf, sx, sy, scale, dust):
    s = scale * config.SC
    for dx, dy, _vx, _vy, life, age in dust:
        a = max(0, int(165 * (1.0 - age / max(0.01, life))))
        r = max(1, ri((2.5 + age * 4.0) * s))
        puff = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(puff, (226, 199, 151, a), (r + 1, r + 1), r)
        surf.blit(puff, (ri(sx + dx * s) - r, ri(sy - dy * s) - r))
