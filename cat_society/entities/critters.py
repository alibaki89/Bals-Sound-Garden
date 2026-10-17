"""Ambient sky/air critters: drifting clouds, wheeling birds and butterflies.

Each holds only its own little bit of state and is positioned in screen space;
the matching painters live in :mod:`cat_society.render.atmosphere`."""

import math
import random

from .. import config


class Cloud:
    def __init__(self, rng):
        self.base = rng.uniform(0, config.W)
        self.y = rng.uniform(config.HORIZON * 0.12, config.HORIZON * 0.66)
        self.s = rng.uniform(0.7, 1.5)
        self.par = rng.uniform(0.02, 0.06)
        self.drift = rng.uniform(2.0, 5.0)

    def screen_x(self, cam, t):
        dom = config.W + 80
        x = (self.base - cam.x * self.par + self.drift * t) % dom - 40
        return x


class Bird:
    def __init__(self, rng):
        self.reset(rng, start=True)

    def reset(self, rng, start=False):
        self.x = rng.uniform(-20, config.W) if start else -20
        self.y = rng.uniform(config.HORIZON * 0.18, config.HORIZON * 0.74)
        self.spd = rng.uniform(16, 30)
        self.flap = rng.uniform(5, 9)
        self.phase = rng.uniform(0, 6.28)
        self.s = rng.uniform(0.8, 1.3)

    def update(self, dt, rng):
        self.x += self.spd * dt
        if self.x > config.W + 24:
            self.reset(rng)


class Butterfly:
    PAL = [(255, 168, 96), (172, 198, 246), (255, 196, 214),
           (250, 224, 130), (210, 178, 236)]

    def __init__(self, rng):
        self.rx = rng.uniform(60, 220)
        self.rz = rng.uniform(40, 150)
        self.zc = rng.uniform(30, 200)
        self.sp = rng.uniform(0.5, 1.1)
        self.phase = rng.uniform(0, 6.28)
        self.col = rng.choice(Butterfly.PAL)
        self.flapsp = rng.uniform(10, 16)

    def world(self, cat, t):
        x = cat.x + self.rx * math.sin(t * self.sp + self.phase) + 10 * math.sin(t * 1.7 + self.phase)
        z = cat.z + self.zc + self.rz * math.cos(t * self.sp * 0.8 + self.phase)
        return x, z
