"""SongProfile: a gentle description of what a song *is* -- never how good it is.

The profile is a pure function of a :class:`cat_society.music.project.Project`
plus the component catalog.  It extracts simple, honest facts:

* tempo and a friendly tempo band (slow / easy / bright)
* which track families carry clips (melody? drums? chords? ...)
* a rough energy feel from how dense the grid is
* the *mood tags* of every component used (watery, night, bright, soft,
  playful, warm, airy, dreamy, animal)

Landmarks and animals read this profile through :func:`soft_check`, which only
ever answers "yes!" or offers one warm nudge.  There are no scores, no grades
and no failure -- by design.
"""

import math

from ..components import catalog

# ---------------------------------------------------------------------------
# Mood tags.  Components may declare explicit ``tags``; everything else is
# derived from what the component already knows about itself (region, voice,
# ambience kind, drum name, type), so the whole catalog -- including the
# infinite procedural components -- is tagged for free.
# ---------------------------------------------------------------------------
_REGION_TAGS = {
    "meadow":   ("soft",),
    "river":    ("watery",),
    "orchard":  ("warm",),
    "deepwood": ("night",),
    "animal":   ("playful",),
    "hidden":   ("dreamy",),
}

_VOICE_TAGS = {
    "music_box": ("soft", "bright"),
    "bell":      ("bright",),
    "glass":     ("bright",),
    "celeste":   ("bright",),
    "shimmer":   ("bright", "dreamy"),
    "toy_piano": ("warm", "playful"),
    "warm_pad":  ("soft", "warm"),
    "pluck":     ("soft",),
    "moon_pluck": ("night", "dreamy"),
    "soft_lead": ("soft",),
    "warm_bass": ("warm",),
    "purr":      ("soft", "animal"),
    "meow":      ("playful", "animal"),
    "croak":     ("playful", "animal", "watery"),
    "quack":     ("playful", "animal", "watery"),
    "hoot":      ("night", "animal"),
    "chirp":     ("playful", "animal"),
    "grand_piano": ("warm", "soft"),
    "electric_piano": ("warm", "dreamy"),
    "harp": ("soft", "airy"),
    "kalimba": ("playful", "warm"),
    "marimba": ("warm", "playful"),
    "vibraphone": ("dreamy", "bright"),
    "organ": ("warm",),
    "flute": ("airy", "soft"),
    "clarinet": ("warm", "soft"),
    "oboe": ("soft",),
    "strings": ("warm", "dreamy"),
    "choir": ("dreamy", "soft"),
    "analog_pad": ("warm", "dreamy"),
    "dream_pad": ("dreamy", "soft"),
    "supersaw": ("bright",),
    "fm_bell": ("bright", "dreamy"),
    "chiptune": ("playful", "bright"),
    "nylon_guitar": ("warm", "soft"),
    "koto": ("soft",),
    "dulcimer": ("bright", "warm"),
    "sitar": ("dreamy",),
    "steel_drum": ("bright", "playful", "watery"),
    "reed": ("airy",),
    "whistle": ("airy", "bright"),
    "brass": ("warm", "bright"),
    "muted_brass": ("warm",),
    "vox": ("soft", "dreamy"),
    "synth_pluck": ("bright", "dreamy"),
    "crystal_pad": ("bright", "dreamy"),
    "accordion": ("warm", "playful"),
    "sub_bass": ("soft",),
    "synth_bass": ("warm",),
    "acid_bass": ("bright",),
    "upright_bass": ("warm",),
    "fm_bass": ("bright",),
    "pluck_bass": ("warm",),
    "rubber_bass": ("playful",),
}

_AMB_TAGS = {
    "wind":     ("airy", "soft"),
    "river":    ("watery",),
    "birds":    ("bright",),
    "crickets": ("night",),
    "owl":      ("night",),
    "crackle":  ("warm",),
    "purr":     ("soft", "animal"),
    "rain": ("watery", "soft"),
    "storm": ("watery", "night"),
    "ocean": ("watery", "airy"),
    "waterfall": ("watery", "bright"),
    "cave": ("night", "dreamy"),
    "night_forest": ("night",),
    "leaves": ("airy", "soft"),
    "vinyl": ("warm", "soft"),
    "tape": ("warm", "soft"),
    "city": ("night",),
    "train": ("night",),
    "clock": ("soft",),
    "underwater": ("watery", "dreamy"),
    "snow": ("soft", "airy"),
    "bees": ("playful", "animal"),
    "distant_bells": ("bright", "dreamy"),
    "drone": ("night", "dreamy"),
    "fireplace": ("warm", "soft"),
    "meadow_night": ("night", "soft"),
    "space": ("dreamy", "airy"),
    "heartbeat": ("soft", "animal"),
}

_DRUM_TAGS = {
    "frog_pop":  ("playful", "watery"),
    "duck":      ("playful", "watery"),
    "bark":      ("playful",),
    "sheep_bell": ("playful",),
    "paw":       ("playful",),
    "shaker":    ("airy",),
    "bell_tick": ("bright",),
    "water_drop": ("watery", "playful"),
    "seed_shaker": ("airy",),
    "tambourine": ("bright",),
    "triangle": ("bright",),
    "ride": ("bright",),
    "crash": ("bright",),
    "finger_snap": ("playful",),
    "glitch_click": ("playful", "bright"),
    "cowbell": ("bright", "playful"),
    "woodblock": ("warm",),
    "hand_drum": ("warm",),
    "frame_drum": ("warm",),
}


def tags_for(comp):
    """The full mood-tag set of one component (explicit + derived)."""
    if comp is None:
        return set()
    tags = set(comp.get("tags", ()))
    tags.update(_REGION_TAGS.get(comp.get("region"), ()))
    tags.update(_VOICE_TAGS.get(comp.get("voice"), ()))
    tags.update(_AMB_TAGS.get(comp.get("amb"), ()))
    tags.update(_DRUM_TAGS.get(comp.get("drum"), ()))
    if comp.get("type") == "ambience":
        tags.add("soft")
    # rhythm patterns are made of drum names -- inherit their tags too
    for hit in comp.get("pattern", ()) or ():
        try:
            name = hit[0]
        except (TypeError, IndexError):
            continue
        if isinstance(name, str):
            tags.update(_DRUM_TAGS.get(name, ()))
    return tags


# ---------------------------------------------------------------------------
# The profile itself
# ---------------------------------------------------------------------------
class SongProfile:
    __slots__ = ("tempo", "band", "bars", "clip_count", "families",
                 "has_melody", "has_chords", "has_bass", "has_drums",
                 "energy", "tags", "tag_counts", "regions")

    def describe(self):
        """One friendly line, used by the journal."""
        bits = []
        if self.has_melody:
            bits.append("a melody")
        if self.has_chords:
            bits.append("chords")
        if self.has_drums:
            bits.append("a beat")
        what = ", ".join(bits) if bits else "a quiet sketch"
        return "%s song with %s" % (self.band, what)


_BAND = ((92, "slow"), (118, "easy"), (10 ** 9, "bright"))


def analyze(project):
    """Build a :class:`SongProfile` from a project.  Pure, cheap, judgment-free."""
    p = SongProfile()
    p.tempo = int(getattr(project, "tempo", 100))
    p.bars = int(getattr(project, "bars", 8))
    for cap, name in _BAND:
        if p.tempo <= cap:
            p.band = name
            break

    p.families = set()
    p.tags = set()
    p.tag_counts = {}
    p.regions = set()
    p.clip_count = 0
    weight = 0.0                     # step-weighted density for the energy feel

    for tr in getattr(project, "tracks", ()):
        if getattr(tr, "muted", False):
            continue
        clips = getattr(tr, "clips", ())
        if not clips:
            continue
        p.families.add(tr.kind)
        for c in clips:
            comp = catalog.get(c.comp_id)
            if comp is None:
                continue
            p.clip_count += 1
            ct = tags_for(comp)
            p.tags |= ct
            for tg in ct:
                p.tag_counts[tg] = p.tag_counts.get(tg, 0) + 1
            if comp.get("region"):
                p.regions.add(comp["region"])
            # loops and rhythms fill more of the bar than a single one-shot
            weight += 1.0 if comp.get("type") in ("note", "chord", "drum") \
                else max(1.0, comp.get("length_steps", 8) / 8.0)

    p.has_melody = bool({"melody", "loops"} & p.families)
    p.has_chords = "chords" in p.families
    p.has_bass = "bass" in p.families
    p.has_drums = bool({"drums", "rhythms"} & p.families)

    per_bar = weight / max(1, p.bars)
    if per_bar <= 1.15 and not p.has_drums:
        p.energy = "low"
    elif per_bar >= 3.0 or (p.has_drums and per_bar >= 2.2 and p.tempo > 118):
        p.energy = "high"
    else:
        p.energy = "mid"
    return p


def is_gentle(profile):
    """A soft, slow-ish feel -- what a shy animal needs before it comes close."""
    return profile.energy != "high" and profile.tempo <= 112


# ---------------------------------------------------------------------------
# Soft requirement checking.  A requirement is a plain dict:
#
#     {"any_tags": ["watery"], "max_tempo": 118, "needs": ["melody"],
#      "calm": True,
#      "nudges": {"any_tags": "...", "max_tempo": "...", ...}}
#
# ``soft_check`` returns ``(ok, nudge)``.  When ok is False the nudge is ONE
# warm sentence about the first missing ingredient -- never a score, never the
# word "wrong".
# ---------------------------------------------------------------------------
_NEED_ATTR = {"melody": "has_melody", "chords": "has_chords",
              "bass": "has_bass", "drums": "has_drums"}

_DEFAULT_NUDGE = {
    "empty":     "It listens... maybe a few more sounds?",
    "any_tags":  "It stirs a little... maybe a different kind of sound?",
    "needs":     "It sways... maybe a little melody?",
    "max_tempo": "It breathes slowly... maybe something a touch gentler?",
    "min_tempo": "It perks up... maybe something a little livelier?",
    "calm":      "It settles... maybe something softer?",
}


def soft_check(profile, req):
    nudges = req.get("nudges", {})

    def nudge(key):
        return nudges.get(key, _DEFAULT_NUDGE[key])

    if profile.clip_count < req.get("min_clips", 2):
        return False, nudge("empty")
    for need in req.get("needs", ()):
        if not getattr(profile, _NEED_ATTR.get(need, ""), False):
            return False, nudge("needs")
    want = req.get("any_tags")
    if want and not (set(want) & profile.tags):
        return False, nudge("any_tags")
    if req.get("calm") and profile.energy == "high":
        return False, nudge("calm")
    if profile.tempo > req.get("max_tempo", 10 ** 9):
        return False, nudge("max_tempo")
    if profile.tempo < req.get("min_tempo", 0):
        return False, nudge("min_tempo")
    return True, ""
