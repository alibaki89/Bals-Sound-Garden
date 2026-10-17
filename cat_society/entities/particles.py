"""Drifting flower petals - the gentle foreground 'snow' of the meadow.

Painted by :func:`cat_society.render.atmosphere.draw_petal`."""

import random

from .. import config


class Petal:
    PAL = [(255, 196, 214), (255, 224, 200), (255, 240, 232), (250, 210, 224)]

    def __init__(self, rng):
        self.x = rng.uniform(0, config.W)
        self.y = rng.uniform(-config.H, config.H)
        self.fall = rng.uniform(8, 18)
        self.swsp = rng.uniform(1.0, 2.4)
        self.swa = rng.uniform(4, 10)
        self.phase = rng.uniform(0, 6.28)
        self.col = rng.choice(Petal.PAL)
        self.size = rng.choice([1, 1, 2])

    def update(self, dt):
        self.y += self.fall * dt
        if self.y > config.H + 3:
            self.y = -3
            self.x = random.uniform(0, config.W)
