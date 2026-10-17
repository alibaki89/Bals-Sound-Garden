"""Garden Works: the notice stump's commissions -- the game's goal structure.

A *work* is a concrete musical task with checkable properties.  Three kinds:

* ``plant``   -- survey the garden's layout (counts, clusters, chains, loops
                 of sprouts) via :class:`SproutManager`'s geometry helpers.
* ``song``    -- perform a saved song at the stump; its
                 :class:`SongProfile` is checked with the same soft rules the
                 Maker teaches (tags, families, tempo, energy).
* ``machine`` -- operate a garden device (the windmill seed bed) until its
                 own meter completes.

Checks are ingredient-based and never judgmental: an unmet work answers with
one warm pointer at the first missing ingredient ("this wants a clearer
beat"), never a score.  Completing a work stamps it into the Songbook, pays
out sound components you cannot find on the ground, and opens the next
commissions.  Everything persists in ``save/world.json``.

Chapters gate cleanly: Chapter 1 teaches planting, Chapter 2 teaches briefs
in the Maker, Chapter 3 combines both with the gramophone and the windmill.
"""

from ..components import catalog
from ..music import profile as profile_mod

# ---------------------------------------------------------------------------
# The works themselves.  Kept as plain data + tiny check lambdas so adding a
# chapter is an afternoon, not a refactor.
#
# plant checks receive (sprouts, garden, context) -> (done, hint)
# song checks receive a SongProfile        -> (done, hint)
# machine works are completed by the device itself calling works.complete().
# ---------------------------------------------------------------------------


def _tags(c):
    return profile_mod.tags_for(c)


def _is_perc(c):
    return c.get("type") in ("drum", "rhythm")


WORKS = [
    # ---------------- Chapter 1: the garden is an instrument ---------------
    dict(
        id="w_first_sprouts", ch=1, name="First Sprouts",
        kind="plant",
        ask=["Plant any 3 sounds from your satchel.",
             "Stand where you want one, press F, pick a seed."],
        short="plant any 3 sounds (F)",
        check=lambda sp, g, _context: (sp.count() >= 3,
                             "Two more sprouts and the bed is started."
                             if sp.count() == 1 else
                             "One more sprout will do it."
                             if sp.count() == 2 else
                             "Press F to plant your first sound."),
        pay=["gift_rabbit_shake"],
        done_line="The stump approves. The garden has its first voices.",
    ),
    dict(
        id="w_perc_row", ch=1, name="A Row You Can Walk",
        kind="plant",
        ask=["Plant a row of 4 percussion sprouts,",
             "each within a short hop of the next,",
             "so one walk plays them all in rhythm."],
        short="a little walking row: 4 percussion sprouts",
        check=lambda sp, g, _context: (
            sp.chain(_is_perc, 150.0, 4) >= 4,
            "%d in the row so far -- drums and rhythms count, planted "
            "close enough to pad from one soil ring into the next."
            % sp.chain(_is_perc, 150.0, 4)),
        pay=["gift_frog_hop"],
        done_line="Walk it slow, walk it fast -- the row keeps your time.",
    ),
    dict(
        id="w_night_corner", ch=1, name="A Night Corner",
        kind="plant",
        ask=["Give the garden a nighttime spot:",
             "3 night-tagged sprouts gathered in one bed.",
             "(Deepwood finds, owl sounds, moon plucks...)"],
        short="3 night sprouts in one bed",
        check=lambda sp, g, _context: (
            sp.cluster(lambda c: "night" in _tags(c), 170.0, 3),
            "Night sounds sit in the journal under Deepwood, and a few "
            "animal sounds carry the tag too. %d planted so far."
            % sp.count_pred(lambda c: "night" in _tags(c))),
        pay=["gift_fox_pluck"],
        done_line="After this, evening walks will sound like evenings.",
    ),
    # ---------------- Chapter 2: the maker takes commissions ----------------
    dict(
        id="w_walking_beat", ch=2, name="Commission: A Walking Beat",
        kind="song",
        ask=["The stump wants a stroll-tempo groove:",
             "at least 2 bars, with drums,",
             "tempo between 96 and 120, nothing frantic."],
        short="2+ bars, drums, tempo 96-120, easy energy",
        req=dict(needs=["drums"], min_tempo=96, max_tempo=120, calm=True,
                 min_clips=3,
                 nudges=dict(
                     needs="It taps its roots... this wants a clearer beat.",
                     min_tempo="A touch quicker -- this is for walking, not napping.",
                     max_tempo="A touch slower -- a stroll, not a sprint.",
                     calm="Lighter on the layers; easy strolling energy.",
                     empty="A few more sounds on the grid first.")),
        pay=["gift_chime_breeze"],
        done_line="Stamped into the Songbook: the garden's walking beat.",
    ),
    dict(
        id="w_windmill", ch=2, name="Pump the Seed Bed",
        kind="machine",
        ask=["The old windmill pumps while drummed music plays nearby.",
             "Your new walking beat would do nicely --",
             "perform it beside the mill until the bed has drunk its fill."],
        short="fill the windmill meter with drummed music",
        pay=[],                            # the bed itself grows the pay
        done_line="The bed drinks deep. Something rare is sprouting...",
    ),
    dict(
        id="w_record_power", ch=2, name="A Loop That Keeps Working",
        kind="plant",
        ask=["Machines shouldn't need you standing there.",
             "Plant a gramophone with a drummed record",
             "near the windmill and let it pump on its own for a while."],
        short="a record powers the mill for 12s",
        check="RECORD_POWER",
        pay=[],
        done_line="The mill runs on your record now.  That's automation, Bal.",
    ),
    dict(
        id="w_rain_loop", ch=2, name="Commission: Rain on the Beds",
        kind="song",
        ask=["A rain piece for the thirsty rows:",
             "use at least 3 watery sounds,",
             "and let a melody run through it."],
        short="3+ watery sounds, with a melody",
        req=dict(any_tags=["watery"], needs=["melody"], min_clips=3,
                 min_tag_count=("watery", 3),
                 nudges=dict(
                     any_tags="It listens for water -- riverside sounds carry it.",
                     min_tag_count="More water in it: three watery sounds at least.",
                     needs="Rain likes a melody threading through.",
                     empty="A few more sounds on the grid first.")),
        pay=["gift_fountain_mist"],
        done_line="The beds drink it in. Stamped and shelved.",
    ),
    dict(
        id="w_reed_lullaby", ch=2, name="Commission: Reed Lullaby",
        kind="song",
        ask=["Something for the reeds at dusk:",
             "slow (92 or under), soft energy,",
             "melody present, nothing loud on top."],
        short="tempo <= 92, low energy, melody",
        req=dict(needs=["melody"], max_tempo=92, energy_at_most="low",
                 min_clips=2,
                 nudges=dict(
                     needs="Even a lullaby wants a little melody.",
                     max_tempo="Slower still -- reeds nod at 92 or under.",
                     energy_at_most="Fewer, softer layers; let it breathe.",
                     empty="A few more sounds on the grid first.")),
        pay=["gift_grove_pad"],
        done_line="The reeds settle. Stamped into the Songbook.",
    ),
    # ---------------- Chapter 3: shape the garden ---------------------------
    dict(
        id="w_soft_corner", ch=3, name="A Corner for Napping",
        kind="plant",
        ask=["Make somewhere hushed: 4 soft sprouts",
             "(pads, notes, washes) gathered in one bed,",
             "with no drums crowding in."],
        short="4 soft sprouts together, no drums near",
        check=lambda sp, g, _context: (lambda ok, n: (
            ok, "%d soft sprouts gathered -- and keep drums a little away."
            % n))(*_quiet_bed(sp, 180.0, 4)),
        pay=[],
        done_line="Hushed and green.  Even the wind walks softer here.",
    ),
    dict(
        id="w_lively_corner", ch=3, name="A Corner for Dancing",
        kind="plant",
        ask=["Now somewhere lively: 5 quick sounds",
             "(drums and rhythms) packed into one patch",
             "so crossing it is a little celebration."],
        short="5 percussion sprouts in one patch",
        check=lambda sp, g, _context: (
            sp.cluster(_is_perc, 160.0, 5),
            "%d percussion planted so far -- tuck 5 into one patch."
            % sp.count_pred(_is_perc)),
        pay=[],
        done_line="Cross it and try not to bounce.  Impossible.",
    ),
    dict(
        id="w_two_families", ch=3, name="A Mixed Bed",
        kind="plant",
        ask=["One bed, three voices: gather 6 sprouts",
             "in one spot using at least 3 different",
             "sound families (drums, notes, pads, vines...)."],
        short="6 sprouts, 3+ families, one bed",
        check=lambda sp, g, _context: (
            _mixed_bed(sp, 200.0, 6, 3) >= 3,
            "The fullest bed holds %d famil%s -- mix in another kind."
            % (_mixed_bed(sp, 200.0, 6, 3),
               "y" if _mixed_bed(sp, 200.0, 6, 3) == 1 else "ies")),
        pay=[],
        done_line="Layers!  The bed sings in parts now.",
    ),
    dict(
        id="w_animal_band", ch=3, name="The Accidental Band",
        kind="plant",
        ask=["Let the garden's animals do the playing:",
             "plant where they wander, and let them",
             "ring 4 different sprouts on their own."],
        short="animals ring 4 different sprouts",
        check=lambda sp, g, _context: (
            sp.animal_ring_count() >= 4,
            "They've rung %d so far -- plant along their trails "
            "and give it a little time." % sp.animal_ring_count()),
        pay=[],
        done_line="A band that doesn't know it's a band.  The best kind.",
    ),
    dict(
        id="w_score_pond", ch=3, name="Score the Pond",
        kind="plant",
        ask=["Plant a gramophone by the water",
             "loaded with a watery song of yours,",
             "so the pond has a record playing."],
        short="a gramophone with a watery song near water",
        check="POND",                      # resolved by the works manager
        pay=["gift_duck_paddle"],
        done_line="The pond keeps your record spinning.",
    ),
    dict(
        id="w_gramo_route", ch=4, name="Score Your Loop",
        kind="plant",
        ask=["Put a record where the walking happens:",
             "plant a gramophone close beside a row or loop",
             "of at least 4 sprouts, so both play together."],
        short="a gramophone beside 4+ sprouts",
        check=lambda sp, g, _context: (
            _gramo_near_chain(sp, g, 260.0, 4),
            "Carry a gramophone (seed tray, F) into one of your "
            "planted patches."),
        pay=[],
        done_line="Record and row, playing over each other.  Lovely racket.",
    ),
    dict(
        id="w_long_loop", ch=4, name="The Long Loop",
        kind="plant",
        ask=["Plant a closed circuit of 8 or more sprouts --",
             "any kinds -- each a hop from the next,",
             "so a full lap of it plays a full phrase."],
        short="a closed loop of 8+ sprouts",
        check=lambda sp, g, _context: (
            sp.loop_of(lambda c: True, 180.0, 8),
            "%d sprouts planted; link them ring-to-ring and close the circle."
            % sp.count()),
        pay=["gift_chime_cascade", "gift_owl_watch"],
        done_line="Lap it once and listen: the garden plays a whole verse.",
    ),
]



def _soft(c):
    return c.get("type") in ("ambience", "chord", "note", "loop", "bass")


def _melodic(c):
    return c.get("type") in ("note", "chord")


def _mixed_bed(sp, radius, need, families):
    pts = sp.by_pred(lambda c: True)
    r2 = radius * radius
    best = 0
    for a in pts:
        near = [b for b in pts
                if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= r2]
        if len(near) >= need:
            fams = {b.comp.get("type") for b in near if b.comp}
            best = max(best, len(fams))
    return best


def _quiet_bed(sp, radius, need):
    pts = sp.by_pred(_soft)
    r2 = radius * radius
    counts = [sum(1 for b in pts
                  if (a.x - b.x) ** 2 + (a.z - b.z) ** 2 <= r2) for a in pts]
    drums = sp.by_pred(lambda c: c.get("type") in ("drum", "rhythm"))
    for a, n in zip(pts, counts):
        if n >= need and not any(
                (a.x - d.x) ** 2 + (a.z - d.z) ** 2 <= (radius + 60) ** 2
                for d in drums):
            return True, n
    return False, max(counts or [0])


def _gramo_near_chain(sp, garden, dist, need):
    for g in garden.gramophones:
        close = [s for s in sp.sprouts
                 if (s.x - g.x) ** 2 + (s.z - g.z) ** 2 <= dist * dist]
        if len(close) >= need:
            return True
    return False


_BY_ID = {w["id"]: w for w in WORKS}


class WorksManager:
    """Tracks which works are open / done, checks them, pays them out."""

    def __init__(self, state, collection):
        self.state = state
        self.collection = collection
        self._events = []              # completed works to announce

    # -- persistence ----------------------------------------------------------
    def _rec(self):
        return self.state.data_dict("works")

    def is_done(self, wid):
        return bool(self._rec().get(wid, {}).get("done"))

    def song_used(self, wid):
        return self._rec().get(wid, {}).get("song", "")

    def chapter(self):
        """Current chapter = first chapter with an unfinished work."""
        for ch in (1, 2, 3, 4, 5):
            if any(w["ch"] == ch and not self.is_done(w["id"])
                   for w in WORKS):
                return ch
        return 5

    def open_works(self):
        ch = self.chapter()
        return [w for w in WORKS if w["ch"] <= ch and not self.is_done(w["id"])]

    def done_works(self):
        return [w for w in WORKS if self.is_done(w["id"])]

    def all_done(self):
        return all(self.is_done(w["id"]) for w in WORKS)

    # -- the active work (what the objective plate points at) ------------------
    def active(self):
        wid = self.state.data_dict("meta").get("active_work")
        w = _BY_ID.get(wid)
        if w is not None and not self.is_done(wid):
            return w
        opens = self.open_works()
        return opens[0] if opens else None

    def set_active(self, wid):
        self.state.data_dict("meta")["active_work"] = wid
        self.state.touch()

    # -- completing --------------------------------------------------------------
    def complete(self, wid, song_name=""):
        if self.is_done(wid):
            return
        rec = self._rec().setdefault(wid, {})
        rec["done"] = True
        if song_name:
            rec["song"] = song_name
        self.state.touch()
        w = _BY_ID[wid]
        if w.get("unlock"):
            self.state.set_flag(w["unlock"])
        paid = []
        for cid in w.get("pay", ()):
            comp = catalog.get(cid)
            if comp is not None and not self.collection.owns(cid):
                self.collection.collect(cid)
                paid.append(comp)
        self._events.append((w, paid))

    def pop_events(self):
        out, self._events = self._events, []
        return out

    # -- checking ---------------------------------------------------------------
    def survey_plant(self, work, sprouts, garden, context=None, cat=None):
        """(done?, hint) for a plant work.  Completes it on success."""
        ok, hint = self.peek(work, sprouts, garden, context, cat)
        if ok:
            self.complete(work["id"])
        return ok, hint

    def peek(self, work, sprouts, garden, context=None, cat=None):
        """Same check, no completion -- for showing live progress hints."""
        if work["kind"] == "song":
            return False, "Perform it at the stump (P) with this active."
        if work["kind"] == "machine":
            from ..world.garden import METER_FULL
            frac = garden.mill_meter() / METER_FULL
            if frac <= 0.02:
                h = "The bed is dry so far -- drums nearby will start the pump."
            elif frac < 0.34:
                h = "The bed has had a first drink -- keep the beat going."
            elif frac < 0.67:
                h = "Past halfway -- the soil is darkening."
            else:
                h = "Nearly full... a little more rhythm."
            return False, h
        chk = work.get("check")
        if chk == "POND":
            return garden.pond_scored()
        if chk == "RECORD_POWER":
            s = garden.record_powered_s()
            if s >= 12.0:
                return True, ""
            if s > 0.5:
                return False, ("The record has pumped for %d seconds -- "
                               "let it keep going." % int(s))
            return False, ("Plant a gramophone holding a drummed song "
                           "within earshot of the mill, then step back.")
        return chk(sprouts, garden, context)

    def check_song(self, work, profile, song_name):
        """(done?, hint) for a song work performed at the stump."""
        ok, nudge = soft_check_song(profile, work["req"])
        if ok:
            self.complete(work["id"], song_name=song_name)
        return ok, nudge


def soft_check_song(profile, req):
    """profile.soft_check plus the two extras works use:

    * ``min_tag_count``: ("watery", 3) -> at least 3 clips carrying the tag
    * ``energy_at_most``: "low" / "mid"
    """
    need = req.get("min_tag_count")
    if need:
        tag, n = need
        if profile.tag_counts.get(tag, 0) < n:
            return False, req.get("nudges", {}).get(
                "min_tag_count", "It wants more of one kind of sound.")
    cap = req.get("energy_at_most")
    if cap:
        order = {"low": 0, "mid": 1, "high": 2}
        if order.get(profile.energy, 1) > order.get(cap, 2):
            return False, req.get("nudges", {}).get(
                "energy_at_most", "A little softer, a little sparser.")
    return profile_mod.soft_check(profile, req)
