"""Focused regression checks for the v30 night-world and intro polish."""
import os
import random
import tempfile
from pathlib import Path

os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = tempfile.mkdtemp(prefix="bsg-v30-")
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = tempfile.mkdtemp(prefix="bsg-v30-exports-")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((960, 540))

from cat_society import config, ui
from cat_society.app import App
from cat_society.entities.animals import Animal
from cat_society.render.background import build_sky
from cat_society.render.daynight import DayNightRenderer

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


# All decorative text symbols are reduced to safe, ordinary characters.
check("shared UI strips unsupported decorative glyphs",
      ui.safe_text("★ 12 • × − — café") == "* 12 - X - - cafe")
check("visible Python source contains no non-ASCII UI glyphs",
      all(not any(ord(ch) > 127 for ch in p.read_text("utf-8"))
          for p in Path("cat_society").rglob("*.py")))

config.init_screen(960, 540, ui_h=540)
renderer = DayNightRenderer(config.W, config.H, seed=31)
base = build_sky(include_sun=False, include_rainbow=False)

# The world darkens with a cool multiply while keeping green grass and detail.
noon = base.copy()
renderer.draw_sky(noon, 720, 1, 0.0)
renderer.apply_world_lighting(noon, 720)
night = base.copy()
renderer.draw_sky(night, 1380, 1, 0.0)
renderer.apply_world_lighting(night, 1380)
probe_y = min(config.H - 3, config.HORIZON + 48)
noon_px = noon.get_at((config.W // 2, probe_y))[:3]
night_px = night.get_at((config.W // 2, probe_y))[:3]
check("night visibly reaches the meadow instead of changing only the sky", night_px != noon_px)
check("night meadow stays green-blue rather than brown", night_px[1] > night_px[0])
check("night remains readable rather than becoming nearly black", sum(night_px) > 150)

# Musical objects make a local warm pool after dark.
lit = night.copy()
before = sum(lit.get_at((config.W // 2, probe_y))[i] for i in range(3))
renderer.draw_music_lights(lit, [(config.W // 2, probe_y, 40, (255, 184, 92), 1.2)], 1380)
after = sum(lit.get_at((config.W // 2, probe_y))[i] for i in range(3))
check("sprout and gramophone light creates a visible local pool", after > before + 8)

# The moon fades in gradually and is a plain disc with no phase-mask eye.
check("moon rises through a gradual dusk fade",
      0.0 < renderer._moon_visibility(19 * 60) < renderer._moon_visibility(20 * 60) <= 1.0)
moon = pygame.Surface((config.W, config.H), pygame.SRCALPHA)
moon.fill((0, 0, 0, 0))
minute = 23 * 60
renderer._draw_moon(moon, minute, 1.0)
t = (minute - 18.5 * 60) % 1440.0
p = t / (12.0 * 60.0)
mx = int(config.W * (.07 + .86 * p))
my = int(renderer.sky_h * .82 - __import__("math").sin(p * __import__("math").pi) * renderer.sky_h * .56)
r = max(3, int(config.H * .017))
left = moon.get_at((mx - max(1, r // 2), my))
right = moon.get_at((mx + max(1, r // 2), my))
check("moon face is a simple even disc", left[:3] == right[:3] and left[3] > 200)

# Diurnal wildlife sleeps at night; nocturnal wildlife remains available.
def ctx(night_value):
    return {"cat_x": 10000.0, "cat_z": 10000.0,
            "valid": lambda x, z, aquatic: True,
            "in_water": lambda x, z: False,
            "song": None, "night": night_value, "minutes": 1380.0}

dog = Animal("dog", 0.0, 0.0, random.Random(1))
dog.update(.1, ctx(1.0))
owl = Animal("owl", 0.0, 0.0, random.Random(2))
owl.update(.1, ctx(1.0))
check("daytime animals use the proper sleeping pose at night",
      dog.state == "sleep" and dog.ai_state == "night_sleep")
check("nocturnal animals are not forced into daytime-animal sleep",
      owl.ai_state != "night_sleep")
dog.update(.1, ctx(0.0))
check("sleeping wildlife wakes after dawn", dog.ai_state != "night_sleep")

# Every new opening reserves the full sea-to-shore path, then releases it.
app = App()
app.start_story(new=True)
story = app.current
game = story.game
start = story.intro._start
land = story.intro._land
checks = []
for i in range(11):
    q = i / 10.0
    x = start[0] + (land[0] - start[0]) * q
    z = start[1] + (land[1] - start[1]) * q
    checks.append(game.in_clear_zone(x, z))
check("arrival reserves a clean corridor along the whole boat path", all(checks))

# Existing wild animals inside that corridor are removed before they can cross it.
intruder = Animal("cow", start[0], (start[1] + land[1]) * .5, random.Random(3))
game.animals.cells[(0, 0)] = [intruder]
game.animals.update(.01, game.cat, night=0.0, minutes=540.0,
                    exclusion_zones=game.clear_zones)
check("wild animals cannot wander through the arrival shot",
      intruder not in game.animals.animals())
story.intro.skip_to_placement(game, story.story)
check("cinematic clearing is released after the landing", not game.clear_zones)

app._shutdown()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
