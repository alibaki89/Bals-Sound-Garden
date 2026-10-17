"""Story cards: the garden's soft-spoken storyteller.

A story card is a centred paper panel with a title and a few short lines --
used for the opening moment, for meeting a sleeping landmark, for the
awakening itself, and for the little milestone when the whole garden hums
again.  While one is showing the world gently pauses (like the journal), so
the player can read at their own pace.  Any key or click turns the page.

Same warm paper, same ink, same rounded panels as everything else -- no new
visual language, just the existing one speaking a little longer.
"""

import math

import pygame

from .. import ui
from ..ui.icons import draw_icon


class StoryCard:
    __slots__ = ("title", "lines", "icon", "color", "footer")

    def __init__(self, title, lines, icon=None, color=None, footer=None):
        self.title = title
        self.lines = list(lines)
        self.icon = icon
        self.color = color or ui.GRASS
        self.footer = footer or "press any key"


class StoryCards:
    """A queue of story cards.  ``blocking`` is True while one is on screen."""

    def __init__(self):
        self._queue = []
        self._current = None
        self._t = 0.0
        self._min_hold = 0.55        # ignore keys for a beat so nothing skips

    def queue(self, title, lines, icon=None, color=None, footer=None):
        self._queue.append(StoryCard(title, lines, icon, color, footer))

    def clear(self):
        """Dismiss the current card and any queued pages."""
        self._queue = []
        self._current = None
        self._t = 0.0

    @property
    def blocking(self):
        return self._current is not None or bool(self._queue)

    def update(self, dt):
        if self._current is None and self._queue:
            self._current = self._queue.pop(0)
            self._t = 0.0
        if self._current is not None:
            self._t += dt

    def handle_event(self, e):
        """Returns True if the event was consumed by the card."""
        if self._current is None:
            return False
        if self._t < self._min_hold:
            return True
        if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self._current = None
            return True
        return False

    def draw(self, surf):
        if self._current is None:
            return
        card = self._current
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)

        # a soft dusk veil so the card floats over a calmer world
        fade = min(1.0, self._t / 0.35)
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((30, 26, 22, int(150 * fade)))
        surf.blit(veil, (0, 0))

        body_h = ui.pixel_line_height(S(18))
        pad = S(30)
        gap = S(10)
        line_h = body_h + gap
        panel_w = min(int(w * 0.86), S(760))
        wrapped = []
        wrap_w = panel_w - pad * 2
        for ln in card.lines:
            wrapped.extend(ui.wrap_lines(ln, wrap_w, S(18)))
        pw = panel_w
        icon_h = S(56) if card.icon else 0
        ph = pad * 2 + S(44) + icon_h + line_h * max(1, len(wrapped)) + S(30)
        panel = pygame.Rect(0, 0, pw, ph)
        panel.center = (w // 2, int(h * 0.46) + int((1 - fade) * S(24)))

        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=18)
        y = panel.y + pad
        if card.icon:
            bob = math.sin(self._t * 2.2) * S(3)
            draw_icon(surf, panel.centerx, y + S(24) + bob, S(22),
                      card.color, card.icon, self._t)
            y += icon_h
        ui.pixel_text(surf, card.title.upper(), S(25), panel.centerx, y,
                      color=ui.INK, center=True)
        y += S(44)
        for ln in wrapped:
            ui.pixel_text(surf, ln, S(18), panel.centerx, y,
                          color=ui.INK_SOFT, center=True)
            y += line_h
        if self._t >= self._min_hold:
            a = 0.55 + 0.45 * math.sin(self._t * 2.6)
            ui.pixel_text(surf, card.footer.upper(), S(13), panel.centerx,
                          panel.bottom - S(30),
                          color=tuple(int(c * a + 247 * (1 - a)) for c in ui.INK_SOFT),
                          center=True)
