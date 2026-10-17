"""The player's collection of found components, persisted to JSON.

Starter components are always considered owned.  Discovery order and a simple
timestamp are kept so the collection screen can show "newest first" and the
explore HUD can show progress.
"""

import json
import time

from ..logging_utils import get_logger
from ..persistence import PersistenceError, atomic_write_json

from . import catalog
from .. import paths

_LOG = get_logger("collection")


class Collection:
    def __init__(self):
        # id -> {"t": unix_time, "order": int}
        self.found = {}
        self._order = 0
        self.collected_pickups = set()   # world instance ids already taken
        self.load()

    # -- queries ----------------------------------------------------------
    def owns(self, cid):
        comp = catalog.get(cid)
        if comp is None:
            return False
        return comp.get("starter", False) or cid in self.found

    def _found_proc(self):
        """Reconstruct every owned procedural component from its saved id."""
        out = []
        for cid in self.found:
            if catalog.procedural.is_proc(cid):
                c = catalog.get(cid)
                if c is not None:
                    out.append(c)
        return out

    def owned_components(self):
        return [c for c in catalog.ALL if self.owns(c["id"])] + self._found_proc()

    def owned_on_track(self, track):
        cur = [c for c in catalog.ALL
               if self.owns(c["id"]) and c.get("track") == track]
        proc = [c for c in self._found_proc() if c.get("track") == track]
        return cur + proc

    def owned_effects(self):
        cur = [c for c in catalog.effects() if self.owns(c["id"])]
        proc = [c for c in self._found_proc() if c.get("type") == "effect"]
        return cur + proc

    def total(self):
        # discoverable components (starters are built-in tools, not finds)
        return len(catalog.placed_components())

    def num_found(self):
        # only genuinely discovered components count (curated + procedural)
        return len([c for c in self.found
                    if not (catalog.get(c) or {}).get("starter")])

    def num_curated_found(self):
        # counts against total(): world-placed curated finds only (gifts and
        # awakening rewards live in their own journal shelf)
        return sum(1 for c in catalog.ALL
                   if not c.get("starter") and not c.get("reward")
                   and c["id"] in self.found)

    def region_progress(self, region):
        comps = [c for c in catalog.ALL if c["region"] == region]
        have = sum(1 for c in comps if self.owns(c["id"]))
        return have, len(comps)

    # -- mutations --------------------------------------------------------
    def collect(self, cid):
        """Mark a component found.  Returns True if it was newly collected."""
        if cid in self.found or (catalog.get(cid) or {}).get("starter"):
            return False
        previous_order = self._order
        self._order += 1
        self.found[cid] = {"t": time.time(), "order": self._order}
        if self.save():
            return True
        self.found.pop(cid, None)
        self._order = previous_order
        return False

    def discovery_order(self, cid):
        rec = self.found.get(cid)
        return rec["order"] if rec else -1

    def consume(self, cid):
        """Remove one discovered sound when it is gifted as a story sprout.

        Built-in starter tools are permanent and cannot be consumed. World
        pickup instance history is intentionally retained, so giving away a
        rare find is a real choice rather than a way to farm the same pickup.
        """
        comp = catalog.get(cid)
        if comp is None or comp.get("starter") or cid not in self.found:
            return False
        previous = self.found.pop(cid, None)
        if self.save():
            return True
        if previous is not None:
            self.found[cid] = previous
        return False

    # -- world pickup instances (so collected pickups never respawn) -------
    def pickup_collected(self, iid):
        return iid in self.collected_pickups

    def mark_pickup(self, iid):
        if iid in self.collected_pickups:
            return True
        self.collected_pickups.add(iid)
        if self.save():
            return True
        self.collected_pickups.discard(iid)
        return False

    def reset(self):
        """Wipe all discovery state back to a clean, fresh start."""
        previous = (self.found, self._order, self.collected_pickups)
        self.found = {}
        self._order = 0
        self.collected_pickups = set()
        if self.save():
            return True
        self.found, self._order, self.collected_pickups = previous
        return False

    # -- persistence ------------------------------------------------------
    def load(self):
        previous = (dict(self.found), self._order, set(self.collected_pickups))
        try:
            with open(paths.collection_file(), "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError("collection root must be an object")
            raw_found = data.get("found", {})
            raw_pickups = data.get("collected_pickups", [])
            if not isinstance(raw_found, dict) or not isinstance(raw_pickups, list):
                raise TypeError("collection fields have invalid types")
            found = {}
            for component_id, record in raw_found.items():
                if catalog.get(component_id) is None or not isinstance(record, dict):
                    continue
                order = record.get("order", 0)
                timestamp = record.get("t", 0.0)
                if isinstance(order, bool) or not isinstance(order, (int, float)):
                    continue
                if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)):
                    continue
                found[component_id] = {"t": float(timestamp), "order": int(order)}
            self.found = found
            self._order = max([0] + [record.get("order", 0) for record in found.values()])
            self.collected_pickups = {str(value) for value in raw_pickups
                                      if isinstance(value, (str, int))}
        except FileNotFoundError:
            self.found = {}
            self._order = 0
            self.collected_pickups = set()
        except (ValueError, TypeError, KeyError, UnicodeError, OSError):
            self.found, self._order, self.collected_pickups = previous
            _LOG.exception("Could not load collection.json; keeping the previous valid state")

    def save(self):
        try:
            return atomic_write_json(
                paths.collection_file(),
                {"found": self.found,
                 "collected_pickups": sorted(self.collected_pickups)},
                indent=1,
            )
        except PersistenceError:
            _LOG.exception("Could not save collection progress")
            return False
