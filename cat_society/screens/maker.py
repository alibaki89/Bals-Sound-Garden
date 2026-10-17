"""Music Maker: a cozy step sequencer that plays and exports real audio.

The player arms a collected component from the browser, clicks it onto a track
lane in the grid, and presses play. Eight lanes (Melody, Chords, Bass, Drums,
Rhythms, Loops, Ambience, User) each accept one component kind. One-shot
components fill a single step; loops, rhythms and ambience span their natural
length. Playback renders the whole project to one buffer (so it matches the WAV
export exactly), and a playhead sweeps the grid.
"""

import json
import math
import os
import time

import pygame

from .. import ui, config
from ..ui.widgets import Button, Slider
from ..ui.icons import draw_icon
from ..audio import synth
from ..audio import sfx
from ..components import catalog
from ..music.project import Project, FAMILIES
from ..logging_utils import get_logger

_LOG = get_logger("maker")
from . import exporting

_TYPE_LABEL = {
    "note": "notes", "chord": "chords", "drum": "drum hits", "rhythm": "rhythms",
    "loop": "loops", "ambience": "ambience", "bass": "bass",
}


class MakerScreen:
    def __init__(self, app):
        self.app = app
        self.project = None
        self.selected_track = 0
        self.armed = None              # armed component id for placement
        self.browser_scroll = 0
        self.editing_name = False
        self._editing_name_original = None
        self.searching = False         # typing in the browser search box
        self.search = ""               # browser filter text
        self.sort_mode = 0             # 0 name, 1 rarity, 2 recent
        self.message = ""
        self.message_t = 0.0
        self.transport = []
        self.lane_sliders = []
        self._chip_rects = []          # (rect, comp_id) for browser hit-testing
        self._search_rect = None
        self._sort_rect = None
        self.track_scroll = 0          # vertical scroll of the track lanes
        self.time_scroll = 0           # horizontal scroll of the timeline
        self._drag_bar = None          # "v" or "h" while dragging a scrollbar
        self._drag_off = 0
        self.track_menu_open = False   # the "Add Track" family picker
        self.editing_track = -1        # index of the track being renamed (-1 = none)
        self._editing_track_original = None
        self._track_btn_rects = []     # (rect, ("kind"/"del"/"dup"/"name", idx))
        self._add_track_rect = None
        self._menu_rects = []          # (rect, kind) for the family popup
        self._name_rect = None
        self._browser_area = None
        self.dialog = None             # modal dialog dict (save/export confirms)
        self.load_modal = None         # saved-project browser
        self._load_rects = []
        self._dialog_rects = []        # (rect, action_key)
        self._hover_clip = None        # (comp, rect) under the mouse, for tooltip
        self.export_task = None        # responsive background WAV render
        # connected-phrase ("Connect") workflow
        self.connect_mode = False      # the Connect tool toggle
        self.link_track = -1           # track index of the pending selection
        self.link_anchor = None        # step of the first picked tile
        self.link_range = None         # (lo, hi) steps of the pending selection
        self.link_editing = None       # phrase index when adjusting an existing one
        self._connect_rect = None      # Connect segment in the edit-tool group
        self._tiles_rect = None        # ordinary tile-editing segment
        self._pill_rects = []          # (rect, action) in the arrangement toolbar
        self._top_groups = {}          # stable visual groups in the Maker header
        self.timeline_header = None
        self.ruler = None
        self._clean_signature = None
        self._pending_discard = None

    def on_enter(self):
        # edit an existing project handed over by Your Music, else start fresh
        pend = getattr(self.app, "pending_project", None)
        established_clean = False
        if pend is not None:
            self.project = pend
            self.app.pending_project = None
            established_clean = True
        elif self.project is None:
            self.project = Project("Untitled Song")
            established_clean = True
        self._reset_transient_input_state()
        pygame.mouse.set_visible(True)
        self._layout()
        if established_clean or self._clean_signature is None:
            self._set_clean_baseline()
        pop_warning = getattr(self.app, "pop_project_warning", None)
        warning = pop_warning() if callable(pop_warning) else None
        if warning:
            self._flash(warning)

    def _project_signature(self):
        if self.project is None:
            return None
        payload = self.project.to_dict()
        # Modified time is persistence metadata, not musical content.
        payload.pop("modified", None)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _set_clean_baseline(self):
        self._clean_signature = self._project_signature()

    def _is_dirty(self):
        return self.project is not None and self._project_signature() != self._clean_signature

    def _request_discard(self, action, project_id=None):
        if not self._is_dirty():
            self._perform_discard_action(action, project_id)
            return
        self._pending_discard = (action, project_id)
        self._open_dialog(
            "Unsaved changes",
            ["You have unsaved changes.", "Leave without saving them?"],
            [("Stay", "cancel"), ("Leave without saving", "discard_confirm")],
        )

    def _perform_discard_action(self, action, project_id=None):
        self._pending_discard = None
        if action == "new":
            self._create_new()
        elif action == "load":
            self._load_project_by_id(project_id)
        elif action == "leave":
            self.app.engine.stop_music()
            self.project = None
            self._clean_signature = None
            self.app.goto("menu")

    def _leave(self):
        if self._editing_locked():
            self.app.engine.stop_music()
            self.play_btn.label = "Play"
        self._request_discard("leave")

    # -- layout -------------------------------------------------------------
    ROW_H = 86                 # fixed lane height (panels never shrink)
    MIN_STEP = 26              # minimum step width before the timeline scrolls

    def _layout(self):
        """Build a calm, grouped Maker layout without changing its actions."""
        w, h = self.app.window.get_size()
        self.w, self.h = w, h
        S = lambda v: ui.scaled(h, v)
        P = lambda v: max(1, int(round(v * getattr(config, "UI_H", h) / 1080.0)))
        self.S = S
        self.P = P

        margin = P(14)
        gutter = P(14)
        self.topbar = pygame.Rect(0, 0, w, S(144))
        self.browser = pygame.Rect(0, h - S(210), w, S(210))
        self.lane_w = max(S(248), min(S(310), int(w * 0.225)))

        header_y = self.topbar.bottom + P(8)
        header_h = S(52)
        ruler_h = S(28)
        self.lane_header = pygame.Rect(margin, header_y,
                                       self.lane_w - margin, header_h + ruler_h)
        self.timeline_header = pygame.Rect(self.lane_w, header_y,
                                           w - self.lane_w - margin - gutter,
                                           header_h)
        self.ruler = pygame.Rect(self.lane_w, self.timeline_header.bottom,
                                 self.timeline_header.w, ruler_h)

        gy = self.ruler.bottom
        self.grid = pygame.Rect(self.lane_w, gy,
                                w - self.lane_w - margin - gutter,
                                self.browser.y - gy - P(12) - gutter)
        self.lanes = pygame.Rect(margin, self.grid.y,
                                 self.lane_w - margin, self.grid.h)
        self.vbar = pygame.Rect(self.grid.right + S(4), self.grid.y,
                                S(9), self.grid.h)
        self.hbar = pygame.Rect(self.grid.x, self.grid.bottom + S(4),
                                self.grid.w, S(9))

        self.row_h = S(94)
        self._clamp_scroll()
        self._clamp_time_scroll()

        inner = self.topbar.inflate(-margin * 2, -P(12))
        song_w = max(S(350), min(S(470), int(w * 0.30)))
        song = pygame.Rect(inner.x, inner.y, song_w, inner.h)
        right_x = song.right + P(10)
        right_w = inner.right - right_x
        row_gap = P(8)
        row_h = (inner.h - row_gap) // 2
        top_y = inner.y
        bottom_y = top_y + row_h + row_gap

        playback_w = max(S(245), int(right_w * 0.27))
        playback = pygame.Rect(right_x, top_y, playback_w, row_h)
        project = pygame.Rect(playback.right + P(8), top_y,
                              inner.right - playback.right - P(8), row_h)

        tempo_w = max(S(215), int(right_w * 0.23))
        bars_w = max(S(195), int(right_w * 0.21))
        tempo = pygame.Rect(right_x, bottom_y, tempo_w, row_h)
        bars = pygame.Rect(tempo.right + P(8), bottom_y, bars_w, row_h)
        tools = pygame.Rect(bars.right + P(8), bottom_y,
                            inner.right - bars.right - P(8), row_h)
        hint = pygame.Rect(0, 0, 0, 0)
        self._top_groups = {
            "song": song, "playback": playback, "project": project,
            "tempo": tempo, "bars": bars, "tools": tools, "hint": hint,
        }

        self.transport = []

        def make_button(rect, label, callback, accent=None, size=19):
            button = Button(rect, label, callback, size=S(size), accent=accent)
            self.transport.append(button)
            return button

        cap_h = P(22)
        button_y = playback.y + cap_h
        button_h = playback.h - cap_h - P(6)
        gap = P(6)

        play_w = int((playback.w - P(12) - gap) * 0.52)
        self.play_btn = make_button(
            pygame.Rect(playback.x + P(6), button_y, play_w, button_h),
            "Play", self._toggle_play, ui.GRASS, 20)
        self.loop_btn = make_button(
            pygame.Rect(self.play_btn.rect.right + gap, button_y,
                        playback.right - P(6) - self.play_btn.rect.right - gap,
                        button_h),
            self._loop_label(), self._toggle_loop, None, 17)

        labels = [
            ("New", self._new, None, 15),
            ("Load", self._open_load, None, 15),
            ("Save", self._save, ui.GRASS, 15),
            ("Export", self._export, ui.SUN, 14),
            ("Back", self._leave, None, 15),
        ]
        usable = project.w - P(12) - gap * (len(labels) - 1)
        weights = [0.16, 0.18, 0.18, 0.25, 0.23]
        widths = [int(usable * q) for q in weights]
        px = project.x + P(6)
        widths[-1] = project.right - P(6) - px - sum(widths[:-1]) - gap * (len(labels) - 1)
        for (label, callback, accent, font_size), bw in zip(labels, widths):
            make_button(pygame.Rect(px, project.y + cap_h,
                                    max(S(44), bw), button_h),
                        label, callback, accent, font_size)
            px += bw + gap

        step_h = tempo.h - cap_h - P(6)
        step_y = tempo.y + cap_h
        square = max(S(28), step_h)
        self.tempo_minus = make_button(
            pygame.Rect(tempo.x + P(6), step_y, square, step_h), "-",
            lambda: self._tempo(-5), None, 22)
        self.tempo_plus = make_button(
            pygame.Rect(tempo.right - P(6) - square, step_y, square, step_h), "+",
            lambda: self._tempo(5), None, 22)
        self.bars_minus = make_button(
            pygame.Rect(bars.x + P(6), step_y, square, step_h), "-",
            lambda: self._bars(-1), None, 22)
        self.bars_plus = make_button(
            pygame.Rect(bars.right - P(6) - square, step_y, square, step_h), "+",
            lambda: self._bars(1), None, 22)

        tool_inner = pygame.Rect(tools.x + P(6), tools.y + cap_h,
                                 tools.w - P(12), tools.h - cap_h - P(6))
        half = tool_inner.w // 2
        self._tiles_rect = pygame.Rect(tool_inner.x, tool_inner.y,
                                       half, tool_inner.h)
        self._connect_rect = pygame.Rect(tool_inner.x + half, tool_inner.y,
                                         tool_inner.w - half, tool_inner.h)

        self.lane_sliders = []
        for i, track in enumerate(self.project.tracks):
            ry = self._row_y(i)
            rect = pygame.Rect(self.lanes.x + S(120),
                               ry + int(self.row_h) - S(22),
                               self.lane_w - S(140), S(8))
            self.lane_sliders.append(
                Slider(rect, 0.0, 1.0, track.volume, None, fmt=lambda value: ""))
        self._clamp_browser_scroll()

    def _content_h(self):
        return len(self.project.tracks) * self.row_h

    def _max_scroll(self):
        return max(0, int(self._content_h() - self.grid.h))

    def _clamp_scroll(self):
        self.track_scroll = max(0, min(self.track_scroll, self._max_scroll()))

    def _row_y(self, i):
        return int(self.grid.y + i * self.row_h - self.track_scroll)

    def _row_for_pos(self, my):
        r = int((my - self.grid.y + self.track_scroll) // self.row_h)
        return r if 0 <= r < len(self.project.tracks) else -1

    def _step_w(self):
        return max(self.S(self.MIN_STEP),
                   self.grid.w / max(1, self.project.total_steps))

    def _content_w(self):
        return self._step_w() * self.project.total_steps

    def _max_time_scroll(self):
        return max(0, int(self._content_w() - self.grid.w))

    def _clamp_time_scroll(self):
        self.time_scroll = max(0, min(self.time_scroll, self._max_time_scroll()))

    def _cancel_widget_interactions(self):
        """Release pointer-only widget state that must never survive a focus change."""
        for button in self.transport:
            button._down = False
        for slider in self.lane_sliders:
            slider._drag = False
        self._drag_bar = None

    def _reset_transient_input_state(self):
        """Reset focus/drag state while preserving the current arrangement."""
        if self.editing_name:
            self._finish_project_name_edit()
        if self.editing_track >= 0:
            self._finish_track_name_edit()
        self.editing_name = False
        self.editing_track = -1
        self._editing_name_original = None
        self._editing_track_original = None
        self.searching = False
        self.track_menu_open = False
        self.dialog = None
        self.load_modal = None
        self._load_rects = []
        self._dialog_rects = []
        self._menu_rects = []
        self._hover_clip = None
        self.connect_mode = False
        self._clear_link_selection()
        self._pill_rects = []
        self._cancel_widget_interactions()

    def _begin_project_name_edit(self):
        self._cancel_widget_interactions()
        if self.editing_track >= 0:
            self._finish_track_name_edit()
        if not self.editing_name:
            self._editing_name_original = self.project.name
        self.editing_track = -1
        self._editing_track_original = None
        self.searching = False
        self.editing_name = True

    def _finish_project_name_edit(self):
        if not self.editing_name:
            return
        before = (self._editing_name_original if self._editing_name_original is not None
                  else self.project.name)
        if not self.project.name.strip():
            self.project.name = "Untitled Song"
        self.editing_name = False
        self._editing_name_original = None
        if self.project.name != before:
            self.project.touch()

    def _begin_track_name_edit(self, idx):
        if not (0 <= idx < len(self.project.tracks)):
            return
        self._cancel_widget_interactions()
        if self.editing_name:
            self._finish_project_name_edit()
        if self.editing_track >= 0 and self.editing_track != idx:
            self._finish_track_name_edit()
        self.editing_name = False
        self._editing_name_original = None
        self.searching = False
        self.editing_track = idx
        self._editing_track_original = self.project.tracks[idx].name

    def _finish_track_name_edit(self):
        idx = self.editing_track
        if idx < 0:
            return
        before = self._editing_track_original
        self.editing_track = -1
        self._editing_track_original = None
        if not (0 <= idx < len(self.project.tracks)):
            return
        track = self.project.tracks[idx]
        if not track.name.strip():
            track.name = "Track"
        if before is not None and track.name != before:
            self.project.touch()

    def _active_track_name_rect(self):
        for rect, action in self._track_btn_rects:
            if action == ("name", self.editing_track):
                return rect
        return None

    def _handle_text_focus_event(self, e):
        """Consume typing, but let an outside click continue in the same event."""
        if not self.editing_name and self.editing_track < 0:
            return False
        if e.type == pygame.KEYDOWN:
            if self.editing_name:
                self._name_event(e)
            else:
                self._track_name_event(e)
            return True
        if e.type == pygame.MOUSEBUTTONDOWN:
            active_rect = (self._name_rect if self.editing_name
                           else self._active_track_name_rect())
            if active_rect is not None and active_rect.collidepoint(e.pos):
                return True
            self._cancel_widget_interactions()
            if self.editing_name:
                self._finish_project_name_edit()
            else:
                self._finish_track_name_edit()
            return False
        return False

    def _browser_geometry(self):
        S = self.S
        area = pygame.Rect(self.browser.x + S(16), self.browser.y + S(76),
                           self.browser.w - S(32), self.browser.h - S(88))
        chip_w, chip_h, gap = S(206), S(40), S(9)
        per_row = max(1, area.w // (chip_w + gap))
        return area, chip_w, chip_h, gap, per_row

    def _max_browser_scroll(self, track=None):
        if self.project is None or not self.project.tracks or not hasattr(self, "S"):
            return 0
        track = track or self.project.tracks[self.selected_track]
        area, _, chip_h, gap, per_row = self._browser_geometry()
        count = len(self._browser_items(track))
        rows = (count + per_row - 1) // per_row
        content_h = max(0, rows * (chip_h + gap) - gap)
        return max(0, int(content_h - area.h))

    def _clamp_browser_scroll(self, track=None):
        self.browser_scroll = max(0, min(self.browser_scroll,
                                         self._max_browser_scroll(track)))

    def _placement_prompt(self, track):
        noun = {
            "melody": "note", "chords": "chord", "bass": "bass sound",
            "drums": "drum sound", "rhythms": "rhythm", "loops": "loop",
            "ambience": "ambience sound",
        }.get(track.kind, "sound")
        return "Choose a %s from the drawer first" % noun

    def _clear_incompatible_armed(self):
        if self.armed is None or not self.project.tracks:
            return False
        comp = catalog.get(self.armed)
        track = self.project.tracks[self.selected_track]
        if comp is None or not track.accepts(comp):
            self.armed = None
            return True
        return False

    def _select_track(self, idx):
        if not self.project.tracks:
            return False
        idx = max(0, min(idx, len(self.project.tracks) - 1))
        changed = idx != self.selected_track
        self.selected_track = idx
        if changed:
            self.browser_scroll = 0
        self._clear_incompatible_armed()
        self._clamp_browser_scroll()
        return changed

    # -- add-track family menu ---------------------------------------------
    def _open_track_menu(self):
        self.track_menu_open = not self.track_menu_open

    def _add_track(self, kind):
        self._clear_link_selection()
        self.project.add_track(kind)
        self._select_track(len(self.project.tracks) - 1)
        self.track_menu_open = False
        self.track_scroll = self._max_scroll()   # scroll to reveal the new track
        self._layout()

    def _delete_track(self, idx):
        self._clear_link_selection()
        if self.project.remove_track(idx):
            self._select_track(min(self.selected_track, len(self.project.tracks) - 1))
            self._layout()

    def _duplicate_track(self, idx):
        self._clear_link_selection()
        if self.project.duplicate_track(idx) is not None:
            self._select_track(min(idx + 1, len(self.project.tracks) - 1))
            self._layout()


    def _loop_label(self):
        return "Loop  ON" if getattr(self, "_loop", False) else "Loop  off"

    # -- transport ----------------------------------------------------------
    def _toggle_play(self):
        if self.app.engine.is_playing():
            self.app.engine.stop_music()
            self.play_btn.label = "Play"
        else:
            self.app.engine.play_project(self.project, samples=exporting.sample_buffers(self.app),
                                         loop=getattr(self, "_loop", False))
            self.play_btn.label = "Stop"

    def _toggle_loop(self):
        if self._stop_before_edit():
            return
        self._loop = not getattr(self, "_loop", False)
        self.loop_btn.label = self._loop_label()
        if self.app.engine.is_playing():
            self._toggle_play()
            self._toggle_play()

    def _tempo(self, d):
        if self._stop_before_edit():
            return
        self.project.tempo = max(50, min(200, self.project.tempo + d))
        self.project.touch()
        self.app.engine.invalidate()

    def _bars(self, d):
        if self._stop_before_edit():
            return
        self.project.bars = max(2, min(32, self.project.bars + d))
        if d < 0:
            for track in self.project.tracks:
                track.trim_phrases(self.project.total_steps)
            self._clear_link_selection()
        self.project.touch()
        self._clamp_time_scroll()

    def _new(self):
        if self._stop_before_edit():
            return
        self._request_discard("new")

    def _create_new(self):
        self.app.engine.stop_music()
        self.connect_mode = False
        self._clear_link_selection()
        self.project = Project("Untitled Song")
        self.selected_track = 0
        self.armed = None
        self.play_btn.label = "Play"
        self._layout()
        self._set_clean_baseline()
        self._flash("New song")

    def _editing_locked(self):
        return bool(self.app.engine.is_playing())

    def _stop_before_edit(self):
        if self._editing_locked():
            self._flash("Stop playback before editing the song")
            return True
        return False

    def _open_load(self):
        if self._stop_before_edit():
            return
        projects = self.app.refresh_projects()
        if not projects:
            self._flash("No saved songs yet")
            return
        self._cancel_widget_interactions()
        self.load_modal = {"items": list(projects), "idx": 0}
        self._load_rects = []

    def _close_load(self):
        self.load_modal = None
        self._load_rects = []

    def _load_selected(self, project=None):
        if self._stop_before_edit():
            return
        if project is None:
            items = (self.load_modal or {}).get("items", [])
            if not items:
                self._close_load()
                return
            project = items[(self.load_modal or {}).get("idx", 0)]
        project_id = project.id
        self._close_load()
        self._request_discard("load", project_id)

    def _load_project_by_id(self, project_id):
        try:
            loaded = self.app.projects.load(project_id)
        except Exception:
            loaded = None
            _LOG.exception("Unexpected failure while loading saved song %s", project_id)
        if loaded is None:
            self._flash("That saved song could not be opened")
            self.app.refresh_projects()
            pop_warning = getattr(self.app, "pop_project_warning", None)
            warning = pop_warning() if callable(pop_warning) else None
            if warning:
                self._flash(warning)
            return
        self.project = loaded
        self.selected_track = 0
        self.armed = None
        self.track_scroll = 0
        self.time_scroll = 0
        self._reset_transient_input_state()
        self._layout()
        self._set_clean_baseline()
        self._flash("Loaded '%s'" % self.project.name)

    def _load_event(self, e):
        items = (self.load_modal or {}).get("items", [])
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self._close_load()
            elif items and e.key in (pygame.K_UP, pygame.K_w):
                self.load_modal["idx"] = (self.load_modal["idx"] - 1) % len(items)
            elif items and e.key in (pygame.K_DOWN, pygame.K_s):
                self.load_modal["idx"] = (self.load_modal["idx"] + 1) % len(items)
            elif items and e.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._load_selected()
            return
        if e.type == pygame.MOUSEMOTION:
            for rect, actual, _project in self._load_rects:
                if rect.collidepoint(e.pos):
                    self.load_modal["idx"] = actual
                    return
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, _actual, project in self._load_rects:
                if rect.collidepoint(e.pos):
                    self._load_selected(project)
                    return
            self._close_load()

    def _draw_load_modal(self, surf):
        if self.load_modal is None:
            return
        S = self.S
        items = self.load_modal.get("items", [])
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((20, 24, 22, 165))
        surf.blit(veil, (0, 0))
        rows = min(7, len(items))
        row_h = S(52)
        panel = pygame.Rect(0, 0, min(self.w - S(40), S(620)),
                            S(108) + rows * row_h)
        panel.center = (self.w // 2, self.h // 2)
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=S(16), shadow=True)
        ui.pixel_text(surf, "LOAD A SAVED SONG", S(24), panel.centerx,
                      panel.y + S(18), color=ui.INK, center=True)
        ui.pixel_text(surf, "UP / DOWN AND ENTER     CLICK     ESC TO CLOSE",
                      S(10), panel.centerx, panel.y + S(57),
                      color=ui.INK_SOFT, center=True)
        self._load_rects = []
        idx = max(0, min(self.load_modal.get("idx", 0), len(items) - 1))
        self.load_modal["idx"] = idx
        first = max(0, min(idx - rows // 2, len(items) - rows))
        top = panel.y + S(88)
        mouse = pygame.mouse.get_pos()
        for visible, project in enumerate(items[first:first + rows]):
            actual = first + visible
            rect = pygame.Rect(panel.x + S(18), top + visible * row_h,
                               panel.w - S(36), row_h - S(8))
            active = actual == idx or rect.collidepoint(mouse)
            ui.draw_panel(surf, rect, fill=ui.CREAM if active else ui.PAPER_DK,
                          edge=ui.GRASS if active else ui.PAPER_EDGE,
                          radius=S(9), shadow=False)
            ui.pixel_text_fit_box(surf, project.name.upper(), S(16),
                                  pygame.Rect(rect.x + S(16), rect.y + S(8),
                                              rect.w - S(170), S(20)),
                                  color=ui.INK, min_size=S(10), center=False)
            info = "%d BPM     %d BARS" % (project.tempo, project.bars)
            ui.pixel_text_fit_box(surf, info, S(11),
                                  pygame.Rect(rect.right - S(150), rect.y + S(10),
                                              S(134), S(18)),
                                  color=ui.INK_SOFT, min_size=S(8), right=True,
                                  center=False, bold=False)
            self._load_rects.append((rect, actual, project))

    def _safe_name(self):
        s = "".join(c if c.isalnum() or c in "-_ " else "_"
                    for c in self.project.name).strip().replace(" ", "_")
        return s or "song"

    def _save(self):
        name = self.project.name.strip().lower()
        clash = [p for p in self.app.projects.list_projects()
                 if p.name.strip().lower() == name and p.id != self.project.id]
        if clash:
            self._open_dialog(
                "Name already in use",
                ["A song called \"%s\" already exists." % self.project.name.strip(),
                 "Replace it, rename this one, or cancel?"],
                [("Cancel", "cancel"), ("Rename", "save_rename"),
                 ("Replace", "save_replace")],
                conflict_ids=[p.id for p in clash])
            return
        self._do_save()

    def _do_save(self, replace_ids=None):
        if self.app.projects.save(self.project, replace_ids=replace_ids):
            self.app.refresh_projects()
            self._set_clean_baseline()
            self._flash("Saved  '%s'" % self.project.name)
        else:
            self._flash("Save failed. Your previous song is safe; try again.")

    def _ask_save_path(self, default_name):
        return exporting.ask_save_path(default_name)

    def _export(self):
        if self.export_task is not None and not self.export_task.status()["finished"]:
            self._flash("A WAV export is already rendering")
            return
        if self.project.clip_count() == 0:
            self._flash("Add some sounds first")
            return
        default = exporting.safe_filename(self.project.name)
        res = exporting.ask_save_path(default)
        if res:                                  # a chosen path (native dialog)
            self._do_export(res)
        elif res == "":                          # user cancelled the dialog
            self._flash("Export cancelled")
        else:                                    # no GUI -> internal folder
            target = exporting.fallback_target(default)
            if os.path.exists(target):
                self._open_dialog(
                    "File already exists",
                    ["A file named \"%s\" is already in the exports folder."
                     % default, "Replace it?"],
                    [("Cancel", "cancel"), ("Replace", "export_replace")],
                    export_path=target)
            else:
                self._do_export(target)

    def _do_export(self, path):
        if self.export_task is not None and not self.export_task.status()["finished"]:
            self._flash("A WAV export is already rendering")
            return
        try:
            self.export_task = exporting.start_export(
                self.project, path, samples=exporting.sample_buffers(self.app))
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

    # -- modal dialogs (save collision / export overwrite) ------------------
    def _open_dialog(self, title, lines, buttons, **data):
        self.dialog = {"title": title, "lines": lines, "buttons": buttons}
        self.dialog.update(data)

    def _dialog_action(self, key):
        d = self.dialog or {}
        self.dialog = None
        if key == "save_replace":
            self._do_save(replace_ids=d.get("conflict_ids"))
        elif key == "save_rename":
            self.editing_name = True
        elif key == "export_replace":
            self._do_export(d.get("export_path"))
        elif key == "discard_confirm":
            action, project_id = self._pending_discard or (None, None)
            self._perform_discard_action(action, project_id)
        elif key == "cancel":
            self._pending_discard = None

    def _wrap(self, text, font, max_w):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if font.size(test)[0] <= max_w or not cur:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        return lines or [""]

    def _draw_dialog(self, surf):
        S = self.S
        self._dialog_rects = []
        veil = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        veil.fill((20, 24, 22, 150))
        surf.blit(veil, (0, 0))
        d = self.dialog
        pw = S(580)
        pad = S(30)
        inner = pw - 2 * pad
        tf = ui.font(S(23), True)
        bf = ui.font(S(18), False)
        title_lines = self._wrap(d["title"], tf, inner)
        body_lines = []
        for ln in d["lines"]:
            body_lines += self._wrap(ln, bf, inner)
        th, bh_, btn_h = S(30), S(26), S(48)
        content_h = (pad + len(title_lines) * th + S(10)
                     + len(body_lines) * bh_ + S(22) + btn_h + pad)
        ph = max(S(196), content_h)
        panel = pygame.Rect((self.w - pw) // 2, (self.h - ph) // 2, pw, ph)
        ui.draw_panel(surf, panel, fill=ui.CREAM, radius=16, shadow=True)
        y = panel.y + pad
        for ln in title_lines:
            ui.text(surf, ln, S(23), panel.centerx, y, color=ui.INK, center=True)
            y += th
        y += S(10)
        for ln in body_lines:
            ui.text(surf, ln, S(18), panel.centerx, y, color=ui.INK_SOFT, center=True)
            y += bh_
        # buttons (shrink to fit if needed so they never spill)
        btns = d["buttons"]
        gap = S(16)
        bw = S(150)
        if len(btns) * bw + (len(btns) - 1) * gap > inner:
            bw = (inner - (len(btns) - 1) * gap) // len(btns)
        total = len(btns) * bw + (len(btns) - 1) * gap
        bx = panel.centerx - total // 2
        by = panel.bottom - pad - btn_h
        mp = pygame.mouse.get_pos()
        for label, key in btns:
            r = pygame.Rect(bx, by, bw, btn_h)
            danger = key in ("save_replace", "export_replace")
            fill = (206, 110, 100) if danger else (ui.GRASS if key == "save_rename"
                                                   else ui.PAPER_DK)
            if r.collidepoint(mp):
                fill = _light(fill)
            ui.draw_panel(surf, r, fill=fill, radius=S(10), shadow=False)
            ui.text_center_box(surf, label, S(18), r,
                               color=ui.CREAM if danger or key == "save_rename" else ui.INK)
            self._dialog_rects.append((r, key))
            bx += bw + gap

    def _flash(self, msg):
        self.message = msg
        self.message_t = 3.2

    # -- events -------------------------------------------------------------
    def handle_event(self, e):
        if self.load_modal is not None:
            self._load_event(e)
            return
        if self.dialog is not None:
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self._dialog_action("cancel")
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for rect, key in self._dialog_rects:
                    if rect.collidepoint(e.pos):
                        self._dialog_action(key)
                        return
            return

        # Playback is a listening state. Arrangement, tempo, bars, track
        # controls and naming remain frozen until playback stops.
        if self._editing_locked():
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_SPACE:
                    self._toggle_play()
                elif e.key == pygame.K_s:
                    self._save()
                elif e.key == pygame.K_e:
                    self._export()
                elif e.key == pygame.K_ESCAPE:
                    self._toggle_play()
                else:
                    self._flash("Stop playback before editing the song")
                return
            if self._handle_transport_event(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                self._flash("Stop playback before editing the song")
            return

        # Text fields own keyboard input, but an outside mouse-down commits the
        # edit and continues through the normal click path in this same event.
        if self._handle_text_focus_event(e):
            return

        if self.searching:
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                    self.searching = False
                elif e.key == pygame.K_BACKSPACE:
                    self.search = self.search[:-1]
                    self.browser_scroll = 0
                elif e.unicode and e.unicode.isprintable() and len(self.search) < 24:
                    self.search += e.unicode
                    self.browser_scroll = 0
                self._clamp_browser_scroll()
                return
            if e.type == pygame.MOUSEBUTTONDOWN:
                if self._search_rect and self._search_rect.collidepoint(e.pos):
                    return
                self.searching = False

        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                if self.track_menu_open:
                    self.track_menu_open = False
                    return
                if self._link_selection_active():
                    self._clear_link_selection()
                    self._flash("Selection cleared")
                    return
                if self.connect_mode:
                    self._toggle_connect()
                    return
                self._leave()
                return
            if e.key == pygame.K_SPACE:
                self._toggle_play()
                return
            if e.key == pygame.K_RETURN and self.connect_mode:
                self._commit_link()
                return
            if e.key == pygame.K_c:
                self._toggle_connect()
                return
            if e.key == pygame.K_s:
                self._save()
                return
            if e.key == pygame.K_e:
                self._export()
                return
            if e.key == pygame.K_l:
                self._toggle_loop()
                return
            if e.key in (pygame.K_DELETE, pygame.K_BACKSPACE):
                self._remove_under_mouse(pygame.mouse.get_pos())
                return

        if e.type == pygame.MOUSEWHEEL:
            mp = pygame.mouse.get_pos()
            mods = pygame.key.get_mods()
            if self.browser.collidepoint(mp):
                self.browser_scroll -= e.y * 60
                self._clamp_browser_scroll()
                return
            if self.grid.collidepoint(mp) or self.lanes.collidepoint(mp):
                if mods & pygame.KMOD_SHIFT:
                    self.time_scroll -= e.y * 80
                    self._clamp_time_scroll()
                else:
                    self.track_scroll -= e.y * 48
                    self._clamp_scroll()
                return

        # An open popup owns the next left click, including an outside click
        # used solely to dismiss it.
        if (self.track_menu_open and e.type == pygame.MOUSEBUTTONDOWN
                and e.button == 1):
            for rect, kind in self._menu_rects:
                if rect.collidepoint(e.pos):
                    self._add_track(kind)
                    return
            self.track_menu_open = False
            return

        # Real widgets are dispatched before custom hit regions.  Each helper
        # reports whether it consumed the event so one click cannot leak into
        # unrelated controls underneath it.
        if self._handle_transport_event(e):
            return
        if self._handle_lane_slider_event(e):
            return

        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 3:
                self._remove_under_mouse(e.pos)
                return
            if e.button == 1:
                if self._max_scroll() > 0 and self.vbar.collidepoint(e.pos):
                    self._drag_bar = "v"
                    self._scrollbar_drag(e.pos[1])
                    return
                if self._max_time_scroll() > 0 and self.hbar.collidepoint(e.pos):
                    self._drag_bar = "h"
                    self._scrollbar_drag(e.pos[0])
                    return
                self._click(e.pos)
                return
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            self._drag_bar = None
            self._cancel_widget_interactions()
        elif e.type == pygame.MOUSEMOTION and self._drag_bar:
            self._scrollbar_drag(e.pos[1] if self._drag_bar == "v" else e.pos[0])

    def _handle_transport_event(self, e):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for button in self.transport:
                if button.rect.collidepoint(e.pos):
                    if self._editing_locked() and button.label not in ("Stop", "Save", "Export", "Back"):
                        self._flash("Stop playback before editing the song")
                        return True
                    button.handle_event(e)
                    return True
            return False
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            pressed = [button for button in self.transport if button._down]
            if not pressed:
                return False
            pressed[0].handle_event(e)
            for button in pressed[1:]:
                button._down = False
            return True
        return False

    def _handle_lane_slider_event(self, e):
        active_idx = next((i for i, slider in enumerate(self.lane_sliders)
                           if slider._drag), None)
        if active_idx is not None and e.type in (pygame.MOUSEMOTION,
                                                 pygame.MOUSEBUTTONUP):
            slider = self.lane_sliders[active_idx]
            if slider.handle_event(e):
                self._sync_lane_slider(active_idx)
            return True
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, slider in enumerate(self.lane_sliders):
                if i >= len(self.project.tracks):
                    break
                row_y = self._row_y(i)
                if row_y + self.row_h < self.grid.y or row_y > self.grid.bottom:
                    continue
                if slider.rect.inflate(0, 18).collidepoint(e.pos):
                    if slider.handle_event(e):
                        self._sync_lane_slider(i)
                    return True
        return False

    def _sync_lane_slider(self, idx):
        if 0 <= idx < len(self.project.tracks):
            self.project.tracks[idx].volume = self.lane_sliders[idx].value
            self.project.touch()

    def _track_name_event(self, e):
        if e.type != pygame.KEYDOWN:
            return
        idx = self.editing_track
        if idx < 0 or idx >= len(self.project.tracks):
            self.editing_track = -1
            self._editing_track_original = None
            return
        tr = self.project.tracks[idx]
        if e.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self._finish_track_name_edit()
        elif e.key == pygame.K_BACKSPACE:
            tr.name = tr.name[:-1]
        elif e.unicode and e.unicode.isprintable() and len(tr.name) < 22:
            tr.name += e.unicode

    def _name_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_RETURN, pygame.K_ESCAPE):
                self._finish_project_name_edit()
            elif e.key == pygame.K_BACKSPACE:
                self.project.name = self.project.name[:-1]
            elif e.unicode and e.unicode.isprintable() and len(self.project.name) < 28:
                self.project.name += e.unicode

    def _click(self, pos):
        mx, my = pos
        self.searching = False
        # "+ Add Track" button
        if self._add_track_rect and self._add_track_rect.collidepoint(pos):
            self._open_track_menu()
            return
        # per-track header buttons (mute / delete / duplicate / rename)
        for rect, action in self._track_btn_rects:
            if rect.collidepoint(pos):
                kind, idx = action
                if idx >= len(self.project.tracks):
                    return
                if kind == "mute":
                    self.project.tracks[idx].muted = not self.project.tracks[idx].muted
                    self.project.touch()
                elif kind == "del":
                    self._delete_track(idx)
                elif kind == "dup":
                    self._duplicate_track(idx)
                elif kind == "fx":
                    self._cycle_effect(self.project.tracks[idx])
                elif kind == "name":
                    self._select_track(idx)
                    self._begin_track_name_edit(idx)
                return
        # Segmented edit tool. Tiles returns to ordinary placement; Connect
        # enters the existing phrase workflow.
        if self._tiles_rect and self._tiles_rect.collidepoint(pos):
            if self.connect_mode:
                self._toggle_connect()
            return
        if self._connect_rect and self._connect_rect.collidepoint(pos):
            if not self.connect_mode:
                self._toggle_connect()
            return
        for rect, action in self._pill_rects:
            if rect.collidepoint(pos):
                self._pill_action(action)
                return
        # browser search box + sort button
        if self._search_rect and self._search_rect.collidepoint(pos):
            self.searching = True
            self.editing_name = False
            self.editing_track = -1
            self._editing_name_original = None
            self._editing_track_original = None
            return
        if self._sort_rect and self._sort_rect.collidepoint(pos):
            self.sort_mode = (self.sort_mode + 1) % len(self._SORT_LABELS)
            self.browser_scroll = 0
            self._clamp_browser_scroll()
            return
        # project name field
        if self._name_rect and self._name_rect.collidepoint(pos):
            self._begin_project_name_edit()
            return
        # lane column -> select track
        if self.lanes.collidepoint(pos):
            row = self._row_for_pos(my)
            if row >= 0:
                self._select_track(row)
            return
        # browser chips -> arm a component
        if self.browser.collidepoint(pos):
            for rect, cid in self._chip_rects:
                if rect.collidepoint(pos):
                    self.armed = cid
                    self.app.engine.preview_component(catalog.get(cid),
                                                      bpm=self.project.tempo)
                    return
            return
        # grid -> place / remove (or select tiles for a phrase in Connect mode)
        if self.grid.collidepoint(pos):
            if self.connect_mode:
                self._click_grid_connect(pos)
            else:
                self._click_grid(pos)

    def _cycle_effect(self, track):
        owned = [c["id"] for c in self.app.collection.owned_effects()]
        options = [None] + owned
        try:
            idx = options.index(track.effect_id)
        except ValueError:
            idx = 0
        track.effect_id = options[(idx + 1) % len(options)]
        self.project.touch()

    def _click_grid(self, pos):
        row = self._row_for_pos(pos[1])
        n_steps = self.project.total_steps
        step_w = self._step_w()
        col = int((pos[0] - self.grid.x + self.time_scroll) / step_w)
        if row < 0 or not (0 <= col < n_steps):
            return
        self._select_track(row)
        track = self.project.tracks[row]
        # remove if clicking on an existing clip span
        for clip in list(track.clips):
            length = synth.clip_length_steps(catalog.get(clip.comp_id))
            if clip.step <= col < clip.step + length:
                track.remove_at(clip.step, clip.comp_id)
                self.project.touch()
                return
        # otherwise place the armed component if this lane accepts it
        comp = catalog.get(self.armed) if self.armed is not None else None
        if comp is not None and track.accepts(comp):
            track.add(self.armed, col)
            self.project.touch()
            self.app.engine.preview_component(comp, bpm=self.project.tempo)
            return
        if self.armed is not None:
            self.armed = None
        self._flash(self._placement_prompt(track))

    def _remove_under_mouse(self, pos):
        if not self.grid.collidepoint(pos):
            return
        row = self._row_for_pos(pos[1])
        if row < 0:
            return
        n_steps = self.project.total_steps
        step_w = self._step_w()
        col = int((pos[0] - self.grid.x + self.time_scroll) / step_w)
        track = self.project.tracks[row]
        for clip in list(track.clips):
            length = synth.clip_length_steps(catalog.get(clip.comp_id))
            if clip.step <= col < clip.step + length:
                track.remove_at(clip.step, clip.comp_id)
                self.project.touch()
                if self.connect_mode:
                    # phrase indices may have shifted after healing
                    self._clear_link_selection()
                return

    # -- connected phrases ("Connect" tool) ----------------------------------
    def _clear_link_selection(self):
        self.link_track = -1
        self.link_anchor = None
        self.link_range = None
        self.link_editing = None

    def _link_selection_active(self):
        return (self.link_anchor is not None or self.link_range is not None
                or self.link_editing is not None)

    def _toggle_connect(self):
        self.connect_mode = not self.connect_mode
        self._clear_link_selection()
        if self.connect_mode:
            self.armed = None
            self._flash("Connect: click the first and last tile of a phrase, "
                        "then press Enter")
        else:
            self._flash("Connect tool off")

    def _link_track_obj(self):
        if 0 <= self.link_track < len(self.project.tracks):
            return self.project.tracks[self.link_track]
        return None

    def _phrase_member_step_at(self, track, phrase_index, col):
        """The member whose stretched segment covers grid column ``col``."""
        phrase = track.phrases[phrase_index]
        for j, ref in enumerate(phrase):
            if j + 1 < len(phrase):
                seg_end = phrase[j + 1][1]
            else:
                comp = catalog.get(ref[0])
                seg_end = ref[1] + max(1, synth.clip_length_steps(comp or {}))
            if ref[1] <= col < seg_end:
                return ref[1]
        return phrase[-1][1]

    def _click_grid_connect(self, pos):
        row = self._row_for_pos(pos[1])
        col = int((pos[0] - self.grid.x + self.time_scroll) / self._step_w())
        if row < 0 or not (0 <= col < self.project.total_steps):
            return
        self._select_track(row)
        track = self.project.tracks[row]
        if self._link_selection_active() and self.link_track != row:
            self._clear_link_selection()
            self._flash("Phrases live on one track. Starting over here")
        phrase_idx = track.phrase_index_covering(col)
        clip = next((c for c in track.clips
                     if c.step <= col < c.step + max(
                         1, synth.clip_length_steps(catalog.get(c.comp_id) or {}))),
                    None)
        if not self._link_selection_active():
            if phrase_idx >= 0:
                phrase = track.phrases[phrase_idx]
                self.link_track = row
                self.link_editing = phrase_idx
                self.link_range = (phrase[0][1], phrase[-1][1])
                self._flash("Phrase selected. Click tiles to move its ends, "
                            "or use Disconnect")
                return
            if clip is None:
                self._flash("Start the phrase on an existing tile")
                return
            self.link_track = row
            self.link_anchor = clip.step
            self._flash("First tile picked. Now click the last tile")
            return
        # a selection already lives on this track
        if clip is not None:
            target = clip.step
        elif phrase_idx >= 0:
            target = self._phrase_member_step_at(track, phrase_idx, col)
        else:
            self._flash("Click a tile to change the selection, Enter to "
                        "connect, Esc to cancel")
            return
        if self.link_range is None:
            if target == self.link_anchor:
                self._clear_link_selection()
                self._flash("Selection cleared")
                return
            lo, hi = sorted((self.link_anchor, target))
            self.link_anchor = None
            self.link_range = (lo, hi)
        else:
            lo, hi = self.link_range
            if abs(target - lo) < abs(target - hi):
                lo = target
            else:
                hi = target
            self.link_range = (min(lo, hi), max(lo, hi))
        count = len(track.clips_in_range(*self.link_range))
        if count < 2:
            self._flash("Select at least two tiles on the same track")
        else:
            self._flash("%d tiles selected. Press Enter (or Connect) to tie "
                        "them together" % count)

    def _commit_link(self):
        track = self._link_track_obj()
        if track is None or self.link_range is None:
            self._flash("Select at least two tiles on the same track")
            return
        lo, hi = self.link_range
        if len(track.clips_in_range(lo, hi)) < 2:
            self._flash("Select at least two tiles on the same track")
            return
        editing = self.link_editing
        if editing is not None and 0 <= editing < len(track.phrases):
            track.disconnect_phrase(editing)
        count = track.connect_range(lo, hi)
        self.project.touch()
        self._clear_link_selection()
        if editing is not None:
            self._flash("Phrase updated (%d tiles)" % count)
        else:
            self._flash("Connected %d tiles into one phrase" % count)

    def _disconnect_link(self):
        track = self._link_track_obj()
        if (track is not None and self.link_editing is not None
                and 0 <= self.link_editing < len(track.phrases)):
            track.disconnect_phrase(self.link_editing)
            self.project.touch()
            self._flash("Phrase disconnected. The tiles are still there")
        self._clear_link_selection()

    def _pill_action(self, action):
        if action == "connect":
            self._commit_link()
        elif action == "disconnect":
            self._disconnect_link()
        elif action == "cancel":
            self._clear_link_selection()
            self._flash("Selection cleared")

    # -- update -------------------------------------------------------------
    def update(self, dt):
        # Story mode never freezes merely because Bal opened the Maker.  The
        # studio is part of the same working day: appointments age, walk-ins
        # arrive, and deadlines continue while the player composes.
        if getattr(self.app, "profile_kind", None) == "story":
            story = self.app.screens.get("story")
            if story is not None:
                story.update_offscreen(dt)
        self._poll_export()
        if self.message_t > 0:
            self.message_t -= dt
        if not self.app.engine.is_playing() and self.play_btn.label == "Stop":
            self.play_btn.label = "Play"

    # -- draw ---------------------------------------------------------------
    def draw(self, surf):
        self._select_track(self.selected_track)
        ui.vertical_gradient(surf, surf.get_rect(), ui.PAPER, ui.PAPER_DK)
        self._draw_topbar(surf)
        self._draw_track_header(surf)
        self._draw_timeline_header(surf)
        self._draw_ruler(surf)
        self._draw_grid(surf)
        self._draw_lanes(surf)
        self._draw_browser(surf)
        self._draw_link_pill(surf)
        self._draw_story_status(surf)
        if self.track_menu_open:
            self._draw_track_menu(surf)
        self._draw_clip_tooltip(surf)
        if getattr(self, "dialog", None):
            self._draw_dialog(surf)
        if self.load_modal is not None:
            self._draw_load_modal(surf)
        if self.message_t > 0:
            self._draw_message(surf)


    def _draw_story_status(self, surf):
        """Keep the live shop legible without turning the Maker into a HUD."""
        if getattr(self.app, "profile_kind", None) != "story":
            return
        story = self.app.screens.get("story")
        if story is None:
            return
        status = story.maker_status()
        S = self.S
        P = self.P
        width = min(S(500), max(S(340), int(self.w * 0.34)))
        height = S(90)
        panel = pygame.Rect(self.w - width - P(20),
                            self.browser.y - height - P(18), width, height)
        urgent = bool(status.get("urgent"))
        alert = status.get("alert")
        alert_text = alert.get("text") if isinstance(alert, dict) else alert
        alert_level = alert.get("level", "normal") if isinstance(alert, dict) else "normal"
        if urgent or alert_level == "bad":
            edge = ui.ROSE
        elif alert_level == "warning":
            edge = (226, 173, 94)
        else:
            edge = ui.GRASS_DK if status.get("shop_open") else ui.INK_SOFT
        ui.draw_panel(surf, panel, fill=ui.CREAM, edge=edge,
                      radius=S(10), shadow=True)

        state = "SHOP OPEN" if status.get("shop_open") else "SHOP CLOSED"
        title = "DAY %s  -  %s  -  %s" % (
            status.get("day", 1), status.get("time", "--:--"), state)
        ui.pixel_text(surf, title, S(16), panel.x + S(14), panel.y + S(10),
                      color=ui.INK, bold=True)
        counts = "COUNTER %d  -  AWAY %d  -  ACTIVE %d  -  OFFERS %d" % (
            status.get("at_shop", 0), status.get("away", 0),
            status.get("orders", 0), status.get("offers", 0))
        ui.pixel_text_fit_box(surf, counts, S(13),
                              pygame.Rect(panel.x + S(14), panel.y + S(32),
                                          panel.w - S(28), S(22)),
                              color=ui.INK_SOFT, bold=True, min_size=S(10),
                              center=False)

        detail = status.get("delivery") or alert_text or status.get("due_text") or "The studio is quiet."
        if urgent or alert_level == "bad":
            color = ui.ROSE
        elif alert_level == "warning":
            color = (184, 126, 67)
        else:
            color = ui.GRASS_DK
        detail_rect = pygame.Rect(panel.x + S(12), panel.y + S(55),
                                  panel.w - S(24), S(24))
        ui.pixel_text_fit_box(surf, detail, S(13), detail_rect,
                              color=color, bold=True, min_size=9,
                              center=False)

    def _draw_clip_tooltip(self, surf):
        hc = getattr(self, "_hover_clip", None)
        if not hc or self.track_menu_open or getattr(self, "dialog", None) or self.load_modal is not None:
            return
        S = self.S
        comp, crect = hc
        rar = comp.get("rarity", "common")
        line1 = comp["name"]
        line2 = "%s . %s . %s" % (comp.get("type", "").title(),
                                  comp.get("track", ""), rar.title())
        f1 = ui.font(S(16), True)
        f2 = ui.font(S(13), False)
        tw = max(f1.size(line1)[0], f2.size(line2)[0]) + S(20)
        thg = S(46)
        tx = min(max(crect.centerx - tw // 2, S(6)), self.w - tw - S(6))
        ty = crect.y - thg - S(6)
        if ty < self.topbar.bottom + S(2):
            ty = crect.bottom + S(6)
        panel = pygame.Rect(tx, ty, tw, thg)
        ui.draw_panel(surf, panel, fill=ui.CREAM, radius=S(8), shadow=True)
        pygame.draw.rect(surf, tuple(comp.get("color", ui.GRASS)),
                         (panel.x + S(6), panel.y + S(8), S(5), thg - S(16)),
                         border_radius=2)
        ui.text(surf, line1, S(16), panel.x + S(18), panel.y + S(6), color=ui.INK)
        ui.text(surf, line2, S(13), panel.x + S(18), panel.y + S(26), color=ui.INK_SOFT)

    def _draw_topbar(self, surf):
        S = self.S
        P = self.P
        ui.draw_panel(surf, self.topbar, fill=ui.CREAM, radius=0, shadow=True,
                      sheen=False)
        mouse_pos = pygame.mouse.get_pos()

        for key, rect in self._top_groups.items():
            if key == "hint":
                continue
            ui.draw_panel(surf, rect,
                          fill=ui.PAPER if key == "song" else ui.PAPER_DK,
                          edge=ui.PAPER_EDGE, radius=S(10), shadow=False)

        song = self._top_groups["song"]
        ui.pixel_text(surf, "SONG", S(12), song.x + P(14), song.y + P(9),
                      color=ui.INK_SOFT)
        name = self.project.name + ("_" if self.editing_name else "")
        self._name_rect = pygame.Rect(song.x + P(10), song.y + P(24),
                                      song.w - P(20), S(42))
        ui.draw_panel(surf, self._name_rect,
                      fill=(255, 252, 240) if self.editing_name else ui.CREAM,
                      edge=ui.GRASS_DK if self.editing_name else ui.PAPER_EDGE,
                      radius=S(8), shadow=False)
        ui.pixel_text_fit_box(surf, name, S(25),
                              self._name_rect.inflate(-S(14), -S(5)),
                              color=ui.INK, min_size=S(15), center=False)

        info_y = song.bottom - P(27)
        facts = "%d BPM   -   %d BARS" % (self.project.tempo, self.project.bars)
        ui.pixel_text(surf, facts, S(13), song.x + P(14), info_y,
                      color=ui.INK_SOFT)
        if self.app.engine.is_playing():
            step = self.app.engine.playhead_fraction() * self.project.total_steps
            bar = int(step // synth.STEPS_PER_BAR) + 1
            beat = int((step % synth.STEPS_PER_BAR) // synth.STEPS_PER_BEAT) + 1
            position = "BAR %d  -  BEAT %d" % (bar, beat)
            ui.pixel_text(surf, position, S(13), song.right - P(14), info_y,
                          color=ui.GRASS_DK, right=True)

        captions = {
            "playback": "PLAYBACK", "project": "PROJECT",
            "tempo": "TEMPO", "bars": "SONG LENGTH", "tools": "EDIT TOOL",
        }
        for key, caption in captions.items():
            rect = self._top_groups[key]
            ui.pixel_text(surf, caption, S(11), rect.x + P(8), rect.y + P(5),
                          color=ui.INK_SOFT)

        for key, value in (("tempo", "%d BPM" % self.project.tempo),
                           ("bars", "%d BARS" % self.project.bars)):
            left = self.tempo_minus.rect if key == "tempo" else self.bars_minus.rect
            right = self.tempo_plus.rect if key == "tempo" else self.bars_plus.rect
            value_rect = pygame.Rect(left.right + P(3), left.y,
                                     max(S(32), right.x - left.right - P(6)), left.h)
            ui.pixel_text_fit_box(surf, value, S(15), value_rect,
                                  color=ui.INK, min_size=S(11))

        for rect, label, active, color in (
                (self._tiles_rect, "Tiles", not self.connect_mode, ui.GRASS),
                (self._connect_rect, "Connect  C", self.connect_mode, ui.PLUM)):
            hover = rect.collidepoint(mouse_pos)
            fill = color if active else (ui.CREAM if hover else ui.PAPER)
            edge = _dark(color) if active else ui.PAPER_EDGE
            ui.draw_panel(surf, rect, fill=fill, edge=edge, radius=S(7),
                          shadow=False, sheen=False)
            ui.pixel_text_fit_box(surf, label, S(14), rect.inflate(-S(8), -S(4)),
                                  color=ui.CREAM if active else ui.INK_SOFT,
                                  min_size=S(10))

        for button in self.transport:
            button.draw(surf, mouse_pos)
        if self._editing_locked():
            lock = pygame.Rect(song.right - S(178), song.y + P(7), S(164), S(23))
            ui.draw_panel(surf, lock, fill=(235, 215, 176), edge=ui.SUN,
                          radius=S(6), shadow=False)
            ui.pixel_text_fit_box(surf, "PLAYING. EDITING LOCKED", S(10),
                                  lock.inflate(-S(8), -S(3)), color=ui.INK,
                                  min_size=S(8), center=True)

    def _draw_timeline_header(self, surf):
        S = self.S
        header = self.timeline_header
        ui.draw_panel(surf, header, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                      radius=S(9), shadow=False)
        ui.pixel_text(surf, "ARRANGEMENT", S(15), header.x + S(12),
                      header.y + S(10), color=ui.INK)

    def _draw_ruler(self, surf):
        S = self.S
        ruler = self.ruler
        ui.draw_panel(surf, ruler, fill=ui.PAPER_DK, edge=ui.PAPER_EDGE,
                      radius=0, shadow=False, sheen=False)
        step_w = self._step_w()
        origin_x = self.grid.x - self.time_scroll
        for bar in range(self.project.bars):
            step = bar * synth.STEPS_PER_BAR
            x = int(origin_x + step * step_w)
            if x < ruler.x - S(30) or x > ruler.right:
                continue
            ui.pixel_text(surf, str(bar + 1), S(10), x + S(5), ruler.y + S(6),
                          color=ui.INK_SOFT)
            pygame.draw.line(surf, ui.GRID_BAR,
                             (x, ruler.bottom - S(5)), (x, ruler.bottom), 2)

    def _draw_grid(self, surf):
        S = self.S
        g = self.grid
        row_h = self.row_h
        n = len(self.project.tracks)
        n_steps = self.project.total_steps
        step_w = self._step_w()
        ox = g.x - self.time_scroll          # x origin after horizontal scroll

        prev_clip = surf.get_clip()
        surf.set_clip(g)

        # neutral fill for the whole timeline area (so empty space below the last
        # lane still reads as an intentional grid, not a gap)
        pygame.draw.rect(surf, ui.LANE_B, g)

        # lane row backgrounds (alternating), only those in view
        for i, tr in enumerate(self.project.tracks):
            ry = self._row_y(i)
            if ry + row_h < g.y or ry > g.bottom:
                continue
            base = ui.LANE_A if i % 2 == 0 else ui.LANE_B
            if i == self.selected_track:
                base = (246, 240, 224)
            pygame.draw.rect(surf, base, (g.x, ry, g.w, int(row_h) - 1))

        # bar + beat grid lines
        for s in range(n_steps + 1):
            x = int(ox + s * step_w)
            if x < g.x - 2 or x > g.right + 2:
                continue
            if s % synth.STEPS_PER_BAR == 0:
                pygame.draw.line(surf, ui.GRID_BAR, (x, g.y), (x, g.bottom), 2)
            elif s % synth.STEPS_PER_BEAT == 0:
                pygame.draw.line(surf, ui.GRID_LINE, (x, g.y), (x, g.bottom), 1)
        for i in range(n + 1):
            y = self._row_y(i)
            if g.y - 1 <= y <= g.bottom + 1:
                pygame.draw.line(surf, ui.GRID_LINE, (g.x, y), (g.right, y), 1)

        # selected-track highlight border
        sy = self._row_y(self.selected_track)
        pygame.draw.rect(surf, ui.GRASS_DK, (g.x, sy, g.w, int(row_h)), 2)

        # placed clips -- clean color-coded rectangles, no icons or names.
        # Clips tied into a phrase are drawn as ONE rounded body with soft
        # internal note divisions and a slur curve, so a connected phrase
        # reads as a single musical object.
        mx, my = pygame.mouse.get_pos()
        self._hover_clip = None
        for i, tr in enumerate(self.project.tracks):
            ry = self._row_y(i)
            if ry + row_h < g.y or ry > g.bottom:
                continue
            in_phrase = set()
            for phrase in tr.phrases:
                in_phrase.update((r[0], r[1]) for r in phrase)
            for clip in tr.clips:
                if (clip.comp_id, clip.step) in in_phrase:
                    continue
                comp = catalog.get(clip.comp_id)
                if comp is None:
                    continue
                length = synth.clip_length_steps(comp)
                cx = int(ox + clip.step * step_w) + 2
                cw = max(int(step_w * length) - 3, int(step_w) - 3)
                if cx + cw < g.x or cx > g.right:
                    continue
                crect = pygame.Rect(cx, ry + 4, cw, int(row_h) - 9)
                col = tuple(comp.get("color", ui.GRASS))
                if tr.muted:
                    col = _mix(col, (200, 196, 188), 0.6)
                pygame.draw.rect(surf, col, crect, border_radius=5)
                # subtle polish: top sheen, soft border, a darker tab on the left
                pygame.draw.line(surf, _light(col), (crect.x + 4, crect.y + 2),
                                 (crect.right - 4, crect.y + 2))
                pygame.draw.rect(surf, _dark(col), crect, 1, border_radius=5)
                pygame.draw.rect(surf, _dark(col),
                                 (crect.x, crect.y + 2, max(2, S(4)), crect.h - 4),
                                 border_radius=2)
                if crect.collidepoint(mx, my):
                    self._hover_clip = (comp, crect)
            for pi, phrase in enumerate(tr.phrases):
                self._draw_phrase(surf, i, tr, pi, phrase, ox, step_w, ry,
                                  int(row_h), (mx, my))
            self._draw_link_selection(surf, i, tr, ox, step_w, ry, int(row_h))

        # playhead with a soft glow band and a gently pulsing head
        if self.app.engine.is_playing():
            frac = self.app.engine.playhead_fraction()
            px = int(ox + frac * step_w * n_steps)
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 1000.0 * 8.0)
            band = pygame.Surface((S(14), g.h), pygame.SRCALPHA)
            pygame.draw.rect(band, (*ui.PLAYHEAD, 55), band.get_rect())
            surf.blit(band, (px - S(7), g.y))
            pygame.draw.line(surf, ui.PLAYHEAD, (px, g.y), (px, g.bottom), 2)
            pygame.draw.circle(surf, ui.PLAYHEAD, (px, g.y), S(5) + int(pulse * S(2)))
            pygame.draw.circle(surf, ui.CREAM, (px, g.y), max(1, S(2)))

        surf.set_clip(prev_clip)
        self._draw_scrollbars(surf)

    # -- connected-phrase drawing --------------------------------------------
    def _phrase_segments(self, phrase):
        """(comp, start_step, end_step) for every member, where a note lasts
        until the next member begins and the final one keeps its own length."""
        segs = []
        for j, ref in enumerate(phrase):
            comp = catalog.get(ref[0])
            if j + 1 < len(phrase):
                end = phrase[j + 1][1]
            else:
                end = ref[1] + max(1, synth.clip_length_steps(comp or {}))
            segs.append((comp, ref[1], max(ref[1] + 1, end)))
        return segs

    def _draw_phrase(self, surf, row, tr, pi, phrase, ox, step_w, ry, row_h, mp):
        S = self.S
        segs = self._phrase_segments(phrase)
        if not segs:
            return
        x0 = int(ox + segs[0][1] * step_w) + 2
        x1 = int(ox + segs[-1][2] * step_w) - 1
        if x1 < self.grid.x or x0 > self.grid.right:
            return
        base = tuple((segs[0][0] or {}).get("color", ui.GRASS))
        if tr.muted:
            base = _mix(base, (200, 196, 188), 0.6)
        body_col = _mix(base, ui.CREAM, 0.42)
        body = pygame.Rect(x0, ry + 4, max(x1 - x0, int(step_w) - 3), row_h - 9)
        pygame.draw.rect(surf, body_col, body, border_radius=7)
        # internal note / sound divisions, tinted by each member's colour
        for k, (comp, s0, s1) in enumerate(segs):
            col = tuple((comp or {}).get("color", ui.GRASS))
            if tr.muted:
                col = _mix(col, (200, 196, 188), 0.6)
            sx = int(ox + s0 * step_w) + (2 if k == 0 else 0)
            sw = int(ox + s1 * step_w) - sx - (3 if k == len(segs) - 1 else 0)
            seg = pygame.Rect(sx, ry + 4 + S(10), max(2, sw), row_h - 9 - S(13))
            tint = pygame.Surface(seg.size, pygame.SRCALPHA)
            tint.fill((*_mix(col, body_col, 0.35), 150))
            surf.blit(tint, seg.topleft)
            if k > 0:      # a soft bridge line where two tiles were joined
                pygame.draw.line(surf, _mix(_dark(base), body_col, 0.45),
                                 (sx, ry + 4 + S(8)), (sx, ry + row_h - 9),
                                 1)
                pygame.draw.circle(surf, _dark(col),
                                   (sx, ry + 4 + S(8)), max(2, S(3)))
            if comp is not None and seg.collidepoint(mp):
                self._hover_clip = (comp, seg)
        # one attack tab on the left, one border, one slur curve over the top
        pygame.draw.rect(surf, _dark(base), body, 1, border_radius=7)
        pygame.draw.rect(surf, _dark(base),
                         (body.x, body.y + 2, max(2, S(4)), body.h - 4),
                         border_radius=2)
        self._draw_slur(surf, body, _dark(base))

    def _draw_slur(self, surf, body, col):
        """A gentle legato arc across the top of a connected phrase."""
        S = self.S
        if body.w < S(18):
            return
        amp = min(S(6), body.h // 4)
        pts = []
        n = max(8, min(28, body.w // 6))
        for k in range(n + 1):
            u = k / float(n)
            x = body.x + S(5) + u * (body.w - S(10))
            y = body.y + S(3) + amp * (1.0 - math.sin(math.pi * u))
            pts.append((x, y))
        pygame.draw.aalines(surf, col, False, pts)

    def _draw_link_selection(self, surf, row, tr, ox, step_w, ry, row_h):
        """Pending selection glow / selected-phrase outline with end handles."""
        if not self.connect_mode or self.link_track != row:
            return
        S = self.S
        if self.link_range is not None:
            lo, hi = self.link_range
            end = hi + 1
            for c in tr.clips_in_range(lo, hi):
                if c.step == hi:
                    comp = catalog.get(c.comp_id)
                    end = max(end, hi + max(1, synth.clip_length_steps(comp or {})))
            x0 = int(ox + lo * step_w) + 1
            x1 = int(ox + end * step_w) - 1
            rect = pygame.Rect(x0, ry + 2, max(4, x1 - x0), row_h - 5)
            glow = pygame.Surface(rect.size, pygame.SRCALPHA)
            glow.fill((*ui.SUN, 60))
            surf.blit(glow, rect.topleft)
            pygame.draw.rect(surf, (226, 178, 88), rect, 2, border_radius=7)
            hs = max(4, S(7))
            for hx in (rect.x, rect.right - hs):
                pygame.draw.rect(surf, (226, 178, 88),
                                 (hx, rect.centery - hs // 2, hs, hs),
                                 border_radius=2)
        elif self.link_anchor is not None:
            comp = None
            for c in tr.clips:
                if c.step == self.link_anchor:
                    comp = catalog.get(c.comp_id)
                    break
            length = max(1, synth.clip_length_steps(comp or {}))
            x0 = int(ox + self.link_anchor * step_w) + 1
            x1 = int(ox + (self.link_anchor + length) * step_w) - 1
            rect = pygame.Rect(x0, ry + 2, max(4, x1 - x0), row_h - 5)
            pygame.draw.rect(surf, (226, 178, 88), rect, 2, border_radius=7)

    def _draw_link_pill(self, surf):
        """Put Connect guidance and actions in the arrangement toolbar."""
        self._pill_rects = []
        if getattr(self, "dialog", None) or self.timeline_header is None:
            return
        S = self.S
        header = self.timeline_header
        track = self._link_track_obj()
        buttons = []
        if self.connect_mode and self.link_range is not None and track is not None:
            count = len(track.clips_in_range(*self.link_range))
            if self.link_editing is not None:
                label = "Phrase selected  -  %d tiles" % count
                buttons = [("Apply", "connect"), ("Disconnect", "disconnect"),
                           ("Cancel", "cancel")]
            else:
                label = "%d tiles selected" % count
                buttons = [("Connect", "connect"), ("Cancel", "cancel")]
        elif self.connect_mode and self.link_anchor is not None:
            label = "First tile selected  -  choose the final tile"
            buttons = [("Cancel", "cancel")]
        elif self.connect_mode:
            label = "Click the first tile, then the last tile of the phrase"
        else:
            label = "Click to place or remove  -  choose Connect to join existing tiles"

        gap = S(6)
        right = header.right - S(8)
        button_h = header.h - S(12)
        mouse_pos = pygame.mouse.get_pos()
        built = []
        for text, action in reversed(buttons):
            width = max(S(72), ui.pixel_measure(text, S(13))[0] + S(20))
            rect = pygame.Rect(right - width, header.y + S(6), width, button_h)
            right = rect.x - gap
            built.append((rect, text, action))
        built.reverse()

        label_rect = pygame.Rect(header.x + S(118), header.y + S(6),
                                 max(S(80), right - header.x - S(126)), button_h)
        ui.pixel_text_fit_box(surf, label, S(13), label_rect,
                              color=ui.INK_SOFT, min_size=S(10), center=False)
        for rect, text, action in built:
            accent = {"connect": ui.GRASS, "disconnect": ui.ROSE,
                      "cancel": ui.PAPER}[action]
            hover = rect.collidepoint(mouse_pos)
            ui.draw_panel(surf, rect, fill=_light(accent) if hover else accent,
                          radius=S(7), shadow=False, sheen=False)
            ui.pixel_text_fit_box(surf, text, S(13), rect.inflate(-S(8), -S(4)),
                                  color=ui.CREAM if action != "cancel" else ui.INK_SOFT,
                                  min_size=S(10))
            self._pill_rects.append((rect, action))

    def _draw_scrollbars(self, surf):
        S = self.S
        max_v = self._max_scroll()
        if max_v > 0:
            ui.draw_panel(surf, self.vbar, fill=ui.PAPER_DK, radius=S(4), shadow=False)
            frac = self.grid.h / max(1.0, self._content_h())
            th = max(S(30), int(self.vbar.h * frac))
            ty = self.vbar.y + int((self.vbar.h - th) * (self.track_scroll / max_v))
            ui.draw_panel(surf, pygame.Rect(self.vbar.x, ty, self.vbar.w, th),
                          fill=ui.GRASS, radius=S(4), shadow=False)
        max_h = self._max_time_scroll()
        if max_h > 0:
            ui.draw_panel(surf, self.hbar, fill=ui.PAPER_DK, radius=S(4), shadow=False)
            frac = self.grid.w / max(1.0, self._content_w())
            tw = max(S(30), int(self.hbar.w * frac))
            tx = self.hbar.x + int((self.hbar.w - tw) * (self.time_scroll / max_h))
            ui.draw_panel(surf, pygame.Rect(tx, self.hbar.y, tw, self.hbar.h),
                          fill=ui.GRASS, radius=S(4), shadow=False)

    def _scrollbar_drag(self, my_or_mx):
        if self._drag_bar == "v":
            max_v = self._max_scroll()
            if max_v <= 0:
                return
            rel = (my_or_mx - self.vbar.y) / max(1, self.vbar.h)
            self.track_scroll = int(rel * max_v)
            self._clamp_scroll()
        elif self._drag_bar == "h":
            max_h = self._max_time_scroll()
            if max_h <= 0:
                return
            rel = (my_or_mx - self.hbar.x) / max(1, self.hbar.w)
            self.time_scroll = int(rel * max_h)
            self._clamp_time_scroll()

    def _draw_lanes(self, surf):
        S = self.S
        mouse_pos = pygame.mouse.get_pos()
        self._track_btn_rects = []
        panel = pygame.Rect(self.lanes.x, self.grid.y - S(2),
                            self.lanes.w, self.grid.h + S(4))
        ui.draw_panel(surf, panel, fill=ui.PAPER_DK, radius=S(8), shadow=False)
        previous_clip = surf.get_clip()
        surf.set_clip(self.lanes)
        for i, track in enumerate(self.project.tracks):
            row_y = self._row_y(i)
            if row_y + self.row_h < self.grid.y or row_y > self.grid.bottom:
                continue
            row_h = int(self.row_h)
            selected = i == self.selected_track
            row_rect = pygame.Rect(self.lanes.x + S(3), row_y + S(3),
                                   self.lanes.w - S(6), row_h - S(6))
            ui.draw_panel(surf, row_rect,
                          fill=ui.CREAM if selected else ui.PAPER,
                          edge=ui.GRASS if selected else ui.PAPER_EDGE,
                          radius=S(8), shadow=False, sheen=False)
            family_color = _family_color(track.kind)
            pygame.draw.rect(surf, family_color,
                             (row_rect.x, row_rect.y + S(5), S(5),
                              row_rect.h - S(10)), border_radius=S(2))

            name_x = row_rect.x + S(13)
            action_y = row_rect.y + S(8)
            delete_rect = pygame.Rect(row_rect.right - S(28), action_y, S(22), S(22))
            duplicate_rect = pygame.Rect(delete_rect.x - S(48), action_y, S(44), S(22))
            mute_rect = pygame.Rect(duplicate_rect.x - S(48), action_y, S(44), S(22))
            name_color = ui.GRASS_DK if selected else ui.INK
            name = track.name + ("_" if self.editing_track == i else "")
            name_rect = pygame.Rect(name_x, row_rect.y + S(7),
                                    max(S(45), mute_rect.x - name_x - S(6)), S(22))
            ui.pixel_text_fit_box(surf, name, S(17), name_rect,
                                  color=name_color, min_size=S(11), center=False)
            ui.pixel_text(surf, track.kind.upper(), S(10), name_x,
                          row_rect.y + S(31), color=_dark(family_color))
            self._track_btn_rects.append((name_rect, ("name", i)))

            actions = (
                (mute_rect, "Mute", track.muted, ui.ROSE, "mute"),
                (duplicate_rect, "Copy", False, ui.PAPER, "dup"),
                (delete_rect, "X", False, ui.PAPER, "del"),
            )
            for rect, label, active, color, action in actions:
                hover = rect.collidepoint(mouse_pos)
                fill = color if active else (ui.CREAM if hover else ui.PAPER_DK)
                ui.draw_panel(surf, rect, fill=fill,
                              edge=_dark(color) if active else ui.PAPER_EDGE,
                              radius=S(6), shadow=False, sheen=False)
                ui.pixel_text_fit_box(
                    surf, label, S(11 if action in ("mute", "dup") else 15),
                    rect.inflate(-S(4), -S(3)),
                    color=(ui.CREAM if active else
                           ((196, 110, 100) if action == "del" else ui.INK_SOFT)),
                    min_size=S(9))
                self._track_btn_rects.append((rect, (action, i)))

            bottom_y = row_rect.bottom - S(27)
            effect_rect = pygame.Rect(name_x, bottom_y, S(82), S(20))
            effect = catalog.get(track.effect_id) if track.effect_id else None
            ui.draw_panel(surf, effect_rect,
                          fill=ui.PLUM if effect else ui.PAPER_DK,
                          radius=S(6), shadow=False, sheen=False)
            effect_label = ("FX  " + effect["name"].split()[0]) if effect else "FX  NONE"
            ui.pixel_text_fit_box(surf, effect_label, S(10),
                                  effect_rect.inflate(-S(5), -S(2)),
                                  color=ui.CREAM if effect else ui.INK_SOFT,
                                  min_size=S(8))
            self._track_btn_rects.append((effect_rect, ("fx", i)))
            volume_label_x = effect_rect.right + S(7)
            ui.pixel_text(surf, "VOL", S(9), volume_label_x, bottom_y + S(5),
                          color=ui.INK_SOFT)
            if i < len(self.lane_sliders):
                slider = self.lane_sliders[i]
                slider.rect.x = volume_label_x + S(28)
                slider.rect.width = max(S(24), row_rect.right - S(12) - slider.rect.x)
                slider.rect.y = bottom_y + S(6)
                slider.value = track.volume
                slider.draw(surf, mouse_pos)
        surf.set_clip(previous_clip)

    def _draw_track_header(self, surf):
        S = self.S
        header = self.lane_header
        mouse_pos = pygame.mouse.get_pos()
        ui.draw_panel(surf, header, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                      radius=S(9), shadow=False)
        ui.pixel_text(surf, "TRACKS", S(15), header.x + S(12), header.y + S(10),
                      color=ui.INK)
        ui.pixel_text(surf, "%d lanes" % len(self.project.tracks), S(10),
                      header.x + S(12), header.y + S(34), color=ui.INK_SOFT)
        add_rect = pygame.Rect(header.right - S(104), header.y + S(9), S(94), S(30))
        hover = add_rect.collidepoint(mouse_pos)
        ui.draw_panel(surf, add_rect,
                      fill=_light(ui.GRASS) if hover else ui.GRASS,
                      radius=S(7), shadow=False, sheen=False)
        ui.pixel_text_fit_box(surf, "+ Add track", S(13),
                              add_rect.inflate(-S(8), -S(4)),
                              color=ui.CREAM, min_size=S(10))
        self._add_track_rect = add_rect

    def _draw_track_menu(self, surf):
        S = self.S
        mouse_pos = pygame.mouse.get_pos()
        self._menu_rects = []
        from ..music.project import FAMILIES
        row_h = S(40)
        menu_w = min(S(240), self.lane_header.w)
        menu_h = row_h * len(FAMILIES) + S(42)
        x = self.lane_header.x
        y = self.lane_header.bottom + S(4)
        panel = pygame.Rect(x, y, menu_w, menu_h)
        ui.draw_panel(surf, panel, fill=ui.CREAM, radius=S(10), shadow=True)
        ui.pixel_text(surf, "ADD A TRACK", S(13), x + S(12), y + S(10),
                      color=ui.INK_SOFT)
        for index, (label, kind) in enumerate(FAMILIES):
            rect = pygame.Rect(x + S(8), y + S(34) + index * row_h,
                               menu_w - S(16), row_h - S(5))
            hover = rect.collidepoint(mouse_pos)
            ui.draw_panel(surf, rect,
                          fill=ui.CREAM if hover else ui.PAPER,
                          edge=_family_color(kind) if hover else ui.PAPER_EDGE,
                          radius=S(7), shadow=False, sheen=False)
            pygame.draw.rect(surf, _family_color(kind),
                             (rect.x + S(7), rect.y + S(6), S(6), rect.h - S(12)),
                             border_radius=S(2))
            ui.pixel_text_fit_box(
                surf, label, S(15),
                pygame.Rect(rect.x + S(22), rect.y, rect.w - S(28), rect.h),
                color=ui.INK, min_size=S(11), center=False)
            self._menu_rects.append((rect, kind))

    def _draw_browser(self, surf):
        S = self.S
        browser = self.browser
        ui.draw_panel(surf, browser, fill=ui.CREAM, radius=0, shadow=True,
                      sheen=False)
        track = self.project.tracks[self.selected_track]
        kind = track.kind
        owned = self._browser_items(track)
        total_owned = len(self._owned_for(track))

        controls_w = min(S(390), int(browser.w * 0.38))
        left = pygame.Rect(browser.x + S(16), browser.y + S(9),
                           browser.w - controls_w - S(42), S(58))
        ui.pixel_text(surf, "SOUND DRAWER", S(11), left.x, left.y,
                      color=ui.INK_SOFT)
        title_rect = pygame.Rect(left.x, left.y + S(14), left.w, S(25))
        ui.pixel_text_fit_box(surf, track.name, S(20), title_rect,
                              color=ui.INK, min_size=S(13), center=False)
        armed = catalog.get(self.armed) if self.armed else None
        if armed is not None and track.accepts(armed):
            instruction = "Selected: %s  -  click the timeline to place" % armed["name"]
            instruction_color = ui.GRASS_DK
        else:
            instruction = "%d of %d sounds shown  -  choose one to place" % (
                len(owned), total_owned)
            instruction_color = ui.INK_SOFT
        instruction_rect = pygame.Rect(left.x, left.y + S(39), left.w, S(18))
        ui.pixel_text_fit_box(surf, instruction, S(12), instruction_rect,
                              color=instruction_color, min_size=S(9), center=False)

        controls_x = browser.right - controls_w - S(16)
        controls_y = browser.y + S(17)
        sort_w = min(S(145), int(controls_w * 0.36))
        self._sort_rect = pygame.Rect(controls_x, controls_y, sort_w, S(34))
        self._search_rect = pygame.Rect(
            self._sort_rect.right + S(8), controls_y,
            browser.right - S(16) - self._sort_rect.right - S(8), S(34))
        ui.draw_panel(surf, self._sort_rect, fill=ui.PAPER, radius=S(7),
                      shadow=False)
        ui.pixel_text_fit_box(surf, "Sort: %s" % self._SORT_LABELS[self.sort_mode],
                              S(12), self._sort_rect.inflate(-S(7), -S(3)),
                              color=ui.INK, min_size=S(9))
        ui.draw_panel(surf, self._search_rect,
                      fill=(255, 252, 240) if self.searching else ui.PAPER,
                      edge=ui.GRASS_DK if self.searching else ui.BTN_EDGE,
                      radius=S(7), shadow=False)
        if self.search or self.searching:
            shown = self.search + ("_" if self.searching else "")
            search_color = ui.INK
        else:
            shown = "Search sounds..."
            search_color = ui.INK_SOFT
        ui.pixel_text_fit_box(surf, shown, S(12),
                              self._search_rect.inflate(-S(10), -S(4)),
                              color=search_color, min_size=S(9), center=False)

        area, chip_w, chip_h, gap, per_row = self._browser_geometry()
        self._browser_area = area
        self._clamp_browser_scroll(track)
        previous_clip = surf.get_clip()
        surf.set_clip(area)
        self._chip_rects = []
        mouse_pos = pygame.mouse.get_pos()
        for index, component in enumerate(owned):
            row = index // per_row
            column = index % per_row
            x = area.x + column * (chip_w + gap)
            y = area.y + row * (chip_h + gap) - self.browser_scroll
            rect = pygame.Rect(x, y, chip_w, chip_h)
            if not rect.colliderect(area):
                continue
            self._chip_rects.append((rect, component["id"]))
            armed_now = component["id"] == self.armed
            component_color = tuple(component.get("color", ui.GRASS))
            hover = rect.collidepoint(mouse_pos)
            ui.draw_panel(surf, rect,
                          fill=ui.CREAM if armed_now or hover else ui.PAPER,
                          edge=ui.GRASS_DK if armed_now else ui.BTN_EDGE,
                          radius=S(8), shadow=False, sheen=False)
            icon_rect = pygame.Rect(rect.x + S(5), rect.y + S(5),
                                    chip_h - S(10), chip_h - S(10))
            pygame.draw.rect(surf, _mix(component_color, ui.CREAM, 0.62),
                             icon_rect, border_radius=S(6))
            draw_icon(surf, icon_rect.centerx, icon_rect.centery,
                      icon_rect.h * 0.34, component_color,
                      component.get("icon", "note"), 0.0)
            label_rect = pygame.Rect(icon_rect.right + S(7), rect.y + S(3),
                                     rect.right - icon_rect.right - S(12),
                                     rect.h - S(6))
            ui.pixel_text_fit_box(surf, component["name"], S(13), label_rect,
                                  color=ui.INK, min_size=S(9), center=False)
            if armed_now:
                pygame.draw.circle(surf, ui.GRASS_DK,
                                   (rect.right - S(9), rect.centery), S(3))
        surf.set_clip(previous_clip)

        if not owned:
            ui.pixel_text(surf, "No %s collected yet. Explore to find some."
                          % _TYPE_LABEL.get(kind, kind), S(16),
                          area.x, area.y + S(10), color=ui.INK_SOFT)

    _RARITY_RANK = {"secret": 0, "rare": 1, "uncommon": 2, "common": 3}
    _SORT_LABELS = ["Name", "Rarity", "Recent"]

    def _browser_items(self, track):
        """Owned components for this track, after the search filter and sort."""
        items = self._owned_for(track)
        q = self.search.strip().lower()
        if q:
            items = [c for c in items if q in c["name"].lower()]
        if self.sort_mode == 0:
            items = sorted(items, key=lambda c: c["name"].lower())
        elif self.sort_mode == 1:
            items = sorted(items, key=lambda c: (
                self._RARITY_RANK.get(c.get("rarity", "common"), 3), c["name"].lower()))
        else:
            items = sorted(items, key=lambda c: -self.app.collection.discovery_order(c["id"]))
        return items

    def _owned_for(self, track):
        return self.app.collection.owned_on_track(track.kind)

    def _draw_message(self, surf):
        S = self.S
        alpha = min(1.0, self.message_t / 0.6)
        max_width = min(self.w - S(40), S(620))
        font_size = ui.fit_size(self.message, S(16), max_width - S(28),
                                min_size=S(10), bold=True,
                                measure=ui.pixel_measure)
        image = ui.pixel_render(self.message, font_size, ui.INK)
        box = pygame.Surface((min(max_width, image.get_width() + S(28)),
                              image.get_height() + S(14)), pygame.SRCALPHA)
        pygame.draw.rect(box, (*ui.SUN, int(240 * alpha)), box.get_rect(),
                         border_radius=S(8))
        pygame.draw.rect(box, (*ui.INK, int(150 * alpha)), box.get_rect(), 1,
                         border_radius=S(8))
        box.blit(image, image.get_rect(center=box.get_rect().center))
        box.set_alpha(int(255 * alpha))
        surf.blit(box, box.get_rect(center=(self.w // 2,
                                            self.browser.y - S(24))))

def _short(path):
    """A truthful, compact view of the actual export path."""
    p = os.path.abspath(path)
    if len(p) <= 58:
        return p
    return "..." + p[-55:]


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


_FAMILY_COLOR = {
    "melody": (255, 196, 120), "chords": (255, 158, 150), "bass": (206, 188, 130),
    "drums": (210, 180, 140), "rhythms": (232, 196, 120), "loops": (150, 200, 230),
    "ambience": (180, 192, 232),
}


def _family_color(kind):
    return _FAMILY_COLOR.get(kind, (200, 200, 190))


def _dark(c):
    return tuple(max(0, int(v * 0.55)) for v in c)


def _light(c):
    return tuple(min(255, int(v + 50)) for v in c)
