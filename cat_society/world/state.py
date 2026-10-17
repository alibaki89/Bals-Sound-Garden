"""Persistent world state: the garden remembers itself between launches.

Before this file existed the world seed was rerolled every launch, so the
meadow forgot its own layout and no place could ever feel like *a place*.
Now the seed is rolled once, saved to ``save/world.json``, and reused forever
(until the player resets), together with everything the player has changed in
the world:

* everything the garden systems persist: planted sprouts, gramophones,
  finished Garden Works, machine meters,
* which animal friends have given their one little gift,
* small story flags (intro seen, garden-complete card shown).

The file is tiny, human-readable JSON, written eagerly on every change --
the same philosophy as :mod:`cat_society.components.collection`.
"""

import json
import os
import random
import time

from .. import paths
from ..logging_utils import get_logger
from ..persistence import PersistenceError, atomic_write_json

_LOG = get_logger("world_state")


def _state_path():
    return os.path.join(paths.save_dir(), "world.json")


class WorldState:
    def __init__(self):
        self.seed = None
        self.flags = {}               # small one-shot story flags
        self.data = {}                # everything the garden systems persist:
                                      # sprouts, gramophones, works, machines...
        self.load()
        if self.seed is None:
            self.seed = random.randrange(1, 2_000_000_000)
            self.save()

    # -- persistence --------------------------------------------------------
    def load(self):
        previous = (self.seed, dict(self.flags), dict(self.data))
        try:
            with open(_state_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise TypeError("world root must be an object")
            seed = d.get("seed")
            flags = d.get("flags", {}) or {}
            data = d.get("data", {}) or {}
            if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
                raise TypeError("world seed must be an integer")
            if not isinstance(flags, dict) or not isinstance(data, dict):
                raise TypeError("world flags/data must be objects")
            self.seed = seed
            self.flags = flags
            self.data = data
            # Route replay was removed from the game. Discard only known old
            # route payloads; all other legacy keys remain untouched.
            removed_routes = False
            for key in ("route_ghost", "route_ghosts"):
                if key in self.data:
                    self.data.pop(key, None)
                    removed_routes = True
            for key in ("taught_record", "ghost_slot_2"):
                if key in self.flags:
                    self.flags.pop(key, None)
                    removed_routes = True
            if removed_routes:
                self.save()
        except FileNotFoundError:
            return
        except (ValueError, TypeError, KeyError, UnicodeError, OSError):
            self.seed, self.flags, self.data = previous
            _LOG.exception("Could not load world.json; keeping the previous valid state")

    def save(self):
        try:
            return atomic_write_json(_state_path(), {
                "seed": self.seed,
                "flags": self.flags,
                "data": self.data,
            }, indent=1)
        except PersistenceError:
            _LOG.exception("Could not save world progress")
            return False

    # -- generic persisted data ---------------------------------------------
    def data_list(self, key):
        v = self.data.get(key)
        return v if isinstance(v, list) else []

    def set_data_list(self, key, value):
        previous = self.data.get(key, None)
        self.data[key] = list(value)
        if self.save():
            return True
        if previous is None:
            self.data.pop(key, None)
        else:
            self.data[key] = previous
        return False

    def data_dict(self, key):
        v = self.data.setdefault(key, {})
        if not isinstance(v, dict):
            v = self.data[key] = {}
        return v

    def touch(self):
        """Call after mutating a dict from :meth:`data_dict`."""
        return self.save()

    # -- flags ------------------------------------------------------------------
    def flag(self, name):
        return bool(self.flags.get(name))

    def set_flag(self, name, value=True):
        value = bool(value)
        previous_present = name in self.flags
        previous = self.flags.get(name)
        if bool(previous) == value:
            return True
        self.flags[name] = value
        if self.save():
            return True
        if previous_present:
            self.flags[name] = previous
        else:
            self.flags.pop(name, None)
        return False

    # -- reset --------------------------------------------------------------------
    def reset(self):
        """Fresh garden: new seed, empty beds, blank works ledger."""
        previous = (self.seed, self.flags, self.data)
        self.seed = random.randrange(1, 2_000_000_000)
        self.flags = {}
        self.data = {}
        if self.save():
            return True
        self.seed, self.flags, self.data = previous
        return False
