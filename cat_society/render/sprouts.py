"""Painters for planted sound sprouts.

Each component *type* has its own silhouette, so a planted garden reads like
a score at a glance:

* drum      -> a squat seed-drum on a reed (small, ticky)
* rhythm    -> a cluster of three seed-drums
* note      -> a bell-flower on a stem, blossom tinted by the component colour
* chord     -> a three-headed pad-fern
* bass      -> a deep round gourd, low to the soil
* loop      -> a curling vine with beads
* ambience  -> a tall mist-lily

All of them share the world's language: soft ellipses, one up-left highlight,
warm outline, ground contact shade, `_haze(fade)` into the distance.  The soil
ring (the trigger area) is a faint tilled circle -- information drawn as
gardening, not as UI.  When a sprout rings it *blooms*: a quick lift, a
brighter blossom, and one note glyph that floats off.
"""

import math

import pygame

from .. import config
from ..utils import ri, clamp, lerp_color, ground_color_at
from ..palette import GROUND_DEEP, HAZE

STEM = (96, 150, 92)
STEM_D = (74, 124, 76)
SOIL = (150, 124, 96)
SOIL_D = (124, 100, 78)
GLYPH = (255, 240, 190)


def _haze(fade):
    def col(c):
        return lerp_color(c, HAZE, fade * 0.85)
    return col


def ring_radius_px(radius_world, scale):
    return max(6, ri(radius_world * scale * config.SC * 0.42))


def _soil_ring(surf, sx, sy, rw, scale, fade, strength=1.0):
    """The tilled circle that marks a sprout's trigger soil."""
    r = ring_radius_px(rw, scale)
    col = _haze(fade)
    base = lerp_color(ground_color_at(sy), SOIL, 0.30 * strength)
    dark = lerp_color(ground_color_at(sy), SOIL_D, 0.34 * strength)
    rect = (sx - r, sy - ri(r * 0.42), r * 2, max(3, ri(r * 0.84)))
    pygame.draw.ellipse(surf, col(dark), rect, 1)
    if scale * config.SC >= 0.7:
        pygame.draw.ellipse(surf, col(lerp_color(dark, base, 0.5)),
                            (rect[0] + 1, rect[1] + 1,
                             rect[2] - 2, max(2, rect[3] - 2)), 1)
    # four little tilled nicks around the ring, like a hoed bed
    for k in range(4):
        ang = k * (math.tau / 4) + 0.55
        nx = sx + ri(math.cos(ang) * r * 0.98)
        ny = sy + ri(math.sin(ang) * r * 0.41)
        surf.set_at((clamp(nx, 0, config.W - 1), clamp(ny, 0, config.H - 1)),
                    col(base))


def _contact(surf, sx, sy, w, fade):
    pygame.draw.ellipse(
        surf, lerp_color(ground_color_at(sy), GROUND_DEEP, 0.4 * (1.0 - fade)),
        (sx - w, sy - max(1, w // 3), w * 2, max(2, ri(w * 0.7))))


def _blossom(surf, x, y, s, col_fn, color, lift, glow):
    """A proper pixel blossom in the component's own colour: four petals,
    four shoulder petals when close, and a warm heart."""
    bright = lerp_color(color, (255, 255, 255), 0.25 + 0.45 * glow)
    deep = lerp_color(color, (70, 56, 66), 0.25)
    heart = lerp_color(color, (255, 244, 200), 0.65)
    y = y - ri(lift)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        surf.set_at((clamp(x + dx, 0, config.W - 1),
                     clamp(y + dy, 0, config.H - 1)), col_fn(bright))
    if s >= 0.75:
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            surf.set_at((clamp(x + dx, 0, config.W - 1),
                         clamp(y + dy, 0, config.H - 1)), col_fn(deep))
        for dx, dy in ((-2, 0), (2, 0), (0, -2)):
            surf.set_at((clamp(x + dx, 0, config.W - 1),
                         clamp(y + dy, 0, config.H - 1)), col_fn(bright))
    surf.set_at((clamp(x, 0, config.W - 1), clamp(y, 0, config.H - 1)),
                col_fn(heart))


def _note_float(surf, x, y, s, pulse, col_fn):
    """The glyph that floats up right after a ring (pulse = seconds since)."""
    if pulse > 0.9:
        return
    k = pulse / 0.9
    py = y - ri((6 + k * 14) * s)
    px = x + ri(math.sin(k * 6.0) * 1.5 * s)
    c = col_fn(GLYPH)
    surf.set_at((clamp(px, 0, config.W - 1), clamp(py, 0, config.H - 1)), c)
    surf.set_at((clamp(px, 0, config.W - 1), clamp(py - 1, 0, config.H - 1)), c)
    surf.set_at((clamp(px + 1, 0, config.W - 1), clamp(py + 1, 0, config.H - 1)), c)


def draw_sprout(surf, sx, sy, scale, fade, t, comp, pulse, sway, beat_phase,
                resting=False, planning=False):
    from ..world.sprouts import RADII      # local import avoids a cycle
    s = scale * config.SC * 1.45           # sprouts are proud garden objects
    col = _haze(fade)
    sx, sy = ri(sx), ri(sy)
    kind = comp.get("type", "note")
    color = tuple(comp.get("color", (170, 214, 150)))
    if resting and pulse > 0.6:          # cooling down: petals fold a shade
        color = lerp_color(color, (150, 150, 140), 0.35)
    glow = max(0.0, 1.0 - pulse * 1.6)          # bright right after ringing
    lift = glow * 2.0 * s                        # the happy hop when it rings
    if not resting and beat_phase < 0.12:
        lift += 0.7 * s                          # armed sprouts nod on the beat
    wob = math.sin(t * 1.4 + sway) * 0.7 * s

    ring_str = 0.75 + 0.5 * glow
    if planning:
        ring_str = 1.6                           # holding a seed: rings speak up
    _soil_ring(surf, sx, sy, RADII.get(kind, 90.0), scale, fade,
               strength=ring_str)
    if pulse < 0.35 and s >= 0.5:
        # the ring itself blooms outward for a breath when the sprout sings
        rr = ring_radius_px(RADII.get(kind, 90.0), scale)
        k = pulse / 0.35
        fr = ri(rr * (0.45 + 0.6 * k))
        flash = lerp_color(tuple(comp.get("color", GLYPH)), GLYPH, 0.5)
        pygame.draw.ellipse(surf, col(flash),
                            (sx - fr, sy - ri(fr * 0.42), fr * 2,
                             max(2, ri(fr * 0.84))), 1)
    if s < 0.35:
        surf.set_at((clamp(sx, 0, config.W - 1), clamp(sy - 2, 0, config.H - 1)),
                    col(color))
        return
    _contact(surf, sx, sy, max(2, ri(3.5 * s)), fade)

    if kind in ("drum", "rhythm"):
        heads = 1 if kind == "drum" else 3
        for i in range(heads):
            hx = sx + ri((i - (heads - 1) / 2) * 5.5 * s + (wob if i == 1 else 0))
            hh = ri((6 + (i % 2)) * s) + ri(lift)
            pygame.draw.line(surf, col(STEM), (hx, sy), (hx, sy - hh), 1)
            rw = max(2, ri(3.2 * s))
            body = (hx - rw, sy - hh - ri(2.6 * s), rw * 2, max(2, ri(3.4 * s)))
            pygame.draw.ellipse(surf, col(lerp_color(color, (60, 44, 40), 0.25)),
                                body)
            pygame.draw.ellipse(surf, col(lerp_color(color, (255, 250, 230),
                                                     0.35 + 0.4 * glow)),
                                (body[0], body[1], body[2], max(1, body[3] // 2)))
    elif kind == "bass":
        rw = max(3, ri(5.5 * s))
        pygame.draw.ellipse(surf, col(lerp_color(color, (40, 36, 52), 0.3)),
                            (sx - rw, sy - ri(6 * s) - ri(lift), rw * 2,
                             max(3, ri(6.5 * s))))
        pygame.draw.ellipse(surf, col(lerp_color(color, (255, 255, 255), 0.2)),
                            (sx - ri(rw * 0.6), sy - ri(5.6 * s) - ri(lift),
                             max(2, ri(rw * 0.7)), max(1, ri(2 * s))))
        pygame.draw.line(surf, col(STEM_D), (sx, sy - ri(6 * s)), (sx, sy), 1)
    elif kind == "chord":
        for i, dx in enumerate((-4.0, 0.0, 4.0)):
            hx = sx + ri(dx * s + wob * (0.4 if i != 1 else 1.0))
            hh = ri((8 + (1 - abs(i - 1)) * 3) * s) + ri(lift)
            pygame.draw.line(surf, col(STEM), (sx, sy), (hx, sy - hh), 1)
            _blossom(surf, hx, sy - hh, s, col, color, 0, glow)
    elif kind == "loop":
        # a curling vine: three beads along a soft arc
        top = sy - ri(11 * s) - ri(lift)
        pygame.draw.line(surf, col(STEM), (sx, sy), (sx + ri(wob), top), 1)
        for i in range(3):
            ang = t * 0.8 + i * 2.1 + sway
            bx = sx + ri(math.cos(ang) * (3 + i) * s * 0.8 + wob)
            by = top + ri(i * 3 * s)
            _blossom(surf, bx, by, s, col, color, 0, glow * (1.0 - i * 0.2))
    elif kind == "ambience":
        hh = ri(14 * s) + ri(lift)
        pygame.draw.line(surf, col(STEM), (sx, sy), (sx + ri(wob), sy - hh), 1)
        # a tall lily cup
        cw = max(2, ri(3 * s))
        pygame.draw.ellipse(surf, col(lerp_color(color, (255, 255, 255), 0.3)),
                            (sx + ri(wob) - cw, sy - hh - ri(3.5 * s),
                             cw * 2, max(2, ri(4 * s))))
        # slow breath rings while resting, mist while glowing
        if glow > 0.05 and s >= 0.6:
            for k in range(2):
                mx = sx + ri(math.sin(t * 1.1 + k * 2.4) * 4 * s)
                my = sy - hh - ri((5 + k * 3) * s)
                surf.set_at((clamp(mx, 0, config.W - 1),
                             clamp(my, 0, config.H - 1)), col((236, 246, 250)))
    else:   # note: the classic bell-flower
        hh = ri(9 * s) + ri(lift)
        pygame.draw.line(surf, col(STEM), (sx, sy), (sx + ri(wob), sy - hh), 1)
        leaf = (sx + ri(2 * s), sy - ri(4 * s))
        pygame.draw.ellipse(surf, col(STEM_D),
                            (leaf[0], leaf[1], max(2, ri(3 * s)), max(1, ri(1.6 * s))))
        _blossom(surf, sx + ri(wob), sy - hh, s, col, color, 0, glow)

    _note_float(surf, sx, sy - ri(10 * s), s, pulse, col)
    # a faint beat shimmer on the soil ring exactly on the garden clock
    if beat_phase < 0.12 and s >= 0.6:
        from ..world.sprouts import RADII as _R
        r = ring_radius_px(_R.get(kind, 90.0), scale)
        px = sx + ri(math.cos(sway * 2.3) * r)
        py = sy + ri(math.sin(sway * 2.3) * r * 0.42)
        surf.set_at((clamp(px, 0, config.W - 1), clamp(py, 0, config.H - 1)),
                    col(GLYPH))


def draw_plant_preview(surf, sx, sy, scale, comp, ok):
    """The planting preview at Bal's feet: soil ring + a translucent blossom."""
    from ..world.sprouts import RADII
    s = scale * config.SC * 1.45
    sx, sy = ri(sx), ri(sy)
    kind = comp.get("type", "note")
    r = ring_radius_px(RADII.get(kind, 90.0), scale)
    color = (170, 214, 150) if ok else (216, 150, 130)
    preview = pygame.Surface((r * 2 + 4, max(6, ri(r * 0.84)) + 4), pygame.SRCALPHA)
    pygame.draw.ellipse(preview, (*color, 110),
                        (2, 2, r * 2, max(3, ri(r * 0.84))), 1)
    surf.blit(preview, (sx - r - 2, sy - ri(r * 0.42) - 2))
    dot = pygame.Surface((6, 6), pygame.SRCALPHA)
    pygame.draw.circle(dot, (*color, 170), (3, 3), 2)
    surf.blit(dot, (sx - 3, sy - ri(6 * s) - 3))
