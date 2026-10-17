"""Portable locations for Bal's Sound Garden data and exports.

Development checkouts remain self-contained by default, but packaged/system
installs use a per-user writable data directory.  This avoids writing into
Program Files, read-only app bundles, Linux package directories, or
PyInstaller's temporary one-file extraction folder.

Environment overrides are intentionally supported for tests and portable
builds::

    BAL_SOUND_GARDEN_DATA_DIR=/path/to/data
    BAL_SOUND_GARDEN_EXPORTS_DIR=/path/to/exports
    BAL_SOUND_GARDEN_PORTABLE=1
"""

import os
import shutil
import sys
import tempfile

APP_DIR_NAME = "BalsSoundGarden"
EXPORT_DIR_NAME = "Bal's Sound Garden Exports"

# Source/package root = parent of the cat_society package directory.
_PACKAGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MIGRATED = False
_ACTIVE_PROFILE = None


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def is_packaged():
    """Return True for the common frozen/app-container launch modes."""
    return bool(
        getattr(sys, "frozen", False)
        or hasattr(sys, "_MEIPASS")
        or os.environ.get("APPIMAGE")
        or os.environ.get("SNAP")
        or os.environ.get("FLATPAK_ID")
    )


def resource_root():
    """Directory containing bundled read-only resources."""
    return getattr(sys, "_MEIPASS", _PACKAGE_ROOT)


def _platform_user_data_root():
    override = os.environ.get("BAL_SOUND_GARDEN_DATA_DIR")
    if override:
        return os.path.abspath(os.path.expanduser(override))

    # Explicit portable mode is useful for an unpacked USB build.
    if _truthy(os.environ.get("BAL_SOUND_GARDEN_PORTABLE")):
        return _PACKAGE_ROOT

    # Keep ordinary source checkouts self-contained unless their directory is
    # not writable.  Packaged/system installs always use per-user storage.
    if not is_packaged() and os.access(_PACKAGE_ROOT, os.W_OK):
        return _PACKAGE_ROOT

    home = os.path.expanduser("~")
    if sys.platform.startswith("win"):
        base = (os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                or os.path.join(home, "AppData", "Local"))
        return os.path.join(base, APP_DIR_NAME)
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", APP_DIR_NAME)

    # python-for-android exposes a private writable application directory.
    android_private = os.environ.get("ANDROID_PRIVATE")
    if android_private:
        return os.path.join(android_private, APP_DIR_NAME)

    base = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(base, APP_DIR_NAME)


_DATA_ROOT = _platform_user_data_root()


def _ensure(path):
    os.makedirs(path, exist_ok=True)
    return path


def _is_writable_dir(path):
    """Create and probe a directory without leaving a file behind."""
    try:
        os.makedirs(path, exist_ok=True)
        fd, probe = tempfile.mkstemp(prefix=".bsg-write-test-", dir=path)
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def _copy_missing(src, dst):
    """Copy a legacy file/tree without overwriting newer user data."""
    if not os.path.exists(src):
        return
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for name in os.listdir(src):
            _copy_missing(os.path.join(src, name), os.path.join(dst, name))
    elif not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            shutil.copy2(src, dst)
        except OSError:
            pass


def _migrate_legacy_once():
    """Import saves from older builds that stored data beside the executable."""
    global _MIGRATED
    if _MIGRATED:
        return
    _MIGRATED = True
    if os.path.abspath(_DATA_ROOT) == os.path.abspath(_PACKAGE_ROOT):
        return
    try:
        _copy_missing(os.path.join(_PACKAGE_ROOT, "save"),
                      os.path.join(_DATA_ROOT, "save"))
    except OSError:
        pass


def root():
    """Writable application-data root (legacy name kept for compatibility)."""
    _migrate_legacy_once()
    return _ensure(_DATA_ROOT)


def base_save_dir():
    """The shared save root. Settings and imported samples always live here."""
    _migrate_legacy_once()
    return _ensure(os.path.join(_DATA_ROOT, "save"))


def set_active_profile(profile_dir):
    """Route gameplay-owned files through ``profile_dir``.

    Passing ``None`` restores the historical Creative profile at ``save/``.
    The indirection is intentionally tiny: collection, world state and project
    storage already ask this module for their paths, so they become isolated
    without knowing anything about story mode.
    """
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = (os.path.abspath(profile_dir) if profile_dir else None)
    if _ACTIVE_PROFILE:
        _ensure(_ACTIVE_PROFILE)


def active_profile():
    return _ACTIVE_PROFILE


def save_dir():
    return _ensure(_ACTIVE_PROFILE) if _ACTIVE_PROFILE else base_save_dir()


def projects_dir():
    return _ensure(os.path.join(save_dir(), "projects"))


def samples_dir():
    return _ensure(os.path.join(base_save_dir(), "samples"))


def _desktop_exports_candidates():
    home = os.path.expanduser("~")
    if not home or home == "~":
        return []
    candidates = []
    override = os.environ.get("BAL_SOUND_GARDEN_EXPORTS_DIR")
    if override:
        candidates.append(os.path.abspath(os.path.expanduser(override)))

    # On mobile/app-sandbox platforms, private app storage is the only location
    # guaranteed to be writable without platform-specific permission APIs.
    if os.environ.get("ANDROID_PRIVATE"):
        candidates.append(os.path.join(_DATA_ROOT, "exports"))
        return candidates

    candidates.extend([
        os.path.join(home, "Music", EXPORT_DIR_NAME),
        os.path.join(home, "Documents", EXPORT_DIR_NAME),
        os.path.join(home, EXPORT_DIR_NAME),
        os.path.join(_DATA_ROOT, "exports"),
    ])
    return candidates


def exports_dir():
    """Return a user-writable default export directory.

    Source/portable builds keep the historical local ``exports`` folder.
    Packaged builds prefer the user's Music folder, with safe fallbacks.
    """
    override = os.environ.get("BAL_SOUND_GARDEN_EXPORTS_DIR")
    if override:
        target = os.path.abspath(os.path.expanduser(override))
        if _is_writable_dir(target):
            return target

    if not is_packaged() and os.path.abspath(_DATA_ROOT) == os.path.abspath(_PACKAGE_ROOT):
        return _ensure(os.path.join(_PACKAGE_ROOT, "exports"))

    for candidate in _desktop_exports_candidates():
        if _is_writable_dir(candidate):
            return candidate

    # Last-resort path.  If this also fails, callers receive the real OSError
    # and can show a useful export failure instead of pretending success.
    return _ensure(os.path.join(_DATA_ROOT, "exports"))


def collection_file():
    return os.path.join(save_dir(), "collection.json")


def settings_file():
    return os.path.join(base_save_dir(), "settings.json")
