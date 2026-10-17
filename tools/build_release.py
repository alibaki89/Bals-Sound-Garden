#!/usr/bin/env python3
"""Create a clean, reproducible runtime/source release staging directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT_FILES = (
    "main.py", "requirements.txt", "pyproject.toml", "README.md", "BUILDING.md",
    "LICENSE.md", "THIRD_PARTY_NOTICES.md", "CREDITS.md", "ASSET_LICENSE_REVIEW.md", "RELEASE_REPORT.md", "BalSoundGarden.spec",
)
EXCLUDED_PARTS = {
    "__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "save", "exports", "logs", "build", "dist", ".venv", "venv",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".zip"}
PROHIBITED_RELEASE_NAMES = {"collection.json", "world.json", "story.json", "settings.json"}


def allowed_package_file(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return False
    return path.is_file()


def copy_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*")):
        if not allowed_package_file(path):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def inspect(stage: Path):
    violations = []
    files = []
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(stage)
        files.append(relative.as_posix())
        if path.name in PROHIBITED_RELEASE_NAMES:
            violations.append(relative.as_posix())
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            violations.append(relative.as_posix())
        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            violations.append(relative.as_posix())
    return files, sorted(set(violations))


def write_manifest(stage: Path, files):
    records = []
    for relative in files:
        path = stage / relative
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        records.append({"path": relative, "sha256": digest, "bytes": path.stat().st_size})
    manifest = {"game": "Bal's Sound Garden", "version": "1.0.0", "files": records}
    (stage / "RELEASE_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def make_zip(stage: Path, archive: Path):
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(stage.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(stage).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, path.read_bytes())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="release_stage")
    parser.add_argument("--archive")
    args = parser.parse_args()
    stage = Path(args.output).resolve()
    if stage == ROOT or ROOT in stage.parents and stage.name == "cat_society":
        raise SystemExit("Refusing unsafe output directory")
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for filename in RUNTIME_ROOT_FILES:
        source = ROOT / filename
        if not source.is_file():
            raise SystemExit("Required release file is missing: %s" % filename)
        shutil.copy2(source, stage / filename)
    copy_tree(ROOT / "cat_society", stage / "cat_society")
    files, violations = inspect(stage)
    if violations:
        raise SystemExit("Prohibited release files found: %s" % ", ".join(violations))
    write_manifest(stage, files)
    files, violations = inspect(stage)
    if violations:
        raise SystemExit("Prohibited release files found after manifest: %s" % ", ".join(violations))
    if args.archive:
        make_zip(stage, Path(args.archive).resolve())
    print("Release staged at %s" % stage)
    print("Runtime files: %d" % len(files))
    print("Prohibited files: 0")


if __name__ == "__main__":
    main()
