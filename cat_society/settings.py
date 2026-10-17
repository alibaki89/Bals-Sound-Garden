"""Central, gentle audio settings.

One small place holds the master / music / sfx volumes and a mute toggle, so
the whole game stays balanced and not noisy.  Values persist next to the game
in ``save/settings.json``.  Everything is clamped to soft, comfortable levels.
"""

import json

from . import paths
from .logging_utils import get_logger
from .persistence import PersistenceError, atomic_write_json

_LOG = get_logger("settings")

# defaults are intentionally gentle so nothing is ever jarring
_DEFAULTS = {"master": 0.8, "music": 0.85, "sfx": 0.6, "muted": False}

_state = dict(_DEFAULTS)


def load():
    previous = dict(_state)
    try:
        with open(paths.settings_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise TypeError("settings root must be an object")
        for key in _DEFAULTS:
            if key in data:
                _state[key] = data[key]
        _clamp()
    except FileNotFoundError:
        return
    except (OSError, ValueError, TypeError, UnicodeError):
        _state.clear()
        _state.update(previous)
        _LOG.exception("Could not load settings.json; keeping previous settings")


def save():
    try:
        return atomic_write_json(paths.settings_file(), _state, indent=1)
    except PersistenceError:
        _LOG.exception("Could not save settings")
        return False


def _clamp():
    for k in ("master", "music", "sfx"):
        _state[k] = max(0.0, min(1.0, float(_state[k])))
    _state["muted"] = bool(_state["muted"])


def get(key):
    return _state.get(key, _DEFAULTS.get(key))


def set_value(key, value):
    previous = dict(_state)
    if key in ("master", "music", "sfx"):
        _state[key] = max(0.0, min(1.0, float(value)))
    elif key == "muted":
        _state[key] = bool(value)
    _clamp()
    if save():
        return True
    _state.clear()
    _state.update(previous)
    return False


def toggle_mute():
    previous = bool(_state["muted"])
    _state["muted"] = not previous
    if save():
        return _state["muted"]
    _state["muted"] = previous
    return previous


def music_volume():
    return 0.0 if _state["muted"] else _state["master"] * _state["music"]


def sfx_volume():
    # sfx sit a little under music so they stay in the background
    return 0.0 if _state["muted"] else _state["master"] * _state["sfx"]
