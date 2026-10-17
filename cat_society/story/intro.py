"""The playable opening: sail in, hop ashore, choose a shop site, build it."""

import math

from ..world.water import coast_z_at


class LandingIntro:
    """A small deterministic state machine owned by :class:`StoryScreen`."""

    def __init__(self, story_state, shop):
        self.state = story_state
        self.shop = shop
        self.phase = "done" if story_state.intro_complete else "sail"
        self.t = 0.0
        self.cards_queued = False
        self.build_finished = False
        self.preview = None
        self.preview_reason = ""
        self._boat = None
        self._start = None
        self._land = None
        self._shop_candidate = None
        self._hammer_tick = -1

    @property
    def active(self):
        return self.phase != "done"

    @property
    def cinematic(self):
        return self.phase in ("sail", "hop", "build")

    @property
    def placing(self):
        return self.phase == "place"

    def begin(self, game):
        if self.phase == "done":
            game.set_clear_zones([])
            return
        x = -105.0
        coast = coast_z_at(x)
        start_z = coast + 650.0
        end_z = coast + 150.0
        land_x, land_z = game.water.nearest_dry(x + 18.0, coast - 80.0)
        boat = game.water.spawn_boat(x, start_z)
        boat.occupied = True
        boat.facing = -1
        game.cat.boat = boat
        game.cat.x, game.cat.z = x, start_z
        game.cam.snap(x, start_z)
        self._boat = boat
        self._start = (x, start_z)
        self._land = (land_x, land_z)

        # Reserve a clean oval corridor from open water onto the beach.  The
        # procedural world still exists underneath and returns after the intro,
        # but no tree, stone, water rock, spare boat or wild animal can cross or
        # hide Bal's arrival shot.
        centre_z = (start_z + land_z) * .5
        half_depth = abs(start_z - land_z) * .5 + 190.0
        game.set_clear_zones([(x + 8.0, centre_z, 260.0, half_depth)])

    def skip_to_placement(self, game, story_cards):
        if self.phase == "done":
            return
        if self._boat is None:
            self.begin(game)
        self._boat.x = self._land[0] - 18.0
        self._boat.z = coast_z_at(self._land[0]) + 145.0
        self._boat.occupied = False
        game.cat.boat = None
        game.cat.x, game.cat.z = self._land
        game.cat.y_off = 0.0
        game.cam.snap(game.cat.x, game.cat.z)
        game.set_clear_zones([])
        story_cards.clear()
        self.phase = "place"
        self.t = 0.0

    def update(self, dt, game, story_cards):
        if self.phase == "done":
            return
        self.t += dt
        if self._boat is None:
            self.begin(game)

        if self.phase == "sail":
            # Slow ease-in, then a gentle glide into the shallows.
            p = min(1.0, self.t / 4.6)
            e = p * p * (3.0 - 2.0 * p)
            x0, z0 = self._start
            coast = coast_z_at(x0)
            z1 = coast + 150.0
            self._boat.x = x0 + math.sin(p * math.pi) * 22.0
            self._boat.z = z0 + (z1 - z0) * e
            self._boat.t += dt
            game.cat.x, game.cat.z = self._boat.x, self._boat.z
            if p >= 1.0:
                self.phase = "hop"
                self.t = 0.0
                game.cat.boat = None
                self._boat.occupied = False

        elif self.phase == "hop":
            p = min(1.0, self.t / 1.15)
            e = p * p * (3.0 - 2.0 * p)
            bx, bz = self._boat.x, self._boat.z
            lx, lz = self._land
            game.cat.x = bx + (lx - bx) * e
            game.cat.z = bz + (lz - bz) * e
            game.cat.y_off = math.sin(p * math.pi) * 34.0
            game.cat.facing = 1
            if p >= 1.0:
                game.cat.x, game.cat.z = self._land
                game.cat.y_off = 0.0
                self.phase = "cards"
                self.t = 0.0

        elif self.phase == "cards":
            if not self.cards_queued:
                self.cards_queued = True
                story_cards.queue(
                    "BAL, THE FAMOUS MUSIC MAKER",
                    ["Bal is a world-famous music maker. Animals from many lands know his songs.",
                     "Now he has sailed to a new island to begin a different kind of adventure."],
                    icon="note", footer="press any key")
                story_cards.queue(
                    "BAL STARTS A NEW ADVENTURE",
                    ["The animals here need songs, sound seeds, and music placed around the island.",
                     "Bal will meet them, take the requests he likes, and build a new life through his work."],
                    icon="note", footer="press any key")
                story_cards.queue(
                    "BUILD BAL'S MUSIC SHOP",
                    ["Choose a dry, open place for Bal's shop.",
                     "Clients will visit during the day. Some will wait, some will return later, and some will ask for a delivery."],
                    icon="note", footer="press any key")
            if self.cards_queued and not story_cards.blocking:
                game.set_clear_zones([])
                self.phase = "place"
                self.t = 0.0

        elif self.phase == "place":
            x, z = game.cat.x, game.cat.z + 78.0
            ok, reason = self.shop.valid_at(game, x, z)
            self.preview = (x, z, ok)
            self.preview_reason = reason
            self._shop_candidate = (x, z, ok)

        elif self.phase == "build":
            # Bal repeatedly pats and hammers at the rising stall rather than
            # standing frozen while the building assembles itself.
            hammer_tick = int(self.t * 3.0)
            if hammer_tick != self._hammer_tick:
                self._hammer_tick = hammer_tick
                game.cat.facing = -1 if hammer_tick % 2 else 1
                game.cat.attack()
            self.shop.update(dt)
            if self.shop.ready and not self.build_finished:
                self.build_finished = True
                self.state.place_shop(self.shop.x, self.shop.z,
                                      self._boat.x, self._boat.z)
                story_cards.queue(
                    "BAL'S ISLAND STUDIO IS OPEN",
                    ["Bal's new studio is ready.",
                     "The first clients are already walking toward the shop."],
                    icon="note", footer="press any key")
                self.phase = "finish_cards"

        elif self.phase == "finish_cards":
            self.shop.update(dt)
            if self.build_finished and not story_cards.blocking:
                game.set_clear_zones([])
                self.phase = "done"
                self.t = 0.0

    def try_build(self):
        if self.phase != "place" or not self._shop_candidate:
            return False, ""
        x, z, ok = self._shop_candidate
        if not ok:
            return False, self.preview_reason
        self.preview = None
        self.shop.start_build(x, z)
        self.phase = "build"
        self.t = 0.0
        return True, "Bal starts building the shop."

    def overlay_text(self):
        if self.phase == "sail":
            return "THE FAMOUS MUSIC MAKER ARRIVES", "S  SKIP INTRO"
        if self.phase == "hop":
            return "BAL STEPS ONTO THE ISLAND", "S  SKIP INTRO"
        if self.phase == "place":
            return ("CHOOSE WHERE BAL'S SHOP WILL STAND",
                    "WASD  MOVE   -   E  BUILD HERE")
        if self.phase == "build":
            return "BAL BUILDS HIS MUSIC SHOP", ""
        return None, None
