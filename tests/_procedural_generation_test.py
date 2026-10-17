"""Regression and quality tests for ComponentDNA v2.

Run headless:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python _procedural_generation_test.py
"""

import hashlib
import json
import math
import os
from collections import Counter, defaultdict

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np

from cat_society.audio import export, synth
from cat_society.components import catalog, procedural
from cat_society.music.project import Project


PASSED = 0
FAILED = 0


def check(label, condition):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print("  ok   ", label)
    else:
        FAILED += 1
        print("  FAIL ", label)


def finite_tree(value):
    if isinstance(value, dict):
        return all(finite_tree(k) and finite_tree(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(finite_tree(v) for v in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return True


def valid_note(note):
    try:
        midi = synth.note_to_midi(note)
        return 12 <= midi <= 120
    except (TypeError, ValueError):
        return False


def validate_component(comp):
    required = {"id", "name", "type", "track", "rarity", "proc", "dna", "desc"}
    if not required <= set(comp):
        return False
    if not comp["id"].startswith("proc2.") or comp.get("proc_version") != 2:
        return False
    if comp["rarity"] not in ("common", "uncommon", "rare", "secret"):
        return False
    if comp["track"] not in ("melody", "chords", "bass", "drums", "rhythms",
                              "loops", "ambience", "effect"):
        return False
    if not finite_tree(comp):
        return False
    try:
        json.dumps(comp, sort_keys=True)
    except (TypeError, ValueError):
        return False

    typ = comp["type"]
    if typ == "note":
        if not comp.get("notes") or not all(valid_note(n) for n in comp["notes"]):
            return False
    elif typ == "chord":
        if comp.get("notes") and not all(valid_note(n) for n in comp["notes"]):
            return False
    elif typ == "loop":
        length = float(comp.get("length_steps", 0))
        if length <= 0:
            return False
        for event in comp.get("pattern", ()):
            if len(event) < 3:
                return False
            notes, step, dur = event[:3]
            notes = notes if isinstance(notes, (list, tuple)) else [notes]
            if not notes or not all(valid_note(n) for n in notes):
                return False
            if not (0 <= float(step) < length and 0 < float(dur) <= length):
                return False
    elif typ == "rhythm":
        length = float(comp.get("length_steps", 0))
        kit = comp.get("drum_kit") or {}
        if length <= 0 or not kit:
            return False
        for event in comp.get("pattern", ()):
            if len(event) < 2 or event[0] not in kit or not (0 <= float(event[1]) < length):
                return False
    elif typ == "drum":
        if not comp.get("drum_spec"):
            return False
    elif typ == "ambience":
        if not comp.get("amb_layers"):
            return False
    elif typ == "effect":
        if comp.get("fx") != "chain" or len(comp.get("fx_params", {}).get("chain", ())) < 2:
            return False
    return True


def structure_hash(comp):
    item = json.loads(json.dumps(comp))
    for key in ("id", "name", "desc", "origin", "region"):
        item.pop(key, None)
    item.get("dna", {}).pop("seed", None)
    return hashlib.sha256(json.dumps(item, sort_keys=True).encode("utf-8")).hexdigest()


def complexity_score(comp):
    return (len(comp.get("layers", ())) + len(comp.get("effects", ()))
            + len(comp.get("drum_kit", {})) + len(comp.get("amb_layers", ()))
            + len(comp.get("detail_events", ())) + len(comp.get("pattern", ())) / 12.0)


def main():
    # Historical save compatibility: these dictionaries were captured from v18
    # before ComponentDNA v2 existed.
    expected_42 = {
        "name": "Misty Chime D4", "type": "note", "voice": "organ",
        "notes": ["D4"], "track": "melody", "icon": "note",
        "desc": "A misty organ note (D4).", "id": "proc.42",
        "rarity": "common", "proc": True, "origin": "Clearing",
        "color": (255, 224, 150),
    }
    expected_99 = {
        "name": "Frost A Maj7", "type": "chord", "voice": "crystal_pad",
        "root": "A", "quality": "maj7", "octave": 5, "track": "chords",
        "icon": "cluster", "desc": "A frost A Maj7 chord.", "id": "proc.99",
        "rarity": "secret", "proc": True, "origin": "Hollow",
        "color": (255, 176, 156),
    }
    check("legacy proc.42 is byte-compatible", procedural.from_id("proc.42") == expected_42)
    check("legacy proc.99 is byte-compatible", procedural.from_id("proc.99") == expected_99)
    check("malformed procedural ids fail safely",
          all(procedural.from_id(value) is None for value in
              (None, "proc.", "proc2.", "proc.nope", "proc2.-x", "other.4")))

    sample_count = 5000
    families = Counter()
    archetypes = set()
    tracks = Counter()
    rarity_scores = defaultdict(list)
    structures = set()
    valid = roundtrip = True
    names = set()
    custom_timbres = custom_drums = layered_amb = macros = poly_loops = 0

    for seed in range(1, sample_count + 1):
        comp = procedural.generate(seed)
        valid = valid and validate_component(comp)
        roundtrip = roundtrip and procedural.from_id(comp["id"]) == comp
        families[comp["dna"]["family"]] += 1
        archetypes.add(comp["dna"]["archetype"])
        tracks[comp["track"]] += 1
        rarity_scores[comp["rarity"]].append(complexity_score(comp))
        structures.add(structure_hash(comp))
        names.add(comp["name"])
        custom_timbres += bool(comp.get("timbre"))
        custom_drums += bool(comp.get("drum_spec") or comp.get("drum_kit"))
        layered_amb += bool(comp.get("amb_layers"))
        macros += comp.get("fx") == "chain"
        poly_loops += any(isinstance(event[0], (list, tuple))
                          for event in comp.get("pattern", ()))

    check("all generated dictionaries are valid and serializable", valid)
    check("proc2 ids reconstruct exactly", roundtrip)
    check("all ten musical generator families appear",
          set(families) == {"note", "bass_note", "chord", "drum", "melody_loop",
                            "bass_loop", "chord_loop", "rhythm", "ambience", "effect"})
    check("all Music Maker destinations receive generated material",
          set(tracks) == {"melody", "chords", "bass", "drums", "rhythms",
                          "loops", "ambience", "effect"})
    check("all twelve style archetypes appear", len(archetypes) == 12)
    check("structural variety is effectively seed-level",
          len(structures) >= int(sample_count * 0.995))
    check("display names have strong practical variety", len(names) >= int(sample_count * 0.94))
    check("advanced structures occur at useful rates",
          custom_timbres >= 3000 and custom_drums >= 900 and layered_amb >= 250
          and macros >= 100 and poly_loops >= 300)

    averages = {rarity: sum(values) / len(values)
                for rarity, values in rarity_scores.items()}
    check("rarity increases average generative complexity",
          averages["common"] < averages["uncommon"] < averages["rare"] < averages["secret"])

    # Rendering and export-path compatibility across a broad deterministic sample.
    render_seeds = list(range(1, 81)) + [101, 137, 211, 377, 610, 987, 1597, 2584]
    audible = deterministic = unique_audio = project_safe = True
    audio_hashes = set()
    for seed in render_seeds:
        comp = procedural.generate(seed)
        first = synth.render_component(comp, bpm=103)
        second = synth.render_component(comp, bpm=103)
        audible = audible and len(first) > 100 and float(np.max(np.abs(first))) > 1e-4
        deterministic = deterministic and np.array_equal(first, second)
        audio_hashes.add(hashlib.sha1(first.tobytes()).hexdigest())

        if comp["track"] != "effect":
            project = Project("DNA", tempo=103, bars=max(4, int(math.ceil(
                synth.clip_length_steps(comp) / synth.STEPS_PER_BAR))))
            track = next((t for t in project.tracks if t.accepts(comp)), None)
            if track is None:
                track = project.add_track(comp["track"])
            track.add(comp["id"], 0)
            loaded = Project.from_dict(project.to_dict())
            project_safe = project_safe and loaded.clip_count() == 1 \
                           and catalog.get(comp["id"]) == comp

    unique_audio = len(audio_hashes) >= int(len(render_seeds) * 0.97)
    check("sampled ComponentDNA sounds are audible", audible)
    check("sampled ComponentDNA rendering is deterministic", deterministic)
    check("sampled waveforms are overwhelmingly unique", unique_audio)
    check("proc2 clips survive project serialization", project_safe)

    # One representative from every placeable family must survive the actual
    # project mixer with the same waveform shape used by collect/browser preview.
    representatives = {}
    for seed in range(1, 5000):
        comp = procedural.generate(seed)
        family = comp["dna"]["family"]
        if family != "effect" and family not in representatives:
            representatives[family] = comp
        if len(representatives) == 9:
            break
    mixer_ok = True
    for comp in representatives.values():
        bars = max(1, int(math.ceil(synth.clip_length_steps(comp) / synth.STEPS_PER_BAR)))
        project = Project("Mixer DNA", tempo=103, bars=bars)
        track = next((t for t in project.tracks if t.accepts(comp)), None)
        if track is None:
            track = project.add_track(comp["track"])
        track.volume = 1.0
        track.add(comp["id"], 0)
        mixed = export.render_project(project, loop=False, samples={})
        expected = synth.render_component(comp, bpm=103)
        if comp["type"] == "ambience":
            expected = synth.fit_to_steps(expected, synth.clip_length_steps(comp), 103)
        span = min(len(expected), len(mixed),
                   int(synth.clip_length_steps(comp) * synth.sec_per_step(103) * synth.SR))
        a = expected[:span].astype(np.float64)
        b = mixed[:span].astype(np.float64)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        correlation = float(np.dot(a, b) / denom) if denom > 1e-12 else 0.0
        mixer_ok = mixer_ok and correlation > 0.98
    check("every generated clip family matches the real project mixer", mixer_ok)

    # Effect macros must process rather than silently return their input.
    effect_comp = next(procedural.generate(seed) for seed in range(1, 1000)
                       if procedural.generate(seed)["type"] == "effect")
    source = synth.voice("bell", synth.note_freq("C5"), 0.7)
    effected = synth.apply_effect(source, effect_comp["fx"], effect_comp["fx_params"])
    n = min(len(source), len(effected))
    check("generated effect macros audibly transform a signal",
          len(effected) >= len(source) and not np.array_equal(source[:n], effected[:n]))

    print("\nFamilies:", dict(sorted(families.items())))
    print("Tracks:", dict(sorted(tracks.items())))
    print("Complexity averages:", {k: round(v, 3) for k, v in averages.items()})
    print("Distinct structures: %d / %d" % (len(structures), sample_count))
    print("\nRESULT: %d passed, %d failed" % (PASSED, FAILED))
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
