"""Regression tests for the final pause, Journal, controls, and route cleanup."""
import importlib.util
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
    backup = "save._golden_polish_backup"
    shutil.rmtree(backup, ignore_errors=True)
    shutil.move("save", backup)

try:
    pygame.init()
    from cat_society.app import App
    from cat_society import ui

    app = App()
    menu = app.screens["menu"]
    labels = [label for _, label, _ in menu._buttons]
    check("Soundbook remains available from the main menu",
          labels == ["New Game", "Continue Story", "Explore", "Music Maker",
                     "Your Music", "Soundbook"])

    app.goto("explore")
    ex = app.screens["explore"]
    ex.story._queue = []
    ex.story._current = None

    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_c))
    c_did_nothing = not ex.paused
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j))
    check("C and J are not Explore shortcuts", c_did_nothing and not ex.paused)

    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    pause_surface = pygame.Surface(app.window.get_size())
    ex.draw(pause_surface)
    actions = {action for _, action in ex._pause_buttons}
    check("pause menu contains a Journal button",
          actions == {"resume", "journal", "controls", "menu", "quit"})

    ex._pause_action("journal")
    ex.draw(pause_surface)
    check("Journal opens the shared Soundbook in pause",
          ex.paused and ex.pause_page == "journal"
          and ex.soundbook is not None)
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc from Journal returns to pause root",
          ex.paused and ex.pause_page == "main")

    captured = []
    old_text = ui.pixel_text

    def capture_text(surf, text, *args, **kwargs):
        captured.append(str(text))
        return old_text(surf, text, *args, **kwargs)

    ui.pixel_text = capture_text
    try:
        ex._pause_action("controls")
        ex.draw(pause_surface)
    finally:
        ui.pixel_text = old_text

    joined = " ".join(captured)
    check("controls use complete natural instructions",
          "Use WASD or the arrow keys to walk around the garden." in joined
          and "Press E near a floating sound to collect it." in joined
          and "Press Esc to pause the game" in joined)
    check("controls contain no removed route keys",
          "remembered walk" not in joined.lower()
          and "Press R" not in joined and "Press X" not in joined)

    captured = []
    old_center = ui.pixel_text_center_box
    old_text = ui.pixel_text

    def cap_center(surf, text, *args, **kwargs):
        captured.append(str(text))
        return old_center(surf, text, *args, **kwargs)

    def cap_text(surf, text, *args, **kwargs):
        captured.append(str(text))
        return old_text(surf, text, *args, **kwargs)

    ui.pixel_text_center_box = cap_center
    ui.pixel_text = cap_text
    try:
        ex._region_name = "Meadow of First Notes"
        ex._near = None
        ex._draw_hud(pygame.Surface(app.window.get_size()))
    finally:
        ui.pixel_text_center_box = old_center
        ui.pixel_text = old_text
    check("HUD keeps the small Esc pause hint without the sound label",
          "ESC  PAUSE" in captured
          and not any(text.lower().endswith(" sounds") for text in captured))

    check("route state module is removed",
          importlib.util.find_spec("cat_society.world.ghost") is None)
    check("route renderer module is removed",
          importlib.util.find_spec("cat_society.render.ghost") is None)
    check("Explore no longer owns route replay state",
          not hasattr(ex, "ghost") and not hasattr(ex, "_toggle_record")
          and not hasattr(ex.game, "route_ghost"))
    check("sprout walkers no longer include replay ghosts",
          all(kind != "ghost" for _, kind, _, _ in ex.sprouts._walkers(ex.game)))

    ex._set_paused(False)
    app._shutdown()
finally:
    shutil.rmtree("save", ignore_errors=True)
    if backup:
        shutil.move(backup, "save")

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
