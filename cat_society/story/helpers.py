"""Non-cat helpers who support Bal without replacing his creative work.

Bal is the only cat in the game.  The scout, assistant, and courier use the
same procedural animal actors already found in the world.  A helper actor does
not even exist until that helper has been hired, which keeps recruitment
contracts from leaking invisible positions or NPCs into the map.
"""

import hashlib
import math
import random

from .. import config
from ..components import catalog
from ..entities.animals import Animal
from ..projection import project


HELPER_INFO = {
    "scout": dict(name="Juniper", species="fox", role="Sound scout", wage=10,
                  offset=(102.0, 18.0)),
    "assistant": dict(name="Clover", species="rabbit", role="Shop assistant", wage=12,
                      offset=(-76.0, -42.0)),
    "courier": dict(name="Bramble", species="dog", role="Courier", wage=9,
                    offset=(92.0, -92.0)),
}
REGIONS = ("meadow", "river", "orchard", "deepwood", "animal", "hidden")


def _stable(*parts):
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


class HelperVisual:
    """One hired helper's real in-world animal actor."""

    def __init__(self, kind, shop, world_seed):
        self.kind = kind
        self.info = HELPER_INFO[kind]
        self.shop = shop
        seed = _stable(world_seed, "helper-actor", kind)
        self.animal = Animal(self.info["species"], 0.0, 0.0, random.Random(seed))
        self.visible = False
        self._place()

    def _place(self):
        dx, dz = self.info["offset"]
        base_x = float(self.shop.x) if self.shop.x is not None else 0.0
        base_z = float(self.shop.z) if self.shop.z is not None else 0.0
        self.animal.x = base_x + dx
        self.animal.z = base_z + dz
        self.animal.home_x = self.animal.x
        self.animal.home_z = self.animal.z
        self.animal.tx = self.animal.x
        self.animal.tz = self.animal.z
        self.animal.vx = 0.0
        self.animal.vz = 0.0
        self.animal.facing = -1 if dx > 0 else 1

    def update(self, dt, sleeping=False):
        self._place()
        if self.shop.x is None or self.shop.z is None:
            self.visible = False
            return
        mode = "sleep" if sleeping else "idle"
        self.animal.update(dt, {"script": {"mode": mode,
                                            "mood": "neutral" if sleeping else "happy"}})

    def drawable(self, game):
        if not self.visible:
            return None
        pr = project(self.animal.x, self.animal.z, game.cam)
        if pr is None:
            return None
        sx, sy, sc = pr
        if sc <= .11:
            return None
        draw_scale = sc * config.SC * self.animal.spec.draw_scale
        return (sy, 40,
                lambda surf, a=self.animal, px=sx, py=sy, ds=draw_scale, raw=sc:
                a.draw(surf, px, py, ds, raw, swim=0.0, fade=0.0))


class HelperManager:
    def __init__(self, story_state, collection, shop, world_seed):
        self.state = story_state
        self.collection = collection
        self.shop = shop
        self.world_seed = int(world_seed)
        # Important: no actor, position, or drawable exists before hiring.
        self.visuals = {}
        self._ensure_records()
        self._ensure_hired_visuals()
        self.alerts = []

    def _ensure_records(self):
        for kind, info in HELPER_INFO.items():
            rec = self.state.helpers.setdefault(kind, {})
            rec.setdefault("hired", False)
            rec.setdefault("scheduled", False)
            rec.setdefault("on_duty", False)
            rec.setdefault("wage", info["wage"])
            # Refresh presentation fields when loading older v31 saves.
            rec["name"] = info["name"]
            rec["species"] = info["species"]
            rec.setdefault("last_paid_day", 0)
            if kind == "scout":
                rec.setdefault("region", "meadow")
                rec.setdefault("away_until", None)
        self.state.save()

    def _ensure_visual(self, kind):
        if kind in HELPER_INFO and self.hired(kind) and kind not in self.visuals:
            self.visuals[kind] = HelperVisual(kind, self.shop, self.world_seed)
        return self.visuals.get(kind)

    def _ensure_hired_visuals(self):
        for kind in HELPER_INFO:
            if self.hired(kind):
                self._ensure_visual(kind)

    def record(self, kind):
        return self.state.helpers.setdefault(kind, {})

    def hired(self, kind):
        return bool(self.record(kind).get("hired"))

    def active(self, kind):
        rec = self.record(kind)
        return bool(rec.get("hired") and rec.get("on_duty"))

    @property
    def assistant_active(self):
        return self.active("assistant")

    @property
    def courier_active(self):
        return self.active("courier")

    def hire(self, kind):
        if kind not in HELPER_INFO:
            return False
        rec = self.record(kind)
        rec.update(hired=True, scheduled=True,
                   name=HELPER_INFO[kind]["name"],
                   species=HELPER_INFO[kind]["species"])
        self._ensure_visual(kind)
        self.state.save()
        return True

    def toggle_schedule(self, kind):
        rec = self.record(kind)
        if not rec.get("hired"):
            return False
        rec["scheduled"] = not bool(rec.get("scheduled"))
        self.state.save()
        return True

    def cycle_scout_region(self, direction=1):
        rec = self.record("scout")
        cur = rec.get("region", "meadow")
        idx = REGIONS.index(cur) if cur in REGIONS else 0
        rec["region"] = REGIONS[(idx + direction) % len(REGIONS)]
        self.state.save()
        return rec["region"]

    def _start_day(self, clock):
        for kind, info in HELPER_INFO.items():
            rec = self.record(kind)
            if not rec.get("hired") or int(rec.get("last_paid_day", 0)) == clock.day:
                continue
            rec["last_paid_day"] = clock.day
            booked = bool(rec.get("scheduled"))
            # A booking covers one day only. Bal chooses tomorrow's team in
            # the journal instead of silently paying an endless salary.
            rec["scheduled"] = False
            if booked and self.state.coins >= int(rec.get("wage", info["wage"])):
                wage = int(rec.get("wage", info["wage"]))
                self.state.coins -= wage
                rec["on_duty"] = True
                self.alerts.append("%s started work. Wage paid: %d coins." % (info["name"], wage))
                if kind == "scout":
                    rec["away_until"] = (clock.day - 1) * 1440.0 + (16 * 60 - 5 * 60 - 30)
            else:
                rec["on_duty"] = False
                if booked:
                    self.alerts.append("%s took the day off because Bal could not cover the wage." % info["name"])
        self.state.save()

    def _finish_scout(self, clock):
        rec = self.record("scout")
        due = rec.get("away_until")
        if not rec.get("on_duty") or due is None or clock.stamp < float(due):
            return
        rec["away_until"] = None
        region = rec.get("region", "meadow")
        rng = random.Random(_stable(self.world_seed, "scout", clock.day, region))
        candidates = [c for c in catalog.by_region(region)
                      if not c.get("starter") and not c.get("reward")
                      and not self.collection.owns(c["id"])]
        rng.shuffle(candidates)
        roll = rng.random()
        scout_name = HELPER_INFO["scout"]["name"]
        if candidates and roll < .72:
            comp = candidates[0]
            self.collection.collect(comp["id"])
            text = "%s returned with %s from the %s." % (scout_name, comp["name"], region)
            result = {"day": clock.day, "kind": "sound", "region": region,
                      "text": text, "component_id": comp["id"]}
        elif roll < .91:
            text = "%s found a clue: listen around the %s after sunset." % (scout_name, region)
            result = {"day": clock.day, "kind": "clue", "region": region, "text": text}
        else:
            text = "%s searched the %s but did not find a new sound today." % (scout_name, region)
            result = {"day": clock.day, "kind": "none", "region": region, "text": text}
        self.state.helper_reports.append(result)
        self.state.helper_reports = self.state.helper_reports[-30:]
        self.alerts.append(text)
        self.state.save()

    def update(self, dt, clock, events=()):
        if "new_day" in events or any(int(self.record(k).get("last_paid_day", 0)) < clock.day
                                      for k in HELPER_INFO if self.hired(k)):
            self._start_day(clock)
        self._finish_scout(clock)
        self._ensure_hired_visuals()
        night = clock.minutes >= 20 * 60 + 30 or clock.minutes < 5 * 60 + 30
        for kind, visual in list(self.visuals.items()):
            rec = self.record(kind)
            if not rec.get("hired"):
                del self.visuals[kind]
                continue
            # Hired helpers have a real home by the shop.  The scout leaves the
            # map only while actively searching elsewhere.
            visible = not (kind == "scout" and rec.get("away_until") is not None)
            visual.visible = visible
            visual.update(dt, sleeping=night and visible)

    def pop_alert(self):
        return self.alerts.pop(0) if self.alerts else None

    def world_drawables(self, game):
        out = []
        for visual in self.visuals.values():
            draw = visual.drawable(game)
            if draw is not None:
                out.append(draw)
        return out

    def nearest(self, cat, radius=105.0):
        result = None
        best = radius
        for kind, visual in self.visuals.items():
            if not visual.visible:
                continue
            dist = math.hypot(visual.animal.x - cat.x, visual.animal.z - cat.z)
            if dist < best:
                best = dist
                result = kind
        return result

    def can_courier(self, order):
        req = order.get("request") or {}
        return (self.courier_active and order.get("status") == "delivery"
                and int(req.get("difficulty", 1)) <= 3
                and not req.get("light_task"))

    def courier_minutes(self):
        return 58.0 if self.state.upgrades.get("delivery_shelf") else 86.0
