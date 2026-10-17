"""Versioned infinite procedural sound generation.

``proc.<seed>`` is the historical generator used by existing saves.  It is kept
byte-for-byte compatible in :mod:`procedural_legacy`.

New world discoveries use ``proc2.<seed>``.  ComponentDNA v2 separates musical
choices into stable labelled random streams and generates substantially richer
material:

* custom subtractive/additive/FM timbres, with optional instrument layers,
* scale-aware notes, extended chord voicings and chord progressions,
* motif development instead of unrelated random walks,
* custom synthesized drum kits and style-aware grooves,
* layered environmental beds with tonal details,
* multi-stage effect macros,
* rarity-dependent complexity without making common finds unusable.

Every result remains a pure function of its integer seed.  The id alone is
therefore sufficient to reconstruct previews, sequencer clips and exports.
"""

from __future__ import annotations

import hashlib
import math
import random

from . import rarity as _rarity
from . import procedural_legacy as _legacy

V2_PREFIX = "proc2."
LEGACY_PREFIX = "proc."
DNA_VERSION = 2

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "natural minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "lydian": [0, 2, 4, 6, 7, 9, 11],
    "phrygian": [0, 1, 3, 5, 7, 8, 10],
    "harmonic minor": [0, 2, 3, 5, 7, 8, 11],
    "melodic minor": [0, 2, 3, 5, 7, 9, 11],
    "major pentatonic": [0, 2, 4, 7, 9],
    "minor pentatonic": [0, 3, 5, 7, 10],
    "blues": [0, 3, 5, 6, 7, 10],
    "hirajoshi": [0, 2, 3, 7, 8],
    "in sen": [0, 1, 5, 7, 10],
    "whole tone": [0, 2, 4, 6, 8, 10],
    "double harmonic": [0, 1, 4, 5, 7, 8, 11],
}

_COMMON_MODES = [
    ("major", 24), ("natural minor", 21), ("major pentatonic", 16),
    ("minor pentatonic", 15), ("dorian", 10), ("mixolydian", 8),
    ("lydian", 4), ("harmonic minor", 2),
]
_RARE_MODES = _COMMON_MODES + [
    ("phrygian", 5), ("melodic minor", 5), ("blues", 6),
    ("hirajoshi", 4), ("in sen", 3), ("whole tone", 2),
    ("double harmonic", 2),
]

_MELODIC_VOICES = {
    "keys": ["grand_piano", "electric_piano", "toy_piano", "organ", "accordion"],
    "mallets": ["music_box", "bell", "glass", "celeste", "kalimba", "marimba",
                "vibraphone", "fm_bell", "steel_drum", "dulcimer"],
    "plucks": ["pluck", "moon_pluck", "harp", "nylon_guitar", "koto", "sitar",
               "synth_pluck"],
    "winds": ["flute", "clarinet", "oboe", "reed", "whistle"],
    "pads": ["warm_pad", "strings", "choir", "analog_pad", "dream_pad",
             "crystal_pad", "vox"],
    "leads": ["soft_lead", "supersaw", "chiptune", "brass", "muted_brass"],
    "animal": ["meow", "purr", "croak", "quack", "hoot", "chirp"],
}
_BASS_VOICES = ["warm_bass", "sub_bass", "synth_bass", "acid_bass",
                "upright_bass", "fm_bass", "pluck_bass", "rubber_bass"]
_AMBIENCES = ["wind", "river", "birds", "crickets", "purr", "crackle", "owl",
              "rain", "storm", "ocean", "waterfall", "cave", "night_forest",
              "leaves", "vinyl", "tape", "city", "train", "clock", "underwater",
              "snow", "bees", "distant_bells", "drone", "fireplace",
              "meadow_night", "space", "heartbeat"]

_ARCHETYPES = {
    "lullaby": {
        "modes": ["major", "major pentatonic", "natural minor"],
        "families": ["mallets", "keys", "plucks", "pads"],
        "tags": ["soft", "dreamy", "warm"], "density": (0.34, 0.58),
        "effects": ["reverb", "delay", "chorus"],
    },
    "forest folk": {
        "modes": ["major", "dorian", "mixolydian", "major pentatonic"],
        "families": ["plucks", "winds", "mallets"],
        "tags": ["warm", "airy", "playful"], "density": (0.46, 0.76),
        "effects": ["reverb", "delay", "resonator"],
    },
    "nocturne": {
        "modes": ["natural minor", "dorian", "harmonic minor"],
        "families": ["keys", "pads", "mallets", "plucks"],
        "tags": ["night", "dreamy", "soft"], "density": (0.30, 0.62),
        "effects": ["reverb", "delay", "wow_flutter"],
    },
    "ambient": {
        "modes": ["lydian", "major pentatonic", "dorian", "whole tone"],
        "families": ["pads", "mallets", "winds"],
        "tags": ["airy", "dreamy", "soft"], "density": (0.20, 0.48),
        "effects": ["reverb", "chorus", "phaser", "delay"],
    },
    "cinematic": {
        "modes": ["natural minor", "dorian", "harmonic minor", "major"],
        "families": ["pads", "keys", "leads", "winds"],
        "tags": ["warm", "night"], "density": (0.42, 0.75),
        "effects": ["reverb", "compressor", "delay", "resonator"],
    },
    "garden jazz": {
        "modes": ["dorian", "mixolydian", "melodic minor", "blues"],
        "families": ["keys", "winds", "mallets", "plucks"],
        "tags": ["warm", "playful"], "density": (0.50, 0.82),
        "effects": ["reverb", "chorus", "compressor"],
    },
    "clockwork": {
        "modes": ["major pentatonic", "minor pentatonic", "whole tone"],
        "families": ["mallets", "plucks", "keys"],
        "tags": ["bright", "playful"], "density": (0.58, 0.90),
        "effects": ["delay", "resonator", "bitcrush"],
    },
    "electronic": {
        "modes": ["natural minor", "dorian", "mixolydian", "minor pentatonic"],
        "families": ["leads", "pads", "plucks", "mallets"],
        "tags": ["bright", "dreamy"], "density": (0.55, 0.92),
        "effects": ["chorus", "delay", "phaser", "overdrive"],
    },
    "pixel garden": {
        "modes": ["major", "natural minor", "major pentatonic", "hirajoshi"],
        "families": ["leads", "mallets", "plucks"],
        "tags": ["bright", "playful"], "density": (0.58, 0.94),
        "effects": ["bitcrush", "delay", "gate"],
    },
    "world garden": {
        "modes": ["dorian", "phrygian", "hirajoshi", "in sen", "double harmonic"],
        "families": ["plucks", "winds", "mallets"],
        "tags": ["warm", "airy"], "density": (0.42, 0.80),
        "effects": ["reverb", "delay", "resonator"],
    },
    "glitch bloom": {
        "modes": ["minor pentatonic", "whole tone", "blues", "phrygian"],
        "families": ["leads", "mallets", "plucks"],
        "tags": ["bright", "playful", "dreamy"], "density": (0.42, 0.88),
        "effects": ["bitcrush", "ring_mod", "gate", "flanger"],
    },
    "animal chorus": {
        "modes": ["major pentatonic", "minor pentatonic", "dorian"],
        "families": ["animal", "mallets", "plucks"],
        "tags": ["animal", "playful", "soft"], "density": (0.36, 0.72),
        "effects": ["reverb", "delay", "chorus"],
    },
}

_TYPE_WEIGHTS = [
    ("note", 14), ("bass_note", 7), ("chord", 11), ("drum", 8),
    ("melody_loop", 17), ("bass_loop", 10), ("chord_loop", 9),
    ("rhythm", 14), ("ambience", 7), ("effect", 3),
]

_COMPLEXITY = {
    "common": {"layers": 0, "bars": (1, 2), "fx": 0, "detail": 0},
    "uncommon": {"layers": 1, "bars": (1, 2), "fx": 1, "detail": 1},
    "rare": {"layers": 1, "bars": (2, 3), "fx": 2, "detail": 2},
    "secret": {"layers": 2, "bars": (2, 4), "fx": 3, "detail": 3},
}

_ADJECTIVES = ["Amber", "Astral", "Bramble", "Clouded", "Copper", "Dewlit",
               "Dreaming", "Ember", "Fern", "Frosted", "Golden", "Hollow",
               "Honey", "Lunar", "Maple", "Misty", "Moonlit", "Mossy",
               "Opal", "Quiet", "Rainwashed", "River", "Silver", "Soft",
               "Starlit", "Sunken", "Velvet", "Willow", "Windborne"]
_MATERIALS = ["Bell", "Bloom", "Circuit", "Feather", "Glass", "Lantern",
              "Leaf", "Meadow", "Mist", "Moth", "Pebble", "Petal", "Pond",
              "Reed", "Ribbon", "Seed", "Shadow", "Shell", "Spark", "Stone",
              "Thread", "Tide", "Vine", "Wisp"]
_FORM_NAMES = {
    "note": ["Tone", "Chime", "Note", "Voice"],
    "bass_note": ["Root", "Pulse", "Low Note", "Ground"],
    "chord": ["Voicing", "Harmony", "Chord", "Cluster"],
    "drum": ["Hit", "Knock", "Strike", "Tap"],
    "melody_loop": ["Motif", "Phrase", "Arp", "Run", "Lullaby"],
    "bass_loop": ["Bassline", "Undercurrent", "Low Walk", "Pulse"],
    "chord_loop": ["Progression", "Changes", "Harmony Loop", "Cycle"],
    "rhythm": ["Groove", "Beat", "Shuffle", "Pattern", "Pulse"],
    "ambience": ["Atmosphere", "Soundscape", "Haze", "Field", "Dream"],
    "effect": ["Transform", "Prism", "Machine", "Veil", "Processor"],
}
_ORIGINS = ["Meadow", "Riverside", "Orchard", "Deepwood", "Glade", "Hollow",
            "Clearing", "Hilltop", "Coastline", "Old Garden", "Night Path"]
_TINT = {"note": (255, 224, 150), "chord": (255, 176, 156),
         "drum": (214, 188, 150), "rhythm": (232, 200, 130),
         "loop": (176, 214, 235), "ambience": (196, 206, 235),
         "effect": (214, 176, 236)}


class DNA:
    """Stable named random streams.

    Adding a choice to the rhythm stream cannot unexpectedly change a sound's
    key, name or timbre.  This makes future generator upgrades safer.
    """

    def __init__(self, seed: int):
        self.seed = int(seed) & 0x7FFFFFFF

    def rng(self, label: str) -> random.Random:
        raw = ("bsg.component-dna.v2|%d|%s" % (self.seed, label)).encode("utf-8")
        value = int.from_bytes(hashlib.blake2s(raw, digest_size=8).digest(), "big")
        return random.Random(value)

    def choice(self, label, values):
        return self.rng(label).choice(list(values))

    def weighted(self, label, weighted):
        rng = self.rng(label)
        total = float(sum(weight for _, weight in weighted))
        roll = rng.uniform(0.0, total)
        upto = 0.0
        for value, weight in weighted:
            upto += weight
            if roll <= upto:
                return value
        return weighted[-1][0]


def is_proc(cid):
    return isinstance(cid, str) and (cid.startswith(LEGACY_PREFIX) or cid.startswith(V2_PREFIX))


def from_id(cid):
    if not isinstance(cid, str):
        return None
    try:
        if cid.startswith(V2_PREFIX):
            return generate(int(cid[len(V2_PREFIX):]))
        if cid.startswith(LEGACY_PREFIX):
            return _legacy.generate(int(cid[len(LEGACY_PREFIX):]))
    except (TypeError, ValueError):
        return None
    return None


def generate_legacy(seed):
    """Explicit compatibility entry point for tests and migration tools."""
    return _legacy.generate(seed)


def _midi_name(midi):
    midi = int(round(midi))
    return _NOTE_NAMES[midi % 12] + str(midi // 12 - 1)


def _root_name(pc):
    return _NOTE_NAMES[int(pc) % 12]


def _mode_midis(root_pc, octave, mode, octaves=3):
    base = (int(octave) + 1) * 12 + int(root_pc)
    degrees = _SCALES[mode]
    result = []
    for octv in range(octaves):
        for degree, semi in enumerate(degrees):
            result.append((base + semi + 12 * octv, degree + octv * len(degrees)))
    return result


def _degree_to_midi(root_pc, octave, mode, degree):
    scale = _SCALES[mode]
    n = len(scale)
    q, r = divmod(int(degree), n)
    return (int(octave) + 1) * 12 + int(root_pc) + scale[r] + 12 * q


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _round(value, digits=4):
    return round(float(value), digits)


def _timbre_spec(dna, label, role, rarity, archetype):
    """Create a bounded procedural synthesizer patch."""
    rng = dna.rng(label)
    detail = _COMPLEXITY[rarity]["detail"]

    if role == "bass":
        osc_pool = ["sine", "triangle", "saw", "square"]
        primary = rng.choices(osc_pool, [35, 32, 23, 10])[0]
        attack = rng.uniform(0.002, 0.035)
        decay = rng.uniform(0.10, 0.34)
        sustain = rng.uniform(0.42, 0.82)
        release = rng.uniform(0.08, 0.34)
        cutoff = rng.uniform(260.0, 1250.0)
        noise = rng.uniform(0.0, 0.025)
    elif role == "pad":
        primary = rng.choice(["sine", "triangle", "saw"])
        attack = rng.uniform(0.16, 0.72)
        decay = rng.uniform(0.18, 0.65)
        sustain = rng.uniform(0.58, 0.90)
        release = rng.uniform(0.35, 1.10)
        cutoff = rng.uniform(750.0, 4200.0)
        noise = rng.uniform(0.0, 0.035)
    elif role == "pluck":
        primary = rng.choice(["triangle", "saw", "square", "sine"])
        attack = rng.uniform(0.001, 0.012)
        decay = rng.uniform(0.09, 0.38)
        sustain = rng.uniform(0.02, 0.28)
        release = rng.uniform(0.07, 0.34)
        cutoff = rng.uniform(1000.0, 7200.0)
        noise = rng.uniform(0.0, 0.06)
    else:
        primary = rng.choice(["sine", "triangle", "saw", "square"])
        attack = rng.uniform(0.003, 0.075)
        decay = rng.uniform(0.08, 0.42)
        sustain = rng.uniform(0.32, 0.78)
        release = rng.uniform(0.10, 0.48)
        cutoff = rng.uniform(700.0, 6500.0)
        noise = rng.uniform(0.0, 0.045)

    oscillator_weights = [(primary, 1.0)]
    if detail >= 1 or rng.random() < 0.45:
        second = rng.choice([x for x in ["sine", "triangle", "saw", "square"] if x != primary])
        oscillator_weights.append((second, _round(rng.uniform(0.08, 0.34), 3)))

    partials = []
    possible = [2.0, 3.0, 4.0, 5.0, 1.5, 2.01, 3.02]
    for _ in range(min(3, detail + (1 if rng.random() < 0.45 else 0))):
        ratio = rng.choice(possible)
        partials.append((ratio, _round(rng.uniform(0.025, 0.18), 3)))

    detune = []
    if role == "pad" or detail >= 2:
        width = rng.uniform(2.0, 11.0 if role == "pad" else 7.0)
        detune = [-_round(width, 2), _round(width, 2)]
        if detail >= 3 and role == "pad":
            detune.extend([-_round(width * 0.45, 2), _round(width * 0.45, 2)])

    fm_index = 0.0
    fm_ratio = 2.0
    if (archetype in ("clockwork", "electronic", "pixel garden", "glitch bloom")
            and rng.random() < 0.32 + detail * 0.10):
        fm_index = rng.uniform(0.18, 1.55 if detail >= 2 else 0.75)
        fm_ratio = rng.choice([1.5, 2.0, 2.5, 3.0, 4.0])

    return {
        "oscillators": [(name, _round(gain, 3)) for name, gain in oscillator_weights],
        "partials": partials,
        "detune_cents": detune,
        "attack": _round(attack), "decay": _round(decay),
        "sustain": _round(sustain), "release": _round(release),
        "cutoff": _round(cutoff, 1),
        "highpass": _round(rng.uniform(20.0, 90.0 if role == "bass" else 240.0), 1),
        "noise": _round(noise, 4),
        "vibrato_rate": _round(rng.uniform(3.2, 7.2), 2),
        "vibrato_cents": _round(rng.uniform(0.0, 4.0 + detail * 2.5), 2),
        "tremolo_rate": _round(rng.uniform(0.3, 8.0), 2),
        "tremolo_depth": _round(rng.uniform(0.0, 0.08 + detail * 0.06), 3),
        "fm_ratio": _round(fm_ratio, 2), "fm_index": _round(fm_index, 3),
        "drive": _round(rng.uniform(1.0, 1.7 if archetype == "glitch bloom" else 1.25), 3),
    }


def _layers(dna, label, rarity, archetype, role):
    count = _COMPLEXITY[rarity]["layers"]
    if count <= 0:
        return []
    rng = dna.rng(label)
    profile = _ARCHETYPES[archetype]
    layers = []
    for i in range(count):
        family = rng.choice(profile["families"])
        voice_name = rng.choice(_MELODIC_VOICES[family])
        octave = rng.choice([-1, 0, 0, 1]) if role != "bass" else rng.choice([0, 0, 1])
        layers.append({
            "voice": voice_name,
            "gain": _round(rng.uniform(0.10, 0.28 if i == 0 else 0.20), 3),
            "octave": octave,
            "detune_cents": _round(rng.uniform(-5.0, 5.0), 2),
        })
    return layers


def _component_effects(dna, label, rarity, archetype, subtle=True):
    count = _COMPLEXITY[rarity]["fx"]
    if count == 0 and subtle:
        return []
    rng = dna.rng(label)
    allowed = list(_ARCHETYPES[archetype]["effects"])
    rng.shuffle(allowed)
    count = min(count, len(allowed))
    effects = []
    for kind in allowed[:count]:
        if kind == "reverb":
            params = {"amount": _round(rng.uniform(0.16, 0.44), 2),
                      "decay": _round(rng.uniform(0.32, 0.88), 2)}
        elif kind == "delay":
            params = {"time": _round(rng.choice([0.11, 0.15, 0.18, 0.22, 0.28, 0.34]), 2),
                      "feedback": _round(rng.uniform(0.14, 0.38), 2),
                      "mix": _round(rng.uniform(0.12, 0.30), 2)}
        elif kind == "chorus":
            params = {"depth": _round(rng.uniform(0.002, 0.008), 4),
                      "rate": _round(rng.uniform(0.25, 0.95), 2),
                      "mix": _round(rng.uniform(0.14, 0.32), 2)}
        elif kind == "phaser":
            params = {"rate": _round(rng.uniform(0.12, 1.1), 2),
                      "depth": _round(rng.uniform(0.18, 0.58), 2)}
        elif kind == "overdrive":
            params = {"drive": _round(rng.uniform(1.3, 2.5), 2),
                      "mix": _round(rng.uniform(0.10, 0.28), 2)}
        elif kind == "bitcrush":
            params = {"bits": rng.choice([6, 7, 8, 9, 10]), "down": rng.choice([2, 2, 3, 4])}
        elif kind == "gate":
            params = {"threshold": _round(rng.uniform(0.03, 0.13), 2),
                      "floor": _round(rng.uniform(0.04, 0.25), 2)}
        elif kind == "ring_mod":
            params = {"freq": _round(rng.uniform(18.0, 95.0), 1),
                      "mix": _round(rng.uniform(0.08, 0.24), 2)}
        elif kind == "flanger":
            params = {"base": _round(rng.uniform(0.0015, 0.0035), 4),
                      "depth": _round(rng.uniform(0.0015, 0.005), 4),
                      "rate": _round(rng.uniform(0.18, 0.75), 2),
                      "mix": _round(rng.uniform(0.12, 0.28), 2)}
        elif kind == "wow_flutter":
            params = {"rate": _round(rng.uniform(0.25, 0.85), 2),
                      "depth": _round(rng.uniform(0.0015, 0.005), 4),
                      "flutter_rate": _round(rng.uniform(4.0, 7.0), 2),
                      "flutter_depth": _round(rng.uniform(0.0002, 0.0008), 4)}
        elif kind == "compressor":
            params = {"threshold": _round(rng.uniform(0.28, 0.55), 2),
                      "ratio": _round(rng.uniform(2.0, 4.5), 1)}
        else:  # resonator
            params = {"freq": rng.choice([165, 220, 330, 440, 550, 660, 880]),
                      "decay": _round(rng.uniform(0.16, 0.42), 2),
                      "mix": _round(rng.uniform(0.10, 0.27), 2)}
        effects.append((kind, params))
    return effects


def _name(dna, family):
    rng = dna.rng("name")
    signature = "%03X" % (dna.seed & 0xFFF)
    return "%s %s %s %s" % (rng.choice(_ADJECTIVES), rng.choice(_MATERIALS),
                              rng.choice(_FORM_NAMES[family]), signature)


def _base(dna, family, typ, track, rarity, archetype, **extra):
    root_rng = dna.rng("identity")
    origin = root_rng.choice(_ORIGINS)
    mode = extra.pop("mode", None)
    root = extra.pop("root_name", None)
    tags = list(dict.fromkeys(_ARCHETYPES[archetype]["tags"] + extra.pop("tags", [])))
    dna_meta = {
        "version": DNA_VERSION, "seed": dna.seed, "family": family,
        "archetype": archetype, "complexity": _COMPLEXITY[rarity]["detail"],
    }
    if mode:
        dna_meta["mode"] = mode
    if root:
        dna_meta["root"] = root
    comp = {
        "id": V2_PREFIX + str(dna.seed), "name": _name(dna, family),
        "type": typ, "track": track, "rarity": rarity, "proc": True,
        "proc_version": DNA_VERSION, "origin": origin, "region": origin.lower().replace(" ", "_"),
        "icon": extra.pop("icon", {"note": "note", "chord": "cluster", "drum": "stone",
                                     "loop": "cassette", "rhythm": "rune",
                                     "ambience": "orb", "effect": "crystal"}.get(typ, "note")),
        "color": _TINT.get(typ, (255, 214, 130)), "tags": tags, "dna": dna_meta,
    }
    comp.update(extra)
    return comp


def _identity(dna, rarity, archetype):
    rng = dna.rng("harmony")
    mode_options = _RARE_MODES if rarity in ("rare", "secret") else _COMMON_MODES
    preferred = _ARCHETYPES[archetype]["modes"]
    weighted = []
    for mode, weight in mode_options:
        weighted.append((mode, weight * (2.2 if mode in preferred else 1.0)))
    mode = DNA(dna.seed).weighted("mode", weighted)
    root_pc = rng.randrange(12)
    return root_pc, mode


def _voice_choice(dna, archetype, label="voice"):
    rng = dna.rng(label)
    family = rng.choice(_ARCHETYPES[archetype]["families"])
    return rng.choice(_MELODIC_VOICES[family]), family


def _single_note(dna, rarity, archetype, bass=False):
    root_pc, mode = _identity(dna, rarity, archetype)
    rng = dna.rng("note")
    octave = rng.choice([2, 2, 3]) if bass else rng.choice([3, 4, 4, 5, 5])
    degree = rng.randrange(len(_SCALES[mode]))
    note = _midi_name(_degree_to_midi(root_pc, octave, mode, degree))
    role = "bass" if bass else rng.choice(["pluck", "lead", "lead", "pad"])
    voice_name = rng.choice(_BASS_VOICES) if bass else _voice_choice(dna, archetype)[0]
    timbre = _timbre_spec(dna, "timbre", role, rarity, archetype)
    family = "bass_note" if bass else "note"
    desc = "A generated %s tone in %s %s, shaped by a unique synthesis patch." % (
        "bass" if bass else archetype, _root_name(root_pc), mode)
    return _base(dna, family, "note", "bass" if bass else "melody", rarity, archetype,
                 root_name=_root_name(root_pc), mode=mode, voice=voice_name, notes=[note],
                 dur=_round(rng.uniform(0.75, 1.55 if not bass else 1.15), 2),
                 timbre=timbre, layers=_layers(dna, "layers", rarity, archetype, role),
                 effects=_component_effects(dna, "effects", rarity, archetype),
                 desc=desc)


def _chord_intervals(mode, rng, rarity):
    scale = _SCALES[mode]
    degree = rng.randrange(len(scale))
    intervals = []
    for leap in (0, 2, 4):
        target = degree + leap
        q, r = divmod(target, len(scale))
        intervals.append(scale[r] + 12 * q - scale[degree])
    if rarity in ("uncommon", "rare", "secret") and rng.random() < 0.72:
        target = degree + rng.choice([6, 8])
        q, r = divmod(target, len(scale))
        intervals.append(scale[r] + 12 * q - scale[degree])
    if rarity == "secret" and rng.random() < 0.45:
        intervals.append(rng.choice([14, 17, 19]))
    return degree, sorted(set(intervals))


def _voicing_notes(root_pc, octave, mode, degree, intervals, rng):
    root_midi = _degree_to_midi(root_pc, octave, mode, degree)
    notes = [root_midi + interval for interval in intervals]
    inversion = rng.randrange(min(3, len(notes)))
    for i in range(inversion):
        notes[i] += 12
    if rng.random() < 0.35 and len(notes) >= 4:
        notes[-2] -= 12
    notes = sorted(_clamp(n, 36, 96) for n in notes)
    return [_midi_name(n) for n in notes]


def _single_chord(dna, rarity, archetype):
    root_pc, mode = _identity(dna, rarity, archetype)
    rng = dna.rng("chord")
    degree, intervals = _chord_intervals(mode, rng, rarity)
    octave = rng.choice([3, 4, 4])
    notes = _voicing_notes(root_pc, octave, mode, degree, intervals, rng)
    role = "pad" if archetype in ("ambient", "cinematic", "nocturne") else "pluck"
    voice_name = _voice_choice(dna, archetype)[0]
    root_label = _midi_name(_degree_to_midi(root_pc, octave, mode, degree))[:-1]
    desc = "A %s voicing built on %s inside %s %s, with deterministic inversion and color tones." % (
        archetype, root_label, _root_name(root_pc), mode)
    return _base(dna, "chord", "chord", "chords", rarity, archetype,
                 root_name=_root_name(root_pc), mode=mode, notes=notes, voice=voice_name,
                 timbre=_timbre_spec(dna, "timbre", role, rarity, archetype),
                 layers=_layers(dna, "layers", rarity, archetype, role),
                 dur=_round(rng.uniform(1.45, 2.7), 2),
                 strum_ms=_round(rng.uniform(0.0, 34.0 if role == "pluck" else 18.0), 1),
                 strum_direction=rng.choice(["up", "down"]),
                 effects=_component_effects(dna, "effects", rarity, archetype), desc=desc)


def _rhythm_grid(dna, label, length_steps, density, archetype):
    rng = dna.rng(label)
    subdivision = 0.5 if (density > 0.60 or archetype in ("electronic", "pixel garden", "glitch bloom")) else 1.0
    positions = [i * subdivision for i in range(int(length_steps / subdivision))]
    onsets = [0.0]
    for pos in positions[1:]:
        beat_strength = 1.0 if abs(pos % 2.0) < 1e-6 else (0.72 if abs(pos % 1.0) < 1e-6 else 0.46)
        chance = density * beat_strength
        if rng.random() < chance:
            onsets.append(pos)
    # Maintain space and a recognisable phrase beginning.
    max_events = max(3, int(length_steps * (1.0 if subdivision == 0.5 else 0.72)))
    return sorted(set(onsets[:max_events]))


def _contour_degrees(dna, count, mode_size, archetype):
    rng = dna.rng("contour")
    shape = rng.choice(["arch", "wave", "rise", "fall", "pendulum", "call_response"])
    degree = rng.randrange(max(1, mode_size // 2)) + mode_size
    values = []
    direction = 1
    for i in range(count):
        values.append(degree)
        if shape == "arch":
            direction = 1 if i < count / 2 else -1
        elif shape == "rise":
            direction = 1
        elif shape == "fall":
            direction = -1
        elif shape == "wave":
            if i and i % max(2, count // 3) == 0:
                direction *= -1
        elif shape == "pendulum":
            direction *= -1
        elif shape == "call_response" and i == count // 2:
            degree = values[0]
            direction *= -1
        move = rng.choices([-2, -1, 0, 1, 2, 3], [5, 22, 16, 28, 12, 3])[0]
        if shape in ("arch", "rise", "fall"):
            move = abs(move) * direction
        degree = int(_clamp(degree + move, 0, mode_size * 3 - 1))
    if values:
        values[-1] = mode_size + rng.choice([0, 0, 4 if mode_size >= 5 else 0])
    return values


def _melody_loop(dna, rarity, archetype, bass=False):
    root_pc, mode = _identity(dna, rarity, archetype)
    cfg = _COMPLEXITY[rarity]
    rng = dna.rng("phrase")
    bars = rng.randint(cfg["bars"][0], cfg["bars"][1])
    length = bars * 8
    profile = _ARCHETYPES[archetype]
    density = rng.uniform(*profile["density"])
    if bass:
        density *= 0.72
    onsets = _rhythm_grid(dna, "phrase-rhythm", length, density, archetype)
    degrees = _contour_degrees(dna, len(onsets), len(_SCALES[mode]), archetype)
    octave = rng.choice([2, 2, 3]) if bass else rng.choice([3, 4, 4, 5])
    swing = rng.uniform(0.0, 0.16 if archetype in ("garden jazz", "forest folk") else 0.08)
    pattern = []
    for i, (step, degree) in enumerate(zip(onsets, degrees)):
        if swing and abs((step * 2) % 2 - 1) < 1e-6:
            step += swing
        next_step = onsets[i + 1] if i + 1 < len(onsets) else length
        dur = _clamp((next_step - onsets[i]) * rng.uniform(0.58, 0.95), 0.22, 3.0)
        midi = _degree_to_midi(root_pc, octave, mode, degree)
        gain = 1.0 if abs(step % 2.0) < 0.08 else rng.uniform(0.68, 0.92)
        pattern.append((_midi_name(midi), _round(step, 3), _round(dur, 3), _round(gain, 3)))
    role = "bass" if bass else rng.choice(["pluck", "lead", "lead", "pad"])
    voice_name = rng.choice(_BASS_VOICES) if bass else _voice_choice(dna, archetype)[0]
    family = "bass_loop" if bass else "melody_loop"
    desc = "A %d-bar %s phrase in %s %s, developed from a repeated contour and cadence." % (
        bars, "bass" if bass else archetype, _root_name(root_pc), mode)
    return _base(dna, family, "loop", "bass" if bass else "loops", rarity, archetype,
                 root_name=_root_name(root_pc), mode=mode, voice=voice_name, pattern=pattern,
                 length_steps=length, timbre=_timbre_spec(dna, "timbre", role, rarity, archetype),
                 layers=_layers(dna, "layers", rarity, archetype, role),
                 effects=_component_effects(dna, "effects", rarity, archetype), desc=desc)


def _progression_degrees(mode, rng, bars):
    majorish = mode in ("major", "lydian", "mixolydian", "major pentatonic")
    libraries = [
        [0, 4, 5, 3], [0, 3, 4, 0], [0, 5, 3, 4], [0, 2, 5, 4],
        [0, 4, 3, 5], [0, 1, 4, 0],
    ] if majorish else [
        [0, 5, 2, 6], [0, 3, 6, 0], [0, 6, 5, 6], [0, 2, 3, 4],
        [0, 4, 5, 3], [0, 1, 6, 0],
    ]
    base = list(rng.choice(libraries))
    needed = max(1, bars)
    return (base * int(math.ceil(needed / len(base))))[:needed]


def _chord_loop(dna, rarity, archetype):
    root_pc, mode = _identity(dna, rarity, archetype)
    cfg = _COMPLEXITY[rarity]
    rng = dna.rng("progression")
    bars = rng.randint(max(2, cfg["bars"][0]), max(2, cfg["bars"][1]))
    length = bars * 8
    progression = _progression_degrees(mode, rng, bars)
    pattern = []
    for bar, degree in enumerate(progression):
        local_rng = dna.rng("progression-%d" % bar)
        degree %= len(_SCALES[mode])
        _, intervals = _chord_intervals(mode, local_rng, rarity)
        notes = _voicing_notes(root_pc, 3 if archetype == "cinematic" else 4,
                               mode, degree, intervals, local_rng)
        pattern.append((tuple(notes), float(bar * 8), _round(7.4, 2),
                        _round(0.78 + local_rng.random() * 0.18, 3)))
        if rarity in ("rare", "secret") and local_rng.random() < 0.42:
            passing_degree = (degree + local_rng.choice([-1, 1])) % len(_SCALES[mode])
            _, pints = _chord_intervals(mode, local_rng, "uncommon")
            pnotes = _voicing_notes(root_pc, 4, mode, passing_degree, pints, local_rng)
            pattern.append((tuple(pnotes), bar * 8 + 6.0, 1.7, 0.58))
    role = "pad" if archetype in ("ambient", "cinematic", "nocturne") else "pluck"
    desc = "A %d-bar generated chord cycle in %s %s with voice-led inversions." % (
        bars, _root_name(root_pc), mode)
    return _base(dna, "chord_loop", "loop", "chords", rarity, archetype,
                 root_name=_root_name(root_pc), mode=mode, voice=_voice_choice(dna, archetype)[0],
                 pattern=pattern, length_steps=length,
                 timbre=_timbre_spec(dna, "timbre", role, rarity, archetype),
                 layers=_layers(dna, "layers", rarity, archetype, role),
                 effects=_component_effects(dna, "effects", rarity, archetype), desc=desc)


def _drum_spec(dna, label, role, rarity):
    rng = dna.rng(label)
    detail = _COMPLEXITY[rarity]["detail"]
    if role == "kick":
        return {"kind": "kick", "dur": _round(rng.uniform(0.24, 0.52), 3),
                "f0": _round(rng.uniform(82.0, 168.0), 1),
                "f1": _round(rng.uniform(34.0, 62.0), 1),
                "sweep": _round(rng.uniform(11.0, 28.0), 1),
                "click": _round(rng.uniform(0.05, 0.36), 3),
                "drive": _round(rng.uniform(1.0, 1.6 + detail * 0.18), 3)}
    if role == "snare":
        return {"kind": "snare", "dur": _round(rng.uniform(0.14, 0.38), 3),
                "tone": _round(rng.uniform(135.0, 265.0), 1),
                "noise": _round(rng.uniform(0.46, 0.92), 3),
                "brightness": _round(rng.uniform(1200.0, 5200.0), 1),
                "decay": _round(rng.uniform(10.0, 28.0), 2)}
    if role == "hat":
        return {"kind": "hat", "dur": _round(rng.uniform(0.035, 0.22), 3),
                "brightness": _round(rng.uniform(4800.0, 10500.0), 1),
                "metal": _round(rng.uniform(0.10, 0.62), 3),
                "decay": _round(rng.uniform(18.0, 62.0), 2)}
    if role == "tom":
        return {"kind": "tom", "dur": _round(rng.uniform(0.16, 0.45), 3),
                "freq": _round(rng.uniform(82.0, 260.0), 1),
                "bend": _round(rng.uniform(0.06, 0.34), 3),
                "decay": _round(rng.uniform(7.0, 18.0), 2)}
    if role == "metal":
        return {"kind": "metal", "dur": _round(rng.uniform(0.12, 0.72), 3),
                "freq": _round(rng.uniform(260.0, 980.0), 1),
                "inharmonic": _round(rng.uniform(1.31, 2.73), 3),
                "decay": _round(rng.uniform(5.0, 22.0), 2)}
    if role == "clap":
        return {"kind": "clap", "dur": _round(rng.uniform(0.12, 0.30), 3),
                "bursts": rng.randint(2, 5), "brightness": _round(rng.uniform(900.0, 4200.0), 1),
                "decay": _round(rng.uniform(12.0, 30.0), 2)}
    if role == "shaker":
        return {"kind": "shaker", "dur": _round(rng.uniform(0.05, 0.25), 3),
                "brightness": _round(rng.uniform(2800.0, 9200.0), 1),
                "decay": _round(rng.uniform(16.0, 55.0), 2)}
    return {"kind": "perc", "dur": _round(rng.uniform(0.08, 0.38), 3),
            "freq": _round(rng.uniform(180.0, 920.0), 1),
            "ratio": _round(rng.uniform(1.35, 3.4), 3),
            "noise": _round(rng.uniform(0.02, 0.30), 3),
            "decay": _round(rng.uniform(8.0, 32.0), 2)}


def _single_drum(dna, rarity, archetype):
    rng = dna.rng("drum")
    roles = ["kick", "snare", "hat", "tom", "perc", "shaker", "clap", "metal"]
    weights = [15, 15, 17, 10, 16, 12, 8, 7]
    role = rng.choices(roles, weights)[0]
    desc = "A unique synthesized %s hit with seed-shaped pitch, envelope and texture." % role
    return _base(dna, "drum", "drum", "drums", rarity, archetype,
                 drum="procedural", drum_spec=_drum_spec(dna, "drum-spec", role, rarity),
                 icon="stone" if role not in ("metal", "hat") else "crystal", desc=desc)


def _groove_style(dna, archetype):
    options = ["four pulse", "half time", "broken beat", "shuffle", "three feel",
               "minimal", "tribal", "syncopated", "clockwork", "glitch"]
    weights = [14, 12, 16, 11, 6, 12, 9, 12, 5, 3]
    if archetype in ("electronic", "pixel garden"):
        weights[0] += 12; weights[8] += 8
    if archetype == "garden jazz":
        weights[3] += 15; weights[2] += 8
    if archetype == "glitch bloom":
        weights[9] += 22; weights[2] += 7
    if archetype in ("forest folk", "world garden"):
        weights[6] += 13; weights[4] += 5
    return dna.rng("groove-style").choices(options, weights)[0]


def _rhythm(dna, rarity, archetype):
    rng = dna.rng("rhythm")
    cfg = _COMPLEXITY[rarity]
    bars = rng.randint(cfg["bars"][0], min(3, cfg["bars"][1]))
    length = bars * 8
    style = _groove_style(dna, archetype)
    kit = {
        "K": _drum_spec(dna, "kit-kick", "kick", rarity),
        "S": _drum_spec(dna, "kit-snare", "snare", rarity),
        "H": _drum_spec(dna, "kit-hat", "hat", rarity),
        "P": _drum_spec(dna, "kit-perc", rng.choice(["perc", "tom", "shaker", "metal"]), rarity),
    }
    if rarity in ("rare", "secret"):
        kit["C"] = _drum_spec(dna, "kit-color", rng.choice(["clap", "metal", "tom"]), rarity)

    kick, snare, hats, perc = set(), set(), set(), set()
    for bar in range(bars):
        o = bar * 8.0
        if style == "four pulse":
            kick.update(o + x for x in (0, 2, 4, 6)); snare.update(o + x for x in (2, 6))
        elif style == "half time":
            kick.update((o, o + 4.5)); snare.add(o + 4)
        elif style == "broken beat":
            kick.update((o, o + 2.5, o + 5.5)); snare.update((o + 2, o + 6))
        elif style == "shuffle":
            kick.update((o, o + 4)); snare.update((o + 2.7, o + 6.7))
        elif style == "three feel":
            kick.update((o, o + 5.5)); snare.update((o + 2.5, o + 5.0))
        elif style == "tribal":
            kick.update((o, o + 3, o + 5.5)); perc.update((o + 1.5, o + 4.5, o + 7))
        elif style == "clockwork":
            kick.update((o, o + 4)); snare.update((o + 2, o + 6)); perc.update(o + x for x in (1, 3, 5, 7))
        elif style == "glitch":
            kick.update((o, o + 3.5)); snare.update((o + 2, o + 6.5)); perc.update((o + 1.0, o + 1.5, o + 5.0, o + 7.5))
        elif style == "minimal":
            kick.update((o, o + 4)); snare.add(o + 6)
        else:  # syncopated
            kick.update((o, o + 3, o + 5.5)); snare.update((o + 2, o + 6))

        hat_step = 0.5 if archetype in ("electronic", "pixel garden", "clockwork", "glitch bloom") else 1.0
        for i in range(int(8 / hat_step)):
            pos = o + i * hat_step
            if rng.random() < (0.68 if hat_step == 1.0 else 0.52):
                hats.add(pos)
        if rng.random() < 0.55:
            perc.add(o + rng.choice([1.5, 3.5, 5.0, 7.0]))

    pattern = []
    for token, positions in (("K", kick), ("S", snare), ("H", hats), ("P", perc)):
        for step in sorted(positions):
            base = 1.0 if token in ("K", "S") and abs(step % 2.0) < 0.08 else 0.78
            gain = _round(base * rng.uniform(0.82, 1.04), 3)
            pattern.append((token, _round(step, 3), gain))
    if "C" in kit:
        for bar in range(bars):
            if rng.random() < 0.55:
                pattern.append(("C", bar * 8 + rng.choice([3.5, 7.0, 7.5]), _round(rng.uniform(0.48, 0.78), 3)))
    pattern.sort(key=lambda event: (event[1], event[0]))
    desc = "A %d-bar %s groove with its own synthesized drum kit and velocity pattern." % (bars, style)
    return _base(dna, "rhythm", "rhythm", "rhythms", rarity, archetype,
                 pattern=pattern, drum_kit=kit, length_steps=length, groove_style=style,
                 effects=_component_effects(dna, "rhythm-effects", rarity, archetype), desc=desc)


def _ambience(dna, rarity, archetype):
    rng = dna.rng("ambience")
    detail = _COMPLEXITY[rarity]["detail"]
    layer_count = 2 + min(2, detail)
    choices = list(_AMBIENCES)
    if archetype == "animal chorus":
        choices += ["birds", "owl", "purr", "bees", "crickets"] * 2
    if archetype == "ambient":
        choices += ["space", "drone", "cave", "wind", "underwater"] * 2
    layers = []
    used = set()
    for i in range(layer_count):
        kind = rng.choice(choices)
        if kind in used:
            continue
        used.add(kind)
        layers.append({"kind": kind, "gain": _round(rng.uniform(0.16, 0.48 if i == 0 else 0.32), 3)})
    root_pc, mode = _identity(dna, rarity, archetype)
    drone_notes = []
    if detail >= 1 or rng.random() < 0.48:
        for degree in [0, 4 if len(_SCALES[mode]) >= 5 else 0]:
            drone_notes.append(_midi_name(_degree_to_midi(root_pc, 2, mode, degree)))
    detail_events = []
    if detail >= 2:
        for i in range(detail):
            detail_events.append({
                "note": _midi_name(_degree_to_midi(root_pc, rng.choice([4, 5]), mode,
                                                   rng.randrange(len(_SCALES[mode])))),
                "time": _round(rng.uniform(0.4, 4.2), 3),
                "gain": _round(rng.uniform(0.07, 0.19), 3),
                "voice": rng.choice(["bell", "glass", "flute", "fm_bell", "whistle"]),
            })
    duration = _round(rng.uniform(4.0, 6.5), 2)
    desc = "A layered %s soundscape combining %s%s." % (
        archetype, ", ".join(layer["kind"].replace("_", " ") for layer in layers),
        " and a tonal drone" if drone_notes else "")
    return _base(dna, "ambience", "ambience", "ambience", rarity, archetype,
                 root_name=_root_name(root_pc), mode=mode, amb=layers[0]["kind"] if layers else "wind",
                 amb_layers=layers, drone_notes=drone_notes,
                 drone_timbre=_timbre_spec(dna, "drone-timbre", "pad", rarity, archetype),
                 detail_events=detail_events, dur=duration, length_steps=16,
                 effects=_component_effects(dna, "ambience-effects", rarity, archetype), desc=desc)


def _effect_chain(dna, rarity, archetype):
    rng = dna.rng("effect-chain")
    # Effects are valuable discoveries, so even common macros contain two safe stages.
    fake_rarity = rarity if rarity != "common" else "uncommon"
    chain = _component_effects(dna, "effect-macro", fake_rarity, archetype, subtle=False)
    if len(chain) < 2:
        chain.append(("reverb", {"amount": 0.22, "decay": 0.42}))
    chain = chain[:4]
    character = ", ".join(stage[0].replace("_", " ") for stage in chain)
    desc = "A generated track-effect macro combining %s in a controlled signal chain." % character
    return _base(dna, "effect", "effect", "effect", rarity, archetype,
                 fx="chain", fx_params={"chain": chain}, icon="crystal", desc=desc)


def generate(seed):
    """Generate one ComponentDNA v2 sound from ``seed``.

    The public default intentionally returns a versioned ``proc2`` id so old
    ``proc`` ids never change their sound when the generator evolves.
    """
    dna = DNA(seed)
    rarity = dna.weighted("rarity", _rarity.GEN_WEIGHTS)
    archetype = dna.choice("archetype", sorted(_ARCHETYPES))
    family = dna.weighted("family", _TYPE_WEIGHTS)

    if family == "note":
        return _single_note(dna, rarity, archetype, bass=False)
    if family == "bass_note":
        return _single_note(dna, rarity, archetype, bass=True)
    if family == "chord":
        return _single_chord(dna, rarity, archetype)
    if family == "drum":
        return _single_drum(dna, rarity, archetype)
    if family == "melody_loop":
        return _melody_loop(dna, rarity, archetype, bass=False)
    if family == "bass_loop":
        return _melody_loop(dna, rarity, archetype, bass=True)
    if family == "chord_loop":
        return _chord_loop(dna, rarity, archetype)
    if family == "rhythm":
        return _rhythm(dna, rarity, archetype)
    if family == "ambience":
        return _ambience(dna, rarity, archetype)
    return _effect_chain(dna, rarity, archetype)
