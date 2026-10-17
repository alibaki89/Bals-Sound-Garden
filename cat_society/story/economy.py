"""Deterministic merchant stock and coin prices for Story mode."""

import hashlib
import random

from ..components import catalog
from .decorations import DECORATIONS, definition as decor_definition
from .helpers import HELPER_INFO


RARITY_PRICE = {"common": 34, "uncommon": 68, "rare": 128, "secret": 220}
UPGRADES = {
    "request_board": dict(name="Request Board", price=150, desc="Helps Clover record visitor details before they leave."),
    "listening_corner": dict(name="Listening Corner", price=185, desc="Clients who wait at the shop are more patient."),
    "sound_cabinet": dict(name="Sound Cabinet", price=210, desc="The merchant brings one extra sound when visiting."),
    "delivery_shelf": dict(name="Courier Delivery Shelf", price=175, desc="Courier jobs are completed faster."),
    "larger_counter": dict(name="Larger Counter", price=240, desc="One more visitor can wait comfortably."),
}
HELPER_CONTRACTS = {
    "scout": dict(name="Hire %s, Sound Scout" % HELPER_INFO["scout"]["name"],
                  price=220, desc="A fox who searches one chosen region for sounds. Wage: 10 coins per work day."),
    "assistant": dict(name="Hire %s, Shop Assistant" % HELPER_INFO["assistant"]["name"],
                      price=260, desc="A rabbit who records visitor requests while Bal is away. Wage: 12 coins per work day."),
    "courier": dict(name="Hire %s, Courier" % HELPER_INFO["courier"]["name"],
                    price=240, desc="A dog who carries ordinary prepared deliveries. Wage: 9 coins per work day."),
}


def _seed(*parts):
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def sound_price(comp):
    base = RARITY_PRICE.get(comp.get("rarity", "common"), 34)
    if comp.get("type") in ("loop", "ambience", "effect"):
        base += 14
    return base


def merchant_visits(world_seed, day):
    if int(day) == 1:
        return False
    if int(day) == 2:
        return True
    return random.Random(_seed(world_seed, "merchant-day", day)).random() < 0.68


def build_stock(world_seed, day, collection, story_state):
    rng = random.Random(_seed(world_seed, "merchant-stock", day))
    sounds = [c for c in catalog.ALL
              if not c.get("starter") and not c.get("reward") and not collection.owns(c["id"])]
    rng.shuffle(sounds)
    sound_count = 4 + (1 if story_state.upgrades.get("sound_cabinet") else 0)
    stock = []
    for comp in sounds[:sound_count]:
        stock.append({"kind": "sound", "id": comp["id"], "name": comp["name"],
                      "price": sound_price(comp), "desc": "%s  -  %s" %
                      (comp.get("type", "sound").title(), comp.get("rarity", "common").title())})

    decor_ids = list(DECORATIONS)
    rng.shuffle(decor_ids)
    for item_id in decor_ids[:5]:
        row = decor_definition(item_id)
        stock.append({"kind": "decor", "id": item_id, "name": row["name"],
                      "price": row["price"], "desc": row["desc"]})

    upgrade_ids = [k for k in UPGRADES if not story_state.upgrades.get(k)]
    rng.shuffle(upgrade_ids)
    for item_id in upgrade_ids[:2]:
        row = UPGRADES[item_id]
        stock.append({"kind": "upgrade", "id": item_id, "name": row["name"],
                      "price": row["price"], "desc": row["desc"]})

    helper_ids = [k for k in HELPER_CONTRACTS
                  if not (story_state.helpers.get(k) or {}).get("hired")]
    rng.shuffle(helper_ids)
    for item_id in helper_ids[:1]:
        row = HELPER_CONTRACTS[item_id]
        stock.append({"kind": "helper", "id": item_id, "name": row["name"],
                      "price": row["price"], "desc": row["desc"]})
    return stock
