"""Story mode: Bal arrives by boat and runs a living island music shop."""

import math

import pygame

from .. import config, ui
from ..components import catalog
from ..projection import project
from ..render.sprouts import draw_plant_preview
from ..render.garden_objects import draw_gramophone
from ..audio import sfx
from ..logging_utils import get_logger
from ..story.clock import StoryClock
from ..story.state import StoryState
from ..story.shop import Shop
from ..story.intro import LandingIntro
from ..story.clients import ClientDirector
from ..story.dialogue import DialogueOverlay
from ..story.decorations import DecorationManager, definition as decoration_definition
from ..story.helpers import HelperManager, HELPER_INFO
from ..story.merchant import Merchant, MerchantOverlay
from ..story.journal import StoryJournalOverlay
from .explore import ExploreScreen

_LOG = get_logger("story_screen")


class StoryScreen(ExploreScreen):
    """The existing world with a persistent clock, shop and client simulation."""

    def __init__(self, app):
        super().__init__(app)
        self.story_state = None
        self.clock = None
        self.shop = None
        self.intro = None
        self.clients = None
        self.dialogue = DialogueOverlay()
        self.delivery_actor = None
        self.delivery_order = None
        self.delivery_project = None
        self.field_delivery = None
        self.tray_for = "plant"
        self._clients_started = False
        self._save_t = 0.0
        self.decorations = None
        self.helpers = None
        self.merchant = None
        self.market = None
        self.soundbook = StoryJournalOverlay(app, self)
        self._sleep_confirm = False
        self._sleep_confirm_rects = {}

    def rebuild_world(self):
        super().rebuild_world()
        self.story_state = None
        self.clock = None
        self.shop = None
        self.intro = None
        self.clients = None
        self.dialogue.close()
        self.delivery_actor = None
        self.delivery_order = None
        self.delivery_project = None
        self.field_delivery = None
        self._clients_started = False
        self._save_t = 0.0
        self.decorations = None
        self.helpers = None
        self.merchant = None
        self.market = None
        self.soundbook = StoryJournalOverlay(self.app, self)
        self._sleep_confirm = False
        self._sleep_confirm_rects = {}

    def ensure_game(self):
        game = super().ensure_game()
        if self.story_state is None:
            self.story_state = StoryState()
            self.clock = StoryClock(self.story_state.day,
                                    self.story_state.clock_minutes)
            self.shop = Shop(self.story_state.shop_x, self.story_state.shop_z,
                             built=1.0 if self.story_state.has_shop else 0.0)
            self.intro = LandingIntro(self.story_state, self.shop)
            self.clients = ClientDirector(self.story_state, self.shop,
                                          self.app.world_state.seed)
            self.decorations = DecorationManager(self.story_state)
            self.helpers = HelperManager(self.story_state, self.app.collection, self.shop,
                                         self.app.world_state.seed)
            self.merchant = Merchant(self.story_state, self.app.collection, self.shop,
                                     self.app.world_state.seed, self.helpers)
            self.market = MerchantOverlay(self.app, self.merchant)
            self.soundbook = StoryJournalOverlay(self.app, self)
            self.field_delivery = (dict(self.story_state.active_delivery)
                                   if self.story_state.active_delivery else None)
            if self.story_state.has_shop:
                self._restore_boat(game)
            else:
                self.intro.begin(game)
            self._wire_solids()
        return game

    def _restore_boat(self, game):
        if self.story_state.boat_x is None or self.story_state.boat_z is None:
            return
        bo = game.water.spawn_boat(self.story_state.boat_x,
                                   self.story_state.boat_z)
        bo.occupied = False
        bo.facing = -1
        game.cat.x = self.shop.x
        game.cat.z = self.shop.z - 145.0
        game.cat.x, game.cat.z = game.water.nearest_dry(game.cat.x, game.cat.z)
        game.cam.snap(game.cat.x, game.cat.z)

    def _wire_solids(self):
        def solids(x, z):
            out = []
            if self.garden is not None:
                out.extend(self.garden.solids_near(x, z))
            if self.shop is not None:
                out.extend(self.shop.solids_near(x, z))
            return out
        self.game.landmark_solids = solids

    def on_enter(self):
        self.ensure_game()
        self._was_in_water = False
        self._set_paused(False)
        pygame.mouse.set_visible(False)
        if self.intro.phase == "done" and not self._clients_started:
            self.clients.begin(self.clock)
            self._clients_started = True

    # ---------------------------------------------------------------- events
    def handle_event(self, e):
        if self.paused:
            self._pause_event(e)
            return

        if getattr(self, "_sleep_confirm", False):
            if e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e, pygame.K_y, pygame.K_z):
                    self._sleep_confirm = False
                    self._sleep_until_morning()
                elif e.key in (pygame.K_ESCAPE, pygame.K_n, pygame.K_q):
                    self._sleep_confirm = False
                    self._toast = "Bal stays awake."
                    self._toast_t = 1.8
                return
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                rects = getattr(self, "_sleep_confirm_rects", {})
                yes = rects.get("yes")
                no = rects.get("no")
                if yes and yes.collidepoint(e.pos):
                    self._sleep_confirm = False
                    self._sleep_until_morning()
                elif no and no.collidepoint(e.pos):
                    self._sleep_confirm = False
                    self._toast = "Bal stays awake."
                    self._toast_t = 1.8
                return

        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            if self.market is not None and self.market.active:
                self.market.close()
            elif self.decorations is not None and self.decorations.placing is not None:
                self.decorations.cancel()
                self._toast = "Decoration returned to shop storage."
                self._toast_t = 2.0
            elif self.dialogue.active:
                self.dialogue.close()
            elif self.picker is not None:
                self._close_picker()
            elif self.tray is not None:
                self._close_tray()
            elif self.intro.cinematic:
                return
            else:
                self._set_paused(True)
            return

        if (e.type == pygame.KEYDOWN and e.key == pygame.K_s
                and self.intro.active and self.intro.phase in ("sail", "hop", "cards")):
            self.intro.skip_to_placement(self.game, self.story)
            self._toast = "Choose a dry, open patch and press E."
            self._toast_t = 3.0
            return

        if self.market is not None and self.market.active:
            self.market.handle_event(e)
            return
        if self.story.handle_event(e):
            return
        if self.dialogue.handle_event(e):
            return
        if self.picker is not None:
            self._picker_event(e)
            return
        if self.tray is not None:
            self._tray_event(e)
            return

        if self.intro.cinematic:
            return
        if self.decorations is not None and self.decorations.placing is not None and e.type == pygame.KEYDOWN:
            if e.key == pygame.K_e:
                ok, message = self.decorations.place()
                self._toast = message
                self._toast_t = 2.8
                return
            if e.key == pygame.K_r:
                self.decorations.rotate()
                self._toast = "Decoration rotated."
                self._toast_t = 1.2
                return
            if e.key == pygame.K_q:
                self.decorations.cancel()
                self._toast = "Decoration returned to storage."
                self._toast_t = 2.0
                return
        if (e.type == pygame.KEYDOWN and e.key in (pygame.K_BACKSPACE, pygame.K_DELETE)
                and self.decorations is not None and self.decorations.placing is None):
            item = self.decorations.remove_nearest(self.game.cat.x, self.game.cat.z)
            if item is not None:
                self._toast = "%s returned to shop storage." % item["name"]
                self._toast_t = 2.5
                return
        if (e.type == pygame.KEYDOWN and e.key == pygame.K_z
                and self.game.cat.on_ground
                and (self.clock.minutes >= 18 * 60 or self.clock.minutes < 5 * 60 + 30)):
            self._sleep_confirm = True
            return
        if e.type == pygame.KEYDOWN and e.key == pygame.K_e and self.intro.placing:
            ok, message = self.intro.try_build()
            self._toast = message
            self._toast_t = 2.8
            if ok:
                try:
                    sfx.collect()
                except Exception:
                    pass
            return

        super().handle_event(e)

    def _sleep_until_morning(self):
        """Skip a closed-shop night and resolve every deadline coherently."""
        target_stamp = self.clock.day * 1440.0 + (8 * 60 + 30 - (5 * 60 + 30))
        self.clock.set_stamp(target_stamp)
        self.game.cat.sleeping = False
        if self.clients is not None and self._clients_started:
            self.clients.update(0.0, self.game, self.clock, ("shop_close", "new_day"),
                                assistant_active=self.helpers.assistant_active if self.helpers else False)
        if self.helpers is not None:
            self.helpers.update(0.0, self.clock, ("new_day",))
        if self.merchant is not None:
            self.merchant.update(0.0, self.clock)
        self._sync_field_delivery()
        self.story_state.sync_clock(self.clock, save=True)
        self._toast = "Bal sleeps until 08:30. A new day begins."
        self._toast_t = 3.4


    def _sleep_confirm_buttons(self):
        w, h = self.app.window.get_size()
        S = lambda v: ui.scaled(h, v)
        panel = pygame.Rect(0, 0, min(w - S(40), S(430)), S(180))
        panel.center = (w // 2, h // 2)
        yes = pygame.Rect(panel.x + S(34), panel.bottom - S(54), S(150), S(38))
        no = pygame.Rect(panel.right - S(184), panel.bottom - S(54), S(150), S(38))
        return yes, no

    def _draw_sleep_confirm(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((24, 22, 20, 140))
        surf.blit(veil, (0, 0))
        panel = pygame.Rect(0, 0, min(w - S(40), S(430)), S(180))
        panel.center = (w // 2, h // 2)
        ui.draw_panel(surf, panel, fill=ui.PAPER, edge=ui.PAPER_EDGE, radius=S(14), shadow=True)
        ui.pixel_text(surf, "SLEEP FOR THE NIGHT?", S(20), panel.centerx, panel.y + S(24), color=ui.INK, center=True)
        ui.pixel_text(surf, "Bal will sleep until 08:30 and begin a new day.", S(13), panel.centerx, panel.y + S(64), color=ui.INK_SOFT, center=True, bold=False)
        yes, no = self._sleep_confirm_buttons()
        ui.draw_panel(surf, yes, fill=ui.GRASS, edge=ui.GRASS_DK, radius=S(9), shadow=False)
        ui.pixel_text_center_box(surf, "YES, SLEEP", S(14), yes, color=ui.CREAM)
        ui.draw_panel(surf, no, fill=ui.PAPER_DK, edge=ui.PAPER_EDGE, radius=S(9), shadow=False)
        ui.pixel_text_center_box(surf, "NO, STAY AWAKE", S(14), no, color=ui.INK)

    def _pause_action(self, action):
        if action == "menu":
            self._set_paused(False)
            self.story_state.sync_clock(self.clock, save=True)
            self.app.exit_story_to_menu()
            return
        super()._pause_action(action)

    def _near_counter(self, reach=125.0):
        if not self.shop or not self.shop.ready:
            return False
        return math.hypot(self.game.cat.x - self.shop.x,
                          self.game.cat.z - (self.shop.z - 70.0)) <= reach

    def _pending_delivery_order(self):
        if self.field_delivery is not None:
            return None
        return next((o for o in self.story_state.active_orders
                     if o.get("status") == "delivery"), None)

    def _use_key(self):
        if self.merchant is not None and self.merchant.near(self.game.cat):
            self.market.open()
            self.merchant.say("Welcome, Bal. Have a look at today's cart.")
            return
        helper_kind = self.helpers.nearest(self.game.cat) if self.helpers is not None else None
        if helper_kind is not None:
            self._talk_helper(helper_kind)
            return
        if self.field_delivery is not None and self._near_delivery_target():
            self._finish_field_delivery()
            return
        actor = self.clients.interactable(self.game.cat) if self.clients else None
        if actor is not None:
            self.clients.open_conversation(self, actor)
            return
        order = self._pending_delivery_order()
        if order is not None and self._near_counter():
            self._prepare_order(order)
            return
        super()._use_key()

    def _talk_helper(self, kind):
        info = HELPER_INFO[kind]
        rec = self.helpers.record(kind)
        if kind == "assistant":
            pages = ["I will greet visitors and write their requests in the journal.",
                     "I do not accept work for you. You decide which commissions become active."]
        elif kind == "scout":
            pages = ["I am searching the %s today." % rec.get("region", "meadow"),
                     "I may return with a sound, a clue, or an honest report that I found nothing."]
        else:
            pages = ["I can carry ordinary prepared field deliveries.",
                     "Prepare the song or seed first, then assign the delivery from Active Missions."]
        visual = self.helpers.visuals.get(kind)
        self.dialogue.open("%s the %s" % (info["name"], info["species"]),
                           info["species"], pages, [("Thanks", "bye")],
                           portrait_entity=(visual.animal if visual is not None else None))

    # ------------------------------------------------------------ deliveries
    def _prepare_order(self, order, actor=None):
        self.delivery_actor = actor
        self.delivery_order = order
        request = order.get("request") or {}
        if request.get("kind") == "song":
            self._open_picker(purpose="client")
        else:
            self._open_client_tray()

    def start_client_song(self, actor):
        order = self.clients.order_for(actor)
        if order is None:
            return
        self._prepare_order(order, actor)

    def _open_client_tray(self):
        """Show every sound Bal owns, including permanent starter sounds."""
        seen = set()
        owned = []
        for comp in self.app.collection.owned_components():
            cid = comp.get("id")
            if cid and cid not in seen:
                seen.add(cid)
                owned.append(comp)
        if not owned:
            self._toast = "Bal does not have any sound seeds yet."
            self._toast_t = 3.0
            return
        order_rank = {"drum": 0, "rhythm": 1, "note": 2, "chord": 3,
                      "bass": 4, "loop": 5, "ambience": 6, "effect": 7}
        owned.sort(key=lambda c: (order_rank.get(c.get("type"), 9), c.get("name", "")))
        self.tray_for = "client"
        self.tray = {"idx": 0, "rects": [], "items": owned, "records": []}
        pygame.mouse.set_visible(True)

    def start_client_sprout(self, actor):
        order = self.clients.order_for(actor)
        if order is None:
            return
        self.delivery_actor = actor
        self.delivery_order = order
        self._open_client_tray()

    def _close_tray(self):
        super()._close_tray()
        self.tray_for = "plant"

    def _set_field_delivery(self, order, payload):
        job = {
            "order_id": order.get("id"),
            "name": order.get("name"),
            "species": order.get("species"),
            "target_x": float(order.get("target_x")),
            "target_z": float(order.get("target_z")),
            "destination_label": order.get("destination_label", "the marked place"),
        }
        job.update(payload)
        if payload.get("kind") == "gramophone":
            order["project_id"] = payload.get("project_id")
            order["project_hash"] = payload.get("project_hash")
            self.story_state.upsert_order(order)
        self.field_delivery = job
        self.story_state.active_delivery = dict(job)
        self.story_state.save()
        self._toast = "Delivery prepared. Follow the gold marker to %s." % job["destination_label"]
        self._toast_t = 4.0

    def _tray_pick(self, item):
        if self.tray_for != "client":
            return super()._tray_pick(item)
        order = self.delivery_order
        actor = self.delivery_actor
        self.tray = None
        self.tray_for = "plant"
        pygame.mouse.set_visible(False)
        if order is None or not isinstance(item, dict):
            return
        request = order.get("request") or {}
        score = self.clients.score_sprout(item, request)
        if request.get("service") == "plant":
            self._set_field_delivery(order, {
                "kind": "sprout", "item_id": item.get("id"),
                "item_name": item.get("name", "Sound seed"), "score": score,
            })
        else:
            if actor is None or actor.state in ("leaving", "gone"):
                self._toast = "The client has already left the shop."
                self._toast_t = 2.8
                self.delivery_actor = None
                self.delivery_order = None
                return
            # Starter sounds are permanent tools. Bal can make a cutting for a
            # client without deleting the tool from the collection.
            if not item.get("starter") and not self.app.collection.consume(item["id"]):
                self._toast = "That seed is no longer in Bal's collection."
                self._toast_t = 2.8
                return
            self.clients.complete(self, actor, score, item.get("name", "Sound seed"))
        self.delivery_actor = None
        self.delivery_order = None
        self.delivery_project = None

    def _perform(self, proj):
        purpose = self.picker_for
        self._close_picker()
        if proj is None:
            return
        if purpose == "client" and self.delivery_order is not None:
            order = self.delivery_order
            request = order.get("request") or {}
            if request.get("service") == "gramophone":
                from ..music import profile as profile_mod
                from ..story import scoring as story_scoring
                score = self.clients.score_song(profile_mod.analyze(proj), request, project=proj)
                self._set_field_delivery(order, {
                    "kind": "gramophone", "project_id": proj.id,
                    "project_hash": story_scoring.project_content_hash(proj),
                    "item_name": proj.name, "score": score,
                })
                if self.delivery_actor is not None:
                    self.delivery_actor.begin_departure(
                        "I will meet you there after you place it.", 1.8, True)
                self.delivery_actor = None
                self.delivery_order = None
                return

        self.perf.start(proj, self.game.cat)
        self.delivery_project = proj if purpose == "client" else None
        if purpose == "client" and self.delivery_actor is not None:
            self.delivery_actor.state = "listening"
            self._toast = "%s listens closely to \"%s\"..." % (
                self.delivery_actor.name, proj.name)
        else:
            self._toast = "Bal plays  \"%s\"  for the island..." % proj.name
        self._toast_t = 2.8

    def _near_delivery_target(self):
        if self.field_delivery is None:
            return False
        return math.hypot(self.game.cat.x - float(self.field_delivery.get("target_x", 0.0)),
                          self.game.cat.z - float(self.field_delivery.get("target_z", 0.0))) <= 92.0

    def _field_order(self):
        if self.field_delivery is None:
            return None
        rid = self.field_delivery.get("order_id")
        return next((o for o in self.story_state.active_orders if o.get("id") == rid), None)

    def _finish_field_delivery(self):
        job = self.field_delivery
        order = self._field_order()
        if job is None or order is None:
            self.field_delivery = None
            self.story_state.active_delivery = None
            self.story_state.save()
            return
        x, z = float(job["target_x"]), float(job["target_z"])
        if job.get("kind") == "sprout":
            comp = catalog.get(job.get("item_id"))
            if comp is None or not self.app.collection.owns(comp["id"]):
                self._toast = "Bal no longer has that sound seed. Choose another one."
                self._toast_t = 3.2
                self.field_delivery = None
                self.story_state.active_delivery = None
                self.story_state.save()
                return
            planted, why = self.sprouts.plant(comp["id"], x, z)
            if planted is None:
                self._toast = why or "The marker needs a little clearer ground."
                self._toast_t = 3.0
                return
            if not comp.get("starter") and not self.app.collection.consume(comp["id"]):
                self.sprouts.uproot(planted)
                self._toast = "That seed is no longer in Bal's collection."
                self._toast_t = 3.0
                return
        else:
            try:
                proj = self.app.projects.load(job.get("project_id"))
            except Exception:
                proj = None
            if proj is None:
                self._toast = "That saved song could not be loaded. Prepare the delivery again."
                self._toast_t = 3.2
                self.field_delivery = None
                self.story_state.active_delivery = None
                self.story_state.save()
                return
            self.garden.plant_gramophone(proj, x, z)
        self.clients.complete_remote(self, order, float(job.get("score", 0.0)),
                                     job.get("item_name", "Delivery"))
        self.field_delivery = None
        self.delivery_actor = None
        self.delivery_order = None
        self.delivery_project = None

    def assign_courier(self, order):
        if self.helpers is None or not self.helpers.can_courier(order):
            return False, "%s can only take ordinary difficulty 1 to 3 field deliveries while working." % HELPER_INFO["courier"]["name"]
        if self.field_delivery is None or self.field_delivery.get("order_id") != order.get("id"):
            return False, "Prepare the song or seed first. Then the courier can carry it."
        job = dict(self.field_delivery)
        if job.get("kind") == "sprout":
            comp = catalog.get(job.get("item_id"))
            if comp is None or not self.app.collection.owns(comp.get("id")):
                return False, "That sound seed is no longer available."
        elif job.get("kind") == "gramophone":
            if self.app.projects.load(job.get("project_id")) is None:
                return False, "That saved song could not be loaded. Choose another song."
        job["complete_at"] = self.clock.stamp + self.helpers.courier_minutes()
        job["order_id"] = order.get("id")
        job["placed"] = False
        job["resource_consumed"] = False
        snapshot_jobs = list(self.story_state.courier_jobs)
        snapshot_orders = list(self.story_state.active_orders)
        snapshot_delivery = self.story_state.active_delivery
        self.story_state.courier_jobs.append(job)
        updated = dict(order)
        updated["status"] = "courier"
        self.story_state.active_orders = [o for o in self.story_state.active_orders
                                          if o.get("id") != updated.get("id")]
        self.story_state.active_orders.append(updated)
        self.story_state.active_delivery = None
        if not self.story_state.save():
            self.story_state.courier_jobs = snapshot_jobs
            self.story_state.active_orders = snapshot_orders
            self.story_state.active_delivery = snapshot_delivery
            return False, "The courier job could not be saved. Please try again."
        self.field_delivery = None
        return True, "%s took the delivery. It should arrive in about %d in-game minutes." % (HELPER_INFO["courier"]["name"], int(self.helpers.courier_minutes()))

    def _courier_object_exists(self, job):
        x = float(job.get("target_x", 0.0))
        z = float(job.get("target_z", 0.0))
        if job.get("kind") == "sprout":
            return any(s.comp_id == job.get("item_id") and abs(s.x - x) < .2 and abs(s.z - z) < .2
                       for s in self.sprouts.sprouts)
        if job.get("kind") == "gramophone":
            return any(g.song_id == job.get("project_id") and abs(g.x - x) < .2 and abs(g.z - z) < .2
                       for g in self.garden.gramophones)
        return False

    def _courier_failure(self, job, message):
        job["last_error"] = str(message)
        job["retry_at"] = self.clock.stamp + 30.0
        self.clients.notify("Courier delivery failed. The order remains active.", "bad", 6.0)
        _LOG.warning("Courier job %s failed: %s", job.get("order_id"), message)

    def _process_courier_jobs(self):
        if not self.story_state.courier_jobs:
            return
        remaining = []
        changed = False
        for job in self.story_state.courier_jobs:
            order = next((o for o in self.story_state.active_orders
                          if o.get("id") == job.get("order_id")), None)
            if order is None:
                changed = True
                continue
            due = float(job.get("complete_at", self.clock.stamp + 1))
            retry_at = float(job.get("retry_at", due))
            if self.clock.stamp < max(due, retry_at):
                remaining.append(job)
                continue
            x = float(job.get("target_x", order.get("target_x", 0.0)))
            z = float(job.get("target_z", order.get("target_z", 0.0)))
            placed_object = None

            if job.get("placed") and not self._courier_object_exists(job):
                job["placed"] = False
                job["resource_consumed"] = False
                changed = True

            if not job.get("placed"):
                try:
                    if job.get("kind") == "sprout":
                        comp = catalog.get(job.get("item_id"))
                        collection = getattr(self.app, "collection", None)
                        owns_seed = (comp is not None and (comp.get("starter") or
                                     (collection is not None and collection.owns(job.get("item_id")))))
                        if not owns_seed:
                            raise ValueError("required sound seed is unavailable")
                        placed_object, why = self.sprouts.plant(comp["id"], x, z)
                        if placed_object is None:
                            raise RuntimeError(why or "sprout placement was rejected")
                    elif job.get("kind") == "gramophone":
                        proj = self.app.projects.load(job.get("project_id"))
                        if proj is None:
                            raise ValueError("saved song is missing or invalid")
                        placed_object = self.garden.plant_gramophone(proj, x, z)
                        if placed_object is None:
                            raise RuntimeError("gramophone placement could not be saved")
                    else:
                        raise ValueError("unknown courier delivery type")
                    can_inspect_world = ((job.get("kind") == "sprout" and
                                          hasattr(self.sprouts, "sprouts")) or
                                         (job.get("kind") == "gramophone" and
                                          hasattr(self.garden, "gramophones")))
                    if can_inspect_world and not StoryScreen._courier_object_exists(self, job):
                        raise RuntimeError("world object was not created")
                    if not can_inspect_world and placed_object is None:
                        raise RuntimeError("world object was not created")
                except Exception as exc:
                    StoryScreen._courier_failure(self, job, exc)
                    remaining.append(job)
                    changed = True
                    continue

                consumed_record = None
                comp = catalog.get(job.get("item_id")) if job.get("kind") == "sprout" else None
                if comp is not None and not comp.get("starter"):
                    consumed_record = self.app.collection.found.get(comp["id"])
                    if not self.app.collection.consume(comp["id"]):
                        self.sprouts.uproot(placed_object)
                        StoryScreen._courier_failure(self, job, "required sound seed could not be consumed")
                        remaining.append(job)
                        changed = True
                        continue
                    job["resource_consumed"] = True
                job["placed"] = True
                job.pop("last_error", None)
                job.pop("retry_at", None)
                if not self.story_state.save():
                    if job.get("kind") == "sprout":
                        self.sprouts.uproot(placed_object)
                        if consumed_record is not None:
                            self.app.collection.found[comp["id"]] = consumed_record
                            self.app.collection.save()
                    elif placed_object is not None:
                        self.garden.remove_gramophone(placed_object)
                    job["placed"] = False
                    job["resource_consumed"] = False
                    StoryScreen._courier_failure(self, job, "courier state could not be saved")
                    remaining.append(job)
                    changed = True
                    continue
                changed = True

            completed = self.clients.complete_remote(
                self, order, float(job.get("score", 0.0)),
                "%s, delivered by %s" % (job.get("item_name", "Delivery"),
                                           HELPER_INFO["courier"]["name"]))
            if completed is True or (completed is None and
                                     not any(o.get("id") == order.get("id")
                                             for o in self.story_state.active_orders)):
                changed = True
                continue
            StoryScreen._courier_failure(self, job, "reward state could not be saved")
            remaining.append(job)
            changed = True

        if changed or remaining != self.story_state.courier_jobs:
            previous = self.story_state.courier_jobs
            self.story_state.courier_jobs = remaining
            if not self.story_state.save():
                self.story_state.courier_jobs = previous

    # --------------------------------------------------------------- clock/live
    def _start_clients_after_intro(self):
        if self._clients_started:
            return
        # The opening resolves just before business begins, so the first client
        # arrives promptly without pretending the construction took no time.
        if self.clock.minutes < 8 * 60 + 55 or self.clock.minutes >= 18 * 60:
            self.clock.set_time(8 * 60 + 55)
        self.story_state.sync_clock(self.clock, save=True)
        self.clients.begin(self.clock)
        self.clients._next_walkin = self.clock.stamp + 4.0
        self._clients_started = True

    def _advance_story_systems(self, dt):
        if self.intro.phase != "done":
            return
        if not self._clients_started:
            self._start_clients_after_intro()
        events = self.clock.advance(dt)
        if self.helpers is not None:
            self.helpers.update(dt, self.clock, events)
        if self.merchant is not None:
            self.merchant.update(dt, self.clock)
            if self.market is not None and self.market.active and not self.merchant.active:
                self.market.close()
                self.clients.notify("Poko packed the cart and left for the day.", "normal", 6.0)
        self.clients.update(dt, self.game, self.clock, events,
                            assistant_active=self.helpers.assistant_active if self.helpers else False)
        self._process_courier_jobs()
        self._sync_field_delivery()
        if self.helpers is not None:
            helper_alert = self.helpers.pop_alert()
            if helper_alert:
                self.clients.notify(helper_alert, "good", 8.0)
        self.story_state.sync_clock(self.clock, save=False)
        self._save_t += dt
        if self._save_t >= float(getattr(config, "STORY_SAVE_INTERVAL", 4.0)):
            self._save_t = 0.0
            self.story_state.sync_clock(self.clock, save=True)

    def update_offscreen(self, dt):
        """Advance the shop while the active Story profile is in the Maker."""
        self.ensure_game()
        if self.paused or self.intro.phase != "done":
            return
        if self.shop and not self.shop.building:
            self.shop.update(dt)
        self._advance_story_systems(dt)

    def _sync_field_delivery(self):
        """Drop an in-memory marker when its order expired or was cancelled."""
        if self.field_delivery is None:
            return
        rid = self.field_delivery.get("order_id")
        alive = any(o.get("id") == rid for o in self.story_state.active_orders)
        if alive:
            return
        self.field_delivery = None
        self.story_state.active_delivery = None
        self.story_state.save()
        self._toast = "That field order is no longer active."
        self._toast_t = 3.0

    def maker_status(self):
        self.ensure_game()
        status = self.clients.status(self.clock) if self.clients else {
            "day": self.clock.day, "time": self.clock.format_time(),
            "shop_open": self.clock.shop_open, "at_shop": 0, "away": 0,
            "orders": 0, "due_text": "No accepted deadline", "urgent": False,
            "alert": None,
        }
        if self.field_delivery is not None:
            status["delivery"] = "DELIVER TO %s" % self.field_delivery.get("destination_label", "MARKER").upper()
        elif self._pending_delivery_order() is not None:
            order = self._pending_delivery_order()
            status["delivery"] = "PREPARE %s'S FIELD ORDER" % order.get("name", "CLIENT").upper()
        else:
            status["delivery"] = None
        status["offers"] = len(self.story_state.commission_inbox)
        return status

    # ---------------------------------------------------------------- update
    def update(self, dt):
        if self.paused:
            return
        self.card.update(dt)
        self.story.update(dt)
        self.dialogue.update(dt)
        if self.market is not None:
            self.market.update(dt)
        if self._toast_t > 0:
            self._toast_t -= dt

        g = self.game
        g.set_daylight(self.clock.minutes, self.clock.day)
        before = self.intro.phase
        self.intro.update(dt, g, self.story)
        if self.intro.phase == "done" and before != "done":
            self._start_clients_after_intro()

        # Time and client patience continue through dialogue, request cards,
        # pickers and the seed tray. Only the pause menu stops the story clock.
        self._advance_story_systems(dt)

        modal = (self.picker is not None or self.tray is not None
                 or (self.market is not None and self.market.active)
                 or self.dialogue.active or self.story.blocking)
        if modal:
            return

        if self.decorations is not None:
            self.decorations.update_preview(g, self.shop)
        g.input_locked = self.perf.active or self.intro.cinematic
        g.song_ctx = self.perf.song_ctx()
        g.update(dt)

        if self.shop and not self.shop.building:
            self.shop.update(dt)
        self.perf.update(dt, g, self.app.window.get_size())
        self.sprouts.update(dt, g, muted=self.perf.active)
        self.garden.update(dt, self.perf, g.cat.x, g.cat.z,
                           beat_phase=self.sprouts.beat_phase())

        if self.clients and not self.dialogue.active and self.intro.phase == "done":
            for actor in self.clients._queue():
                if (actor.name == "Pip the dog" and actor.state == "waiting"
                        and not actor.greeted
                        and math.hypot(actor.animal.x - g.cat.x,
                                       actor.animal.z - g.cat.z) < 230.0):
                    actor.greeted = True
                    self.clients.open_conversation(self, actor)
                    break

        result = self.perf.pop_result()
        if result is not None and self.delivery_actor is not None:
            actor = self.delivery_actor
            if self.clients.order_for(actor) is None:
                self._toast = "The order ended before the performance was finished."
                self._toast_t = 3.2
                actor.begin_departure("The deadline has passed. I have to go.", 1.5, False)
            else:
                score = self.clients.score_song(result["profile"], actor.request,
                                                project=self.delivery_project)
                self.clients.complete(self, actor, score, result["song_name"])
            self.delivery_actor = None
            self.delivery_order = None
            self.delivery_project = None
        elif (not self.perf.active and self.delivery_actor is not None
              and self.delivery_actor.state == "listening"):
            self.delivery_actor.state = "waiting"
            self.delivery_project = None

        if not self.perf.active:
            for comp in self.pickups.update(dt, g.cat):
                self._collected(comp)
        self._region_name = self._region_at(g.cat.x, g.cat.z)
        self._near = self._nearest_pickup()
        self._near_id = self._near.get("id") if self._near else None

        cat = g.cat
        in_water = bool(getattr(cat, "in_water", False))
        if in_water and not self._was_in_water:
            sfx.splash()
            sfx.start_water()
        elif not in_water and self._was_in_water:
            sfx.stop_water()
        elif in_water:
            sfx.start_water()
        self._was_in_water = in_water
        for fx in self._fx:
            fx.update(dt)
        self._fx = [fx for fx in self._fx if not fx.done]

    def _capture_dialogue_photo(self, surf, entity):
        """Take a real on-screen face photo of a speaking world entity.

        The portrait is a literal crop from the already-rendered meadow, but it
        is framed around the actor's head and upper chest instead of the whole
        body.  This keeps the icon looking like an actual in-game snapshot while
        staying readable inside the dialogue box.
        """
        if entity is None or self.game is None:
            return None
        pr = project(float(entity.x), float(entity.z), self.game.cam)
        if pr is None:
            return None
        wx, wy = config.canvas_to_window(pr[0], pr[1])
        S = lambda value: ui.scaled(surf.get_height(), value)
        draw_scale = float(getattr(getattr(entity, "spec", None), "draw_scale", 1.0))
        side = int(max(72, S(92) + S(14) * min(2.4, draw_scale)))
        facing = 1 if getattr(entity, "facing", 1) >= 0 else -1
        # Keep a little meadow around the head so the result still reads as a
        # screenshot from the world, not a redrawn icon or an over-zoomed crop.
        cx = int(round(wx + facing * side * 0.06))
        cy = int(round(wy - side * (0.52 + 0.04 * min(2.0, draw_scale))))
        frame = pygame.Rect(0, 0, side, side)
        frame.center = (cx, cy)

        photo = pygame.Surface((side, side), pygame.SRCALPHA)
        clipped = frame.clip(surf.get_rect())
        if clipped.w <= 0 or clipped.h <= 0:
            return None
        photo.blit(surf, (clipped.x - frame.x, clipped.y - frame.y), clipped)
        return photo

    # ------------------------------------------------------------------ draw
    def _delivery_drawable(self, g):
        if self.field_delivery is None:
            return None
        x = float(self.field_delivery.get("target_x", 0.0))
        z = float(self.field_delivery.get("target_z", 0.0))
        pr = project(x, z, g.cam)
        if pr is None:
            return None
        sx, sy, sc = pr
        t = g.time
        kind = self.field_delivery.get("kind")
        if kind == "sprout":
            comp = catalog.get(self.field_delivery.get("item_id"))
            if comp is None:
                return None
            return (sy + 0.5, 40,
                    lambda surf, a=(sx, sy, sc, comp):
                    draw_plant_preview(surf, a[0], a[1], a[2], a[3], True))
        return (sy + 0.5, 40,
                lambda surf, a=(sx, sy, sc, t):
                draw_gramophone(surf, a[0], a[1], a[2], 0.0, a[3], False))

    def draw(self, surf):
        g = self.game
        extra = self.pickups.world_drawables(g.cam, g.time, g.cat)
        extra.extend(self.sprouts.world_drawables(
            g.cam, g.time, planning=self.holding is not None))
        extra.extend(self.garden.world_drawables(
            g.cam, g.time, 0, chapters_done=0, blooming=False))
        preview = self.intro.preview if self.intro.placing else None
        extra.extend(self.shop.world_drawables(g, preview=preview))
        if self.decorations is not None:
            extra.extend(self.decorations.world_drawables(g))
            extra.extend(self.decorations.upgrade_world_drawables(g, self.shop))
        if self.helpers is not None:
            extra.extend(self.helpers.world_drawables(g))
        if self.merchant is not None:
            extra.extend(self.merchant.world_drawables(g))
        extra.extend(self.clients.world_drawables(g))
        delivery = self._delivery_drawable(g)
        if delivery is not None:
            extra.append(delivery)

        plant_preview = self._plant_preview_info()
        if plant_preview is not None and not self.intro.placing:
            hx, hy, hs, comp, ok = plant_preview
            extra.append((hy + 0.5, 40,
                          lambda canvas, a=(hx, hy, hs, comp, ok):
                          draw_plant_preview(canvas, a[0], a[1], a[2], a[3], a[4])))

        g.set_daylight(self.clock.minutes, self.clock.day)
        g.paint_world(extra_drawables=extra)
        lights = self._music_light_sources()
        if self.decorations is not None:
            lights.extend(self.decorations.light_sources(g))
        if self.field_delivery is not None:
            pr = project(float(self.field_delivery.get("target_x", 0.0)),
                         float(self.field_delivery.get("target_z", 0.0)), g.cam)
            if pr is not None:
                lights.append((pr[0], pr[1] - 6, 52, (255, 184, 86), 1.35))
        g.draw_music_lights(lights)
        g.apply_vignette()
        g.upscale_to_window(surf)
        # Capture the speaker before bubbles, HUD elements, and the dialogue
        # veil are painted.  This is a literal crop of the current game frame.
        self.dialogue.capture_world_portrait(surf, self._capture_dialogue_photo)
        for fx in self._fx:
            fx.draw(surf)
        self.perf.draw_fx(surf)
        self.clients.draw_bubbles(surf, g)
        if self.merchant is not None:
            self.merchant.draw_bubble(surf, g)

        if not self.paused:
            if not self.intro.cinematic:
                self._draw_hud(surf)
            self.card.draw(surf)
            if self.picker is not None:
                self._draw_picker(surf)
            if self.tray is not None:
                self._draw_tray(surf)
            if self.market is not None and self.market.active:
                self.market.draw(surf)
            self._draw_intro_overlay(surf)
            self.story.draw(surf)
            self.dialogue.draw(surf)
            self._draw_sleep_confirm(surf)
        else:
            self._draw_pause(surf)

    def _draw_sleep_confirm(self, surf):
        if not self._sleep_confirm:
            self._sleep_confirm_rects = {}
            return
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((24, 23, 25, 84))
        surf.blit(veil, (0, 0))
        panel = pygame.Rect(0, 0, min(w - S(46), S(420)), S(150))
        panel.center = (w // 2, h // 2)
        ui.draw_panel(surf, panel, fill=ui.PAPER, edge=ui.PAPER_EDGE, radius=S(12))
        ui.pixel_text(surf, "SLEEP UNTIL MORNING?", S(18), panel.centerx, panel.y + S(16),
                      color=ui.INK, center=True)
        ui.pixel_text(surf, "It is after 18:00.", S(13), panel.centerx, panel.y + S(52),
                      color=ui.INK_SOFT, center=True)
        ui.pixel_text(surf, "Bal will sleep until 08:30 and begin a new day.", S(13),
                      panel.centerx, panel.y + S(74), color=ui.INK_SOFT, center=True)
        gap = S(12)
        bw = S(124)
        bh = S(38)
        yes = pygame.Rect(0, 0, bw, bh)
        no = pygame.Rect(0, 0, bw, bh)
        yes.right = panel.centerx - gap // 2
        no.left = panel.centerx + gap // 2
        yes.bottom = no.bottom = panel.bottom - S(16)
        self._sleep_confirm_rects = {"yes": yes, "no": no}
        for rect, label, active in ((yes, "YES, SLEEP", True), (no, "NO, STAY", False)):
            ui.draw_panel(surf, rect, fill=(ui.GRASS if active else ui.PAPER_DK),
                          edge=(ui.GRASS_DK if active else ui.PAPER_EDGE),
                          radius=S(8), shadow=False)
            ui.pixel_text_fit_box(surf, label, S(13), rect.inflate(-S(8), -S(6)),
                                  color=(ui.CREAM if active else ui.INK), min_size=S(9), center=True)

    def _draw_intro_overlay(self, surf):
        title, hint = self.intro.overlay_text()
        if not title:
            return
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        if self.intro.cinematic:
            # Keep the arrival cinematic inside the painted world.  The old
            # full-width dark bars read as a black rectangle and hid the sky.
            tw, _ = ui.pixel_measure(title, S(17))
            title_box = pygame.Rect(0, 0, min(w - S(40), tw + S(42)), S(42))
            title_box.midtop = (w // 2, S(14))
            ui.draw_panel(surf, title_box, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                          radius=S(8), shadow=False)
            ui.pixel_text_center_box(surf, title, S(17), title_box, color=ui.INK)
            if hint:
                hw, _ = ui.pixel_measure(hint, S(11))
                hint_box = pygame.Rect(0, 0, min(w - S(30), hw + S(28)), S(30))
                hint_box.bottomright = (w - S(14), h - S(14))
                ui.draw_panel(surf, hint_box, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                              radius=S(7), shadow=False)
                ui.pixel_text_center_box(surf, hint, S(11), hint_box, color=ui.INK_SOFT)
        elif self.intro.placing:
            tw, _ = ui.pixel_measure(title, S(15))
            box = pygame.Rect(0, 0, min(w - S(36), tw + S(42)), S(66))
            box.midtop = (w // 2, S(16))
            ui.draw_panel(surf, box, fill=ui.CREAM,
                          edge=(ui.GRASS if self.intro.preview and self.intro.preview[2]
                                else (198, 110, 104)), radius=S(9), shadow=False)
            ui.pixel_text(surf, title, S(15), box.centerx, box.y + S(10),
                          color=ui.INK, center=True)
            ui.pixel_text(surf, hint, S(11), box.centerx, box.y + S(37),
                          color=ui.INK_SOFT, center=True)

    def _context_prompt(self):
        if self.decorations is not None and self.decorations.placing is not None:
            if self.decorations.preview and self.decorations.preview[2]:
                return "E  Place decoration   R  Rotate   Q  Cancel", ui.GRASS
            return "Move to a clear place near the shop", (198, 110, 104)
        if self.merchant is not None and self.merchant.near(self.game.cat):
            return "E  Browse Poko's travelling cart", (226, 173, 94)
        helper_kind = self.helpers.nearest(self.game.cat) if self.helpers is not None else None
        if helper_kind is not None:
            return "E  Talk to %s" % HELPER_INFO[helper_kind]["name"], ui.GRASS
        if self.intro.placing:
            if self.intro.preview and self.intro.preview[2]:
                return "E  Build Bal's island studio here", ui.GRASS
            return self.intro.preview_reason or "Find a clearer patch", (198, 110, 104)
        if self.field_delivery is not None and self._near_delivery_target():
            verb = "Plant" if self.field_delivery.get("kind") == "sprout" else "Place gramophone"
            return "E  %s for %s" % (verb, self.field_delivery.get("name", "the client")), (226, 173, 94)
        if self.clients:
            text = self.clients.prompt(self.game.cat)
            if text:
                return text, (226, 173, 94)
        order = self._pending_delivery_order()
        if order is not None and self._near_counter():
            return "E  Prepare %s's field delivery" % order.get("name", "client"), (226, 173, 94)
        if self.decorations is not None:
            rec = self.decorations.nearest(self.game.cat.x, self.game.cat.z)
            if rec is not None:
                item = decoration_definition(rec.get("id"))
                name = item.get("name", "decoration") if item else "decoration"
                return "Backspace  Pick up %s" % name, ui.GRASS
        return super()._context_prompt()

    def _draw_hud(self, surf):
        super()._draw_hud(surf)
        if self.story_state is None:
            return
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        status = self.clients.status(self.clock)
        labels = [
            ("DAY %d  %s" % (self.clock.day, self.clock.format_time()),
             ui.GRASS if self.clock.shop_open else ui.PLUM),
            ("COINS %d" % self.story_state.coins, (226, 173, 94)),
            ("REP %.1f" % self.story_state.reputation, (208, 148, 172)),
            ("AT SHOP %d  -  AWAY %d" % (status["at_shop"], status["away"]), ui.GRASS),
        ]
        x = S(16)
        y = S(58)
        for text, edge in labels:
            tw, _ = ui.pixel_measure(text, S(12))
            r = pygame.Rect(x, y, tw + S(20), S(28))
            ui.draw_panel(surf, r, fill=ui.CREAM, edge=edge,
                          radius=S(7), shadow=False)
            ui.pixel_text_center_box(surf, text, S(12), r, color=ui.INK)
            x += r.w + S(7)

        ribbon = None
        if self.field_delivery is not None:
            ribbon = "FIELD DELIVERY  -  %s  -  FOLLOW THE GOLD MARKER" % self.field_delivery.get("destination_label", "marked place").upper()
        elif status.get("urgent"):
            ribbon = status.get("due_text", "DEADLINE APPROACHING").upper()
        if ribbon:
            rw, _ = ui.pixel_measure(ribbon, S(13))
            rr = pygame.Rect(0, S(96), min(w - S(40), rw + S(30)), S(34))
            rr.centerx = w // 2
            ui.draw_panel(surf, rr, fill=ui.CREAM, edge=(226, 146, 92),
                          radius=S(8), shadow=False)
            ui.pixel_text_fit_box(surf, ribbon, S(13), rr.inflate(-S(12), -S(5)),
                                  color=ui.INK, min_size=S(10), center=True)
        self._draw_delivery_direction(surf)

    def _draw_delivery_direction(self, surf):
        """Keep a gold direction marker visible until the delivery is done."""
        if self.field_delivery is None:
            return
        tx = float(self.field_delivery.get("target_x", 0.0))
        tz = float(self.field_delivery.get("target_z", 0.0))
        dx = tx - self.game.cat.x
        dz = tz - self.game.cat.z
        distance = max(1.0, math.hypot(dx, dz))
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        gold = (226, 173, 94)
        dark = (151, 103, 54)

        # A pulsing arrow stays directly above the marker while it is visible.
        pr = project(tx, tz, self.game.cam)
        if pr is not None:
            px, py = config.canvas_to_window(pr[0], pr[1])
            if -S(40) <= px <= w + S(40) and -S(40) <= py <= h + S(40):
                pulse = 1.0 + 0.12 * math.sin(self.game.time * 5.0)
                ay = int(py - S(52) * pulse)
                pygame.draw.polygon(surf, gold, [
                    (int(px), ay + S(18)),
                    (int(px - S(12)), ay),
                    (int(px + S(12)), ay),
                ])
                pygame.draw.polygon(surf, dark, [
                    (int(px), ay + S(18)),
                    (int(px - S(12)), ay),
                    (int(px + S(12)), ay),
                ], max(1, S(2)))

        # A fixed compass chip is always present, even when the target itself
        # is on screen. This makes the objective impossible to lose.
        chip = pygame.Rect(w - S(196), h - S(86), S(176), S(58))
        ui.draw_panel(surf, chip, fill=ui.CREAM, edge=gold,
                      radius=S(10), shadow=True)
        angle = math.atan2(-dz, dx)
        cx, cy = chip.x + S(28), chip.centery
        tip = (cx + math.cos(angle) * S(15), cy + math.sin(angle) * S(15))
        left = (cx + math.cos(angle + 2.45) * S(10),
                cy + math.sin(angle + 2.45) * S(10))
        right = (cx + math.cos(angle - 2.45) * S(10),
                 cy + math.sin(angle - 2.45) * S(10))
        pygame.draw.circle(surf, (255, 247, 224), (cx, cy), S(21))
        pygame.draw.circle(surf, gold, (cx, cy), S(21), max(1, S(2)))
        pygame.draw.polygon(surf, dark, [tip, left, right])
        label = self.field_delivery.get("destination_label", "Delivery")
        ui.pixel_text_fit_box(surf, str(label).upper(), S(11),
                              pygame.Rect(chip.x + S(56), chip.y + S(8),
                                          chip.w - S(66), S(18)),
                              color=ui.INK, min_size=S(8), center=False)
        ui.pixel_text(surf, "%d steps away" % int(distance + 0.5), S(10),
                      chip.x + S(56), chip.y + S(33), color=ui.INK_SOFT)

    def _picker_copy(self):
        if self.picker_for != "client":
            return super()._picker_copy()
        request = (self.delivery_order or {}).get("request") or {}
        if request.get("service") == "gramophone":
            return "CHOOSE A SONG TO DELIVER", "Bal will carry this song to the gold marker."
        return "CHOOSE A SONG", "Bal will play it for the client now."

    def _draw_picker(self, surf):
        super()._draw_picker(surf)
