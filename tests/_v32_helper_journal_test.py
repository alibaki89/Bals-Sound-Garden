"""Focused checks for non-cat hired helpers and journal-open discipline."""
import os
import random
import tempfile
from types import SimpleNamespace

os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = tempfile.mkdtemp(prefix="bsg-v32-")
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = tempfile.mkdtemp(prefix="bsg-v32-exports-")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((960, 540))

from cat_society import paths
from cat_society.components.collection import Collection
from cat_society.entities.animals import SPECIES
from cat_society.screens.explore import ExploreScreen
from cat_society.screens.story import StoryScreen
from cat_society.story.helpers import HELPER_INFO, HelperManager
from cat_society.story.journal import StoryJournalOverlay
from cat_society.story.shop import Shop
from cat_society.story.state import StoryState

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


profile = os.path.join(os.environ["BAL_SOUND_GARDEN_DATA_DIR"], "save", "slots", "slot_test")
paths.set_active_profile(profile)
state = StoryState()
state.shop_x = 0.0
state.shop_z = 0.0
state.intro_complete = True
state.save()
manager = HelperManager(state, Collection(), Shop(0.0, 0.0, built=1.0), 9921)

check("Bal remains the only cat and every helper uses an existing animal species",
      len({info["species"] for info in HELPER_INFO.values()}) == 3
      and all(info["species"] in SPECIES and info["species"] != "cat"
              for info in HELPER_INFO.values()))
check("unhired helpers create no actors or map positions", manager.visuals == {})

manager.hire("assistant")
check("hiring creates only that helper's animal actor",
      set(manager.visuals) == {"assistant"}
      and manager.visuals["assistant"].animal.key == HELPER_INFO["assistant"]["species"])
manager.update(0.0, SimpleNamespace(day=1, minutes=600.0, stamp=270.0), ())
check("a hired helper becomes a visible world animal",
      manager.visuals["assistant"].visible)
check("unhired scout and courier still have no hidden actor or position",
      "scout" not in manager.visuals and "courier" not in manager.visuals)

fake_screen = SimpleNamespace(helpers=manager, story_state=state,
                              decorations=SimpleNamespace(inventory_count=lambda _item: 0))
journal = StoryJournalOverlay(SimpleNamespace(), fake_screen)
check("Team journal lists only helpers Bal has actually hired",
      journal._team_rows() == [("helper", "assistant")])

# The old D shortcut conflicted with rightward movement and caused the journal
# to appear near the counter. Ensure D now falls through to normal play.
screen = StoryScreen.__new__(StoryScreen)
screen.paused = False
screen.market = None
screen.decorations = SimpleNamespace(placing=None)
screen.dialogue = SimpleNamespace(active=False, handle_event=lambda _e: False)
screen.picker = None
screen.tray = None
screen.intro = SimpleNamespace(active=False, phase="done", cinematic=False, placing=False)
screen.story = SimpleNamespace(handle_event=lambda _e: False)
screen.clock = SimpleNamespace(minutes=600.0)
screen.game = SimpleNamespace(cat=SimpleNamespace(on_ground=True))
screen._near_counter = lambda: True
screen.pause_page = "main"
screen.fell_through = False
original = ExploreScreen.handle_event
try:
    ExploreScreen.handle_event = lambda self, event: setattr(self, "fell_through", True)
    StoryScreen.handle_event(screen, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_d))
finally:
    ExploreScreen.handle_event = original
check("pressing D near the counter never opens or pauses on the journal",
      screen.fell_through and not screen.paused and screen.pause_page == "main")

pygame.quit()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
