# Cross-platform PyInstaller specification for Bal's Sound Garden.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

APP_NAME = "BalsSoundGarden"
MAC_APP_NAME = "Bal's Sound Garden.app"
MAC_BUNDLE_ID = "com.alibaghiparikhani.balssoundgarden"

datas = collect_data_files("cat_society", includes=["assets/**/*"])

analysis = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["scipy"],
    noarchive=False,
)

pyz = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

exe_options = {}
if sys.platform == "darwin":
    target_arch = os.environ.get("PYI_TARGET_ARCH", "").strip()
    if target_arch:
        exe_options["target_arch"] = target_arch
    exe_options["codesign_identity"] = None
    exe_options["entitlements_file"] = None

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    **exe_options,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name=MAC_APP_NAME,
        icon=None,
        bundle_identifier=MAC_BUNDLE_ID,
        info_plist={
            "CFBundleName": "Bal's Sound Garden",
            "CFBundleDisplayName": "Bal's Sound Garden",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.games",
            "LSMinimumSystemVersion": "14.0",
        },
    )
