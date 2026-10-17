"""Tiny eager persistence for the island-shop story.

The musical collection, songs and world live inside the active profile.  This
file owns only story-facing state: shop placement, time, economy, active briefs,
appointments, remembered visitors and Bal's current field delivery.
"""

import json
import os
import time

from .. import config, paths
from ..logging_utils import get_logger
from ..persistence import PersistenceError, atomic_write_json

_LOG = get_logger("story_state")


def _path():
    return os.path.join(paths.save_dir(), "story.json")


class StoryState:
    def __init__(self):
        self.intro_complete = False
        self.shop_x = None
        self.shop_z = None
        self.boat_x = None
        self.boat_z = None
        self.coins = 0
        self.reputation = 2.5
        self.day = 1
        self.clock_minutes = float(getattr(config, "STORY_START_MINUTE", 510))
        self.completed = 0
        self.missed_walkins = 0
        self.visits = {}
        self.request_serial = 0
        self.active_orders = []
        self.scheduled_visits = []
        self.history = []
        self.active_delivery = None
        self.sold_songs = {}
        self.commission_inbox = []
        self.helpers = {}
        self.helper_reports = []
        self.courier_jobs = []
        self.decorations_owned = {}
        self.decorations_placed = []
        self.upgrades = {}
        self.merchant_purchases = 0
        self.merchant_sold = {}
        self.last_played = time.time()
        self.load()

    @property
    def has_shop(self):
        return self.shop_x is not None and self.shop_z is not None

    def load(self):
        previous = dict(self.__dict__)
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                raise TypeError("story root must be an object")
            self.intro_complete = bool(d.get("intro_complete", False))
            self.shop_x = d.get("shop_x")
            self.shop_z = d.get("shop_z")
            self.boat_x = d.get("boat_x")
            self.boat_z = d.get("boat_z")
            self.coins = int(d.get("coins", 0))
            self.reputation = float(d.get("reputation", 2.5))
            self.day = max(1, int(d.get("day", 1)))
            self.clock_minutes = float(d.get("clock_minutes", getattr(config, "STORY_START_MINUTE", 510))) % 1440.0
            self.completed = max(0, int(d.get("completed", 0)))
            self.missed_walkins = max(0, int(d.get("missed_walkins", 0)))
            visits = d.get("visits", {}) or {}
            if not isinstance(visits, dict):
                raise TypeError("visits must be an object")
            self.visits = dict(visits)
            self.request_serial = max(0, int(d.get("request_serial", 0)))
            self.active_orders = [dict(x) for x in (d.get("active_orders", []) or []) if isinstance(x, dict)]
            self.scheduled_visits = [dict(x) for x in (d.get("scheduled_visits", []) or []) if isinstance(x, dict)]
            self.history = [dict(x) for x in (d.get("history", []) or []) if isinstance(x, dict)][-80:]
            delivery = d.get("active_delivery")
            self.active_delivery = dict(delivery) if isinstance(delivery, dict) else None
            sold_songs = d.get("sold_songs", {}) or {}
            if not isinstance(sold_songs, dict):
                raise TypeError("sold_songs must be an object")
            self.sold_songs = {str(k): max(0, int(v)) for k, v in sold_songs.items()}
            self.commission_inbox = [dict(x) for x in (d.get("commission_inbox", []) or []) if isinstance(x, dict)][-40:]
            helpers = d.get("helpers", {}) or {}
            if not isinstance(helpers, dict):
                raise TypeError("helpers must be an object")
            self.helpers = {str(k): dict(v) for k, v in helpers.items() if isinstance(v, dict)}
            self.helper_reports = [dict(x) for x in (d.get("helper_reports", []) or []) if isinstance(x, dict)][-30:]
            self.courier_jobs = [dict(x) for x in (d.get("courier_jobs", []) or []) if isinstance(x, dict)]
            owned = d.get("decorations_owned", {}) or {}
            if not isinstance(owned, dict):
                raise TypeError("decorations_owned must be an object")
            self.decorations_owned = {str(k): max(0, int(v)) for k, v in owned.items()}
            self.decorations_placed = [dict(x) for x in (d.get("decorations_placed", []) or []) if isinstance(x, dict)]
            upgrades = d.get("upgrades", {}) or {}
            if not isinstance(upgrades, dict):
                raise TypeError("upgrades must be an object")
            self.upgrades = {str(k): bool(v) for k, v in upgrades.items()}
            self.merchant_purchases = max(0, int(d.get("merchant_purchases", 0)))
            merchant_sold = d.get("merchant_sold", {}) or {}
            if not isinstance(merchant_sold, dict):
                raise TypeError("merchant_sold must be an object")
            self.merchant_sold = {
                str(k): [str(token) for token in values]
                for k, values in merchant_sold.items() if isinstance(values, list)
            }
            self.last_played = float(d.get("last_played", time.time()))
        except FileNotFoundError:
            return
        except (ValueError, TypeError, KeyError, UnicodeError, OSError):
            self.__dict__.clear()
            self.__dict__.update(previous)
            _LOG.exception("Could not load story.json; keeping the previous valid state")

    def _payload(self):
        return {
            "intro_complete": self.intro_complete,
            "shop_x": self.shop_x,
            "shop_z": self.shop_z,
            "boat_x": self.boat_x,
            "boat_z": self.boat_z,
            "coins": self.coins,
            "reputation": round(self.reputation, 3),
            "day": self.day,
            "clock_minutes": round(self.clock_minutes, 3),
            "completed": self.completed,
            "missed_walkins": self.missed_walkins,
            "visits": self.visits,
            "request_serial": self.request_serial,
            "active_orders": self.active_orders,
            "scheduled_visits": self.scheduled_visits,
            "history": self.history[-80:],
            "active_delivery": self.active_delivery,
            "sold_songs": self.sold_songs,
            "commission_inbox": self.commission_inbox[-40:],
            "helpers": self.helpers,
            "helper_reports": self.helper_reports[-30:],
            "courier_jobs": self.courier_jobs,
            "decorations_owned": self.decorations_owned,
            "decorations_placed": self.decorations_placed,
            "upgrades": self.upgrades,
            "merchant_purchases": self.merchant_purchases,
            "merchant_sold": self.merchant_sold,
            "last_played": self.last_played,
        }

    def save(self):
        previous_last_played = self.last_played
        self.last_played = time.time()
        try:
            return atomic_write_json(_path(), self._payload(), indent=1)
        except PersistenceError:
            self.last_played = previous_last_played
            _LOG.exception("Could not save story progress")
            return False

    def sync_clock(self, clock, save=False):
        previous = (self.day, self.clock_minutes)
        self.day = int(clock.day)
        self.clock_minutes = float(clock.minutes)
        if not save or self.save():
            return True
        self.day, self.clock_minutes = previous
        return False

    def next_serial(self):
        previous = self.request_serial
        self.request_serial += 1
        if self.save():
            return self.request_serial
        self.request_serial = previous
        return None

    def place_shop(self, x, z, boat_x, boat_z):
        previous = (self.shop_x, self.shop_z, self.boat_x, self.boat_z,
                    self.intro_complete)
        self.shop_x, self.shop_z = float(x), float(z)
        self.boat_x, self.boat_z = float(boat_x), float(boat_z)
        self.intro_complete = True
        if self.save():
            return True
        (self.shop_x, self.shop_z, self.boat_x, self.boat_z,
         self.intro_complete) = previous
        return False

    def adjust_reputation(self, delta):
        previous = self.reputation
        self.reputation = max(1.0, min(5.0, self.reputation + float(delta)))
        if self.save():
            return True
        self.reputation = previous
        return False

    def finish_visit(self, client_name, stars, coins, request=None, item_name=""):
        request_id = request.get("id") if isinstance(request, dict) else None
        if request_id and any(entry.get("id") == request_id for entry in self.history):
            return False
        snapshot = (self.coins, self.completed, dict(self.visits),
                    self.reputation, list(self.history))
        self.coins += max(0, int(coins))
        self.completed += 1
        self.visits[client_name] = int(self.visits.get(client_name, 0)) + 1
        self.reputation = max(1.0, min(5.0, self.reputation * 0.8 + stars * 0.2))
        if request is not None:
            self.history.append({
                "id": request_id, "client": client_name,
                "title": request.get("title", "Request"), "stars": int(stars),
                "coins": int(coins), "item": item_name, "day": self.day,
            })
        if self.save():
            return True
        self.coins, self.completed, self.visits, self.reputation, self.history = snapshot
        return False

    def cancel_accepted(self, order):
        """Cancel one accepted order once, with a smaller penalty than expiry."""
        request_id = order.get("id") if isinstance(order, dict) else None
        if not request_id or not any(o.get("id") == request_id for o in self.active_orders):
            return False
        snapshot = (self.reputation, list(self.active_orders), list(self.history),
                    self.active_delivery, list(self.courier_jobs))
        penalty = float(getattr(config, "STORY_CANCEL_REP_LOSS", 0.15))
        self.reputation = max(1.0, self.reputation - penalty)
        self.active_orders = [o for o in self.active_orders if o.get("id") != request_id]
        self.active_delivery = (None if isinstance(self.active_delivery, dict)
                                and self.active_delivery.get("order_id") == request_id
                                else self.active_delivery)
        self.courier_jobs = [job for job in self.courier_jobs
                             if job.get("order_id") != request_id]
        self.history.append({
            "id": request_id, "client": order.get("name", "Client"),
            "title": (order.get("request") or {}).get("title", "Request"),
            "stars": 0, "coins": 0, "item": "cancelled early", "day": self.day,
        })
        if self.save():
            return True
        (self.reputation, self.active_orders, self.history,
         self.active_delivery, self.courier_jobs) = snapshot
        return False

    def miss_walkin(self, client_name, request):
        previous = (self.missed_walkins, self.reputation, list(self.history))
        self.missed_walkins += 1
        self.reputation = max(1.0, self.reputation - float(getattr(config, "STORY_WALKIN_REP_LOSS", 0.08)))
        self.history.append({
            "id": request.get("id"), "client": client_name,
            "title": request.get("title", "Request"), "stars": 0,
            "coins": 0, "item": "missed walk-in", "day": self.day,
        })
        if self.save():
            return True
        self.missed_walkins, self.reputation, self.history = previous
        return False

    def miss_accepted(self, order):
        previous = (self.reputation, list(self.history))
        self.reputation = max(1.0, self.reputation - float(getattr(config, "STORY_ACCEPTED_REP_LOSS", 0.4)))
        self.history.append({
            "id": order.get("id"), "client": order.get("name", "Client"),
            "title": (order.get("request") or {}).get("title", "Request"),
            "stars": 1, "coins": 0, "item": "missed deadline", "day": self.day,
        })
        if self.save():
            return True
        self.reputation, self.history = previous
        return False

    @staticmethod
    def _sale_key(project_id, content_hash):
        return "%s:%s" % (project_id or "song", content_hash or "unknown")

    def song_times_sold(self, project_id, content_hash):
        return int(self.sold_songs.get(self._sale_key(project_id, content_hash), 0))

    def mark_song_sold(self, project_id, content_hash):
        key = self._sale_key(project_id, content_hash)
        previous = self.sold_songs.get(key)
        self.sold_songs[key] = int(previous or 0) + 1
        if self.save():
            return self.sold_songs[key]
        if previous is None:
            self.sold_songs.pop(key, None)
        else:
            self.sold_songs[key] = previous
        return int(previous or 0)

    def upsert_order(self, record):
        previous = list(self.active_orders)
        rid = record.get("id")
        self.active_orders = [o for o in self.active_orders if o.get("id") != rid]
        self.active_orders.append(dict(record))
        if self.save():
            return True
        self.active_orders = previous
        return False

    def remove_order(self, request_id):
        previous = list(self.active_orders)
        self.active_orders = [o for o in self.active_orders if o.get("id") != request_id]
        if self.active_orders == previous:
            return False
        if self.save():
            return True
        self.active_orders = previous
        return False


    def add_commission_lead(self, record):
        """Store a request recorded by the shop assistant. It is not accepted yet."""
        rid = record.get("id")
        if not rid or any(x.get("id") == rid for x in self.commission_inbox):
            return False
        previous = list(self.commission_inbox)
        self.commission_inbox.append(dict(record))
        self.commission_inbox = self.commission_inbox[-40:]
        if self.save():
            return True
        self.commission_inbox = previous
        return False

    def remove_commission_lead(self, request_id):
        previous = list(self.commission_inbox)
        self.commission_inbox = [x for x in self.commission_inbox if x.get("id") != request_id]
        if self.commission_inbox == previous:
            return False
        if self.save():
            return True
        self.commission_inbox = previous
        return False

    def schedule_visit(self, record):
        key = (record.get("kind"), record.get("name"), record.get("at"))
        for old in self.scheduled_visits:
            if (old.get("kind"), old.get("name"), old.get("at")) == key:
                return True
        previous = list(self.scheduled_visits)
        self.scheduled_visits.append(dict(record))
        self.scheduled_visits.sort(key=lambda r: float(r.get("at", 0.0)))
        if self.save():
            return True
        self.scheduled_visits = previous
        return False

    def pop_due_visits(self, stamp):
        due = [r for r in self.scheduled_visits if float(r.get("at", 0.0)) <= float(stamp)]
        if not due:
            return []
        previous = list(self.scheduled_visits)
        self.scheduled_visits = [r for r in self.scheduled_visits if r not in due]
        if self.save():
            return due
        self.scheduled_visits = previous
        return []
