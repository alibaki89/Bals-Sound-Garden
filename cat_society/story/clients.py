"""Living shop visitors: arrivals, appointments, patience, dialogue and returns.

Clients are not a permanent queue.  A visitor may wait at the counter, leave
and return later, expect Bal to deliver something in the world, miss a deadline,
or come back days later simply to tell Bal what became of the music.
"""

import math
import random

import pygame

from .. import config, ui
from ..components import catalog
from ..entities.animals import Animal, SPECIES
from ..projection import project
from .clock import DAWN_MINUTE, SHOP_OPEN_MINUTE, SHOP_CLOSE_MINUTE
from .requests import RequestGenerator
from . import scoring
from .helpers import HELPER_INFO


_WAITING_CHATTER = (
    "I can wait a little longer.",
    "The shop looks good from here.",
    "I heard music on the road this morning.",
    "Take your time, but please watch the clock.",
    "I am trying to remember every detail of my request.",
    "The island feels busy today.",
    "I hope you have the right sound in your collection.",
    "Let me know when you are ready.",
)

_NEW_GREETINGS = (
    "Hello. Are you Bal, the music maker?",
    "I heard that Bal opened a shop here.",
    "You must be Bal. I have a music request for you.",
    "Hello, Bal. Are you taking new work today?",
    "I came because everyone says you make excellent music.",
    "I have a small problem that music might solve.",
    "I hope I came at a good time. I need your help.",
    "Hello. I have been thinking about this request all morning.",
)

_RETURN_GREETINGS = (
    "Hello again, Bal. I have another request.",
    "I came back with a new idea.",
    "Do you remember me? I need your help again.",
    "The last order went well, so I came back.",
    "I did not expect to need another song so soon.",
)

_CALLBACKS = (
    "The music worked very well. Everyone enjoyed it.",
    "People kept asking who made the music for us.",
    "I still hear your tune when I pass that place.",
    "The children keep humming your melody.",
    "The music was exactly where it needed to be.",
    "The sound seed has grown into a lovely plant.",
)



class ClientActor:
    def __init__(self, species, name, request, x, z, seed, visit=0,
                 accepted=False, social=False, order_id=None):
        self.species = species
        self.name = name
        self.request = request or {}
        self.animal = Animal(species, x, z, random.Random(seed))
        self.state = "arriving"
        self.queue_index = 0
        self.accepted = bool(accepted)
        self.fulfilled = False
        self.social = bool(social)
        self.order_id = order_id or self.request.get("id")
        self.bubble = ""
        self.bubble_t = 0.0
        self.chatter_t = random.Random(seed + 17).uniform(5.0, 9.0)
        self.visit = int(visit)
        self.leave_x = x
        self.leave_z = z
        self.result = None
        self.arrived = False
        self.arrival_announced = False
        self.greeted = False
        self.patience_stamp = None
        self.depart_after = None
        self.depart_happy = True
        self.assistant_stamp = None

    def begin_departure(self, text="", delay=1.8, happy=True):
        if text:
            self.say(text, max(2.4, delay + 0.8))
        self.depart_after = max(0.0, float(delay))
        self.depart_happy = bool(happy)
        if self.state not in ("leaving", "gone"):
            self.state = "farewell"

    def update(self, dt, target, water):
        self.bubble_t = max(0.0, self.bubble_t - dt)
        self.chatter_t -= dt
        if self.depart_after is not None:
            self.depart_after -= dt
            if self.depart_after <= 0.0 and self.state not in ("leaving", "gone"):
                self.state = "leaving"
                self.depart_after = None

        if self.state in ("arriving", "queueing"):
            tx, tz = target
            mode = "move"
            if math.hypot(self.animal.x - tx, self.animal.z - tz) < 15.0:
                self.state = "waiting"
                self.arrived = True
                mode = "idle"
            script = {"mode": mode, "x": tx, "z": tz,
                      "speed": self.animal.spec.speed * 0.92, "stop": 12.0,
                      "mood": "happy"}
        elif self.state == "leaving":
            script = {"mode": "move", "x": self.leave_x, "z": self.leave_z,
                      "speed": self.animal.spec.speed * 1.14, "stop": 10.0,
                      "mood": "happy" if self.depart_happy else "sad"}
            if math.hypot(self.animal.x - self.leave_x,
                          self.animal.z - self.leave_z) < 18.0:
                self.state = "gone"
        elif self.state == "listening":
            script = {"mode": "listen", "mood": "happy",
                      "dance": self.animal.t * 2.0}
        elif self.state == "celebrate":
            script = {"mode": "play", "mood": "happy"}
        elif self.state in ("disappointed", "farewell"):
            script = {"mode": "idle", "mood": "sad" if not self.depart_happy else "happy"}
        else:
            script = {"mode": "idle", "mood": "happy" if self.accepted else "neutral"}

        self.animal.update(dt, {"script": script})
        depth = water.depth_at(self.animal.x, self.animal.z)[0]
        self.animal.swim = water.submerge_for_depth(depth) if depth > 0.0 else 0.0

    def say(self, text, seconds=3.2):
        self.bubble = text
        self.bubble_t = seconds


class ClientDirector:
    def __init__(self, story_state, shop, seed):
        self.story_state = story_state
        self.shop = shop
        self.seed = int(seed)
        self.rng = random.Random(seed ^ 0xC11E17)
        self.generator = RequestGenerator(seed)
        self.actors = []
        self.started = False
        self.first_spawned = False
        self.session_names = set()
        self.delivery_actor = None
        self._day_primary = {}
        self._next_walkin = None
        self._clock = None
        self.alert = None
        self._pending_due = []
        self._restored_with_game = False
        self._score_cache = {}
        self._sale_cache = {}

    def reset_for_world(self):
        self.actors = []
        self.started = False
        self.first_spawned = False
        self.delivery_actor = None
        self._next_walkin = None
        self.alert = None
        self._restored_with_game = False
        self._score_cache = {}
        self._sale_cache = {}

    def notify(self, text, level="normal", seconds=6.0):
        self.alert = {"text": str(text), "level": level, "ttl": float(seconds)}

    def begin(self, clock=None):
        self.started = True
        self._clock = clock or self._clock
        self.first_spawned = self.story_state.completed > 0 or self.story_state.request_serial > 0
        if self._clock is not None:
            self._next_walkin = self._clock.stamp + (4.0 if not self.first_spawned else self.rng.uniform(35.0, 80.0))

    def _restore_orders(self, clock, game):
        existing = {a.order_id for a in self.actors}
        for order in list(self.story_state.active_orders):
            if float(order.get("due", 0.0)) <= clock.stamp:
                self.story_state.miss_accepted(order)
                self.story_state.remove_order(order.get("id"))
                continue
            if order.get("status") == "waiting" and order.get("id") not in existing:
                self._spawn_order_actor(order, game)

    def _queue(self):
        return [a for a in self.actors if a.state not in ("leaving", "gone")]

    def _at_shop(self):
        return [a for a in self._queue() if a.state in (
            "arriving", "queueing", "waiting", "listening", "celebrate",
            "disappointed", "farewell")]

    def _used_primary(self, day):
        return self._day_primary.setdefault(int(day), set())

    def _new_request(self, species, visit=0, first=False):
        serial = self.story_state.next_serial()
        req = self.generator.generate(
            self._clock.day if self._clock else self.story_state.day,
            serial, species, visit=visit, first=first,
            used_primary=self._used_primary(self._clock.day if self._clock else self.story_state.day))
        self._used_primary(self._clock.day if self._clock else self.story_state.day).add(req.get("primary"))
        return req

    def _new_identity(self, species=None):
        """Choose a natural name. Duplicate visitors never receive numbers."""
        day = self._clock.day if self._clock else self.story_state.day
        serial_hint = self.story_state.request_serial + len(self.actors) + 1
        chosen_species = species
        name = None
        for attempt in range(24):
            chosen_species, candidate = self.generator.identity(
                day, serial_hint + attempt * 37, chosen_species)
            name = candidate
            if candidate not in self.session_names:
                break
        self.session_names.add(name)
        return chosen_species, name

    def _spawn_position(self, game):
        side = -1 if self.rng.random() < 0.5 else 1
        x = self.shop.x + side * self.rng.uniform(470.0, 620.0)
        z = self.shop.z + self.rng.uniform(-20.0, 170.0)
        return game.water.nearest_dry(x, z)

    def spawn(self, game, species=None, name=None, visit=0, first=False,
              request=None, accepted=False, social=False, order_id=None):
        if not self.shop.ready:
            return None
        if species is None or name is None:
            species, name = self._new_identity(species)
        x, z = self._spawn_position(game)
        req = request if request is not None else self._new_request(species, visit, first)
        actor = ClientActor(species, name, req, x, z,
                            self.rng.randrange(1, 2_000_000_000), visit=visit,
                            accepted=accepted, social=social, order_id=order_id)
        actor.leave_x, actor.leave_z = x, z
        if social:
            actor.say("Bal! I came back with news.", 2.8)
        elif accepted:
            actor.say("I said I would return.", 2.8)
        else:
            actor.say("There is Bal's music shop.", 2.8)
        if self._clock is not None:
            patience = float(req.get("patience_minutes", 90))
            if self.story_state.upgrades.get("listening_corner"):
                patience *= 1.25
            if any(r.get("id") == "small_bench" for r in self.story_state.decorations_placed):
                patience *= 1.18
            actor.patience_stamp = self._clock.stamp + patience
        self.actors.append(actor)
        return actor

    def _spawn_order_actor(self, order, game):
        if game is None:
            return None
        actor = self.spawn(game, order.get("species"), order.get("name"),
                           visit=int(order.get("visit", 0)), request=order.get("request") or {},
                           accepted=True, order_id=order.get("id"))
        if actor is not None and self._clock is not None:
            actor.patience_stamp = min(float(order.get("due", self._clock.stamp + 120)),
                                       self._clock.stamp + max(70.0, float((order.get("request") or {}).get("accepted_patience", 150))))
            order["status"] = "waiting"
            self.story_state.upsert_order(order)
        return actor

    def _schedule_next_walkin(self, clock, quick=False):
        rep = max(1.0, min(5.0, self.story_state.reputation))
        lo = max(22.0, 82.0 - rep * 8.0)
        hi = max(lo + 18.0, 145.0 - rep * 9.0)
        self._next_walkin = clock.stamp + (4.0 if quick else self.rng.uniform(lo, hi))

    def _close_stamp(self, clock, offset_days=0):
        base = (clock.day - 1) * 1440.0
        close_offset = SHOP_CLOSE_MINUTE - DAWN_MINUTE
        stamp = base + close_offset + max(0, int(offset_days)) * 1440.0
        if stamp <= clock.stamp:
            stamp += 1440.0
        return stamp

    def _schedule_callback(self, actor_or_order, request=None):
        if self._clock is None:
            return
        if isinstance(actor_or_order, ClientActor):
            species, name, visit = actor_or_order.species, actor_or_order.name, actor_or_order.visit + 1
            req = request or actor_or_order.request
        else:
            species = actor_or_order.get("species")
            name = actor_or_order.get("name")
            visit = int(actor_or_order.get("visit", 0)) + 1
            req = request or actor_or_order.get("request") or {}
        days = int(req.get("callback_delay_days", self.rng.randint(1, 4)))
        at = self._clock.stamp + days * 1440.0 + self.rng.uniform(220.0, 650.0)
        self.story_state.schedule_visit({
            "kind": "callback", "at": at, "species": species,
            "name": name, "visit": visit,
        })

    def _reschedule_unmet(self, actor, days=None):
        if self._clock is None or self.rng.random() > 0.58:
            return
        days = days or self.rng.randint(1, 3)
        self.story_state.schedule_visit({
            "kind": "new_request", "at": self._clock.stamp + days * 1440.0 + self.rng.uniform(230.0, 620.0),
            "species": actor.species, "name": actor.name, "visit": actor.visit + 1,
        })

    @staticmethod
    def _next_open_stamp(clock):
        """Return the next 09:00 stamp; visitors never materialize at night."""
        open_offset = SHOP_OPEN_MINUTE - DAWN_MINUTE
        cycle = int(clock.stamp // 1440.0)
        candidate = cycle * 1440.0 + open_offset
        if candidate <= clock.stamp:
            candidate += 1440.0
        return candidate

    def _process_clock_events(self, events):
        for event in events:
            if event == "shop_open":
                self.notify("The shop bell rings. Today's visitors are on their way.", "good")
                self._schedule_next_walkin(self._clock, quick=True)
            elif event == "shop_close":
                self.notify("The shop has closed. Unfinished accepted orders remain on the clock.", "warning")
                for actor in list(self._at_shop()):
                    if actor.accepted:
                        order = self.order_for(actor)
                        if order is not None and float(order.get("due", 0.0)) > self._clock.stamp:
                            self._send_accepted_away(actor, order, "The shop is closing. I will return tomorrow.")
                        elif order is not None:
                            self._fail_order(order, actor)
                    elif not actor.social:
                        self.story_state.miss_walkin(actor.name, actor.request)
                        actor.begin_departure("I waited as long as I could. Another day, perhaps.", 1.6, False)
                        self._reschedule_unmet(actor)
            elif event == "new_day":
                self._day_primary = {self._clock.day: set()}
                self.notify("Day %d begins. New visitors are on their way." % self._clock.day, "good")

    def update(self, dt, game, clock, clock_events=(), assistant_active=False):
        if not self.started or not self.shop.ready:
            return
        self._clock = clock
        if not self._restored_with_game:
            self._restore_orders(clock, game)
            self._restored_with_game = True
        if self.alert is not None:
            self.alert["ttl"] -= dt
            if self.alert["ttl"] <= 0.0:
                self.alert = None
        self._process_clock_events(clock_events)

        # Deadlines remain real while Bal composes in the Maker.
        for order in list(self.story_state.active_orders):
            if float(order.get("due", 0.0)) <= clock.stamp:
                actor = self.actor_for_order(order.get("id"))
                self._fail_order(order, actor)

        # The assistant records offers, not timeless contracts. Ignoring an offer has no
        # reputation penalty, but the animal's original deadline still matters.
        for lead in list(self.story_state.commission_inbox):
            expires = float(lead.get("offer_due", 0.0))
            if expires and expires <= clock.stamp:
                self.story_state.remove_commission_lead(lead.get("id"))
                self.notify("The recorded offer from %s expired." %
                            lead.get("name", "a visitor"), "normal", 5.0)

        due = self.story_state.pop_due_visits(clock.stamp)
        for rec in due:
            if not clock.shop_open:
                rec["at"] = self._next_open_stamp(clock) + self.rng.uniform(5.0, 28.0)
                self.story_state.schedule_visit(rec)
                continue
            if len(self._at_shop()) >= (int(getattr(config, "STORY_MAX_VISIBLE_CLIENTS", 4))
                         + (1 if self.story_state.upgrades.get("larger_counter") else 0)):
                rec["at"] = clock.stamp + self.rng.uniform(18.0, 42.0)
                self.story_state.schedule_visit(rec)
                continue
            kind = rec.get("kind")
            if kind == "order_return":
                order = next((o for o in self.story_state.active_orders if o.get("id") == rec.get("order_id")), None)
                if order is not None:
                    self._spawn_order_actor(order, game)
                    self.notify("%s has returned for the order." % order.get("name", "A client"), "warning")
            elif kind == "callback":
                self.spawn(game, rec.get("species"), rec.get("name"),
                           visit=int(rec.get("visit", 1)), social=True)
                self.notify("%s came back with news." % rec.get("name", "A client"), "good")
            elif kind == "new_request":
                self.spawn(game, rec.get("species"), rec.get("name"),
                           visit=int(rec.get("visit", 1)))
                self.notify("%s has returned with a new idea." % rec.get("name", "A client"), "normal")

        if clock.shop_open:
            if not self.first_spawned and self._next_walkin is not None and clock.stamp >= self._next_walkin:
                self.first_spawned = True
                self.spawn(game, "dog", "Pip the dog", first=True)
                self._schedule_next_walkin(clock)
            elif (self.first_spawned and self._next_walkin is not None
                  and clock.stamp >= self._next_walkin
                  and len(self._at_shop()) < (int(getattr(config, "STORY_MAX_VISIBLE_CLIENTS", 4))
                         + (1 if self.story_state.upgrades.get("larger_counter") else 0))):
                self.spawn(game)
                self._schedule_next_walkin(clock)

        queue = self._at_shop()
        for i, actor in enumerate(queue):
            actor.queue_index = i
            tx = self.shop.x + (i % 2) * 34.0 - (18.0 if i else 0.0)
            tz = self.shop.z - 86.0 - i * 48.0
            if actor.state == "waiting" and i > 0:
                actor.state = "queueing"
            actor.update(dt, (tx, tz), game.water)
            if actor.arrived and not actor.arrival_announced:
                actor.arrival_announced = True
                if actor.social:
                    self.notify("%s is at the counter with news." % actor.name, "good")
                elif actor.accepted:
                    self.notify("%s is back. The order is waiting." % actor.name, "warning")
                else:
                    mins = max(1, int(actor.patience_stamp - clock.stamp)) if actor.patience_stamp else 0
                    self.notify("%s arrived and can wait about %d in-game minutes." % (actor.name, mins), "normal")
                    if assistant_active:
                        delay = 7.0 if self.story_state.upgrades.get("request_board") else 14.0
                        actor.assistant_stamp = clock.stamp + delay

            if (assistant_active and not actor.social and not actor.accepted
                    and actor.state in ("waiting", "queueing")
                    and actor.assistant_stamp is not None
                    and clock.stamp >= actor.assistant_stamp):
                self._assistant_record(actor)
                continue

            if actor.state in ("waiting", "queueing") and actor.patience_stamp is not None \
                    and clock.stamp >= actor.patience_stamp:
                if actor.social:
                    actor.begin_departure("I only stopped by to say hello. See you again, Bal.", 1.6, True)
                elif actor.accepted:
                    order = self.order_for(actor)
                    if order is not None:
                        self._send_accepted_away(actor, order,
                                                "I cannot wait here any longer. I will return before the deadline.")
                else:
                    self.story_state.miss_walkin(actor.name, actor.request)
                    actor.begin_departure("I have to keep moving. I hope we meet at a better hour.", 1.8, False)
                    self.notify("%s left unserved. Reputation slipped slightly." % actor.name, "bad")
                    self._reschedule_unmet(actor)

            if actor.arrived and actor.chatter_t <= 0.0 and actor.state in ("waiting", "queueing"):
                actor.say(self.rng.choice(_WAITING_CHATTER), 3.3)
                actor.chatter_t = self.rng.uniform(9.0, 16.0)

        # Actors already walking out still need body updates after leaving the queue.
        for actor in [a for a in self.actors if a not in queue]:
            actor.update(dt, (self.shop.x, self.shop.z - 90.0), game.water)
        self.actors = [a for a in self.actors if a.state != "gone"]

    def _assistant_record(self, actor):
        due = self._close_stamp(self._clock,
                                int(actor.request.get("due_day_offset", 0)))
        lead = {
            "id": actor.request.get("id"), "name": actor.name,
            "species": actor.species, "visit": actor.visit,
            "request": dict(actor.request),
            "recorded_day": self._clock.day if self._clock else self.story_state.day,
            "recorded_at": self._clock.stamp if self._clock else 0.0,
            "offer_due": due,
        }
        if self.story_state.add_commission_lead(lead):
            actor.begin_departure(
                "%s wrote everything down. Bal can decide after reading the journal." % HELPER_INFO["assistant"]["name"],
                1.8, True)
            self.notify("%s recorded a new commission from %s." % (HELPER_INFO["assistant"]["name"], actor.name), "good", 7.0)
        else:
            actor.begin_departure("The request is already in Bal's journal.", 1.4, True)

    def accept_lead(self, screen, lead):
        """Accept an assistant-recorded request from the journal."""
        req = dict(lead.get("request") or {})
        if not req or any(o.get("id") == req.get("id") for o in self.story_state.active_orders):
            self.story_state.remove_commission_lead(lead.get("id"))
            return None, "That commission is no longer available."
        due = float(lead.get("offer_due", 0.0))
        if due <= self._clock.stamp:
            self.story_state.remove_commission_lead(lead.get("id"))
            return None, "That offer has expired. Declining it did not hurt Bal's reputation."
        order = {
            "id": req.get("id"), "name": lead.get("name", "Client"),
            "species": lead.get("species", "dog"), "visit": int(lead.get("visit", 0)),
            "request": req, "due": due, "accepted_at": self._clock.stamp,
            "status": "away", "from_assistant": True,
        }
        service = req.get("service", "wait")
        if service in ("gramophone", "plant"):
            tx, tz = self.delivery_target(screen.game, req)
            order.update(status="delivery", target_x=tx, target_z=tz,
                         destination_label=req.get("destination_label", "the marked place"))
        else:
            return_at = min(due - 25.0, self._clock.stamp + self.rng.uniform(80.0, 210.0))
            self.story_state.schedule_visit({
                "kind": "order_return", "at": return_at, "order_id": order["id"],
                "species": order["species"], "name": order["name"],
                "visit": order["visit"],
            })
        self.story_state.upsert_order(order)
        self.story_state.remove_commission_lead(lead.get("id"))
        self.notify("Bal accepted %s's recorded commission." % order["name"], "good")
        return order, "Commission accepted. It is now in Active Missions."

    def decline_lead(self, lead):
        removed = self.story_state.remove_commission_lead(lead.get("id"))
        if removed:
            self.notify("Bal declined %s's recorded request." % lead.get("name", "the request"), "normal")
        return removed

    def _fail_order(self, order, actor=None):
        self.story_state.miss_accepted(order)
        self.story_state.remove_order(order.get("id"))
        if self.story_state.active_delivery and self.story_state.active_delivery.get("order_id") == order.get("id"):
            self.story_state.active_delivery = None
            self.story_state.save()
        if actor is not None:
            actor.begin_departure("The deadline has passed. I have to leave now.", 2.0, False)
        self.notify("Deadline missed for %s. Reputation fell." % order.get("name", "a client"), "bad", 8.0)

    def _send_accepted_away(self, actor, order, line):
        request = order.get("request") or {}
        remaining = max(20.0, float(order.get("due", self._clock.stamp + 120)) - self._clock.stamp)
        delay = min(remaining - 10.0, max(35.0, remaining * self.rng.uniform(0.35, 0.68)))
        if delay > 8.0:
            order["status"] = "away"
            self.story_state.upsert_order(order)
            self.story_state.schedule_visit({
                "kind": "order_return", "at": self._clock.stamp + delay,
                "order_id": order.get("id"), "species": order.get("species"),
                "name": order.get("name"), "visit": order.get("visit", 0),
            })
            actor.begin_departure(line, 2.0, True)
            self.notify("%s left for now and will return before the deadline." % actor.name, "normal")
        else:
            self._fail_order(order, actor)

    def order_for(self, actor):
        rid = actor.order_id or actor.request.get("id")
        return next((o for o in self.story_state.active_orders if o.get("id") == rid), None)

    def actor_for_order(self, request_id):
        return next((a for a in self.actors if a.order_id == request_id), None)

    def interactable(self, cat):
        queue = self._at_shop()
        if not queue:
            return None
        ranked = sorted(queue, key=lambda a: math.hypot(a.animal.x - cat.x,
                                                        a.animal.z - cat.z))
        nearest = ranked[0]
        if math.hypot(nearest.animal.x - cat.x,
                      nearest.animal.z - cat.z) <= 120.0:
            return nearest
        first = queue[0]
        counter = (self.shop.x, self.shop.z - 70.0)
        if math.hypot(cat.x - counter[0], cat.z - counter[1]) <= 120.0:
            return first
        return None

    def prompt(self, cat):
        actor = self.interactable(cat)
        if actor is None:
            return None
        if actor.social:
            return "E  Hear what %s came back to say" % actor.name
        if actor.accepted:
            return "E  Talk to %s about the order" % actor.name
        if actor.visit:
            return "E  Welcome %s back" % actor.name
        return "E  Greet %s" % actor.name

    def _accept(self, screen, actor):
        req = actor.request
        actor.accepted = True
        due = self._close_stamp(self._clock, int(req.get("due_day_offset", 0)))
        order = {
            "id": req.get("id"), "name": actor.name, "species": actor.species,
            "visit": actor.visit, "request": req, "due": due,
            "accepted_at": self._clock.stamp, "status": "waiting",
        }
        service = req.get("service", "wait")
        if service in ("gramophone", "plant"):
            tx, tz = self.delivery_target(screen.game, req)
            order.update(status="delivery", target_x=tx, target_z=tz,
                         destination_label=req.get("destination_label", "the marked place"))
            self.story_state.upsert_order(order)
            actor.begin_departure(
                "Please take it to %s. The gold marker will show you the way." % order["destination_label"],
                2.2, True)
            self.notify("Choose the delivery item for %s." % actor.name, "warning")
            return order
        if service in ("return_later", "return_tomorrow"):
            delay = float(req.get("return_delay", 120.0))
            return_at = min(due - 20.0, self._clock.stamp + delay)
            order["status"] = "away"
            self.story_state.upsert_order(order)
            self.story_state.schedule_visit({
                "kind": "order_return", "at": return_at, "order_id": order["id"],
                "species": actor.species, "name": actor.name, "visit": actor.visit,
            })
            when = "tomorrow" if delay >= 1000 else "later today"
            actor.begin_departure("I will come back %s." % when, 1.8, True)
            self.notify("%s will return %s." % (actor.name, when), "normal")
            return order
        actor.patience_stamp = min(due, self._clock.stamp + float(req.get("accepted_patience", 170)))
        order["status"] = "waiting"
        self.story_state.upsert_order(order)
        actor.say("I will wait nearby. Please watch the time.", 3.0)
        return order

    @staticmethod
    def _bal_accept_line(service):
        if service == "wait":
            return "I understand. I will start now."
        if service in ("return_later", "return_tomorrow"):
            return "All right. I will have it ready when you return."
        return "All right. First, I need to choose what I will carry."

    def _finish_accept_dialogue(self, screen, order):
        if (order.get("request") or {}).get("service") in ("gramophone", "plant"):
            screen._prepare_order(order, None)

    def open_conversation(self, screen, actor):
        if actor.social:
            pages = [self.rng.choice(_CALLBACKS)]
            choices = [("That is good to hear", "bye"), ("Do you need anything else?", "new")]

            def social_choice(value):
                if value == "new" and self._clock.shop_open:
                    actor.social = False
                    actor.accepted = False
                    actor.fulfilled = False
                    actor.request = self._new_request(actor.species, actor.visit)
                    actor.order_id = actor.request.get("id")
                    actor.patience_stamp = self._clock.stamp + float(actor.request.get("patience_minutes", 90))
                    actor.state = "waiting"
                    self.open_conversation(screen, actor)
                else:
                    actor.begin_departure("Thank you, Bal. See you again.", 1.4, True)
            screen.dialogue.open(actor.name, actor.species, pages, choices, social_choice,
                                 portrait_entity=actor.animal)
            return

        req = actor.request
        if not actor.accepted:
            greeting = self.rng.choice(_RETURN_GREETINGS if actor.visit else _NEW_GREETINGS)
            pages = [greeting, req.get("flavor", "I have a specific request.")]
            choices = [("Accept", "accept"), ("Show the details", "more"), ("Decline", "decline")]

            def chose(value):
                if value == "accept":
                    order = self._accept(screen, actor)
                    line = self._bal_accept_line(req.get("service", "wait"))
                    screen.dialogue.open("Bal", "bal", [line],
                        callback=lambda _v: self._finish_accept_dialogue(screen, order),
                        portrait_entity=screen.game.cat)
                elif value == "more":
                    screen.dialogue.open(actor.name, actor.species, [self._explain(req)],
                        [("Accept", "accept"), ("Decline", "decline")],
                        lambda v: self._second_choice(screen, actor, v),
                        portrait_entity=actor.animal)
                elif value == "decline":
                    actor.begin_departure("That is fine. Thank you for telling me.", 1.6, True)
                    self._reschedule_unmet(actor)
            screen.dialogue.open(actor.name, actor.species, pages, choices, chose,
                                 portrait_entity=actor.animal)
            return

        order = self.order_for(actor)
        if order is None:
            actor.begin_departure("This order is no longer active. I will come back another day.", 1.5, False)
            return
        service = req.get("service", "wait")
        if req.get("kind") == "song":
            prompt = ("Have you chosen the song for %s?" % req.get("destination_label")
                      if service == "gramophone" else "Are you ready to play the song?")
            choices = [("Choose a song", "song"), ("Not yet", "later"), ("Cancel order", "cancel")]
        else:
            prompt = ("Have you chosen the seed for %s?" % req.get("destination_label")
                      if service == "plant" else "Have you chosen a sound seed?")
            choices = [("Choose a seed", "sprout"), ("Not yet", "later"), ("Cancel order", "cancel")]

        def deliver_choice(value):
            if value == "song":
                screen.start_client_song(actor)
            elif value == "sprout":
                screen.start_client_sprout(actor)
            elif value == "cancel":
                if self.story_state.cancel_accepted(order):
                    actor.accepted = False
                    if (screen.field_delivery is not None
                            and screen.field_delivery.get("order_id") == order.get("id")):
                        screen.field_delivery = None
                    actor.begin_departure("I understand. I will leave the order with you another time.", 1.8, False)
                    self.notify("Accepted commission cancelled: reputation -%.2f." %
                                float(getattr(config, "STORY_CANCEL_REP_LOSS", 0.15)), "bad", 6.0)
                else:
                    self.notify("The commission could not be cancelled. Please try again.", "bad", 5.0)
        screen.dialogue.open(actor.name, actor.species, [prompt], choices, deliver_choice,
                             portrait_entity=actor.animal)

    def _second_choice(self, screen, actor, value):
        if value == "accept":
            order = self._accept(screen, actor)
            screen.dialogue.open("Bal", "bal", [self._bal_accept_line(actor.request.get("service", "wait"))],
                callback=lambda _v: self._finish_accept_dialogue(screen, order),
                portrait_entity=screen.game.cat)
        else:
            actor.begin_departure("No problem. I will come back another time.", 1.5, True)
            self._reschedule_unmet(actor)

    @staticmethod
    def _explain(req):
        service = req.get("service", "wait")
        if req.get("kind") == "song":
            lo, hi = req.get("tempo", (80, 120))
            tags = list(req.get("tags", (req.get("primary", "warm"),)))
            needs = " and ".join(req.get("needs", ("melody",)))
            core = "I want a %s song at %d to %d BPM. It needs %s." % (
                " and ".join(tags[:2]), lo, hi, needs)
        else:
            core = "I need a %s seed with a %s mood from the %s region." % (
                req.get("want_type", "note"),
                " or ".join(req.get("tags", ("warm",))[:2]),
                req.get("region", "meadow"))
        if service == "wait":
            return core + " I will wait near the shop for a while."
        if service == "return_later":
            return core + " I will return later today."
        if service == "return_tomorrow":
            return core + " I will return tomorrow before closing time."
        if service == "gramophone":
            return core + " Please place a gramophone at %s." % req.get("destination_label", "the marked place")
        return core + " Please plant it at %s." % req.get("destination_label", "the marked place")

    def delivery_target(self, game, request):
        rng = random.Random(int(request.get("seed", 1)) ^ 0xD311)
        for _ in range(18):
            ang = rng.random() * math.tau
            dist = rng.uniform(420.0, 980.0)
            x = self.shop.x + math.cos(ang) * dist
            z = self.shop.z + math.sin(ang) * dist
            x, z = game.water.nearest_dry(x, z)
            if all(math.hypot(wx - x, wz - z) > r + 55.0
                   for r, wx, wz in game.world.solids_near(x, z)):
                return x, z
        return game.water.nearest_dry(self.shop.x + 520.0, self.shop.z + 180.0)

    def score_song(self, profile, req, project=None):
        project_id = getattr(project, "id", None)
        content_hash = scoring.project_content_hash(project) if project is not None else None
        times_sold = (self.story_state.song_times_sold(project_id, content_hash)
                      if content_hash is not None else 0)
        result = scoring.score_song(profile, req, times_sold=times_sold)
        request_id = req.get("id")
        self._score_cache[request_id] = result
        if content_hash is not None:
            self._sale_cache[request_id] = (project_id, content_hash)
        return result.total

    def score_sprout(self, comp, req):
        result = scoring.score_sprout(comp, req)
        self._score_cache[req.get("id")] = result
        return result.total

    def _result_values(self, actor_or_order, score):
        score = max(0.0, min(1.0, float(score)))
        if isinstance(actor_or_order, ClientActor):
            req = actor_or_order.request
            order = self.order_for(actor_or_order) or {}
        else:
            order = actor_or_order
            req = actor_or_order.get("request", {})
        passed = score >= float(getattr(config, "STORY_PASS_SCORE", 0.55))
        stars = 1 if not passed else max(1, min(5, 1 + round(score * 4)))
        difficulty = max(1, min(5, int(req.get("difficulty", 1))))
        base = (float(getattr(config, "STORY_PAY_BASE", 16))
                + float(getattr(config, "STORY_PAY_DIFFICULTY", 12)) * difficulty)
        accepted_at = float(order.get("accepted_at", self._clock.stamp if self._clock else 0.0))
        now = float(self._clock.stamp if self._clock else accepted_at)
        speed_window = float(getattr(config, "STORY_SPEED_WINDOW", 180.0))
        speed = (float(getattr(config, "STORY_SPEED_BONUS", 1.25))
                 if now - accepted_at <= speed_window else 1.0)
        rep_mult = (float(getattr(config, "STORY_REP_PAY_BASE", 0.70))
                    + float(getattr(config, "STORY_REP_PAY_STEP", 0.12))
                    * float(self.story_state.reputation))
        if passed:
            coins = round(base * (0.25 + 0.75 * score) * speed * rep_mult)
        else:
            coins = round(base * float(getattr(config, "STORY_FAIL_PAY_RATE", 0.10)))
        return score, passed, stars, max(1, int(coins)), req

    def complete(self, screen, actor, score, item_name):
        score, passed, stars, coins, req = self._result_values(actor, score)
        actor.fulfilled = True
        actor.result = (score, stars, coins)
        actor.state = "celebrate" if passed else "disappointed"
        actor.depart_after = 8.0  # guaranteed cleanup even if the result dialogue is escaped
        actor.depart_happy = passed
        actor.say("Oh!" if passed else "Hmm...", 1.2)
        if not self.story_state.finish_visit(actor.name, stars, coins, req, item_name):
            self.notify("The result could not be saved. The commission remains active.", "bad", 6.0)
            return False
        sale = self._sale_cache.pop(req.get("id"), None)
        if sale is not None:
            self.story_state.mark_song_sold(sale[0], sale[1])
        self.story_state.remove_order(req.get("id"))
        self._schedule_callback(actor, req)
        reactions = ([
            "This matches my request very well.",
            "Yes. This is what I was hoping for.",
            "The important parts are all here.",
            "This will work perfectly for the occasion.",
        ] if passed else [
            "This does not match enough of my request.",
            "Some important parts are missing.",
            "I can hear the idea, but it needs more work.",
        ])
        reaction = self.rng.choice(reactions)
        stars_text = "*" * stars + "-" * (5 - stars)
        breakdown = self._score_cache.pop(req.get("id"), None)
        pages = [reaction, "%s. %s. You earned %d coins." % (item_name, stars_text, coins)]
        if breakdown is not None:
            details = ", ".join("%s %d%%" % (key.title(), int(value * 100 + 0.5))
                                for key, value in list(breakdown.parts.items())[:4])
            pages.append("Score %d%%. %s." % (int(breakdown.total * 100 + 0.5), details))
            if breakdown.notes:
                pages.append(breakdown.notes[0])

        def finish(_value):
            actor.begin_departure("Thank you, Bal. I will see you again.", 1.6, passed)
        screen.dialogue.open(actor.name, actor.species, pages,
                             [("Safe travels", "bye")], finish,
                             portrait_entity=actor.animal)
        self.notify("Commission complete: %s earned %d coins." % (actor.name, coins), "good" if passed else "bad")
        return True

    def complete_remote(self, screen, order, score, item_name):
        score, passed, stars, coins, req = self._result_values(order, score)
        if not self.story_state.finish_visit(order.get("name", "Client"), stars, coins, req, item_name):
            self.notify("The delivery result could not be saved. It will be retried safely.", "bad", 6.0)
            return False
        sale = self._sale_cache.pop(req.get("id"), None)
        if sale is None and order.get("project_hash"):
            sale = (order.get("project_id"), order.get("project_hash"))
        if sale is not None:
            self.story_state.mark_song_sold(sale[0], sale[1])
        self.story_state.remove_order(order.get("id"))
        self.story_state.active_delivery = None
        self.story_state.save()
        self._schedule_callback(order, req)
        stars_text = "*" * stars + "-" * (5 - stars)
        pages = [
            "Bal leaves %s at %s." % (item_name, order.get("destination_label", "the marked place")),
            "%s. You earned %d coins. %s may return another day." %
            (stars_text, coins, order.get("name", "The client")),
        ]
        breakdown = self._score_cache.pop(req.get("id"), None)
        if breakdown is not None:
            details = ", ".join("%s %d%%" % (key.title(), int(value * 100 + 0.5))
                                for key, value in list(breakdown.parts.items())[:4])
            pages.append("Score %d%%. %s." % (int(breakdown.total * 100 + 0.5), details))
            if breakdown.notes:
                pages.append(breakdown.notes[0])
        screen.story.queue("DELIVERY COMPLETE", pages,
                           icon="note", footer="press any key")
        self.notify("Field delivery completed for %s: +%d coins." % (order.get("name", "client"), coins),
                    "good" if passed else "bad", 8.0)
        return True

    def status(self, clock):
        at_shop = len([a for a in self._at_shop() if not a.social])
        away = len([o for o in self.story_state.active_orders
                    if o.get("status") in ("away", "delivery", "courier")])
        next_due = None
        next_name = None
        for order in self.story_state.active_orders:
            due = float(order.get("due", 0.0))
            if next_due is None or due < next_due:
                next_due = due
                next_name = order.get("name")
        urgent = False
        due_text = "No accepted deadline"
        if next_due is not None:
            mins = max(0, int(next_due - clock.stamp + 0.5))
            urgent = mins <= 60
            due_text = "%s due in %dm" % (next_name, mins)
        return {
            "day": clock.day, "time": clock.format_time(), "shop_open": clock.shop_open,
            "at_shop": at_shop, "away": away,
            "orders": len(self.story_state.active_orders),
            "due_text": due_text, "urgent": urgent,
            "alert": dict(self.alert) if self.alert else None,
        }

    def world_drawables(self, game):
        out = []
        cam = game.cam
        for actor in self.actors:
            an = actor.animal
            pr = project(an.x, an.z, cam)
            if pr is None:
                continue
            sx, sy, sc = pr
            if sc <= 0.11:
                continue
            draw_scale = sc * config.SC * an.spec.draw_scale

            def draw_one(surf, a=an, px=sx, py=sy, ds=draw_scale, raw=sc):
                a.draw(surf, px, py, ds, raw, swim=a.swim, fade=0.0)
            out.append((sy, 40, draw_one))
        return out

    def draw_bubbles(self, surf, game):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        for actor in self.actors:
            if actor.bubble_t <= 0.0 or not actor.bubble:
                continue
            pr = project(actor.animal.x, actor.animal.z, game.cam)
            if pr is None:
                continue
            px, py = config.canvas_to_window(pr[0], pr[1] - 46 * pr[2] * config.SC)
            max_w = S(300)
            lines = ui.wrap_lines(actor.bubble, max_w - S(22), S(13))[:3]
            lh = ui.pixel_line_height(S(13)) + S(3)
            bw = min(max_w, max(S(120), max([ui.pixel_measure(line, S(13))[0] for line in lines] or [S(80)]) + S(22)))
            bh = S(18) + len(lines) * lh
            box = pygame.Rect(0, 0, bw, bh)
            box.midbottom = (int(px), int(py) - S(8))
            box.clamp_ip(pygame.Rect(S(8), S(8), w - S(16), h - S(16)))
            ui.draw_panel(surf, box, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                          radius=S(8), shadow=False)
            y = box.y + S(9)
            for line in lines:
                ui.pixel_text(surf, line, S(13), box.centerx, y,
                              color=ui.INK, center=True, bold=False)
                y += lh
