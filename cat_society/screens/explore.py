"""Explore mode: drive the cozy world, scatter musical components, collect them.

This wraps the existing :class:`cat_society.game.Game` world engine and layers on
the pickups, the discovery card and a small cozy HUD. It
deliberately drops the old debug keys (spawn animal, place signpost, moods) so
normal play stays clean.
"""

import math
import time

import pygame

from .. import config, ui
from ..game import Game
from ..projection import project
from ..components import catalog
from ..components import rarity as _rarity
from ..ui.icons import draw_icon
from ..world.music_pickups import PickupManager, GRAB_RADIUS
from ..world.sprouts import SproutManager, plantable, RADII
from ..world.garden import GardenFixtures
from ..systems.performance import Performance
from ..render.sprouts import draw_plant_preview
from ..audio import sfx
from .card import CardManager
from .soundbook import SoundbookOverlay
from .storycard import StoryCards

class ExploreScreen:
    def __init__(self, app):
        self.app = app
        self.game = None
        self.pickups = None
        self.sprouts = None            # SproutManager, built with the world
        self.garden = None             # stump / windmill / gramophones
        self.works = None            # task/commission layer intentionally disabled
        self.perf = Performance(app)   # Bal's in-world performances
        self.story = StoryCards()      # onboarding / commission cards
        self.card = CardManager()
        self.soundbook = SoundbookOverlay(app)
        self.picker = None             # song picker overlay state, or None
        self.picker_for = "perform"    # or "gramophone"
        self.tray = None               # seed tray overlay state, or None
        self.holding = None            # comp dict currently being planted
        self._plantables = []          # tray order, for Tab-cycling the seed
        self._toast = None
        self._toast_t = 0.0
        self._region_name = ""
        self._near = None
        self._near_id = None           # id of the nearest pickup
        self._was_in_water = False     # for water enter/leave sounds
        self._fx = []                  # active collect bursts
        self.paused = False
        self.pause_page = "main"       # "main" | "controls" | "journal"
        self._pause_buttons = []
        self._pause_started_at = None
        self._pause_index = 0
        self.controls_scroll = 0
        self._controls_max_scroll = 0

    def ensure_game(self):
        """Build the world + pickups once, on demand.  Safe to call from the
        menu (to borrow the world for its background) or on entering explore."""
        if self.game is None:
            self.game = Game(window=self.app.window)
            self.pickups = PickupManager(self.game.world, self.game.water,
                                         self.app.collection)
            self.sprouts = SproutManager(self.app.world_state,
                                         self.app.engine)
            self.garden = GardenFixtures(self.game.world, self.game.water,
                                         self.app.world_state,
                                         self.app.engine, None)
            # the stump, windmill and gramophones stand solid, like wells
            self.game.landmark_solids = self.garden.solids_near
        return self.game

    def rebuild_world(self):
        """Forget the built world so the next visit regrows it fresh --
        used by Reset Progress, which also rolls a brand-new seed."""
        try:
            self.perf.stop(quiet=True)
        except Exception:
            pass
        try:
            self.app.engine.gramo_stop()
        except Exception:
            pass
        self.game = None
        self.pickups = None
        self.sprouts = None
        self.garden = None
        self.works = None
        self.picker = None
        self.tray = None
        self.holding = None
        self._set_paused(False)

    def on_enter(self):
        self.ensure_game()
        self._was_in_water = False
        pygame.mouse.set_visible(self.picker is not None or self.tray is not None)
        self._set_paused(False)
        # A compact two-page introduction to the sandbox mechanisms.
        ws = self.app.world_state
        if not ws.flag("intro_seen"):
            ws.set_flag("intro_seen")
            self.story.queue(
                "Collect and plant sound.",
                ["Find sounds in the world and collect them with E.",
                 "Open the seed tray with F, then plant musical sprouts.",
                 "Cross their soil rings to let the garden play."],
                icon="note", color=ui.GRASS, footer="press any key")
            self.story.queue(
                "Make the garden your instrument.",
                ["Press P to perform one of your saved songs in the world.",
                 "Press M whenever you want to open the Music Maker.",
                 "Press Esc for the Journal, controls, and pause options."],
                icon="note", color=ui.GRASS, footer="press any key")

    # -- pause --------------------------------------------------------------
    def _set_paused(self, value):
        value = bool(value)
        if self.paused == value:
            return
        self.paused = value
        if value:
            self.pause_page = "main"
            self._pause_index = 0
            self._pause_started_at = time.time()
            pygame.mouse.set_visible(True)
            try:
                pygame.mixer.pause()
            except pygame.error:
                pass
        else:
            paused_for = (max(0.0, time.time() - self._pause_started_at)
                          if self._pause_started_at is not None else 0.0)
            self._pause_started_at = None
            if paused_for:
                if self.sprouts is not None:
                    self.sprouts.shift_clock(paused_for)
                self.perf.shift_clock(paused_for)
                try:
                    self.app.engine.shift_music_clock(paused_for)
                except AttributeError:
                    pass
            try:
                pygame.mixer.unpause()
            except pygame.error:
                pass
            pygame.mouse.set_visible(self.picker is not None or self.tray is not None)

    def _pause_main_items(self):
        return [
            ("Resume", "resume", True),
            ("Journal", "journal", False),
            ("How to Play", "controls", False),
            ("Main Menu", "menu", False),
            ("Quit Game", "quit", False),
        ]

    def _pause_action(self, action):
        if action == "resume":
            self._set_paused(False)
        elif action == "journal":
            self.soundbook.reset()
            self.pause_page = "journal"
        elif action == "controls":
            self.pause_page = "controls"
            self.controls_scroll = 0
        elif action == "back":
            self.pause_page = "main"
        elif action == "menu":
            self._set_paused(False)
            self.app.goto("menu")
        elif action == "quit":
            self._set_paused(False)
            self.app.quit()

    def _pause_event(self, e):
        if self.pause_page == "journal":
            self.soundbook.handle_event(e, lambda: self._pause_action("back"))
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self._pause_action("back" if self.pause_page == "controls" else "resume")
                return
            if self.pause_page == "main":
                items = self._pause_main_items()
                if e.key in (pygame.K_UP, pygame.K_w):
                    self._pause_index = (self._pause_index - 1) % len(items)
                    return
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    self._pause_index = (self._pause_index + 1) % len(items)
                    return
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._pause_action(items[self._pause_index][1])
                    return
            elif self.pause_page == "controls":
                if e.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self._pause_action("back")
                    return
                if e.key in (pygame.K_DOWN, pygame.K_s):
                    self.controls_scroll = min(self._controls_max_scroll,
                                               self.controls_scroll + ui.scaled(self.app.window.get_height(), 36))
                    return
                if e.key in (pygame.K_UP, pygame.K_w):
                    self.controls_scroll = max(0, self.controls_scroll - ui.scaled(self.app.window.get_height(), 36))
                    return
                if e.key == pygame.K_PAGEDOWN:
                    self.controls_scroll = min(self._controls_max_scroll,
                                               self.controls_scroll + ui.scaled(self.app.window.get_height(), 180))
                    return
                if e.key == pygame.K_PAGEUP:
                    self.controls_scroll = max(0, self.controls_scroll - ui.scaled(self.app.window.get_height(), 180))
                    return
            return
        if e.type == pygame.MOUSEWHEEL and self.pause_page == "controls":
            step = ui.scaled(self.app.window.get_height(), 42)
            self.controls_scroll = max(0, min(self._controls_max_scroll,
                                               self.controls_scroll - e.y * step))
            return
        if e.type == pygame.MOUSEMOTION and self.pause_page == "main":
            for i, (rect, _action) in enumerate(self._pause_buttons):
                if rect.collidepoint(e.pos):
                    self._pause_index = i
                    break
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, (rect, action) in enumerate(self._pause_buttons):
                if rect.collidepoint(e.pos):
                    self._pause_index = i
                    self._pause_action(action)
                    return

    # -- events -------------------------------------------------------------
    def handle_event(self, e):
        if self.paused:
            self._pause_event(e)
            return

        # Esc is now a pause key.  It only closes a true modal overlay first.
        if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
            if self.picker is not None:
                self._close_picker()
            elif self.tray is not None:
                self._close_tray()
            else:
                self._set_paused(True)
            return

        if self.story.handle_event(e):
            return
        if self.picker is not None:
            self._picker_event(e)
            return
        if self.tray is not None:
            self._tray_event(e)
            return

        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_p:
                if self.perf.active:
                    self.perf.stop()
                else:
                    self._open_picker()
                return
            if self.perf.active:
                return
            if e.key == pygame.K_q and self.holding is not None:
                self.holding = None
                self._toast = "The seed returns to your satchel."
                self._toast_t = 1.8
            elif e.key == pygame.K_TAB and self.holding is not None and self._plantables:
                try:
                    i = self._plantables.index(self.holding)
                except ValueError:
                    i = -1
                self.holding = self._plantables[(i + 1) % len(self._plantables)]
                self.app.engine.preview_component(self.holding)
            elif e.key == pygame.K_f:
                if self.holding is not None:
                    self._plant_held()
                else:
                    self._open_tray()
            elif e.key == pygame.K_m:
                self.app.goto("maker")
            elif e.key == pygame.K_SPACE:
                self.game.cat.jump()
            elif e.key == pygame.K_z and self.game.cat.on_ground:
                self.game.cat.sleeping = not self.game.cat.sleeping
            elif e.key == pygame.K_e:
                self._use_key()

    # -- E does the nearest sensible thing -----------------------------------
    def _use_key(self):
        g = self.game
        cx, cz = g.cat.x, g.cat.z
        # 1) a grown seed bed: harvest
        if (self.garden.mill_grown() and not self.garden.mill_claimed()
                and math.hypot(self.garden.bed[0] - cx,
                               self.garden.bed[1] - cz) < 90.0):
            for comp in self.garden.harvest(self.app.collection):
                self.card.queue(comp, self.app.collection.num_found(), None)
                self._spawn_collect_fx(comp)
            self._toast = "The seed bed's harvest, from your own music."
            self._toast_t = 3.4
            return
        # 2) uproot the sprout underfoot
        s = self.sprouts.nearest(cx, cz, max_dist=55.0)
        if s is not None:
            name = (s.comp or {}).get("name", "a sprout")
            self.sprouts.uproot(s)
            self._toast = "Uprooted  %s  (still in your satchel)" % name
            self._toast_t = 2.2
            return
        # 3) pick up a planted gramophone
        gr = self.garden.nearest_gramophone(cx, cz, max_dist=55.0)
        if gr is not None:
            self.garden.remove_gramophone(gr)
            self._toast = "Picked the gramophone back up."
            self._toast_t = 2.2
            return
        # 4) otherwise: collect
        comp = self.pickups.grab_nearest(g.cat)
        if comp:
            self._collected(comp)

    # -- planting -------------------------------------------------------------
    def _open_tray(self):
        owned = [c for c in catalog.ALL
                 if self.app.collection.owns(c["id"]) and plantable(c)]
        owned += [c for c in self.app.collection._found_proc() if plantable(c)]
        if not owned:
            self._toast = "There is nothing plantable in the satchel yet. Go collect a sound."
            self._toast_t = 3.0
            return
        order = {"drum": 0, "rhythm": 1, "note": 2, "chord": 3, "bass": 4,
                 "loop": 5, "ambience": 6}
        owned.sort(key=lambda c: (order.get(c["type"], 9), c["name"]))
        # saved songs can be planted too, as gramophone records
        records = self.app.refresh_projects()
        self._plantables = owned
        self.tray = {"idx": 0, "rects": [], "items": owned,
                     "records": records}
        pygame.mouse.set_visible(True)

    def _close_tray(self):
        self.tray = None
        pygame.mouse.set_visible(False)

    def _tray_pick(self, item):
        self._close_tray()
        if item is None:
            return
        if isinstance(item, dict):
            self.holding = item
            self.app.engine.preview_component(item)
            self._toast = "Holding %s. Press F to plant it or Q to put it away." % item["name"]
            self._toast_t = 3.0
        else:                                   # a saved song -> gramophone
            g = self.game
            self.garden.plant_gramophone(item, g.cat.x, g.cat.z + 26.0)
            self._toast = "Planted a gramophone playing  \"%s\"" % item.name
            self._toast_t = 3.0

    def _tray_event(self, e):
        items = self.tray["items"] + self.tray["records"]
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_f):
                self._close_tray()
            elif e.key in (pygame.K_UP, pygame.K_w):
                self.tray["idx"] = (self.tray["idx"] - 1) % len(items)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self.tray["idx"] = (self.tray["idx"] + 1) % len(items)
            elif e.key in (pygame.K_RETURN, pygame.K_e):
                self._tray_pick(items[self.tray["idx"]])
        elif e.type == pygame.MOUSEWHEEL:
            self.tray["idx"] = max(0, min(len(items) - 1,
                                          self.tray["idx"] - e.y))
        elif e.type == pygame.MOUSEMOTION:
            for i, (rect, _) in enumerate(self.tray["rects"]):
                if rect.collidepoint(e.pos):
                    self.tray["idx"] = i
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, item in self.tray["rects"]:
                if rect.collidepoint(e.pos):
                    self._tray_pick(item)
                    return
            self._close_tray()

    def _plant_held(self):
        g = self.game
        x, z = g.cat.x, g.cat.z + 22.0        # just ahead of the paws
        if g.water.depth_at(x, z)[0] > 0.0:
            self._toast = "This place is too wet. Sprouts need dry soil."
            self._toast_t = 2.4
            return
        s, why = self.sprouts.plant(self.holding["id"], x, z)
        if s is None:
            self._toast = why
            self._toast_t = 2.4
            return
        self.app.world_state.set_flag("taught_plant")
        self.app.engine.trigger_sprout(self.holding)   # it says hello
        s.pulse = 0.0

    # -- the song picker: which song shall Bal play? --------------------------
    def _open_picker(self, purpose="perform"):
        songs = self.app.refresh_projects()
        if not songs:
            self._toast = "Bal hasn't written a song yet.  Press M to compose one."
            self._toast_t = 3.2
            return
        self.picker = {"idx": 0, "rects": []}
        self.picker_for = purpose
        pygame.mouse.set_visible(True)

    def _close_picker(self):
        self.picker = None
        pygame.mouse.set_visible(False)

    def _perform(self, proj):
        self._close_picker()
        if proj is None:
            return
        self.perf.start(proj, self.game.cat)
        self._toast = "Bal plays  \"%s\"  for the garden..." % proj.name
        self._toast_t = 2.6

    def _picker_event(self, e):
        songs = self.app.project_list
        if not songs:
            self._close_picker()
            return
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_p):
                self._close_picker()
            elif e.key in (pygame.K_UP, pygame.K_w):
                self.picker["idx"] = (self.picker["idx"] - 1) % len(songs)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self.picker["idx"] = (self.picker["idx"] + 1) % len(songs)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                self._perform(songs[self.picker["idx"]])
        elif e.type == pygame.MOUSEMOTION:
            for i, (rect, _) in enumerate(self.picker["rects"]):
                if rect.collidepoint(e.pos):
                    self.picker["idx"] = i
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for rect, proj in self.picker["rects"]:
                if rect.collidepoint(e.pos):
                    self._perform(proj)
                    return
            self._close_picker()

    def _collected(self, comp):
        # play only the component's own exact sound, nothing extra over it
        self.app.engine.preview_component(comp)
        col = self.app.collection
        self.card.queue(comp, col.num_found(), None)
        self._toast = "Found  %s" % comp["name"]
        self._toast_t = 2.2
        self._spawn_collect_fx(comp)

    def _spawn_collect_fx(self, comp):
        """A sparkle burst at the cat that streams a glowing icon up to the
        collection counter -- the 'added to your music' moment."""
        g = self.game
        pr = project(g.cat.x, g.cat.z, g.cam)
        if pr is None:
            cxp, cyp = config.W * 0.5, config.H * 0.5
        else:
            cxp, cyp = pr[0], pr[1]
        px, py = config.canvas_to_window(cxp, cyp)
        w, h = self.app.window.get_size()
        # Fly toward the discovery card icon rather than the removed HUD count.
        target = (w - ui.scaled(h, 90), ui.scaled(h, 90))
        color = tuple(comp.get("color", ui.GRASS))
        self._fx.append(CollectFx(px, py, target, color,
                                  comp.get("icon", "note"),
                                  comp.get("rarity", "common")))

    # -- update -------------------------------------------------------------
    def update(self, dt):
        if self.paused:
            return
        self.card.update(dt)
        self.story.update(dt)
        if self._toast_t > 0:
            self._toast_t -= dt
        if self.picker is not None or self.tray is not None:
            return
        if self.story.blocking:
            return

        g = self.game
        g.input_locked = self.perf.active
        g.song_ctx = self.perf.song_ctx()
        g.update(dt)

        self.perf.update(dt, g, self.app.window.get_size())
        self.sprouts.update(dt, g, muted=self.perf.active)
        self.garden.update(dt, self.perf, g.cat.x, g.cat.z,
                           beat_phase=self.sprouts.beat_phase())
        if self.garden.just_powered:
            self.garden.just_powered = False
            self._toast = "The windmill hears the beat; the seed bed is drinking."
            self._toast_t = 3.0

        # Performances still affect animals, machines and gramophones, but no
        # commission/task layer consumes their result in free-play mode.
        self.perf.pop_result()

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

    # -- E does the nearest sensible thing -----------------------------------
    def _region_at(self, x, z):
        best = None
        best_d = 1e18
        for key, r in catalog.REGIONS.items():
            d = math.hypot(x - r["cx"], z - r["cz"])
            if d < r["radius"] * 1.15 and d < best_d:
                best_d = d
                best = r["name"]
        return best or "The Sound Garden"

    def _nearest_pickup(self):
        return self.pickups.nearest_comp(self.game.cat)

    def _controls_sections(self):
        story_mode = getattr(self.app, "profile_kind", None) == "story"
        last_title = "Shop and menus" if story_mode else "Menus and options"
        if story_mode:
            sleep_line = "After 18:00, press Z to sleep. The game will ask you first."
            sections = [
                ("Moving around", [
                    "Use WASD or the arrow keys to walk around the garden.",
                    "Hold Shift to run.",
                    "Press Space to jump.",
                    sleep_line,
                ]),
                ("Sounds and planting", [
                    "Press E near a floating sound to collect it.",
                    "Press F to open the seed tray.",
                    "Choose a sound and press F again to plant it.",
                    "While holding a sound, press Tab to switch or Q to put it away.",
                ]),
                ("Music", [
                    "Walk through a sprout ring to hear it play.",
                    "Press P to open your saved-song list and choose one to perform.",
                    "Press P again to stop the performance.",
                    "Press M at any time in Explore to open the Music Maker.",
                    "In the Maker, stop playback before editing the song.",
                ]),
                ("Commissions and journal", [
                    "Open the Journal from the pause menu.",
                    "Missions shows offers, active jobs, deadlines, and completed jobs.",
                    "A note written by Clover is only an offer until you accept it.",
                    "Team shows your hired helpers and lets you choose who works tomorrow.",
                ]),
                ("Merchant, helpers, and decorating", [
                    "Press E beside Poko to browse the travelling cart.",
                    "While placing a decoration: E places it, R rotates it, and Q cancels.",
                    "Press Backspace near a decoration to return it to storage.",
                    "Prepare a normal field delivery before asking Bramble to take it.",
                ]),
                (last_title, [
                    "Press E near an animal or the counter to talk or deliver.",
                    "The clock keeps moving in the Maker, so watch your deadlines.",
                    "Press Esc to pause the game and open the pause menu.",
                    "Use the mouse or arrow keys and Enter in menus. Press F11 for fullscreen.",
                ]),
            ]
            return sections

        sections = [
            ("Moving around", [
                "Use WASD or the arrow keys to walk around the garden.",
                "Hold Shift to run.",
                "Press Space to jump.",
                "Press Z on dry ground to sleep or wake up.",
            ]),
            ("Sounds and planting", [
                "Press E near a floating sound to collect it.",
                "Press F to open the seed tray.",
                "Choose a sound and press F again to plant it.",
                "While holding a sound, press Tab to switch or Q to put it away.",
            ]),
            ("Music", [
                "Walk through a sprout ring to hear it play.",
                "Press P to open your saved-song list and choose one to perform.",
                "Press P again to stop the performance.",
                "Press M at any time in Explore to open the Music Maker.",
            ]),
            (last_title, [
                "Press Esc to pause the game and open the pause menu.",
                "From the pause menu, choose Journal, How to Play, Main Menu, or Quit.",
                "Use the mouse or arrow keys and Enter in menus.",
                "Press F11 to switch between windowed and fullscreen mode.",
            ]),
        ]
        return sections

    def _plant_preview_info(self):
        if self.holding is None:
            return None
        g = self.game
        x, z = g.cat.x, g.cat.z + 22.0
        if g.water.depth_at(x, z)[0] > 0.0:
            return None
        pr = project(x, z, g.cam)
        if pr is None:
            return None
        ok, _ = self.sprouts.can_plant_here(x, z)
        return pr[0], pr[1], pr[2], self.holding, ok

    def _music_light_sources(self):
        """Visible world-space music lights, projected onto the low-res canvas."""
        if self.game is None or self.game.night_strength <= 0.02:
            return []
        out = []
        base_r = float(getattr(config, "MUSIC_LIGHT_RADIUS", 34))
        for sprout in getattr(self.sprouts, "sprouts", ()):
            comp = sprout.comp
            if comp is None:
                continue
            pr = project(sprout.x, sprout.z, self.game.cam)
            if pr is None:
                continue
            sx, sy, scale = pr
            if -base_r <= sx <= config.W + base_r and -base_r <= sy <= config.H + base_r:
                pulse = 0.70 + 0.30 * math.sin(self.game.time * 2.2 + sprout.sway)
                out.append((sx, sy - max(2, 10 * scale),
                            max(8, base_r * max(.35, scale)),
                            tuple(comp.get("color", ui.GRASS)), pulse))
        gr = float(getattr(config, "GRAMOPHONE_LIGHT_RADIUS", 46))
        for gramophone in getattr(self.garden, "gramophones", ()):
            pr = project(gramophone.x, gramophone.z, self.game.cam)
            if pr is None:
                continue
            sx, sy, scale = pr
            if -gr <= sx <= config.W + gr and -gr <= sy <= config.H + gr:
                pulse = 0.82 + 0.18 * math.sin(self.game.time * 1.5 + gramophone.x * .01)
                out.append((sx, sy - max(2, 8 * scale),
                            max(10, gr * max(.35, scale)),
                            (255, 190, 104), pulse))
        return out

    # -- draw ---------------------------------------------------------------
    def draw(self, surf):
        g = self.game
        # pickups, sprouts and fixtures are real world objects: hand them to
        # paint_world so they depth-sort against props, animals and the cat
        extra = self.pickups.world_drawables(g.cam, g.time, g.cat)
        extra.extend(self.sprouts.world_drawables(
            g.cam, g.time, planning=self.holding is not None))
        extra.extend(self.garden.world_drawables(
            g.cam, g.time, 0, chapters_done=0, blooming=False))
        preview = self._plant_preview_info()
        if preview is not None:
            hx, hy, hs, comp, ok = preview

            def d_preview(surf, _a=(hx, hy, hs), _c=comp, _ok=ok):
                draw_plant_preview(surf, _a[0], _a[1], _a[2], _c, _ok)
            extra.append((hy + 0.5, 40, d_preview))
        g.paint_world(extra_drawables=extra)
        g.draw_music_lights(self._music_light_sources())
        g.apply_vignette()
        g.upscale_to_window(surf)
        for fx in self._fx:
            fx.draw(surf)
        self.perf.draw_fx(surf)
        if not self.paused:
            self._draw_hud(surf)
            self.card.draw(surf)
            if self.picker is not None:
                self._draw_picker(surf)
            if self.tray is not None:
                self._draw_tray(surf)
            self.story.draw(surf)
        else:
            self._draw_pause(surf)

    def _context_prompt(self):
        if self.card.busy() or self.perf.active:
            return None, ui.GRASS
        if self._near is not None:
            return "E  Collect  %s" % self._near["name"], \
                ui.RARITY_COL.get(self._near.get("rarity"), ui.GRASS)

        g = self.game
        if (self.garden.mill_grown() and not self.garden.mill_claimed()
                and math.hypot(self.garden.bed[0] - g.cat.x,
                               self.garden.bed[1] - g.cat.z) < 90.0):
            return "E  Harvest the seed bed", (255, 214, 130)
        if self.holding is None:
            sprout = self.sprouts.nearest(g.cat.x, g.cat.z, max_dist=55.0)
            if sprout is not None and sprout.comp is not None:
                return "E  Uproot  %s" % sprout.comp["name"], ui.PAPER_EDGE
            gramophone = self.garden.nearest_gramophone(
                g.cat.x, g.cat.z, max_dist=55.0)
            if gramophone is not None:
                return "E  Pick up the gramophone", ui.PAPER_EDGE
        return None, ui.GRASS

    def _draw_hud(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)

        # One quiet location label and one tiny pause hint.  The collection
        # counter remains in persistent state and the main-menu Soundbook, but
        # no longer competes with the world view.
        region = self._region_name or "The Sound Garden"
        rs = S(16)
        rw, _ = ui.pixel_measure(region.upper(), rs)
        plate = pygame.Rect(S(16), S(16), rw + S(24), S(34))
        ui.draw_panel(surf, plate, fill=ui.CREAM, radius=S(7), shadow=False)
        ui.pixel_text_fit_box(surf, region.upper(), rs, plate.inflate(-S(10), -S(4)),
                              color=ui.INK, min_size=S(11))

        pause_text = "ESC  PAUSE"
        pw, _ = ui.pixel_measure(pause_text, S(13))
        pplate = pygame.Rect(0, S(17), pw + S(20), S(30))
        pplate.right = w - S(16)
        ui.draw_panel(surf, pplate, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                      radius=S(7), shadow=False)
        ui.pixel_text_center_box(surf, pause_text, S(13), pplate,
                                 color=ui.INK_SOFT)

        prompt, edge = self._context_prompt()
        if prompt:
            ps = S(18)
            pwidth, _ = ui.pixel_measure(prompt, ps)
            box = pygame.Rect(0, 0, pwidth + S(30), S(40))
            box.midbottom = (w // 2, h - S(22))
            ui.draw_panel(surf, box, fill=ui.CREAM, edge=edge,
                          radius=S(9), shadow=False)
            ui.pixel_text_fit_box(surf, prompt, ps, box.inflate(-S(12), -S(6)),
                                  color=ui.INK, min_size=S(12))

        # Only one top-centre mode ribbon is shown at a time.
        mode_text = None
        mode_edge = ui.GRASS
        if self.holding is not None:
            mode_text = "PLANTING %s   -   F PLANT   -   TAB NEXT   -   Q POCKET" \
                        % self.holding["name"].upper()
            mode_edge = tuple(self.holding.get("color", ui.GRASS))
        if mode_text:
            ms = S(15)
            mw, _ = ui.pixel_measure(mode_text, ms)
            chip = pygame.Rect(0, 0, min(w - S(40), mw + S(34)), S(36))
            chip.midtop = (w // 2, S(16))
            ui.draw_panel(surf, chip, fill=ui.CREAM, edge=mode_edge,
                          radius=S(8), shadow=False)
            ui.pixel_text_fit_box(surf, mode_text, ms, chip.inflate(-S(14), -S(6)),
                                  color=ui.INK, min_size=S(11))

        if self._toast_t > 0 and self._toast:
            alpha = min(1.0, self._toast_t / 0.45)
            ts = S(16)
            img = ui.pixel_render(self._toast, ts, ui.INK)
            box = pygame.Surface((img.get_width() + S(28),
                                  img.get_height() + S(14)), pygame.SRCALPHA)
            pygame.draw.rect(box, (*ui.CREAM, int(232 * alpha)), box.get_rect(),
                             border_radius=S(7))
            box.blit(img, (S(14), S(7)))
            box.set_alpha(int(255 * alpha))
            y = h - (S(82) if prompt else S(36))
            surf.blit(box, box.get_rect(midbottom=(w // 2, y)))

        if self.perf.active:
            name = "~  %s  ~" % self.perf.project.name.upper()
            ps = S(16)
            nw, _ = ui.pixel_measure(name, ps)
            bw = max(nw + S(60), S(300))
            box = pygame.Rect(0, 0, bw, S(58))
            box.midbottom = (w // 2, h - S(18))
            ui.draw_panel(surf, box, fill=ui.CREAM, radius=S(10))
            ui.pixel_text(surf, name, ps, box.centerx, box.y + S(8),
                          color=ui.INK, center=True)
            bar = pygame.Rect(box.x + S(18), box.y + S(36),
                              box.w - S(36), S(7))
            ui.draw_panel(surf, bar, fill=ui.PAPER_DK, radius=S(4), shadow=False)
            fill = bar.copy()
            fill.w = max(2, int(bar.w * self.perf.progress()))
            ui.draw_panel(surf, fill, fill=ui.GRASS, radius=S(4), shadow=False)
            ui.pixel_text(surf, "P  STOP", S(11), box.right - S(12),
                          box.y + S(9), color=ui.INK_SOFT, right=True)

    def _draw_pause_button(self, surf, rect, label, action, accent=False, selected=False):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        active = hover or selected
        fill = ui.CREAM if active else ui.PAPER_DK
        edge = ui.GRASS if accent else (ui.PLUM if active else ui.PAPER_EDGE)
        ui.draw_panel(surf, rect, fill=fill, edge=edge, radius=11,
                      shadow=active)
        ui.pixel_text_fit_box(surf, label.upper(),
                              ui.scaled(surf.get_height(), 17), rect.inflate(-12, -6),
                              color=ui.INK, min_size=ui.scaled(surf.get_height(), 12))
        self._pause_buttons.append((rect, action))

    def _draw_pause(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        self._pause_buttons = []

        if self.pause_page == "journal":
            self.soundbook.draw(surf)
            return

        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((28, 24, 22, 176))
        surf.blit(veil, (0, 0))

        if self.pause_page == "controls":
            panel = pygame.Rect(0, 0, min(w - S(28), S(980)),
                                min(h - S(26), S(860)))
            panel.center = (w // 2, h // 2)
            ui.draw_panel(surf, panel, fill=ui.PAPER, radius=18)
            ui.pixel_text(surf, "HOW TO PLAY", S(28), panel.centerx,
                          panel.y + S(22), color=ui.INK, center=True)
            ui.pixel_text(surf, "Mouse wheel or arrow keys scroll.", S(11), panel.centerx,
                          panel.y + S(56), color=ui.INK_SOFT, center=True, bold=False)

            sections = self._controls_sections()
            viewport = pygame.Rect(panel.x + S(28), panel.y + S(84),
                                   panel.w - S(56), panel.h - S(154))
            col_gap = S(20)
            col_w = (viewport.w - col_gap) // 2
            text_size = S(15)
            line_gap = S(2)
            paragraph_gap = S(7)
            card_pad = S(14)
            title_h = S(24)

            card_heights = []
            text_w = col_w - card_pad * 2 - S(14)
            for title, paragraphs in sections:
                body_h = 0
                for paragraph in paragraphs:
                    lines = ui.wrap_lines(paragraph, text_w, text_size, pixel=True, bold=False)
                    body_h += len(lines) * (ui.pixel_line_height(text_size, False) + line_gap)
                    body_h += paragraph_gap
                card_heights.append(card_pad + title_h + S(8) + body_h + card_pad)

            rows = []
            for index in range(0, len(sections), 2):
                rows.append(max(card_heights[index:index + 2]))
            row_gap = S(16)
            total_h = sum(rows) + max(0, len(rows) - 1) * row_gap
            self._controls_max_scroll = max(0, total_h - viewport.h)
            self.controls_scroll = max(0, min(self.controls_scroll, self._controls_max_scroll))

            old_clip = surf.get_clip()
            surf.set_clip(viewport)
            row_y = viewport.y - self.controls_scroll
            self._controls_card_metrics = []
            for row_index, row_h in enumerate(rows):
                for col in range(2):
                    index = row_index * 2 + col
                    if index >= len(sections):
                        continue
                    title, paragraphs = sections[index]
                    sx = viewport.x + col * (col_w + col_gap)
                    srect = pygame.Rect(sx, row_y, col_w, row_h)
                    self._controls_card_metrics.append((title, srect.copy(), card_heights[index]))
                    ui.draw_panel(surf, srect, fill=ui.CREAM, edge=ui.PAPER_EDGE,
                                  radius=S(11), shadow=False)
                    ui.pixel_text_fit_box(
                        surf, title.upper(), S(17),
                        pygame.Rect(srect.x + card_pad, srect.y + card_pad,
                                    srect.w - card_pad * 2, title_h),
                        color=ui.GRASS_DK, min_size=S(12), center=False)
                    y = srect.y + card_pad + title_h + S(8)
                    for paragraph in paragraphs:
                        bullet_x = srect.x + card_pad
                        text_rect = pygame.Rect(srect.x + card_pad + S(14), y,
                                                srect.w - card_pad * 2 - S(14),
                                                max(1, srect.bottom - y - card_pad))
                        ui.pixel_text(surf, "-", S(12), bullet_x, y,
                                      color=ui.GRASS_DK)
                        lines = ui.wrap_lines(paragraph, text_rect.w, text_size,
                                              pixel=True, bold=False)
                        for line in lines:
                            ui.pixel_text(surf, line, text_size, text_rect.x, y,
                                          color=ui.INK_SOFT, bold=False)
                            y += ui.pixel_line_height(text_size, False) + line_gap
                        y += paragraph_gap
                row_y += row_h + row_gap
            surf.set_clip(old_clip)

            if self._controls_max_scroll > 0:
                track = pygame.Rect(viewport.right + S(8), viewport.y, S(6), viewport.h)
                pygame.draw.rect(surf, ui.PAPER_DK, track, border_radius=S(3))
                thumb_h = max(S(28), int(track.h * viewport.h / float(total_h)))
                thumb_y = track.y + int((track.h - thumb_h) *
                                        self.controls_scroll / float(self._controls_max_scroll))
                pygame.draw.rect(surf, ui.GRASS,
                                 pygame.Rect(track.x, thumb_y, track.w, thumb_h),
                                 border_radius=S(3))

            back = pygame.Rect(0, 0, S(180), S(42))
            back.midbottom = (panel.centerx, panel.bottom - S(16))
            self._draw_pause_button(surf, back, "Back", "back", accent=True, selected=True)
            return

        panel = pygame.Rect(0, 0, min(w - S(48), S(500)),
                            min(h - S(48), S(650)))
        panel.center = (w // 2, h // 2)
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=18)
        ui.pixel_text(surf, "PAUSED", S(29), panel.centerx, panel.y + S(30),
                      color=ui.INK, center=True)
        ui.pixel_text(surf, (self._region_name or "The Sound Garden").upper(),
                      S(13), panel.centerx, panel.y + S(78),
                      color=ui.INK_SOFT, center=True)

        labels = self._pause_main_items()
        y = panel.y + S(126)
        for i, (label, action, accent) in enumerate(labels):
            rect = pygame.Rect(panel.x + S(58), y,
                               panel.w - S(116), S(54))
            self._draw_pause_button(surf, rect, label, action, accent,
                                    selected=(i == self._pause_index))
            y += S(68)
        ui.pixel_text(surf, "UP / DOWN  MOVE   -   ENTER  CHOOSE   -   ESC  RESUME",
                      S(12), panel.centerx, panel.bottom - S(30), color=ui.INK_SOFT, center=True)

    # -- the song picker overlay ---------------------------------------------
    def _picker_copy(self):
        return "PLAY A SONG", "Choose one of Bal's saved projects."

    def _draw_picker(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        songs = self.app.project_list
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((30, 26, 22, 150))
        surf.blit(veil, (0, 0))

        rows = min(len(songs), 7)
        row_h = S(52)
        header_h = S(106)
        panel = pygame.Rect(0, 0, min(int(w * 0.66), S(610)),
                            header_h + rows * row_h + S(16))
        panel.center = (w // 2, int(h * 0.48))
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=16)
        title, subtitle = self._picker_copy()
        ui.pixel_text_fit_box(surf, title, S(22),
                              pygame.Rect(panel.x + S(20), panel.y + S(14),
                                          panel.w - S(40), S(30)),
                              color=ui.INK, min_size=S(15), center=True)
        ui.pixel_text_fit_box(surf, subtitle, S(12),
                              pygame.Rect(panel.x + S(24), panel.y + S(48),
                                          panel.w - S(48), S(21)),
                              color=ui.INK_SOFT, min_size=S(9), center=True,
                              bold=False)
        ui.pixel_text(surf, "UP / DOWN AND ENTER     CLICK     ESC TO CLOSE",
                      S(10), panel.centerx, panel.y + S(76),
                      color=ui.INK_SOFT, center=True)

        self.picker["rects"] = []
        top = panel.y + header_h
        first = max(0, min(self.picker["idx"] - rows // 2, len(songs) - rows))
        for i in range(first, first + rows):
            proj = songs[i]
            r = pygame.Rect(panel.x + S(18), top + (i - first) * row_h,
                            panel.w - S(36), row_h - S(8))
            sel = i == self.picker["idx"]
            ui.draw_panel(surf, r, fill=(ui.CREAM if sel else ui.PAPER_DK),
                          edge=(ui.GRASS if sel else ui.PAPER_EDGE),
                          radius=10, shadow=False)
            draw_icon(surf, r.x + S(22), r.centery, S(12), ui.GRASS, "note", 0.0)
            nrect = pygame.Rect(r.x + S(44), r.y + S(6), r.w - S(172), S(20))
            ui.pixel_text_fit_box(surf, proj.name.upper(), S(16), nrect,
                                  color=ui.INK, min_size=S(10), center=False)
            info = "%d BPM     %d BARS" % (proj.tempo, proj.bars)
            irect = pygame.Rect(r.right - S(148), r.y + S(8), S(134), S(16))
            ui.pixel_text_fit_box(surf, info, S(11), irect,
                                  color=ui.INK_SOFT, min_size=S(8), bold=False,
                                  right=True, center=False)
            self.picker["rects"].append((r, proj))

    # -- collection journal -------------------------------------------------
    # -- the seed tray overlay ------------------------------------------------
    def _draw_tray(self, surf):
        w, h = surf.get_size()
        S = lambda v: ui.scaled(h, v)
        items = self.tray["items"] + self.tray["records"]
        veil = pygame.Surface((w, h), pygame.SRCALPHA)
        veil.fill((30, 26, 22, 150))
        surf.blit(veil, (0, 0))

        rows = min(len(items), 9)
        row_h = S(44)
        panel = pygame.Rect(0, 0, min(int(w * 0.6), S(560)),
                            S(118) + rows * row_h)
        panel.center = (w // 2, int(h * 0.47))
        ui.draw_panel(surf, panel, fill=ui.PAPER, radius=16)
        ui.pixel_text(surf, "WHAT SHALL BAL PLANT?", S(21),
                      panel.centerx, panel.y + S(16), color=ui.INK, center=True)
        ui.pixel_text(surf, "SOUNDS BECOME SPROUTS   -   SONGS BECOME GRAMOPHONES",
                      S(11), panel.centerx, panel.y + S(48),
                      color=ui.INK_SOFT, center=True)
        ui.pixel_text(surf, "UP / DOWN + ENTER   -   CLICK   -   ESC CLOSE", S(11),
                      panel.centerx, panel.y + S(68),
                      color=ui.INK_SOFT, center=True)

        self.tray["rects"] = []
        top = panel.y + S(92)
        idx = self.tray["idx"]
        first = max(0, min(idx - rows // 2, len(items) - rows))
        for i in range(first, first + rows):
            item = items[i]
            r = pygame.Rect(panel.x + S(16), top + (i - first) * row_h,
                            panel.w - S(32), row_h - S(6))
            sel = (i == idx)
            is_rec = not isinstance(item, dict)
            ui.draw_panel(surf, r, fill=(ui.CREAM if sel else ui.PAPER_DK),
                          edge=(ui.GRASS if sel else ui.PAPER_EDGE),
                          radius=9, shadow=False)
            if is_rec:
                draw_icon(surf, r.x + S(19), r.centery, S(10),
                          (222, 178, 110), "note", 0.0)
                nrect = pygame.Rect(r.x + S(38), r.y + S(6), r.w - S(144), S(18))
                ui.pixel_text_fit_box(surf, item.name.upper(), S(14), nrect,
                                      color=ui.INK, min_size=S(10), center=False)
                irect = pygame.Rect(r.right - S(126), r.y + S(8), S(114), S(14))
                ui.pixel_text_fit_box(surf, "RECORD  -  %d BPM" % item.tempo, S(10), irect,
                                      color=ui.INK_SOFT, min_size=S(8), bold=False, right=True, center=False)
            else:
                col = tuple(item.get("color", ui.GRASS))
                draw_icon(surf, r.x + S(19), r.centery, S(10), col,
                          item.get("icon", "note"), 0.0)
                nrect = pygame.Rect(r.x + S(38), r.y + S(6), r.w - S(116), S(18))
                ui.pixel_text_fit_box(surf, item["name"].upper(), S(14), nrect,
                                      color=ui.INK, min_size=S(10), center=False)
                irect = pygame.Rect(r.right - S(98), r.y + S(8), S(86), S(14))
                ui.pixel_text_fit_box(surf, item.get("type", "").upper(), S(10), irect,
                                      color=ui.INK_SOFT, min_size=S(8), bold=False, right=True, center=False)
            self.tray["rects"].append((r, item))



class CollectFx:
    """A short celebratory burst when a component is collected.

    Sparkle motes fan out from the cat while a glowing copy of the component
    icon arcs up toward the collection counter, so the find clearly 'goes into'
    your library.
    """

    _LIFE = 0.95
    _spark_cache = {}
    _glow_cache = {}

    @classmethod
    def _spark_surface(cls, radius, alpha):
        aq = max(0, min(255, int(alpha // 32) * 32))
        key = (radius, aq)
        surf = cls._spark_cache.get(key)
        if surf is None:
            surf = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 250, 232, aq),
                               (radius + 1, radius + 1), radius)
            cls._spark_cache[key] = surf
        return surf

    @classmethod
    def _glow_surface(cls, radius, color, alpha):
        aq = max(0, min(255, int(alpha // 24) * 24))
        key = (radius, tuple(color), aq)
        surf = cls._glow_cache.get(key)
        if surf is None:
            surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*color, aq), (radius, radius), radius)
            cls._glow_cache[key] = surf
            if len(cls._glow_cache) > 256:
                cls._glow_cache.pop(next(iter(cls._glow_cache)))
        return surf

    def __init__(self, x, y, target, color, icon, rarity):
        self.x0, self.y0 = x, y
        self.tx, self.ty = target
        self.color = color
        self.icon = icon
        self.rarity = rarity
        self.t = 0.0
        self.done = False
        rng = __import__("random").Random()
        n = {"common": 8, "uncommon": 11, "rare": 16, "secret": 22}.get(rarity, 8)
        self.motes = []
        for _ in range(n):
            a = rng.uniform(0, math.tau)
            sp = rng.uniform(60, 230)
            self.motes.append([x, y, math.cos(a) * sp, math.sin(a) * sp - 60,
                               rng.uniform(0.4, self._LIFE)])

    def update(self, dt):
        self.t += dt
        if self.t >= self._LIFE:
            self.done = True
            return
        for m in self.motes:
            m[0] += m[2] * dt
            m[1] += m[3] * dt
            m[3] += 320 * dt           # gentle gravity

    def draw(self, surf):
        p = min(1.0, self.t / self._LIFE)
        # sparkle motes
        for m in self.motes:
            if self.t > m[4]:
                continue
            a = int(255 * (1 - self.t / m[4]))
            r = max(1, int(3 * (1 - p) + 1))
            spark = self._spark_surface(r, a)
            surf.blit(spark, (int(m[0]) - r, int(m[1]) - r))
        # streaming icon: arc from cat toward the counter, shrinking + glowing
        ease = p * p * (3 - 2 * p)
        ix = self.x0 + (self.tx - self.x0) * ease
        iy = self.y0 + (self.ty - self.y0) * ease - math.sin(p * math.pi) * 70
        size = 26 * (1 - p) + 8
        glow_r = int(size * 2.2)
        ga = min(180, int(150 * (1 - p) + 40))
        glow = self._glow_surface(glow_r, self.color, ga)
        surf.blit(glow, (int(ix) - glow_r, int(iy) - glow_r))
        draw_icon(surf, int(ix), int(iy), int(size), self.color, self.icon, self.t * 4)
