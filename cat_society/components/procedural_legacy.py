"""Infinite, musically-coherent procedural components ("ComponentDNA").

The curated catalog is the hand-made backbone.  This module adds an endless
supply of *generated* components so discovery never runs out -- but they are not
random noise.  Each one is built from rules:

* a fixed palette of supported synth voices / drums / effects / ambience kinds
  (so nothing is ever silent or broken),
* pitches locked to a real scale and root (so notes, chords and loops are
  musical),
* bounded, on-grid rhythm/loop patterns (so they are rhythmically coherent),
* a proper generated name, rarity, icon, colour and world-origin tag.

The whole component is a pure function of one integer seed, and its id encodes
that seed (``"proc.<seed>"``).  That means a generated component can be rebuilt
from its id alone, so the collection only has to store ids and everything
(preview, sequencer, export) reconstructs the identical component.
"""

import random

from . import rarity as _rarity

# ---------------------------------------------------------------------------
# Supported palettes  (must stay a subset of what synth.py can render)
# ---------------------------------------------------------------------------
_MELODIC = [
    "music_box", "bell", "glass", "celeste", "toy_piano", "pluck",
    "moon_pluck", "soft_lead", "grand_piano", "electric_piano", "harp",
    "kalimba", "marimba", "vibraphone", "organ", "flute", "clarinet",
    "oboe", "strings", "choir", "analog_pad", "dream_pad", "supersaw",
    "fm_bell", "chiptune", "nylon_guitar", "koto", "dulcimer", "sitar",
    "steel_drum", "reed", "whistle", "brass", "muted_brass", "vox",
    "synth_pluck", "crystal_pad", "accordion",
]
_BRIGHT = ["glass", "celeste", "shimmer", "bell", "fm_bell", "vibraphone",
           "steel_drum", "dulcimer"]
_CHORD_VOICES = ["toy_piano", "warm_pad", "bell", "celeste", "glass", "pluck",
                 "grand_piano", "electric_piano", "harp", "vibraphone", "organ",
                 "strings", "choir", "analog_pad", "dream_pad", "crystal_pad"]
_BASS_VOICES = ["warm_bass", "sub_bass", "synth_bass", "acid_bass",
                "upright_bass", "fm_bass", "pluck_bass", "rubber_bass"]
_ANIMAL = ["meow", "purr", "croak", "quack", "hoot", "chirp"]
_DRUMS = ["kick", "deep_kick", "punch_kick", "sub_kick", "snare",
          "brush_snare", "rimshot", "finger_snap", "hat", "open_hat",
          "brush_hat", "shaker", "seed_shaker", "tambourine", "pebble",
          "log", "clap", "tick", "bell_tick", "triangle", "ride", "crash",
          "tom_low", "tom_mid", "tom_high", "conga_low", "conga_high",
          "bongo_low", "bongo_high", "hand_drum", "frame_drum", "woodblock",
          "clave", "cowbell", "metal_hit", "glitch_click", "noise_hit",
          "stomp", "water_drop", "paw", "duck", "sheep_bell", "frog_pop",
          "bark"]
_KICKS = ["kick", "deep_kick", "punch_kick", "sub_kick", "stomp"]
_SNARES = ["snare", "brush_snare", "clap", "rimshot", "finger_snap",
           "hand_drum"]
_HATS = ["hat", "open_hat", "brush_hat", "shaker", "seed_shaker",
         "tambourine", "tick", "pebble", "ride"]
_PERC = ["log", "bell_tick", "triangle", "tom_low", "tom_mid", "tom_high",
         "conga_low", "conga_high", "bongo_low", "bongo_high", "woodblock",
         "clave", "cowbell", "metal_hit", "glitch_click", "water_drop",
         "paw", "frog_pop", "duck", "sheep_bell", "bark"]
_AMB = ["wind", "river", "birds", "crickets", "purr", "crackle", "owl",
        "rain", "storm", "ocean", "waterfall", "cave", "night_forest",
        "leaves", "vinyl", "tape", "city", "train", "clock", "underwater",
        "snow", "bees", "distant_bells", "drone", "fireplace",
        "meadow_night", "space", "heartbeat"]
_QUALITIES = ["major", "minor", "maj7", "min7", "sus2", "sus4", "add9"]
_QUALITY_PRETTY = {"major": "Major", "minor": "Minor", "maj7": "Maj7",
                   "min7": "Min7", "sus2": "Sus2", "sus4": "Sus4",
                   "add9": "add9"}

_SCALES = {
    "major":  [0, 2, 4, 5, 7, 9, 11],
    "minor":  [0, 2, 3, 5, 7, 8, 10],
    "penta":  [0, 2, 4, 7, 9],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "minor_penta": [0, 3, 5, 7, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
}
_ROOTS = ["C", "D", "E", "F", "G", "A", "B"]
_ROOT_SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# word banks for nice generated names
_ADJ = ["Glass", "Moss", "Velvet", "Moonlit", "Misty", "Golden", "Amber",
        "Hollow", "Dream", "Frost", "Dewy", "Willow", "Cloud", "Ember",
        "Twilight", "Meadow", "River", "Forest", "Silver", "Quiet", "Soft",
        "Bright", "Tiny", "Pebble", "Lunar", "Honey", "Maple", "Cozy"]
_NOUN = {
    "note":     ["Note", "Tone", "Chime", "Drop", "Spark"],
    "chord":    ["Chord", "Harmony", "Pad", "Triad", "Bloom"],
    "loop":     ["Loop", "Arp", "Motif", "Phrase", "Waltz", "Lullaby", "Run"],
    "rhythm":   ["Rhythm", "Beat", "Shuffle", "Groove", "Pulse", "Step"],
    "ambience": ["Drone", "Bed", "Air", "Haze", "Mist", "Texture"],
    "effect":   ["Echo", "Delay", "Filter", "Veil", "Shimmer", "Bloom"],
}
_ORIGINS = ["Meadow", "Riverside", "Orchard", "Deepwood", "Glade", "Hollow",
            "Clearing", "Hilltop"]

_TINT = {"note": (255, 224, 150), "chord": (255, 176, 156),
         "bass": (210, 196, 150), "drum": (214, 188, 150),
         "rhythm": (232, 200, 130), "loop": (176, 214, 235),
         "ambience": (196, 206, 235), "effect": (214, 176, 236)}

_TYPE_WEIGHTS = ([("note", 30), ("chord", 18), ("loop", 22), ("rhythm", 14),
                  ("ambience", 10), ("effect", 6)])
_RARITY_WEIGHTS = _rarity.GEN_WEIGHTS


def is_proc(cid):
    return isinstance(cid, str) and cid.startswith("proc.")


def from_id(cid):
    """Rebuild a generated component from its id (``proc.<seed>``)."""
    try:
        seed = int(cid.split(".", 1)[1])
    except (ValueError, IndexError):
        return None
    return generate(seed)


def _pick(rng, weighted):
    total = sum(w for _, w in weighted)
    r = rng.uniform(0, total)
    upto = 0
    for item, w in weighted:
        upto += w
        if r <= upto:
            return item
    return weighted[-1][0]


def _midi_name(m):
    return _NOTE_NAMES[m % 12] + str(m // 12 - 1)


def _scale_midis(root, octave, scale, span=2):
    base = _ROOT_SEMI[root] + (octave + 1) * 12
    degs = _SCALES[scale]
    out = []
    for o in range(span + 1):
        for d in degs:
            out.append(base + d + 12 * o)
    return out


def generate(seed):
    """A musically-coherent component, deterministic from ``seed``."""
    rng = random.Random(seed * 2654435761 & 0xFFFFFFFF)
    typ = _pick(rng, _TYPE_WEIGHTS)
    rarity = _pick(rng, _RARITY_WEIGHTS)
    origin = rng.choice(_ORIGINS)
    adj = rng.choice(_ADJ)
    cid = "proc.%d" % seed

    def base(**kw):
        kw.setdefault("id", cid)
        kw.setdefault("rarity", rarity)
        kw.setdefault("proc", True)
        kw.setdefault("origin", origin)
        kw.setdefault("color", _TINT.get(kw.get("type"), (255, 214, 130)))
        return kw

    if typ == "note":
        animal = rng.random() < 0.16
        if animal:
            voice = rng.choice(_ANIMAL)
            icon = {"meow": "paw", "purr": "paw", "chirp": "feather",
                    "hoot": "moon", "croak": "droplet", "quack": "droplet"}[voice]
        else:
            voice = rng.choice(_MELODIC)
            icon = "note"
        scale = rng.choice(list(_SCALES))
        root = rng.choice(_ROOTS)
        octave = rng.choice([4, 4, 5, 3])
        midis = _scale_midis(root, octave, scale, span=1)
        note = _midi_name(rng.choice(midis))
        low = voice in ("warm_bass",) or note.endswith("2") or note.endswith("3")
        track = "bass" if (low and animal is False and rng.random() < 0.5) else "melody"
        if track == "bass":
            voice = rng.choice(_BASS_VOICES)
            note = _midi_name(_ROOT_SEMI[root] + (rng.choice([2, 3]) + 1) * 12)
        name = "%s %s %s" % (adj, rng.choice(_NOUN["note"]), note)
        return base(name=name, type="note", voice=voice, notes=[note],
                    track=track, icon=icon,
                    desc="A %s %s note (%s)." % (adj.lower(),
                         voice.replace("_", " "), note))

    if typ == "chord":
        voice = rng.choice(_CHORD_VOICES)
        root = rng.choice(_ROOTS)
        quality = rng.choice(_QUALITIES)
        octave = rng.choice([4, 4, 5])
        name = "%s %s %s" % (adj, root, _QUALITY_PRETTY[quality])
        return base(name=name, type="chord", voice=voice, root=root,
                    quality=quality, octave=octave, track="chords", icon="cluster",
                    desc="A %s %s %s chord." % (adj.lower(), root,
                         _QUALITY_PRETTY[quality]))

    if typ == "loop":
        voice = rng.choice(_MELODIC)
        scale = rng.choice(list(_SCALES))
        root = rng.choice(_ROOTS)
        octave = rng.choice([4, 5])
        midis = _scale_midis(root, octave, scale, span=2)
        idx = len(midis) // 3
        pattern = []
        step = 0
        length = rng.choice([12, 16, 16])
        while step < length - 1:
            idx = max(0, min(len(midis) - 1, idx + rng.choice([-2, -1, -1, 0, 1, 1, 2])))
            dur = rng.choice([1, 2, 2])
            pattern.append((_midi_name(midis[idx]), step, dur))
            step += rng.choice([1, 2, 2])
        noun = rng.choice(_NOUN["loop"])
        name = "%s %s %02d" % (adj, noun, seed % 100)
        comp = base(name=name, type="loop", voice=voice, pattern=pattern,
                    length_steps=length, track="loops", icon="cassette",
                    desc="A %s %s phrase in %s %s." % (adj.lower(), noun.lower(),
                         root, scale))
        if rng.random() < 0.3:
            comp["effects"] = [("delay", {"time": 0.2, "mix": 0.28})]
        return comp

    if typ == "rhythm":
        length = 8
        pattern = []
        pattern.append((rng.choice(_KICKS), 0))
        if rng.random() < 0.6:
            pattern.append((rng.choice(_KICKS), 4))
        pattern.append((rng.choice(_SNARES), 4))
        hat = rng.choice(_HATS)
        for s in range(0, 8, rng.choice([1, 2, 2])):
            if rng.random() < 0.7:
                pattern.append((hat, s))
        if rng.random() < 0.4:
            pattern.append((rng.choice(_PERC), rng.choice([2, 6])))
        noun = rng.choice(_NOUN["rhythm"])
        name = "%s %s %02d" % (adj, noun, seed % 100)
        icon = "paw" if any(p[0] in ("paw", "bark") for p in pattern) else "stone"
        return base(name=name, type="rhythm", pattern=pattern, length_steps=length,
                    track="rhythms", icon=icon,
                    desc="A %s %s groove." % (adj.lower(), noun.lower()))

    if typ == "ambience":
        amb = rng.choice(_AMB)
        icon = {"river": "droplet", "wind": "wisp", "birds": "feather",
                "owl": "moon", "purr": "paw"}.get(amb, "orb")
        noun = rng.choice(_NOUN["ambience"])
        name = "%s %s %02d" % (adj, noun, seed % 100)
        comp = base(name=name, type="ambience", amb=amb, length_steps=16,
                    dur=rng.choice([4.0, 4.0, 5.0]), track="ambience", icon=icon,
                    desc="A %s %s bed." % (adj.lower(), noun.lower()))
        if rng.random() < 0.35:
            cut = rng.choice([500, 700, 900])
            comp["effects"] = [("lowpass", {"cutoff": cut})]
        return comp

    # effect
    fx, params, icon = _rand_effect(rng)
    noun = rng.choice(_NOUN["effect"])
    name = "%s %s" % (adj, noun)
    return base(name=name, type="effect", fx=fx, fx_params=params, track="effect",
                icon=icon, desc="A %s %s effect for a track." % (adj.lower(),
                     noun.lower()))


def _rand_effect(rng):
    kind = rng.choice(["reverb", "delay", "lowpass", "highpass", "tremolo",
                       "bitcrush", "ripple_delay", "chorus", "flanger",
                       "phaser", "overdrive", "ring_mod", "vibrato",
                       "wow_flutter", "gate", "compressor", "resonator",
                       "lo_fi"])
    if kind == "reverb":
        return "reverb", {"amount": round(rng.uniform(0.25, 0.58), 2),
                          "decay": round(rng.uniform(0.35, 1.05), 2)}, "ring"
    if kind == "delay":
        return "delay", {"time": round(rng.uniform(0.08, 0.42), 2),
                         "feedback": round(rng.uniform(0.15, 0.5), 2),
                         "mix": round(rng.uniform(0.2, 0.42), 2)}, "ring"
    if kind == "ripple_delay":
        return "ripple_delay", {"time": round(rng.uniform(0.1, 0.2), 2),
                                "mix": round(rng.uniform(0.3, 0.45), 2)}, "ring"
    if kind == "lowpass":
        return "lowpass", {"cutoff": rng.choice([360, 500, 700, 900, 1200, 1600])}, "crystal"
    if kind == "highpass":
        return "highpass", {"cutoff": rng.choice([500, 900, 1400, 2000, 2800])}, "crystal"
    if kind == "tremolo":
        return "tremolo", {"rate": round(rng.uniform(2.0, 11.0), 1),
                           "depth": round(rng.uniform(0.3, 0.78), 2)}, "crystal"
    if kind == "bitcrush":
        return "bitcrush", {"bits": rng.choice([4, 5, 6, 7, 8, 9]),
                            "down": rng.choice([2, 3, 4, 5])}, "crystal"
    if kind == "chorus":
        return "chorus", {"depth": round(rng.uniform(0.002, 0.012), 4),
                          "rate": round(rng.uniform(0.25, 1.2), 2),
                          "mix": round(rng.uniform(0.2, 0.44), 2)}, "ring"
    if kind == "flanger":
        return "flanger", {"base": round(rng.uniform(0.0015, 0.004), 4),
                           "depth": round(rng.uniform(0.002, 0.008), 4),
                           "rate": round(rng.uniform(0.15, 1.0), 2),
                           "mix": round(rng.uniform(0.22, 0.46), 2)}, "ring"
    if kind == "phaser":
        return "phaser", {"rate": round(rng.uniform(0.15, 1.6), 2),
                          "depth": round(rng.uniform(0.2, 0.7), 2)}, "ring"
    if kind == "overdrive":
        return "overdrive", {"drive": round(rng.uniform(1.5, 4.5), 2),
                             "mix": round(rng.uniform(0.2, 0.62), 2)}, "crystal"
    if kind == "ring_mod":
        return "ring_mod", {"freq": round(rng.uniform(18.0, 180.0), 1),
                            "mix": round(rng.uniform(0.2, 0.56), 2)}, "crystal"
    if kind == "vibrato":
        return "vibrato", {"rate": round(rng.uniform(3.5, 7.5), 1),
                           "depth": round(rng.uniform(0.001, 0.006), 4)}, "ring"
    if kind == "wow_flutter":
        return "wow_flutter", {"rate": round(rng.uniform(0.2, 1.0), 2),
                               "depth": round(rng.uniform(0.002, 0.009), 4)}, "ring"
    if kind == "gate":
        return "gate", {"threshold": round(rng.uniform(0.03, 0.2), 2),
                        "floor": round(rng.uniform(0.0, 0.35), 2)}, "crystal"
    if kind == "compressor":
        return "compressor", {"threshold": round(rng.uniform(0.2, 0.6), 2),
                              "ratio": round(rng.uniform(2.0, 7.0), 1)}, "crystal"
    if kind == "resonator":
        return "resonator", {"freq": rng.choice([160, 220, 330, 440, 660, 880]),
                             "decay": round(rng.uniform(0.18, 0.5), 2),
                             "mix": round(rng.uniform(0.18, 0.38), 2)}, "ring"
    return "lo_fi", {"bits": rng.choice([5, 6, 7, 8, 9, 10]),
                      "down": rng.choice([2, 3, 4, 5, 6]),
                      "cutoff": rng.choice([1600, 2400, 3600, 5000])}, "crystal"
