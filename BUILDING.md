# Building Bal's Sound Garden

## Run from source

Use Python 3.8 or newer. The release verification described here was run with Python 3.13.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

## Build and inspect the wheel

```bash
python -m pip install build
python -m build --wheel
python -m zipfile -l dist/bals_sound_garden-1.0.0-py3-none-any.whl
```

The installed command is:

```bash
bals-sound-garden
```

## Create a clean source/runtime release archive

```bash
python tools/build_release.py --output release_stage --archive dist/Bals_Sound_Garden_1.0.0.zip
```

The staging process excludes player saves, song projects, exports, logs, bytecode, caches, tests, design notes, and prior build output.

## Windows executable configuration

Install PyInstaller, then run on Windows:

```powershell
python -m pip install pyinstaller
pyinstaller --clean BalSoundGarden.spec
```

`BalSoundGarden.spec` collects the package assets without machine-specific paths. A Windows executable must be built and smoke-tested on Windows; creating the specification on another operating system does not verify the resulting Windows binary.

## Distribution policy

This repository is primarily a source and engineering showcase. Build locally when verifying changes, but distribute public Windows, macOS and Linux executables from the existing [itch.io page](https://abprojects.itch.io/bals-sound-garden). The historical artifact-building GitHub Actions workflow is intentionally not part of this streamlined repository, and no GitHub Releases are planned.

To make a runtime-only source archive (not a GitHub release), use `tools/build_release.py` as documented above. The source code, assets and specification remain unchanged from the supplied build source.
