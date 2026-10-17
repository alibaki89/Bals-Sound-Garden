"""The player cat: movement, jumping, the paw swat, mood and the wading/swimming
state that the water biome drives.

State lives here; the actual pixel art is drawn by
:func:`cat_society.render.cat.draw_cat`, which :meth:`Cat.draw` calls."""

import math
import random

from .. import config
from ..config import *
from ..render.cat import draw_cat


class Cat:
    def __init__(self):
        self.x = 0.0
        self.z = 0.0
        self.facing = 1
        self.t = 0.0
        self.moving = False
        self.running = False
        self.blink_t = 0.0
        self.blink = False
        self.y_off = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.attack_t = 0.0
        self.expression = "neutral"
        self.sleeping = False
        self.boat = None
        self.swim = 0.0          # 0 = on land, 1 = fully swimming (smoothed)
        self.in_water = False
        self.splash_t = 0.0      # brief entry-splash timer
        self.bridge_lift = 0.0   # world-height the bridge arch lifts the cat

    def jump(self):
        if self.on_ground:
            self.vy = JUMP_V0 * config.SC
            self.on_ground = False
            self.sleeping = False

    def attack(self):
        if self.attack_t <= 0.0:
            self.attack_t = ATTACK_DUR
            self.sleeping = False

    def set_expression(self, name):
        self.expression = name

    def update(self, dt, ix, iz, running=False, speed_scale=1.0):
        mag = math.hypot(ix, iz)
        if self.sleeping and mag > 0:
            self.sleeping = False
        if self.sleeping and self.on_ground:
            self.moving = False
            self.running = False
            if self.attack_t > 0.0:
                self.attack_t = max(0.0, self.attack_t - dt)
            self.t += dt
            return

        if mag > 0:
            ix, iz = ix / mag, iz / mag
            self.moving = True
        else:
            self.moving = False

        run_move = running and self.moving
        spd = CAT_SPEED * (RUN_MULT if run_move else 1.0) * speed_scale
        self.x += ix * spd * dt
        self.z += iz * spd * dt
        self.running = run_move and self.on_ground and speed_scale > 0.9

        if ix > 0.01:
            self.facing = 1
        elif ix < -0.01:
            self.facing = -1

        if not self.on_ground:
            self.y_off += self.vy * dt
            self.vy -= JUMP_GRAV * config.SC * dt
            if self.y_off <= 0.0:
                self.y_off = 0.0
                self.vy = 0.0
                self.on_ground = True

        if self.attack_t > 0.0:
            self.attack_t = max(0.0, self.attack_t - dt)

        self.t += dt
        self.blink_t += dt
        if self.blink:
            if self.blink_t > 0.12:
                self.blink = False
                self.blink_t = 0.0
        elif self.blink_t > random.uniform(2.4, 4.2):
            self.blink = True
            self.blink_t = 0.0

    # solids are drawn generously but should block a touch tighter than
    # they look, so Bal brushes past trunks instead of bouncing off air
    SOLID_FIT = 0.84

    def resolve_collisions(self, solids):
        for _ in range(3):
            worst, worst_pen = None, 0.0
            for r, wx, wz in solids:
                dx = self.x - wx
                dz = self.z - wz
                md = CAT_R + r * self.SOLID_FIT
                d = math.hypot(dx, dz)
                pen = md - d
                if pen > worst_pen:
                    worst, worst_pen = (dx, dz, d, md, wx, wz), pen
            if worst is None:
                break
            dx, dz, d, md, wx, wz = worst
            if d < 1e-6:
                dx, dz, d = 1.0, 0.0, 1.0
            f = md / d
            # a radial push-out: Bal slides along the rim instead of stopping
            self.x = wx + dx * f
            self.z = wz + dz * f

    def draw(self, surf, sx, sy, scale, draw_shadow=True, swim=0.0, palette=None):
        draw_cat(surf, sx, sy, self.facing, self.t, scale * CAT_DRAW_SCALE,
                 self.moving, self.running, self.blink,
                 self.y_off, self.attack_t, self.expression, self.sleeping,
                 draw_shadow=draw_shadow, swim=swim, palette=palette)
