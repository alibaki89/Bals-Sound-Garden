"""Main-menu Soundbook overlay.

The collection remains persistent game state, but browsing it no longer adds a
permanent key or overlay to Explore.  The menu owns this calm, scrollable view.
"""

import pygame

from .. import ui
from ..components import catalog
from ..components import rarity as _rarity
from ..ui.icons import draw_icon


class SoundbookOverlay:
    def __init__(self, app):
        self.app = app
        self.scroll = 0
        self.max_scroll = 0
        self.play_rects = []

    def reset(self):
        self.scroll = 0
        self.max_scroll = 0
        self.play_rects = []

    def handle_event(self, e, close):
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            close()
            return True
        if e.type == pygame.MOUSEWHEEL:
            step = max(-3, min(3, e.y)) * 48
            self.scroll = max(0, min(self.scroll - step, self.max_scroll))
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, cid in self.play_rects:
                if rect.collidepoint(e.pos):
                    comp = catalog.get(cid)
                    if comp is not None:
                        self.app.engine.preview_component(comp)
                    return True
        return False

    def draw(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        self.play_rects = []

        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((24, 22, 20, 190))
        surf.blit(veil, (0, 0))

        panel = pygame.Rect(int(w * 0.055), int(h * 0.055),
                            int(w * 0.89), int(h * 0.89))
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(16))
        col = self.app.collection

        ui.pixel_text(surf, "SOUNDBOOK", S(31), panel.x + S(28), panel.y + S(18),
                      color=ui.INK)
        summary = "%d collected   -   %d / %d curated" % (
            col.num_found(), col.num_curated_found(), col.total())
        sr = pygame.Rect(panel.x + S(250), panel.y + S(20), panel.w - S(278), S(24))
        ui.pixel_text_fit_box(surf, summary, S(15), sr, color=ui.INK_SOFT,
                              min_size=S(11))
        ui.pixel_text(surf, "ESC  BACK", S(13), panel.right - S(28),
                      panel.y + S(53), color=ui.INK_SOFT, right=True)

        grid = pygame.Rect(panel.x + S(24), panel.y + S(82),
                           panel.w - S(48), panel.h - S(104))
        self.scroll = max(0, min(self.scroll, self.max_scroll))
        previous_clip = surf.get_clip()
        surf.set_clip(grid)

        cell_w = S(268)
        cell_h = S(66)
        cols = max(1, grid.w // max(1, cell_w))
        cell_w = grid.w // cols
        y = grid.y - self.scroll
        total = 0

        def header(title, subtitle, color):
            nonlocal y, total
            if grid.y - cell_h <= y <= grid.bottom:
                ui.pixel_text(surf, title.upper(), S(19), grid.x, y + S(4), color=color)
                if subtitle:
                    ui.pixel_text(surf, subtitle, S(13), grid.right, y + S(7),
                                  color=ui.INK_SOFT, right=True)
            y += S(38)
            total += S(38)

        def cells(comps):
            nonlocal y, total
            for i, comp in enumerate(comps):
                ci = i % cols
                if ci == 0 and i > 0:
                    y += cell_h
                    total += cell_h
                cx = grid.x + ci * cell_w
                if grid.y - cell_h <= y <= grid.bottom:
                    self._draw_cell(surf, cx, y, cell_w - S(10),
                                    cell_h - S(8), comp, h)
            if comps:
                y += cell_h + S(14)
                total += cell_h + S(14)

        families = {}
        for comp in catalog.ALL:
            if col.owns(comp["id"]):
                families[comp["type"]] = families.get(comp["type"], 0) + 1
        family_line = "   -   ".join("%s %d" % (name, count)
                                     for name, count in sorted(families.items()))
        header("Collected sounds", family_line, ui.PLUM)

        for key, region in catalog.REGIONS.items():
            comps = catalog.by_region(key)
            if not comps:
                continue
            owned = [comp for comp in comps if col.owns(comp["id"])]
            header(region["name"], "%d / %d discovered" % (len(owned), len(comps)),
                   ui.GRASS_DK)
            cells(owned)
            hidden = len(comps) - len(owned)
            if hidden:
                if grid.y - S(30) <= y <= grid.bottom:
                    ui.pixel_text(surf, "%d sounds still hidden here" % hidden,
                                  S(13), grid.x + S(10), y,
                                  color=ui.INK_SOFT)
                y += S(30)
                total += S(30)

        generated = col._found_proc()
        generated.sort(key=lambda comp: -col.discovery_order(comp["id"]))
        header("Endless discoveries", "%d generated sounds found" % len(generated),
               ui.PLUM)
        if generated:
            cells(generated)
        else:
            if grid.y - cell_h <= y <= grid.bottom:
                ui.pixel_text(surf, "Wander farther to discover generated sounds.",
                              S(14), grid.x, y, color=ui.INK_SOFT)
            y += S(30)
            total += S(30)

        surf.set_clip(previous_clip)
        self.max_scroll = max(0, total - grid.h)
        self.scroll = min(self.scroll, self.max_scroll)

        if self.max_scroll > 0:
            rail = pygame.Rect(panel.right - S(12), grid.y, S(4), grid.h)
            pygame.draw.rect(surf, ui.PAPER_EDGE, rail, border_radius=S(2))
            frac = grid.h / max(grid.h, total)
            thumb_h = max(S(32), int(grid.h * frac))
            travel = max(1, grid.h - thumb_h)
            yoff = int(travel * self.scroll / max(1, self.max_scroll))
            thumb = pygame.Rect(rail.x, rail.y + yoff, rail.w, thumb_h)
            pygame.draw.rect(surf, ui.GRASS_DK, thumb, border_radius=S(2))

    def _draw_cell(self, surf, x, y, cw, ch, comp, h):
        S = lambda v: ui.scaled(h, v)
        rect = pygame.Rect(x, y, cw, ch)
        ui.draw_panel(surf, rect, fill=ui.PAPER_DK, radius=S(8), shadow=False)
        ccol = tuple(comp.get("color", ui.GRASS))
        draw_icon(surf, x + ch // 2, y + ch // 2, ch * 0.32, ccol,
                  comp.get("icon", "note"), 0.0)
        tx = x + ch
        name_y = y + ch // 2 - S(17)
        nr = pygame.Rect(tx, name_y, cw - ch - S(48), S(20))
        ui.pixel_text_fit_box(surf, comp["name"], S(15), nr, color=ui.INK,
                              min_size=S(11), center=False)
        rar = comp.get("rarity", "common")
        info = "%s  -  %s  -  ~%.0f%%" % (
            comp.get("type", "").title(), comp.get("track", ""),
            _rarity.percent(rar))
        ir = pygame.Rect(tx, name_y + S(22), cw - ch - S(48), S(16))
        ui.pixel_text_fit_box(surf, info, S(11), ir, color=_rarity.color(rar),
                              min_size=S(9), bold=False, center=False)

        pr = pygame.Rect(x + cw - S(34), y + (ch - S(28)) // 2, S(28), S(28))
        ui.draw_panel(surf, pr, fill=ui.GRASS, radius=S(14), shadow=False)
        cx, cy = pr.center
        pygame.draw.polygon(surf, ui.CREAM,
                            [(cx - S(4), cy - S(6)),
                             (cx - S(4), cy + S(6)),
                             (cx + S(6), cy)])
        self.play_rects.append((pr, comp["id"]))
