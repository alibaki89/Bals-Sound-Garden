"""The ripples, wake, splash ring and droplets the cat stirs up in the water.

Lifted verbatim out of the main draw loop into one function so the loop stays
readable; called once per frame from :meth:`cat_society.game.Game.draw_scene`."""

import math

import pygame

from .. import config
from ..utils import ri, lerp_color
from ..projection import project
from ..palette import FW_SHALLOW, FOAM


def draw_cat_water_fx(surf, cat, cam, t):
    """Draw the ripples / wake / splash the cat makes while in water."""
    if (cat.boat is None and cat.on_ground
            and (cat.in_water or cat.splash_t > 0.0)):
        _pr = project(cat.x, cat.z, cam)
        if _pr is not None:
            _rx, _ry, _rs = _pr
            _rx = config.W * 0.5      # keep ripples centred under the pinned cat
            _k = _rs * config.SC
            _sub = cat.swim                       # 0..1 submersion
            if cat.in_water:
                # soft concentric ripples that breathe and grow with depth
                _base = 5.0 + 6.0 * _sub
                _n = 2 + (1 if _sub > 0.5 else 0)
                for _i in range(_n):
                    _grow = 0.5 + 0.5 * math.sin(t * 2.2 + _i * 1.5)
                    _rr = ri((_base + _i * 5.0 + _grow * 3.0) * _k)
                    if _rr > 1:
                        _col = lerp_color(FW_SHALLOW, FOAM, 0.55 - _i * 0.16)
                        pygame.draw.ellipse(surf, _col,
                                            (ri(_rx - _rr), ri(_ry - _rr * 0.42),
                                             _rr * 2, max(1, ri(_rr * 0.84))), 1)
                # a little paddle wake in front while actually moving
                if cat.moving:
                    _wob = math.sin(t * 9.0) * 2.0 * _k
                    _fx = ri(_rx + cat.facing * 8.0 * _k)
                    pygame.draw.ellipse(surf, lerp_color(FW_SHALLOW, FOAM, 0.5),
                                        (ri(_fx - 3.0 * _k), ri(_ry - 1 + _wob * 0.2),
                                         max(2, ri(6.0 * _k)), max(1, ri(3.0 * _k))), 1)
            # a soft fading splash ring + a few gentle droplets on entry
            if cat.splash_t > 0.0:
                _p = cat.splash_t / 0.5            # 1 -> 0
                _a = int(200 * _p)
                _sr = ri((9.0 + (1.0 - _p) * 24.0) * _k)
                if _sr > 1 and _a > 6:
                    _spl = pygame.Surface((_sr * 2 + 4, ri(_sr * 0.9) + 4), pygame.SRCALPHA)
                    pygame.draw.ellipse(_spl, (236, 248, 250, _a),
                                        (2, 2, _sr * 2, max(1, ri(_sr * 0.8))), max(1, ri(1.4 * _k)))
                    surf.blit(_spl, (ri(_rx - _sr - 2), ri(_ry - _sr * 0.4 - 2)))
                for _d in range(4):
                    _ang = _d * 1.5708 + cat.x * 0.01
                    _dist = (1.0 - _p) * 15.0 * _k
                    _dx = ri(_rx + math.cos(_ang) * _dist)
                    _dy = ri(_ry - abs(math.sin(_ang)) * _dist * 0.7 - _p * 6.0 * _k)
                    if 0 <= _dx < config.W and 0 <= _dy < config.H:
                        surf.set_at((_dx, _dy), FOAM)

