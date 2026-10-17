"""The "found component" discovery card.

When the cat collects a component, a card slides in from the side, holds briefly,
then fades. It is drawn at full window resolution (over the already-upscaled
world) so the component name and description stay crisp and readable, while the
world keeps its pixel look. A newly found sound replaces the current card
immediately, so rapid discoveries never create a delayed notification backlog.
"""

import math

import pygame

from .. import ui
from ..ui.icons import draw_icon
from ..music.project import FAMILIES

_SLIDE_IN = 0.32
_HOLD = 2.4
_SLIDE_OUT = 0.5
_TOTAL = _SLIDE_IN + _HOLD + _SLIDE_OUT

_TRACK_LABEL = {k: n for n, k in FAMILIES}
_TYPE_LABEL = {
    "note": "Note", "chord": "Chord", "drum": "Drum Hit", "rhythm": "Rhythm",
    "loop": "Loop", "ambience": "Ambience", "effect": "Effect", "user": "User Sound",
}


class CardManager:
    def __init__(self):
        self._queue = []
        self._current = None
        self._found = None
        self._total = None
        self._t = 0.0
        self._sparks = []

    def queue(self, comp, found=None, total=None):
        replacing = self._current is not None
        self._queue.clear()              # retained only for old test/save introspection
        self._current = comp
        self._found = found
        self._total = total
        # The first card keeps its gentle entrance.  A later discovery swaps in
        # at the settled position immediately and receives a fresh hold period.
        self._t = _SLIDE_IN if replacing else 0.0
        self._sparks = self._make_sparks()

    def busy(self):
        return self._current is not None

    def update(self, dt):
        if self._current is None:
            return
        self._t += dt
        for s in self._sparks:
            s[0] += s[2] * dt
            s[1] += s[3] * dt
            s[3] += 40 * dt
        if self._t >= _TOTAL:
            self._current = None
            self._t = 0.0

    def _make_sparks(self):
        rng = __import__("random").Random()
        rarity = self._current.get("rarity", "common")
        n = {"common": 0, "uncommon": 4, "rare": 9, "secret": 16}.get(rarity, 0)
        out = []
        for _ in range(n):
            a = rng.uniform(0, math.tau)
            sp = rng.uniform(20, 70)
            out.append([rng.uniform(-10, 10), rng.uniform(-10, 10),
                        math.cos(a) * sp, math.sin(a) * sp - 30])
        return out

    def draw(self, surf):
        if self._current is None:
            return
        comp = self._current
        w, h = surf.get_size()

        # animation: ease in, hold, fade out
        if self._t < _SLIDE_IN:
            p = self._t / _SLIDE_IN
            off = (1 - _ease(p))
            alpha = p
            pop = 1.0 + 0.5 * (1 - p)            # icon pops then settles
        elif self._t < _SLIDE_IN + _HOLD:
            off = 0.0
            alpha = 1.0
            pop = 1.0
        else:
            p = (self._t - _SLIDE_IN - _HOLD) / _SLIDE_OUT
            off = _ease(p) * 0.6
            alpha = 1.0 - p
            pop = 1.0

        cw = ui.scaled(h, 470)
        ch = ui.scaled(h, 226)
        margin = ui.scaled(h, 36)
        x = w - cw - margin + int(off * (cw + margin))
        y = margin

        card = pygame.Surface((cw + 24, ch + 24), pygame.SRCALPHA)
        rarity = comp.get("rarity", "common")
        glow_col = ui.RARITY_COL.get(rarity, ui.GRASS)
        # rarity glow behind the card (stronger + pulsing for secret/rare)
        boost = {"common": 0, "uncommon": 1, "rare": 2, "secret": 3}.get(rarity, 0)
        pulse = 0.5 + 0.5 * math.sin(self._t * 5.0)
        ga = 70 + boost * 22 + (int(40 * pulse) if boost >= 2 else 0)
        pygame.draw.rect(card, (*glow_col, min(190, ga)), card.get_rect(), border_radius=20)
        if boost >= 3:                          # secret: extra shimmer ring
            pygame.draw.rect(card, (*ui.CREAM, int(120 * pulse)), card.get_rect(),
                             width=3, border_radius=20)
        ui.draw_panel(card, pygame.Rect(12, 12, cw, ch), fill=ui.CREAM,
                      edge=glow_col, radius=14)

        pad = ui.scaled(h, 22)
        # header
        ui.pixel_text(card, "FOUND COMPONENT", ui.scaled(h, 16), 12 + pad, 12 + pad,
                      color=ui.INK_SOFT)
        # collected count under the header
        if self._found is not None:
            cnt = ("%d / %d collected" % (self._found, self._total)
                   if self._total else "%d collected" % self._found)
            ui.pixel_text(card, cnt.upper(), ui.scaled(h, 13), 12 + pad,
                          12 + pad + ui.scaled(h, 22), color=ui.INK_SOFT)

        # icon disc (top-right) with a pop scale + sparkles
        icon_r = ui.scaled(h, 32)
        icx = 12 + cw - pad - icon_r
        icy = 12 + pad + icon_r - ui.scaled(h, 2)
        pygame.draw.circle(card, (*glow_col, 110), (icx, icy), icon_r + 7)
        for s in self._sparks:
            sa = max(0, int(220 * (1 - self._t / (_SLIDE_IN + _HOLD))))
            pygame.draw.circle(card, (255, 250, 232, sa),
                               (int(icx + s[0]), int(icy + s[1])), max(1, ui.scaled(h, 3)))
        draw_icon(card, icx, icy, int(icon_r * pop), tuple(comp.get("color", ui.GRASS)),
                  comp.get("icon", "note"), self._t * 3)

        # name
        ny = 12 + pad + ui.scaled(h, 30)
        nrect = pygame.Rect(12 + pad, ny, cw - pad * 2 - ui.scaled(h, 90), ui.scaled(h, 28))
        ui.pixel_text_fit_box(card, comp["name"].upper(), ui.scaled(h, 24),
                              nrect, color=ui.INK, min_size=ui.scaled(h, 16), center=False)

        # type . rarity pill
        line_y = ny + ui.scaled(h, 38)
        type_lab = _TYPE_LABEL.get(comp.get("type"), comp.get("type", "").title())
        rarity_lab = rarity.title()
        ui.pixel_text(card, type_lab.upper(), ui.scaled(h, 17), 12 + pad, line_y, color=ui.INK)
        rx = 12 + pad + ui.pixel_measure(type_lab.upper() + "   ", ui.scaled(h, 17))[0]
        pill = ui.pixel_measure(rarity_lab.upper(), ui.scaled(h, 15))[0] + ui.scaled(h, 16)
        prect = pygame.Rect(rx, line_y - 2, pill, ui.scaled(h, 24))
        pygame.draw.rect(card, glow_col, prect, border_radius=8)
        ui.pixel_text_center_box(card, rarity_lab.upper(), ui.scaled(h, 15), prect, color=ui.INK)

        # use in maker
        use_y = line_y + ui.scaled(h, 32)
        track = _TRACK_LABEL.get(comp.get("track"), comp.get("track", "").title())
        if comp.get("type") == "effect":
            use_txt = "Use:  Track effect slot"
        else:
            use_txt = "Use:  %s track" % track
        ui.pixel_text(card, use_txt.upper(), ui.scaled(h, 15), 12 + pad, use_y,
                      color=ui.INK_SOFT)

        # description (wrapped)
        desc = comp.get("desc", "")
        dy = use_y + ui.scaled(h, 26)
        _wrap(card, desc, ui.scaled(h, 17), 12 + pad, dy, cw - pad * 2, ui.INK_SOFT)

        # "Added to Music Maker" confirmation pill along the bottom
        add_txt = "+  Added to Music Maker"
        aw = ui.pixel_measure(add_txt.upper(), ui.scaled(h, 14))[0] + ui.scaled(h, 20)
        arect = pygame.Rect(12 + pad, 12 + ch - ui.scaled(h, 34),
                            aw, ui.scaled(h, 24))
        pygame.draw.rect(card, ui.GRASS, arect, border_radius=8)
        ui.pixel_text_center_box(card, add_txt.upper(), ui.scaled(h, 14), arect,
                                 color=ui.CREAM)

        card.set_alpha(int(255 * max(0.0, min(1.0, alpha))))
        surf.blit(card, (x - 12, y - 12))


def _ease(p):
    return 1 - (1 - p) * (1 - p)


def _wrap(surf, s, size, x, y, maxw, color):
    words = s.split()
    line = ""
    lh = ui.pixel_render("Ag", size, color).get_height() + 2
    for word in words:
        test = (line + " " + word).strip()
        if ui.pixel_measure(test, size)[0] > maxw and line:
            ui.pixel_text(surf, line, size, x, y, color=color)
            y += lh
            line = word
        else:
            line = test
    if line:
        ui.pixel_text(surf, line, size, x, y, color=color)
