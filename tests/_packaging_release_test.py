"""Clean release staging and wheel asset regression checks."""
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMP = Path(tempfile.mkdtemp(prefix="bsg-packaging-test-"))
passed = failed = 0


def check(label, condition):
    global passed, failed
    ok = bool(condition)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


stage = TEMP / "stage"
archive = TEMP / "release.zip"
result = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "build_release.py"),
     "--output", str(stage), "--archive", str(archive)],
    cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
check("clean release staging command succeeds", result.returncode == 0)
check("clean release archive is created", archive.is_file())
files = [p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()]
prohibited_suffixes = {".pyc", ".pyo", ".log", ".tmp", ".zip"}
prohibited_names = {"collection.json", "world.json", "story.json", "settings.json"}
check("release staging contains no bytecode, logs, temp files or nested archives",
      not [p for p in files if Path(p).suffix.lower() in prohibited_suffixes])
check("release staging contains no bundled player progress",
      not [p for p in files if Path(p).name in prohibited_names])
check("release staging contains no tests or development design notes",
      not [p for p in files if "test" in Path(p).name.lower()
           or Path(p).name in {"ANIMALS.md", "COMPONENT_DNA.md", "INTERFACE_CLEANUP.md"}])
check("release staging retains required runtime WAV asset",
      "cat_society/assets/sfx/water_splash.wav" in files)
check("release manifest is present", "RELEASE_MANIFEST.json" in files)

wheel_dir = TEMP / "wheel"
wheel_dir.mkdir()
wheel_result = subprocess.run(
    [sys.executable, "-m", "pip", "wheel", ".", "--no-deps",
     "--no-build-isolation", "-w", str(wheel_dir)],
    cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
check("wheel build succeeds", wheel_result.returncode == 0)
wheels = list(wheel_dir.glob("*.whl"))
check("exactly one wheel is produced", len(wheels) == 1)
if wheels:
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        entry = next((n for n in names if n.endswith("entry_points.txt")), None)
        entry_text = wheel.read(entry).decode("utf-8") if entry else ""
        check("wheel uses current distribution metadata",
              wheels[0].name.startswith("bals_sound_garden-1.0.0"))
        check("wheel exposes the current console command",
              "bals-sound-garden = cat_society.app:main" in entry_text)
        check("wheel includes menu animation frames",
              sum("/assets/menu/frame_" in n and n.endswith(".jpg") for n in names) == 256)
        check("wheel includes every dialogue portrait",
              sum("/assets/dialogue_photos/" in n and n.endswith(".png") for n in names) == 21)
        check("wheel includes runtime sound assets",
              any(n.endswith("assets/sfx/water_splash.wav") for n in names)
              and any(n.endswith("assets/sfx/water_splash.mp3") for n in names))
        check("wheel includes release notices",
              any(n.endswith("THIRD_PARTY_NOTICES.md") for n in names)
              and any(n.endswith("ASSET_LICENSE_REVIEW.md") for n in names))

print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
