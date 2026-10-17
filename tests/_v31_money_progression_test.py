"""Focused checks for the v31 merchant, decoration, helper and journal loop."""
import os
import tempfile
from types import SimpleNamespace

os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = tempfile.mkdtemp(prefix="bsg-v31-")
os.environ["BAL_SOUND_GARDEN_EXPORTS_DIR"] = tempfile.mkdtemp(prefix="bsg-v31-exports-")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
pygame.display.set_mode((960, 540))

from cat_society import paths
from cat_society.components import catalog
from cat_society.components.collection import Collection
from cat_society.story.clock import StoryClock
from cat_society.story.clients import ClientActor, ClientDirector
from cat_society.story.decorations import DECORATIONS, DecorationManager, draw_decoration
from cat_society.story.economy import build_stock, merchant_visits
from cat_society.story.helpers import HELPER_INFO, HelperManager
from cat_society.story.journal import StoryJournalOverlay
from cat_society.story.merchant import Merchant, MerchantOverlay, draw_merchant_cart
from cat_society.story.shop import Shop
from cat_society.story.state import StoryState
from cat_society.story.decorations import draw_shop_upgrade
from cat_society.story.dialogue import DialogueOverlay, _crop_exact_sprite
from cat_society.entities.animals import Animal, SPECIES
import random
from cat_society.screens.story import StoryScreen

passed = failed = 0


def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


profile = os.path.join(os.environ["BAL_SOUND_GARDEN_DATA_DIR"], "save", "slots", "slot_test")
paths.set_active_profile(profile)
state = StoryState()
state.shop_x = 0.0
state.shop_z = 0.0
state.intro_complete = True
state.day = 2
state.clock_minutes = 10 * 60
state.coins = 5000
state.save()
collection = Collection()
shop = Shop(0.0, 0.0, built=1.0)
helpers = HelperManager(state, collection, shop, 77123)

check("day two always receives a travelling merchant", merchant_visits(77123, 2))
stock_a = [(x["kind"], x["id"], x["price"])
           for x in build_stock(77123, 2, collection, state)]
stock_b = [(x["kind"], x["id"], x["price"])
           for x in build_stock(77123, 2, collection, state)]
check("merchant stock is deterministic for a slot and day", stock_a == stock_b)
check("merchant offers sounds, decorations, upgrades and a helper contract",
      {kind for kind, _item_id, _price in stock_a} == {"sound", "decor", "upgrade", "helper"})

merchant = Merchant(state, collection, shop, 77123, helpers)
clock = StoryClock(2, 10 * 60)
merchant.update(0.0, clock)
check("merchant is physically available during daytime visit hours", merchant.active)
start_coins = state.coins
purchased = {}
for kind in ("sound", "decor", "upgrade", "helper"):
    item = next(x for x in list(merchant.stock) if x["kind"] == kind)
    ok, _text = merchant.purchase(item)
    purchased[kind] = item
    check("merchant purchase works for %s" % kind, ok)
check("purchases spend story coins", state.coins < start_coins)
check("bought sound enters only the active collection",
      collection.owns(purchased["sound"]["id"]))
check("bought decoration enters shop storage",
      state.decorations_owned.get(purchased["decor"]["id"]) == 1)
check("bought upgrade becomes active",
      state.upgrades.get(purchased["upgrade"]["id"]) is True)
check("bought helper contract hires an animal helper",
      helpers.hired(purchased["helper"]["id"]))

# Reloading during the same day must not restock items already bought.
merchant_reloaded = Merchant(state, collection, shop, 77123, helpers)
merchant_reloaded.update(0.0, clock)
token = (purchased["decor"]["kind"], purchased["decor"]["id"])
check("same-day reload does not restore sold cart stock",
      token not in {(x["kind"], x["id"]) for x in merchant_reloaded.stock})

# Decorations are manually placed and can be returned to storage.
decor = DecorationManager(state)
decor_id = purchased["decor"]["id"]
check("bought decoration is available for manual placement", decor.begin(decor_id))
decor.preview = (75.0, -90.0, True)
ok, _text = decor.place()
check("decoration placement is persisted", ok and len(state.decorations_placed) == 1)
removed = decor.remove_nearest(75.0, -90.0)
check("placed decoration can be picked up and reused",
      removed and removed["id"] == decor_id and decor.inventory_count(decor_id) == 1)
check("decoration catalogue has broad cozy variety", len(DECORATIONS) >= 18)

# Animal helpers charge only for scheduled days and never create debt.
for kind in HELPER_INFO:
    helpers.hire(kind)
    rec = helpers.record(kind)
    rec["last_paid_day"] = 2
    rec["scheduled"] = True
state.coins = 100
before_wages = state.coins
clock.set_stamp(2 * 1440.0 + 180.0)  # Day 3, 08:30.
helpers.update(0.0, clock, ("new_day",))
expected_wages = sum(info["wage"] for info in HELPER_INFO.values())
check("scheduled helpers are paid once at the start of a work day",
      state.coins == before_wages - expected_wages)
check("assistant, scout and courier can all work on the same day",
      all(helpers.active(kind) for kind in HELPER_INFO))
state.coins = 0
for kind in HELPER_INFO:
    helpers.record(kind)["scheduled"] = True
clock.set_stamp(3 * 1440.0 + 180.0)  # Day 4, 08:30.
helpers.update(0.0, clock, ("new_day",))
check("helpers take a day off instead of putting Bal into debt",
      state.coins == 0 and not any(helpers.active(kind) for kind in HELPER_INFO))

# Force one paid scout return to verify reports and sound-search results.
state.coins = 40
scout = helpers.record("scout")
scout.update(scheduled=True, last_paid_day=4)
clock.set_stamp(4 * 1440.0 + 180.0)  # Day 5, 08:30.
helpers.update(0.0, clock, ("new_day",))
scout["away_until"] = clock.stamp
reports_before = len(state.helper_reports)
helpers.update(0.0, clock)
check("sound scout returns with a sound, clue, or honest empty report",
      len(state.helper_reports) == reports_before + 1
      and state.helper_reports[-1]["kind"] in ("sound", "clue", "none"))

# Clover records an offer, but Bal must explicitly accept it in the journal.
director = ClientDirector(state, shop, 77123)
director._clock = clock
request = {
    "id": "assistant-offer-1", "title": "Warm Porch Song", "kind": "song",
    "service": "wait", "due_day_offset": 0, "primary": "warm",
    "tempo": (80, 105), "needs": ("melody",), "difficulty": 2,
}
actor = ClientActor("dog", "Maple the dog", request, 0.0, 0.0, 12)
director._assistant_record(actor)
check("shop assistant records information without accepting the commission",
      len(state.commission_inbox) == 1 and not state.active_orders)
lead = state.commission_inbox[0]
check("recorded offer keeps the animal's real deadline", lead.get("offer_due", 0) > clock.stamp)
order, _text = director.accept_lead(SimpleNamespace(game=None), lead)
check("Bal can explicitly accept an assistant offer from the journal",
      order is not None and order in state.active_orders and not state.commission_inbox)

request2 = dict(request, id="assistant-offer-2", title="Quiet Window Song")
actor2 = ClientActor("deer", "Fern the deer", request2, 0.0, 0.0, 13)
director._assistant_record(actor2)
rep_before = state.reputation
director.decline_lead(state.commission_inbox[0])
check("declining an unaccepted assistant offer costs no reputation",
      not state.commission_inbox and state.reputation == rep_before)

expired = {
    "id": "expired-offer", "name": "Old visitor", "species": "dog",
    "request": dict(request, id="expired-offer"), "offer_due": clock.stamp - 1,
}
state.add_commission_lead(expired)
order, _text = director.accept_lead(SimpleNamespace(game=None), expired)
check("expired recorded offers cannot become fresh contracts", order is None)

# Courier jobs create the physical field object before the normal result payout.
starter = next(c for c in catalog.ALL if c.get("starter"))
field_order = {
    "id": "courier-order", "name": "Willow the sheep", "species": "sheep",
    "status": "courier", "target_x": 10.0, "target_z": 20.0,
    "request": {"difficulty": 2, "service": "plant", "kind": "sprout"},
}
state.active_orders = [field_order]
state.courier_jobs = [{
    "order_id": "courier-order", "complete_at": clock.stamp - 1,
    "kind": "sprout", "item_id": starter["id"], "item_name": starter["name"],
    "target_x": 10.0, "target_z": 20.0, "score": 0.8,
}]
planted = []
completed = []

class FakeSprouts:
    def plant(self, cid, x, z):
        planted.append((cid, x, z))
        return object(), ""

class FakeClients:
    def complete_remote(self, screen, order, score, item_name):
        completed.append((order["id"], score, item_name))
        screen.story_state.remove_order(order["id"])

fake_screen = SimpleNamespace(
    story_state=state, clock=clock, sprouts=FakeSprouts(), clients=FakeClients(),
    app=SimpleNamespace(projects=None), garden=None,
)
StoryScreen._process_courier_jobs(fake_screen)
check("courier leaves the prepared sprout at the real destination",
      planted == [(starter["id"], 10.0, 20.0)])
check("courier completion uses the ordinary scoring and payout handoff",
      completed and not state.courier_jobs)

# New persistence fields survive a fresh StoryState object.
state.save()
reloaded = StoryState()
check("money progression data survives save and load",
      reloaded.decorations_owned == state.decorations_owned
      and reloaded.upgrades == state.upgrades
      and reloaded.helpers.keys() == state.helpers.keys()
      and reloaded.merchant_sold == state.merchant_sold)

# Merchant overlay must map scrolled mouse rows to their real stock indices.
engine = SimpleNamespace(preview_component=lambda comp: None)
overlay = MerchantOverlay(SimpleNamespace(engine=engine), merchant_reloaded)
overlay.open()
overlay.idx = min(8, max(0, len(merchant_reloaded.stock)-1))
surf = pygame.Surface((960, 540))
overlay.draw(surf)
row_entries = [entry for entry in overlay.rects if entry[1] == "row"]
check("merchant mouse rows retain the real stock index after scrolling",
      not row_entries or all(isinstance(entry[2], int) for entry in row_entries))

# Team and shop journal layouts remain readable at the game's small window size.
fake_app = SimpleNamespace(collection=collection, engine=engine)
fake_journal_screen = SimpleNamespace(
    story_state=state, helpers=helpers, decorations=decor, clock=clock,
)
journal = StoryJournalOverlay(fake_app, fake_journal_screen)
journal.tab = 2
journal.draw(surf)
team_rows = [rect for rect, action, _value in journal.buttons if action == "row"]
team_footer = [rect for rect, action, _value in journal.buttons if action == "primary"]
check("team journal rows stay clear of the footer buttons",
      not team_rows or not team_footer
      or all(not rect.colliderect(team_footer[0]) for rect in team_rows))
journal.tab = 3
journal.draw(surf)
check("shop journal renders owned decorations and installed upgrades", bool(journal.buttons))

# New fixtures and animal helpers use ordinary painterly world rendering.
fixture = pygame.Surface((260, 200), pygame.SRCALPHA)
draw_shop_upgrade(fixture, 70, 145, 1.0, "request_board")
draw_merchant_cart(fixture, 180, 150, 1.0)
check("merchant cart and shop devices render as real world props",
      pygame.mask.from_surface(fixture).count() > 100)
all_decor = pygame.Surface((240, 160), pygame.SRCALPHA)
decor_ok = True
try:
    for item_id, row in DECORATIONS.items():
        item = dict(row, id=item_id)
        draw_decoration(all_decor, 120, 130, 1.0, item)
except Exception:
    decor_ok = False
check("every decoration variant renders without a missing-shape crash", decor_ok)
animal_pixels = []
for i, kind in enumerate(("assistant", "scout", "courier")):
    info = HELPER_INFO[kind]
    helper_surf = pygame.Surface((180, 180), pygame.SRCALPHA)
    animal = Animal(info["species"], 0.0, 0.0, random.Random(100+i))
    animal.draw(helper_surf, 90, 150, 1.8 * animal.spec.draw_scale, 1.0)
    animal_pixels.append(pygame.image.tostring(helper_surf, "RGBA"))
check("helpers use three distinct existing animal species",
      len({HELPER_INFO[k]["species"] for k in HELPER_INFO}) == 3
      and all(HELPER_INFO[k]["species"] in SPECIES for k in HELPER_INFO)
      and len(set(animal_pixels)) == 3 and all(any(blob) for blob in animal_pixels))
helper_portraits = [pygame.image.tostring(
    _crop_exact_sprite(HELPER_INFO[kind]["species"], 96), "RGBA")
    for kind in ("assistant", "scout", "courier")]
check("helper dialogue portraits match their in-world animal species",
      len(set(helper_portraits)) == 3 and all(any(blob) for blob in helper_portraits))
dialogue = DialogueOverlay()
assistant = HELPER_INFO["assistant"]
dialogue.open("%s the %s" % (assistant["name"], assistant["species"]),
              assistant["species"], ["I wrote the request in the journal."],
              [("Thanks", "bye")])
dialogue.update(3.0)
dialogue.draw(surf)
check("animal helper portraits render inside the ordinary dialogue overlay",
      dialogue.active and dialogue.species == assistant["species"]
      and dialogue.portrait_palette is None)
dialogue.close()

pygame.quit()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
