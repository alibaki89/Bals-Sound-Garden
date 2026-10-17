"""The :class:`Game` loop: input, update and the per-frame draw.

This is the conductor.  It owns no drawing maths of its own beyond sequencing
the render calls; world/entity logic lives in their own modules and the actual
pixels are produced by :mod:`cat_society.render`.  Two small pieces were lifted
out of the original monolithic loop for readability: the in-water cat effects
(:func:`cat_society.render.effects.draw_cat_water_fx`) and the HUD
(:func:`cat_society.render.ui.draw_hud`).
"""

import math
import random

import pygame

from . import config
from .config import *
from .utils import clamp, ri, lerp_color
from .palette import *
from .camera import Camera
from .projection import project
from .entities.cat import Cat
from .entities.critters import Cloud, Bird, Butterfly
from .entities.particles import Petal
from .world.generation import World, land_allowed
from .world.water import WaterWorld
from .world.animal_spawns import AnimalManager
from .entities.animals import SPECIES_KEYS, Animal
from .render.background import build_sky, build_mountains, build_vignette, draw_mountains
from .render.daynight import DayNightRenderer
from .render.props import draw_prop, draw_building
from .render.atmosphere import draw_cloud, draw_bird, draw_butterfly, draw_petal
from .render.water import draw_water_obj
from .render.structures import (
    draw_bridge, draw_boat, draw_boat_body, draw_boat_trim,
    boat_seat_lift, draw_well, draw_fountain,
)
from .render.effects import draw_cat_water_fx
from .render.ui import draw_hud
from .systems.input import handle_input


class Game:
    """The whole game: owns the window, the world and the per-frame loop.

    ``__init__`` chooses the display mode, derives the low-res canvas via
    :func:`config.init_screen`, bakes the backdrop and spawns the world, the cat
    and the ambient critters.  :meth:`run` is the main loop."""

    def __init__(self, test_size=None, window=None):
        # When the app owns the display we receive the window directly and skip
        # creating one (and skip re-initialising pygame, which the app already
        # did).  Standalone use still works via test_size / fullscreen below.
        if window is not None:
            self.window = window
            win_w, win_h = window.get_size()
            config.init_screen(win_w, win_h, ui_h=getattr(config, "UI_H", win_h))
            self._init_world()
            return

        pygame.init()
        pygame.display.set_caption(TITLE)

        if test_size is not None:
            win_w, win_h = test_size
            self.window = pygame.display.set_mode(test_size, pygame.RESIZABLE)
        else:
            try:
                dw, dh = pygame.display.get_desktop_sizes()[0]
            except Exception:
                info = pygame.display.Info()
                dw, dh = info.current_w, info.current_h
            if dw < 320 or dh < 320:
                dw, dh = 1600, 900
            win_w = min(1600, max(640, dw - 80))
            win_h = min(1000, max(480, dh - 80))
            win_w, win_h = min(win_w, dw), min(win_h, dh)
            try:
                self.window = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)
            except pygame.error:
                self.window = pygame.display.set_mode((win_w, win_h))
            pygame.mouse.set_visible(False)

        # derive the low-res canvas + scale factors from the real window size
        config.init_screen(win_w, win_h, ui_h=win_h)
        self._init_world()

    def resize(self, window, ui_h=None):
        """Adopt a resized display without resetting gameplay state.

        Expensive static world backdrops are rebuilt only when the logical
        field of view actually changes. Repeating the same display size reuses
        the existing canvas and art caches.
        """
        self.window = window
        win_w, win_h = window.get_size()
        old_size = self.canvas.get_size() if hasattr(self, "canvas") else (0, 0)
        config.init_screen(win_w, win_h, ui_h=(config.UI_H if ui_h is None else ui_h))
        new_size = (config.W, config.H)
        if old_size != new_size:
            self.canvas = pygame.Surface(new_size)
            self.sky = build_sky(include_sun=False, include_rainbow=False)
            self.mountains = build_mountains()
            self.vig = build_vignette()
            self.daynight.resize(*new_size)
        self._upscale_buffer = None

    def _init_world(self):
        self.canvas = pygame.Surface((config.W, config.H))
        self._upscale_buffer = None
        self.sky = build_sky(include_sun=False, include_rainbow=False)
        self.mountains = build_mountains()
        self.vig = build_vignette()
        self.daynight = DayNightRenderer(config.W, config.H, seed=config.WORLD_SEED)
        self.visual_minutes = 9.0 * 60.0
        self.visual_day = 1
        self._story_daylight = False
        self.font = pygame.font.SysFont("couriernew,consolas,monospace", 8, bold=True)
        self.clock = pygame.time.Clock()
        self.running = True
        self.time = 0.0

        self.cam = Camera()
        self.cat = Cat()
        self.world = World()
        self.water = WaterWorld()
        # make sure we never start standing in a river, pond, or the sea
        self.cat.x, self.cat.z = self.water.nearest_dry(self.cat.x, self.cat.z)
        self.cam.snap(self.cat.x, self.cat.z)

        rng = random.Random(99)
        self.clouds = [Cloud(rng) for _ in range(6)]
        self.birds = [Bird(rng) for _ in range(3)]
        self.butterflies = [Butterfly(rng) for _ in range(4)]
        self.petals = [Petal(rng) for _ in range(18)]
        self._rng = rng

        # wandering animal NPCs (drawn procedurally, just like the cat)
        self.animals = AnimalManager(self.world, self.water, seed=99)
        self.animal_debug = False        # K toggles collision circles
        self.dbg_species = 0             # O cycles which species P spawns

        # hooks the explore screen wires up: freeze the cat while Bal performs
        # or a story card is open, feed the animals the song in the air, and
        # let landmarks stand solid like wells and fountains do
        self.input_locked = False
        self.song_ctx = None             # dict from Performance.song_ctx()
        self.landmark_solids = None      # callable (x, z) -> [(r, x, z)]
        # Temporary visual/physical clearings, used by the arrival cinematic so
        # procedural trees, stones and wildlife can never block the boat shot.
        # Each zone is (centre_x, centre_z, half_width, half_depth).
        self.clear_zones = []


    def set_clear_zones(self, zones=None):
        self.clear_zones = [tuple(map(float, zone)) for zone in (zones or [])]

    def in_clear_zone(self, x, z):
        for cx, cz, rx, rz in self.clear_zones:
            if rx <= 0.0 or rz <= 0.0:
                continue
            # Ellipses soften the edge of the temporary clearing and avoid a
            # visibly rectangular empty strip in the procedural meadow.
            if ((x - cx) / rx) ** 2 + ((z - cz) / rz) ** 2 <= 1.0:
                return True
        return False

    def set_daylight(self, minutes, day=1):
        """Use an external clock for the next world draw (Story mode)."""
        self.visual_minutes = float(minutes) % 1440.0
        self.visual_day = max(1, int(day))
        self._story_daylight = True

    def clear_external_daylight(self):
        self._story_daylight = False

    @property
    def night_strength(self):
        return self.daynight.night_strength(self.visual_minutes)

    def update(self, dt):
        self.time += dt
        if not self._story_daylight:
            real_minutes = max(4.0, float(getattr(config, "CREATIVE_DAY_REAL_MINUTES", 34.0)))
            self.visual_minutes = (self.visual_minutes + dt * 1440.0 / (real_minutes * 60.0)) % 1440.0
        keys = pygame.key.get_pressed()
        ix = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        iz = (keys[pygame.K_w] or keys[pygame.K_UP]) - (keys[pygame.K_s] or keys[pygame.K_DOWN])
        running = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        if self.input_locked:
            ix = iz = 0
            running = False

        if self.cat.boat is not None:
            self._update_boat(dt, ix, iz, running)
        else:
            on_deck = self.water.on_bridge(self.cat.x, self.cat.z)
            depth0, _, mode0 = self.water.water_mode_at(self.cat.x, self.cat.z)

            # speed depends on how deep the water is: full on land/bridge,
            # a gentle wade in the shallows, slower the deeper it gets
            if on_deck or mode0 == "land":
                spd_scale = 1.0
            elif mode0 == "shallow":
                spd_scale = 0.82
            elif mode0 == "medium":
                spd_scale = 0.66
            else:
                spd_scale = 0.5

            was_in_water = self.cat.in_water
            self.cat.update(dt, ix, iz, running, speed_scale=spd_scale)

            # props never block, but deep water still shouldn't hide solid
            # trunks the cat is standing next to, so only keep near-dry solids
            solids = self.world.solids_near(self.cat.x, self.cat.z)
            solids = [s for s in solids if self.water.depth_at(s[1], s[2])[0] <= 0.03]
            # wells and fountains are solid landmarks: the cat bumps into them
            for ob in self.water.interactives:
                if abs(ob.x - self.cat.x) < 140 and abs(ob.z - self.cat.z) < 140:
                    r = 30.0 if ob.kind == "fountain" else 26.0
                    solids.append((r, ob.x, ob.z))
            if self.landmark_solids is not None:
                solids.extend(self.landmark_solids(self.cat.x, self.cat.z))
            self.cat.resolve_collisions(solids)

            # how high the bridge lifts the cat right here (0 off a bridge)
            self.cat.bridge_lift = self.water.bridge_arch_at(self.cat.x, self.cat.z)

            # recompute depth where we ended up and aim the submersion at it
            nd, _, nmode = self.water.water_mode_at(self.cat.x, self.cat.z)
            airborne = not self.cat.on_ground
            if on_deck or airborne:
                target = 0.0
                self.cat.in_water = False
            else:
                target = self.water.submerge_for_depth(nd)
                self.cat.in_water = nmode != "land"

            # a splash the moment the cat steps into real (not just edge) water
            entered = self.cat.in_water and not was_in_water
            if entered and nmode in ("medium", "deep"):
                self.cat.splash_t = 0.5

            rate = dt * 9.0
            self.cat.swim += clamp(target - self.cat.swim, -rate, rate)
            if self.cat.splash_t > 0.0:
                self.cat.splash_t = max(0.0, self.cat.splash_t - dt)
        self.cam.follow(self.cat.x, self.cat.z)

        self.water.update(dt, self.cat)
        self.animals.update(dt, self.cat, song=self.song_ctx,
                            night=self.night_strength,
                            minutes=self.visual_minutes,
                            exclusion_zones=self.clear_zones)
        for b in self.birds:
            b.update(dt, self._rng)
        for p in self.petals:
            p.update(dt)

    def _update_boat(self, dt, ix, iz, running):
        b = self.cat.boat
        mag = math.hypot(ix, iz)
        if mag > 0:
            ix, iz = ix / mag, iz / mag
        spd = BOAT_SPEED * (RUN_MULT if running else 1.0)
        nx = b.x + ix * spd * dt
        nz = b.z + iz * spd * dt
        if self.water.boat_water(nx, nz):
            b.x, b.z = nx, nz
        else:
            if self.water.boat_water(nx, b.z):
                b.x = nx
            if self.water.boat_water(b.x, nz):
                b.z = nz
        if ix > 0.01:
            b.facing = 1
        elif ix < -0.01:
            b.facing = -1
        b.t += dt
        self.cat.x, self.cat.z = b.x, b.z
        self.cat.facing = b.facing
        self.cat.moving = False
        self.cat.running = False
        self.cat.on_ground = True
        self.cat.t += dt
        self.cat.swim = 0.0
        self.cat.in_water = False
        self.cat.bridge_lift = 0.0

    def paint_world(self, extra_drawables=None):
        """Paint the whole world onto the low-res canvas (no vignette/HUD/upscale).

        ``extra_drawables`` is an optional list of ``(sort_y, 40, draw_fn)``
        entries (used by the explore screen to inject music pickups) which are
        merged into the world's depth sort so they occlude / are occluded by
        props, trees and the cat exactly like every other world object.
        """
        surf = self.canvas
        surf.blit(self.sky, (0, 0))
        self.daynight.draw_sky(surf, self.visual_minutes, self.visual_day, self.time)
        draw_mountains(surf, self.mountains, self.cam)

        cloud_palette = self.daynight.palette(self.visual_minutes)
        for c in self.clouds:
            draw_cloud(surf, c.screen_x(self.cam, self.time), c.y, c.s,
                       cloud_palette)
        # Day birds and butterflies settle once night is established.
        if self.night_strength < .62:
            for b in self.birds:
                draw_bird(surf, b, self.time)

        self.water.draw_surface(surf, self.cam, self.time)

        scenery, placed = self.world.gather(self.cam)

        cam_x = self.cam.x
        cam_z = self.cam.z
        gy_h = config.GROUND_Y - config.MEADOW_HORIZON
        w_half = config.W * 0.5
        # generous off-screen margins so objects ease in/out instead of popping
        top = config.HORIZON - 80
        bottom = config.H + 260
        margin_x = int(config.W * 0.45)
        left = -margin_x
        right = config.W + margin_x

        drawables = []
        add = drawables.append

        for kind, wx, wz, seed in scenery:
            if self.in_clear_zone(wx, wz):
                continue
            depth = self.water.depth_at(wx, wz)[0]
            if not land_allowed(kind, depth):
                continue
            d = (wz - cam_z) + FOCAL
            if d <= MIN_D:
                continue
            scale = FOCAL / d
            if scale <= FADE_S_LO:        # fully melted into the horizon haze
                continue
            # wide atmospheric ramp: props stay crisp up close, then lose
            # contrast gently into a soft, calm, readable far field -- no more
            # full-contrast specks that pop as the camera moves
            if scale >= PROP_FADE_HI:
                fade = 0.0
            else:
                fade = clamp((PROP_FADE_HI - scale) / (PROP_FADE_HI - FADE_S_LO),
                             0.0, 1.0) * PROP_FADE_MAX
            if kind in SMALL_DECO:
                # quality control for the far field: drop the tiniest specks and
                # ease the rest into the haze so they stop reading as confetti
                if scale < DECO_MIN_S:
                    continue
                extra = clamp((DECO_HAZE_S - scale) / (DECO_HAZE_S - DECO_MIN_S), 0.0, 1.0)
                fade = clamp(fade + extra * 0.45, 0.0, 0.92)
            sy = config.MEADOW_HORIZON + gy_h * scale
            if sy < top or sy > bottom:
                continue
            sx = w_half + (wx - cam_x) * scale * config.SC
            if sx < left or sx > right:
                continue
            add((sy, 0, kind, sx, sy, scale, seed, fade))

        for obj in placed:
            if self.in_clear_zone(obj.x, obj.z):
                continue
            d = (obj.z - cam_z) + FOCAL
            if d <= MIN_D:
                continue
            scale = FOCAL / d
            if scale <= FADE_S_LO:
                continue
            if scale >= PROP_FADE_HI:
                fade = 0.0
            else:
                fade = clamp((PROP_FADE_HI - scale) / (PROP_FADE_HI - FADE_S_LO),
                             0.0, 1.0) * PROP_FADE_MAX
            sy = config.MEADOW_HORIZON + gy_h * scale
            if sy < top or sy > bottom:
                continue
            sx = w_half + (obj.x - cam_x) * scale * config.SC
            if sx < left or sx > right:
                continue
            add((sy, 2, obj.kind, sx, sy, scale, 0, fade))

        # butterflies live in the world so they sort with everything else
        for bf in self.butterflies:
            if self.night_strength >= .48:
                continue
            wx, wz = bf.world(self.cat, self.time)
            if self.in_clear_zone(wx, wz):
                continue
            pr = project(wx, wz, self.cam)
            if pr is None:
                continue
            bsx, bsy, bscale = pr
            if bscale < FADE_S_HI:
                continue
            bob = math.sin(self.time * 4.0 + bf.phase) * 6.0 * bscale * config.SC
            flap = math.sin(self.time * bf.flapsp + bf.phase)
            add((bsy + bob, 3, bf.col, bsx, bsy + bob - 12 * bscale * config.SC, bscale * config.SC, flap, 0.0))

        # wandering animals sort into the same depth list as props and the cat
        for an in self.animals.animals():
            if self.in_clear_zone(an.x, an.z):
                continue
            d = (an.z - cam_z) + FOCAL
            if d <= MIN_D:
                continue
            ascale = FOCAL / d
            if ascale <= FADE_S_LO:
                continue
            if ascale >= PROP_FADE_HI:
                afade = 0.0
            else:
                afade = clamp((PROP_FADE_HI - ascale) / (PROP_FADE_HI - FADE_S_LO),
                              0.0, 1.0) * PROP_FADE_MAX
            asy = config.MEADOW_HORIZON + gy_h * ascale
            if asy < top or asy > bottom:
                continue
            asx = w_half + (an.x - cam_x) * ascale * config.SC
            if asx < left or asx > right:
                continue
            adraw = ascale * config.SC * an.spec.draw_scale
            add((asy, 30, an, asx, asy, adraw, ascale, afade))

        cx, cy, cscale = project(self.cat.x, self.cat.z, self.cam)
        # The camera tracks the cat's x, so the cat always belongs at the exact
        # horizontal centre.  Pin it there (instead of trusting a sub-pixel
        # projection that can round either way on odd canvas widths) so the
        # focal point of the whole game stays perfectly steady while the world
        # snaps around it.
        cx = config.W * 0.5
        ck = cscale * config.SC
        sw = self.cat.swim
        if self.cat.boat is not None:
            # the boat + cat are drawn together so the rim sits in front of it.
            # store the RAW projection scale (the boat helpers multiply by SC).
            add((cy + 0.6, 19, self.cat.boat, cx, cy, cscale))
        else:
            # ride the bridge arch: lift the contact point by the world arch
            lift_px = self.cat.bridge_lift * ck
            sort_y = cy
            # when standing on a bridge, the cat and the bridge are at the same
            # depth (a sort tie), so the cat could land under the deck.  Push the
            # cat's sort key in front of the bridge's nearest edge so it always
            # draws on top of the deck it is walking on.
            bu = self.water._bridge_under(self.cat.x, self.cat.z)
            if bu is not None:
                _bk, bzb, _bh = bu
                pne = project(self.cat.x, bzb - DECK_Z * 0.5, self.cam)
                if pne is not None:
                    sort_y = max(cy, pne[1]) + 1.0
            add((sort_y, 1, None, cx, cy - lift_px, ck, sw <= 0.05, sw))

        self.water.gather_drawables(self.cam, self.time, add, self.cat,
                                    clear_zone=self.in_clear_zone if self.clear_zones else None)

        if extra_drawables:
            drawables.extend(extra_drawables)

        drawables.sort(key=lambda e: e[0])
        for e in drawables:
            tag = e[1]
            if tag == 0:
                draw_prop(surf, e[2], e[3], e[4], e[5], e[6], e[7])
            elif tag == 2:
                draw_building(surf, e[2], e[3], e[4], e[5], e[7])
            elif tag == 3:
                draw_butterfly(surf, e[3], e[4], e[5], e[6], e[2])
            elif tag == 30:
                an = e[2]
                an.draw(surf, e[3], e[4], e[5], e[6], swim=an.swim, fade=e[7])
            elif tag == 9:
                draw_water_obj(surf, e[2], e[3], e[4], e[5], e[7], e[6], self.time)
            elif tag == 15:
                bc, bhw, bzb, bfade = e[2]
                draw_bridge(surf, bc, bhw, bzb, bfade, self.cam, e[3], self.time)
            elif tag == 16:
                draw_boat(surf, e[2][0], e[2][1], e[3], e[4], e[5], e[6], self.time)
            elif tag == 17:
                draw_well(surf, e[2], e[3], e[4], e[5], e[6], e[7], self.time)
            elif tag == 18:
                draw_fountain(surf, e[2], e[3], e[4], e[5], e[6], e[7], self.time)
            elif tag == 19:
                # boat hull, then the cat sitting in it, then the near rim/oar.
                # e[5] is the RAW projection scale; boat helpers apply SC, but
                # the cat wants the SC-multiplied scale.
                bo = e[2]
                bsx, bsy, braw = e[3], e[4], e[5]
                draw_boat_body(surf, bo.kind, bo, bsx, bsy, braw, 0.0, self.time)
                seat = bsy - boat_seat_lift(braw)
                self.cat.draw(surf, bsx, seat, braw * config.SC, draw_shadow=False, swim=0.0)
                draw_boat_trim(surf, bo.kind, bo, bsx, bsy, braw, 0.0, self.time)
            elif tag == 40:
                e[2](surf)            # depth-sorted music pickup
            else:
                self.cat.draw(surf, e[3], e[4], e[5], draw_shadow=e[6], swim=e[7])

        draw_cat_water_fx(surf, self.cat, self.cam, self.time)

        for p in self.petals:
            draw_petal(surf, p)

        if self.animal_debug:
            self._draw_animal_debug(surf, cam_x, cam_z, gy_h, w_half, top, bottom)

        self.daynight.apply_world_lighting(surf, self.visual_minutes)

    def draw_music_lights(self, sources):
        """Draw additive light halos supplied by sprouts and gramophones."""
        self.daynight.draw_music_lights(self.canvas, sources, self.visual_minutes)

    def apply_vignette(self):
        """Soft corner darkening over the world (and anything drawn on top)."""
        self.canvas.blit(self.vig, (0, 0))

    def upscale_to_window(self, dest=None):
        """Present the world with a fixed, uniform integer pixel scale.

        Fullscreen expands the low-resolution canvas instead of stretching it.
        The persistent fallback surface is needed only for the one-or-two-pixel
        centred crop produced by ``ceil``; it avoids allocating a screen-sized
        temporary on every frame.
        """
        dest = self.window if dest is None else dest
        target = (config.W * config.PIX, config.H * config.PIX)
        if target == dest.get_size() and config.VIEW_X == 0 and config.VIEW_Y == 0:
            try:
                pygame.transform.scale(self.canvas, target, dest)
                return
            except (TypeError, ValueError, pygame.error):
                pass

        buf = getattr(self, "_upscale_buffer", None)
        if buf is None or buf.get_size() != target:
            buf = pygame.Surface(target)
            self._upscale_buffer = buf
        pygame.transform.scale(self.canvas, target, buf)
        dest.blit(buf, (config.VIEW_X, config.VIEW_Y))

    def draw_scene(self):
        """Standalone full draw: world + vignette + the old HUD + upscale.

        The app does not use this -- the explore screen calls paint_world,
        injects pickups, then applies the vignette and upscales itself -- but it
        keeps the engine runnable on its own (and is handy for smoke tests).
        """
        self.paint_world()
        self.apply_vignette()
        draw_hud(self.canvas, self.font)
        self.upscale_to_window()

    # -- animal debug helpers (wired to keys in systems/input.py) ----------
    def dbg_spawn_animal(self):
        """Drop one animal of the current debug species just ahead of the cat."""
        key = SPECIES_KEYS[self.dbg_species % len(SPECIES_KEYS)]
        ox = 70.0 * self.cat.facing
        x, z = self.cat.x + ox, self.cat.z + 40.0
        x, z = self.water.nearest_dry(x, z)
        cell = (int(x // 780), int(z // 780))  # ANIMAL_CELL = CHUNK*3
        a = Animal(key, x, z, random.Random(self._rng.random() * 1e9))
        self.animals.cells.setdefault(cell, []).append(a)
        return key

    def dbg_cycle_species(self):
        self.dbg_species = (self.dbg_species + 1) % len(SPECIES_KEYS)
        return SPECIES_KEYS[self.dbg_species]

    def dbg_clear_animals(self, reach=520.0):
        """Forget every cell near the cat, clearing the local animals."""
        cx, cz = self.cat.x, self.cat.z
        for key in list(self.animals.cells.keys()):
            ccx = (key[0] + 0.5) * 780
            ccz = (key[1] + 0.5) * 780
            if math.hypot(ccx - cx, ccz - cz) < reach + 780:
                del self.animals.cells[key]

    def _draw_animal_debug(self, surf, cam_x, cam_z, gy_h, w_half, top, bottom):
        for an in self.animals.animals():
            if self.in_clear_zone(an.x, an.z):
                continue
            d = (an.z - cam_z) + FOCAL
            if d <= MIN_D:
                continue
            sc = FOCAL / d
            sy = config.MEADOW_HORIZON + gy_h * sc
            if sy < top or sy > bottom:
                continue
            sx = w_half + (an.x - cam_x) * sc * config.SC
            rr = max(2, ri(an.spec.radius * sc * config.SC))
            col = (235, 90, 90) if an.spec.temperament == "shy" else (
                90, 170, 235) if an.spec.temperament == "friendly" else (235, 205, 90)
            pygame.draw.circle(surf, col, (ri(sx), ri(sy)), rr, 1)

    def run(self):
        dt = 0.0
        while self.running:
            handle_input(self)
            self.update(dt)
            self.draw_scene()
            pygame.display.flip()
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 20.0)
        pygame.quit()


def _main():
    """Console entry point (see pyproject.toml [project.scripts])."""
    Game().run()
