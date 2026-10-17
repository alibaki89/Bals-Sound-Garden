"""Focused regression checks for the v29 visual restoration and reset dialog."""
import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="bsg-v29-")
_EXPORTS = tempfile.mkdtemp(prefix="bsg-v29-exports-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _DATA
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = _EXPORTS
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((960, 540))

from cat_society import config
from cat_society.app import App
from cat_society.render.background import build_sky
from cat_society.render.daynight import DayNightRenderer

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


config.init_screen(960, 540, ui_h=540)
renderer = DayNightRenderer(config.W, config.H, seed=19)
base = build_sky(include_sun=False, include_rainbow=False)
ground_start = min(config.H - 2, config.HORIZON + max(8, (config.H - config.HORIZON) // 3))
ground_rect = pygame.Rect(0, ground_start, config.W, config.H - ground_start)
ground_before = base.subsurface(ground_rect).copy()

for minute in (0, 330, 720, 1080, 1140, 1320):
    frame = base.copy()
    renderer.draw_sky(frame, minute, 1, 4.0)
    check("sky cycle leaves original meadow pixels untouched at %04d" % minute,
          pygame.image.tostring(frame.subsurface(ground_rect), "RGB") ==
          pygame.image.tostring(ground_before, "RGB"))

noon = base.copy()
renderer.draw_sky(noon, 720, 1, 2.0)
renderer.apply_world_lighting(noon, 720)
check("midday world keeps the original grass colour and texture",
      pygame.image.tostring(noon.subsurface(ground_rect), "RGB") ==
      pygame.image.tostring(ground_before, "RGB"))

night = base.copy()
renderer.draw_sky(night, 1380, 1, 2.0)
renderer.apply_world_lighting(night, 1380)
probe = night.get_at((config.W // 2, min(config.H - 2, config.HORIZON + 28)))[:3]
check("night grass remains green rather than brown", probe[1] > probe[0])
check("night still visibly changes the world", pygame.image.tostring(
      night.subsurface(ground_rect), "RGB") != pygame.image.tostring(ground_before, "RGB"))
check("night one has a visible aurora layer", renderer.aurora_active(1))

app = App()
menu = app.screens["menu"]
menu.dialog = "reset"
try:
    menu.draw(app.window)
    reset_dialog_draws = True
except Exception:
    reset_dialog_draws = False
check("Reset Progress confirmation renders without crashing", reset_dialog_draws)

story = app.screens["story"]
from types import SimpleNamespace
old_intro = story.intro
story.intro = SimpleNamespace(
    overlay_text=lambda: ("Bal arrives at the island", "Space to skip"),
    cinematic=True,
    placing=False,
    preview=None,
)
sample = pygame.Surface(app.window.get_size())
sample.fill((240, 240, 240))
story._draw_intro_overlay(sample)
check("intro no longer paints a full-width black bar at the top",
      sample.get_at((0, 0))[:3] == (240, 240, 240))
story.intro = old_intro

app.reset_progress()
check("Reset Progress action completes after its confirmation is drawn",
      app.screens["menu"].dialog is None)
app._shutdown()

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
