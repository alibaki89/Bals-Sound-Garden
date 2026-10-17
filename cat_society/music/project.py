"""The music project data model.

Grid resolution comes from the synth: ``STEPS_PER_BAR`` 8th-note steps per bar.
A clip is just ``(component_id, step)``; its length on the grid is derived from
the component (one-shots take one step, loops/rhythms/ambience take their
natural length).
"""

import math
import re
import time
import uuid

from ..audio.synth import STEPS_PER_BAR
from ..components import catalog

DEFAULT_TEMPO = 100
DEFAULT_BARS = 8

# the component families a track can be (no user-sample track anymore)
FAMILIES = [
    ("Melody",   "melody"),
    ("Chords",   "chords"),
    ("Bass",     "bass"),
    ("Drums",    "drums"),
    ("Rhythms",  "rhythms"),
    ("Loops",    "loops"),
    ("Ambience", "ambience"),
]
_FAMILY_LABEL = {k: n for n, k in FAMILIES}

# every new project opens with this handful of tracks; the player adds more
DEFAULT_TRACKS = [
    ("Melody",   "melody"),
    ("Chords",   "chords"),
    ("Drums",    "drums"),
    ("Loops",    "loops"),
]


def family_label(kind):
    return _FAMILY_LABEL.get(kind, kind.title())


class ProjectValidationError(ValueError):
    """Raised when an on-disk song project is structurally unsafe."""


_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_VALID_KINDS = {kind for _label, kind in FAMILIES}


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProjectValidationError("%s must be a number" % field)
    value = float(value)
    if not math.isfinite(value):
        raise ProjectValidationError("%s must be finite" % field)
    return value


def _required_text(mapping, field, max_length=120):
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ProjectValidationError("%s must be non-empty text" % field)
    return value.strip()[:max_length]


class Clip:
    __slots__ = ("comp_id", "step")

    def __init__(self, comp_id, step):
        self.comp_id = comp_id
        self.step = int(step)


class Track:
    def __init__(self, name, kind):
        self.name = name
        self.kind = kind            # matches component["track"]
        self.clips = []
        self.muted = False
        self.volume = 0.85
        self.effect_id = None       # owned effect component applied to the track
        # connected phrases: each entry is a step-sorted list of [comp_id, step]
        # references into ``clips``.  A phrase always has at least two members.
        self.phrases = []

    def accepts(self, comp):
        return comp.get("track") == self.kind

    def add(self, comp_id, step):
        # avoid exact duplicate stacking at the same step
        for c in self.clips:
            if c.comp_id == comp_id and c.step == step:
                return
        self.clips.append(Clip(comp_id, step))

    def remove_at(self, step, comp_id=None):
        before = len(self.clips)
        if comp_id is None:
            self.clips = [c for c in self.clips if c.step != step]
        else:
            self.clips = [c for c in self.clips
                          if not (c.step == step and c.comp_id == comp_id)]
        changed = len(self.clips) != before
        if changed:
            self.heal_phrases()
        return changed

    # -- connected phrases -------------------------------------------------
    def _clip_keys(self):
        return {(c.comp_id, c.step) for c in self.clips}

    def heal_phrases(self):
        """Drop phrase members whose clip vanished; dissolve tiny phrases.

        Called after any clip removal or load so connection data can never
        point at clips that no longer exist.
        """
        keys = self._clip_keys()
        healed = []
        for phrase in self.phrases:
            seen = set()
            members = []
            for ref in phrase:
                try:
                    key = (ref[0], int(ref[1]))
                except (TypeError, ValueError, IndexError):
                    continue
                if key in keys and key not in seen:
                    seen.add(key)
                    members.append([key[0], key[1]])
            members.sort(key=lambda r: r[1])
            if len(members) >= 2:
                healed.append(members)
        self.phrases = healed

    def trim_phrases(self, total_steps):
        """After Bars-, drop members that fell off the grid, then heal."""
        for phrase in self.phrases:
            phrase[:] = [r for r in phrase if 0 <= int(r[1]) < total_steps]
        self.heal_phrases()

    def phrase_index_for(self, comp_id, step):
        for i, phrase in enumerate(self.phrases):
            for ref in phrase:
                if ref[0] == comp_id and int(ref[1]) == int(step):
                    return i
        return -1

    def phrase_index_covering(self, step):
        """Phrase whose member-step range contains ``step`` (grid column)."""
        step = int(step)
        for i, phrase in enumerate(self.phrases):
            if phrase and phrase[0][1] <= step <= phrase[-1][1]:
                return i
        return -1

    def clips_in_range(self, a, b):
        lo, hi = (a, b) if a <= b else (b, a)
        found = [c for c in self.clips if lo <= c.step <= hi]
        found.sort(key=lambda c: (c.step, c.comp_id))
        return found

    def connect_range(self, a, b):
        """Tie every clip between steps ``a`` and ``b`` into one phrase.

        Any existing phrase that overlaps the new range is dissolved first,
        so the player's latest selection always wins.  Returns the number of
        clips connected (0 means the selection was invalid).
        """
        members = self.clips_in_range(a, b)
        if len(members) < 2:
            return 0
        lo, hi = members[0].step, members[-1].step
        self.phrases = [p for p in self.phrases
                        if p[-1][1] < lo or p[0][1] > hi]
        self.phrases.append([[c.comp_id, c.step] for c in members])
        self.phrases.sort(key=lambda p: p[0][1])
        return len(members)

    def disconnect_phrase(self, index):
        if 0 <= index < len(self.phrases):
            self.phrases.pop(index)
            return True
        return False

    def to_dict(self):
        d = {
            "name": self.name, "kind": self.kind, "muted": self.muted,
            "volume": self.volume, "effect_id": self.effect_id,
            "clips": [[c.comp_id, c.step] for c in self.clips],
        }
        if self.phrases:
            # optional + versioned: absent for older saves, ignored by them
            d["phrases_v"] = 1
            d["phrases"] = [[[r[0], int(r[1])] for r in p] for p in self.phrases]
        return d

    @classmethod
    def from_dict(cls, d, total_steps=None):
        if not isinstance(d, dict):
            raise ProjectValidationError("track must be an object")
        name = _required_text(d, "name", 24)
        kind = _required_text(d, "kind", 24)
        if kind == "user":
            return None  # supported legacy track type, intentionally retired
        if kind not in _VALID_KINDS:
            raise ProjectValidationError("unsupported track kind")
        muted = d.get("muted", False)
        if not isinstance(muted, bool):
            raise ProjectValidationError("track muted must be true or false")
        volume = _number(d.get("volume", 0.85), "track volume")
        if not 0.0 <= volume <= 1.0:
            raise ProjectValidationError("track volume is outside 0..1")
        effect_id = d.get("effect_id")
        if effect_id is not None and not isinstance(effect_id, str):
            raise ProjectValidationError("effect_id must be text or null")
        clips = d.get("clips", [])
        if not isinstance(clips, list):
            raise ProjectValidationError("track clips must be a list")
        t = cls(name, kind)
        t.muted = muted
        t.volume = volume
        t.effect_id = effect_id
        for item in clips:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ProjectValidationError("clip must contain component and step")
            comp_id, step = item
            if not isinstance(comp_id, str) or isinstance(step, bool) or not isinstance(step, int):
                raise ProjectValidationError("clip component/step has wrong type")
            if step < 0 or (total_steps is not None and step >= total_steps):
                raise ProjectValidationError("clip step is outside the song")
            # Preserve historical behavior for components removed from a newer
            # catalog: the rest of the valid song still loads.
            if catalog.get(comp_id) is not None:
                t.clips.append(Clip(comp_id, step))
        raw = d.get("phrases")
        if raw is not None:
            if not isinstance(raw, list):
                raise ProjectValidationError("phrases must be a list")
            for phrase in raw:
                if not isinstance(phrase, list):
                    raise ProjectValidationError("phrase must be a list")
                parsed = []
                for ref in phrase:
                    if (not isinstance(ref, (list, tuple)) or len(ref) < 2
                            or not isinstance(ref[0], str)
                            or isinstance(ref[1], bool) or not isinstance(ref[1], int)):
                        raise ProjectValidationError("invalid phrase reference")
                    parsed.append([ref[0], ref[1]])
                t.phrases.append(parsed)
            t.heal_phrases()
        return t


class Project:
    def __init__(self, name="Untitled Song", tempo=DEFAULT_TEMPO, bars=DEFAULT_BARS):
        self.id = uuid.uuid4().hex[:12]
        self.name = name
        self.tempo = int(tempo)
        self.bars = int(bars)
        self.created = time.time()
        self.modified = self.created
        self.tracks = [Track(n, k) for n, k in DEFAULT_TRACKS]

    # -- track management -------------------------------------------------
    def add_track(self, kind, name=None):
        base = name or family_label(kind)
        existing = {t.name for t in self.tracks}
        nm, n = base, 2
        while nm in existing:
            nm, n = "%s %d" % (base, n), n + 1
        t = Track(nm, kind)
        self.tracks.append(t)
        self.touch()
        return t

    def remove_track(self, idx):
        if 0 <= idx < len(self.tracks) and len(self.tracks) > 1:
            self.tracks.pop(idx)
            self.touch()
            return True
        return False

    def duplicate_track(self, idx):
        if not (0 <= idx < len(self.tracks)):
            return None
        src = self.tracks[idx]
        t = Track(self.add_track(src.kind).name, src.kind)
        self.tracks.pop()                 # add_track appended a placeholder name
        t.volume, t.muted, t.effect_id = src.volume, src.muted, src.effect_id
        t.clips = [Clip(c.comp_id, c.step) for c in src.clips]
        t.phrases = [[[r[0], int(r[1])] for r in p] for p in src.phrases]
        self.tracks.insert(idx + 1, t)
        self.touch()
        return t

    def rename_track(self, idx, name):
        if 0 <= idx < len(self.tracks) and name.strip():
            self.tracks[idx].name = name.strip()[:24]
            self.touch()

    # -- grid helpers -----------------------------------------------------
    @property
    def total_steps(self):
        return self.bars * STEPS_PER_BAR

    def touch(self):
        self.modified = time.time()

    def clip_count(self):
        return sum(len(t.clips) for t in self.tracks)

    def components_used(self):
        ids = []
        for t in self.tracks:
            for c in t.clips:
                if c.comp_id not in ids:
                    ids.append(c.comp_id)
        return ids

    def duration_seconds(self):
        return self.total_steps * (60.0 / self.tempo) / 2.0    # 2 steps per beat

    # -- serialization ----------------------------------------------------
    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "tempo": self.tempo,
            "bars": self.bars, "created": self.created, "modified": self.modified,
            "tracks": [t.to_dict() for t in self.tracks],
        }

    @classmethod
    def from_dict(cls, d, fallback_id=None):
        if not isinstance(d, dict):
            raise ProjectValidationError("project must be an object")
        version = d.get("version", 1)
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise ProjectValidationError("unsupported project version")
        name = _required_text(d, "name", 80)
        tempo_raw = _number(d.get("tempo"), "tempo")
        bars_raw = _number(d.get("bars"), "bars")
        if not tempo_raw.is_integer() or not 20 <= tempo_raw <= 400:
            raise ProjectValidationError("tempo is outside supported range")
        if not bars_raw.is_integer() or not 1 <= bars_raw <= 256:
            raise ProjectValidationError("bars is outside supported range")
        tempo, bars = int(tempo_raw), int(bars_raw)
        tracks = d.get("tracks")
        if not isinstance(tracks, list) or not tracks:
            raise ProjectValidationError("tracks must be a non-empty list")
        if len(tracks) > 64:
            raise ProjectValidationError("too many tracks")
        project_id = d.get("id", fallback_id)
        if not isinstance(project_id, str) or not _ID_RE.fullmatch(project_id):
            raise ProjectValidationError("invalid project id")
        created = _number(d.get("created", time.time()), "created")
        modified = _number(d.get("modified", created), "modified")
        p = cls(name, tempo, bars)
        p.id = project_id
        p.created = created
        p.modified = modified
        kept = []
        for track_data in tracks:
            track = Track.from_dict(track_data, total_steps=p.total_steps)
            if track is not None:
                kept.append(track)
        p.tracks = kept or [Track(n, k) for n, k in DEFAULT_TRACKS]
        return p
