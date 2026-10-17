"""Every colour used by the game, grouped by what it paints.

Art-pass note: the ramps below were deliberately tuned as *families* rather than
isolated swatches.  Each surface (sky, meadow, water, mountains) carries a little
shared warmth from the same sun and a little shared cool from the same sky, so
the whole frame reads as one painted world instead of separate clip-art.  Values
stay soft and cozy on purpose - this is a storybook meadow, not a photo.
"""

# ============================================================
# Sky  - a deeper cornflower zenith melting into a warm peach horizon
# ============================================================
SKY_TOP = (122, 184, 236)        # a touch deeper/richer at the top of the dome
SKY_MID = (183, 217, 245)
SKY_HIGH = (150, 200, 240)        # NEW: a band between TOP and MID for a longer,
                                  # smoother gradient (less terracing up high)
SKY_HORIZON = (253, 224, 198)    # warm peach hem at the skyline
SKY_GLOWBAND = (255, 238, 214)   # NEW: faint warm lift just above the horizon

# The atmosphere colour distant things dissolve into.  Slightly lighter and a
# hair cooler than the meadow so far props/hills lift into a soft morning mist
# instead of muddying into the grass.
HAZE = (212, 223, 205)

# ============================================================
# Meadow greens  - a wider, richer near->far ramp for real depth
# ============================================================
GROUND_FAR = (202, 227, 169)     # airy, sunlit far grass near the haze
GROUND_MID = (147, 199, 127)
GROUND_NEAR = (104, 175, 100)
GROUND_DEEP = (82, 150, 89)      # deeper shadow green for richer contact shade

# Painterly meadow brushwork (used by the baked ground texture).  A warm sunlit
# tuft tone and a cool shaded tone, plus a soft dappled-light highlight.
GRASS_LIT  = (168, 212, 124)     # NEW: warm sun-struck grass dab
GRASS_DEEP = (96, 168, 104)      # NEW: cool grass-clump shadow dab
MEADOW_DAPPLE = (224, 240, 188)  # NEW: gentle sun-dapple highlight

# A faint sky-coloured light used for rim highlights so lit edges across the
# world agree on where the sun is.
SKYLIGHT = (236, 246, 236)       # NEW

# ============================================================
# Sun
# ============================================================
SUN_CORE = (255, 248, 214)
SUN_GLOW = (255, 232, 172)       # a warmer, more golden bloom
SUN_HALO = (255, 244, 206)       # NEW: pale outer halo for a soft wide bloom

# ============================================================
# Mountains  - layered aerial perspective (cool violet far, teal near)
# ============================================================
MTN_FAR = (189, 185, 222)
MTN_FAR_HI = (211, 207, 235)
MTN_NEAR = (145, 189, 184)
MTN_NEAR_HI = (181, 215, 204)
MTN_SHADE = (112, 154, 153)
SNOW = (243, 247, 253)
SNOW_SHADE = (210, 220, 238)     # NEW: soft blue underside so snow reads domed

CLOUD = (252, 250, 247)
CLOUD_HI = (255, 255, 255)
CLOUD_LO = (221, 220, 236)       # cool underside shadow
CLOUD_WARM = (255, 247, 236)     # NEW: faint warm sunlit tint on crowns


# ============================================================
# Water palettes (soft, slightly richer, to sit beside the greens)
# ============================================================
FW_SHALLOW = (158, 220, 210)
FW_MID     = (94, 182, 199)
FW_DEEP    = (56, 138, 179)
FW_DEEPEST = (42, 113, 160)
FW_GLINT   = (224, 248, 248)     # NEW: soft tinted sparkle (never stark white)

SEA_SHALLOW = (150, 212, 218)
SEA_MID     = (80, 164, 205)
SEA_DEEP    = (48, 122, 183)
SEA_DEEPEST = (36, 99, 164)
SEA_HORIZON = (172, 214, 224)    # NEW: pale band where the sea meets the sky

FOAM     = (239, 250, 252)
WET_SAND = (212, 195, 152)
DRY_SAND = (234, 222, 188)
SAND_LIT = (245, 236, 207)       # NEW: sunlit dry-sand highlight
WET_BANK = (80, 118, 106)


# ============================================================
# Boat woods
# ============================================================
BOAT_WOOD   = (176, 122, 74)
BOAT_WOOD_D = (126, 84, 50)
BOAT_WOOD_L = (210, 164, 108)
BOAT_INSIDE = (150, 106, 66)
BOAT_INSIDE_D = (118, 82, 50)
BOAT_RIM    = (200, 154, 100)
