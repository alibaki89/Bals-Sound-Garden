"""Small pure helpers: clamping, interpolation, rounding, seeding.

These have no game state of their own; they are imported all over the place,
so keep them dependency-light (only :mod:`config` and :mod:`palette`)."""

from . import config
from .palette import GROUND_FAR, GROUND_MID, GROUND_NEAR


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t),
            int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def ri(v):
    return int(v + 0.5) if v >= 0 else -int(-v + 0.5)


def quant(t, steps):
    return round(t * steps) / steps


def smooth01(t):
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return t * t * (3.0 - 2.0 * t)


def seed_hash(*ints):
    """A stable 31-bit number built from config.WORLD_SEED + whatever ints we pass.

    Same inputs always give the same result inside one run, so chunks never
    flicker, but a different config.WORLD_SEED reshuffles the whole world."""
    h = (config.WORLD_SEED & 0x7FFFFFFF) ^ 0x9E3779B1
    for v in ints:
        h = (h * 0x01000193) ^ (int(v) & 0xFFFFFFFF)
        h &= 0xFFFFFFFF
    h ^= h >> 15
    return h & 0x7FFFFFFF


def _h01(*ints):
    """seed_hash as a 0..1 float."""
    return seed_hash(*ints) / 2147483647.0


def ground_color_at(sy):
    # World-object contact colours should come from the playable meadow plane,
    # not from the peach sky/mountain transition above it.
    t = clamp((sy - config.MEADOW_HORIZON) / max(1, (config.H - config.MEADOW_HORIZON)), 0.0, 1.0)
    if t < 0.5:
        return lerp_color(GROUND_FAR, GROUND_MID, t / 0.5)
    return lerp_color(GROUND_MID, GROUND_NEAR, (t - 0.5) / 0.5)
