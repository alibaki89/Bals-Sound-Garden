"""Animal NPCs that wander the meadow beside the cat.

This module owns the *data* and *physics* of an animal.  The look lives in
:mod:`cat_society.render.animals` (drawn procedurally, just like the cat) and
the wandering brain lives in :mod:`cat_society.systems.animal_ai`.  Keeping
those three apart mirrors how the cat is split across ``entities/cat.py`` and
``render/cat.py``.

An :class:`Animal` holds a world position ``x, z``, a little velocity, a hop
height ``y_off`` (same idea the cat uses) and a handful of behaviour timers.
Every frame :meth:`update` lets the AI pick a move, then steps the simple
gravity/landing physics.  Collisions with trees, stones and the cat are sorted
out by the spawn manager, which is the piece that actually knows where those
solids are.
"""

import math

from .. import config
from ..config import JUMP_V0, JUMP_GRAV
from ..utils import clamp
from ..render.animals import draw_animal, SPECIES_KEYS
from ..systems.animal_ai import step_ai


class Species:
    """Fixed, shared facts about one kind of animal.

    All the live, changing stuff (where it is, what it is doing) lives on the
    :class:`Animal` instead.  One ``Species`` is shared by every animal of that
    kind, so this is just a tidy bag of constants.
    """

    __slots__ = ("key", "draw_scale", "habitat", "temperament", "semi_aquatic",
                 "speed", "radius", "move", "hop_power", "weight")

    def __init__(self, key, draw_scale, habitat, temperament, semi_aquatic,
                 speed, radius, move, hop_power, weight):
        self.key = key
        self.draw_scale = draw_scale      # size relative to the cat
        self.habitat = habitat            # where it likes to spawn
        self.temperament = temperament    # how it reacts to the cat
        self.semi_aquatic = semi_aquatic  # may wade into shallow water
        self.speed = speed                # wander speed, world units / second
        self.radius = radius              # body radius for collisions
        self.move = move                  # "walk" or "hop"
        self.hop_power = hop_power         # 0 = never leaves the ground
        self.weight = weight              # relative spawn frequency


# habitat tags:   meadow | forest | water_edge | farm | rare_forest
# temperament:    shy (runs from cat) | friendly (drifts toward it) | calm (ignores)
# Sizes are tuned against the cat in render/animals.py.  Speeds are gentle so
# the world feels lazy rather than busy.  weight steers how common each animal
# is when a patch of world is populated.
SPECIES = {
    "rabbit":   Species("rabbit",   0.88, "meadow",      "shy",      False, 78,  9,  "hop",  1.05, 1.1),
    "dog":      Species("dog",      1.08, "farm",        "friendly", False, 74,  13, "walk", 0.55, 0.9),
    "fox":      Species("fox",      1.02, "forest",      "shy",      False, 88,  12, "walk", 0.7,  0.7),
    "raccoon":  Species("raccoon",  1.0,  "water_edge",  "calm",     False, 60,  12, "walk", 0.5,  0.6),
    "squirrel": Species("squirrel", 0.62, "forest",      "shy",      False, 96,  7,  "hop",  0.9,  0.9),
    "frog":     Species("frog",     0.6,  "water_edge",  "shy",      True,  70,  7,  "hop",  1.1,  0.9),
    "turtle":   Species("turtle",   0.82, "water_edge",  "calm",     True,  26,  10, "walk", 0.0,  0.6),
    "pig":      Species("pig",      1.18, "farm",        "calm",     False, 50,  15, "walk", 0.35, 0.7),
    "goat":     Species("goat",     1.12, "farm",        "calm",     False, 64,  12, "walk", 0.7,  0.6),
    "chicken":  Species("chicken",  0.82, "farm",        "calm",     False, 58,  8,  "walk", 0.45, 0.8),
    "duck":     Species("duck",     0.88, "water_edge",  "calm",     True,  54,  9,  "walk", 0.4,  0.8),
    "bird":     Species("bird",     0.5,  "meadow",      "shy",      False, 92,  6,  "hop",  0.8,  0.7),
    "butterfly":Species("butterfly",0.5,  "meadow",      "shy",      False, 70,  5,  "hop",  0.6,  0.3),
    "deer":     Species("deer",     1.32, "forest",      "shy",      False, 96,  15, "walk", 0.9,  0.6),
    "sheep":    Species("sheep",    1.34, "farm",        "calm",     False, 48,  16, "walk", 0.4,  0.6),
    "cow":      Species("cow",      1.62, "farm",        "calm",     False, 42,  20, "walk", 0.0,  0.5),
    "horse":    Species("horse",    1.72, "farm",        "friendly", False, 88,  21, "walk", 0.6,  0.45),
    "owl":      Species("owl",      0.85, "rare_forest", "calm",     False, 40,  9,  "hop",  0.7,  0.45),
    "hedgehog": Species("hedgehog", 0.72, "forest",      "shy",      False, 46,  8,  "walk", 0.3,  0.6),
    "tanuki":   Species("tanuki",   1.0,  "water_edge",  "calm",     False, 58,  12, "walk", 0.5,  0.5),
}

# guard: every drawable species should have data, and vice versa
assert set(SPECIES) == set(SPECIES_KEYS), "SPECIES table is out of sync with the renderer"


class Animal:
    """One live creature wandering the world."""

    __slots__ = ("key", "spec", "x", "z", "facing", "t", "phase",
                 "vx", "vz", "y_off", "vy", "on_ground",
                 "state", "mood", "swim",
                 "ai_state", "ai_timer", "tx", "tz",
                 "home_x", "home_z", "roam",
                 "blink", "blink_t", "mood_t", "rng", "dance")

    def __init__(self, key, x, z, rng):
        self.key = key
        self.spec = SPECIES[key]
        self.x = x
        self.z = z
        self.facing = 1 if rng.random() < 0.5 else -1
        self.t = rng.uniform(0.0, 6.0)        # desync animations
        self.phase = rng.uniform(0.0, 6.28)

        self.vx = 0.0
        self.vz = 0.0
        self.y_off = 0.0
        self.vy = 0.0
        self.on_ground = True

        self.state = "idle"
        self.mood = "neutral"
        self.swim = 0.0                        # 0..1 wade depth for water animals

        # brain bookkeeping (the AI module reads and writes these)
        self.ai_state = "idle"
        self.ai_timer = rng.uniform(0.4, 2.0)
        self.tx = x                            # current wander target
        self.tz = z
        self.home_x = x                        # patch the animal sticks near
        self.home_z = z
        self.roam = 150.0 + self.spec.radius * 10.0

        self.dance = 0.0                       # beat phase while listening to a song
        self.blink = False
        self.blink_t = rng.uniform(1.0, 5.0)
        self.mood_t = rng.uniform(4.0, 12.0)
        self.rng = rng

    # -- physics -----------------------------------------------------------
    def hop(self):
        """Leave the ground with a species-sized little jump."""
        if self.on_ground and self.spec.hop_power > 0.0:
            self.vy = JUMP_V0 * config.SC * self.spec.hop_power
            self.on_ground = False

    def update(self, dt, ctx):
        """Advance the brain, then the body, for one frame."""
        self.t += dt

        # let the AI choose a heading / state for this frame
        step_ai(self, dt, ctx)

        # horizontal motion (collisions are resolved by the manager afterwards).
        # everyone can cross water: semi-aquatics glide, the rest paddle
        # gamely at a gentler pace, and nobody freezes at a shoreline.
        wf = 1.0
        if self.swim > 0.0:
            wf = 0.8 if self.spec.semi_aquatic else 0.55
        self.x += self.vx * wf * dt
        self.z += self.vz * wf * dt

        # face the way we are moving (quarter-front art flips horizontally)
        if self.vx > 6.0:
            self.facing = 1
        elif self.vx < -6.0:
            self.facing = -1

        # vertical hop physics, copied straight from the cat
        if not self.on_ground:
            self.y_off += self.vy * dt
            self.vy -= JUMP_GRAV * config.SC * dt
            if self.y_off <= 0.0:
                self.y_off = 0.0
                self.vy = 0.0
                self.on_ground = True

        # slow eye-blink and the rare mood flicker
        self.blink_t -= dt
        if self.blink_t <= 0.0:
            self.blink = not self.blink
            self.blink_t = self.rng.uniform(0.08, 0.16) if self.blink else self.rng.uniform(2.0, 6.0)

        self.mood_t -= dt
        if self.mood_t <= 0.0:
            self.mood = self.rng.choice(("neutral", "neutral", "happy"))
            self.mood_t = self.rng.uniform(5.0, 14.0)

    # -- drawing -----------------------------------------------------------
    def draw(self, surf, sx, sy, draw_scale, proj_scale, swim=0.0,
             fade=0.0, draw_shadow=True):
        """Hand off to the procedural painter at screen point ``(sx, sy)``.

        ``draw_scale`` already folds in perspective and the species size.
        ``proj_scale`` is the raw projection scale, used only to shrink the hop
        height with distance so a far-away hop does not look huge.
        """
        # the AI may want "walk" while the body is mid-hop: trust the air state
        state = self.state
        if not self.on_ground and self.spec.move == "hop":
            state = "hop"
        draw_animal(
            surf, sx, sy, self.key, self.facing, self.t, draw_scale,
            state=state, y_off=self.y_off * proj_scale, mood=self.mood,
            phase=self.phase, blink=self.blink, draw_shadow=draw_shadow,
            swim=swim, fade=fade, dance=self.dance,
        )
