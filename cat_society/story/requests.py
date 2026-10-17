"""Deterministic and readable commission briefs for Story mode.

Every request starts with a coherent occasion. Species preferences then weight
which occasion appears, while the place, recipient, service pattern and exact
musical limits are varied from the slot seed. The spoken text is plain enough
to understand quickly. Scoring reads the structured fields, never the prose.
"""

import hashlib
import random

from ..entities.animals import SPECIES


NAMES = {
    "dog": ("Pip", "Milo", "Patch", "Scout", "Tansy", "Rufus", "Poppy", "Otis", "Nell", "Toby", "Mabel", "Biscuit"),
    "fox": ("Maple", "Saffron", "Ember", "Russet", "Sorrel", "Lark", "Copper", "Mica", "Fern", "Cinder", "Hazel", "Rowan"),
    "rabbit": ("Poppy", "Button", "Mallow", "Thimble", "Dandelion", "Pecan", "Pipkin", "Basil", "Nettle", "Luna", "Minnie", "Bunty"),
    "frog": ("Puddle", "Moss", "Ripple", "Reed", "Plop", "Bogart", "Lily", "Pebble", "Sprig", "Croaker", "Fern", "Dew"),
    "duck": ("Waddle", "Pond", "Dabble", "Pondel", "Quill", "Marnie", "Puck", "Drift", "Sunny", "Piper", "Mallow", "Breeze"),
    "owl": ("Morrow", "Lumen", "Nightingale", "Orion", "Velvet", "Mira", "Sable", "Atlas", "Rune", "Nova", "Cedar", "Moth"),
    "deer": ("Fern", "Hazel", "Willow", "Rowan", "Fawnlight", "Aster", "Briar", "Elowen", "Meadow", "Cedar", "Lark", "Ivy"),
    "sheep": ("Daisy", "Woolly", "Cloud", "Fleece", "Puffin", "Meringue", "Pearl", "Tilly", "Cotton", "Bonnie", "Lambkin", "Muffin"),
    "cow": ("Marigold", "Bessie", "Mallow", "Cloverbell", "Mooira", "Dottie", "Maisie", "Buttercup", "Rosie", "Mabel", "Nora", "Penny"),
    "horse": ("Copper", "Breeze", "Tumble", "Comet", "Chestnut", "Maple", "Rook", "Sage", "Marlow", "River", "Pinto", "Storm"),
    "turtle": ("Pebble", "Old Moss", "Shellby", "Drift", "Mossback", "Harbor", "Tide", "Olive", "Cove", "Myrtle", "Dune", "Sage"),
    "raccoon": ("Patch", "Tinker", "Mooncap", "Latch", "Buttonhook", "Sprocket", "Nim", "Mischief", "Pocket", "Rivet", "Smudge", "Pepper"),
    "tanuki": ("Kumo", "Poko", "Chestnut", "Nori", "Mochi", "Sora", "Yuzu", "Momo", "Kiki", "Taro", "Hana", "Beni"),
    "goat": ("Thistle", "Nibbles", "Basil", "Crag", "Pepper", "Poppy", "Clove", "Ridge", "Marmot", "Tansy", "Bruno", "Fig"),
    "pig": ("Truffle", "Rosie", "Poppy", "Turnip", "Plum", "Peaches", "Mabel", "Figgy", "Toby", "Pip", "Tulip", "Mochi"),
    "chicken": ("Peep", "Goldie", "Dottie", "Cluckett", "Sunseed", "Penny", "Pip", "Ginger", "Dot", "Honey", "Midge", "Tilly"),
    "squirrel": ("Acorn", "Flick", "Chestnut", "Nutmeg", "Twig", "Hazel", "Pecan", "Nimble", "Pip", "Briar", "Tumble", "Maple"),
    "hedgehog": ("Burr", "Needle", "Pipkin", "Briar", "Prickle", "Thimble", "Moss", "Button", "Quill", "Truffle", "Tansy", "Midge"),
    "bird": ("Chirp", "Blue", "Pico", "Lilt", "Skylark", "Piper", "Robin", "Mira", "Lark", "Sunny", "Wren", "Echo"),
}


# Established one-off and recurring NPCs must never be duplicated by the
# procedural client generator. Comparisons use stripped, case-folded base names.
RESERVED_NAMES = frozenset({"poko", "juniper", "clover", "bramble", "pip"})


def _available_names(species):
    names = NAMES.get(species, (species.title(),))
    allowed = [name for name in names if name.strip().casefold() not in RESERVED_NAMES]
    return tuple(allowed or (species.title(),))


# key, title, tags, energy, tempo range, required families, plain occasion text
OCCASIONS = (
    ("porch_lullaby", "A porch lullaby", ("soft", "warm"), "low", (62, 92), ("melody",), "a lullaby for {recipient} at bedtime"),
    ("puddle_parade", "The puddle parade", ("watery", "playful"), "high", (116, 150), ("drums", "melody"), "a marching tune for the puddle parade near {place}"),
    ("star_watch", "Music for watching stars", ("night", "dreamy"), "low", (58, 88), ("chords",), "quiet music for watching the stars above {place}"),
    ("market_courage", "Market morning courage", ("bright", "playful"), "high", (120, 154), ("drums",), "an entrance tune for a speech at the market near {place}"),
    ("river_memory", "A riverbank memory", ("watery", "soft"), "low", (70, 102), ("melody", "chords"), "a song about an afternoon beside {place}"),
    ("windy_dance", "A windy hill dance", ("airy", "bright"), "mid", (98, 132), ("melody",), "a dance for a windy afternoon at {place}"),
    ("blanket_fort", "The blanket fort song", ("warm", "dreamy"), "low", (64, 94), ("chords",), "a secret song for a blanket fort built with {recipient}"),
    ("woodland_tiptoe", "A woodland walk", ("soft", "animal"), "mid", (84, 116), ("melody",), "music for following animal tracks near {place}"),
    ("sunrise_greeting", "A sunrise greeting", ("bright", "airy"), "mid", (92, 126), ("melody", "chords"), "music for tomorrow's first sunrise"),
    ("muddy_anthem", "The muddy boots anthem", ("playful", "warm"), "high", (112, 145), ("drums", "bass"), "an anthem for the island's muddiest boots"),
    ("orchard_wedding", "An orchard wedding", ("warm", "bright"), "mid", (86, 118), ("chords", "melody"), "a wedding processional under the orchard trees for {recipient}"),
    ("storm_shelter", "Storm shelter music", ("warm", "soft"), "low", (60, 88), ("chords", "bass"), "steady music for neighbors sheltering at {place}"),
    ("moon_ferry", "The moon ferry tune", ("night", "watery"), "mid", (76, 108), ("bass", "melody"), "a rowing tune for a ferry crossing after dark"),
    ("hatchling_dance", "A first dance", ("animal", "playful"), "high", (118, 148), ("drums", "melody"), "a first dance for {recipient}"),
    ("harvest_feast", "The harvest feast", ("warm", "bright"), "high", (106, 138), ("drums", "chords"), "an opening tune for the harvest table at {place}"),
    ("apology", "An apology in music", ("soft", "warm"), "low", (66, 96), ("melody",), "an honest apology to {recipient}"),
    ("first_flight", "A first flight", ("airy", "bright"), "high", (124, 158), ("drums", "melody"), "a countdown for {recipient}'s first flight"),
    ("rain_reading", "Rainy reading music", ("watery", "dreamy"), "low", (58, 84), ("chords",), "reading music for a rainy afternoon at {place}"),
    ("firefly_waltz", "The firefly waltz", ("night", "playful"), "mid", (82, 116), ("melody", "chords"), "a waltz for the fireflies above {place}"),
    ("lost_path", "A song that points home", ("airy", "soft"), "mid", (80, 112), ("melody",), "a clear musical signal for anyone lost beyond {place}"),
    ("winter_makebelieve", "A make believe winter", ("dreamy", "warm"), "low", (60, 90), ("chords", "melody"), "a pretend snow day for {recipient}"),
    ("birthday_secret", "A birthday surprise", ("playful", "bright"), "high", (120, 152), ("drums", "bass"), "a surprise entrance for {recipient}'s birthday"),
    ("pond_opera", "The pond opera", ("watery", "animal"), "mid", (78, 112), ("melody", "chords"), "an opening for a pond opera at {place}"),
    ("bridge_opening", "A bridge opening", ("bright", "airy"), "high", (112, 146), ("drums", "chords"), "a fanfare for a new bridge near {place}"),
    ("acorn_race", "The acorn cart race", ("playful", "animal"), "high", (126, 160), ("drums", "bass"), "race music for acorn carts at {place}"),
    ("tea_cooling", "Music while tea cools", ("warm", "soft"), "low", (64, 92), ("chords",), "calm music for tea with {recipient}"),
    ("den_bedtime", "Bedtime in the den", ("soft", "night"), "low", (56, 82), ("melody", "chords"), "bedtime music for a family den near {place}"),
    ("hoofbeat_road", "The long road", ("animal", "bright"), "high", (116, 148), ("drums", "bass"), "a road song for the trip to {place}"),
    ("dawn_bakery", "Early bakery music", ("warm", "bright"), "mid", (88, 120), ("bass", "melody"), "music for baking before sunrise"),
    ("lantern_walk", "The lantern walk", ("night", "warm"), "mid", (76, 108), ("drums", "chords"), "a walking tune for lanterns heading to {place}"),
    ("cave_echo", "A cave echo", ("dreamy", "airy"), "mid", (68, 104), ("melody",), "a tune with clear pauses for the cave below {place}"),
    ("cloud_names", "Naming the clouds", ("airy", "dreamy"), "low", (62, 94), ("chords",), "slow music for naming clouds with {recipient}"),
    ("century", "A hundredth birthday", ("warm", "night"), "low", (54, 82), ("bass", "chords"), "a dignified birthday song for an old friend at {place}"),
    ("chorus_audition", "The pond chorus audition", ("watery", "animal"), "high", (108, 142), ("drums", "melody"), "an audition tune for the pond chorus at {place}"),
    ("astronomy", "An astronomy lesson", ("night", "dreamy"), "low", (58, 90), ("chords", "bass"), "music for teaching constellations to {recipient}"),
    ("repair_rhythm", "The repair rhythm", ("playful", "warm"), "mid", (94, 126), ("drums", "bass"), "a steady rhythm for repairing a machine at {place}"),
    ("egg_ceremony", "The first egg ceremony", ("bright", "animal"), "high", (114, 148), ("drums", "melody"), "a proud tune for the first egg of spring"),
    ("pasture_nap", "The pasture nap", ("soft", "warm"), "low", (52, 78), ("bass", "chords"), "sleepy music for the pasture near {place}"),
    ("spinning_song", "The spinning circle", ("warm", "airy"), "mid", (82, 112), ("melody", "bass"), "a work song for the wool spinners at {place}"),
    ("trading_jingle", "A trader's jingle", ("playful", "bright"), "mid", (102, 136), ("drums", "melody"), "a short jingle for a cart travelling to {place}"),
    ("forest_memorial", "A forest memorial", ("soft", "night"), "low", (56, 86), ("chords", "melody"), "a memorial for an old tree at {place}"),
    ("migration", "A migration farewell", ("airy", "soft"), "mid", (84, 118), ("melody", "chords"), "a farewell for friends leaving the island"),
    ("school_play", "The school play", ("playful", "warm"), "mid", (92, 124), ("melody", "drums"), "music for a school play starring {recipient}"),
    ("boat_race", "The little boat race", ("watery", "bright"), "high", (122, 156), ("drums", "bass"), "race music for boats leaving {place}"),
    ("quiet_breakfast", "A quiet breakfast", ("soft", "warm"), "low", (58, 86), ("chords",), "morning music for breakfast with {recipient}"),
    ("garden_work", "A garden work song", ("warm", "animal"), "mid", (92, 122), ("bass", "drums"), "a work song for planting near {place}"),
    ("night_patrol", "The night patrol", ("night", "bright"), "mid", (88, 118), ("drums", "bass"), "a confident tune for the night patrol at {place}"),
    ("picnic", "A meadow picnic", ("bright", "warm"), "mid", (96, 126), ("melody", "chords"), "music for a picnic with {recipient} at {place}"),
    ("river_cleanup", "The river cleanup", ("watery", "bright"), "mid", (100, 132), ("drums", "melody"), "a work tune for cleaning the river near {place}"),
    ("library_close", "Closing the library", ("soft", "night"), "low", (54, 80), ("chords",), "quiet music for closing the library at {place}"),
    ("morning_exercise", "Morning exercise", ("bright", "playful"), "high", (124, 158), ("drums", "bass"), "exercise music for {recipient}"),
    ("new_home", "A new home", ("warm", "dreamy"), "mid", (76, 108), ("chords", "melody"), "a welcome song for {recipient}'s new home near {place}"),
    ("path_light", "A light for the path", ("bright", "warm"), "mid", (80, 112), ("chords", "melody"), "a glowing sound to light the path at {place}"),
    ("moon_garden", "Moon garden lights", ("night", "dreamy"), "low", (58, 88), ("chords",), "a soft light for the moon garden near {place}"),
    ("bridge_lantern", "A bridge lantern", ("bright", "night"), "mid", (76, 108), ("melody", "bass"), "a musical light for the bridge at {place}"),
    ("safe_crossing", "A safe crossing", ("warm", "bright"), "mid", (88, 116), ("drums", "chords"), "a bright sound that marks the crossing at {place}"),
    ("night_stall", "A night market light", ("night", "playful"), "mid", (96, 126), ("drums", "melody"), "music and light for a market stall at {place}"),
    ("welcome_beacon", "A welcome beacon", ("airy", "bright"), "mid", (84, 118), ("melody", "chords"), "a musical beacon for visitors arriving at {place}"),
)

LIGHT_OCCASIONS = {"path_light", "moon_garden", "bridge_lantern", "safe_crossing", "night_stall", "welcome_beacon"}

PLACES = (
    "the reed bridge", "the orchard gate", "Mooncap Hill", "the old ferry post",
    "the blue stone path", "the eastern meadow", "the willow bend", "the windmill field",
    "the hidden pond", "the cliff path", "the lantern grove", "the mossy well",
    "the south beach", "acorn lane", "the river steps", "the old oak", "the farm gate",
    "the quiet cove", "the hill path", "the berry patch",
)
RECIPIENTS = (
    "my little cousins", "my oldest friend", "the neighbors", "the hatchlings",
    "someone I miss", "my nervous brother", "the whole family", "my closest friend",
    "the village children", "the workers", "our visitors", "my new neighbor",
)
OPENERS = (
    "I need help with a special occasion.",
    "I have a clear idea, but I cannot make it myself.",
    "I was told you are the best music maker on the island.",
    "I came here because this request matters to me.",
    "I have been thinking about this since yesterday.",
    "I need music made for a real purpose.",
    "I hope you have time for one more commission.",
)
DETAILS = (
    "Please keep it clear and easy to remember.",
    "I want the main feeling to be obvious when it starts.",
    "It should sound complete, not like a short sketch.",
    "Please do not make it busier than it needs to be.",
    "A small surprise near the end would be welcome.",
    "The people hearing it should understand the mood right away.",
    "It can be simple, but it should feel finished.",
    "I would rather hear one strong idea than many weak ones.",
)
VOICE = {
    "shy": ("Please keep it gentle.", "I do not want it to be too loud."),
    "friendly": ("It should be easy to enjoy.", "I hope everyone can move to it."),
    "calm": ("There is no need to make it complicated.", "A steady and honest sound will work."),
}

SPROUT_TYPES = ("note", "chord", "bass", "drum", "rhythm", "loop", "ambience")
REGIONS = ("meadow", "river", "orchard", "deepwood", "animal", "hidden")

SPECIES_TAGS = {
    "frog": ("watery", "playful", "animal"), "duck": ("watery", "bright", "playful"),
    "turtle": ("watery", "soft", "warm"), "owl": ("night", "dreamy", "soft"),
    "fox": ("soft", "night", "dreamy"), "deer": ("soft", "airy", "night"),
    "dog": ("playful", "bright", "warm"), "horse": ("bright", "animal", "playful"),
    "sheep": ("warm", "soft", "dreamy"), "cow": ("warm", "soft", "animal"),
    "bird": ("airy", "bright", "dreamy"), "chicken": ("bright", "animal", "playful"),
    "raccoon": ("playful", "night", "warm"), "tanuki": ("playful", "warm", "bright"),
    "rabbit": ("soft", "playful", "airy"), "squirrel": ("playful", "animal", "bright"),
    "hedgehog": ("soft", "warm", "night"), "pig": ("warm", "playful", "bright"),
    "goat": ("animal", "bright", "playful"),
}


def _stable_seed(*parts):
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def _weighted_choice(rng, rows, weights):
    total = max(.0001, float(sum(weights)))
    pick = rng.random() * total
    acc = 0.0
    for row, weight in zip(rows, weights):
        acc += weight
        if pick <= acc:
            return row
    return rows[-1]


class RequestGenerator:
    def __init__(self, world_seed):
        self.world_seed = int(world_seed)

    def identity(self, day, serial, species=None):
        rng = random.Random(_stable_seed(self.world_seed, "identity", day, serial))
        species = species or rng.choice(tuple(k for k in SPECIES if k != "butterfly"))
        name = rng.choice(_available_names(species))
        return species, "%s the %s" % (name, species)

    def generate(self, day, serial, species, visit=0, first=False, used_primary=()):
        rng = random.Random(_stable_seed(self.world_seed, day, serial, species, visit))
        if first:
            row = OCCASIONS[0]
        else:
            prefs = set(SPECIES_TAGS.get(species, ()))
            used = set(used_primary)
            rows = [r for r in OCCASIONS if r[2][0] not in used] or list(OCCASIONS)
            habitat = SPECIES[species].habitat
            weights = []
            for item in rows:
                overlap = len(set(item[2]) & prefs)
                bonus = 0.0
                if habitat == "water_edge" and "watery" in item[2]:
                    bonus = 1.8
                elif habitat in ("forest", "rare_forest") and set(item[2]) & {"soft", "night", "dreamy", "airy"}:
                    bonus = 1.2
                elif habitat == "farm" and set(item[2]) & {"warm", "bright", "playful", "animal"}:
                    bonus = 1.2
                weights.append(1.0 + overlap * 2.3 + bonus)
            row = _weighted_choice(rng, rows, weights)

        key, title, base_tags, energy, tempo, needs, premise = row
        difficulty = max(1, min(5, 1 + int(visit) + (int(day) - 1) // 2 + rng.choice((0, 0, 1))))
        tags = list(base_tags)
        all_tags = ("watery", "night", "bright", "soft", "playful", "warm", "airy", "dreamy", "animal")
        extras = [tag for tag in all_tags if tag not in tags]
        if difficulty >= 3 and rng.random() < .72:
            tags.append(rng.choice(extras))
        place = rng.choice(PLACES)
        recipient = rng.choice(RECIPIENTS)
        purpose = premise.format(place=place, recipient=recipient)
        temperament = SPECIES[species].temperament
        voice = rng.choice(VOICE.get(temperament, VOICE["calm"]))
        opener = rng.choice(OPENERS)
        detail = rng.choice(DETAILS)

        light_task = key in LIGHT_OCCASIONS
        kind = "song" if first or rng.random() >= .28 else "sprout"
        if light_task and rng.random() < .62:
            kind = "sprout"

        if kind == "song":
            if first:
                service = "wait"
            elif light_task:
                service = "gramophone"
            else:
                service = _weighted_choice(rng,
                    ("wait", "return_later", "return_tomorrow", "gramophone"),
                    (.36, .27, .16, .21))
            jitter = rng.randint(-6, 6)
            lo, hi = max(48, tempo[0] + jitter), min(170, tempo[1] + jitter)
            banned = None
            if difficulty >= 4 and rng.random() < .55:
                banned = rng.choice([t for t in all_tags if t not in tags])
            req = {
                "kind": "song", "title": title, "occasion": key,
                "primary": tags[0], "tags": tags[:3], "support_tags": tags[1:3],
                "banned_tag": banned,
                "energy": energy, "tempo": (lo, hi), "needs": tuple(needs[:2]),
                "min_bars": 6 + difficulty * 2, "min_clips": 3 + difficulty,
                "service": service, "destination_label": place,
                "light_task": light_task,
            }
            spec = "Keep it %s and aim for %d to %d BPM. I need %s." % (
                tags[0], lo, hi, " and ".join(req["needs"]))
            if banned:
                spec += " Please do not let the %s mood become the main feeling." % banned
        else:
            service = "plant" if light_task else _weighted_choice(
                rng, ("wait", "return_later", "plant"), (.41, .22, .37))
            want_type = rng.choice(SPROUT_TYPES)
            if light_task:
                want_type = rng.choice(("note", "chord", "loop", "ambience"))
            if tags[0] == "watery":
                region = rng.choice(("river", "hidden", "animal"))
            elif tags[0] in ("night", "dreamy"):
                region = rng.choice(("deepwood", "hidden", "animal"))
            elif tags[0] in ("warm", "bright"):
                region = rng.choice(("meadow", "orchard", "animal"))
            else:
                region = rng.choice(REGIONS)
            req = {
                "kind": "sprout", "title": "A sound seed for " + title.lower(),
                "occasion": key, "primary": tags[0], "tags": tags[:2],
                "support_tags": tags[1:2], "want_type": want_type,
                "region": region, "want_region": region,
                "min_rarity": ("common", "uncommon", "uncommon", "rare", "rare")[difficulty - 1],
                "service": service, "destination_label": place,
                "light_task": light_task,
            }
            spec = "I need a %s sound seed with a %s feeling. A sound from the %s region would fit best." % (
                want_type, tags[0], region)

        if service == "wait":
            service_line = "I can wait at the shop for a while."
        elif service == "return_later":
            service_line = "I will come back later today."
        elif service == "return_tomorrow":
            service_line = "I will come back tomorrow before the shop closes."
        elif service == "gramophone":
            service_line = "Please carry the finished song to %s and place a gramophone there." % place
        else:
            service_line = "Please carry the sound seed to %s and plant it there." % place

        # Four short, ordinary sentences. The many independent choices provide
        # procedural breadth without hiding the actual requirements.
        flavor = "%s I need %s. %s %s %s" % (opener, purpose, spec, service_line,
                                                   rng.choice((detail, voice)))
        note = "%s %s" % (detail, voice)

        patience = 180 if first else rng.randint(55, 125)
        if service == "wait":
            accepted_patience = rng.randint(120, 260)
            return_delay = 0
        elif service == "return_later":
            accepted_patience = 0
            return_delay = rng.randint(70, 230)
        elif service == "return_tomorrow":
            accepted_patience = 0
            return_delay = rng.randint(18 * 60, 28 * 60)
        else:
            accepted_patience = 0
            return_delay = 0
        due_days = 1 if service in ("return_tomorrow", "gramophone", "plant") or difficulty >= 4 else 0
        req.update({
            "id": "req_%d_%d" % (day, serial),
            "difficulty": difficulty,
            "flavor": flavor,
            "detail": purpose,
            "note": note,
            "patience_minutes": patience,
            "accepted_patience": accepted_patience,
            "return_delay": return_delay,
            "due_day_offset": due_days,
            "callback_delay_days": rng.randint(1, 4),
            "seed": _stable_seed(self.world_seed, "request", day, serial),
        })
        return req
