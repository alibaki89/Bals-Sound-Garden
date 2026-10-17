"""A restrained painted day/night cycle for the Sound Garden.

The original meadow is never rebuilt or recoloured.  The game's authored grass,
brushwork, water and props stay exactly as they were.  This renderer replaces
only the sky dome and adds light-touch atmosphere on top: a moving sun and moon,
stars, a quiet aurora, cloud tinting, and a cool nighttime wash that keeps the
world readable without turning the grass brown.
"""

import math
import random

import pygame

from .. import config
from ..palette import (
    SKY_TOP, SKY_HIGH, SKY_MID, SKY_HORIZON, SKY_GLOWBAND,
    CLOUD, CLOUD_HI, CLOUD_LO, CLOUD_WARM,
    SUN_HALO, SUN_GLOW, SUN_CORE,
)
from ..utils import clamp, lerp_color, quant


# ART: sky-only keyframes.  Midday uses the original palette verbatim.  Dawn
# and sunset stay pastel and painterly rather than becoming a saturated filter.
# Each row is: minute, top, high, mid, horizon, glow band,
# cloud body, cloud highlight, cloud underside, ambient, warmth.
KEYFRAMES = (
    (0,    (34, 52, 92),   (56, 72, 116),  (88, 91, 133),   (132, 111, 146), (160, 132, 158),
           (108, 116, 148), (151, 158, 184), (73, 78, 116), .82, .05),
    (270,  (42, 63, 103),  (79, 83, 128),  (151, 105, 143), (225, 151, 160), (246, 178, 168),
           (154, 137, 162), (203, 178, 190), (105, 99, 136), .86, .28),
    (330,  (70, 96, 145),  (148, 116, 164),(232, 151, 170), (255, 187, 164), (255, 207, 174),
           (211, 171, 182), (247, 205, 204), (145, 121, 153), .91, .55),
    (375,  (101, 143, 190),(188, 166, 198),(246, 184, 166), (255, 209, 169), (255, 224, 190),
           (233, 205, 202), (255, 235, 221), (169, 156, 177), .96, .70),
    (450,  SKY_TOP,         SKY_HIGH,        SKY_MID,         SKY_HORIZON,     SKY_GLOWBAND,
           CLOUD,           CLOUD_HI,        CLOUD_LO,       1.00, .22),
    (720,  SKY_TOP,         SKY_HIGH,        SKY_MID,         SKY_HORIZON,     SKY_GLOWBAND,
           CLOUD,           CLOUD_HI,        CLOUD_LO,       1.00, .12),
    (1020, (111, 169, 220),(173, 195, 226),(234, 186, 179), (255, 205, 158), (255, 220, 181),
           (239, 207, 195), (255, 235, 215), (175, 151, 168), .98, .58),
    (1080, (91, 132, 184), (181, 141, 181),(237, 137, 146), (255, 173, 119), (255, 194, 139),
           (226, 168, 172), (255, 205, 186), (147, 112, 144), .94, .82),
    (1140, (65, 88, 143),  (151, 100, 155),(224, 105, 139), (252, 146, 126), (255, 170, 145),
           (193, 131, 159), (239, 163, 180), (113, 85, 126), .89, .88),
    (1230, (46, 67, 112),  (89, 84, 132),  (151, 103, 147), (214, 139, 153), (228, 157, 164),
           (139, 119, 151), (188, 157, 178), (87, 80, 118), .84, .42),
    (1320, (35, 53, 93),   (58, 73, 117),  (89, 92, 134),   (133, 112, 147), (160, 133, 159),
           (109, 117, 149), (151, 158, 184), (73, 79, 117), .82, .08),
    (1440, (34, 52, 92),   (56, 72, 116),  (88, 91, 133),   (132, 111, 146), (160, 132, 158),
           (108, 116, 148), (151, 158, 184), (73, 78, 116), .82, .05),
)


def _phase(minutes):
    m = float(minutes) % 1440.0
    for i in range(len(KEYFRAMES) - 1):
        a, b = KEYFRAMES[i], KEYFRAMES[i + 1]
        if a[0] <= m <= b[0]:
            return i, i + 1, (m - a[0]) / max(1.0, b[0] - a[0])
    return len(KEYFRAMES) - 2, len(KEYFRAMES) - 1, 1.0


def _mix(a, b, t):
    if isinstance(a, tuple):
        return lerp_color(a, b, t)
    return a + (b - a) * t


def _smoothstep(t):
    t = clamp(float(t), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class DayNightRenderer:
    """Cached low-resolution sky and atmosphere renderer."""

    def __init__(self, width, height, seed=1):
        self.seed = int(seed)
        self.resize(width, height)

    def resize(self, width, height):
        self.w, self.h = int(width), int(height)
        self.sky_h = max(1, min(self.h, int(config.HORIZON) + 1))
        self._baked = [self._bake_sky(row, i) for i, row in enumerate(KEYFRAMES)]
        self._blend = pygame.Surface((self.w, self.sky_h), pygame.SRCALPHA)
        self._world_overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        self._world_multiply = pygame.Surface((self.w, self.h))
        self._aurora = pygame.Surface((self.w, self.sky_h), pygame.SRCALPHA)
        self._aurora_key = None
        self._glow_cache = {}

        rng = random.Random(self.seed ^ 0x57A2)
        self.stars = []
        count = max(34, int(self.w * self.sky_h * .0015))
        for _ in range(count):
            self.stars.append((
                rng.randrange(2, max(3, self.w - 2)),
                rng.randrange(2, max(3, int(self.sky_h * .82))),
                rng.choice((1, 1, 1, 1, 2)),
                rng.random() * math.tau,
                rng.uniform(.55, 1.25),
            ))

    def _bake_sky(self, row, index):
        _minute, top, high, mid, horizon, glow = row[:6]
        surf = pygame.Surface((self.w, self.sky_h))
        stops = ((0.00, top), (.33, high), (.68, mid), (.91, horizon), (1.00, glow))
        for y in range(self.sky_h):
            t = quant(y / max(1, self.sky_h - 1), 28)
            col = stops[-1][1]
            for j in range(len(stops) - 1):
                t0, c0 = stops[j]
                t1, c1 = stops[j + 1]
                if t <= t1:
                    q = clamp((t - t0) / max(1e-6, t1 - t0), 0.0, 1.0)
                    col = lerp_color(c0, c1, q)
                    break
            pygame.draw.line(surf, col, (0, y), (self.w, y))

        # Static, almost invisible horizontal brush marks make the sky belong to
        # the same painted world without introducing shimmer during cross-fades.
        rng = random.Random(self.seed + index * 1201)
        for _ in range(max(14, self.w // 18)):
            y = rng.randrange(max(1, int(self.sky_h * .18)), max(2, self.sky_h - 2))
            x = rng.randrange(self.w)
            length = rng.choice((2, 3, 4, 5, 7))
            base = surf.get_at((x, y))[:3]
            tint = lerp_color(base, (255, 255, 255), rng.uniform(.025, .055))
            pygame.draw.line(surf, tint, (x, y), (min(self.w - 1, x + length), y))
        return surf

    def palette(self, minutes):
        ia, ib, t = _phase(minutes)
        a, b = KEYFRAMES[ia], KEYFRAMES[ib]
        return {
            "sky_top": _mix(a[1], b[1], t),
            "sky_high": _mix(a[2], b[2], t),
            "sky_mid": _mix(a[3], b[3], t),
            "sky_horizon": _mix(a[4], b[4], t),
            "cloud_body": _mix(a[6], b[6], t),
            "cloud_hi": _mix(a[7], b[7], t),
            "cloud_lo": _mix(a[8], b[8], t),
            "ambient": _mix(a[9], b[9], t),
            "warmth": _mix(a[10], b[10], t),
            "night": self.night_strength(minutes),
        }

    @staticmethod
    def night_strength(minutes):
        m = float(minutes) % 1440.0
        if m >= 20.5 * 60 or m < 5.0 * 60:
            return 1.0
        if 19.0 * 60 <= m < 20.5 * 60:
            return (m - 19.0 * 60) / 90.0
        if 5.0 * 60 <= m < 6.5 * 60:
            return 1.0 - (m - 5.0 * 60) / 90.0
        return 0.0

    @staticmethod
    def daylight_strength(minutes):
        return 1.0 - DayNightRenderer.night_strength(minutes)

    def draw_sky(self, surf, minutes, day, world_time=0.0):
        """Replace only the sky dome; the original meadow remains untouched."""
        ia, ib, t = _phase(minutes)
        surf.blit(self._baked[ia], (0, 0))
        if ib != ia and t > .001:
            self._blend.fill((0, 0, 0, 0))
            self._blend.blit(self._baked[ib], (0, 0))
            self._blend.set_alpha(int(255 * t))
            surf.blit(self._blend, (0, 0))
            self._blend.set_alpha(255)

        night = self.night_strength(minutes)
        if night > .01:
            self._draw_stars(surf, night, world_time)
            if self.aurora_active(day):
                self._draw_aurora(surf, night, day, world_time)
        else:
            self._draw_day_rainbow(surf, minutes)

        # The moon has its own long dusk/dawn fade.  It rises gently instead of
        # popping into existence when the generic night overlay crosses a line.
        moon_alpha = self._moon_visibility(minutes)
        if moon_alpha > .005:
            self._draw_moon(surf, minutes, moon_alpha)

        sun_alpha = self._sun_alpha(minutes)
        if sun_alpha > .01:
            self._draw_sun(surf, minutes, sun_alpha)

    def _sun_alpha(self, minutes):
        m = float(minutes) % 1440.0
        if m < 5.35 * 60 or m > 19.55 * 60:
            return 0.0
        return clamp(min((m - 5.35 * 60) / 48.0,
                         (19.55 * 60 - m) / 48.0,
                         1.0), 0.0, 1.0)

    def _draw_sun(self, surf, minutes, alpha):
        m = float(minutes) % 1440.0
        p = clamp((m - 5.35 * 60) / (14.2 * 60), 0.0, 1.0)
        x = int(self.w * (.08 + .84 * p))
        y = int(self.sky_h * .84 - math.sin(p * math.pi) * self.sky_h * .60)
        radius = max(3, int(self.h * .019))
        size = radius * 12
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        c = glow.get_rect().center
        for rr, aa, col in (
            (radius * 5, 9, SUN_HALO),
            (radius * 4, 13, SUN_HALO),
            (radius * 3, 20, SUN_GLOW),
            (radius * 2, 35, SUN_GLOW),
        ):
            pygame.draw.circle(glow, (*col, int(aa * alpha)), c, rr)
        pygame.draw.circle(glow, (*SUN_GLOW, int(245 * alpha)), c, radius + 2)
        pygame.draw.circle(glow, (*SUN_CORE, int(255 * alpha)), c, radius)
        pygame.draw.circle(glow, (255, 255, 246, int(225 * alpha)),
                           (c[0] - max(1, radius // 3), c[1] - max(1, radius // 3)),
                           max(1, radius // 3))
        surf.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_day_rainbow(self, surf, minutes):
        m = float(minutes) % 1440.0
        # The original soft rainbow remains a daytime detail, fading out before
        # golden hour so it never competes with the sunset passages.
        fade = clamp(min((m - 7.0 * 60) / 90.0,
                         (17.0 * 60 - m) / 90.0,
                         1.0), 0.0, 1.0)
        if fade <= .01:
            return
        band = pygame.Surface((self.w, self.sky_h), pygame.SRCALPHA)
        cx, cy = int(self.w * .26), self.sky_h + 30
        cols = ((255, 176, 176), (255, 202, 152), (255, 234, 158),
                (176, 226, 176), (164, 206, 246), (186, 184, 236),
                (208, 178, 232))
        radius = int(self.h * .46)
        a = int(getattr(config, "RAINBOW_ALPHA", 46) * .78 * fade)
        for i, col in enumerate(cols):
            for w in range(2):
                pygame.draw.circle(band, (*col, a), (cx, cy), radius - i * 3 - w, 1)
        surf.blit(band, (0, 0))

    def _draw_stars(self, surf, night, world_time):
        for x, y, size, phase, speed in self.stars:
            twinkle = .66 + .34 * math.sin(world_time * speed + phase)
            a = int(168 * night * twinkle)
            col = (226, 232, 240, a)
            if size == 1:
                dot = pygame.Surface((1, 1), pygame.SRCALPHA)
                dot.set_at((0, 0), col)
                surf.blit(dot, (x, y))
            else:
                pygame.draw.line(surf, col, (x - 1, y), (x + 1, y))
                pygame.draw.line(surf, col, (x, y - 1), (x, y + 1))

    def aurora_active(self, day):
        if int(day) == 1:
            return True
        rng = random.Random(self.seed ^ (int(day) * 0x9E3779B1))
        return rng.random() < float(getattr(config, "AURORA_CHANCE", .45))

    def _draw_aurora(self, surf, night, day, world_time):
        # Refresh five times per second.  The aurora is drawn as thin painted
        # ribbons with short translucent curtains, never as a solid sky block.
        key = (int(day), int(world_time * 5))
        if key != self._aurora_key:
            self._aurora_key = key
            self._aurora.fill((0, 0, 0, 0))
            colors = ((95, 220, 170), (100, 200, 225), (190, 145, 225))
            rng = random.Random(self.seed ^ (int(day) * 1759))
            for curtain in range(3):
                phase = rng.random() * math.tau + world_time * (.065 + curtain * .014)
                centre = self.w * (.20 + curtain * .30)
                spread = self.w * (.22 + rng.random() * .045)
                base = self.sky_h * (.18 + curtain * .075)
                x0 = max(0, int(centre - spread))
                x1 = min(self.w - 1, int(centre + spread))
                points = []
                col = colors[(curtain + int(day)) % len(colors)]
                for x in range(x0, x1 + 1):
                    q = (x - centre) / max(1.0, spread)
                    edge = max(0.0, 1.0 - abs(q)) ** 1.5
                    y = int(base + math.sin(x * .060 + phase) * 2.2
                            + math.sin(x * .121 - phase * .55) * .9)
                    points.append((x, y))
                    if x % 3 == 0 and edge > .08:
                        length = int((3 + 8 * edge) * (1.0 + .12 * math.sin(x * .09 + phase)))
                        a = int(34 * edge)
                        pygame.draw.line(self._aurora, (*col, a),
                                         (x, y + 1), (x, min(self.sky_h - 1, y + length)))
                if len(points) > 1:
                    pygame.draw.lines(self._aurora, (*col, 78), False, points, 1)
                    lower = [(x, min(self.sky_h - 1, y + 2)) for x, y in points]
                    pygame.draw.lines(self._aurora, (*col, 32), False, lower, 1)
        copy = self._aurora.copy()
        copy.set_alpha(int(215 * night))
        surf.blit(copy, (0, 0))

    @staticmethod
    def _moon_visibility(minutes):
        """A soft 90-minute rise and set around the visible night arc."""
        m = float(minutes) % 1440.0
        # Work on a continuous evening-to-morning axis: 18:30 is zero.
        t = (m - 18.5 * 60.0) % 1440.0
        if t > 12.0 * 60.0:
            return 0.0
        fade_in = _smoothstep(t / 90.0)
        fade_out = _smoothstep((12.0 * 60.0 - t) / 90.0)
        return min(fade_in, fade_out)

    def _draw_moon(self, surf, minutes, alpha):
        """Draw one clean moon disc with a quiet halo and no face-like phase."""
        m = float(minutes) % 1440.0
        t = (m - 18.5 * 60.0) % 1440.0
        p = clamp(t / (12.0 * 60.0), 0.0, 1.0)
        x = int(self.w * (.07 + .86 * p))
        y = int(self.sky_h * .82 - math.sin(p * math.pi) * self.sky_h * .56)
        radius = max(3, int(self.h * .017))

        size = radius * 12
        glow = pygame.Surface((size, size), pygame.SRCALPHA)
        c = glow.get_rect().center
        pygame.draw.circle(glow, (130, 166, 214, int(14 * alpha)), c, radius * 5)
        pygame.draw.circle(glow, (174, 197, 224, int(25 * alpha)), c, radius * 3)
        pygame.draw.circle(glow, (210, 218, 226, int(34 * alpha)), c, radius * 2)
        surf.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGBA_ADD)

        moon = pygame.Surface((radius * 2 + 6, radius * 2 + 6), pygame.SRCALPHA)
        mc = moon.get_rect().center
        pygame.draw.circle(moon, (226, 224, 207, int(235 * alpha)), mc, radius + 1)
        pygame.draw.circle(moon, (247, 244, 222, int(250 * alpha)), mc, radius)
        surf.blit(moon, moon.get_rect(center=(x, y)))

    def apply_world_lighting(self, surf, minutes):
        """Let the painted world share the sky's light without recolouring it.

        Night uses a cool RGB multiply, which keeps every original brush mark
        and preserves green grass, then adds a very faint blue lift.  Sunset is
        only a translucent peach reflection.  Nothing here paints a black or
        brown rectangle over the meadow.
        """
        p = self.palette(minutes)
        night = p["night"]
        warmth = p["warmth"]
        if night <= .001 and warmth <= .35:
            return

        start = max(0, int(config.HORIZON) - 18)

        if night > .001:
            mult = self._world_multiply
            mult.fill((255, 255, 255))
            for y in range(start, self.h):
                depth = clamp((y - start) / max(1, self.h - start), 0.0, 1.0)
                # Distant meadow stays airy; nearby ground and characters read
                # as clearly moonlit.  Red is reduced a little more than green,
                # so foliage stays green-blue instead of becoming muddy brown.
                target = lerp_color((207, 224, 242), (164, 193, 222), depth)
                col = lerp_color((255, 255, 255), target, _smoothstep(night))
                pygame.draw.line(mult, col, (0, y), (self.w, y))
            surf.blit(mult, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        overlay = self._world_overlay
        overlay.fill((0, 0, 0, 0))

        # Pink/orange light catches the world during golden hour.  Alpha remains
        # deliberately low so the authored palette is still the dominant one.
        warm_amount = clamp((warmth - .38) / .62, 0.0, 1.0) * (1.0 - night)
        if warm_amount > .001:
            for y in range(start, self.h):
                depth = (y - start) / max(1, self.h - start)
                a = int((3 + 9 * depth) * warm_amount)
                pygame.draw.line(overlay, (255, 175, 133, a), (0, y), (self.w, y))

        if night > .001:
            # A tiny moon-blue lift stops the multiply pass from feeling flat and
            # makes pale fur, stones and water catch the night sky naturally.
            for y in range(start, self.h):
                depth = (y - start) / max(1, self.h - start)
                a = int((3 + 8 * (1.0 - depth)) * night)
                pygame.draw.line(overlay, (76, 119, 171, a), (0, y), (self.w, y))

        surf.blit(overlay, (0, 0))

    def draw_music_lights(self, surf, sources, minutes):
        """Paint warm pools around sprouts and gramophones after dusk."""
        night = self.night_strength(minutes)
        if night <= .03:
            return
        fade = _smoothstep((night - .03) / .97)
        for sx, sy, radius, color, strength in sources:
            r = max(4, int(radius))
            rgb = tuple(int(c) for c in color[:3])
            alpha = int(126 * fade * clamp(strength, .2, 1.4))
            key = (r, rgb, alpha // 10)
            glow = self._glow_cache.get(key)
            if glow is None:
                glow = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                centre = (r, r)
                # A broad, flattened pool belongs to the ground; the smaller
                # circles make the actual musical object shine.
                for frac, a in ((1.0, .045), (.78, .075), (.55, .12)):
                    rect = pygame.Rect(0, 0, max(2, int(r * 2 * frac)),
                                       max(2, int(r * .70 * frac)))
                    rect.center = (r, int(r * 1.17))
                    pygame.draw.ellipse(glow, (*rgb, int(alpha * a)), rect)
                for frac, a in ((.72, .08), (.48, .17), (.25, .42), (.11, .78)):
                    pygame.draw.circle(glow, (*rgb, int(alpha * a)), centre,
                                       max(1, int(r * frac)))
                self._glow_cache[key] = glow
                if len(self._glow_cache) > 180:
                    self._glow_cache.pop(next(iter(self._glow_cache)))
            surf.blit(glow, glow.get_rect(center=(int(sx), int(sy))),
                      special_flags=pygame.BLEND_RGBA_ADD)

