"""Regression checks for UI cleanup, pause keyboard navigation, and plant preview rules."""
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
    backup = "save._ui_touchup_backup"
    shutil.rmtree(backup, ignore_errors=True)
    shutil.move("save", backup)

try:
    pygame.init()
    from cat_society.app import App
    from cat_society.components import catalog
    from cat_society import ui

    app = App()
    app.goto("explore")
    ex = app.screens["explore"]
    ex.story._queue = []
    ex.story._current = None

    ex._set_paused(True)
    check("pause keyboard selection starts on Resume", ex._pause_index == 0)
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    check("Down arrow moves to the next pause option", ex._pause_index == 1)
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    check("Up arrow moves back through the pause options", ex._pause_index == 0)
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    check("Enter opens the highlighted pause option", ex.pause_page == "controls")
    ex.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    check("Esc from controls returns to the pause root", ex.paused and ex.pause_page == "main")

    controls = ex._controls_sections()
    joined = " ".join(title + " " + " ".join(lines) for title, lines in controls)
    for phrase in (
        "Use WASD or the arrow keys",
        "Press E near a floating sound",
        "Press F to open the seed tray",
        "press Tab to switch",
        "Press P to open your saved-song list",
        "Press M at any time in Explore",
        "choose Journal",
        "Press F11 to switch",
    ):
        check(f"controls mention: {phrase}", phrase in joined)

    comp = next(c for c in catalog.ALL if c.get("type") in ("note", "drum", "bass"))
    ex.holding = comp
    old_depth = ex.game.water.depth_at
    ex.game.water.depth_at = lambda x, z: (1.0, 0.0)
    check("plant preview is hidden over water", ex._plant_preview_info() is None)
    ex.game.water.depth_at = lambda x, z: (0.0, 0.0)
    preview = ex._plant_preview_info()
    check("plant preview returns draw information on land", preview is not None and preview[3] is comp)
    ex.game.water.depth_at = old_depth

    # Wrapped / fitted helpers should keep oversized labels within their boxes.
    surf = pygame.Surface((320, 160), pygame.SRCALPHA)
    rect = pygame.Rect(10, 10, 120, 30)
    r = ui.pixel_text_center_box(surf, "A VERY LONG BUTTON LABEL", 22, rect)
    check("pixel_text_center_box shrinks long labels to fit", r.width <= rect.width)
    wrapped = ui.wrap_lines("This is a readable wrapped sentence for the UI.", 16, 110, pixel=True, bold=False)
    check("wrap_lines splits long text into multiple lines", len(wrapped) >= 2)

    # Soundbook drawing should succeed with the cleaned layout.
    sb = app.screens["menu"].soundbook
    sb.reset()
    sb.draw(pygame.Surface(app.window.get_size()))
    check("soundbook draws with the tidied layout", True)

    app._shutdown()
finally:
    shutil.rmtree("save", ignore_errors=True)
    if backup:
        shutil.move(backup, "save")

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
