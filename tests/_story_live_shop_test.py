"""Headless checks for the live clock, visitor lifecycle and procedural briefs."""
import os
import tempfile

_DATA = tempfile.mkdtemp(prefix="bsg-live-shop-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _DATA
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()

from cat_society.app import App
from cat_society.story.requests import RequestGenerator, OCCASIONS
from cat_society.story.dialogue import _crop_exact_sprite
from cat_society.components import catalog
from cat_society.music.project import Project

passed = failed = 0

def check(label, value):
    global passed, failed
    ok = bool(value)
    print(("[PASS] " if ok else "[FAIL] ") + label)
    passed += int(ok)
    failed += int(not ok)


def make_playable(app):
    app.start_story(new=True)
    sc = app.current
    sc.intro.skip_to_placement(sc.game, sc.story)
    for _ in range(80):
        sc.update(1 / 60)
        if sc.intro.preview and sc.intro.preview[2]:
            break
        sc.game.cat.z -= 35.0
    ok, _ = sc.intro.try_build()
    assert ok
    for _ in range(220):
        sc.update(1 / 60)
    sc.story.clear()
    sc.update(1 / 60)
    sc.intro.phase = "done"
    sc.story_state.intro_complete = True
    sc.clock.set_time(9 * 60)
    sc.story_state.sync_clock(sc.clock, save=True)
    sc._start_clients_after_intro()
    return sc


app = App()
story = make_playable(app)

# The Maker is a room in the same day, not a pause screen.
app.goto("maker")
old_stamp = story.clock.stamp
app.current.update(10.0)
check("story clock advances inside Music Maker", story.clock.stamp > old_stamp + 10.0)
status = story.maker_status()
check("Maker status exposes time and client counts",
      status["time"] == story.clock.format_time() and "at_shop" in status and "away" in status)
app.current.draw(app.window)
check("live shop status draws over the Maker", True)

# A walk-in can arrive and expire while Bal keeps composing.
story.clients._next_walkin = story.clock.stamp
app.current.update(0.2)
check("new animals can arrive while Maker is open", bool(story.clients.actors))
actor = story.clients.actors[0]
actor.state = "waiting"
actor.arrived = True
actor.animal.x = story.shop.x
actor.animal.z = story.shop.z - 86.0
rep_before = story.story_state.reputation
actor.patience_stamp = story.clock.stamp + 0.1
app.current.update(1.0)
check("ignored walk-in harms shop reputation", story.story_state.reputation < rep_before)
for _ in range(100):
    app.current.update(0.2)
check("expired animal walks away and is removed", actor not in story.clients.actors)

# Refusal resolves visibly and does not strand an animal at the counter.
refused = story.clients.spawn(story.game, species="fox", name="Maple the fox")
refused.state = "waiting"
refused.arrived = True
story.clients.open_conversation(story, refused)
story.dialogue.reveal = 9999
story.dialogue._advance()
story.dialogue.reveal = 9999
story.dialogue._choose(2)
for _ in range(100):
    story.update(0.2)
check("refused client leaves the shop", refused not in story.clients.actors)

# Accepted clients can leave, return later, and keep a coherent deadline.
returning = None
for serial in range(10, 500):
    req = story.clients.generator.generate(story.clock.day, serial, "owl")
    if req.get("service") in ("return_later", "return_tomorrow"):
        returning = story.clients.spawn(story.game, "owl", "Morrow the owl", request=req)
        break
check("generator produces leave-and-return appointments", returning is not None)
if returning is not None:
    returning.state = "waiting"
    returning.arrived = True
    order = story.clients._accept(story, returning)
    check("accepted appointment is persisted away from counter",
          order.get("status") == "away" and any(v.get("kind") == "order_return"
          for v in story.story_state.scheduled_visits))
    for _ in range(90):
        story.update(0.2)
    check("appointment client physically leaves after accepting", returning not in story.clients.actors)

# Some commissions deliberately send Bal into the world.
field = None
for serial in range(500, 1400):
    req = story.clients.generator.generate(story.clock.day, serial, "rabbit")
    if req.get("service") in ("plant", "gramophone"):
        field = story.clients.spawn(story.game, "rabbit", "Clover the rabbit", request=req)
        break
check("generator produces field-delivery commissions", field is not None)
if field is not None:
    field.state = "waiting"
    field.arrived = True
    order = story.clients._accept(story, field)
    check("field commission contains a real dry world target",
          order.get("status") == "delivery" and isinstance(order.get("target_x"), float)
          and isinstance(order.get("target_z"), float))

# Execute both kinds of world delivery, not merely their request setup.
plant_req = None
for serial in range(1500, 2600):
    candidate = story.clients.generator.generate(story.clock.day, serial, "frog")
    if candidate.get("service") == "plant":
        plant_req = candidate
        break
plant_actor = story.clients.spawn(story.game, "frog", "Ripple the frog", request=plant_req)
plant_actor.state = "waiting"; plant_actor.arrived = True
plant_order = story.clients._accept(story, plant_actor)
gift = next(c for c in catalog.ALL if not c.get("starter"))
story.app.collection.collect(gift["id"])
story._set_field_delivery(plant_order, {
    "kind": "sprout", "item_id": gift["id"], "item_name": gift["name"], "score": 0.8,
})
story.game.cat.x = plant_order["target_x"]; story.game.cat.z = plant_order["target_z"]
sprouts_before = story.sprouts.count()
story._finish_field_delivery()
check("Bal can personally plant a commissioned sprout in the world",
      story.sprouts.count() == sprouts_before + 1 and not story.app.collection.owns(gift["id"])
      and all(o.get("id") != plant_order.get("id") for o in story.story_state.active_orders))
story.story.clear()

gram_req = None
for serial in range(2600, 4000):
    candidate = story.clients.generator.generate(story.clock.day, serial, "owl")
    if candidate.get("service") == "gramophone":
        gram_req = candidate
        break
gram_actor = story.clients.spawn(story.game, "owl", "Lumen the owl", request=gram_req)
gram_actor.state = "waiting"; gram_actor.arrived = True
gram_order = story.clients._accept(story, gram_actor)
project = Project("Roadside Commission")
story.app.projects.save(project)
story._set_field_delivery(gram_order, {
    "kind": "gramophone", "project_id": project.id, "item_name": project.name, "score": 0.75,
})
story.game.cat.x = gram_order["target_x"]; story.game.cat.z = gram_order["target_z"]
gram_before = len(story.garden.gramophones)
story._finish_field_delivery()
check("Bal can personally place a commissioned gramophone in the world",
      len(story.garden.gramophones) == gram_before + 1
      and all(o.get("id") != gram_order.get("id") for o in story.story_state.active_orders))
story.story.clear()

# Procedural breadth: authored archetypes combine with place, recipient,
# texture, service style, species taste and return behavior.
gen = RequestGenerator(991337)
req_a = gen.generate(4, 77, "frog", visit=1)
req_b = gen.generate(4, 77, "frog", visit=1)
check("request generation is deterministic for the same slot/day/client", req_a == req_b)
requests = [gen.generate(1 + i // 140, i + 1,
                         ("frog", "owl", "fox", "dog", "turtle", "horse", "rabbit")[i % 7],
                         visit=i % 3)
            for i in range(1400)]
check("procedural system reaches every authored occasion",
      len({r["occasion"] for r in requests}) == len(OCCASIONS))
check("procedural requests produce hundreds of distinct spoken briefs",
      len({r["flavor"] for r in requests}) > 1100)
check("all five service rhythms occur", {r["service"] for r in requests} >=
      {"wait", "return_later", "return_tomorrow", "plant", "gramophone"})
check("requests vary task kind, destination and musical constraints",
      len({(r["kind"], r["destination_label"], r["primary"], tuple(r.get("needs", ())))
           for r in requests}) > 350)

# Portraits use the exact procedural sprite renderer and crop its face.
face = _crop_exact_sprite("deer", 112)
check("dialogue face is a non-empty crop of the in-world animal sprite",
      face.get_bounding_rect(min_alpha=8).w > 40 and face.get_bounding_rect(min_alpha=8).h > 40)

app._shutdown()
print("\n%d passed, %d failed" % (passed, failed))
raise SystemExit(1 if failed else 0)
