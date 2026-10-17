"""Small reusable widgets: a chunky cozy Button and a horizontal Slider.

These are deliberately tiny and self-contained.  A screen creates them, calls
``draw`` each frame and feeds mouse events to ``handle_event``; the widget
reports clicks/changes through a callback or a polled value.
"""

import pygame

from . import (font, draw_panel, BTN, BTN_HOVER, BTN_DOWN, BTN_EDGE, INK,
               INK_SOFT, GRASS, GRASS_DK, PAPER_EDGE, CREAM, pixel_text_fit_box,
               safe_text)


class Button:
    def __init__(self, rect, label, on_click=None, size=22, accent=None,
                 enabled=True, lift=False):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.on_click = on_click
        self.size = size
        self.accent = accent          # optional fill colour when idle
        self.enabled = enabled
        self.lift = lift              # gentle grow + glow on hover (menu buttons)
        self._down = False

    def handle_event(self, e):
        if not self.enabled:
            return False
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.rect.collidepoint(e.pos):
                self._down = True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            was = self._down
            self._down = False
            if was and self.rect.collidepoint(e.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surf, mouse_pos):
        hover = self.enabled and self.rect.collidepoint(mouse_pos)
        if not self.enabled:
            fill, edge, txt = (236, 230, 218), PAPER_EDGE, (170, 158, 142)
        elif self._down and hover:
            fill, edge, txt = BTN_DOWN, BTN_EDGE, INK
        elif hover:
            fill, edge, txt = (self.accent or BTN_HOVER), BTN_EDGE, INK
        else:
            fill, edge, txt = (self.accent or BTN), BTN_EDGE, INK
        rect = self.rect
        if self.lift and hover and not self._down:
            grow = max(2, self.rect.h // 18)
            rect = self.rect.inflate(grow * 2, grow * 2)
            glow = pygame.Surface((rect.w + 28, rect.h + 28), pygame.SRCALPHA)
            pygame.draw.rect(glow, (*GRASS, 70), glow.get_rect(), border_radius=18)
            surf.blit(glow, (rect.x - 14, rect.y - 10))
        draw_panel(surf, rect, fill=fill, edge=edge, radius=12,
                   shadow=self.enabled, sheen=True)
        pixel_text_fit_box(surf, self.label, self.size, rect.inflate(-10, -6),
                           color=txt, bold=True, min_size=max(10, self.size - 6))


class IconButton(Button):
    """A square button that draws a tiny glyph instead of (or beside) text."""
    def __init__(self, rect, glyph, on_click=None, size=22, accent=None):
        super().__init__(rect, glyph, on_click, size, accent)


class Slider:
    def __init__(self, rect, lo, hi, value, on_change=None, label="",
                 fmt=lambda v: str(int(v))):
        self.rect = pygame.Rect(rect)
        self.lo = lo
        self.hi = hi
        self.value = value
        self.on_change = on_change
        self.label = label
        self.fmt = fmt
        self._drag = False

    def _val_from_x(self, x):
        t = (x - self.rect.x) / max(1, self.rect.w)
        t = max(0.0, min(1.0, t))
        return self.lo + (self.hi - self.lo) * t

    def handle_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.rect.inflate(0, 18).collidepoint(e.pos):
                self._drag = True
                self.value = self._val_from_x(e.pos[0])
                if self.on_change:
                    self.on_change(self.value)
                return True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if self._drag:
                self._drag = False
                return True
        elif e.type == pygame.MOUSEMOTION and self._drag:
            self.value = self._val_from_x(e.pos[0])
            if self.on_change:
                self.on_change(self.value)
            return True
        return False

    def draw(self, surf, mouse_pos):
        r = self.rect
        # track
        track = pygame.Rect(r.x, r.centery - 3, r.w, 6)
        pygame.draw.rect(surf, (220, 210, 190), track, border_radius=3)
        pygame.draw.rect(surf, PAPER_EDGE, track, width=1, border_radius=3)
        # filled portion
        t = (self.value - self.lo) / max(1e-6, (self.hi - self.lo))
        fillw = int(r.w * t)
        if fillw > 0:
            pygame.draw.rect(surf, GRASS, pygame.Rect(r.x, r.centery - 3, fillw, 6),
                             border_radius=3)
        # knob
        kx = r.x + fillw
        pygame.draw.circle(surf, CREAM, (kx, r.centery), 9)
        pygame.draw.circle(surf, GRASS_DK, (kx, r.centery), 9, 2)
        # label
        if self.label:
            f = font(max(12, r.h - 2), True)
            img = f.render(safe_text("%s %s" % (self.label, self.fmt(self.value))), False, INK)
            surf.blit(img, (r.x, r.y - img.get_height() - 4))
