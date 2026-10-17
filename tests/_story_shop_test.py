"""Headless regression checks for the boat/shop/dialogue story pass."""
import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="bsg-story-test-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _DATA
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

passed = failed = 0


def check(label, condition):
    global passed, failed
    ok = bool(condition)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


def dismiss_story_cards(screen):
    for _ in range(8):
        for _ in range(40):
            screen.update(1 / 60)
        if screen.story.blocking:
            screen.handle_event(pygame.event.Event(pygame.KEYDOWN,
                                                   key=pygame.K_SPACE))
        else:
            break


pygame.init()
from cat_society.app import App
from cat_society.components import catalog
from cat_society.story.state import StoryState

app = App()
labels = [label for _rect, label, _cb in app.screens["menu"]._buttons]
check("menu exposes story and creative destinations",
      labels == ["New Game", "Continue Story", "Explore", "Music Maker",
                 "Your Music", "Soundbook"])

# Creative and story collections must not bleed into one another.
creative_comp = next(c for c in catalog.ALL
                     if not c.get("starter") and not app.collection.owns(c["id"]))
app.collection.collect(creative_comp["id"])
creative_owned_ids = set(app.collection.found)
app.start_story(new=True)
check("new story opens the story screen", app.current_name() == "story")
check("story starts with an isolated collection",
      not app.collection.owns(creative_comp["id"]))
story_comp = next(c for c in catalog.ALL
                  if not c.get("starter") and c["id"] not in creative_owned_ids)
app.collection.collect(story_comp["id"])

screen = app.current
check("new story starts with the sailing cinematic", screen.intro.phase == "sail")
screen.intro.skip_to_placement(screen.game, screen.story)
for _ in range(40):
    screen.update(1 / 60)
    if screen.intro.preview and screen.intro.preview[2]:
        break
    screen.game.cat.z -= 40.0
check("shop placement finds a dry buildable patch",
      screen.intro.preview is not None and screen.intro.preview[2])
if screen.intro.preview and screen.intro.preview[2]:
    ok, _message = screen.intro.try_build()
else:
    ok = False
check("pressing build starts the construction animation", ok and screen.shop.building)
for _ in range(180):
    screen.update(1 / 60)
check("construction produces a persistent finished shop", screen.shop.ready)
dismiss_story_cards(screen)
for _ in range(3):
    screen.update(1 / 60)
check("intro reaches normal story play", screen.intro.phase == "done")

# Keep Bal at the counter while Pip walks in. The first greeting should open
# by itself, teaching the dialogue loop without a floating tutorial panel.
screen.game.cat.x = screen.shop.x
screen.game.cat.z = screen.shop.z - 130.0
for _ in range(1200):
    screen.update(1 / 60)
    if screen.dialogue.active:
        break
check("first client walks to the shop", bool(screen.clients.actors))
check("first client starts a real dialogue tutorial", screen.dialogue.active)
if screen.clients.actors:
    pip = screen.clients.actors[0]
    check("starter client is Pip the dog", pip.name == "Pip the dog")
    check("request has authored musical details",
          bool(pip.request.get("flavor")) and bool(pip.request.get("tempo"))
          and bool(pip.request.get("needs")))
    # Reveal both animal pages, then select Bal's direct reply.
    screen.dialogue.reveal = 9999
    screen.dialogue._advance()
    screen.dialogue.reveal = 9999
    screen.dialogue._choose(0)
    check("dialogue choices become an on-screen reply from Bal",
          screen.dialogue.active and screen.dialogue.speaker == "Bal"
          and screen.dialogue.species == "bal")
    screen.dialogue.close()

# Rendering every layered element is part of the regression: world shop,
# visitor, speech bubble, HUD and full-resolution dialogue bar.
screen.draw(app.window)
check("story world and dialogue render headlessly", True)

saved = StoryState()
check("shop position and story economy serialize",
      saved.has_shop and saved.shop_x == screen.shop.x and saved.coins == 0)

app.exit_story_to_menu()
check("leaving story restores Creative", app.profile_kind == "creative")
check("Creative discovery is restored", app.collection.owns(creative_comp["id"]))
check("story discovery stays isolated", not app.collection.owns(story_comp["id"]))

app.start_story(new=False)
check("continuing restores story discovery", app.collection.owns(story_comp["id"]))
check("continuing does not import Creative discovery",
      not app.collection.owns(creative_comp["id"]))
check("continuing restores the built shop", app.current.shop.ready)

app._shutdown()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
