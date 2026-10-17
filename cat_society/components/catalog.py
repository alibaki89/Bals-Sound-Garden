"""The component catalog and the world regions they live in.

Every entry is a plain dict.  The synth (:mod:`cat_society.audio.synth`) reads
the musical fields; the UI reads the presentation fields.  Components are
grouped into named *regions* which the explore map scatters them across.

Presentation fields
    id        unique string id (also the save key)
    name      display name
    type      note | chord | drum | rhythm | loop | ambience | effect | user
    track     which music-maker track it can be placed on
    rarity    common | uncommon | rare | secret
    region    region key (see REGIONS)
    desc      one-line flavour / usage text
    icon      icon style drawn by the pickup + card
    color     (r,g,b) theme tint
    starter   True -> unlocked from the start (no pickup placed)

Musical fields (consumed by synth.render_component)
    voice / notes / root / quality / octave / drum / pattern /
    length_steps / amb / fx / fx_params / effects / dur

ComponentDNA v2 may additionally provide data-only synthesis structures:
    timbre / layers / strum_ms / strum_direction / drum_spec / drum_kit /
    amb_layers / drone_notes / drone_timbre / detail_events / dna
"""

# ---------------------------------------------------------------------------
# Regions  (key -> metadata).  Centres are world coordinates; pickups for a
# region are scattered within ``radius`` of its centre.
# ---------------------------------------------------------------------------
REGIONS = {
    "meadow":   dict(name="Meadow of First Notes", cx=0,     cz=620,  radius=620,
                     color=(120, 196, 116)),
    "rhythm":   dict(name="Rhythm Path",           cx=1280,  cz=980,  radius=620,
                     color=(214, 158, 96)),
    "river":    dict(name="Riverbank",             cx=-1320, cz=1180, radius=640,
                     color=(94, 182, 199)),
    "orchard":  dict(name="Grove of Chords",       cx=1520,  cz=2060, radius=660,
                     color=(240, 158, 148)),
    "deepwood": dict(name="Deepwood",              cx=-1640, cz=2680, radius=700,
                     color=(140, 130, 200)),
    "animal":   dict(name="Animal Corners",        cx=620,   cz=1880, radius=720,
                     color=(236, 200, 120)),
    "hidden":   dict(name="Hidden Clearings",      cx=2500,  cz=3300, radius=760,
                     color=(250, 224, 150)),
    # not a place on the map: the journal shelf for landmark rewards and the
    # little thank-you sounds animal friends leave behind
    "gifts":    dict(name="Commission Pay",    cx=0,     cz=0,    radius=0,
                     color=(246, 176, 186)),
}

# rarity -> (glow color, label)
RARITY = {
    "common":   ((176, 214, 150), "Common"),
    "uncommon": ((150, 206, 224), "Uncommon"),
    "rare":     ((212, 168, 236), "Rare"),
    "secret":   ((250, 224, 150), "Secret"),
}

TRACK_NAMES = ["melody", "chords", "bass", "drums", "rhythms", "loops",
               "ambience", "user"]

# default icon per type
_ICON = {"note": "note", "chord": "cluster", "drum": "stone",
         "rhythm": "rune", "loop": "cassette", "ambience": "orb",
         "effect": "crystal", "user": "tape"}

# default theme tint per type
_TINT = {"note": (255, 214, 130), "chord": (255, 168, 150),
         "drum": (210, 180, 150), "rhythm": (230, 196, 120),
         "loop": (170, 210, 235), "ambience": (190, 200, 235),
         "effect": (210, 170, 236), "user": (200, 230, 200)}


_COMPONENTS = []


def _add(**kw):
    kw.setdefault("rarity", "common")
    kw.setdefault("region", "meadow")
    kw.setdefault("starter", False)
    kw.setdefault("icon", _ICON.get(kw["type"], "note"))
    kw.setdefault("color", _TINT.get(kw["type"], (255, 214, 130)))
    _COMPONENTS.append(kw)


def _note(cid, name, voice, note, track="melody", **kw):
    _add(id=cid, name=name, type="note", voice=voice, notes=[note],
         track=track, desc=kw.pop("desc", f"A single {voice.replace('_', ' ')} note ({note})."),
         **kw)


def _chord(cid, name, voice, root, quality, octave=4, **kw):
    q = quality
    pretty = {"major": "Major", "minor": "Minor"}.get(q, q)
    _add(id=cid, name=name, type="chord", voice=voice, root=root, quality=q,
         octave=octave, track="chords",
         desc=kw.pop("desc", f"A {root} {pretty} chord on {voice.replace('_', ' ')}."),
         **kw)


def _drum(cid, name, drum, **kw):
    _add(id=cid, name=name, type="drum", drum=drum, track="drums",
         desc=kw.pop("desc", "A single percussive hit."), **kw)


def _rhythm(cid, name, pattern, length=8, **kw):
    _add(id=cid, name=name, type="rhythm", pattern=pattern, length_steps=length,
         track="rhythms", desc=kw.pop("desc", "A ready-made rhythm pattern."), **kw)


def _loop(cid, name, voice, pattern, length=16, **kw):
    _add(id=cid, name=name, type="loop", voice=voice, pattern=pattern,
         length_steps=length, track="loops",
         desc=kw.pop("desc", "A short melodic phrase."), **kw)


def _amb(cid, name, amb, length=16, **kw):
    _add(id=cid, name=name, type="ambience", amb=amb, length_steps=length,
         dur=kw.pop("dur", 4.0), track="ambience",
         desc=kw.pop("desc", "A soft background layer."), **kw)


def _fx(cid, name, fx, fx_params=None, **kw):
    _add(id=cid, name=name, type="effect", fx=fx, fx_params=fx_params or {},
         track="effect", desc=kw.pop("desc", "An effect for a track."), **kw)


# ===========================================================================
# STARTER PACK  (unlocked from the start so Music Maker works immediately)
# ===========================================================================
_note("mb_c4", "Music Box C4", "music_box", "C4", region="meadow", starter=True)
_note("mb_e4", "Music Box E4", "music_box", "E4", region="meadow", starter=True)
_note("mb_g4", "Music Box G4", "music_box", "G4", region="meadow", starter=True)
_drum("soft_kick", "Soft Kick", "kick", region="rhythm", starter=True)
_drum("paw_snare", "Paw Tap Snare", "snare", region="rhythm", starter=True)
_drum("twig_hat", "Twig Hi-Hat", "hat", region="rhythm", starter=True)
_chord("tp_cmaj", "Toy Piano C Major", "toy_piano", "C", "major",
       region="orchard", starter=True)
_note("warm_bass_c", "Warm Bass C", "warm_bass", "C3", track="bass",
      region="orchard", starter=True, desc="A round, warm bass note (C3).")
_amb("meadow_air", "Meadow Air Loop", "wind", region="meadow", starter=True,
     desc="A gentle open-meadow air bed.")
_fx("soft_reverb", "Soft Reverb", "reverb", {"amount": 0.32, "decay": 0.5},
    region="meadow", starter=True, desc="A soft room reverb for any track.")

# ===========================================================================
# NOTES  (Meadow + scattered)
# ===========================================================================
_note("mb_d4", "Music Box D4", "music_box", "D4", region="meadow")
_note("mb_f4", "Music Box F4", "music_box", "F4", region="meadow")
_note("mb_a4", "Music Box A4", "music_box", "A4", region="meadow")
_note("mb_b4", "Music Box B4", "music_box", "B4", region="meadow")
_note("bell_c5", "Soft Bell C5", "bell", "C5", region="meadow", rarity="uncommon")
_note("bell_d5", "Soft Bell D5", "bell", "D5", region="meadow", rarity="uncommon")
_note("bell_e5", "Soft Bell E5", "bell", "E5", region="meadow", rarity="uncommon")
_note("bell_g5", "Soft Bell G5", "bell", "G5", region="meadow", rarity="uncommon")
_note("bell_a5", "Soft Bell A5", "bell", "A5", region="meadow", rarity="uncommon")
_note("tp_c4", "Toy Piano C4", "toy_piano", "C4", region="orchard")
_note("tp_d4", "Toy Piano D4", "toy_piano", "D4", region="orchard")
_note("tp_e4", "Toy Piano E4", "toy_piano", "E4", region="orchard")
_note("tp_g4", "Toy Piano G4", "toy_piano", "G4", region="orchard")
_note("tp_a4", "Toy Piano A4", "toy_piano", "A4", region="orchard")
_note("moon_c5", "Moon Pluck C5", "moon_pluck", "C5", region="deepwood", rarity="uncommon")
_note("moon_e5", "Moon Pluck E5", "moon_pluck", "E5", region="deepwood", rarity="uncommon")
_note("moon_g5", "Moon Pluck G5", "moon_pluck", "G5", region="deepwood", rarity="uncommon")

# ===========================================================================
# CHORDS  (Orchard / Grove)
# ===========================================================================
_chord("tp_fmaj", "Toy Piano F Major", "toy_piano", "F", "major", region="orchard")
_chord("tp_gmaj", "Toy Piano G Major", "toy_piano", "G", "major", region="orchard")
_chord("tp_amin", "Toy Piano A Minor", "toy_piano", "A", "minor", region="orchard")
_chord("pad_cmaj", "Warm Pad C Major", "warm_pad", "C", "major", region="orchard", rarity="uncommon")
_chord("pad_fmaj", "Warm Pad F Major", "warm_pad", "F", "major", region="orchard", rarity="uncommon")
_chord("pad_gmaj", "Warm Pad G Major", "warm_pad", "G", "major", region="orchard", rarity="uncommon")
_chord("pad_amin", "Warm Pad A Minor", "warm_pad", "A", "minor", region="orchard", rarity="uncommon")
_chord("dream_cmaj", "Dream Bell C Major", "bell", "C", "major", octave=5, region="hidden", rarity="rare")
_chord("dream_gmaj", "Dream Bell G Major", "bell", "G", "major", octave=4, region="hidden", rarity="rare")
_chord("forest_dmin", "Forest Pad D Minor", "warm_pad", "D", "minor", region="deepwood", rarity="rare")
_chord("golden_fmaj", "Golden Bell F Major", "glass", "F", "major", octave=5, region="hidden", rarity="rare")

# ===========================================================================
# DRUMS  (Rhythm Path + animals)
# ===========================================================================
_drum("deep_kick", "Deep Soft Kick", "deep_kick", region="rhythm")
_drum("brush_snare", "Brush Snare", "brush_snare", region="rhythm")
_drum("open_hat", "Open Twig Hat", "open_hat", region="rhythm")
_drum("pebble_click", "Pebble Click", "pebble", region="rhythm")
_drum("pebble_shaker", "Pebble Shaker", "shaker", region="rhythm")
_drum("hollow_log", "Hollow Log Hit", "log", region="rhythm")
_drum("tiny_clap", "Tiny Clap", "clap", region="rhythm")
_drum("bell_tick", "Bell Tick", "bell_tick", region="rhythm", rarity="uncommon")
_drum("paw_step", "Paw Step Percussion", "paw", region="animal")
_drum("frog_pop", "Frog Pop", "frog_pop", region="river", rarity="uncommon")
_drum("duck_quack", "Duck Quack Hit", "duck", region="animal", rarity="uncommon")
_drum("sheep_bell", "Sheep Bell Hit", "sheep_bell", region="animal", rarity="uncommon")
_drum("dog_bark", "Dog Bark Percussion", "bark", region="animal", rarity="uncommon")

# ===========================================================================
# RHYTHMS  (Rhythm Path)
# ===========================================================================
_rhythm("rh_meadow", "Meadow Step", [("kick", 0), ("hat", 2), ("snare", 4), ("hat", 6)],
        region="rhythm")
_rhythm("rh_lazy", "Lazy Walk", [("kick", 0), ("hat", 1), ("hat", 3), ("snare", 4),
        ("hat", 5), ("hat", 7)], region="rhythm")
_rhythm("rh_catpaw", "Cat Paw Beat", [("kick", 0), ("paw", 2), ("kick", 4), ("paw", 6)],
        region="animal")
_rhythm("rh_river", "River Pulse", [("shaker", 0), ("shaker", 1), ("shaker", 2),
        ("shaker", 3), ("kick", 0), ("shaker", 4), ("shaker", 5), ("kick", 4),
        ("shaker", 6), ("shaker", 7)], region="river")
_rhythm("rh_march", "Tiny March", [("kick", 0), ("hat", 1), ("kick", 2), ("snare", 4),
        ("hat", 5), ("kick", 6)], region="rhythm")
_rhythm("rh_swing", "Sleepy Swing", [("kick", 0), ("hat", 2), ("snare", 5), ("hat", 6)],
        region="deepwood", rarity="uncommon")
_rhythm("rh_waltz", "Moon Waltz", [("kick", 0), ("hat", 2), ("hat", 4)], length=6,
        region="deepwood", rarity="rare")
_rhythm("rh_shuffle", "Pebble Shuffle", [("pebble", 0), ("pebble", 1), ("pebble", 3),
        ("pebble", 4), ("pebble", 6), ("pebble", 7), ("kick", 0)], region="rhythm")
_rhythm("rh_frog", "Frog Hop Rhythm", [("frog_pop", 0), ("frog_pop", 3), ("frog_pop", 6),
        ("kick", 0)], region="river", rarity="uncommon")
_rhythm("rh_picnic", "Picnic Groove", [("kick", 0), ("hat", 2), ("snare", 4), ("clap", 4),
        ("hat", 6), ("kick", 4)], region="orchard")
_rhythm("rh_dreamwaltz", "Dream Waltz Rhythm", [("bell_tick", 0), ("hat", 2), ("hat", 4)],
        length=6, region="hidden", rarity="secret")

# ===========================================================================
# LOOPS  (phrases)
# ===========================================================================
_loop("lp_river_arp", "River Arpeggio Loop", "pluck",
      [("C4", 0, 2), ("E4", 2, 2), ("G4", 4, 2), ("C5", 6, 2), ("G4", 8, 2),
       ("E4", 10, 2), ("C4", 12, 2), ("E4", 14, 2)], region="river", rarity="uncommon",
      desc="A flowing two-bar pattern gathered from the riverbank.")
_loop("lp_picnic", "Picnic Chord Loop", "toy_piano",
      [("C4", 0, 4), ("E4", 0, 4), ("G4", 0, 4), ("A3", 8, 4), ("C4", 8, 4),
       ("E4", 8, 4)], region="orchard", rarity="uncommon",
      desc="Cozy two-chord toy-piano backing.")
_loop("lp_lullaby", "Forest Lullaby Motif", "music_box",
      [("E4", 0, 2), ("G4", 2, 2), ("A4", 4, 4), ("G4", 8, 2), ("E4", 10, 2),
       ("D4", 12, 4)], region="deepwood", rarity="rare",
      desc="A soft lullaby motif from the deep woods.")
_loop("lp_butterfly", "Butterfly Melody", "celeste",
      [("G5", 0, 1), ("A5", 1, 1), ("C6", 2, 2), ("A5", 4, 1), ("G5", 5, 1),
       ("E5", 6, 2)], length=8, region="orchard", rarity="rare",
      desc="A light, fluttering high melody.")
_loop("lp_catwalk", "Catwalk Bassline", "warm_bass",
      [("C3", 0, 2), ("C3", 3, 1), ("G2", 4, 2), ("A2", 6, 2), ("F2", 8, 2),
       ("F2", 11, 1), ("G2", 12, 4)], region="animal", rarity="uncommon",
      desc="A walking bass groove with a strut.")
_loop("lp_dreambells", "Dream Bells Loop", "bell",
      [("C5", 0, 2), ("G5", 2, 2), ("E5", 4, 2), ("C5", 6, 2), ("D5", 8, 2),
       ("G5", 10, 2), ("E5", 12, 4)], region="hidden", rarity="rare",
      desc="Shimmering bell arpeggio.")
_loop("lp_rainy", "Rainy Window Loop", "pluck",
      [("A4", 0, 2), ("E4", 2, 2), ("A4", 4, 2), ("C5", 6, 2), ("B4", 8, 2),
       ("E4", 10, 2), ("A4", 12, 4)], region="river", rarity="uncommon",
      effects=[("delay", {"time": 0.22, "mix": 0.3})],
      desc="A wistful plucked phrase with rain-like echoes.")
_loop("lp_secret_lullaby", "Secret Lullaby Loop", "music_box",
      [("A4", 0, 2), ("C5", 2, 2), ("E5", 4, 4), ("D5", 8, 2), ("C5", 10, 2),
       ("A4", 12, 4)], region="hidden", rarity="secret",
      desc="A hidden lullaby few cats have heard.")
_loop("lp_moongarden", "Moon Garden Loop", "moon_pluck",
      [("E4", 0, 2), ("G4", 2, 2), ("B4", 4, 2), ("E5", 6, 2), ("B4", 8, 2),
       ("G4", 10, 2), ("E4", 12, 4)], region="hidden", rarity="secret",
      desc="A glowing moonlit garden phrase.")
_loop("lp_brook", "Brook Pulse Loop", "pluck",
      [("G4", 0, 1), ("G4", 2, 1), ("C5", 4, 1), ("C5", 6, 1), ("E5", 8, 1),
       ("E5", 10, 1), ("C5", 12, 2)], length=16, region="river",
      desc="A bubbling, pulsing brook pattern.")

# ===========================================================================
# AMBIENCE / TEXTURES
# ===========================================================================
_amb("amb_softwind", "Soft Wind", "wind", region="meadow")
_amb("amb_riverbed", "River Bed", "river", region="river", rarity="uncommon")
_amb("amb_birds", "Bird Morning", "birds", region="meadow", rarity="uncommon")
_amb("amb_crickets", "Night Crickets", "crickets", region="deepwood", rarity="uncommon")
_amb("amb_purr", "Cat Purr Drone", "purr", region="animal", rarity="uncommon")
_amb("amb_distwind", "Distant Wind Bed", "wind", region="deepwood")
_amb("amb_crackle", "Warm Crackle", "crackle", region="orchard", rarity="uncommon")
_amb("amb_owl", "Owl Hoot Texture", "owl", region="deepwood", rarity="rare")
_amb("amb_rain", "Rain Texture Bed", "river", region="river", rarity="uncommon",
     effects=[("highpass", {"cutoff": 1500})], desc="A soft pattering rain bed.")

# ===========================================================================
# EFFECTS
# ===========================================================================
_fx("fx_echo", "Echo Crystal", "echo", {"time": 0.3, "feedback": 0.42, "mix": 0.35},
    region="hidden", rarity="rare")
_fx("fx_ripple", "Ripple Delay", "ripple_delay", {"time": 0.14, "mix": 0.4},
    region="river", rarity="uncommon")
_fx("fx_lowpass", "Low-Pass Mist", "lowpass", {"cutoff": 800}, region="deepwood",
    rarity="uncommon")
_fx("fx_highpass", "High-Pass Breeze", "highpass", {"cutoff": 1400}, region="meadow")
_fx("fx_reverse", "Reverse Sparkle", "reverse", {}, region="hidden", rarity="rare")
_fx("fx_tremolo", "Tremolo Leaf", "tremolo", {"rate": 6.0, "depth": 0.5}, region="orchard")
_fx("fx_fadein", "Fade In", "fade_in", {"time": 0.6}, region="meadow")
_fx("fx_fadeout", "Fade Out", "fade_out", {"time": 0.6}, region="meadow")
_fx("fx_bitcrush", "Toy Bitcrush", "bitcrush", {"bits": 6, "down": 3}, region="rhythm",
    rarity="uncommon")

# ===========================================================================
# RARE / HIDDEN  (special pieces tucked into hard-to-reach corners)
# ===========================================================================
_note("star_mb_c6", "Star Music Box C6", "music_box", "C6", region="hidden",
      rarity="secret", icon="star", desc="A twinkling top-octave music box note.")
_note("glass_e5", "Glass Bell E5", "glass", "E5", region="hidden", rarity="rare",
      desc="A pure glassy bell note (E5).")
_chord("golden_gmaj", "Golden G Major Chord", "glass", "G", "major", octave=5,
       region="hidden", rarity="rare", icon="star",
       desc="A radiant golden G Major chord.")
_loop("lp_midnight", "Midnight Music Box", "music_box",
      [("A4", 0, 2), ("E5", 2, 2), ("C5", 4, 2), ("B4", 6, 2), ("A4", 8, 4),
       ("G4", 12, 4)], region="hidden", rarity="secret", icon="star",
      desc="A wind-up music box found only at midnight.")
_note("butterfly_shimmer", "Butterfly Shimmer", "shimmer", "C6", region="orchard",
      rarity="rare", desc="A shimmering high texture note.")
_note("owl_bass", "Owl Hoot Bass", "hoot", "C2", track="bass", region="deepwood",
      rarity="rare", desc="A deep, breathy hoot used as a bass (C2).")
_note("frog_bass", "Frog Croak Bass", "croak", "C2", track="bass", region="river",
      rarity="uncommon", desc="A buzzy frog croak that works as a bass (C2).")
_note("cat_meow_lead", "Cat Meow Lead", "meow", "A4", region="animal",
      rarity="uncommon", desc="A playful meow you can use as a lead (A4).")
_loop("lp_birdcall", "Birdcall Melody Fragment", "chirp",
      [("A5", 0, 1), ("C6", 1, 1), ("A5", 3, 1), ("G5", 5, 1), ("C6", 7, 1)],
      length=8, region="animal", rarity="uncommon",
      desc="A fragment of birdsong you can loop.")
_loop("lp_secret_fruit", "Secret Music Fruit", "celeste",
      [("C5", 0, 2), ("E5", 2, 2), ("G5", 4, 2), ("C6", 6, 2), ("G5", 8, 2),
       ("E5", 10, 2), ("C5", 12, 4)], region="hidden", rarity="secret", icon="fruit",
      desc="A rare singing fruit hidden deep in a clearing.")


# ===========================================================================
# EXPANDED LIBRARY  (many more meaningful, musically-usable components)
# Every voice/drum/quality/ambience/effect used below is one the synth can
# actually render, so nothing here is silent.  Icons are tagged per flavour.
# ===========================================================================

# ---- more single notes (melody) ------------------------------------------
_note("mb_c5", "Music Box C5", "music_box", "C5", region="meadow", rarity="uncommon")
_note("mb_d5", "Music Box D5", "music_box", "D5", region="meadow", rarity="uncommon")
_note("mb_e5", "Music Box E5", "music_box", "E5", region="meadow", rarity="uncommon")
_note("mb_fs4", "Music Box F#4", "music_box", "F#4", region="meadow")
_note("mb_a3", "Music Box A3", "music_box", "A3", region="meadow")
_note("cel_c5", "Celeste C5", "celeste", "C5", region="orchard", rarity="uncommon")
_note("cel_e5", "Celeste E5", "celeste", "E5", region="orchard", rarity="uncommon")
_note("cel_g5", "Celeste G5", "celeste", "G5", region="orchard", rarity="uncommon")
_note("cel_a5", "Celeste A5", "celeste", "A5", region="orchard", rarity="uncommon")
_note("cel_c6", "Celeste C6", "celeste", "C6", region="hidden", rarity="rare")
_note("gl_c5", "Glass Note C5", "glass", "C5", region="hidden", rarity="rare")
_note("gl_g5", "Glass Note G5", "glass", "G5", region="hidden", rarity="rare")
_note("gl_d6", "Glass Note D6", "glass", "D6", region="hidden", rarity="secret", icon="star")
_note("tp_c5", "Toy Piano C5", "toy_piano", "C5", region="orchard")
_note("tp_e5", "Toy Piano E5", "toy_piano", "E5", region="orchard")
_note("tp_g5", "Toy Piano G5", "toy_piano", "G5", region="orchard")
_note("sl_c4", "Soft Lead C4", "soft_lead", "C4", region="meadow",
      desc="A smooth, singing lead note (C4).")
_note("sl_e4", "Soft Lead E4", "soft_lead", "E4", region="meadow",
      desc="A smooth, singing lead note (E4).")
_note("sl_g4", "Soft Lead G4", "soft_lead", "G4", region="meadow",
      desc="A smooth, singing lead note (G4).")
_note("sl_a4", "Soft Lead A4", "soft_lead", "A4", region="meadow", rarity="uncommon",
      desc="A smooth, singing lead note (A4).")
_note("sl_c5", "Soft Lead C5", "soft_lead", "C5", region="meadow", rarity="uncommon",
      desc="A smooth, singing lead note (C5).")
_note("moon_b4", "Moon Pluck B4", "moon_pluck", "B4", region="deepwood", rarity="uncommon")
_note("moon_d5", "Moon Pluck D5", "moon_pluck", "D5", region="deepwood", rarity="uncommon")
_note("moon_a5", "Moon Pluck A5", "moon_pluck", "A5", region="deepwood", rarity="rare")
_note("pl_c4", "Pluck C4", "pluck", "C4", region="river")
_note("pl_e4", "Pluck E4", "pluck", "E4", region="river")
_note("pl_g4", "Pluck G4", "pluck", "G4", region="river")
_note("pl_a4", "Pluck A4", "pluck", "A4", region="river")
_note("bell_f5", "Soft Bell F5", "bell", "F5", region="meadow", rarity="uncommon")
_note("bell_b5", "Soft Bell B5", "bell", "B5", region="meadow", rarity="uncommon")
_note("shim_e6", "Shimmer Veil E6", "shimmer", "E6", region="hidden", rarity="rare",
      desc="A high shimmering texture note (E6).")
_note("shim_g6", "Shimmer Veil G6", "shimmer", "G6", region="hidden", rarity="rare",
      desc="A high shimmering texture note (G6).")

# ---- more bass notes ------------------------------------------------------
_note("wb_d3", "Warm Bass D", "warm_bass", "D3", track="bass", region="orchard",
      desc="A round, warm bass note (D3).")
_note("wb_e3", "Warm Bass E", "warm_bass", "E3", track="bass", region="orchard",
      desc="A round, warm bass note (E3).")
_note("wb_f3", "Warm Bass F", "warm_bass", "F3", track="bass", region="orchard",
      desc="A round, warm bass note (F3).")
_note("wb_g3", "Warm Bass G", "warm_bass", "G3", track="bass", region="orchard",
      desc="A round, warm bass note (G3).")
_note("wb_a3", "Warm Bass A", "warm_bass", "A3", track="bass", region="orchard",
      desc="A round, warm bass note (A3).")
_note("wb_c2", "Deep Bass C", "warm_bass", "C2", track="bass", region="deepwood",
      rarity="uncommon", desc="A very low, round bass note (C2).")
_note("wb_g2", "Deep Bass G", "warm_bass", "G2", track="bass", region="deepwood",
      rarity="uncommon", desc="A very low, round bass note (G2).")

# ---- more chords (the fuller quality palette) -----------------------------
_chord("tp_dmin", "Toy Piano D Minor", "toy_piano", "D", "minor", region="orchard")
_chord("tp_emin", "Toy Piano E Minor", "toy_piano", "E", "minor", region="orchard")
_chord("tp_csus2", "Toy Piano C Sus2", "toy_piano", "C", "sus2", region="orchard",
       rarity="uncommon", desc="An open, airy C sus2 chord on toy piano.")
_chord("tp_gsus4", "Toy Piano G Sus4", "toy_piano", "G", "sus4", region="orchard",
       rarity="uncommon", desc="A suspended G sus4 chord on toy piano.")
_chord("tp_fmaj7", "Toy Piano F Maj7", "toy_piano", "F", "maj7", region="orchard",
       rarity="uncommon", desc="A dreamy F major 7 chord on toy piano.")
_chord("tp_amin7", "Toy Piano A Min7", "toy_piano", "A", "min7", region="orchard",
       rarity="uncommon", desc="A mellow A minor 7 chord on toy piano.")
_chord("pad_dmin", "Warm Pad D Minor", "warm_pad", "D", "minor", region="deepwood",
       rarity="uncommon")
_chord("pad_emin", "Warm Pad E Minor", "warm_pad", "E", "minor", region="deepwood",
       rarity="uncommon")
_chord("pad_cmaj7", "Warm Pad C Maj7", "warm_pad", "C", "maj7", region="orchard",
       rarity="rare", desc="A lush C major 7 pad.")
_chord("pad_gdom7", "Warm Pad G7", "warm_pad", "G", "dom7", region="orchard",
       rarity="rare", desc="A warm dominant G7 pad that wants to resolve.")
_chord("pad_aadd9", "Warm Pad A add9", "warm_pad", "A", "add9", region="orchard",
       rarity="rare", desc="A shimmering A add9 pad.")
_chord("pad_csus2", "Warm Pad C Sus2", "warm_pad", "C", "sus2", region="meadow",
       rarity="uncommon")
_chord("pad_fsus4", "Warm Pad F Sus4", "warm_pad", "F", "sus4", region="meadow",
       rarity="uncommon")
_chord("pad_bmin", "Warm Pad B Minor", "warm_pad", "B", "minor", region="deepwood",
       rarity="rare")
_chord("cel_cmaj", "Celeste C Major", "celeste", "C", "major", octave=5, region="orchard",
       rarity="uncommon", desc="A bright celeste C major.")
_chord("cel_amin", "Celeste A Minor", "celeste", "A", "minor", octave=4, region="orchard",
       rarity="uncommon", desc="A tender celeste A minor.")
_chord("cel_fmaj7", "Celeste F Maj7", "celeste", "F", "maj7", octave=4, region="hidden",
       rarity="rare", desc="A glistening celeste F major 7.")
_chord("dream_amin", "Dream Bell A Minor", "bell", "A", "minor", octave=5, region="hidden",
       rarity="rare")
_chord("dream_fmaj7", "Dream Bell F Maj7", "bell", "F", "maj7", octave=4, region="hidden",
       rarity="rare")
_chord("golden_cmaj7", "Golden C Maj7", "glass", "C", "maj7", octave=5, region="hidden",
       rarity="secret", icon="star", desc="A radiant golden C major 7.")
_chord("golden_dsus4", "Golden D Sus4", "glass", "D", "sus4", octave=5, region="hidden",
       rarity="secret", icon="star", desc="A glowing suspended D chord.")
_chord("pluck_emin", "Plucked E Minor", "pluck", "E", "minor", region="river",
       desc="A gently plucked E minor chord.")
_chord("pluck_gmaj", "Plucked G Major", "pluck", "G", "major", region="river",
       desc="A gently plucked G major chord.")

# ---- more loops (phrases) -------------------------------------------------
_loop("lp_meadow_skip", "Meadow Skip", "music_box",
      [("C4", 0, 1), ("E4", 1, 1), ("G4", 2, 1), ("E4", 3, 1), ("A4", 4, 2),
       ("G4", 6, 2), ("C4", 8, 1), ("D4", 9, 1), ("E4", 10, 2), ("G4", 12, 4)],
      region="meadow", desc="A skipping, sunny music-box phrase.")
_loop("lp_sun_arp", "Sunrise Arpeggio", "celeste",
      [("C5", 0, 1), ("E5", 1, 1), ("G5", 2, 1), ("C6", 3, 1), ("G5", 4, 1),
       ("E5", 5, 1), ("C5", 6, 2), ("D5", 8, 1), ("F5", 9, 1), ("A5", 10, 2)],
      region="orchard", rarity="uncommon", desc="A rising celeste arpeggio.")
_loop("lp_evening", "Evening Descent", "toy_piano",
      [("G4", 0, 2), ("F4", 2, 2), ("E4", 4, 2), ("D4", 6, 2), ("C4", 8, 4),
       ("E4", 12, 4)], region="orchard", desc="A calm descending toy-piano line.")
_loop("lp_pond_ripple", "Pond Ripple", "pluck",
      [("E4", 0, 1), ("A4", 2, 1), ("C5", 4, 1), ("A4", 6, 1), ("E4", 8, 1),
       ("G4", 10, 1), ("B4", 12, 2)], region="river", rarity="uncommon",
      icon="droplet", effects=[("delay", {"time": 0.18, "mix": 0.28})],
      desc="A rippling, echoing water phrase.")
_loop("lp_starlight", "Starlight Twinkle", "bell",
      [("C5", 0, 1), ("E5", 2, 1), ("G5", 4, 1), ("C6", 6, 1), ("A5", 8, 1),
       ("G5", 10, 1), ("E5", 12, 2)], region="hidden", rarity="rare", icon="star",
      desc="A twinkling high bell motif.")
_loop("lp_walk_home", "Walk Home Tune", "soft_lead",
      [("C4", 0, 2), ("D4", 2, 2), ("E4", 4, 2), ("G4", 6, 2), ("E4", 8, 2),
       ("D4", 10, 2), ("C4", 12, 4)], region="meadow", rarity="uncommon",
      desc="A wistful, hummable lead melody.")
_loop("lp_moon_river", "Moonlit Stream", "moon_pluck",
      [("E4", 0, 2), ("G4", 2, 2), ("A4", 4, 2), ("B4", 6, 2), ("A4", 8, 2),
       ("G4", 10, 2), ("E4", 12, 4)], region="deepwood", rarity="rare",
      desc="A glowing moonlit stream phrase.")
_loop("lp_glass_falls", "Glass Waterfall", "glass",
      [("C6", 0, 1), ("A5", 1, 1), ("G5", 2, 1), ("E5", 3, 1), ("C5", 4, 2),
       ("E5", 6, 1), ("G5", 7, 1), ("C6", 8, 4)], region="hidden", rarity="secret",
      icon="star", desc="A cascading glass waterfall of notes.")
_loop("lp_purr_groove", "Purr Walk Bass", "warm_bass",
      [("C3", 0, 2), ("C3", 3, 1), ("E3", 4, 2), ("G3", 6, 2), ("F3", 8, 2),
       ("F3", 11, 1), ("G3", 12, 4)], region="animal", rarity="uncommon",
      desc="A purring, walking bass groove.")
_loop("lp_chirp_song", "Birdsong Loop", "chirp",
      [("A5", 0, 1), ("C6", 1, 1), ("A5", 2, 1), ("E5", 4, 1), ("G5", 6, 1),
       ("C6", 8, 1)], length=12, region="animal", rarity="uncommon", icon="feather",
      desc="A looping fragment of birdsong.")
_loop("lp_hoot_round", "Owl Round", "hoot",
      [("C3", 0, 2), ("E3", 4, 2), ("G3", 8, 2), ("E3", 12, 2)], length=16,
      region="deepwood", rarity="rare", icon="moon",
      desc="A slow, rounded owl-hoot motif.")
_loop("lp_meow_tune", "Meow Melody", "meow",
      [("A4", 0, 2), ("C5", 3, 2), ("E5", 6, 2), ("C5", 9, 2), ("A4", 12, 3)],
      length=16, region="animal", rarity="rare", icon="paw",
      desc="A playful melody sung in meows.")
_loop("lp_toy_march", "Toy March", "toy_piano",
      [("C4", 0, 1), ("C4", 2, 1), ("G4", 4, 1), ("G4", 6, 1), ("A4", 8, 1),
       ("A4", 10, 1), ("G4", 12, 2)], region="orchard",
      desc="A bouncy toy-piano marching line.")
_loop("lp_celeste_waltz", "Celeste Waltz", "celeste",
      [("C5", 0, 2), ("E5", 2, 1), ("G5", 4, 1), ("C5", 6, 2), ("F5", 8, 1),
       ("A5", 10, 1)], length=12, region="orchard", rarity="uncommon",
      desc="A lilting 3-feel celeste waltz.")
_loop("lp_deep_lull", "Deepwood Lullaby", "music_box",
      [("A4", 0, 2), ("G4", 2, 2), ("E4", 4, 4), ("D4", 8, 2), ("E4", 10, 2),
       ("C4", 12, 4)], region="deepwood", rarity="rare",
      desc="A soft lullaby from deep in the woods.")
_loop("lp_bright_skip", "Bright Skip", "pluck",
      [("C5", 0, 1), ("G4", 1, 1), ("C5", 2, 1), ("E5", 3, 1), ("G4", 4, 1),
       ("C5", 5, 1), ("E5", 6, 2)], length=8, region="river",
      desc="A bright, skipping plucked phrase.")
_loop("lp_secret_choir", "Secret Choir Pad", "warm_pad",
      [("C4", 0, 8), ("E4", 0, 8), ("G4", 0, 8), ("A3", 8, 8), ("C4", 8, 8),
       ("E4", 8, 8)], region="hidden", rarity="secret", icon="orb",
      desc="A hidden, slow two-chord choir pad.")
_loop("lp_riverbank", "Riverbank Lilt", "pluck",
      [("G4", 0, 1), ("B4", 2, 1), ("D5", 4, 1), ("B4", 6, 1), ("G4", 8, 1),
       ("A4", 10, 1), ("D5", 12, 2)], region="river", rarity="uncommon",
      icon="droplet", desc="A lilting riverbank pattern.")

# ---- more rhythms ---------------------------------------------------------
_rhythm("rh_heartbeat", "Heartbeat", [("deep_kick", 0), ("deep_kick", 1),
        ("deep_kick", 4), ("deep_kick", 5)], region="deepwood",
        desc="A soft, steady heartbeat pulse.")
_rhythm("rh_clip_clop", "Clip Clop", [("log", 0), ("paw", 2), ("log", 4), ("paw", 6)],
        region="animal", desc="A wooden clip-clop trot.")
_rhythm("rh_soft_step", "Soft Step", [("deep_kick", 0), ("hat", 2), ("brush_snare", 4),
        ("hat", 6)], region="rhythm", desc="A gentle brushed backbeat.")
_rhythm("rh_tip_tap", "Tip Tap", [("tick", 0), ("hat", 1), ("tick", 2), ("hat", 3),
        ("tick", 4), ("hat", 5), ("tick", 6), ("hat", 7)], region="rhythm",
        desc="A light ticking eighth-note pattern.")
_rhythm("rh_pebble_run", "Pebble Run", [("pebble", 0), ("pebble", 1), ("pebble", 2),
        ("shaker", 3), ("pebble", 4), ("pebble", 5), ("pebble", 6), ("shaker", 7)],
        region="rhythm", rarity="uncommon", desc="A scampering pebble run.")
_rhythm("rh_clap_along", "Clap Along", [("kick", 0), ("clap", 4), ("kick", 2),
        ("clap", 6)], region="orchard", desc="A simple kick-and-clap groove.")
_rhythm("rh_owl_night", "Owl Night Beat", [("deep_kick", 0), ("bell_tick", 2),
        ("deep_kick", 4), ("bell_tick", 6)], region="deepwood", rarity="uncommon",
        icon="moon", desc="A hushed nighttime beat.")
_rhythm("rh_duck_parade", "Duck Parade", [("duck", 0), ("kick", 0), ("duck", 4),
        ("kick", 4), ("hat", 2), ("hat", 6)], region="animal", rarity="uncommon",
        icon="droplet", desc="A waddling parade groove.")
_rhythm("rh_sheep_meadow", "Sheep Meadow", [("sheep_bell", 0), ("hat", 2),
        ("sheep_bell", 4), ("hat", 6)], region="animal", rarity="uncommon",
        desc="A pastoral bell-and-hat pattern.")
_rhythm("rh_bark_beat", "Bark Beat", [("bark", 0), ("kick", 2), ("bark", 4),
        ("snare", 4), ("kick", 6)], region="animal", rarity="rare", icon="paw",
        desc="A punchy bark-driven beat.")
_rhythm("rh_brush_groove", "Brush Groove", [("kick", 0), ("brush_snare", 4),
        ("shaker", 2), ("shaker", 6), ("kick", 5)], region="rhythm",
        desc="A laid-back brushed groove.")
_rhythm("rh_double_time", "Double Time", [("kick", 0), ("hat", 1), ("kick", 2),
        ("hat", 3), ("snare", 4), ("hat", 5), ("kick", 6), ("hat", 7)],
        region="rhythm", rarity="uncommon", desc="A busy double-time pattern.")
_rhythm("rh_lazy_sun", "Lazy Sunday", [("kick", 0), ("snare", 4), ("open_hat", 6)],
        region="meadow", desc="A wide, lazy backbeat with an open hat.")
_rhythm("rh_jungle_lite", "Jungle Lite", [("kick", 0), ("snare", 3), ("kick", 5),
        ("snare", 4), ("hat", 2), ("hat", 6)], region="deepwood", rarity="rare",
        desc="A syncopated, breakbeat-ish pattern.")

# ---- one more drum (the unused tick voice) --------------------------------
_drum("tick_tiny", "Tiny Tick", "tick", region="rhythm",
      desc="A tiny high tick, great for counting time.")

# ---- more ambience textures ----------------------------------------------
_amb("amb_underriver", "Underwater Hum", "river", region="river", rarity="uncommon",
     icon="droplet", effects=[("lowpass", {"cutoff": 600})],
     desc="A muffled, underwater river hum.")
_amb("amb_dawn", "Dawn Chorus", "birds", region="meadow", rarity="uncommon",
     icon="feather", effects=[("highpass", {"cutoff": 900})],
     desc="A bright early-morning bird chorus.")
_amb("amb_warmpurr", "Warm Purr Bed", "purr", region="animal", rarity="uncommon",
     icon="paw", dur=5.0, desc="A long, cozy cat-purr bed.")
_amb("amb_nightwind", "Deep Night Wind", "wind", region="deepwood",
     icon="wisp", effects=[("lowpass", {"cutoff": 700})],
     desc="A low, deep night wind.")
_amb("amb_meadoweve", "Meadow Evening", "crickets", region="meadow", rarity="uncommon",
     effects=[("reverb", {"amount": 0.25, "decay": 0.6})],
     desc="A spacious cricket-filled evening.")

# ---- more effects (distinct param flavours) -------------------------------
_fx("fx_cathedral", "Cathedral Hall", "reverb", {"amount": 0.5, "decay": 0.95},
    region="hidden", rarity="rare", icon="ring",
    desc="A big, long cathedral reverb.")
_fx("fx_slapback", "Slapback Echo", "delay", {"time": 0.11, "feedback": 0.18, "mix": 0.3},
    region="rhythm", rarity="uncommon", icon="ring",
    desc="A short, snappy slapback echo.")
_fx("fx_deepmist", "Deep Mist", "lowpass", {"cutoff": 500}, region="deepwood",
    rarity="uncommon", desc="A heavy low-pass that softens everything.")
_fx("fx_airy", "Airy Lift", "highpass", {"cutoff": 2600}, region="meadow",
    desc="An airy high-pass that lifts a track.")
_fx("fx_crunch", "Toy Crunch", "bitcrush", {"bits": 4, "down": 4}, region="rhythm",
    rarity="rare", desc="A crunchy, lo-fi bitcrush.")


# ===========================================================================
# EXPANSION PACK  (more "real deal" components across every category)
# ===========================================================================
# -- more melodic notes -----------------------------------------------------
_note("n2_glass_c5", "Glass Bell C5", "glass", "C5", region="river", rarity="uncommon")
_note("n2_glass_e5", "Glass Bell E5", "glass", "E5", region="river", rarity="uncommon")
_note("n2_glass_g5", "Glass Bell G5", "glass", "G5", region="river", rarity="uncommon")
_note("n2_cel_c5", "Celeste C5", "celeste", "C5", region="deepwood", rarity="uncommon")
_note("n2_cel_e5", "Celeste E5", "celeste", "E5", region="deepwood", rarity="uncommon")
_note("n2_cel_g5", "Celeste G5", "celeste", "G5", region="deepwood", rarity="uncommon")
_note("n2_mb_c5", "Music Box C5", "music_box", "C5", region="meadow")
_note("n2_mb_d5", "Music Box D5", "music_box", "D5", region="meadow")
_note("n2_tp_f4", "Toy Piano F4", "toy_piano", "F4", region="orchard")
_note("n2_tp_b4", "Toy Piano B4", "toy_piano", "B4", region="orchard")
_note("n2_pluck_a4", "Pluck A4", "pluck", "A4", region="rhythm")
_note("n2_pluck_d5", "Pluck D5", "pluck", "D5", region="rhythm")
_note("n2_lead_c5", "Soft Lead C5", "soft_lead", "C5", region="hidden", rarity="rare")
_note("n2_shimmer_e6", "Shimmer E6", "shimmer", "E6", region="hidden", rarity="rare")

# -- more chords ------------------------------------------------------------
_chord("c2_glass_dmaj7", "Glass D Maj7", "glass", "D", "maj7", region="river", rarity="uncommon")
_chord("c2_pad_amin7", "Warm Pad A Min7", "warm_pad", "A", "min7", region="orchard", rarity="uncommon")
_chord("c2_pad_emin", "Warm Pad E Minor", "warm_pad", "E", "minor", region="orchard", rarity="uncommon")
_chord("c2_tp_dsus2", "Toy Piano D Sus2", "toy_piano", "D", "sus2", region="orchard")
_chord("c2_tp_gsus4", "Toy Piano G Sus4", "toy_piano", "G", "sus4", region="orchard")
_chord("c2_bell_cadd9", "Dream Bell C add9", "bell", "C", "add9", region="meadow", rarity="uncommon")
_chord("c2_cel_fmaj7", "Celeste F Maj7", "celeste", "F", "maj7", region="deepwood", rarity="rare")
_chord("c2_pluck_amin", "Pluck A Minor", "pluck", "A", "minor", region="rhythm")
_chord("c2_pad_dmaj", "Dream Pad D Major", "warm_pad", "D", "major", region="hidden", rarity="rare")
_chord("c2_glass_gmaj", "Golden Bell Chord G", "glass", "G", "major", region="hidden", rarity="rare")

# -- more bass (incl. animal-flavored) --------------------------------------
_note("b2_bass_e3", "Warm Bass E3", "warm_bass", "E3", track="bass", region="orchard")
_note("b2_bass_g3", "Warm Bass G3", "warm_bass", "G3", track="bass", region="orchard")
_note("b2_bass_a2", "Warm Bass A2", "warm_bass", "A2", track="bass", region="deepwood", rarity="uncommon")
_note("b2_bass_d3", "Warm Bass D3", "warm_bass", "D3", track="bass", region="orchard")
_note("b2_owlbass_c3", "Owl Hoot Bass", "hoot", "C3", track="bass", region="animal",
      rarity="uncommon", icon="moon", desc="A deep, hooting owl bass note (C3).")
_note("b2_croak_e2", "Frog Croak Bass", "croak", "E2", track="bass", region="animal",
      rarity="uncommon", icon="droplet", desc="A low croaking frog bass (E2).")

# -- more drum hits ---------------------------------------------------------
_drum("d2_deepkick", "Deep Kick", "deep_kick", region="rhythm")
_drum("d2_brush", "Brush Snare", "brush_snare", region="rhythm", rarity="uncommon")
_drum("d2_clap", "Hand Clap", "clap", region="rhythm")
_drum("d2_openhat", "Open Hat", "open_hat", region="rhythm")
_drum("d2_shaker", "Shaker", "shaker", region="rhythm")
_drum("d2_log", "Wood Log", "log", region="animal", icon="paw")
_drum("d2_frogpop", "Frog Pop Percussion", "frog_pop", region="animal", rarity="uncommon", icon="droplet")
_drum("d2_belltick", "Bell Tick", "bell_tick", region="river", rarity="uncommon")
_drum("d2_sheepbell", "Sheep Bell", "sheep_bell", region="animal", rarity="uncommon", icon="paw")

# -- more rhythm patterns ---------------------------------------------------
_rhythm("r2_riverpulse", "River Pulse Rhythm",
        [("kick", 0), ("kick", 4), ("snare", 4), ("shaker", 2), ("shaker", 6)],
        region="river", rarity="uncommon")
_rhythm("r2_moonwaltz", "Moon Waltz Rhythm",
        [("deep_kick", 0), ("brush_snare", 3), ("brush_snare", 6), ("tick", 2), ("tick", 5)],
        region="deepwood", rarity="uncommon")
_rhythm("r2_pawbeat", "Paw Beat",
        [("paw", 0), ("paw", 2), ("paw", 4), ("paw", 6), ("log", 4)],
        region="animal", icon="paw")
_rhythm("r2_pebble", "Pebble Shuffle",
        [("pebble", 0), ("pebble", 1), ("pebble", 3), ("pebble", 4), ("pebble", 6)],
        region="rhythm")
_rhythm("r2_heartbeat", "Heartbeat Pulse",
        [("deep_kick", 0), ("deep_kick", 1), ("deep_kick", 4), ("deep_kick", 5)],
        region="hidden", rarity="rare")
_rhythm("r2_clave", "Clap Clave",
        [("clap", 0), ("clap", 3), ("clap", 6), ("tick", 2), ("tick", 4)],
        region="rhythm", rarity="uncommon")

# -- more loops -------------------------------------------------------------
_loop("l2_goldlull", "Golden Lullaby Loop", "music_box",
      [("C5", 0, 2), ("E5", 2, 2), ("G5", 4, 2), ("E5", 6, 2), ("D5", 8, 2), ("C5", 10, 4)],
      region="meadow", rarity="uncommon")
_loop("l2_riverarp", "River Arpeggio Loop", "glass",
      [("C5", 0, 1), ("E5", 1, 1), ("G5", 2, 1), ("B5", 3, 1), ("A5", 4, 1), ("G5", 5, 1), ("E5", 6, 2)],
      region="river", rarity="uncommon")
_loop("l2_moonmotif", "Moonlit Motif", "moon_pluck",
      [("A4", 0, 2), ("C5", 2, 2), ("E5", 4, 2), ("D5", 6, 2), ("C5", 8, 4)],
      region="deepwood", rarity="rare")
_loop("l2_toyrun", "Toy Piano Run", "toy_piano",
      [("C4", 0, 1), ("D4", 1, 1), ("E4", 2, 1), ("G4", 3, 1), ("A4", 4, 1), ("G4", 5, 1), ("E4", 6, 2)],
      region="orchard")
_loop("l2_celestedream", "Celeste Dream", "celeste",
      [("E5", 0, 2), ("G5", 2, 2), ("B5", 4, 2), ("A5", 6, 2), ("G5", 8, 4)],
      region="hidden", rarity="rare")
_loop("l2_chirpsong", "Birdcall Melody", "chirp",
      [("C5", 0, 1), ("E5", 2, 1), ("G5", 4, 1), ("E5", 6, 1)],
      region="animal", rarity="uncommon", icon="feather")

# -- more ambience beds -----------------------------------------------------
_amb("a2_riverbed", "Riverside Flow", "river", region="river", rarity="uncommon",
     icon="droplet", dur=5.0)
_amb("a2_owlnight", "Owl Night Texture", "owl", region="deepwood", rarity="rare",
     icon="moon", dur=5.0)
_amb("a2_cricketeve", "Cricket Evening", "crickets", region="meadow")
_amb("a2_crackle", "Warm Crackle Bed", "crackle", region="hidden", rarity="uncommon",
     icon="wisp")
_amb("a2_birdsmorning", "Birdsong Morning", "birds", region="animal", rarity="uncommon",
     icon="feather")

# -- more effects -----------------------------------------------------------
_fx("f2_echocrystal", "Echo Crystal", "echo",
    {"time": 0.18, "feedback": 0.32, "mix": 0.34}, region="hidden", rarity="rare",
    icon="crystal")
_fx("f2_ripple", "Ripple Delay", "ripple_delay", {"time": 0.16, "mix": 0.4},
    region="river", rarity="uncommon", icon="ring")
_fx("f2_lowpassmist", "Low-Pass Mist", "lowpass", {"cutoff": 700}, region="deepwood",
    rarity="uncommon")
_fx("f2_tremolo", "Tremolo Shimmer", "tremolo", {"rate": 6.0, "depth": 0.5},
    region="meadow", rarity="uncommon", icon="crystal")
_fx("f2_reverse", "Reverse Swell", "reverse", {}, region="hidden", rarity="rare",
    icon="crystal")


# ===========================================================================
# GIFTS & AWAKENINGS  (reward=True: never scattered as world pickups.
# Landmarks give these when they wake; animal friends leave them after a
# song they loved.  They live in their own journal section as gentle,
# mysterious "?" cells until earned.)
# ===========================================================================
_loop("gift_fountain_arp", "Fountain Sparkle Arp", "glass",
      [("C5", 0, 1), ("E5", 2, 1), ("G5", 4, 1), ("C6", 6, 1), ("G5", 8, 1),
       ("E5", 10, 1), ("C5", 12, 2)], region="gifts", rarity="rare",
      reward=True, icon="droplet", tags=["watery", "bright"],
      desc="The old fountain's own glittering water-light phrase.")
_amb("gift_fountain_mist", "Fountain Mist", "river", region="gifts",
     rarity="rare", reward=True, icon="droplet", dur=5.0,
     tags=["watery", "soft"],
     desc="A cool, gentle mist bed from the waking fountain.")
_chord("gift_grove_pad", "Grove Lullaby Pad", "warm_pad", "D", "minor",
       region="gifts", rarity="rare", reward=True, icon="orb",
       tags=["soft", "night"],
       desc="The sleeping grove's slow, deep breath as a chord.")
_note("gift_grove_chime", "Moth Wing Chime", "celeste", "A5",
      region="gifts", rarity="rare", reward=True, icon="star",
      tags=["night", "dreamy"],
      desc="A note as light as a moth landing on a blossom.")
_loop("gift_chime_cascade", "Chime Cascade", "bell",
      [("G5", 0, 1), ("E5", 1, 1), ("C5", 2, 1), ("D5", 4, 1), ("G5", 6, 2),
       ("E5", 8, 1), ("C5", 10, 2)], region="gifts", rarity="rare",
      reward=True, icon="star", tags=["bright"],
      desc="The chime tree remembering all its colours at once.")
_note("gift_chime_breeze", "Breeze Bell G5", "bell", "G5", region="gifts",
      rarity="rare", reward=True, icon="note", tags=["bright", "airy"],
      desc="One clear bell caught on a warm breeze.")
_drum("gift_rabbit_shake", "Clover Shake", "shaker", region="gifts",
      rarity="uncommon", reward=True, icon="stone", tags=["playful"],
      desc="A rabbit's thank-you: a soft shake like clover in wind.")
_note("gift_fox_pluck", "Fox's Night Pluck", "moon_pluck", "E4",
      region="gifts", rarity="rare", reward=True, icon="moon",
      tags=["night"],
      desc="Left by a fox who finally came close. Quiet as dusk.")
_rhythm("gift_duck_paddle", "Duck Paddle Beat",
        [("duck", 0), ("shaker", 2), ("duck", 4), ("shaker", 6), ("kick", 0),
         ("kick", 4)], region="gifts", rarity="uncommon", reward=True,
        icon="droplet", tags=["watery", "playful"],
        desc="A paddling groove from a very pleased duck.")
_amb("gift_owl_watch", "Owl Night Watch", "owl", region="gifts",
     rarity="rare", reward=True, icon="moon", dur=5.0, tags=["night"],
     desc="The owl keeps watch over your night songs now.")
_note("gift_deer_bell", "Fern Bell D5", "bell", "D5", region="gifts",
      rarity="uncommon", reward=True, icon="note", tags=["soft", "bright"],
      desc="A deer's gift, gentle as fern shade.")
_rhythm("gift_frog_hop", "Lilypad Hop",
        [("frog_pop", 0), ("frog_pop", 3), ("kick", 4), ("frog_pop", 6)],
        region="gifts", rarity="uncommon", reward=True, icon="droplet",
        tags=["watery", "playful"],
        desc="Hopped straight off a lilypad and into your songbook.")


# ---------------------------------------------------------------------------
# Sound Atlas: a large deterministic curated library.  It is appended after
# the original hand-written catalog so all legacy ids and world placement
# ordering remain stable for existing save files.
# ---------------------------------------------------------------------------
from .curated_library import install as _install_curated_library  # noqa: E402
SOUND_ATLAS_COUNT = _install_curated_library(_add)


# ---------------------------------------------------------------------------
# Index + public helpers
# ---------------------------------------------------------------------------
ALL = _COMPONENTS
BY_ID = {c["id"]: c for c in _COMPONENTS}

from . import procedural   # noqa: E402  (generated/infinite components)


def get(cid):
    c = BY_ID.get(cid)
    if c is not None:
        return c
    if procedural.is_proc(cid):
        return procedural.from_id(cid)
    return None


def starters():
    return [c for c in ALL if c.get("starter")]


def by_region(region):
    return [c for c in ALL if c["region"] == region and not c.get("starter")]


def placed_components():
    """Components that appear as world pickups.

    Starters are built-in tools and rewards are earned from Garden Works and
    animal friends, so neither is ever scattered into the meadow."""
    return [c for c in ALL if not c.get("starter") and not c.get("reward")]


def effects():
    return [c for c in ALL if c["type"] == "effect"]


def count():
    return len(ALL)


# sanity: ids must be unique
assert len(BY_ID) == len(ALL), "duplicate component id in catalog"
