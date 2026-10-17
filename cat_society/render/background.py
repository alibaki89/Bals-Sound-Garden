"""The baked backdrop: sky gradient, sun glow, rainbow, painterly meadow
texture, the parallax mountain layers and the soft vignette.

These are built once at startup (they do not change with the camera) and then
blitted/scrolled each frame.  The art pass here is all about *atmosphere*: a
longer, smoother sky gradient, a wide soft sun bloom, a misty skyline, layered
sun-dappled grass brushwork instead of flat colour, and rounded hazy hills."""

import math
import random

import pygame

from .. import config
from ..config import *
from ..utils import quant, lerp_color, clamp, ground_color_at
from ..palette import *


def build_sky(include_sun=True, include_rainbow=True):
    sky = pygame.Surface((config.W, config.H))

    # --- sky dome: a long, smooth, multi-stop gradient (deep zenith -> airy
    #     mid -> warm peach horizon) with extra quant steps so it stays clean
    #     and never terraces.  A faint warm glow band lifts the last few rows
    #     above the skyline so the horizon feels sunlit, not pasted on. ---
    stops = [(0.00, SKY_TOP), (0.34, SKY_HIGH), (0.66, SKY_MID),
             (0.90, SKY_HORIZON), (1.00, SKY_GLOWBAND)]
    for y in range(0, config.HORIZON):
        t = quant(y / max(1, config.HORIZON - 1), 24)
        # find the segment this t falls in
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t <= t1 or i == len(stops) - 2:
                seg = (t - t0) / max(1e-6, t1 - t0)
                col = lerp_color(c0, c1, clamp(seg, 0.0, 1.0))
                break
        pygame.draw.line(sky, col, (0, y), (config.W, y))

    # --- ground hem painted into the same surface: a soft misty band at the
    #     skyline melting down through the far->mid->near meadow greens. ---
    gh = max(1, config.H - config.HORIZON)
    hz = 0.15
    for y in range(config.HORIZON, config.H):
        t = (y - config.HORIZON) / gh
        if t < hz:
            # mist hem: warm peach skyline easing into hazy far grass
            f = t / hz
            misty = lerp_color(SKY_HORIZON, lerp_color(GROUND_FAR, HAZE, HORIZON_MIST), f)
            col = misty
        else:
            tt = quant((t - hz) / (1.0 - hz), 14)
            if tt < 0.5:
                col = lerp_color(GROUND_FAR, GROUND_MID, tt / 0.5)
            else:
                col = lerp_color(GROUND_MID, GROUND_NEAR, (tt - 0.5) / 0.5)
        pygame.draw.line(sky, col, (0, y), (config.W, y))

    if include_sun:
        _bake_sun(sky)
    if include_rainbow:
        _bake_rainbow(sky)
    _bake_ground_speckle(sky)
    _bake_meadow_brush(sky)
    return sky


def _bake_sun(sky):
    cx, cy = int(config.W * 0.80), int(config.HORIZON * 0.46)
    glow = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    # ART: a wide, very soft outer halo (many faint rings) for a premium bloom,
    # then a tighter warm glow, sized by SUN_BLOOM.  Kept low-alpha so it reads
    # as light in the air rather than a hard disc.
    outer = int(54 * SUN_BLOOM)
    for i, r in enumerate(range(outer, 10, -2)):
        f = i / max(1, (outer - 10) // 2)
        a = int(4 + 9 * f)
        col = lerp_color(SUN_HALO, SUN_GLOW, f)
        pygame.draw.circle(glow, (col[0], col[1], col[2], a), (cx, cy), r)
    sky.blit(glow, (0, 0))
    # the little sun itself: warm glow disc, bright core, hot speck
    pygame.draw.circle(sky, SUN_GLOW, (cx, cy), 8)
    pygame.draw.circle(sky, SUN_CORE, (cx, cy), 6)
    pygame.draw.circle(sky, (255, 255, 250), (cx - 2, cy - 2), 2)


def _bake_rainbow(sky):
    if RAINBOW_ALPHA <= 0:
        return
    band = pygame.Surface((config.W, config.HORIZON), pygame.SRCALPHA)
    cx, cy = int(config.W * 0.26), config.HORIZON + 30
    cols = [(255, 176, 176), (255, 202, 152), (255, 234, 158),
            (176, 226, 176), (164, 206, 246), (186, 184, 236), (208, 178, 232)]
    R = int(config.H * 0.46)
    # ART: each colour gets a soft 2px arc; the whole bow fades toward its ends
    # and is gentle enough to feel like mist, not a sticker.
    for i, c in enumerate(cols):
        for w in range(2):
            pygame.draw.circle(band, (c[0], c[1], c[2], RAINBOW_ALPHA), (cx, cy), R - i * 3 - w, 1)
    # fade the outer ends of the bow into the sky so it doesn't end abruptly
    fade = pygame.Surface((config.W, config.HORIZON), pygame.SRCALPHA)
    for x in range(config.W):
        d = abs(x - cx) / max(1, config.W * 0.62)
        a = int(clamp(d - 0.55, 0.0, 1.0) * 255)
        if a:
            pygame.draw.line(fade, (0, 0, 0, a), (x, 0), (x, config.HORIZON))
    band.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    sky.blit(band, (0, 0))


def _bake_ground_speckle(sky):
    rng = random.Random(7)
    # Gentle, sparse, low-contrast tonal dabs in the nearer ground only -- the
    # quiet base layer of the painted meadow.  Baked into the static backdrop so
    # it never moves or shimmers; tune GROUND_SPECKLE for density.
    n = int(config.W * config.H * GROUND_SPECKLE)
    for _ in range(n):
        y = rng.randint(config.HORIZON + 6, config.H - 1)
        x = rng.randint(0, config.W - 1)
        t = (y - config.HORIZON) / max(1, config.H - config.HORIZON)
        if t <= 0.40:
            continue
        base = ground_color_at(y)
        if rng.random() < 0.5:
            c = lerp_color(base, GROUND_DEEP, 0.12)
        else:
            c = lerp_color(base, (255, 255, 255), 0.05)
        wdab = rng.choice((2, 3, 3, 4))
        for dx in range(wdab):
            xx = x + dx
            if 0 <= xx < config.W:
                sky.set_at((xx, y), c)
        if rng.random() < 0.45 and y + 1 < config.H:
            xx = x + (wdab // 2)
            if 0 <= xx < config.W:
                sky.set_at((xx, y + 1), c)


def _bake_meadow_brush(sky):
    """A richer painted layer on top of the quiet speckle: short horizontal
    grass dabs (warm sunlit clumps + cool shaded clumps) and the occasional
    bright sun-dapple, all distance-weighted so the FAR meadow stays calm and
    the NEAR meadow feels lush and hand-painted.  Baked + static => zero
    shimmer; deliberately low-contrast => never fights the props."""
    if MEADOW_BRUSH <= 0:
        return
    rng = random.Random(1907)
    n = int(config.W * config.H * MEADOW_BRUSH)
    H = config.H
    HOR = config.HORIZON
    for _ in range(n):
        y = rng.randint(HOR + 4, H - 1)
        t = (y - HOR) / max(1, H - HOR)
        # density falls off toward the horizon: skip most far-field candidates
        if rng.random() > (t * t * 1.15):
            continue
        x = rng.randint(0, config.W - 1)
        base = ground_color_at(y)
        # near rows get a touch more contrast; far rows stay whisper-soft
        amt = 0.30 + 0.45 * t
        roll = rng.random()
        if roll < MEADOW_DAPPLE_CHANCE:
            c = lerp_color(base, MEADOW_DAPPLE, 0.55 * amt)        # sun-dapple
            wdab = rng.choice((3, 4, 5))
        elif roll < 0.58:
            c = lerp_color(base, GRASS_LIT, 0.55 * amt)            # sunlit clump
            wdab = rng.choice((2, 3, 4))
        else:
            c = lerp_color(base, GRASS_DEEP, 0.50 * amt)           # shaded clump
            wdab = rng.choice((2, 3, 3, 4))
        # a soft little horizontal stroke, occasionally two rows for body
        for dx in range(wdab):
            xx = x + dx
            if 0 <= xx < config.W:
                sky.set_at((xx, y), c)
        if rng.random() < 0.40 and y + 1 < H:
            lo = lerp_color(c, GROUND_DEEP, 0.18)
            for dx in range(max(1, wdab - 1)):
                xx = x + dx
                if 0 <= xx < config.W:
                    sky.set_at((xx, y + 1), lo)


# ============================================================
# Parallax mountains (baked layers, scrolled each frame)
# ============================================================
def build_mountain_layer(top, bottom, amp, ks, color, hi, snow, seed):
    surf = pygame.Surface((config.W, bottom + 2), pygame.SRCALPHA)
    rng = random.Random(seed)
    phases = [rng.uniform(0, 6.283) for _ in ks]
    weights = [1.0, 0.55, 0.30, 0.18][:len(ks)]
    mid = (top + bottom) * 0.5
    span = bottom - top
    # ART: aerial-perspective shading.  Each column fills with a soft vertical
    # gradient (cool lit ridge -> hazy foot) so ranges read as rounded volumes
    # melting into the atmosphere.  MTN_HAZE controls how far they dissolve.
    shade = lerp_color(color, MTN_SHADE, 0.42)
    foot_haze = lerp_color(color, HAZE, MTN_HAZE)
    for x in range(config.W):
        h = 0.0
        for k, ph, wgt in zip(ks, phases, weights):
            h += amp * wgt * math.sin(2 * math.pi * k * x / config.W + ph)
        peak = int(clamp(mid - h, top, bottom))
        denom = max(1, bottom - peak)
        base_y = int(bottom - span * 0.30)
        for y in range(peak, bottom):
            f = (y - peak) / denom
            col = lerp_color(color, foot_haze, f * 0.58)
            if y >= base_y:
                fb = (y - base_y) / max(1, bottom - base_y)
                col = lerp_color(col, shade, 0.30 * fb)
            surf.set_at((x, y), col)
        # sunlit ridge highlight (two-tone for a clean lit edge)
        surf.set_at((x, peak), hi)
        if peak + 1 < bottom:
            surf.set_at((x, peak + 1), lerp_color(hi, color, 0.55))
        # snow on the high peaks, with a soft blue-shaded underside so it reads
        # as a rounded cap rather than a painted line
        if snow and peak < top + span * 0.34:
            surf.set_at((x, peak), SNOW)
            if peak + 1 < bottom:
                surf.set_at((x, peak + 1), SNOW)
            if peak + 2 < bottom:
                surf.set_at((x, peak + 2), lerp_color(SNOW, SNOW_SHADE, 0.6))
            if peak + 3 < bottom:
                surf.set_at((x, peak + 3), lerp_color(SNOW_SHADE, color, 0.5))
    return surf


def build_mountains():
    far = build_mountain_layer(config.HORIZON - 26, config.HORIZON + 7, 10.0, [2, 3, 5],
                               MTN_FAR, MTN_FAR_HI, False, 11)
    near = build_mountain_layer(config.HORIZON - 18, config.HORIZON + 16, 15.0, [1, 2, 3, 6],
                                MTN_NEAR, MTN_NEAR_HI, True, 23)
    return [(far, 0.05), (near, 0.10)]


def draw_mountains(surf, layers, cam):
    for img, par in layers:
        off = int(-cam.x * par) % config.W
        surf.blit(img, (off - config.W, 0))
        surf.blit(img, (off, 0))


# ============================================================
# Soft pixel vignette (built at canvas resolution)
# ============================================================
def build_vignette():
    v = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
    cx, cy = config.W / 2, config.H * 0.54
    maxd = math.hypot(cx, cy)
    # ART: a gentle, slightly warm corner-darkening that frames the cat without
    # muddying the scene.  VIGNETTE_STRENGTH = max alpha, VIGNETTE_WARMTH tints
    # the shade from cool (0) to warm dusk (1).
    cool = (26, 22, 40)
    warm = (44, 30, 36)
    tint = lerp_color(cool, warm, clamp(VIGNETTE_WARMTH, 0.0, 1.0))
    for yy in range(0, config.H, 1):
        for xx in range(0, config.W, 1):
            d = math.hypot(xx - cx, yy - cy) / maxd
            a = int(clamp((d - 0.60) * 2.0, 0, 1) ** 2 * VIGNETTE_STRENGTH)
            if a:
                v.set_at((xx, yy), (tint[0], tint[1], tint[2], a))
    return v
