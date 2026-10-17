"""Focused structural/audio regression tests for the expanded Sound Atlas.

Run headless:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python _sound_atlas_test.py
"""

import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from collections import Counter
import numpy as np

from cat_society.audio import synth
from cat_society.components import catalog, procedural
from cat_society.music.project import Project
from cat_society.world.music_pickups import PickupManager
from cat_society.world.water import WaterWorld


passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    ok = bool(condition)
    print(("  ok  " if ok else "  FAIL") + "  " + name)
    passed += int(ok)
    failed += int(not ok)


def audible(comp):
    a = synth.render_component(comp, bpm=100)
    b = synth.render_component(comp, bpm=100)
    return (a.dtype == np.float32 and len(a) > 0 and np.isfinite(a).all()
            and float(np.max(np.abs(a))) > 1e-5 and np.array_equal(a, b))


class _EmptyWorld:
    @staticmethod
    def solids_near(x, z):
        return ()


class _EmptyCollection:
    @staticmethod
    def pickup_collected(iid):
        return False

    @staticmethod
    def owns(component_id):
        return False



def main():
    atlas = [c for c in catalog.ALL if c.get("pack") == "sound_atlas"]
    ids = [c["id"] for c in catalog.ALL]
    tracks = Counter(c.get("track") for c in atlas)

    check("Sound Atlas contains thousands of curated components",
          len(atlas) >= 2500 and catalog.SOUND_ATLAS_COUNT == len(atlas))
    check("whole catalog is close to three thousand entries", len(catalog.ALL) >= 2900)
    check("all component ids are unique", len(ids) == len(set(ids)))
    check("Atlas remains discoverable rather than granted at startup",
          all(not c.get("starter") and not c.get("reward") for c in atlas))
    check("every Music Maker family receives a large library",
          tracks["melody"] >= 900 and tracks["bass"] >= 180
          and tracks["chords"] >= 700 and tracks["loops"] >= 350
          and tracks["rhythms"] >= 150 and tracks["drums"] >= 80
          and tracks["ambience"] >= 100 and tracks["effect"] >= 60)

    voices = {c.get("voice") for c in atlas if c.get("voice")}
    drums = {c.get("drum") for c in atlas if c.get("drum")}
    ambiences = {c.get("amb") for c in atlas if c.get("amb")}
    effects = {c.get("fx") for c in atlas if c.get("fx")}
    check("instrument variety is broad", len(voices) >= 45)
    check("percussion variety is broad", len(drums) >= 40)
    check("ambience variety is broad", len(ambiences) >= 25)
    check("effect variety is broad", len(effects) >= 15)
    check("every Atlas voice has a real synth implementation",
          voices <= set(synth._VOICES))
    check("every Atlas drum has a real synth implementation",
          drums <= set(synth._DRUMS))

    pitches_ok = True
    for comp in atlas:
        try:
            if comp["type"] == "note":
                for note in comp.get("notes", ()):
                    synth.note_freq(note)
            elif comp["type"] == "chord":
                synth.chord_freqs(comp.get("root", "C"), comp.get("quality", "major"),
                                  comp.get("octave", 4))
            elif comp["type"] == "loop":
                for note, _, _ in comp.get("pattern", ()):
                    synth.note_freq(note)
        except (ValueError, KeyError, TypeError):
            pitches_ok = False
            break
    check("all curated pitches and chords are valid", pitches_ok)

    # One representative for every actual synth/scene/effect family plus an
    # evenly spaced catalog sample catches silent placeholders without making
    # this focused test render all ~3,000 entries.
    representatives = {}
    for comp in atlas:
        key = (comp["type"], comp.get("voice") or comp.get("drum")
               or comp.get("amb") or comp.get("fx"))
        representatives.setdefault(key, comp)
    stride = max(1, len(atlas) // 96)
    sample = list(representatives.values()) + atlas[::stride][:96]
    rendered_ok = True
    for comp in sample:
        try:
            if not audible(comp):
                rendered_ok = False
                print("      bad audio:", comp["id"])
                break
        except Exception as exc:
            rendered_ok = False
            print("      render exception:", comp["id"], type(exc).__name__, exc)
            break
    check("representative Atlas sounds are audible and deterministic", rendered_ok)

    # Atlas ids survive normal project serialization and resolve on reload.
    project = Project("Atlas Test")
    chosen = {}
    for family in ("melody", "chords", "drums", "loops"):
        comp = next(c for c in atlas if c.get("track") == family)
        track = next(t for t in project.tracks if t.kind == family)
        track.add(comp["id"], 0)
        chosen[family] = comp["id"]
    reloaded = Project.from_dict(project.to_dict())
    used = reloaded.components_used()
    check("Atlas clips survive project save/reload",
          set(chosen.values()) <= set(used) and all(catalog.get(cid) for cid in used))

    # Existing world slots remain untouched; Atlas content occupies only new
    # slots 2/3 and every discoverable curated entry is assigned exactly once.
    manager = PickupManager.__new__(PickupManager)
    manager._curated_at = {}
    manager._assign_curated()
    assigned_atlas = {v["id"] for k, v in manager._curated_at.items()
                      if v.get("pack") == "sound_atlas"}
    atlas_ids = {c["id"] for c in atlas}
    check("every Atlas component has one deterministic world placement",
          assigned_atlas == atlas_ids)
    check("Atlas uses the save-compatible new pickup slot",
          all(k[2] == 2 for k, v in manager._curated_at.items()
              if v.get("pack") == "sound_atlas"))
    check("legacy curated sounds remain in original slot zero",
          all(k[2] == 0 for k, v in manager._curated_at.items()
              if v.get("pack") != "sound_atlas"))

    # A structural assignment is not enough: finite authored sounds must also
    # resolve to dry, spawnable coordinates in the real procedural water field.
    # This catches accidental placement in the infinite ocean half-plane.
    reachable_manager = PickupManager(_EmptyWorld(), WaterWorld(), _EmptyCollection())
    atlas_by_cell = {
        key[:2]: comp["id"]
        for key, comp in reachable_manager._curated_at.items()
        if comp.get("pack") == "sound_atlas"
    }
    reachable = set()
    for cell in atlas_by_cell:
        for pickup in reachable_manager._gen_cell(cell):
            if pickup.comp.get("pack") == "sound_atlas":
                reachable.add(pickup.comp["id"])
    check("every Atlas discovery resolves to reachable dry ground",
          reachable == atlas_ids)

    # Adding slot 2 must not perturb the old deterministic slots 0/1.  Compare
    # the same cell with and without its Atlas entry and require identical old
    # pickup ids and coordinates.
    legacy_unchanged = False
    for atlas_key, atlas_comp in list(reachable_manager._curated_at.items()):
        if atlas_comp.get("pack") != "sound_atlas":
            continue
        cell = atlas_key[:2]
        with_atlas = [
            (p.iid, p.x, p.z, p.comp["id"])
            for p in reachable_manager._gen_cell(cell)
            if p.iid.rsplit(":", 1)[-1] in ("0", "1")
        ]
        if not with_atlas:
            continue
        del reachable_manager._curated_at[atlas_key]
        without_atlas = [
            (p.iid, p.x, p.z, p.comp["id"])
            for p in reachable_manager._gen_cell(cell)
            if p.iid.rsplit(":", 1)[-1] in ("0", "1")
        ]
        reachable_manager._curated_at[atlas_key] = atlas_comp
        legacy_unchanged = with_atlas == without_atlas
        break
    check("Atlas placement does not perturb legacy procedural slots",
          legacy_unchanged)

    generated_world_ids = []
    for cx in range(-12, 13):
        for cz in range(-12, 13):
            for pickup in reachable_manager._gen_cell((cx, cz)):
                if pickup.comp.get("proc"):
                    generated_world_ids.append(pickup.comp["id"])
            if len(generated_world_ids) >= 20:
                break
        if len(generated_world_ids) >= 20:
            break
    check("new infinite world pickups use versioned ComponentDNA ids",
          len(generated_world_ids) >= 10
          and all(cid.startswith("proc2.") for cid in generated_world_ids))

    # Infinite generation remains active through versioned ComponentDNA ids.
    # Historical proc.<seed> sounds must also remain reconstructable for saves.
    proc_types = Counter()
    proc_families = Counter()
    proc_archetypes = set()
    custom_timbres = custom_kits = layered_ambiences = effect_macros = 0
    proc_ok = True
    for seed in range(1, 1001):
        comp = procedural.generate(seed)
        rebuilt = procedural.from_id(comp["id"])
        if rebuilt != comp or not comp["id"].startswith("proc2."):
            proc_ok = False
            break
        proc_types[comp["type"]] += 1
        proc_families[comp.get("dna", {}).get("family")] += 1
        proc_archetypes.add(comp.get("dna", {}).get("archetype"))
        custom_timbres += bool(comp.get("timbre"))
        custom_kits += bool(comp.get("drum_kit") or comp.get("drum_spec"))
        layered_ambiences += bool(comp.get("amb_layers"))
        effect_macros += comp.get("fx") == "chain"
    legacy_ok = all(procedural.from_id("proc.%d" % seed)
                    == procedural.generate_legacy(seed)
                    for seed in (1, 2, 42, 99, 12345))
    check("infinite procedural reconstruction remains exact", proc_ok)
    check("historical procedural ids remain save-compatible", legacy_ok)
    check("procedural generation still covers every component class",
          {"note", "chord", "drum", "loop", "rhythm", "ambience", "effect"} <= set(proc_types))
    check("ComponentDNA covers every advanced musical family",
          {"note", "bass_note", "chord", "drum", "melody_loop", "bass_loop",
           "chord_loop", "rhythm", "ambience", "effect"} <= set(proc_families))
    check("procedural generation uses advanced synthesis structures",
          custom_timbres >= 450 and custom_kits >= 150
          and layered_ambiences >= 40 and effect_macros >= 10
          and len(proc_archetypes) == 12)

    print("\nSound Atlas entries:", len(atlas))
    print("Whole catalog:", len(catalog.ALL))
    print("Tracks:", dict(sorted(tracks.items())))
    print("Variety: %d voices, %d drums, %d ambiences, %d effects"
          % (len(voices), len(drums), len(ambiences), len(effects)))
    print("\nRESULT: %d passed, %d failed" % (passed, failed))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
