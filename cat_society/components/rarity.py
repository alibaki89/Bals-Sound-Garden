"""The single source of truth for how common each rarity actually is.

Rarity is not a cosmetic label.  The same table drives:

* procedural generation -- a generated component rolls its rarity from these
  weights, so a "Rare" generated find really is generated ~11% of the time and
  a "Secret" one ~3%.
* curated placement -- a curated component of a given rarity scatters into the
  world within that rarity's distance band, so rarer designed components sit
  genuinely farther from spawn and are harder to stumble on.

The journal and the discovery card read the rarity straight off the component,
so what they show is the real value this table produced.
"""

ORDER = ["common", "uncommon", "rare", "secret"]

# weight  = relative chance this rarity is generated (probabilities below)
# band    = (min, max) distance from spawn, in *thousands* of world units, that
#           a curated component of this rarity is scattered into
TABLE = {
    "common":   {"weight": 60, "band": (1.0, 6.0),  "label": "Common"},
    "uncommon": {"weight": 26, "band": (4.5, 11.0), "label": "Uncommon"},
    "rare":     {"weight": 11, "band": (9.0, 18.0), "label": "Rare"},
    "secret":   {"weight": 3,  "band": (15.0, 30.0), "label": "Secret"},
}

GEN_WEIGHTS = [(r, TABLE[r]["weight"]) for r in ORDER]

_TOTAL = float(sum(TABLE[r]["weight"] for r in ORDER))


def label(rarity):
    return TABLE.get(rarity, TABLE["common"])["label"]


def percent(rarity):
    """Roughly how often this rarity occurs, as a percent (for display)."""
    return 100.0 * TABLE.get(rarity, TABLE["common"])["weight"] / _TOTAL


def band_units(rarity):
    """Placement distance band for a curated component, in world units."""
    lo, hi = TABLE.get(rarity, TABLE["common"])["band"]
    return lo * 1000.0, hi * 1000.0


def color(rarity):
    return {"common": (150, 170, 150), "uncommon": (110, 180, 150),
            "rare": (120, 160, 235), "secret": (210, 150, 235)}.get(
                rarity, (150, 170, 150))
