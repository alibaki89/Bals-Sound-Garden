"""Main menu: the gameplay recording loops behind Story and Creative entries.

The six compact destinations preserve the original clean presentation while
making the boat-arrival story a first-class way to begin."""

import os
import glob

import pygame

from .. import ui
from .. import settings
from ..audio import sfx
from .soundbook import SoundbookOverlay


_ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "menu")
_FPS = 12.0


class MenuScreen:
    def __init__(self, app):
        self.app = app
        self.t = 0.0
        self._frames = sorted(glob.glob(os.path.join(_ASSET_DIR, "frame_*.jpg")))
        self._cur_idx = -1
        self._cur_surf = None
        self._cur_size = None
        self.dialog = None             # settings | reset | soundbook | new_story | no_story
        self.soundbook = SoundbookOverlay(app)
        self._hover_key = None
        self._drag = None              # which settings slider is being dragged
        self._about_scroll = 0
        self._build()

    def on_enter(self):
        # A dialog belongs to the visit that opened it.  Clearing it here
        # prevents an overwrite/reset prompt from reappearing after returning
        # from Story, Explore, or the Maker.
        self.dialog = None
        self._drag = None
        self._about_scroll = 0
        self._build()

    def _build(self):
        w, h = self.app.window.get_size()
        self.w, self.h = w, h
        S = lambda v: ui.scaled(h, v)
        self.S = S
        bw = S(340)
        bh = S(52)
        gap = S(10)
        cx = w // 2
        labels = [("New Game", self._new_story),
                  ("Continue Story", self._continue_story),
                  ("Explore", lambda: self.app.goto("explore")),
                  ("Music Maker", lambda: self.app.goto("maker")),
                  ("Your Music", lambda: self.app.goto("your_music")),
                  ("Soundbook", self._open_soundbook)]
        total = len(labels) * bh + (len(labels) - 1) * gap
        top = max(S(250), int(h * 0.91) - total)
        self._buttons = []
        for i, (lab, cb) in enumerate(labels):
            rect = pygame.Rect(cx - bw // 2, top + i * (bh + gap), bw, bh)
            self._buttons.append((rect, lab, cb))
        # subtle Reset Progress link below the destination stack
        self._reset_rect = pygame.Rect(cx - S(110), top + total + S(8), S(220), S(30))
        # small info + sound buttons, tucked in the top-right
        self._sound_rect = pygame.Rect(w - S(132), S(18), S(112), S(38))
        self._info_rect = pygame.Rect(self._sound_rect.x - S(48), S(18), S(38), S(38))

    # -- recording background (decode current frame on demand, cover-fill) ---
    def _bg_frame(self, w, h):
        if not self._frames:
            return None
        idx = int(self.t * _FPS) % len(self._frames)
        if idx != self._cur_idx or self._cur_size != (w, h):
            try:
                img = pygame.image.load(self._frames[idx]).convert()
                iw, ih = img.get_size()
                scale = max(w / iw, h / ih)        # cover: fill, never letterbox
                sw, sh = round(iw * scale), round(ih * scale)
                img = pygame.transform.smoothscale(img, (sw, sh))
                self._cur_surf = (img, ((w - sw) // 2, (h - sh) // 2))
            except Exception:
                self._cur_surf = None
            self._cur_idx = idx
            self._cur_size = (w, h)
        return self._cur_surf

    # -- events -------------------------------------------------------------
    def handle_event(self, e):
        if self.dialog == "settings":
            self._settings_event(e)
            return
        if self.dialog == "reset":
            self._reset_event(e)
            return
        if self.dialog == "soundbook":
            self.soundbook.handle_event(e, self._close_dialog)
            return
        if self.dialog == "about":
            self._about_event(e)
            return
        if self.dialog in ("new_story", "no_story"):
            self._story_dialog_event(e)
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_1:
                self._new_story()
            elif e.key == pygame.K_2:
                self._continue_story()
            elif e.key == pygame.K_3:
                self._go("explore")
            elif e.key == pygame.K_4:
                self._go("maker")
            elif e.key == pygame.K_5:
                self._go("your_music")
            elif e.key == pygame.K_6:
                self._open_soundbook()
            elif e.key == pygame.K_ESCAPE:
                self.app.quit()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self._info_rect.collidepoint(e.pos):
                self.dialog = "about"
                self._about_scroll = 0
                return
            if self._sound_rect.collidepoint(e.pos):
                self.dialog = "settings"
                return
            if self._reset_rect.collidepoint(e.pos):
                self.dialog = "reset"
                return
            for rect, _lab, cb in self._buttons:
                if rect.collidepoint(e.pos):
                    cb()
                    return

    def _new_story(self):
        if self.app.story_exists():
            self.dialog = "new_story"
        else:
            self.dialog = None
            self.app.start_story(new=True)

    def _continue_story(self):
        if self.app.story_exists():
            self.dialog = None
            self.app.start_story(new=False)
        else:
            self.dialog = "no_story"

    def _story_dialog_rects(self):
        S = self.S
        panel = pygame.Rect(0, 0, S(520), S(250))
        panel.center = (self.w // 2, self.h // 2)
        left = pygame.Rect(panel.x + S(38), panel.bottom - S(68), S(190), S(44))
        right = pygame.Rect(panel.right - S(228), panel.bottom - S(68), S(190), S(44))
        return panel, left, right

    def _story_dialog_event(self, e):
        panel, left, right = self._story_dialog_rects()
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.dialog = None
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.dialog == "no_story":
                    self.dialog = None
                else:
                    self.dialog = None
                    self.app.start_story(new=True)
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if self.dialog == "no_story":
                if panel.collidepoint(e.pos):
                    self.dialog = None
                else:
                    self.dialog = None
                return
            if right.collidepoint(e.pos):
                self.dialog = None
                self.app.start_story(new=True)
            elif left.collidepoint(e.pos) or not panel.collidepoint(e.pos):
                self.dialog = None

    def _go(self, name):
        self.app.goto(name)

    def _open_soundbook(self):
        self.soundbook.reset()
        self.dialog = "soundbook"

    def _close_dialog(self):
        self.dialog = None

    # -- settings dialog ----------------------------------------------------
    def _settings_rows(self):
        """Return a spacious sound layout that stays inside the panel."""
        S = self.S
        w, h = self.w, self.h
        pw, ph = S(620), S(430)
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        rows = []
        for i, (key, label) in enumerate((("master", "Overall volume"),
                                          ("music", "Music"),
                                          ("sfx", "Sound effects"))):
            row_y = panel.y + S(118) + i * S(74)
            bar = pygame.Rect(panel.x + S(205), row_y + S(8),
                              panel.w - S(325), S(18))
            rows.append((key, label, bar))
        return panel, rows

    def _settings_buttons(self, panel):
        S = self.S
        mute = pygame.Rect(panel.x + S(38), panel.bottom - S(76), S(180), S(46))
        done = pygame.Rect(panel.right - S(158), panel.bottom - S(76), S(120), S(46))
        return mute, done

    def _settings_event(self, e):
        S = self.S
        panel, rows = self._settings_rows()
        mute_r, done_r = self._settings_buttons(panel)
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.dialog = None
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if mute_r.collidepoint(e.pos):
                settings.toggle_mute()
                self.app.engine.refresh_volume()
                sfx.refresh_ambience()
                sfx.refresh_water()
                return
            if done_r.collidepoint(e.pos) or not panel.collidepoint(e.pos):
                self.dialog = None
                return
            for key, _lab, bar in rows:
                if bar.inflate(0, S(18)).collidepoint(e.pos):
                    self._drag = key
                    self._apply_slider(key, bar, e.pos[0])
                    return
        elif e.type == pygame.MOUSEBUTTONUP:
            self._drag = None
        elif e.type == pygame.MOUSEMOTION and self._drag:
            for key, _lab, bar in rows:
                if key == self._drag:
                    self._apply_slider(key, bar, e.pos[0])

    def _apply_slider(self, key, bar, mx):
        val = (mx - bar.x) / max(1, bar.w)
        settings.set_value(key, max(0.0, min(1.0, val)))
        self.app.engine.refresh_volume()
        sfx.refresh_ambience()
        sfx.refresh_water()

    # -- reset dialog -------------------------------------------------------
    def _reset_buttons(self):
        S = self.S
        w, h = self.w, self.h
        pw, ph = S(700), S(390)
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        cancel = pygame.Rect(panel.x + S(52), panel.bottom - S(82), S(210), S(50))
        reset = pygame.Rect(panel.right - S(262), panel.bottom - S(82), S(210), S(50))
        return panel, cancel, reset

    def _reset_event(self, e):
        panel, cancel, reset = self._reset_buttons()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            self.dialog = None
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if reset.collidepoint(e.pos):
                self.app.reset_progress()
                self.dialog = None
                return
            if cancel.collidepoint(e.pos) or not panel.collidepoint(e.pos):
                self.dialog = None
                return

    # -- about / help dialog -----------------------------------------------
    def _about_rects(self):
        S = self.S
        w, h = self.w, self.h
        pw, ph = min(w - S(46), S(720)), min(h - S(46), S(660))
        panel = pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)
        viewport = pygame.Rect(panel.x + S(34), panel.y + S(88), panel.w - S(68), panel.h - S(154))
        done = pygame.Rect(panel.centerx - S(80), panel.bottom - S(50), S(160), S(38))
        return panel, viewport, done

    def _about_copy(self):
        return [
            ("Bal's Sound Garden is a cozy music game about wandering, listening, and making songs.", False),
            ("You play as Bal. He arrives on the island, opens a music shop, and slowly turns the place into a warm little home for animals and music.", False),
            ("There are two main ways to play.", True),
            ("Story mode is the shop adventure. Animals visit with requests, days pass, the merchant comes by, and money lets you grow the shop.", False),
            ("Explore is the relaxed sandbox mode. You can roam around, collect sounds, plant sprouts, and play songs in the world without worrying about commissions.", False),
            ("Collecting sounds", True),
            ("Floating sounds can be collected in the world. Open the seed tray to choose one, then plant it to create a music sprout in the garden.", False),
            ("Sprouts can be listened to in the world. Saved songs can also be placed with gramophones so Bal can perform them outdoors.", False),
            ("Composing music", True),
            ("Open the Music Maker to build songs from the sounds you have discovered. In Story mode, the clock keeps moving while you compose, so waiting clients and deadlines still matter.", False),
            ("You decide whether to accept a recorded offer or leave it alone. Helpers can record requests for you, but they do not compose your music.", False),
            ("The shop", True),
            ("Animals may ask for a song, a sprout, or a field delivery. Some will wait at the counter. Some will come back later. Some will return on another day.", False),
            ("Poko's travelling cart sells sounds, decorations, upgrades, and helper contracts. Coins finally have a purpose: they help Bal grow the shop.", False),
            ("Helpers", True),
            ("A scout can search for sounds. An assistant can record requests while you are busy. A courier can handle ordinary deliveries once you prepare them.", False),
            ("Journal", True),
            ("The Journal stores useful information about active offers, accepted missions, finished jobs, helpers, and shop items. Open it from the pause menu.", False),
            ("Useful keys", True),
            ("WASD or arrow keys move. Shift runs. Space jumps. E interacts. F opens the seed tray. P plays a saved song. M opens the Music Maker. Escape opens the pause menu.", False),
            ("After 18:00, pressing Z asks whether Bal should sleep for the night. Sleeping moves time forward to the next morning.", False),
        ]

    def _about_content_height(self, viewport_w):
        S = self.S
        total = S(14)
        for line, heading in self._about_copy():
            if heading:
                total += S(26)
            else:
                wrapped = ui.wrap_lines(line, viewport_w - S(32), S(16), pixel=True, bold=False)
                total += len(wrapped) * (ui.pixel_line_height(S(16), False) + S(2)) + S(10)
        total += S(10)
        return total

    def _about_event(self, e):
        panel, viewport, done = self._about_rects()
        max_scroll = max(0, self._about_content_height(viewport.w) - viewport.h)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.dialog = None
                return
            if e.key in (pygame.K_RETURN, pygame.K_SPACE) and done.collidepoint(done.center):
                self.dialog = None
                return
            if e.key in (pygame.K_DOWN, pygame.K_s):
                self._about_scroll = min(max_scroll, self._about_scroll + self.S(28))
                return
            if e.key in (pygame.K_UP, pygame.K_w):
                self._about_scroll = max(0, self._about_scroll - self.S(28))
                return
            if e.key == pygame.K_PAGEDOWN:
                self._about_scroll = min(max_scroll, self._about_scroll + viewport.h // 2)
                return
            if e.key == pygame.K_PAGEUP:
                self._about_scroll = max(0, self._about_scroll - viewport.h // 2)
                return
        if e.type == pygame.MOUSEWHEEL:
            self._about_scroll = max(0, min(max_scroll, self._about_scroll - e.y * self.S(24)))
            return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            if done.collidepoint(e.pos) or not panel.collidepoint(e.pos):
                self.dialog = None
                return

    def update(self, dt):
        self.t += dt

    # -- polished translucent button ---------------------------------------
    def _draw_button(self, surf, rect, label, hover, S):
        lift = S(3) if hover else 0
        r = rect.move(0, -lift)
        shadow = pygame.Surface((r.w + S(12), r.h + S(12)), pygame.SRCALPHA)
        pygame.draw.rect(shadow, (18, 22, 20, 90), shadow.get_rect(),
                         border_radius=S(16))
        surf.blit(shadow, (r.x - S(6), r.y - S(2) + lift))
        face = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        base = (252, 248, 238, 235) if hover else (248, 244, 234, 210)
        pygame.draw.rect(face, base, face.get_rect(), border_radius=S(14))
        pygame.draw.rect(face, (255, 255, 255, 200), face.get_rect(), width=max(1, S(2)),
                         border_radius=S(14))
        pygame.draw.rect(face, (*ui.GRASS, 120),
                         (S(10), r.h - S(7), r.w - S(20), S(3)), border_radius=S(2))
        surf.blit(face, r.topleft)
        ui.text_center_box(surf, label, S(22), r, color=ui.INK)

    def _draw_chip(self, surf, rect, label, hover, S, size=18):
        face = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        a = 215 if hover else 150
        pygame.draw.rect(face, (245, 242, 234, a), face.get_rect(), border_radius=S(10))
        pygame.draw.rect(face, (255, 255, 255, 140), face.get_rect(), width=1,
                         border_radius=S(10))
        surf.blit(face, rect.topleft)
        ui.text_center_box(surf, label, S(size), rect, color=ui.INK)

    def draw(self, surf):
        w, h = self.w, self.h
        S = lambda v: ui.scaled(h, v)
        self.S = S
        frame = self._bg_frame(w, h)
        if frame is not None:
            surf.blit(frame[0], frame[1])
        else:
            ui.vertical_gradient(surf, surf.get_rect(), (150, 200, 170), (210, 230, 200))

        # gentle scrims top + bottom for legibility
        th = int(h * 0.26)
        top_scrim = pygame.Surface((w, th), pygame.SRCALPHA)
        for i in range(th):
            top_scrim.fill((20, 26, 22, int(120 * (1 - i / th))), (0, i, w, 1))
        surf.blit(top_scrim, (0, 0))
        bh2 = int(h * 0.34)
        bot_scrim = pygame.Surface((w, bh2), pygame.SRCALPHA)
        for i in range(bh2):
            bot_scrim.fill((20, 26, 22, int(150 * (i / bh2))), (0, i, w, 1))
        surf.blit(bot_scrim, (0, h - bh2))

        # title
        title = "Bal's Sound Garden"
        ts = S(74)
        f = ui.font(ts, True)
        tw = f.size(title)[0]
        ty = int(h * 0.15)
        pill = pygame.Rect(0, 0, tw + S(96), ts + S(40))
        pill.center = (w // 2, ty)
        glass = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        pygame.draw.rect(glass, (245, 240, 230, 64), glass.get_rect(), border_radius=S(22))
        surf.blit(glass, pill.topleft)
        ui.text(surf, title, ts, w // 2 + S(3), ty - ts // 2 + S(3),
                color=(26, 30, 26), center=True)
        ui.text(surf, title, ts, w // 2, ty - ts // 2, color=ui.CREAM, center=True)

        mp = pygame.mouse.get_pos()
        for i, (rect, lab, _cb) in enumerate(self._buttons):
            self._draw_button(surf, rect, lab, rect.collidepoint(mp), S)

        # small info + sound buttons (top-right)
        self._draw_chip(surf, self._info_rect, "?", self._info_rect.collidepoint(mp), S, 22)
        spk = "Sound: off" if settings.get("muted") else "Sound"
        self._draw_chip(surf, self._sound_rect, spk, self._sound_rect.collidepoint(mp), S, 17)

        # subtle Reset Progress link
        rcol = (235, 224, 214) if self._reset_rect.collidepoint(mp) else (210, 202, 196)
        ui.text(surf, "Reset Progress", S(18), self._reset_rect.centerx,
                self._reset_rect.y + S(7), color=rcol, center=True, shadow=True)

        ui.text(surf, "ABProjects", S(26), w // 2, h - S(40), color=ui.CREAM,
                center=True, shadow=True)

        if self.dialog == "settings":
            self._draw_settings(surf, S)
        elif self.dialog == "reset":
            self._draw_reset(surf, S)
        elif self.dialog == "soundbook":
            self.soundbook.draw(surf)
        elif self.dialog == "about":
            self._draw_about(surf, S)
        elif self.dialog in ("new_story", "no_story"):
            self._draw_story_dialog(surf, S)

    def _draw_about(self, surf, S):
        self._scrim(surf)
        panel, viewport, done = self._about_rects()
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(18), shadow=True)
        ui.pixel_text_fit_box(surf, "ABOUT THE GAME", S(24),
                              pygame.Rect(panel.x + S(24), panel.y + S(18), panel.w - S(48), S(30)),
                              color=ui.INK, min_size=S(16), center=True)
        ui.pixel_text_fit_box(surf, "Mouse wheel or arrow keys scroll.", S(12),
                              pygame.Rect(panel.x + S(24), panel.y + S(48), panel.w - S(48), S(18)),
                              color=ui.INK_SOFT, min_size=S(9), center=True, bold=False)
        ui.draw_panel(surf, viewport, fill=ui.CREAM, edge=ui.PAPER_EDGE, radius=S(10), shadow=False)
        old_clip = surf.get_clip()
        surf.set_clip(viewport.inflate(-S(10), -S(10)))
        y = viewport.y + S(14) - self._about_scroll
        for line, heading in self._about_copy():
            if heading:
                ui.pixel_text(surf, line.upper(), S(17), viewport.x + S(16), y, color=ui.GRASS_DK)
                y += S(26)
            else:
                text_rect = pygame.Rect(viewport.x + S(16), y, viewport.w - S(32), S(400))
                y = ui.draw_wrapped(surf, line, S(16), text_rect, color=ui.INK_SOFT, bold=False, line_gap=S(2))
                y += S(10)
        surf.set_clip(old_clip)
        # simple scroll bar
        total_h = self._about_content_height(viewport.w)
        if total_h > viewport.h:
            track = pygame.Rect(viewport.right - S(12), viewport.y + S(10), S(6), viewport.h - S(20))
            pygame.draw.rect(surf, ui.PAPER_DK, track, border_radius=S(3))
            thumb_h = max(S(30), int(track.h * (viewport.h / float(total_h))))
            max_scroll = max(1, total_h - viewport.h)
            thumb_y = track.y + int((track.h - thumb_h) * (self._about_scroll / float(max_scroll)))
            pygame.draw.rect(surf, ui.GRASS, pygame.Rect(track.x, thumb_y, track.w, thumb_h), border_radius=S(3))
        ui.draw_panel(surf, done, fill=ui.GRASS, radius=S(9), shadow=False)
        ui.pixel_text_center_box(surf, "DONE", S(15), done, color=ui.CREAM)

    def _scrim(self, surf):
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((20, 24, 22, 150))
        surf.blit(veil, (0, 0))

    def _draw_story_dialog(self, surf, S):
        self._scrim(surf)
        panel, left, right = self._story_dialog_rects()
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(16), shadow=True)
        if self.dialog == "no_story":
            ui.pixel_text(surf, "NO STORY TO CONTINUE YET", S(22), panel.centerx,
                          panel.y + S(36), color=ui.INK, center=True)
            lines = ["Choose New Game to watch Bal arrive by boat",
                     "and build the first music shop on the island."]
            y = panel.y + S(92)
            for line in lines:
                ui.pixel_text(surf, line, S(15), panel.centerx, y,
                              color=ui.INK_SOFT, center=True, bold=False)
                y += S(30)
            ok = pygame.Rect(0, 0, S(160), S(44))
            ok.midbottom = (panel.centerx, panel.bottom - S(24))
            ui.draw_panel(surf, ok, fill=ui.GRASS, radius=S(9), shadow=False)
            ui.pixel_text_center_box(surf, "OK", S(16), ok, color=ui.CREAM)
            return
        ui.pixel_text(surf, "BEGIN A NEW STORY?", S(23), panel.centerx,
                      panel.y + S(34), color=ui.INK, center=True)
        ui.pixel_text(surf, "The current island shop and its story progress will be replaced.",
                      S(14), panel.centerx, panel.y + S(92), color=ui.INK_SOFT,
                      center=True, bold=False)
        ui.draw_panel(surf, left, fill=ui.PAPER_DK, radius=S(9), shadow=False)
        ui.pixel_text_center_box(surf, "KEEP CURRENT", S(14), left, color=ui.INK)
        ui.draw_panel(surf, right, fill=(203, 112, 104), radius=S(9), shadow=False)
        ui.pixel_text_center_box(surf, "START OVER", S(14), right, color=ui.CREAM)

    def _draw_settings(self, surf, S):
        self._scrim(surf)
        panel, rows = self._settings_rows()
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(18), shadow=True)

        title_box = pygame.Rect(panel.x + S(34), panel.y + S(22),
                                panel.w - S(68), S(40))
        ui.pixel_text_fit_box(surf, "SOUND SETTINGS", S(28), title_box,
                              color=ui.INK, min_size=S(18), center=True)
        subtitle = pygame.Rect(panel.x + S(42), panel.y + S(68),
                               panel.w - S(84), S(28))
        ui.pixel_text_fit_box(surf, "Adjust the game volume. Changes are saved automatically.",
                              S(15), subtitle, color=ui.INK_SOFT,
                              bold=False, min_size=S(10), center=True)

        for key, label, bar in rows:
            label_box = pygame.Rect(panel.x + S(40), bar.y - S(8),
                                    S(145), S(36))
            ui.pixel_text_fit_box(surf, label, S(18), label_box,
                                  color=ui.INK, bold=False,
                                  min_size=S(11), center=False)

            track = bar.inflate(0, S(8))
            ui.draw_panel(surf, track, fill=ui.PAPER_DK,
                          edge=ui.PAPER_EDGE, radius=S(8), shadow=False,
                          sheen=False)
            val = max(0.0, min(1.0, float(settings.get(key))))
            inner = pygame.Rect(track.x + S(3), track.y + S(3),
                                max(0, int((track.w - S(6)) * val)),
                                max(1, track.h - S(6)))
            if inner.w > 0:
                pygame.draw.rect(surf, ui.GRASS, inner, border_radius=S(6))
            knob_x = track.x + S(3) + int((track.w - S(6)) * val)
            pygame.draw.circle(surf, ui.CREAM, (knob_x, track.centery), S(12))
            pygame.draw.circle(surf, ui.GRASS_DK, (knob_x, track.centery), S(12),
                               max(1, S(2)))

            value_box = pygame.Rect(track.right + S(14), bar.y - S(8),
                                    S(72), S(36))
            ui.pixel_text_fit_box(surf, "%d%%" % round(val * 100), S(16),
                                  value_box, color=ui.INK_SOFT,
                                  bold=False, min_size=S(10), center=True)

        mute_r, done_r = self._settings_buttons(panel)
        muted = settings.get("muted")
        ui.draw_panel(surf, mute_r,
                      fill=(220, 150, 140) if muted else ui.PAPER_DK,
                      radius=S(10), shadow=False)
        ui.pixel_text_fit_box(surf, "SOUND MUTED" if muted else "MUTE ALL SOUND",
                              S(16), mute_r.inflate(-S(12), -S(8)),
                              color=ui.CREAM if muted else ui.INK,
                              min_size=S(10), center=True)
        ui.draw_panel(surf, done_r, fill=ui.GRASS, radius=S(10), shadow=False)
        ui.pixel_text_fit_box(surf, "DONE", S(17), done_r.inflate(-S(10), -S(8)),
                              color=ui.CREAM, min_size=S(11), center=True)

    def _draw_reset(self, surf, S):
        self._scrim(surf)
        panel, cancel, reset = self._reset_buttons()
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(18), shadow=True)

        title_box = pygame.Rect(panel.x + S(44), panel.y + S(24),
                                panel.w - S(88), S(42))
        ui.pixel_text_fit_box(surf, "RESET ALL PROGRESS?", S(28), title_box,
                              color=ui.INK, min_size=S(18), center=True)

        warning = pygame.Rect(panel.x + S(70), panel.y + S(80),
                              panel.w - S(140), S(42))
        ui.draw_panel(surf, warning, fill=(244, 222, 211),
                      edge=(218, 167, 151), radius=S(10), shadow=False)
        ui.pixel_text_fit_box(surf, "THIS CANNOT BE UNDONE", S(15),
                              warning.inflate(-S(14), -S(8)),
                              color=(142, 73, 62), min_size=S(10), center=True)

        body = ("Story progress, Explore progress, collected sounds, decorations, "
                "helpers, coins, and saved songs will be deleted.\n\n"
                "Sound settings, imported audio files, and exported WAV files will stay.")
        body_rect = pygame.Rect(panel.x + S(62), panel.y + S(145),
                                panel.w - S(124), panel.h - S(245))
        paragraphs = body.split("\n\n")
        y = body_rect.y
        for paragraph in paragraphs:
            lines = ui.wrap_lines(paragraph, body_rect.w, S(17),
                                  pixel=True, bold=False)
            for line in lines:
                if y + ui.pixel_line_height(S(17), False) > body_rect.bottom:
                    break
                ui.pixel_text(surf, line, S(17), body_rect.centerx, y,
                              color=ui.INK_SOFT, center=True, bold=False)
                y += ui.pixel_line_height(S(17), False) + S(5)
            y += S(10)

        ui.draw_panel(surf, cancel, fill=ui.PAPER_DK, radius=S(10), shadow=False)
        ui.pixel_text_fit_box(surf, "KEEP MY PROGRESS", S(16),
                              cancel.inflate(-S(12), -S(8)), color=ui.INK,
                              min_size=S(10), center=True)
        ui.draw_panel(surf, reset, fill=(206, 110, 100), radius=S(10), shadow=False)
        ui.pixel_text_fit_box(surf, "RESET EVERYTHING", S(16),
                              reset.inflate(-S(12), -S(8)), color=ui.CREAM,
                              min_size=S(10), center=True)

