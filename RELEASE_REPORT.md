# Bal's Sound Garden 1.0.0 Release-Hardening Report

## Outcome

The identified technical reliability and packaging blockers were repaired with focused patches. The game systems, balance, controls, visuals, audio behavior, story content, progression, randomness, and valid save formats were preserved except where the defect list explicitly required a correction.

The clean runtime archive and Python wheel were produced and verified in Linux/headless Pygame. This report does **not** claim unrestricted final publication approval because two external verification items remain:

1. The Windows PyInstaller configuration was prepared but a Windows executable could not be built or run in this Linux environment.
2. Ownership/licensing for the original game assets has not been established by repository evidence; `ASSET_LICENSE_REVIEW.md` lists the exact owner decisions still required.

The exhaustive 2,946-component sound-matching scan was started but did not finish within a 20-minute audit window. It reached component 250 without reporting a failure. All other listed automated suites completed successfully.

## Preservation contract

This work was performed as a repair and release-hardening pass. It did not redesign gameplay, add mechanics, rebalance rewards or deadlines, replace frameworks, reorganize the repository, change dialogue/story content, or alter unrelated art.

## Fixes by issue

### 1. Safe song overwrite

**Cause:** The Maker deleted the old project before attempting the replacement and ignored the save result.

**Change:** Project saving now serializes and validates first, writes a unique temporary file in the destination directory, flushes and fsyncs it, validates the temporary JSON, and commits with `os.replace()`. Existing projects are removed only after the replacement is committed. The Maker reports success only from a true save result, keeps failed work dirty and open, displays a friendly failure message, and logs technical details.

**Verification:** A mocked `os.replace()` failure preserved the original bytes, created no replacement, left no temporary file, did not show “Saved,” and left the composition dirty.

**Compatibility:** Valid existing projects retain their external JSON structure and remain loadable.

### 2. Malformed project handling

**Cause:** Multiple UI paths assumed project dictionaries were complete and caught too few parser exceptions.

**Change:** `cat_society.music.project` now provides authoritative validation and `cat_society.music.store` is the single safe load/list path. Invalid files are preserved in place, skipped, logged, and surfaced through a non-blocking warning naming the filename. Supported older projects are loaded conservatively rather than quarantined.

**Verification:** Tested empty, truncated, invalid JSON, `{}`, missing/wrong `name`, invalid tracks/steps/types/version structures, unreadable-file simulation, and valid projects beside invalid files. Startup, Your Music, Maker, name checks, load lists, and playback-facing access remained usable.

**Compatibility:** Older valid projects remain supported, including the existing v24-style project fixture.

### 3. Atomic central saves

**Cause:** Collection, world, story, settings, sample index, and song JSON were written directly to final paths; some callers ignored failures.

**Change:** Added `cat_society.persistence.atomic_write_json()` and converted central writers to explicit success/failure behavior. The utility creates parents, serializes first, writes a unique same-directory temporary file, flushes, fsyncs, validates, atomically replaces, logs failures, and removes temporary files. Mutating callers roll back in-memory changes where a failed persistence operation would otherwise falsely advance state.

**Verification:** First save, overwrite, serialization failure, temporary-write/replacement failure, original preservation, in-memory rollback, and no abandoned temporary files were tested for collection, world, story, settings and song data.

**Compatibility:** Existing JSON keys and meanings were preserved; no migration is required.

### 4. Courier delivery transaction

**Cause:** Courier logic rewarded/completed jobs without checking whether the world object was created or whether a gramophone project loaded.

**Change:** Courier assignment validates its source. Completion verifies the placed sprout/gramophone in world state before rewarding. Failed placement/project loading keeps the mission recoverable, consumes nothing permanently, awards nothing, logs one useful failure, delays retry, and prevents object/reward duplication. A failed post-placement state save rolls back the placed object/resource.

**Verification:** Successful/failed sprout delivery, successful gramophone delivery, missing/invalid project, insertion failure, delayed retry, no duplicate object, and no duplicate reward were tested.

**Compatibility:** Successful reward values and deadlines are unchanged.

### 5. Clean release staging

**Cause:** The development tree contained tests, bytecode/cache output, internal design documents, a player world save, and exports.

**Change:** Added `tools/build_release.py`, a clean whitelist staging process. It starts from an empty directory, copies only approved runtime code/assets/release documents, rejects prohibited names/suffixes, writes a SHA-256 manifest, and creates a consistently structured archive. Development files remain available in the source repository but are excluded from runtime releases.

**Verification:** The final staged release contains no player saves, songs, exports, logs, tests, design notes, nested archives, bytecode, caches or temporary files. The staged game starts in a clean state, saves progress/song data, restarts, and reloads it.

**Compatibility:** New-player starting behavior is unchanged; no default progress is bundled.

### 6. Package assets and metadata

**Cause:** The old wheel omitted runtime assets and active metadata/entry points used obsolete NineLives branding.

**Change:** Updated `pyproject.toml` to `bals-sound-garden`, current description/version/console command, package data for all assets, and release documents. Added `BalSoundGarden.spec` and real build instructions. Resource paths remain package-relative and work from source and installed wheel.

**Verification:** Built and inspected the wheel; it contains 256 menu frames, 21 portraits, MP3/WAV sound assets and release notices. Installed into a clean virtual environment and launched/imported from `/tmp` outside the repository.

**Compatibility:** Internal `cat_society` package imports remain unchanged. The new command is `bals-sound-garden`.

### 7. Unsaved Maker confirmation

**Cause:** Escape, New and Load replaced/left a project without tracking whether the saved representation had changed.

**Change:** Added canonical representation-based dirty tracking. Meaningful edits mark dirty; hover, scroll and playback do not. Successful save/load establishes a clean baseline; failed save remains dirty. Every destructive exit/replacement path uses the same Stay / Leave without saving confirmation.

**Verification:** Clean/dirty Escape, New, Load, failed save then exit, successful save then exit, cancel/confirm discard, edit dirtying, and non-mutating interactions were tested.

**Compatibility:** Composition and save formats are unchanged.

### 8. Your Music Stop dispatch

**Cause:** The Stop-labelled button invoked the play action again.

**Change:** The existing control now calls the real stop path while playing and returns to its non-playing state. Existing leave/switch behavior stops playback as expected.

**Verification:** Instrumented call sequence is `play`, then `stop`; no second `play` call occurs.

**Compatibility:** Visual layout and playback engine behavior are unchanged.

### 9. Scrolled Maker Load mapping

**Cause:** Visible rows after scrolling were mapped as though the list started at index zero.

**Change:** Load rows now carry one explicit absolute project index used consistently by hover, click, keyboard movement and Enter.

**Verification:** Lists longer than seven were tested at multiple offsets; hover, click and activation all load the displayed absolute project.

**Compatibility:** Row count and appearance are unchanged.

### 10. How to Play clipping

**Cause:** Fixed card heights did not account for wrapped line count.

**Change:** Card heights are measured from the existing text, and the existing panel supports bounded scrolling with mouse wheel, arrows and Page Up/Down plus a styled scrollbar. No instruction was removed or reduced to unreadable text.

**Verification:** Rendered at supported test resolutions; every measured line fits its card, cards do not overlap, and the final card is reachable.

**Compatibility:** Existing visual style and instructions were preserved, except factually outdated text corrected under issue 14.

### 11. Accepted commission cancellation

**Cause:** Cancelling an accepted obligation was equivalent to declining an unaccepted offer.

**Change:** Added a one-time early cancellation reputation loss of `0.15`, between the existing ignored-walk-in loss (`0.08`) and missed accepted-deadline loss (`0.40`). Cancellation records history, releases order/delivery state and reports the consequence. Declining an unaccepted offer remains free.

**Verification:** Decline, complete, early cancellation, missed deadline scale, duplicate prevention, history, reservation release and save/reload behavior were tested.

**Compatibility:** No existing reward/deadline values changed.

### 12. Reserved character names

**Cause:** Poko and other established unique/helper names remained in random client pools.

**Change:** Added a central casefolded reserved-name set for Poko, Juniper, Clover, Bramble and Pip; random generation filters only those names.

**Verification:** A large deterministic generated sample produced no reserved names.

**Compatibility:** Established characters were not renamed and unrelated names remain available.

### 13. Portrait consistency

**Cause:** Portraits had inconsistent source/framing and two duplicate asset directories.

**Change:** Added a reproducible portrait generator that starts the real game renderer, places one actual in-game animal alone in the Explore world, isolates the subject from a blank render, extracts the largest connected subject component, crops the head/face with species-aware room for ears/horns/antlers, and writes transparent 112×112 nearest-neighbour PNGs. Replaced all 21 portraits and removed the obsolete duplicate portrait directory. Added a contact sheet.

**Verification:** Every species mapping, identity, dimensions, alpha, visible bounds and real dialogue-box display were inspected in a generated contact sheet and runtime dialogue montage.

**Compatibility:** Filenames and dialogue box layout are unchanged.

### 14. Documentation

**Cause:** README/design/build text described the removed D shortcut, old Controls name, immediate sleep, old portrait approach and NineLives packaging.

**Change:** Updated active player/build documentation to match current input handlers, How to Play naming, sleep confirmation, portrait generation, branding and actual build commands. Historical documents are explicitly marked historical where retained.

**Verification:** Final active repository search found no obsolete NineLives branding or active D-journal/immediate-sleep instructions.

**Compatibility:** Documentation only.

### 15. License and notices

**Cause:** No release-facing ownership/license decision or dependency/asset review existed.

**Change:** Added `LICENSE.md`, `THIRD_PARTY_NOTICES.md`, `CREDITS.md` and `ASSET_LICENSE_REVIEW.md`. They do not invent ownership or licensing terms. The exact original assets and owner decisions still requiring confirmation are identified.

**Verification:** Files are included in the clean archive and wheel.

**Compatibility:** No runtime effect.

### 16. Critical logging

**Cause:** Critical save/load/audio/courier failures could be silently swallowed or visible only as a traceback.

**Change:** Added a bounded rotating release log (`logs/game.log`, 512 KiB, two backups) with timestamps and exception details. Persistence, project parsing, save/load, critical audio startup/playback and courier failure paths now log useful diagnostics while player UI remains friendly. Logging failure itself cannot crash the game.

**Verification:** Failure-injection tests confirmed controlled UI/state behavior, and log creation/rotation configuration was inspected.

**Compatibility:** No gameplay effect; player data locations remain unchanged.

### 17. Memory investigation

**Cause investigated:** The process includes Python, Pygame, NumPy, SciPy, the generated sound catalog and eagerly constructed screens. No unbounded screen-transition leak was found.

**Change:** No speculative optimization was applied because no safe change was demonstrated that would preserve transition responsiveness and sound/visual behavior.

**Verification:** Three-run median comparison is recorded below. The app-owned menu delta over the process pre-import baseline was essentially unchanged (37.28 MiB baseline vs 37.38 MiB final), and 30 repeated transitions added the same 3.93 MiB in both builds.

**Compatibility:** Behavior intentionally unchanged.

## Performance comparison

Three independent headless runs per build were measured with the same script and environment; values are medians.

| Checkpoint | v39 baseline | hardened final | Change |
|---|---:|---:|---:|
| Import | 1.2632 s | 1.2411 s | -1.8% |
| App initialization | 0.4018 s | 0.3986 s | -0.8% |
| Menu draw average | 6.2623 ms | 6.0575 ms | -3.3% |
| Explore entry | 0.1736 s | 0.1735 s | -0.05% |
| Explore draw average | 16.2555 ms | 16.5416 ms | +1.8% |
| Maker draw average | 7.9306 ms | 7.8220 ms | -1.4% |
| 30 transitions | 0.0050 s | 0.0048 s | -4.4% |
| App-owned menu RSS delta over pre-import baseline | 37.28 MiB | 37.38 MiB | +0.10 MiB |
| Menu-to-30-transition RSS growth | 3.93 MiB | 3.93 MiB | unchanged |

The Maker entry measurement was approximately 1–2 milliseconds and too small/noisy for a meaningful percentage comparison. No consistent practical regression above 5% was observed.

## Automated test results

Commands were run with dummy SDL video/audio drivers where headless rendering was required.

```bash
python -m py_compile $(find cat_society -name '*.py')
python _release_hardening_test.py
python _packaging_release_test.py
```

Focused release tests:

- `_release_hardening_test.py`: **66 passed, 0 failed**
- `_packaging_release_test.py`: **15 passed, 0 failed**

Existing suites completed successfully:

- `_export_portability_test.py`
- `_freeplay_polish_test.py` — 23/23
- `_garden_test.py` — 53/53
- `_golden_polish_test.py` — 12/12
- `_integration_test.py`
- `_legato_test.py`
- `_maker_input_regression_test.py`
- `_maker_ui_tidy_test.py` — 30/30
- `_procedural_generation_test.py` — 18/18
- `_sound_atlas_test.py` — 25/25
- `_story_live_shop_test.py` — 20/20
- `_story_shop_test.py` — 21/21
- `_ui_touchup_test.py` — 18/18
- `_v28_stability_test.py` — 18/18
- `_v29_visual_reset_test.py` — 13/13
- `_v30_night_intro_polish_test.py` — 14/14
- `_v31_money_progression_test.py` — 38/38
- `_v32_helper_journal_test.py` — 7/7
- `_v33_dialogue_menu_test.py` — 7/7
- `_v35_sleep_confirm_test.py` — 4/4

The exhaustive `_sound_match_test.py` was terminated after the 20-minute audit window. It had reached 250/2,946 components and had not reported a failure. It is not recorded as passed.

## Clean-room verification

A fresh staged release was launched from a temporary directory with temporary data/export locations.

Verified:

- Empty collection/project/story state on first start
- Create and persist progress
- Create and save a song
- Successful overwrite
- Mocked failed overwrite preserves original
- Malformed project remains on disk and does not block Your Music/Maker
- Restart restores valid progress/song
- More than seven projects map correctly in Load
- Dirty confirmations work
- Courier success/failure transactions work
- Valid original v39 save fixtures load and Explore draws
- Existing older v24-style song fixture loads and re-saves compatibly

## Packaging results

### Clean runtime archive

Generated with:

```bash
python tools/build_release.py \
  --output /path/to/stage \
  --archive /path/to/Bals_Sound_Garden_1.0.0_Clean_Release.zip
```

The archive is produced from a clean directory and contains runtime code/assets, required documents and `RELEASE_MANIFEST.json`. It contains no bundled player state, songs, exports, tests, logs, caches, bytecode or development documents.

### Wheel

Generated with:

```bash
python -m build --wheel
```

Wheel metadata:

- Distribution: `bals-sound-garden`
- Version: `1.0.0`
- Console command: `bals-sound-garden`
- Internal package: `cat_society`

The wheel was installed into a clean virtual environment and launched/imported from outside the repository. Required menu, portrait and sound assets were present.

### Windows executable

A reproducible `BalSoundGarden.spec` is provided and documented in `BUILDING.md`. A Windows executable was not built or tested because the verification environment is Linux. No cross-platform binary claim is made.

## Save compatibility

Existing valid v39 collection/world/story saves and saved song projects remain supported. Existing keys and meanings were preserved. Older valid song structures covered by the v24 compatibility fixture remain supported. No destructive migration is performed. Malformed files are preserved and skipped with a warning rather than reinterpreted as valid progress.

## Files changed

### Added

- `ASSET_LICENSE_REVIEW.md`
- `BUILDING.md`
- `BalSoundGarden.spec`
- `CREDITS.md`
- `DIALOGUE_PORTRAITS_CONTACT_SHEET.png`
- `LICENSE.md`
- `RELEASE_REPORT.md`
- `THIRD_PARTY_NOTICES.md`
- `_packaging_release_test.py`
- `_release_hardening_test.py`
- `cat_society/logging_utils.py`
- `cat_society/persistence.py`
- `tools/build_release.py`
- `tools/generate_dialogue_portraits.py`

### Modified

- `ANIMALS.md`
- `COMPONENT_DNA.md`
- `EXPORTING.md`
- `INTERFACE_CLEANUP.md`
- `LEGATO.md`
- `MONEY_AND_SHOP_GROWTH.md`
- `MUSIC_MAKER_UI_TIDY.md`
- `README.md`
- `STORY_SHOP.md`
- `V32_HELPERS_AND_JOURNAL.md`
- `V33_TIDY_MENUS_AND_WORLD_PHOTOS.md`
- `_integration_test.py`
- `cat_society/app.py`
- all 21 files under `cat_society/assets/dialogue_photos/`
- `cat_society/audio/engine.py`
- `cat_society/audio/samples.py`
- `cat_society/components/collection.py`
- `cat_society/config.py`
- `cat_society/music/project.py`
- `cat_society/music/store.py`
- `cat_society/screens/explore.py`
- `cat_society/screens/maker.py`
- `cat_society/screens/story.py`
- `cat_society/screens/your_music.py`
- `cat_society/settings.py`
- `cat_society/story/clients.py`
- `cat_society/story/dialogue.py`
- `cat_society/story/requests.py`
- `cat_society/story/state.py`
- `cat_society/world/garden.py`
- `cat_society/world/sprouts.py`
- `cat_society/world/state.py`
- `pyproject.toml`

### Removed

- all 21 obsolete duplicate files under `cat_society/assets/dialogue_shots/`
- bundled player progress file `save/world.json`

### Excluded only from runtime release staging

- all development test scripts
- internal/historical design documents not on the runtime whitelist
- `tools/`
- `save/`, `exports/`, `logs/`
- `.git/`, caches, bytecode, build output and local environments

## Remaining concerns

1. **Asset/license decision:** The repository does not establish a public license or provenance for the original code/art/audio. `ASSET_LICENSE_REVIEW.md` identifies the precise owner decisions required before public distribution.
2. **Windows binary verification:** The spec is prepared, but the actual `.exe` must be built and smoke-tested on Windows.
3. **Exhaustive audio scan:** `_sound_match_test.py` did not complete within the audit window and cannot honestly be reported as passed.
## Exact changed-file inventory

Relative to the supplied v39 baseline:

```text
M	ANIMALS.md
A	ASSET_LICENSE_REVIEW.md
A	BUILDING.md
A	BalSoundGarden.spec
M	COMPONENT_DNA.md
A	CREDITS.md
A	DIALOGUE_PORTRAITS_CONTACT_SHEET.png
M	EXPORTING.md
M	INTERFACE_CLEANUP.md
M	LEGATO.md
A	LICENSE.md
M	MONEY_AND_SHOP_GROWTH.md
M	MUSIC_MAKER_UI_TIDY.md
M	README.md
A	RELEASE_REPORT.md
M	STORY_SHOP.md
A	THIRD_PARTY_NOTICES.md
M	V32_HELPERS_AND_JOURNAL.md
M	V33_TIDY_MENUS_AND_WORLD_PHOTOS.md
M	_integration_test.py
A	_packaging_release_test.py
A	_release_hardening_test.py
M	cat_society/app.py
M	cat_society/assets/dialogue_photos/bal.png
M	cat_society/assets/dialogue_photos/bird.png
M	cat_society/assets/dialogue_photos/butterfly.png
M	cat_society/assets/dialogue_photos/chicken.png
M	cat_society/assets/dialogue_photos/cow.png
M	cat_society/assets/dialogue_photos/deer.png
M	cat_society/assets/dialogue_photos/dog.png
M	cat_society/assets/dialogue_photos/duck.png
M	cat_society/assets/dialogue_photos/fox.png
M	cat_society/assets/dialogue_photos/frog.png
M	cat_society/assets/dialogue_photos/goat.png
M	cat_society/assets/dialogue_photos/hedgehog.png
M	cat_society/assets/dialogue_photos/horse.png
M	cat_society/assets/dialogue_photos/owl.png
M	cat_society/assets/dialogue_photos/pig.png
M	cat_society/assets/dialogue_photos/rabbit.png
M	cat_society/assets/dialogue_photos/raccoon.png
M	cat_society/assets/dialogue_photos/sheep.png
M	cat_society/assets/dialogue_photos/squirrel.png
M	cat_society/assets/dialogue_photos/tanuki.png
M	cat_society/assets/dialogue_photos/turtle.png
D	cat_society/assets/dialogue_shots/bal.png
D	cat_society/assets/dialogue_shots/bird.png
D	cat_society/assets/dialogue_shots/butterfly.png
D	cat_society/assets/dialogue_shots/chicken.png
D	cat_society/assets/dialogue_shots/cow.png
D	cat_society/assets/dialogue_shots/deer.png
D	cat_society/assets/dialogue_shots/dog.png
D	cat_society/assets/dialogue_shots/duck.png
D	cat_society/assets/dialogue_shots/fox.png
D	cat_society/assets/dialogue_shots/frog.png
D	cat_society/assets/dialogue_shots/goat.png
D	cat_society/assets/dialogue_shots/hedgehog.png
D	cat_society/assets/dialogue_shots/horse.png
D	cat_society/assets/dialogue_shots/owl.png
D	cat_society/assets/dialogue_shots/pig.png
D	cat_society/assets/dialogue_shots/rabbit.png
D	cat_society/assets/dialogue_shots/raccoon.png
D	cat_society/assets/dialogue_shots/sheep.png
D	cat_society/assets/dialogue_shots/squirrel.png
D	cat_society/assets/dialogue_shots/tanuki.png
D	cat_society/assets/dialogue_shots/turtle.png
M	cat_society/audio/engine.py
M	cat_society/audio/samples.py
M	cat_society/components/collection.py
M	cat_society/config.py
A	cat_society/logging_utils.py
M	cat_society/music/project.py
M	cat_society/music/store.py
A	cat_society/persistence.py
M	cat_society/screens/explore.py
M	cat_society/screens/maker.py
M	cat_society/screens/story.py
M	cat_society/screens/your_music.py
M	cat_society/settings.py
M	cat_society/story/clients.py
M	cat_society/story/dialogue.py
M	cat_society/story/requests.py
M	cat_society/story/state.py
M	cat_society/world/garden.py
M	cat_society/world/sprouts.py
M	cat_society/world/state.py
M	pyproject.toml
D	save/world.json
A	tools/build_release.py
A	tools/generate_dialogue_portraits.py
```
