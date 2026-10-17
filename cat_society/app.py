"""Application shell for Bal's Sound Garden.

The :class:`App` owns the single pygame display, the audio engine and the
shared player state (collected components, saved projects).  It hosts the
screens -- menu, explore, music maker and your-music -- and switches between
them.  Each screen exposes ``on_enter`` / ``handle_event`` / ``update`` /
``draw`` and reaches shared state through ``self.app``.

Run with ``python main.py`` or ``python -m cat_society.app``.
"""

import os
import pygame

from . import config
from . import settings
from . import paths
from .audio.engine import AudioEngine
from .audio import samples
from .audio import sfx
from .components.collection import Collection
from .world.state import WorldState
from .music import store
from .logging_utils import get_logger

_LOG = get_logger("app")

from .screens.menu import MenuScreen
from .screens.explore import ExploreScreen
from .screens.story import StoryScreen
from .screens.maker import MakerScreen
from .screens.your_music import YourMusicScreen


# Default windowed size.  We try to fit the desktop but never go below this.
MIN_W, MIN_H = 1024, 640
MARGIN = 80          # leave a little room around the window on the desktop


def _pick_window_size(desktop_size=None):
    """Choose a comfortable windowed size that fits the current desktop."""
    if desktop_size is None:
        try:
            desktop_size = pygame.display.get_desktop_sizes()[0]
        except Exception:
            desktop_size = (1600, 900)
    dw, dh = desktop_size
    if dw < 320 or dh < 320:
        dw, dh = 1600, 900
    # Respect the preferred minimum only when the desktop can actually fit it.
    # On small displays, fitting inside the desktop is more important than
    # forcing a nominal minimum that would push the title bar off-screen.
    avail_w = max(320, dw - MARGIN)
    avail_h = max(320, dh - MARGIN)
    w = min(1600, avail_w)
    h = min(1000, avail_h)
    if avail_w >= MIN_W:
        w = max(MIN_W, w)
    if avail_h >= MIN_H:
        h = max(MIN_H, h)
    w = min(w, dw)
    h = min(h, dh)
    return w, h


class App:
    def __init__(self):
        pygame.init()
        try:
            pygame.key.set_repeat(0)        # no key auto-repeat for typing fields
        except Exception:
            pass

        # -- display ------------------------------------------------------
        # Launch as a normal decorated window.  PyInstaller's --windowed flag
        # only hides the console; fullscreen remains an explicit F11 choice.
        self._headless = os.environ.get("SDL_VIDEODRIVER") == "dummy"
        self._windowed_size = _pick_window_size()
        # Keep one presentation scale for the whole session. Resizing or F11
        # changes the visible field, not Bal/UI pixel size.
        self._presentation_height = self._windowed_size[1]
        self.fullscreen = False
        self._set_display(False)
        pygame.display.set_caption(config.TITLE)

        self.clock = pygame.time.Clock()
        self.running = True

        # -- audio --------------------------------------------------------
        settings.load()
        self.engine = AudioEngine()
        try:
            sfx.init()
        except Exception:
            pass

        # -- shared player state -----------------------------------------
        # Creative keeps the historical save/ layout. Story is routed through
        # save/story_profile so discoveries, sprouts and songs never leak into
        # the sandbox. Settings and imported samples remain shared.
        paths.set_active_profile(None)
        self.profile_kind = "creative"
        self.story_profile_dir = os.path.join(paths.base_save_dir(), "story_profile")

        # the garden remembers itself: one seed, rolled once, kept forever,
        # plus everything the player's music has changed in the world
        self.world_state = WorldState()
        config.WORLD_SEED = self.world_state.seed

        self.collection = Collection()
        self.collection.load()

        self.samples = samples          # module-level user-sample registry
        self.samples.load_all()

        self.projects = store           # project save/load module
        self.project_list = []
        self.project_warnings = []
        self.refresh_projects()

        self.pending_project = None     # set by Your Music -> edit, read by maker

        # -- screens ------------------------------------------------------
        self.screens = {
            "menu": MenuScreen(self),
            "explore": ExploreScreen(self),
            "story": StoryScreen(self),
            "maker": MakerScreen(self),
            "your_music": YourMusicScreen(self),
        }
        self.current = None
        self.goto("menu")

    # ---------------------------------------------------------------- state
    def story_exists(self):
        return os.path.exists(os.path.join(self.story_profile_dir, "story.json"))

    def _reload_profile(self, kind, profile_dir=None):
        """Save the old profile, switch path routing, then reload all owned data."""
        try:
            if not self.collection.save():
                _LOG.error("Could not save the active collection before profile switch")
        except Exception:
            _LOG.exception("Unexpected collection save failure before profile switch")
        try:
            self.engine.stop_music()
        except Exception:
            pass
        paths.set_active_profile(profile_dir)
        self.profile_kind = kind
        self.world_state = WorldState()
        config.WORLD_SEED = self.world_state.seed
        self.collection = Collection()
        self.samples = samples
        self.projects = store
        self.pending_project = None
        self.refresh_projects()
        # Overlays keep an app reference and read app.collection dynamically.
        for key in ("explore", "story"):
            sc = self.screens.get(key) if hasattr(self, "screens") else None
            if sc is not None:
                sc.rebuild_world()
        mk = self.screens.get("maker") if hasattr(self, "screens") else None
        if mk is not None:
            mk.project = None

    def open_creative_profile(self):
        if self.profile_kind != "creative" or paths.active_profile() is not None:
            self._reload_profile("creative", None)

    def start_story(self, new=False):
        if new:
            try:
                import shutil
                shutil.rmtree(self.story_profile_dir)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        self._reload_profile("story", self.story_profile_dir)
        self.goto("story")

    def exit_story_to_menu(self):
        self.open_creative_profile()
        self.goto("menu")

    def refresh_projects(self):
        """Reload saved projects and retain non-blocking parse warnings."""
        try:
            self.project_list = self.projects.list_projects()
            warnings = self.projects.consume_warnings()
            if warnings:
                self.project_warnings.extend(warnings)
                self.project_warnings = self.project_warnings[-20:]
        except Exception:
            _LOG.exception("Could not refresh saved projects")
            self.project_list = []
        return self.project_list

    def pop_project_warning(self):
        return self.project_warnings.pop(0) if self.project_warnings else None

    def reset_progress(self):
        """Delete Creative and Story gameplay safely, then reload Creative.

        Settings, imported samples and exported WAV files are shared user data
        and are deliberately kept. The method does not call save on the old
        profile after deletion, which previously recreated half-reset files and
        left screens pointing at stale objects.
        """
        import shutil

        try:
            self.engine.stop_music()
        except Exception:
            pass

        root = paths.base_save_dir()
        paths.set_active_profile(None)
        for filename in ("world.json", "collection.json"):
            try:
                os.remove(os.path.join(root, filename))
            except FileNotFoundError:
                pass
            except OSError:
                _LOG.exception("Could not remove progress file %s", filename)
        for folder in (os.path.join(root, "projects"), self.story_profile_dir):
            try:
                shutil.rmtree(folder)
            except FileNotFoundError:
                pass
            except OSError:
                _LOG.exception("Could not remove progress folder %s", folder)

        self.profile_kind = "creative"
        self.world_state = WorldState()
        config.WORLD_SEED = self.world_state.seed
        self.collection = Collection()
        self.samples = samples
        self.projects = store
        self.pending_project = None
        self.refresh_projects()

        for key in ("explore", "story"):
            screen = self.screens.get(key)
            if screen is not None:
                screen.rebuild_world()
        maker = self.screens.get("maker")
        if maker is not None:
            maker.project = None
            maker.load_modal = None
        music = self.screens.get("your_music")
        if music is not None:
            # It will rebuild its cards the next time it is opened.
            if hasattr(music, "_playing_id"):
                music._playing_id = None
        menu = self.screens.get("menu")
        if menu is not None:
            menu.dialog = None
            menu._build()
        pygame.mouse.set_visible(True)
        return True

    # --------------------------------------------------------------- screens
    def goto(self, name):
        # Inside a story profile, the Maker and Your Music return to the island
        # rather than silently dropping Bal at the global main menu.
        if (name == "menu" and self.profile_kind == "story"
                and self.current_name() in ("maker", "your_music")):
            name = "story"
        screen = self.screens.get(name)
        if screen is None:
            return
        # Stop any music when leaving the maker / your-music players so songs
        # don't bleed across screens.
        if self.current is not None and name != self.current_name():
            try:
                self.engine.stop_music()
            except Exception:
                pass
        self.current = screen
        # the soft seamless shimmer bed plays on the menu and in explore; it
        # stops in the maker / your-music so it never sits under playback
        try:
            if name in ("menu", "explore", "story"):
                sfx.start_ambience()
            else:
                sfx.stop_ambience()
            if name != "explore":
                sfx.stop_water()
        except Exception:
            pass
        # Default: show the cursor for the click-driven UIs.  Explore's
        # on_enter hides it again unless the journal is open.
        pygame.mouse.set_visible(True)
        screen.on_enter()

    def current_name(self):
        for n, s in self.screens.items():
            if s is self.current:
                return n
        return None

    # ------------------------------------------------------------------ loop
    def _desktop_size(self):
        try:
            return pygame.display.get_desktop_sizes()[0]
        except Exception:
            return (1920, 1080)

    def _set_display(self, fullscreen):
        if fullscreen and not getattr(self, "fullscreen", False) and hasattr(self, "window"):
            self._windowed_size = self.window.get_size()
        self.fullscreen = fullscreen
        if fullscreen:
            dw, dh = self._desktop_size()
            try:
                self.window = pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
            except Exception:
                self.window = pygame.display.set_mode((dw, dh))
        else:
            w, h = self._clamp_windowed_size(*self._windowed_size)
            self._windowed_size = (w, h)
            try:
                self.window = pygame.display.set_mode((w, h), pygame.RESIZABLE)
            except Exception:
                self.window = pygame.display.set_mode((w, h))
        w, h = self.window.get_size()
        ui_h = getattr(self, "_presentation_height", self._windowed_size[1])
        config.init_screen(w, h, ui_h=ui_h)

    def _clamp_windowed_size(self, w, h):
        dw, dh = self._desktop_size()
        max_w, max_h = max(1, dw), max(1, dh)
        min_w, min_h = min(MIN_W, max_w), min(MIN_H, max_h)
        w = min(max_w, max(min_w, int(w)))
        h = min(max_h, max(min_h, int(h)))
        return w, h

    def _refresh_current_layout(self):
        if self.current is None:
            return
        name = self.current_name()
        if name == "maker":
            self.current._layout()
        elif name == "menu":
            self.current._build()
        elif name == "your_music":
            self.current.on_enter()
        elif name in ("explore", "story"):
            if self.current.game is not None:
                self.current.game.resize(self.window, ui_h=config.UI_H)
            pygame.mouse.set_visible(self.current.paused
                                     or self.current.picker is not None
                                     or self.current.tray is not None)
        else:
            self.current.on_enter()

    def toggle_fullscreen(self):
        self._set_display(not self.fullscreen)
        self._refresh_current_layout()

    def quit(self):
        self.running = False

    def run(self):
        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0
            dt = min(dt, 0.05)          # clamp huge frames (e.g. after a stall)

            for e in pygame.event.get():
                self.handle_event(e)
                if not self.running:
                    break

            if not self.running:
                break

            self.current.update(dt)
            self.current.draw(self.window)
            pygame.display.flip()

        self._shutdown()

    def handle_event(self, e):
        """Dispatch one event; split out so global behavior is regression-testable."""
        if e.type == pygame.QUIT:
            self.running = False
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
            self.toggle_fullscreen()
        elif e.type == pygame.VIDEORESIZE:
            self._on_resize(e.w, e.h)
        else:
            self.current.handle_event(e)

    def _on_resize(self, w, h):
        if self.fullscreen:
            return
        w, h = self._clamp_windowed_size(w, h)
        try:
            self.window = pygame.display.set_mode((w, h), pygame.RESIZABLE)
        except Exception:
            return
        self._windowed_size = (w, h)
        config.init_screen(w, h, ui_h=self._presentation_height)
        self._refresh_current_layout()

    def _shutdown(self):
        try:
            if not self.collection.save():
                _LOG.error("Could not save the active collection during shutdown")
        except Exception:
            _LOG.exception("Unexpected collection save failure during shutdown")
        try:
            self.engine.shutdown()
        except Exception:
            _LOG.exception("Audio engine shutdown failed")
        pygame.quit()


def _packaged_smoke_test():
    """Start the frozen application, render one frame, and exit successfully.

    This path is enabled only by the release workflow. Normal players never
    enter it, so it cannot alter gameplay behavior or saved progress.
    """
    app = App()
    try:
        app.current.update(0.0)
        app.current.draw(app.window)
        pygame.display.flip()
    finally:
        app._shutdown()


def main():
    if os.environ.get("BAL_SOUND_GARDEN_SMOKE_TEST") == "1":
        _packaged_smoke_test()
        return
    App().run()


if __name__ == "__main__":
    main()
