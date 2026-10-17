"""Large authored component library for Bal's Sound Garden.

The original hand-written catalog remains the game's intimate core.  This module
adds the *Sound Atlas*: thousands of deterministic, deliberately constrained
musical building blocks assembled from authored instrument palettes, harmonic
sets, motif shapes, drum kits, ambience scenes and effect presets.

This is intentionally different from :mod:`procedural`:

* Atlas ids and recipes are stable release content, not seed rolls.
* Every family has an intentional pitch range, region, colour and mood.
* Loops are scale-locked authored motifs, and grooves use authored kit/pattern
  pairings rather than unconstrained random events.
* The Atlas is appended to the catalog but still has to be discovered in the
  world.  It is not granted to the player at startup.
"""

from __future__ import annotations


_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_ROOTS = _NOTE_NAMES
_QUALITIES = (
    ("major", "Major"),
    ("minor", "Minor"),
    ("maj7", "Maj7"),
    ("min7", "Min7"),
)

_SCALES = {
    "major": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10),
    "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "pentatonic": (0, 2, 4, 7, 9),
    "minor pentatonic": (0, 3, 5, 7, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11),
    "lydian": (0, 2, 4, 6, 7, 9, 11),
}

_REGIONS = ("meadow", "river", "orchard", "deepwood", "animal", "hidden", "rhythm")
_REGION_NAMES = {
    "meadow": "meadow",
    "river": "riverbank",
    "orchard": "chord grove",
    "deepwood": "deepwood",
    "animal": "animal corners",
    "hidden": "hidden clearings",
    "rhythm": "rhythm path",
}

# Roughly 3% / 20% / 45% / 32%.  This keeps only a welcoming slice close to
# spawn, while the majority of the Atlas stays genuinely deep in the world.
def _rarity(serial: int) -> str:
    n = serial % 100
    if n < 3:
        return "common"
    if n < 23:
        return "uncommon"
    if n < 68:
        return "rare"
    return "secret"


def _midi_name(midi: int) -> str:
    return _NOTE_NAMES[midi % 12] + str(midi // 12 - 1)


def _root_midi(root: str, octave: int) -> int:
    return 12 * (octave + 1) + _NOTE_NAMES.index(root)


def _slug(text: str) -> str:
    return (text.lower().replace("#", "s").replace(" ", "_")
            .replace("'", "").replace("-", "_"))


def _shade(color, delta):
    return tuple(max(0, min(255, int(v + delta))) for v in color)


# voice id, label, home region, colour, tags
_MELODY_INSTRUMENTS = (
    ("music_box", "Music Box", "meadow", (255, 214, 130), ("cozy", "delicate")),
    ("bell", "Soft Bell", "meadow", (250, 220, 146), ("bright", "clear")),
    ("glass", "Glass Harp", "hidden", (178, 226, 238), ("glassy", "bright")),
    ("celeste", "Celeste", "hidden", (194, 210, 250), ("dreamy", "bright")),
    ("toy_piano", "Toy Piano", "orchard", (246, 174, 144), ("playful", "warm")),
    ("pluck", "Wood Pluck", "orchard", (218, 178, 120), ("woody", "gentle")),
    ("moon_pluck", "Moon Pluck", "deepwood", (170, 164, 226), ("night", "soft")),
    ("soft_lead", "Soft Lead", "hidden", (188, 184, 242), ("smooth", "dreamy")),
    ("shimmer", "Shimmer", "hidden", (218, 204, 250), ("sparkling", "airy")),
    ("grand_piano", "Felt Piano", "orchard", (222, 183, 150), ("organic", "warm")),
    ("electric_piano", "Electric Piano", "orchard", (220, 170, 188), ("mellow", "soulful")),
    ("harp", "Harp", "river", (214, 202, 142), ("flowing", "delicate")),
    ("kalimba", "Kalimba", "animal", (232, 190, 118), ("earthy", "playful")),
    ("marimba", "Marimba", "rhythm", (202, 150, 104), ("woody", "percussive")),
    ("vibraphone", "Vibraphone", "river", (166, 204, 218), ("mellow", "floating")),
    ("organ", "Reed Organ", "deepwood", (164, 164, 184), ("vintage", "sustained")),
    ("flute", "Flute", "river", (174, 220, 194), ("airy", "gentle")),
    ("clarinet", "Clarinet", "deepwood", (150, 176, 154), ("woody", "round")),
    ("oboe", "Oboe", "deepwood", (166, 184, 132), ("reedy", "wistful")),
    ("strings", "Soft Strings", "orchard", (232, 160, 176), ("lush", "warm")),
    ("choir", "Humming Choir", "hidden", (210, 188, 228), ("human", "ethereal")),
    ("analog_pad", "Analog Pad", "hidden", (176, 176, 226), ("wide", "warm")),
    ("dream_pad", "Dream Pad", "hidden", (184, 202, 244), ("dreamy", "soft")),
    ("supersaw", "Sunrise Synth", "meadow", (244, 184, 126), ("wide", "bright")),
    ("fm_bell", "FM Bell", "hidden", (182, 222, 242), ("digital", "glassy")),
    ("chiptune", "Pocket Chip", "animal", (178, 218, 154), ("retro", "playful")),
    ("nylon_guitar", "Nylon Guitar", "orchard", (224, 180, 130), ("warm", "plucked")),
    ("koto", "Silk Koto", "river", (218, 160, 144), ("plucked", "elegant")),
    ("dulcimer", "Hammered Dulcimer", "meadow", (230, 196, 130), ("bright", "folk")),
    ("sitar", "Moon Sitar", "deepwood", (216, 166, 112), ("buzzing", "mystic")),
    ("steel_drum", "Steel Pan", "river", (136, 206, 218), ("sunny", "metallic")),
    ("reed", "Meadow Reed", "river", (164, 204, 142), ("reedy", "airy")),
    ("whistle", "Willow Whistle", "meadow", (178, 226, 176), ("airy", "clear")),
    ("brass", "Soft Brass", "orchard", (230, 182, 108), ("rounded", "bold")),
    ("muted_brass", "Muted Brass", "rhythm", (205, 164, 104), ("dry", "jazzy")),
    ("vox", "Vowel Voice", "hidden", (226, 178, 214), ("human", "soft")),
    ("synth_pluck", "Prism Pluck", "hidden", (188, 190, 246), ("digital", "plucked")),
    ("crystal_pad", "Crystal Pad", "hidden", (190, 218, 248), ("glassy", "sustained")),
    ("accordion", "Little Accordion", "animal", (218, 154, 144), ("folk", "reedy")),
)

_BASS_INSTRUMENTS = (
    ("warm_bass", "Warm Bass", "orchard", (192, 168, 116), ("warm", "round")),
    ("sub_bass", "Cloud Sub", "hidden", (142, 152, 194), ("deep", "soft")),
    ("synth_bass", "Velvet Synth Bass", "hidden", (172, 142, 196), ("electronic", "round")),
    ("acid_bass", "Moss Acid Bass", "deepwood", (146, 178, 112), ("squelchy", "electronic")),
    ("upright_bass", "Upright Bass", "orchard", (176, 138, 100), ("organic", "woody")),
    ("fm_bass", "FM Bass", "river", (126, 174, 196), ("digital", "punchy")),
    ("pluck_bass", "Plucked Bass", "rhythm", (190, 156, 104), ("plucked", "tight")),
    ("rubber_bass", "Rubber Bass", "animal", (178, 178, 112), ("bouncy", "playful")),
)

_CHORD_VOICES = tuple(v for v in _MELODY_INSTRUMENTS if v[0] in {
    "toy_piano", "warm_pad", "bell", "celeste", "glass", "pluck",
    "grand_piano", "electric_piano", "harp", "vibraphone", "organ",
    "strings", "choir", "analog_pad", "dream_pad", "crystal_pad",
})

_LOOP_VOICES = tuple(v for v in _MELODY_INSTRUMENTS if v[0] in {
    "music_box", "bell", "glass", "celeste", "toy_piano", "pluck",
    "moon_pluck", "soft_lead", "grand_piano", "electric_piano", "harp",
    "kalimba", "marimba", "vibraphone", "flute", "clarinet", "strings",
    "analog_pad", "dream_pad", "fm_bell", "chiptune", "nylon_guitar",
    "koto", "synth_pluck",
})

_DRUM_SOUNDS = (
    ("kick", "Soft Kick"), ("deep_kick", "Deep Kick"),
    ("punch_kick", "Punch Kick"), ("sub_kick", "Sub Kick"),
    ("snare", "Snare"), ("brush_snare", "Brush Snare"),
    ("rimshot", "Rimshot"), ("finger_snap", "Finger Snap"),
    ("clap", "Hand Clap"), ("hat", "Closed Hat"),
    ("open_hat", "Open Hat"), ("brush_hat", "Brush Hat"),
    ("shaker", "Pebble Shaker"), ("seed_shaker", "Seed Shaker"),
    ("tambourine", "Tambourine"), ("tick", "Tiny Tick"),
    ("bell_tick", "Bell Tick"), ("triangle", "Triangle"),
    ("ride", "Soft Ride"), ("crash", "Cloud Crash"),
    ("tom_low", "Low Tom"), ("tom_mid", "Mid Tom"),
    ("tom_high", "High Tom"), ("conga_low", "Low Conga"),
    ("conga_high", "High Conga"), ("bongo_low", "Low Bongo"),
    ("bongo_high", "High Bongo"), ("hand_drum", "Hand Drum"),
    ("frame_drum", "Frame Drum"), ("woodblock", "Woodblock"),
    ("clave", "Clave"), ("cowbell", "Cowbell"),
    ("metal_hit", "Metal Hit"), ("glitch_click", "Glitch Click"),
    ("noise_hit", "Noise Hit"), ("stomp", "Meadow Stomp"),
    ("water_drop", "Water Drop"), ("pebble", "Pebble Click"),
    ("log", "Hollow Log"), ("paw", "Paw Tap"),
    ("duck", "Duck Quack"), ("sheep_bell", "Sheep Bell"),
    ("frog_pop", "Frog Pop"), ("bark", "Bark Hit"),
)

_AMBIENCES = (
    ("wind", "Meadow Wind", "meadow", (184, 212, 188), ("airy",)),
    ("river", "River Current", "river", (120, 198, 218), ("watery",)),
    ("birds", "Morning Birds", "meadow", (198, 220, 154), ("nature", "bright")),
    ("crickets", "Night Crickets", "deepwood", (134, 162, 126), ("night", "nature")),
    ("purr", "Distant Purr", "animal", (224, 190, 154), ("cozy", "animal")),
    ("crackle", "Tiny Fire", "hidden", (232, 170, 116), ("warm", "cozy")),
    ("owl", "Owl Hollow", "deepwood", (142, 146, 196), ("night", "animal")),
    ("rain", "Soft Rain", "river", (138, 180, 208), ("rainy", "soft")),
    ("storm", "Far Storm", "hidden", (112, 124, 166), ("dark", "rainy")),
    ("ocean", "Distant Ocean", "river", (106, 178, 210), ("watery", "wide")),
    ("waterfall", "Hidden Waterfall", "river", (126, 204, 220), ("watery", "bright")),
    ("cave", "Cave Breath", "deepwood", (126, 138, 154), ("dark", "hollow")),
    ("night_forest", "Night Forest", "deepwood", (116, 146, 126), ("night", "nature")),
    ("leaves", "Rustling Leaves", "meadow", (154, 196, 126), ("nature", "airy")),
    ("vinyl", "Vinyl Room", "hidden", (172, 158, 146), ("vintage", "lofi")),
    ("tape", "Tape Hiss", "hidden", (160, 150, 142), ("vintage", "lofi")),
    ("city", "Distant City", "hidden", (146, 156, 174), ("urban", "wide")),
    ("train", "Faraway Train", "hidden", (142, 150, 158), ("travel", "industrial")),
    ("clock", "Quiet Clock", "orchard", (190, 170, 140), ("mechanical", "calm")),
    ("underwater", "Underwater Hush", "river", (100, 164, 192), ("watery", "muffled")),
    ("snow", "Falling Snow", "hidden", (206, 220, 232), ("cold", "soft")),
    ("bees", "Garden Bees", "animal", (226, 194, 104), ("nature", "buzzing")),
    ("distant_bells", "Distant Bells", "hidden", (196, 206, 236), ("bright", "far")),
    ("drone", "Warm Drone", "deepwood", (156, 154, 184), ("sustained", "dark")),
    ("fireplace", "Fireplace", "orchard", (230, 154, 104), ("warm", "cozy")),
    ("meadow_night", "Meadow at Night", "meadow", (132, 158, 158), ("night", "nature")),
    ("space", "Starlit Space", "hidden", (130, 136, 198), ("wide", "ethereal")),
    ("heartbeat", "Gentle Heartbeat", "animal", (210, 132, 142), ("human", "pulse")),
)

_EFFECT_PRESETS = {
    "reverb": (
        ("Small Room", {"amount": 0.22, "decay": 0.28}),
        ("Warm Room", {"amount": 0.34, "decay": 0.52}),
        ("Long Hall", {"amount": 0.48, "decay": 0.88}),
        ("Dream Hall", {"amount": 0.58, "decay": 1.15}),
    ),
    "delay": (
        ("Slap Echo", {"time": 0.10, "feedback": 0.18, "mix": 0.24}),
        ("Dotted Echo", {"time": 0.22, "feedback": 0.34, "mix": 0.32}),
        ("Long Echo", {"time": 0.36, "feedback": 0.42, "mix": 0.38}),
        ("Cloud Echo", {"time": 0.48, "feedback": 0.52, "mix": 0.42}),
    ),
    "lowpass": (
        ("Soft Blanket", {"cutoff": 1500}), ("Warm Blanket", {"cutoff": 950}),
        ("Deep Blanket", {"cutoff": 600}), ("Underwater", {"cutoff": 360}),
    ),
    "highpass": (
        ("Air Lift", {"cutoff": 500}), ("Thin Air", {"cutoff": 1100}),
        ("Telephone", {"cutoff": 1900}), ("Tiny Speaker", {"cutoff": 2800}),
    ),
    "tremolo": (
        ("Slow Pulse", {"rate": 2.0, "depth": 0.34}),
        ("Lantern Pulse", {"rate": 4.0, "depth": 0.48}),
        ("Fast Flutter", {"rate": 7.0, "depth": 0.58}),
        ("Chopped Light", {"rate": 11.0, "depth": 0.75}),
    ),
    "bitcrush": (
        ("Soft Pixels", {"bits": 9, "down": 2}), ("Pocket Console", {"bits": 7, "down": 3}),
        ("Crushed Toy", {"bits": 5, "down": 4}), ("Tiny Robot", {"bits": 4, "down": 6}),
    ),
    "chorus": (
        ("Gentle Chorus", {"depth": 0.003, "rate": 0.45, "mix": 0.24}),
        ("Wide Chorus", {"depth": 0.006, "rate": 0.7, "mix": 0.34}),
        ("Dream Chorus", {"depth": 0.009, "rate": 0.3, "mix": 0.42}),
        ("Wavy Chorus", {"depth": 0.012, "rate": 1.1, "mix": 0.38}),
    ),
    "flanger": (
        ("Soft Flange", {"depth": 0.002, "rate": 0.25, "mix": 0.24, "base": 0.002}),
        ("Silver Flange", {"depth": 0.004, "rate": 0.5, "mix": 0.34, "base": 0.003}),
        ("Jet Flange", {"depth": 0.006, "rate": 0.8, "mix": 0.44, "base": 0.002}),
        ("Slow Sweep", {"depth": 0.008, "rate": 0.12, "mix": 0.40, "base": 0.004}),
    ),
    "phaser": (
        ("Moss Phaser", {"rate": 0.25, "depth": 0.25}),
        ("Moon Phaser", {"rate": 0.45, "depth": 0.38}),
        ("River Phaser", {"rate": 0.8, "depth": 0.46}),
        ("Fast Phaser", {"rate": 1.5, "depth": 0.54}),
    ),
    "overdrive": (
        ("Warm Drive", {"drive": 1.6, "mix": 0.25}),
        ("Amber Drive", {"drive": 2.4, "mix": 0.38}),
        ("Moss Drive", {"drive": 3.2, "mix": 0.52}),
        ("Hot Drive", {"drive": 4.4, "mix": 0.62}),
    ),
    "ring_mod": (
        ("Low Ring", {"freq": 24.0, "mix": 0.25}), ("Bell Ring", {"freq": 57.0, "mix": 0.34}),
        ("Robot Ring", {"freq": 93.0, "mix": 0.46}), ("Glass Ring", {"freq": 151.0, "mix": 0.55}),
    ),
    "vibrato": (
        ("Gentle Vibrato", {"rate": 4.2, "depth": 0.0015}),
        ("Singing Vibrato", {"rate": 5.3, "depth": 0.0025}),
        ("Wide Vibrato", {"rate": 5.8, "depth": 0.004}),
        ("Wobble", {"rate": 7.0, "depth": 0.006}),
    ),
    "wow_flutter": (
        ("Old Tape", {"rate": 0.35, "depth": 0.003}),
        ("Loose Tape", {"rate": 0.6, "depth": 0.005}),
        ("Worn Cassette", {"rate": 0.9, "depth": 0.007}),
        ("Dream Tape", {"rate": 0.22, "depth": 0.009}),
    ),
    "gate": (
        ("Soft Gate", {"threshold": 0.03, "floor": 0.35}),
        ("Clean Gate", {"threshold": 0.07, "floor": 0.16}),
        ("Hard Gate", {"threshold": 0.12, "floor": 0.04}),
        ("Chop Gate", {"threshold": 0.20, "floor": 0.0}),
    ),
    "compressor": (
        ("Glue", {"threshold": 0.55, "ratio": 2.0}),
        ("Evening", {"threshold": 0.42, "ratio": 3.0}),
        ("Tight", {"threshold": 0.30, "ratio": 4.5}),
        ("Pressed", {"threshold": 0.20, "ratio": 7.0}),
    ),
    "resonator": (
        ("Wood Resonator", {"freq": 180.0, "decay": 0.25, "mix": 0.22}),
        ("Glass Resonator", {"freq": 440.0, "decay": 0.35, "mix": 0.28}),
        ("Bell Resonator", {"freq": 660.0, "decay": 0.42, "mix": 0.34}),
        ("Tiny Resonator", {"freq": 980.0, "decay": 0.22, "mix": 0.30}),
    ),
    "lo_fi": (
        ("Dusty", {"bits": 10, "down": 2, "cutoff": 5000}),
        ("Bedroom", {"bits": 8, "down": 3, "cutoff": 3600}),
        ("Pocket Radio", {"bits": 7, "down": 4, "cutoff": 2400}),
        ("Broken Toy", {"bits": 5, "down": 6, "cutoff": 1600}),
    ),
}

# degree, step, duration.  Degree values walk the selected scale and may exceed
# one octave; negative values descend below the root.
_MOTIFS = (
    ("Morning Steps", ((0, 0, 2), (1, 2, 2), (2, 4, 2), (4, 6, 2), (2, 8, 2), (1, 10, 2), (0, 12, 4))),
    ("Falling Leaves", ((7, 0, 2), (5, 2, 2), (4, 4, 2), (2, 6, 2), (1, 8, 2), (0, 10, 4))),
    ("Lantern Arp", ((0, 0, 2), (2, 2, 2), (4, 4, 2), (7, 6, 2), (4, 8, 2), (2, 10, 2), (0, 12, 4))),
    ("River Turn", ((0, 0, 1), (2, 1, 1), (4, 2, 2), (3, 4, 2), (1, 6, 2), (2, 8, 2), (5, 10, 2), (4, 12, 4))),
    ("Tiny Waltz", ((0, 0, 2), (4, 3, 1), (2, 5, 1), (0, 8, 2), (5, 11, 1), (4, 13, 2))),
    ("Moon Question", ((0, 0, 2), (1, 3, 1), (4, 5, 3), (2, 10, 2), (1, 12, 1), (0, 14, 2))),
    ("Sun Answer", ((4, 0, 2), (5, 2, 2), (7, 4, 4), (4, 9, 1), (2, 11, 1), (4, 12, 4))),
    ("Clover Bounce", ((0, 0, 1), (2, 2, 1), (0, 4, 1), (4, 6, 1), (2, 8, 1), (5, 10, 1), (4, 12, 1), (2, 14, 2))),
    ("Quiet Orbit", ((0, 0, 4), (4, 4, 4), (2, 8, 4), (5, 12, 4))),
    ("Pebble Run", ((0, 0, 1), (1, 1, 1), (2, 2, 1), (3, 3, 1), (4, 4, 1), (5, 5, 1), (6, 6, 1), (7, 7, 1), (5, 9, 1), (4, 10, 1), (2, 12, 1), (0, 14, 2))),
    ("Moss Syncopation", ((0, 0, 2), (3, 3, 1), (2, 5, 2), (5, 8, 1), (4, 10, 2), (1, 13, 1), (0, 15, 1))),
    ("Dew Lullaby", ((0, 0, 3), (2, 4, 2), (1, 7, 2), (4, 10, 3), (2, 14, 2))),
    ("Fox Trot", ((0, 0, 1), (4, 2, 1), (2, 4, 1), (5, 6, 1), (4, 8, 1), (7, 10, 1), (5, 12, 1), (4, 14, 2))),
    ("Glass Cascade", ((7, 0, 1), (6, 1, 1), (5, 2, 1), (4, 3, 1), (3, 4, 1), (2, 5, 1), (1, 6, 1), (0, 7, 2), (2, 10, 1), (4, 12, 1), (7, 14, 2))),
    ("Meadow Call", ((0, 0, 2), (2, 2, 1), (4, 4, 3), (0, 9, 2), (3, 11, 1), (5, 13, 3))),
    ("Night Pulse", ((0, 0, 2), (0, 4, 2), (4, 8, 2), (4, 12, 2))),
)

_GROOVES = (
    ("Straight Walk", (("K", 0), ("H", 0), ("H", 2), ("S", 4), ("H", 4), ("H", 6))),
    ("Four Paws", (("K", 0), ("K", 2), ("S", 4), ("K", 6), ("H", 1), ("H", 3), ("H", 5), ("H", 7))),
    ("Soft Backbeat", (("K", 0), ("H", 0), ("H", 2), ("S", 4), ("H", 4), ("K", 6), ("H", 6))),
    ("River Shuffle", (("K", 0), ("H", 0), ("H", 3), ("S", 4), ("H", 5), ("P", 7))),
    ("Lantern Bounce", (("K", 0), ("P", 2), ("S", 4), ("K", 5), ("P", 6), ("H", 1), ("H", 3), ("H", 7))),
    ("Tiny March", (("K", 0), ("S", 2), ("K", 4), ("S", 6), ("H", 1), ("H", 3), ("H", 5), ("H", 7))),
    ("Broken Clock", (("K", 0), ("P", 1), ("H", 3), ("S", 4), ("P", 6), ("H", 7))),
    ("Clover Hop", (("K", 0), ("P", 3), ("S", 4), ("P", 6), ("H", 2), ("H", 7))),
    ("Night Drive", (("K", 0), ("K", 3), ("S", 4), ("K", 7), ("H", 0), ("H", 2), ("H", 4), ("H", 6))),
    ("Pebble Funk", (("K", 0), ("P", 2), ("S", 4), ("P", 5), ("K", 6), ("H", 1), ("H", 3), ("H", 7))),
    ("Slow Heart", (("K", 0), ("S", 4), ("P", 6))),
    ("Busy Garden", (("K", 0), ("H", 0), ("P", 1), ("H", 2), ("P", 3), ("S", 4), ("H", 4), ("P", 5), ("H", 6), ("P", 7))),
    ("Hollow Step", (("K", 0), ("P", 2), ("S", 4), ("P", 7))),
    ("Sunset Swing", (("K", 0), ("H", 0), ("H", 3), ("S", 4), ("H", 5), ("K", 6), ("P", 7))),
)

_DRUM_KITS = (
    ("Meadow", {"K": "kick", "S": "brush_snare", "H": "shaker", "P": "pebble"}),
    ("Deep", {"K": "deep_kick", "S": "snare", "H": "hat", "P": "tom_low"}),
    ("Pocket", {"K": "punch_kick", "S": "clap", "H": "glitch_click", "P": "finger_snap"}),
    ("River", {"K": "sub_kick", "S": "water_drop", "H": "seed_shaker", "P": "woodblock"}),
    ("Woodland", {"K": "stomp", "S": "log", "H": "seed_shaker", "P": "clave"}),
    ("Handmade", {"K": "frame_drum", "S": "hand_drum", "H": "tambourine", "P": "bongo_high"}),
    ("Conga", {"K": "conga_low", "S": "conga_high", "H": "shaker", "P": "cowbell"}),
    ("Tom", {"K": "tom_low", "S": "tom_mid", "H": "brush_hat", "P": "tom_high"}),
    ("Silver", {"K": "punch_kick", "S": "rimshot", "H": "ride", "P": "triangle"}),
    ("Animal", {"K": "paw", "S": "frog_pop", "H": "sheep_bell", "P": "duck"}),
    ("Firelight", {"K": "deep_kick", "S": "clap", "H": "tambourine", "P": "metal_hit"}),
    ("Cloud", {"K": "sub_kick", "S": "noise_hit", "H": "brush_hat", "P": "bell_tick"}),
)


def install(add):
    """Append the Sound Atlas to ``catalog`` through its private ``_add`` hook."""
    serial = 0

    def emit(**kw):
        nonlocal serial
        kw.setdefault("rarity", _rarity(serial))
        kw.setdefault("starter", False)
        kw.setdefault("reward", False)
        kw.setdefault("curated", True)
        kw.setdefault("pack", "sound_atlas")
        serial += 1
        add(**kw)

    # Full two-octave chromatic palettes.  Each voice has a practical range,
    # but all entries still use the same compact note component format.
    for vi, (voice, label, region, color, tags) in enumerate(_MELODY_INSTRUMENTS):
        base_oct = 3 if voice in {"organ", "strings", "brass", "muted_brass", "accordion"} else 4
        for semitone in range(24):
            note = _midi_name(_root_midi("C", base_oct) + semitone)
            emit(id="atlas.note.%s.%s" % (voice, _slug(note)),
                 name="%s %s" % (label, note), type="note", voice=voice,
                 notes=[note], track="melody", region=region, icon="note",
                 color=_shade(color, (semitone % 6) * 2 - 5),
                 tags=list(tags) + ["melody", "chromatic"],
                 collection="Instrument Notes",
                 desc="A curated %s tone at %s, hidden around the %s."
                      % (label.lower(), note, _REGION_NAMES[region]))

    for voice, label, region, color, tags in _BASS_INSTRUMENTS:
        for semitone in range(24):
            note = _midi_name(_root_midi("C", 2) + semitone)
            emit(id="atlas.bass.%s.%s" % (voice, _slug(note)),
                 name="%s %s" % (label, note), type="note", voice=voice,
                 notes=[note], track="bass", region=region, icon="stone",
                 color=_shade(color, (semitone % 5) * 2 - 4), dur=1.25,
                 tags=list(tags) + ["bass", "low"], collection="Bass Notes",
                 desc="A designed %s note at %s for building bass lines."
                      % (label.lower(), note))

    # Four useful harmonic colours on every chromatic root for 16 voices.
    for voice, label, region, color, tags in _CHORD_VOICES:
        octave = 3 if voice in {"organ", "strings", "analog_pad", "dream_pad", "crystal_pad"} else 4
        for root in _ROOTS:
            for quality, pretty in _QUALITIES:
                emit(id="atlas.chord.%s.%s.%s" % (voice, _slug(root), quality),
                     name="%s %s %s" % (label, root, pretty), type="chord",
                     voice=voice, root=root, quality=quality, octave=octave,
                     track="chords", region=region, icon="cluster", color=color,
                     tags=list(tags) + ["harmony", quality], collection="Chord Book",
                     desc="A curated %s %s %s voicing."
                          % (label.lower(), root, pretty))

    # Authored scale-locked loops.  Every instrument receives all motif shapes,
    # but key and scale rotate deliberately so the library spans many moods.
    scale_names = tuple(_SCALES)
    for vi, (voice, label, region, color, tags) in enumerate(_LOOP_VOICES):
        for mi, (motif_name, motif) in enumerate(_MOTIFS):
            root = _ROOTS[(vi * 5 + mi * 3) % len(_ROOTS)]
            scale_name = scale_names[(vi + mi) % len(scale_names)]
            degrees = _SCALES[scale_name]
            base = _root_midi(root, 4 if voice not in {"strings", "analog_pad", "dream_pad"} else 3)
            pattern = []
            for degree, step, dur in motif:
                octaves, idx = divmod(degree, len(degrees))
                midi = base + degrees[idx] + 12 * octaves
                pattern.append((_midi_name(midi), step, dur))
            effects = []
            if mi % 5 == 1:
                effects = [("delay", {"time": 0.18, "feedback": 0.24, "mix": 0.22})]
            elif mi % 5 == 2:
                effects = [("reverb", {"amount": 0.24, "decay": 0.48})]
            elif mi % 5 == 3:
                effects = [("chorus", {"depth": 0.004, "rate": 0.5, "mix": 0.22})]
            emit(id="atlas.loop.%s.%02d" % (voice, mi),
                 name="%s - %s" % (label, motif_name), type="loop", voice=voice,
                 pattern=pattern, length_steps=16, track="loops", region=region,
                 icon="cassette", color=color, effects=effects,
                 tags=list(tags) + ["loop", scale_name, root], collection="Motif Atlas",
                 desc="A designed 16-step %s phrase in %s %s."
                      % (motif_name.lower(), root, scale_name))

    # One-shots in two intentionally different treatments.
    for di, (drum_id, label) in enumerate(_DRUM_SOUNDS):
        region = "animal" if drum_id in {"paw", "duck", "sheep_bell", "frog_pop", "bark", "water_drop"} else "rhythm"
        base_color = (206, 174, 126) if region == "rhythm" else (224, 194, 126)
        for variant in range(2):
            effects = [] if variant == 0 else [("reverb", {"amount": 0.16, "decay": 0.25})]
            suffix = "Dry" if variant == 0 else "Room"
            emit(id="atlas.drum.%s.%s" % (drum_id, suffix.lower()),
                 name="%s - %s" % (label, suffix), type="drum", drum=drum_id,
                 track="drums", region=region, icon="stone", color=_shade(base_color, variant * 12),
                 effects=effects, tags=["percussion", suffix.lower()],
                 collection="Percussion Cabinet",
                 desc="A curated %s hit with a %s finish." % (label.lower(), suffix.lower()))

    # Authored groove shape X authored kit.  This produces variety without
    # sacrificing rhythmic readability.
    for ki, (kit_name, kit) in enumerate(_DRUM_KITS):
        for gi, (groove_name, symbols) in enumerate(_GROOVES):
            pattern = [(kit[symbol], step) for symbol, step in symbols]
            emit(id="atlas.rhythm.%s.%02d" % (_slug(kit_name), gi),
                 name="%s Kit - %s" % (kit_name, groove_name), type="rhythm",
                 pattern=pattern, length_steps=8, track="rhythms", region="rhythm",
                 icon="rune", color=_shade((226, 190, 116), (ki % 5) * 5 - 10),
                 tags=["groove", _slug(kit_name), _slug(groove_name)],
                 collection="Groove Almanac",
                 desc="The %s kit playing the authored %s groove."
                      % (kit_name.lower(), groove_name.lower()))

    # Four treatments per scene: natural, muffled, spacious and worn.
    ambience_treatments = (
        ("Natural", []),
        ("Muffled", [("lowpass", {"cutoff": 900})]),
        ("Spacious", [("reverb", {"amount": 0.38, "decay": 0.8})]),
        ("Worn", [("lo_fi", {"bits": 9, "down": 2, "cutoff": 4200})]),
    )
    for amb, label, region, color, tags in _AMBIENCES:
        for ti, (treatment, effects) in enumerate(ambience_treatments):
            emit(id="atlas.amb.%s.%s" % (amb, treatment.lower()),
                 name="%s - %s" % (label, treatment), type="ambience", amb=amb,
                 length_steps=16, dur=5.0 + (ti % 2), track="ambience", region=region,
                 icon="orb", color=_shade(color, ti * 4 - 6), effects=effects,
                 tags=list(tags) + ["ambience", treatment.lower()],
                 collection="Field Recordings",
                 desc="A generated-but-authored %s ambience in its %s treatment."
                      % (label.lower(), treatment.lower()))

    for fx, presets in _EFFECT_PRESETS.items():
        for pi, (label, params) in enumerate(presets):
            emit(id="atlas.fx.%s.%02d" % (fx, pi), name=label, type="effect",
                 fx=fx, fx_params=params, track="effect", region="hidden",
                 icon="crystal", color=_shade((210, 170, 236), pi * 6 - 8),
                 tags=["effect", fx], collection="Effect Crystals",
                 desc="A curated %s effect preset for shaping any track." % fx.replace("_", " "))

    return serial
