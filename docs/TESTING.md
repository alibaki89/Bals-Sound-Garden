# Verification and testing

This public source snapshot preserves the game modules and art assets byte for byte. It does not claim that moving test files proves runtime correctness.

## Local syntax check

```bash
python -m compileall -q main.py cat_society tests tools
```

## Game regression scripts

The 23 supplied root-level regression scripts are now grouped in `tests/`. Run from the **repository root**, for example:

```bash
# macOS/Linux
export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy
# PowerShell
# $env:SDL_VIDEODRIVER="dummy"; $env:SDL_AUDIODRIVER="dummy"
python -m tests._integration_test
python -m tests._release_hardening_test
python -m tests._maker_input_regression_test
python -m tests._packaging_release_test
```

The scripts may create temporary source builds, files and runtime state; run in a fresh environment. Tests reference original project behavior; three test scripts had their filesystem-root calculation updated when they were moved under `tests/`, without altering their assertions or the game modules.

## Manual acceptance

Before publishing any new platform executable, verify the Story introduction and shop placement, Explore movement and sound pickups, Music Maker composition/playback, WAV export, pause/quit/resume, saving and loading, sound sprouts and gramophones, client deadlines, helper contracts and night/day scenes.

## What was executed in this preparation

- All original game Python source files passed byte-for-byte hash comparison against the supplied archive.
- All Python source and moved test scripts passed syntax compilation.
- Static website assets, navigation and local links were checked.
- An executable game smoke test **was not performed** in this environment because Pygame is unavailable here. The previous release report included test claims from earlier builds; those results have not been independently rerun for this source-preparation exercise.
