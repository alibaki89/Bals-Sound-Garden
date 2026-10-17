"""Your Music: browse, play, edit, export and delete saved songs."""

import os
import time

import pygame

from .. import ui
from ..ui.widgets import Button
from ..audio import sfx
from ..music import store
from . import exporting


class YourMusicScreen:
    def __init__(self, app):
        self.app = app
        self.scroll = 0
        self.projects = []
        self._row_buttons = []          # rebuilt each draw for hit-testing
        self.confirm_delete = None      # project id awaiting a confirm click
        self.confirm_t = 0.0
        self.export_confirm = None       # (proj, target, name) awaiting overwrite confirm
        self.message = ""
        self.message_t = 0.0
        self._playing_id = None
        self.back_btn = None
        self.new_btn = None
        self.export_task = None        # responsive background WAV render

    def on_enter(self):
        self._reload()
        pygame.mouse.set_visible(True)
        w, h = self.app.window.get_size()
        S = lambda v: ui.scaled(h, v)
        self.back_btn = Button(pygame.Rect(S(20), S(18), S(110), S(44)), "Menu",
                               self._leave, size=S(20))
        self.new_btn = Button(pygame.Rect(w - S(210), S(18), S(190), S(44)),
                              "New Song", self._new, size=S(20), accent=ui.GRASS)
        warning = self.app.pop_project_warning()
        if warning:
            self._flash(warning)

    def _reload(self):
        self.projects = list(self.app.refresh_projects())

    def _leave(self):
        self.app.engine.stop_music()
        self._playing_id = None
        self.app.goto("menu")

    def _new(self):
        self.app.engine.stop_music()
        self._playing_id = None
        self.app.pending_project = None
        self.app.goto("maker")

    # -- events -------------------------------------------------------------
    def handle_event(self, e):
        if self.export_confirm is not None:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.export_confirm = None
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                cancel_r, replace_r = self._export_confirm_rects()
                if replace_r.collidepoint(e.pos):
                    proj, target, _ = self.export_confirm
                    self.export_confirm = None
                    self._do_export(proj, target)
                elif cancel_r.collidepoint(e.pos) or not self._export_panel().collidepoint(e.pos):
                    self.export_confirm = None
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self._leave()
            return
        if e.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - e.y * 60)
        self.back_btn.handle_event(e)
        self.new_btn.handle_event(e)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, action, pid in self._row_buttons:
                if rect.collidepoint(e.pos):
                    self._do(action, pid)
                    return

    def _do(self, action, pid):
        if action == "play":
            proj = store.load(pid)
            if proj is not None:
                self.app.engine.play_project(proj, samples=exporting.sample_buffers(self.app), loop=False)
                self._playing_id = pid
        elif action == "stop":
            self.app.engine.stop_music()
            self._playing_id = None
        elif action == "edit":
            proj = store.load(pid)
            if proj is not None:
                self.app.engine.stop_music()
                self._playing_id = None
                self.app.pending_project = proj
                self.app.goto("maker")
        elif action == "export":
            self._start_export(pid)
        elif action == "delete":
            if self.confirm_delete == pid:
                if self._playing_id == pid:
                    self.app.engine.stop_music()
                    self._playing_id = None
                store.delete(pid)
                self.confirm_delete = None
                self._reload()
                self._flash("Deleted")
            else:
                self.confirm_delete = pid
                self.confirm_t = 2.6

    # -- export (identical flow to the Music Maker) -------------------------
    def _start_export(self, pid):
        if self.export_task is not None and not self.export_task.status()["finished"]:
            self._flash("A WAV export is already rendering")
            return
        proj = store.load(pid)
        if proj is None:
            return
        default = exporting.safe_filename(proj.name)
        res = exporting.ask_save_path(default)
        if res:                                  # chosen path (native dialog)
            self._do_export(proj, res)
        elif res == "":                          # cancelled -> no export
            self._flash("Export cancelled")
        else:                                    # no GUI -> internal folder
            target = exporting.fallback_target(default)
            if os.path.exists(target):
                self.export_confirm = (proj, target, default)
            else:
                self._do_export(proj, target)

    def _do_export(self, proj, path):
        if self.export_task is not None and not self.export_task.status()["finished"]:
            self._flash("A WAV export is already rendering")
            return
        try:
            self.export_task = exporting.start_export(
                proj, path, samples=exporting.sample_buffers(self.app))
            self._flash("Rendering WAV...")
        except Exception as exc:
            self.export_task = None
            self._flash("Export failed: %s" % exporting.friendly_error(exc))

    def _poll_export(self):
        if self.export_task is None:
            return
        status = self.export_task.status()
        if not status["finished"]:
            done, total = status["done"], status["total"]
            self.message = ("Rendering WAV... %d/%d" % (done, total)
                            if total else "Rendering WAV...")
            self.message_t = 1.0
            return
        self.export_task = None
        if status["error"] is not None:
            self._flash("Export failed: %s" % exporting.friendly_error(status["error"]))
        else:
            self._flash("Exported  ->  %s" % exporting.short_path(status["result"]))

    def _flash(self, msg):
        self.message = msg
        self.message_t = 3.0

    # -- update -------------------------------------------------------------
    def update(self, dt):
        self._poll_export()
        if self.message_t > 0:
            self.message_t -= dt
        if self.confirm_t > 0:
            self.confirm_t -= dt
            if self.confirm_t <= 0:
                self.confirm_delete = None
        if self._playing_id and not self.app.engine.is_playing():
            self._playing_id = None

    # -- draw ---------------------------------------------------------------
    def draw(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        ui.vertical_gradient(surf, surf.get_rect(), ui.SKY, ui.PAPER)
        ui.text(surf, "Your Music", S(40), w // 2, S(22), color=ui.INK, center=True)
        self.back_btn.draw(surf, pygame.mouse.get_pos())
        self.new_btn.draw(surf, pygame.mouse.get_pos())

        list_area = pygame.Rect(S(40), S(80), w - S(80), h - S(110))
        self._row_buttons = []

        if not self.projects:
            ui.text(surf, "No songs yet.", S(26), w // 2, h // 2 - S(40),
                    color=ui.INK, center=True)
            ui.text(surf, "Open the Music Maker, arrange some sounds, and save.",
                    S(20), w // 2, h // 2 + S(4), color=ui.INK_SOFT, center=True)
            return

        prev = surf.get_clip()
        surf.set_clip(list_area)
        card_h = S(118)
        gap = S(16)
        y = list_area.y - self.scroll
        for proj in self.projects:
            rect = pygame.Rect(list_area.x, y, list_area.w, card_h)
            if rect.bottom >= list_area.y and rect.y <= list_area.bottom:
                self._draw_card(surf, rect, proj, S)
            y += card_h + gap
        surf.set_clip(prev)

        total = len(self.projects) * (card_h + gap)
        self._max_scroll = max(0, total - list_area.h)
        self.scroll = min(self.scroll, self._max_scroll)

        if self.message_t > 0:
            a = min(1.0, self.message_t / 0.6)
            f = ui.font(S(20), True)
            img = f.render(ui.safe_text(self.message), False, ui.INK)
            box = pygame.Surface((img.get_width() + S(30), img.get_height() + S(16)),
                                 pygame.SRCALPHA)
            box.fill((*ui.SUN, int(240 * a)))
            box.blit(img, (S(15), S(8)))
            box.set_alpha(int(255 * a))
            surf.blit(box, box.get_rect(center=(w // 2, h - S(40))))

        if self.export_confirm is not None:
            self._draw_export_confirm(surf, S)

    # -- export overwrite confirm (fallback, no-GUI case) -------------------
    def _export_panel(self):
        w, h = self.app.window.get_size()
        S = lambda v: ui.scaled(h, v)
        pw, ph = S(560), S(210)
        return pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)

    def _export_confirm_rects(self):
        S = lambda v: ui.scaled(self.app.window.get_size()[1], v)
        panel = self._export_panel()
        cancel = pygame.Rect(panel.centerx - S(166), panel.bottom - S(64), S(150), S(46))
        replace = pygame.Rect(panel.centerx + S(16), panel.bottom - S(64), S(150), S(46))
        return cancel, replace

    def _draw_export_confirm(self, surf, S):
        veil = pygame.Surface((surf.get_width(), surf.get_height()), pygame.SRCALPHA)
        veil.fill((20, 24, 22, 150))
        surf.blit(veil, (0, 0))
        panel = self._export_panel()
        name = self.export_confirm[2]
        ui.draw_panel(surf, panel, fill=ui.CREAM, radius=16, shadow=True)
        ui.text(surf, "File already exists", S(24), panel.centerx, panel.y + S(26),
                color=ui.INK, center=True)
        ui.text(surf, "A file named \"%s\" is already in the exports folder." % name,
                S(18), panel.centerx, panel.y + S(74), color=ui.INK_SOFT, center=True)
        ui.text(surf, "Replace it?", S(18), panel.centerx, panel.y + S(100),
                color=ui.INK_SOFT, center=True)
        cancel, replace = self._export_confirm_rects()
        mp = pygame.mouse.get_pos()
        ui.draw_panel(surf, cancel, fill=_light(ui.PAPER_DK) if cancel.collidepoint(mp)
                      else ui.PAPER_DK, radius=S(10), shadow=False)
        ui.text_center_box(surf, "Cancel", S(18), cancel, color=ui.INK)
        rc = (206, 110, 100)
        ui.draw_panel(surf, replace, fill=_light(rc) if replace.collidepoint(mp) else rc,
                      radius=S(10), shadow=False)
        ui.text_center_box(surf, "Replace", S(18), replace, color=ui.CREAM)

    def _draw_card(self, surf, rect, proj, S):
        playing = proj.id == self._playing_id
        ui.draw_panel(surf, rect, fill=(248, 243, 230) if not playing else (255, 250, 232),
                      edge=(ui.GRASS_DK if playing else ui.PAPER_EDGE), radius=12)
        ui.text(surf, proj.name, S(26), rect.x + S(20), rect.y + S(12), color=ui.INK)
        # meta line
        when = time.strftime("%b %d, %Y  %H:%M", time.localtime(proj.modified))
        dur = proj.duration_seconds()
        meta = "%s    .    %d BPM    .    %d bars    .    %s    .    %d components" % (
            when, proj.tempo, proj.bars, _dur(dur), len(proj.components_used()))
        ui.text(surf, meta, S(16), rect.x + S(20), rect.y + S(48), color=ui.INK_SOFT)

        # action buttons
        bw = S(120)
        bh = S(40)
        bx = rect.right - S(16) - bw
        by = rect.bottom - bh - S(12)
        specs = [("Delete", "delete", (228, 170, 160)),
                 ("Export", "export", ui.SUN),
                 ("Edit", "edit", None),
                 ("Play" if not playing else "Stop", "play" if not playing else "stop", ui.GRASS)]
        mp = pygame.mouse.get_pos()
        for label, action, accent in specs:
            r = pygame.Rect(bx, by, bw, bh)
            lab = label
            acc = accent
            if action == "delete" and self.confirm_delete == proj.id:
                lab = "Sure?"
                acc = (224, 130, 120)
            self._row_buttons.append((r, action, proj.id))
            hover = r.collidepoint(mp)
            fill = acc or (ui.BTN_HOVER if hover else ui.BTN)
            if hover and acc:
                fill = _light(acc)
            ui.draw_panel(surf, r, fill=fill, radius=8, shadow=False)
            ui.text_center_box(surf, lab, S(18), r, color=ui.INK)
            bx -= bw + S(10)


def _dur(sec):
    m = int(sec // 60)
    s = int(sec % 60)
    return "%d:%02d" % (m, s)


def _light(c):
    return tuple(min(255, int(v + 25)) for v in c)
