"""Focused checks for v33 menu cleanup and literal world-sprite portraits."""
import os
import random
import tempfile

os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = tempfile.mkdtemp(prefix="bsg-v33-")
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = tempfile.mkdtemp(prefix="bsg-v33-exports-")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

from cat_society import config
from cat_society.app import App
from cat_society.entities.animals import Animal
from cat_society.story.dialogue import DialogueOverlay, _entity_portrait

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


config.init_screen(1280, 720, ui_h=720)
app = App()
menu = app.screens["menu"]
for dialog in ("settings", "reset"):
    menu.dialog = dialog
    try:
        menu.draw(app.window)
        drew = True
    except Exception:
        drew = False
    check("%s dialog draws without overflow-related errors" % dialog, drew)

panel, rows = menu._settings_rows()
mute, done = menu._settings_buttons(panel)
check("sound controls remain inside their panel",
      all(panel.contains(bar.inflate(0, menu.S(8))) for _key, _label, bar in rows)
      and panel.contains(mute) and panel.contains(done))

panel, cancel, reset = menu._reset_buttons()
check("reset actions remain inside their panel",
      panel.contains(cancel) and panel.contains(reset))

animal = Animal("dog", 0.0, 0.0, random.Random(77))
animal.facing = -1
animal.state = "idle"
animal.mood = "happy"
portrait = _entity_portrait("dog", 112, entity=animal)
bounds = portrait.get_bounding_rect(min_alpha=8)
check("dialogue portrait is a non-empty world-entity screenshot",
      bounds.w > 30 and bounds.h > 25)
check("dialogue portrait keeps comfortable distance around the entity",
      bounds.w < 106 and bounds.h < 106 and bounds.x > 0 and bounds.y > 0)

class CountingAnimal:
    spec = animal.spec
    def __init__(self):
        self.calls = 0
    def draw(self, surf, sx, sy, draw_scale, proj_scale, swim=0.0,
             fade=0.0, draw_shadow=True):
        self.calls += 1
        animal.draw(surf, sx, sy, draw_scale, proj_scale, swim=swim,
                    fade=fade, draw_shadow=draw_shadow)

speaker = CountingAnimal()
overlay = DialogueOverlay()
overlay.open("Bramble", "dog", ["Hello, Bal."], portrait_entity=speaker)
overlay.reveal = 999
surface = pygame.Surface((1280, 720))
world_photo = pygame.Surface((120, 120))
world_photo.fill((104, 151, 92))
pygame.draw.rect(world_photo, (238, 218, 170), (14, 14, 92, 92), 3)
overlay.capture_world_portrait(surface, lambda _surf, _entity: world_photo)
overlay.draw(surface)
overlay.draw(surface)
check("dialogue uses the captured world photograph instead of redrawing the animal",
      speaker.calls == 0 and overlay.portrait_photo is not None
      and overlay.portrait_photo.get_at((0, 0))[:3] == (104, 151, 92))

app._shutdown()
pygame.quit()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
