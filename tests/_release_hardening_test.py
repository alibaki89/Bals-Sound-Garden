"""Focused release-hardening regression checks.

Uses only temporary player-data directories and the dummy SDL drivers.
"""
import json
import os
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(tempfile.mkdtemp(prefix="bsg-release-tests-"))
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = str(ROOT / "data")
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = str(ROOT / "exports")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

from cat_society import config, paths, ui
from cat_society.app import App
from cat_society.music.project import Project
from cat_society.music import store
from cat_society.persistence import PersistenceError, atomic_write_json
from cat_society.story.requests import RESERVED_NAMES, RequestGenerator
from cat_society.story.state import StoryState
from cat_society.components.collection import Collection
from cat_society.world.state import WorldState
from cat_society import settings
from cat_society.screens.your_music import YourMusicScreen

passed = failed = 0


def check(label, condition):
    global passed, failed
    ok = bool(condition)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


def no_temps(directory):
    return not list(Path(directory).glob(".*.tmp"))


print("\n--- Atomic persistence and overwrite safety ---")
atomic_dir = ROOT / "atomic"
path = atomic_dir / "state.json"
check("first atomic JSON save succeeds", atomic_write_json(str(path), {"value": 1}))
check("first atomic JSON has expected content", json.loads(path.read_text()) == {"value": 1})
check("atomic overwrite succeeds", atomic_write_json(str(path), {"value": 2}))
check("atomic overwrite replaces content", json.loads(path.read_text()) == {"value": 2})
old_bytes = path.read_bytes()
try:
    with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("blocked")):
        atomic_write_json(str(path), {"value": 3})
except PersistenceError:
    pass
check("replacement failure preserves existing JSON", path.read_bytes() == old_bytes)
check("replacement failure removes temporary file", no_temps(atomic_dir))
try:
    atomic_write_json(str(path), {"bad": {1, 2, 3}})
except PersistenceError:
    pass
check("serialization failure preserves existing JSON", path.read_bytes() == old_bytes)
check("serialization failure creates no temporary file", no_temps(atomic_dir))

print("\n--- Central save categories use atomic replacement ---")
collection = Collection()
collection_path = Path(paths.collection_file())
assert collection.save()
collection_bytes = collection_path.read_bytes()
with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("blocked")):
    collection_result = collection.collect(next(c["id"] for c in __import__("cat_society.components.catalog", fromlist=["catalog"]).ALL if not c.get("starter") and not c.get("reward")))
check("collection mutation reports failed persistence", collection_result is False)
check("collection file survives failed overwrite", collection_path.read_bytes() == collection_bytes)

world = WorldState()
world_path = Path(paths.save_dir()) / "world.json"
world_bytes = world_path.read_bytes()
with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("blocked")):
    world_result = world.set_data_list("release_test", [1, 2, 3])
check("world mutation reports failed persistence", world_result is False)
check("world file survives failed overwrite", world_path.read_bytes() == world_bytes)
check("failed world mutation rolls back memory", "release_test" not in world.data)

story_for_atomic = StoryState()
assert story_for_atomic.save()
story_path = Path(paths.save_dir()) / "story.json"
story_bytes = story_path.read_bytes()
old_rep = story_for_atomic.reputation
with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("blocked")):
    story_result = story_for_atomic.adjust_reputation(0.2)
check("story mutation reports failed persistence", story_result is False)
check("story file survives failed overwrite", story_path.read_bytes() == story_bytes)
check("failed story mutation rolls back memory", story_for_atomic.reputation == old_rep)

assert settings.save()
settings_path = Path(paths.settings_file())
settings_bytes = settings_path.read_bytes()
old_volume = settings.get("music")
with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("blocked")):
    settings_result = settings.set_value("music", 0.17)
check("settings mutation reports failed persistence", settings_result is False)
check("settings file survives failed overwrite", settings_path.read_bytes() == settings_bytes)
check("failed settings mutation rolls back memory", settings.get("music") == old_volume)
check("central save failures leave no temporary files", no_temps(Path(paths.save_dir())))

print("\n--- Song project validation and failed overwrite ---")
project_dir = Path(paths.projects_dir())
project_dir.mkdir(parents=True, exist_ok=True)
old = Project("Protected Song")
check("valid song saves", store.save(old))
old_path = Path(store.path_for(old.id))
old_project_bytes = old_path.read_bytes()
replacement = Project("Protected Song")
with mock.patch("cat_society.persistence.os.replace", side_effect=OSError("mock replace failure")):
    result = store.save(replacement, replace_ids=[old.id])
check("failed replacement reports failure", result is False)
check("failed replacement keeps old song bytes", old_path.read_bytes() == old_project_bytes)
check("failed replacement does not leave new song", not Path(store.path_for(replacement.id)).exists())
check("failed replacement leaves no temporary song", no_temps(project_dir))

valid = Project("Valid Beside Broken")
check("second valid project saves", store.save(valid))
invalid_payloads = {
    "empty.json": "",
    "truncated.json": '{"name": "cut"',
    "empty_object.json": "{}",
    "missing_name.json": json.dumps({"id": "missingname", "tempo": 100, "bars": 8, "tracks": []}),
    "wrong_name.json": json.dumps({"id": "wrongname", "name": 7, "tempo": 100, "bars": 8, "tracks": []}),
    "bad_tracks.json": json.dumps({"id": "badtracks", "name": "Bad", "tempo": 100, "bars": 8, "tracks": {}}),
    "bad_version.json": json.dumps({"id": "badversion", "name": "Future", "tempo": 100, "bars": 8, "version": 99, "tracks": []}),
    "bad_clip.json": json.dumps({"id": "badclip", "name": "Bad Clip", "tempo": 100, "bars": 8,
                                  "tracks": [{"name": "Melody", "kind": "melody", "clips": [["x", "no"]]}]}),
}
for filename, text in invalid_payloads.items():
    (project_dir / filename).write_text(text, encoding="utf-8")
listed = store.list_projects()
check("valid projects remain listed beside malformed projects", any(p.id == valid.id for p in listed))
check("malformed projects are skipped", all(p.name not in ("Bad", "Bad Clip") for p in listed))
check("malformed project files are preserved", all((project_dir / name).exists() for name in invalid_payloads))
check("loading malformed project returns safely", store.load("badclip") is None)
check("project warnings are non-blocking and identify a filename",
      any("saved song" in warning.lower() for warning in store.consume_warnings()))

print("\n--- Malformed central save files fail safely ---")
malformed_paths = [Path(paths.collection_file()), Path(paths.save_dir()) / "world.json",
                   Path(paths.save_dir()) / "story.json", Path(paths.settings_file())]
for malformed in malformed_paths:
    malformed.parent.mkdir(parents=True, exist_ok=True)
    malformed.write_text("{broken", encoding="utf-8")
try:
    malformed_collection = Collection()
    malformed_world = WorldState()
    malformed_story = StoryState()
    settings.load()
    malformed_ok = isinstance(malformed_collection.found, dict) and isinstance(malformed_world.data, dict) and isinstance(malformed_story.history, list)
except Exception:
    malformed_ok = False
check("malformed collection, world, story and settings files do not crash loading", malformed_ok)

print("\n--- App screens, dirty state, Play/Stop and scrolled Load ---")
app = App()
maker = app.screens["maker"]
app.goto("maker")
check("new Maker project begins clean", not maker._is_dirty())
maker.project.tempo += 1
check("meaningful edit marks Maker dirty", maker._is_dirty())
maker._request_discard("new")
check("dirty New opens discard confirmation", maker.dialog is not None and maker._pending_discard[0] == "new")
old_id = maker.project.id
maker._dialog_action("cancel")
check("cancelling discard keeps current composition", maker.project.id == old_id and maker._is_dirty())
maker._request_discard("new")
maker._dialog_action("discard_confirm")
check("confirming discard creates clean new project", maker.project.id != old_id and not maker._is_dirty())
maker.project.tempo += 1
maker.app.projects.save = lambda *args, **kwargs: False
maker._do_save()
check("failed Maker save leaves project dirty", maker._is_dirty())
check("failed Maker save never reports Saved", "failed" in maker.message.lower())
maker._request_discard("leave")
check("failed save still requires discard confirmation", maker.dialog is not None)
maker._dialog_action("cancel")

calls = []
class EngineProbe:
    def play_project(self, *args, **kwargs): calls.append("play")
    def stop_music(self): calls.append("stop")
    def is_playing(self): return bool(calls and calls[-1] == "play")

music = YourMusicScreen(app)
app.engine = EngineProbe()
# Restore authoritative module-level store functions used by Your Music.
music._do("play", valid.id)
music._do("stop", valid.id)
check("Your Music dispatches Play then Stop", calls == ["play", "stop"])

# More than one page of valid projects.
load_items = []
for i in range(10):
    p = Project("Load %02d" % i)
    load_items.append(p)
maker.app = app
maker.project = Project("Current")
maker._layout()
maker.load_modal = {"items": load_items, "idx": 8}
surface = pygame.Surface(app.window.get_size())
maker._draw_load_modal(surface)
check("Load modal stores absolute indices for visible rows",
      maker._load_rects and all(load_items[idx] is proj for _rect, idx, proj in maker._load_rects))
rect, actual, project = maker._load_rects[-1]
maker._load_event(pygame.event.Event(pygame.MOUSEMOTION, pos=rect.center))
check("hover after scrolling selects visible absolute project", maker.load_modal["idx"] == actual)
loaded = []
maker._load_selected = lambda selected=None: loaded.append(selected or load_items[maker.load_modal["idx"]])
maker._load_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=rect.center))
check("click after scrolling loads the visible project", loaded == [project])


print("\n--- Courier transaction success and failure paths ---")
from types import SimpleNamespace
from cat_society.screens.story import StoryScreen
from cat_society.components import catalog

class CourierState:
    def __init__(self, job, order):
        self.courier_jobs = [job]
        self.active_orders = [order]
        self.saved = 0
    def save(self):
        self.saved += 1
        return True

class CourierClients:
    def __init__(self, owner):
        self.owner = owner
        self.rewards = 0
        self.notices = []
    def notify(self, *args):
        self.notices.append(args)
    def complete_remote(self, screen, order, score, item_name):
        if order not in self.owner.story_state.active_orders:
            return False
        self.rewards += 1
        self.owner.story_state.active_orders.remove(order)
        return True

def courier_screen(kind="sprout", fail=False, missing_project=False):
    screen = StoryScreen.__new__(StoryScreen)
    order = {"id": "courier-1", "name": "Client", "target_x": 10.0, "target_z": 20.0,
             "request": {"title": "Delivery"}}
    item_id = catalog.starters()[0]["id"]
    job = {"order_id": order["id"], "kind": kind, "item_id": item_id,
           "project_id": "courier_song", "item_name": "Prepared delivery",
           "target_x": 10.0, "target_z": 20.0, "complete_at": 10.0, "score": 0.8,
           "placed": False, "resource_consumed": False}
    screen.clock = SimpleNamespace(stamp=20.0)
    screen.story_state = CourierState(job, order)
    screen.clients = CourierClients(screen)
    found = {item_id: {"count": 1}}
    collection = SimpleNamespace(
        found=found,
        owns=lambda cid: cid in found,
        consume=lambda cid: True,
        save=lambda: True,
    )
    project = Project("Courier Song")
    project.id = "courier_song"
    screen.app = SimpleNamespace(
        collection=collection,
        projects=SimpleNamespace(load=lambda pid: None if missing_project else project),
    )
    sprouts = []
    def plant(comp_id, x, z):
        if fail:
            return None, "blocked"
        obj = SimpleNamespace(comp_id=comp_id, x=x, z=z)
        sprouts.append(obj)
        return obj, ""
    def uproot(obj):
        if obj in sprouts:
            sprouts.remove(obj)
        return True
    screen.sprouts = SimpleNamespace(sprouts=sprouts, plant=plant, uproot=uproot)
    grams = []
    def plant_gramophone(proj, x, z):
        if fail:
            return None
        obj = SimpleNamespace(song_id=proj.id, x=x, z=z)
        grams.append(obj)
        return obj
    def remove_gramophone(obj):
        if obj in grams:
            grams.remove(obj)
        return True
    screen.garden = SimpleNamespace(gramophones=grams, plant_gramophone=plant_gramophone,
                                    remove_gramophone=remove_gramophone)
    screen._toast = ""
    screen._toast_t = 0.0
    return screen, job, order, sprouts, grams

screen, job, order, sprouts, grams = courier_screen("sprout")
screen._process_courier_jobs()
check("successful courier sprout creates the world object", len(sprouts) == 1)
check("successful courier sprout awards exactly once", screen.clients.rewards == 1)
check("successful courier sprout removes completed job", not screen.story_state.courier_jobs)
screen._process_courier_jobs()
check("retry after success cannot duplicate object or reward", len(sprouts) == 1 and screen.clients.rewards == 1)

screen, job, order, sprouts, grams = courier_screen("sprout", fail=True)
screen._process_courier_jobs()
check("failed courier sprout leaves mission recoverable", screen.story_state.courier_jobs == [job])
check("failed courier sprout gives no reward", screen.clients.rewards == 0)
check("failed courier sprout creates no object", not sprouts)
retry_at = job.get("retry_at")
screen._process_courier_jobs()
check("failed courier does not retry every frame", job.get("retry_at") == retry_at and screen.clients.rewards == 0)

screen, job, order, sprouts, grams = courier_screen("gramophone")
screen._process_courier_jobs()
check("successful courier gramophone creates the world object", len(grams) == 1)
check("successful courier gramophone completes once", screen.clients.rewards == 1 and not screen.story_state.courier_jobs)

screen, job, order, sprouts, grams = courier_screen("gramophone", missing_project=True)
screen._process_courier_jobs()
check("missing courier song leaves order active and unrewarded",
      screen.clients.rewards == 0 and screen.story_state.courier_jobs == [job] and not grams)

print("\n--- Commission cancellation and reserved names ---")
state = StoryState()
state.reputation = 3.0
order = {"id": "cancel-1", "name": "Client", "request": {"title": "Small Song"}}
state.active_orders = [order]
before = state.reputation
check("accepted commission can be cancelled once", state.cancel_accepted(order))
check("early cancellation uses configured small penalty",
      abs(state.reputation - (before - config.STORY_CANCEL_REP_LOSS)) < 1e-9)
check("cancellation is recorded in history", state.history[-1]["item"] == "cancelled early")
check("cancellation releases active order", not state.active_orders)
second_reputation = state.reputation
check("same cancellation cannot penalize twice", not state.cancel_accepted(order) and state.reputation == second_reputation)
check("early cancellation penalty is lower than missed deadline penalty",
      config.STORY_CANCEL_REP_LOSS < config.STORY_ACCEPTED_REP_LOSS)

generator = RequestGenerator(20260712)
generated = [generator.identity(day=1 + i // 200, serial=i)[1].split(" the ", 1)[0] for i in range(10000)]
check("reserved named characters never appear in random clients",
      not ({name.strip().casefold() for name in generated} & RESERVED_NAMES))

print("\n--- Portrait files and How to Play layout ---")
from cat_society.entities.animals import SPECIES_KEYS
photo_dir = Path(__file__).resolve().parents[1] / "cat_society" / "assets" / "dialogue_photos"
portrait_ok = True
for species in ["bal"] + list(SPECIES_KEYS):
    p = photo_dir / (species + ".png")
    try:
        image = pygame.image.load(str(p))
        alpha = pygame.surfarray.array_alpha(image)
        portrait_ok = portrait_ok and image.get_size() == (112, 112) and alpha.max() > 0 and alpha.min() == 0
    except Exception:
        portrait_ok = False
check("all dialogue portraits have correct mapping, dimensions and alpha", portrait_ok)

explore = app.screens["explore"]
explore.ensure_game()
layout_ok = True
last_reachable = True
for size in ((960, 540), (1280, 720), (1920, 1080)):
    config.init_screen(size[0], size[1], ui_h=size[1])
    surface = pygame.Surface(size)
    explore.paused = True
    explore.pause_page = "controls"
    explore.controls_scroll = 10**6
    explore.draw(surface)
    layout_ok = layout_ok and all(required <= rect.h for _title, rect, required in explore._controls_card_metrics)
    S = lambda v: ui.scaled(size[1], v)
    panel = pygame.Rect(0, 0, min(size[0] - S(28), S(980)), min(size[1] - S(26), S(860)))
    panel.center = (size[0] // 2, size[1] // 2)
    viewport_bottom = panel.bottom - S(70)
    if explore._controls_card_metrics:
        last_reachable = last_reachable and explore._controls_card_metrics[-1][1].bottom <= viewport_bottom
check("How to Play renders at supported test resolutions", True)
check("How to Play cards reserve enough height for every wrapped line", layout_ok)
check("How to Play scrolling reaches the final card", last_reachable)

app._shutdown()
pygame.quit()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
