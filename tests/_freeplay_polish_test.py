"""Regression checks for the resolution, echo, pause, HUD and discovery polish."""
import os
import shutil

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

passed = failed = 0


def check(name, condition):
    global passed, failed
    ok = bool(condition)
    print(("[PASS] " if ok else "[FAIL] ") + name)
    passed += int(ok)
    failed += int(not ok)


backup = None
if os.path.isdir("save"):
    backup = "save._freeplay_polish_backup"
    shutil.rmtree(backup, ignore_errors=True)
    shutil.move("save", backup)

try:
    pygame.init()
    from cat_society import config, ui

    print("\n--- Resolution-invariant presentation ---")
    config.init_screen(1280, 720, ui_h=720)
    base = (config.W, config.H, config.SC, config.PIX,
            ui.scaled(720, 100),
            config.VIEW_Y + config.GROUND_Y * config.PIX - 720 / 2.0)
    config.init_screen(1920, 1080, ui_h=720)
    full = (config.W, config.H, config.SC, config.PIX,
            ui.scaled(1080, 100),
            config.VIEW_Y + config.GROUND_Y * config.PIX - 1080 / 2.0)
    check("fullscreen preserves physical world and UI scale",
          base[2:5] == full[2:5])
    check("fullscreen reveals a larger logical field of view",
          full[0] > base[0] and full[1] > base[1])
    check("the original composition stays centred in the expanded view",
          abs(base[5] - full[5]) <= config.PIX)

    config.init_screen(1600, 1000, ui_h=720)
    check("different aspect expands or contracts the field without zoom",
          config.SC == base[2] and config.PIX == base[3])
    check("world canvas is not stretched disproportionately",
          config.SCALE_X == config.SCALE_Y == float(config.PIX))
    px = config.canvas_to_window(53.5, 88.25)
    back = config.window_to_canvas(*px)
    check("window/canvas coordinate conversion round-trips",
          abs(back[0] - 53.5) < 1e-6 and abs(back[1] - 88.25) < 1e-6)

    print("\n--- Free-play screen and pause flow ---")
    from cat_society.app import App
    app = App()
    presentation = (config.PIX, config.SC, config.UI_H)
    rw, rh = app.window.get_size()
    app._on_resize(max(640, rw - 120), max(480, rh - 80))
    check("manual window resizing changes field of view rather than zoom",
          (config.PIX, config.SC, config.UI_H) == presentation)
    app.goto("explore")
    ex = app.screens["explore"]
    # Dismiss the two compact onboarding cards so normal input owns Esc.
    for _ in range(4):
        if ex.story.blocking:
            ex.story.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                                     key=pygame.K_SPACE))
            ex.story.update(1.0)
    current_before = app.current
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc opens pause without leaving Explore",
          ex.paused and app.current is current_before)
    pause_surface = pygame.Surface(app.window.get_size())
    ex.draw(pause_surface)
    check("pause menu exposes Journal and the normal pause actions",
          {action for _, action in ex._pause_buttons}
          == {"resume", "journal", "controls", "menu", "quit"})
    ex._pause_action("journal")
    ex.draw(pause_surface)
    check("Journal opens inside the pause menu", ex.pause_page == "journal")
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc from Journal returns to pause root",
          ex.paused and ex.pause_page == "main")
    ex._pause_action("controls")
    ex.draw(pause_surface)
    check("Controls opens a dedicated pause page",
          ex.pause_page == "controls"
          and any(action == "back" for _, action in ex._pause_buttons))
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc from Controls returns to pause root",
          ex.paused and ex.pause_page == "main")
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc from pause resumes", not ex.paused)

    # Proper pause: wall-clock systems must not jump ahead while SDL audio is
    # paused. Simulate a 2.5-second stay without sleeping the test process.
    ex.perf.active = True
    ex.perf.started = 100.0
    app.engine._music_started = 200.0
    sprout_epoch = ex.sprouts._t0
    ex._set_paused(True)
    ex._pause_started_at -= 2.5
    ex._set_paused(False)
    check("pause excludes elapsed wall time from garden and music clocks",
          abs(ex.sprouts._t0 - (sprout_epoch + 2.5)) < 0.1
          and abs(ex.perf.started - 102.5) < 0.1
          and abs(app.engine._music_started - 202.5) < 0.1)
    ex.perf.active = False
    app.engine.stop_music()

    check("task/commission manager is not instantiated", ex.works is None)

    print("\n--- Immediate discovery cards ---")
    from cat_society.components import catalog
    from cat_society.screens.card import CardManager, _SLIDE_IN
    cards = CardManager()
    one, two = catalog.ALL[0], catalog.ALL[1]
    cards.queue(one, 1, None)
    cards.update(0.1)
    cards.queue(two, 2, None)
    check("new discovery replaces the active card immediately",
          cards._current is two and cards._t == _SLIDE_IN)
    check("discovery notifications never build a queue", cards._queue == [])
    cards.update(0.2)
    check("replacement receives its own visible hold period", cards._current is two)

    print("\n--- Route system removed ---")
    import importlib.util
    check("route state module is absent",
          importlib.util.find_spec("cat_society.world.ghost") is None)
    check("route renderer module is absent",
          importlib.util.find_spec("cat_society.render.ghost") is None)
    check("Explore has no route recorder", not hasattr(ex, "ghost")
          and not hasattr(ex, "_toggle_record"))
    walkers = list(ex.sprouts._walkers(ex.game))
    check("sprout walkers contain no replay ghosts",
          all(kind != "ghost" for _, kind, _, _ in walkers))

    app._shutdown()
finally:
    shutil.rmtree("save", ignore_errors=True)
    if backup:
        shutil.move(backup, "save")

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
