"""Central configuration: every tunable constant in one place.

Two kinds of values live here:

* **Constants** (focal length, speeds, chunk size, water tuning, ...). These
  never change at runtime and are exported via ``from .config import *``.

* **Screen state** (``W``, ``H``, ``PIX``, ``SC``, ``HORIZON``, ``GROUND_Y``,
  ``MEADOW_HORIZON``, ``WIN_W``, ``WIN_H``). These are derived from the real
  window plus the stable presentation scale and refreshed by :func:`init_screen`.
  Because they change after import, every other module reads them live as
  ``config.W``, ``config.SC`` and so on (never ``from .config import W``,
  which would capture a stale value).
"""

import math
import random

# ============================================================
# World seed  (changes every launch unless you fix it below)
# ============================================================
# Set DEBUG_SEED to a number to always get the same world (handy while
# tweaking).  Leave it None to roll a fresh world every time the game starts.
DEBUG_SEED = None
WORLD_SEED = DEBUG_SEED if DEBUG_SEED is not None else random.randrange(1, 2_000_000_000)

# ============================================================
# Screen / canvas state  (filled in by init_screen at startup)
# ============================================================
W, H = 384, 216                  # low-res canvas (field of view may expand)
PIX = 5                          # fixed integer presentation scale
SCALE_X, SCALE_Y = 5.0, 5.0      # exact, uniform canvas->window scale
VIEW_X, VIEW_Y = 0, 0            # tiny centred crop when ceil adds spare pixels
WIN_W, WIN_H = 1920, 1080        # real window size
UI_H = 1080                      # stable windowed height preserved across F11
SC = 216 / 640.0                 # world-art scale; never tied to fullscreen size
HORIZON = int(H * 0.32)
GROUND_Y = int(H * 0.60)
MEADOW_HORIZON = HORIZON + int(216 * 0.075)

VIRTUAL_H = 216                  # composition height of the original view


def init_screen(win_w, win_h, ui_h=None):
    """Build a pixel-perfect canvas without fullscreen zoom.

    ``UI_H`` is the height of the decorated/windowed presentation.  F11 keeps
    that value, so ``PIX`` and every world's physical pixel size remain fixed.
    A larger display receives a larger logical canvas instead: the original
    ``VIRTUAL_H`` composition is centred inside it and the player simply sees
    more world around the edges.  Integer presentation scaling keeps x/y
    proportions identical and preserves the game's crisp pixel style.
    """
    global WIN_W, WIN_H, UI_H, PIX, SCALE_X, SCALE_Y, VIEW_X, VIEW_Y
    global W, H, SC, HORIZON, GROUND_Y, MEADOW_HORIZON
    WIN_W, WIN_H = max(1, int(win_w)), max(1, int(win_h))
    UI_H = max(320, int(ui_h if ui_h is not None else WIN_H))

    PIX = max(2, int(round(UI_H / float(VIRTUAL_H))))
    W = max(96, int(math.ceil(WIN_W / float(PIX))))
    H = max(96, int(math.ceil(WIN_H / float(PIX))))
    SCALE_X = SCALE_Y = float(PIX)
    VIEW_X = (WIN_W - W * PIX) // 2
    VIEW_Y = (WIN_H - H * PIX) // 2
    SC = VIRTUAL_H / 640.0

    # Centre the historical 216-high composition inside the expanded canvas.
    # This keeps the horizon and Bal's ground contact in the same physical
    # place relative to screen centre while extra display area reveals more.
    top = (H - VIRTUAL_H) / 2.0
    HORIZON = int(round(top + VIRTUAL_H * 0.32))
    GROUND_Y = int(round(top + VIRTUAL_H * 0.60))
    MEADOW_HORIZON = HORIZON + int(VIRTUAL_H * 0.075)


def canvas_to_window(x, y):
    """Map a low-resolution world-canvas point to the real window."""
    return VIEW_X + x * PIX, VIEW_Y + y * PIX


def window_to_canvas(x, y):
    """Map a real-window point back to the low-resolution world canvas."""
    return (x - VIEW_X) / float(PIX), (y - VIEW_Y) / float(PIX)


# ============================================================
# Core gameplay / rendering constants
# ============================================================
FPS = 60
TITLE = "Bal's Sound Garden"

# perspective. FOCAL also acts as how far the camera sits behind the cat.
FOCAL = 620.0
MIN_D = 8.0

CAT_SPEED = 230.0
CAT_R = 14.0
COLLIDE_REACH = 170.0
RUN_MULT = 1.7
JUMP_V0 = 540.0
JUMP_GRAV = 1900.0
ATTACK_DUR = 0.42
CAT_DRAW_SCALE = 0.9      # ART: the cat sits a touch smaller beside the animal roster

SOLID_R = {"tree": 40.0, "stone": 30.0, "bush": 0.0}
PLACED_R = {"post": 12.0}

PROP_GROW = {"tree": 2.3, "bush": 1.6, "stone": 1.8, "flower": 1.4,
             "tuft": 1.25, "mushroom": 1.2, "pebble": 1.1}

CHUNK = 260
FAR_Z = 5800.0
FADE_S_HI = 0.22
FADE_S_LO = 0.12
GRASS_MIN_S = 0.52               # dense grass only drawn where scale is at least this

# ---- distant-detail control (the art/quality knobs) -------------------------
# Small decorative props (grass tufts, single flowers, mushrooms, pebbles) turn
# into pixel-confetti when they shrink into the distance, so we (a) stop drawing
# them past DECO_MIN_S and (b) ease the survivors into the haze early, below
# DECO_HAZE_S.  Raise DECO_MIN_S for a cleaner (emptier) far field; lower it to
# keep more distant specks.  GRASS_MIN_S above controls the grass-carpet reach.
SMALL_DECO = ("tuft", "flower", "mushroom", "pebble")
DECO_MIN_S  = 0.32              # ART: below this screen-scale, skip small deco
DECO_HAZE_S = 0.68             # ART: below this, fade small deco toward haze
GROUND_SPECKLE = 0.0011        # ART: baked meadow-texture density (brushstrokes)

# ---- atmospheric far-fade for ALL props (the key calm-distance knob) ---------
# Ramp every prop gently toward the haze across a wide band: crisp and
# full-contrast up close (>= PROP_FADE_HI), losing contrast smoothly into a
# soft, readable, low-contrast far field.  Raise PROP_FADE_HI to start
# softening nearer; lower PROP_FADE_MAX to keep more far detail.
PROP_FADE_HI  = 0.55           # ART: at/above this screen-scale, props are crisp
PROP_FADE_MAX = 0.86           # ART: how far into the haze the most distant go

# ============================================================
# Art-direction polish knobs  (new visual-quality pass)
# ============================================================
# These only affect how things LOOK.  None of them touch geometry, collision,
# projection, speeds or world layout - they are pure painting controls.
#
#   --- Sky / atmosphere ---
SUN_BLOOM        = 1.30        # ART: size of the soft sun bloom (1 = original)
SUN_GLINT        = 0.55        # ART: warmth of the sky lift around the sun
RAINBOW_ALPHA    = 46          # ART: rainbow band opacity (0 = off, ~46 = soft)
HORIZON_MIST     = 0.55        # ART: strength of the misty band along the skyline
MTN_HAZE         = 0.50        # ART: how much the far hills melt into the air
VIGNETTE_STRENGTH = 70         # ART: max corner-darkening alpha (0 = no vignette)
VIGNETTE_WARMTH  = 0.30       # ART: warm vs cool tint of the vignette corners
#
#   --- Meadow brushwork (the painterly ground texture) ---
# A second, layered pass of soft horizontal grass dabs on top of the old
# speckle: warm sunlit clumps, cool shaded clumps and the occasional bright
# sun-dapple.  Raise MEADOW_BRUSH for a busier painted floor, lower it for a
# calmer one.  DAPPLE_CHANCE biases how many dabs are bright highlights.
MEADOW_BRUSH     = 0.0020      # ART: density of painterly grass dabs
MEADOW_DAPPLE_CHANCE = 0.16    # ART: fraction of dabs that are sun-dapple
GRASS_SWAY_TONE  = 0.18        # ART: subtle two-tone shading inside grass tufts
#
#   --- Water look ---
WATER_HAZE       = 0.80        # ART: how strongly water fades into the far haze
SHORE_FOAM       = 1.00        # ART: foam density along river banks / coast
WATER_GLINT      = 1.00        # ART: density of soft surface sparkles
WATER_SHEEN      = 0.22       # ART: strength of the broad surface light sheen


# ============================================================
# Story shop clock / client-flow tuning
# ============================================================
# The shop day deliberately continues while the Music Maker is open.
STORY_DAY_REAL_MINUTES = 20.0   # GAMEPLAY: one complete island day in real minutes
STORY_START_MINUTE = 8 * 60 + 30
STORY_SHOP_OPEN = 9 * 60
STORY_SHOP_CLOSE = 18 * 60
STORY_WALKIN_REP_LOSS = 0.08    # ignored visitor leaves a small mark
STORY_ACCEPTED_REP_LOSS = 0.40  # accepted order missed by its deadline
STORY_CANCEL_REP_LOSS = 0.15    # smaller cost for cancelling before the deadline
STORY_MAX_VISIBLE_CLIENTS = 4
STORY_SAVE_INTERVAL = 4.0
# Commission scoring and payment. Kept here so balancing never requires
# touching the request or client code.
STORY_PASS_SCORE = 0.55
STORY_PAY_BASE = 16
STORY_PAY_DIFFICULTY = 12
STORY_SPEED_BONUS = 1.25
STORY_SPEED_WINDOW = 180.0       # GAMEPLAY: in-game minutes after accepting
STORY_REP_PAY_BASE = 0.70
STORY_REP_PAY_STEP = 0.12
STORY_FAIL_PAY_RATE = 0.10
STORY_FRESHNESS_DECAY = 0.60

# ============================================================
# Water biome tuning  (see world/water.py for the geometry that uses it)
# ============================================================
#  >>> TUNING CHEAT-SHEET <<<
#   RIVER_LANE      - smaller = rivers more often (one river per lane across x)
#   POND_CHANCE     - chance a meadow cell grows a pond  (0..1)
#   LAKE_CHANCE     - chance a meadow cell grows a wider lake
#   REGION          - size of each pond/lake cell (bigger = sparser water)
#   COAST_Z         - how far out (world-z) the sea starts
#   SEA_DEEP_DIST   - how fast the sea deepens past the beach
#   COAST_AMP       - how far the coastline bends in and out
#   lane_half(k)    - controls each river's width (in world/water.py)
COAST_Z       = 2600.0      # mean world-z where the beach begins
COAST_AMP     = 360.0       # how far the shoreline curves in / out
SEA_DEEP_DIST = 900.0       # how slowly the sea deepens (bigger = gentler)
BEACH_W       = 190.0       # width of the sandy beach band

RIVER_LANE = 1700.0         # rivers are spaced about this far apart in x

REGION      = 2300.0        # size of one pond/lake cell
POND_CHANCE = 0.60          # how often a cell grows a pond
LAKE_CHANCE = 0.22          # how often a cell grows a wider lake

WADE_DEEP  = 0.40           # depth above this makes the cat swim
# graded water bands (depth 0..1) -> how the cat behaves and how wet it looks
SHALLOW_MAX = 0.22          # up to here: wading at the very edge
MEDIUM_MAX  = 0.55          # up to here: wading deeper / starting to swim
BOAT_SPEED = 165.0
BOAT_REACH = 150.0          # how close the cat must be to board a boat
USE_REACH  = 72.0           # how close to use a well or fountain

BRIDGE_SPACING = 1150.0     # one crossing roughly every this much z, per river
DECK_Z         = 78.0       # bridge depth (extent along z)
BRIDGE_MIN_HALF = 34.0      # rivers thinner than this get no bridge (hop/swim)
BRIDGE_OVERHANG = 30.0      # how far the deck reaches onto each bank
BRIDGE_ARCH    = 30.0       # world-height of the arch hump (cat rises by this)

# how grand the set-piece props are, relative to a cat (1.0 = cat-sized).
WELL_SCALE     = 2.0
FOUNTAIN_SCALE = 1.85

# Everything except the live screen-state names is safe to `import *`.
__all__ = [
    "DEBUG_SEED", "WORLD_SEED", "VIRTUAL_H", "FPS", "TITLE", "FOCAL", "MIN_D",
    "CAT_SPEED", "CAT_R", "COLLIDE_REACH", "RUN_MULT", "JUMP_V0", "JUMP_GRAV",
    "ATTACK_DUR", "CAT_DRAW_SCALE", "SOLID_R", "PLACED_R", "PROP_GROW", "CHUNK",
    "FAR_Z", "FADE_S_HI", "FADE_S_LO", "GRASS_MIN_S", "SMALL_DECO", "DECO_MIN_S",
    "DECO_HAZE_S", "GROUND_SPECKLE", "PROP_FADE_HI", "PROP_FADE_MAX",
    "SUN_BLOOM", "SUN_GLINT", "RAINBOW_ALPHA", "HORIZON_MIST", "MTN_HAZE",
    "VIGNETTE_STRENGTH", "VIGNETTE_WARMTH", "MEADOW_BRUSH", "MEADOW_DAPPLE_CHANCE",
    "GRASS_SWAY_TONE", "WATER_HAZE", "SHORE_FOAM", "WATER_GLINT", "WATER_SHEEN",
    "STORY_DAY_REAL_MINUTES", "STORY_START_MINUTE", "STORY_SHOP_OPEN",
    "STORY_SHOP_CLOSE", "STORY_WALKIN_REP_LOSS", "STORY_ACCEPTED_REP_LOSS", "STORY_CANCEL_REP_LOSS",
    "STORY_MAX_VISIBLE_CLIENTS", "STORY_SAVE_INTERVAL", "STORY_PASS_SCORE",
    "STORY_PAY_BASE", "STORY_PAY_DIFFICULTY", "STORY_SPEED_BONUS",
    "STORY_SPEED_WINDOW", "STORY_REP_PAY_BASE", "STORY_REP_PAY_STEP",
    "STORY_FAIL_PAY_RATE", "STORY_FRESHNESS_DECAY",
    "COAST_Z", "COAST_AMP", "SEA_DEEP_DIST", "BEACH_W", "RIVER_LANE", "REGION",
    "POND_CHANCE", "LAKE_CHANCE", "WADE_DEEP", "SHALLOW_MAX", "MEDIUM_MAX",
    "BOAT_SPEED", "BOAT_REACH", "USE_REACH", "BRIDGE_SPACING", "DECK_Z",
    "BRIDGE_MIN_HALF", "BRIDGE_OVERHANG", "BRIDGE_ARCH", "WELL_SCALE",
    "FOUNTAIN_SCALE",
]

# ============================================================
# Painted day / night cycle
# ============================================================
# ART: Creative mode uses a slower visual clock. Story follows its real shop
# clock. Night remains moonlit and readable rather than becoming black.
CREATIVE_DAY_REAL_MINUTES = 34.0
AURORA_CHANCE = 0.45             # ART: night one is always an aurora
MUSIC_LIGHT_RADIUS = 34          # ART: low-resolution glow radius for sprouts
GRAMOPHONE_LIGHT_RADIUS = 46     # ART: warm halo around records at night
