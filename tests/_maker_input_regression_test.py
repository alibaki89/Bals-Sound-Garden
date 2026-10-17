"""Focused headless regressions for Music Maker input and window behavior."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
import traceback
import pygame

FAILS = []


def check(label, condition):
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {label}")
    if not condition:
        FAILS.append(label)


class StubEngine:
    def __init__(self):
        self.playing = False
        self.previewed = []

    def is_playing(self):
        return self.playing

    def stop_music(self):
        self.playing = False

    def play_project(self, project, samples=None, loop=False):
        self.playing = True

    def preview_component(self, comp, bpm=100):
        if comp is not None:
            self.previewed.append(comp["id"])

    def invalidate(self):
        pass

    def playhead_fraction(self):
        return 0.0


class StubCollection:
    def owned_on_track(self, track):
        from cat_society.components import catalog
        return [c for c in catalog.ALL
                if c.get("starter") and c.get("track") == track]

    def owned_effects(self):
        return []

    def discovery_order(self, cid):
        return 0


class StubProjects:
    def list_projects(self):
        return []

    def save(self, project):
        return project


class StubApp:
    def __init__(self):
        self.window = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self.engine = StubEngine()
        self.collection = StubCollection()
        self.projects = StubProjects()
        self.pending_project = None
        self.goto_calls = []

    def goto(self, name):
        self.goto_calls.append(name)

    def refresh_projects(self):
        return []


def mouse_down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def mouse_up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def click(screen, pos):
    screen.handle_event(mouse_down(pos))
    screen.handle_event(mouse_up(pos))


def render(screen, app):
    screen.draw(app.window)


def chip_center(screen, cid):
    for rect, comp_id in screen._chip_rects:
        if comp_id == cid:
            return rect.center
    raise AssertionError(f"chip {cid} is not visible")


def track_name_center(screen, idx):
    for rect, action in screen._track_btn_rects:
        if action == ("name", idx):
            return rect.center
    raise AssertionError(f"track name {idx} is not visible")


def grid_center(screen, row, col):
    return (int(screen.grid.x + col * screen._step_w() - screen.time_scroll
                + screen._step_w() * 0.5),
            int(screen._row_y(row) + screen.row_h * 0.5))


def run_maker_tests():
    from cat_society.screens.maker import MakerScreen

    app = StubApp()
    maker = MakerScreen(app)
    maker.on_enter()
    render(maker, app)

    melody_id = "mb_c4"

    print("\n--- Maker input flow ---")
    click(maker, chip_center(maker, melody_id))
    check("clicking a browser component arms it", maker.armed == melody_id)

    before = maker.project.clip_count()
    click(maker, grid_center(maker, 0, 2))
    check("clicking a compatible grid cell places a clip",
          maker.project.clip_count() == before + 1)

    render(maker, app)
    click(maker, track_name_center(maker, 0))
    check("clicking a track name enters editing", maker.editing_track == 0)

    maker.project.modified = 0.0
    maker.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_x,
                                          unicode="x", mod=0))
    maker.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN,
                                          unicode="\r", mod=0))
    check("finishing a track rename touches the project",
          maker.editing_track == -1 and maker.project.modified > 0.0)

    render(maker, app)
    click(maker, track_name_center(maker, 0))

    maker.armed = None
    click(maker, chip_center(maker, melody_id))
    check("browser click ends track editing in the same click",
          maker.editing_track == -1 and maker.armed == melody_id)

    render(maker, app)
    click(maker, track_name_center(maker, 0))
    before = maker.project.clip_count()
    click(maker, grid_center(maker, 0, 5))
    check("grid click ends track editing and places in the same click",
          maker.editing_track == -1 and maker.project.clip_count() == before + 1)

    render(maker, app)
    click(maker, maker._name_rect.center)
    check("clicking the project name enters editing", maker.editing_name)
    play_center = maker.play_btn.rect.center
    click(maker, play_center)
    check("transport click exits name editing without a second click",
          not maker.editing_name and app.engine.is_playing())
    app.engine.stop_music()

    maker._select_track(0)
    maker.armed = melody_id
    render(maker, app)
    drum_row = 2
    lane_select_pos = (maker.lanes.x + maker.S(18),
                       int(maker._row_y(drum_row) + maker.row_h * 0.50))
    click(maker, lane_select_pos)
    check("switching to an incompatible track clears the armed component",
          maker.selected_track == drum_row and maker.armed is None)

    maker.message = ""
    click(maker, grid_center(maker, drum_row, 7))
    check("empty invalid placement gives useful feedback",
          "drum sound" in maker.message.lower() and maker.message_t > 0)

    # A return to the Maker must clean focus/drag state but keep the arrangement.
    project_before = maker.project
    clips_before = maker.project.clip_count()
    maker.editing_name = True
    maker._editing_name_original = maker.project.name
    maker.searching = True
    maker.track_menu_open = True
    maker._drag_bar = "v"
    maker.transport[0]._down = True
    maker.lane_sliders[0]._drag = True
    maker.on_enter()
    check("re-entering Maker preserves the project object",
          maker.project is project_before)
    check("re-entering Maker preserves clips",
          maker.project.clip_count() == clips_before)
    check("re-entering Maker clears transient focus and drag state",
          not maker.editing_name and maker.editing_track == -1
          and not maker.searching and not maker.track_menu_open
          and maker._drag_bar is None
          and all(not b._down for b in maker.transport)
          and all(not s._drag for s in maker.lane_sliders))

    # Only rendered chips should be hit-testable, and scrolling is bounded.
    render(maker, app)
    visible = list(maker._chip_rects)
    check("browser hit-testing contains only visible chips",
          all(maker._browser_area.colliderect(rect) for rect, _ in visible))
    maker.browser_scroll = 10**6
    maker._clamp_browser_scroll()
    check("browser scrolling is clamped to content",
          maker.browser_scroll == maker._max_browser_scroll())


def run_window_tests():
    from cat_society.app import App, _pick_window_size
    from cat_society.components import catalog

    print("\n--- Window behavior ---")
    small = _pick_window_size((800, 600))
    check("initial size never exceeds a small desktop",
          small[0] <= 800 and small[1] <= 600)

    app = App()
    check("windowed mode is the default", app.fullscreen is False)
    check("default display is not fullscreen",
          not bool(app.window.get_flags() & pygame.FULLSCREEN))

    app.goto("maker")
    maker = app.current
    project_before = maker.project
    comp = catalog.get("mb_c4")
    maker.project.tracks[0].add(comp["id"], 3)
    clips_before = maker.project.clip_count()
    windowed_size = app.window.get_size()

    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11,
                                        unicode="", mod=0))
    first_toggle = (app.fullscreen and app.current is maker
                    and maker.project is project_before
                    and maker.project.clip_count() == clips_before)
    app.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F11,
                                        unicode="", mod=0))
    second_toggle = (not app.fullscreen and app.current is maker
                     and maker.project is project_before
                     and maker.project.clip_count() == clips_before
                     and app._windowed_size == windowed_size
                     and (app.window.get_size() == windowed_size or app._headless))
    check("F11 toggles fullscreen without losing the active project",
          first_toggle and second_toggle)

    app.running = True
    app.handle_event(pygame.event.Event(pygame.QUIT))
    check("pygame.QUIT still closes the application", app.running is False)
    app._shutdown()


def main():
    pygame.init()
    run_maker_tests()
    run_window_tests()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n!!! UNCAUGHT EXCEPTION !!!")
        traceback.print_exc()
        FAILS.append("uncaught exception")

    print("\n" + "=" * 58)
    if FAILS:
        print(f"RESULT: {len(FAILS)} FAILURE(S)")
        for failure in FAILS:
            print("  - " + failure)
        sys.exit(1)
    print("RESULT: ALL REGRESSION TESTS PASSED")
