"""Focused headless checks for the v28 stabilization and day/night pass."""
import os
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

_DATA = tempfile.mkdtemp(prefix="bsg-v28-")
_EXPORTS = tempfile.mkdtemp(prefix="bsg-v28-exports-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _DATA
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = _EXPORTS
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()

from cat_society.app import App
from cat_society import paths
from cat_society.entities.animals import SPECIES
from cat_society.music.project import Project
from cat_society.story.requests import RequestGenerator
from cat_society.story.scoring import project_content_hash, score_song
from cat_society.render.daynight import DayNightRenderer

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


# Request identities and prose stay readable and task generation remains broad.
gen = RequestGenerator(90210)
identities = [gen.identity(1 + i // 50, i + 1, tuple(SPECIES)[i % len(SPECIES)])[1]
              for i in range(500)]
check("generated client names never contain numeric suffixes",
      all(not re.search(r"\d", name) for name in identities))
requests = [gen.generate(1 + i // 120, i + 1,
                         ("frog", "owl", "fox", "dog", "turtle", "horse", "rabbit")[i % 7],
                         visit=i % 4)
            for i in range(1200)]
check("request dialogue avoids em and en dashes",
      all("—" not in r["flavor"] and "–" not in r["flavor"] for r in requests))
check("light-source commissions are reachable",
      any(r.get("light_task") for r in requests)
      and any(r.get("light_task") and r.get("service") in ("plant", "gramophone") for r in requests))

# Static portraits are literal captures from the in-world procedural renderer.
portrait_dir = Path("cat_society/assets/story/portraits")
portrait_names = set(SPECIES) | {"bal"}
check("every animal and Bal have a saved in-game portrait",
      all((portrait_dir / (name + ".png")).is_file()
          and (portrait_dir / (name + ".png")).stat().st_size > 100
          for name in portrait_names))

# Day/night visuals differ, night one has an aurora, and music lights brighten locally.
renderer = DayNightRenderer(240, 135, seed=77)
shots = []
for minute in (12 * 60, 18 * 60 + 40, 23 * 60):
    surf = pygame.Surface((240, 135))
    renderer.draw_sky(surf, minute, 1, 2.0)
    shots.append(pygame.image.tostring(surf, "RGB"))
check("noon, sunset, and night skies are visibly different", len(set(shots)) == 3)
check("night one always enables the aurora", renderer.aurora_active(1))
night = pygame.Surface((240, 135))
night.fill((18, 22, 32))
before = sum(night.get_at((120 + dx, 80))[i] for dx in (-2, 0, 2) for i in range(3))
renderer.draw_music_lights(night, [(120, 80, 32, (255, 180, 90), 1.0)], 23 * 60)
after = sum(night.get_at((120 + dx, 80))[i] for dx in (-2, 0, 2) for i in range(3))
check("sprout and gramophone light halos brighten the night locally", after > before)

# Arrangement freshness ignores a rename but reacts to a musical edit.
project = Project("First Name")
hash_a = project_content_hash(project)
project.name = "Second Name"
hash_b = project_content_hash(project)
project.tracks[0].add("note.meadow.c4", 0)
hash_c = project_content_hash(project)
check("renaming a song does not reset its freshness hash", hash_a == hash_b)
check("editing an arrangement changes its freshness hash", hash_c != hash_b)
profile = SimpleNamespace(has_melody=True, has_chords=True, has_bass=True, has_drums=True,
                          tag_counts={"warm": 4, "soft": 2}, clip_count=6,
                          tempo=90, energy="low", bars=12)
request = {"needs": ("melody",), "primary": "warm", "support_tags": ("soft",),
           "tempo": (80, 100), "energy": "low", "min_bars": 8, "min_clips": 4}
check("reselling the same arrangement lowers its score",
      score_song(profile, request, times_sold=1).total < score_song(profile, request, times_sold=0).total)

app = App()

# Maker Load and playback lock.
saved = Project("Completed Project")
app.projects.save(saved)
app.refresh_projects()
app.goto("maker")
maker = app.current
maker._open_load()
check("Maker exposes a load browser for saved projects", maker.load_modal is not None)
maker._load_selected(next(p for p in app.project_list if p.id == saved.id))
check("Maker loads a completed project into the editor", maker.project.id == saved.id)
old_tempo, old_bars, old_id = maker.project.tempo, maker.project.bars, maker.project.id
real_is_playing = app.engine.is_playing
app.engine.is_playing = lambda: True
maker._tempo(10)
maker._bars(2)
maker._new()
maker._open_load()
check("tempo, bars, New, and Load are frozen during playback",
      maker.project.tempo == old_tempo and maker.project.bars == old_bars
      and maker.project.id == old_id and maker.load_modal is None)
app.engine.is_playing = real_is_playing

# Reset preserves shared user files, clears both gameplay profiles, and leaves a drawable menu.
sample_marker = Path(paths.samples_dir()) / "keep-me.txt"
sample_marker.write_text("sample", encoding="utf-8")
export_marker = Path(paths.exports_dir()) / "keep-me.wav"
export_marker.write_bytes(b"RIFF")
Path(app.story_profile_dir).mkdir(parents=True, exist_ok=True)
(Path(app.story_profile_dir) / "story.json").write_text("{}", encoding="utf-8")
app.open_creative_profile()
Path(paths.base_save_dir(), "world.json").write_text(
    '{"seed": 123, "flags": {"old": true}, "data": {"old": 1}}', encoding="utf-8")
Path(paths.base_save_dir(), "collection.json").write_text(
    '{"found": ["old.component"], "counts": {"old.component": 9}}', encoding="utf-8")
Path(paths.projects_dir(), "temp.json").write_text("{}", encoding="utf-8")
app.goto("menu")
app.screens["menu"].dialog = "reset"
reset_ok = app.reset_progress()
app.screens["menu"].draw(app.window)
check("Reset Progress completes without crashing", reset_ok)
check("Reset clears old Creative and Story gameplay data",
      app.world_state.seed != 123 and not app.world_state.flags
      and not app.project_list and not Path(app.story_profile_dir).exists())
check("Reset preserves imported samples and exported audio",
      sample_marker.exists() and export_marker.exists())
check("Reset returns the menu to a clean dialog state",
      app.screens["menu"].dialog is None)

# Story sleep resolves the closed night and reaches a fresh morning.
app.start_story(new=True)
story = app.current
story.intro.phase = "done"
story.story_state.intro_complete = True
story.shop.x = 0.0
story.shop.z = 0.0
story.shop.built = 1.0
story._clients_started = True
story.clients.started = True
story.clock.set_time(22 * 60)
story._sleep_until_morning()
check("sleep after closing advances to the next day at 08:30",
      story.clock.day == 2 and abs(story.clock.minutes - 510.0) < 0.01)

app._shutdown()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
