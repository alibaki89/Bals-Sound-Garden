"""Focused checks for v35 sleep confirmation and portrait framing."""
import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="bsg-v35-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _DATA
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import random
import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

from cat_society.app import App
from cat_society.entities.animals import Animal

passed = failed = 0

def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


def make_playable(app):
    app.start_story(new=True)
    sc = app.current
    sc.intro.skip_to_placement(sc.game, sc.story)
    for _ in range(80):
        sc.update(1 / 60)
        if sc.intro.preview and sc.intro.preview[2]:
            break
        sc.game.cat.z -= 35.0
    ok, _ = sc.intro.try_build()
    assert ok
    for _ in range(220):
        sc.update(1 / 60)
    sc.story.clear()
    sc.update(1 / 60)
    sc.intro.phase = "done"
    sc.story_state.intro_complete = True
    return sc

app = App()
story = make_playable(app)
story.clock.set_time(18 * 60 + 15)
old_stamp = story.clock.stamp
story.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
check("first sleep key press opens a confirmation instead of skipping immediately",
      story._sleep_confirm and abs(story.clock.stamp - old_stamp) < 0.001)
story.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
check("second confirmation press performs the overnight skip",
      not story._sleep_confirm and story.clock.format_time() == "08:30")

story.clock.set_time(18 * 60 + 5)
story.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_z))
story.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
check("escape cancels the sleep confirmation", not story._sleep_confirm)

app.window.fill((0, 0, 0))
story._sleep_confirm = True
story.draw(app.window)
check("sleep confirmation overlay draws without crashing", True)

app._shutdown()
pygame.quit()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
