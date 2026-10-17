"""Explainable scoring for shop commissions.

The shop never grades prose.  It compares the structured request with either a
SongProfile or one component and returns small named parts that the result card
can explain.  The module has no pygame dependency, so request balance can be
tested without opening the game.
"""

from dataclasses import dataclass, field
import hashlib
import json

from .. import config
from ..components.rarity import ORDER as RARITY_ORDER
from ..music.profile import tags_for


_NEED_ATTR = {
    "melody": "has_melody",
    "chords": "has_chords",
    "bass": "has_bass",
    "drums": "has_drums",
}
_ENERGY = {"low": 0, "mid": 1, "high": 2}
_ADJACENT_TYPES = {
    ("rhythm", "drum"), ("drum", "rhythm"),
    ("loop", "note"), ("note", "loop"),
    ("chord", "bass"), ("bass", "chord"),
    ("ambience", "effect"), ("effect", "ambience"),
}


@dataclass
class ScoreBreakdown:
    total: float
    passed: bool
    parts: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    cap: float = 1.0
    penalty: float = 0.0

    def percent(self, key):
        return int(round(max(0.0, min(1.0, self.parts.get(key, 0.0))) * 100))




def project_content_hash(project):
    """Stable arrangement hash; renaming a song does not make it fresh again."""
    tracks = []
    for track in getattr(project, "tracks", ()):
        clips = sorted((str(c.comp_id), int(c.step)) for c in getattr(track, "clips", ()))
        phrases = []
        for phrase in getattr(track, "phrases", ()):
            phrases.append(sorted((str(r[0]), int(r[1])) for r in phrase))
        tracks.append({
            "kind": str(getattr(track, "kind", "")),
            "muted": bool(getattr(track, "muted", False)),
            "volume": round(float(getattr(track, "volume", .85)), 3),
            "effect": getattr(track, "effect_id", None),
            "clips": clips,
            "phrases": phrases,
        })
    payload = {
        "tempo": int(getattr(project, "tempo", 100)),
        "bars": int(getattr(project, "bars", 8)),
        "tracks": tracks,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _required_family(profile, needs):
    needs = tuple(needs or ())
    if not needs:
        return 1.0, []
    missing = []
    found = 0
    for need in needs:
        attr = _NEED_ATTR.get(need)
        ok = bool(attr and getattr(profile, attr, False))
        found += int(ok)
        if not ok:
            missing.append(need)
    return found / float(len(needs)), missing


def _tag_alignment(profile, request):
    counts = dict(getattr(profile, "tag_counts", {}) or {})
    clips = max(1, int(getattr(profile, "clip_count", 0)))
    primary = request.get("primary") or request.get("primary_tag") or "warm"
    support = tuple(request.get("support_tags") or ())
    if not support:
        raw = tuple(request.get("tags") or ())
        support = tuple(t for t in raw if t != primary)[:2]

    pshare = counts.get(primary, 0) / float(clips)
    primary_score = _clamp(pshare / 0.34)
    support_scores = []
    for tag in support:
        share = counts.get(tag, 0) / float(clips)
        present = 1.0 if counts.get(tag, 0) else 0.0
        support_scores.append(0.60 * present + 0.40 * _clamp(share / 0.24))
    support_score = sum(support_scores) / len(support_scores) if support_scores else 1.0
    combined = 0.72 * primary_score + 0.28 * support_score

    banned = request.get("banned_tag")
    banned_share = counts.get(banned, 0) / float(clips) if banned else 0.0
    penalty = 0.15 if banned and banned_share >= 0.34 else 0.0
    return _clamp(combined), penalty, pshare, banned_share


def _tempo_fit(tempo, request):
    lo, hi = request.get("tempo", (request.get("tempo_lo", 80), request.get("tempo_hi", 120)))
    lo, hi = float(lo), float(hi)
    bpm = float(tempo)
    if lo <= bpm <= hi:
        return 1.0
    distance = lo - bpm if bpm < lo else bpm - hi
    return _clamp(1.0 - distance / 30.0)


def _energy_fit(actual, wanted):
    a = _ENERGY.get(actual, 1)
    b = _ENERGY.get(wanted, 1)
    distance = abs(a - b)
    return 1.0 if distance == 0 else 0.5 if distance == 1 else 0.0


def _effort(profile, request):
    bars = max(0.0, float(getattr(profile, "bars", 0)))
    clips = max(0.0, float(getattr(profile, "clip_count", 0)))
    min_bars = max(1.0, float(request.get("min_bars", 8)))
    min_clips = max(1.0, float(request.get("min_clips", 4)))
    return _clamp(bars / min_bars) * _clamp(clips / min_clips)


def _cohesion(profile):
    counts = sorted((int(v) for v in (getattr(profile, "tag_counts", {}) or {}).values() if v > 0), reverse=True)
    total = sum(counts)
    if total <= 0:
        return 0.0
    concentration = sum(counts[:2]) / float(total)
    distinct = len(counts)
    if distinct <= 3:
        return 1.0
    variety_cost = max(0.0, (distinct - 5) * 0.08)
    return _clamp(concentration * 1.35 - variety_cost)


def score_song(profile, request, times_sold=0):
    """Score one SongProfile against one structured brief."""
    family, missing = _required_family(profile, request.get("needs", ()))
    tags, penalty, primary_share, banned_share = _tag_alignment(profile, request)
    tempo = _tempo_fit(getattr(profile, "tempo", 100), request)
    energy = _energy_fit(getattr(profile, "energy", "mid"), request.get("energy", "mid"))
    effort = _effort(profile, request)
    cohesion = _cohesion(profile)

    parts = {
        "required families": family,
        "mood": tags,
        "tempo": tempo,
        "energy": energy,
        "effort": effort,
        "cohesion": cohesion,
    }
    raw = family * 0.25 + tags * 0.30 + tempo * 0.15 + energy * 0.10 + effort * 0.10 + cohesion * 0.10
    raw -= penalty
    cap = 0.35 if missing else 1.0
    raw = min(cap, raw)
    freshness = float(getattr(config, "STORY_FRESHNESS_DECAY", 0.60)) ** max(0, int(times_sold))
    total = _clamp(raw * freshness)

    notes = []
    if missing:
        notes.append("Missing required part: %s." % ", ".join(missing))
    if primary_share < 0.18:
        notes.append("The main mood was hard to hear.")
    if penalty:
        notes.append("The unwanted mood became too strong.")
    if effort < 0.75:
        notes.append("The arrangement needed more development.")
    if cohesion < 0.55:
        notes.append("Too many moods competed with each other.")
    if times_sold:
        notes.append("This arrangement has already been sold before.")
    if not notes:
        notes.append("The song matched the request clearly.")
    return ScoreBreakdown(total, total >= float(getattr(config, "STORY_PASS_SCORE", 0.55)),
                          parts, notes, cap, penalty)


def score_sprout(component, request):
    wanted_type = request.get("want_type", "note")
    actual_type = component.get("type")
    type_score = 1.0 if actual_type == wanted_type else 0.43 if (actual_type, wanted_type) in _ADJACENT_TYPES else 0.0

    wanted = tuple(request.get("want_tags") or request.get("tags") or (request.get("primary", "warm"),))
    actual_tags = set(tags_for(component))
    weights = [2.0] + [1.0] * max(0, len(wanted) - 1)
    matched = sum(weight for tag, weight in zip(wanted, weights) if tag in actual_tags)
    tag_score = matched / float(sum(weights) or 1.0)

    wanted_region = request.get("want_region") or request.get("region")
    region_score = 1.0 if component.get("region") == wanted_region else 0.0

    ranks = {name: i for i, name in enumerate(RARITY_ORDER)}
    actual_rank = ranks.get(component.get("rarity", "common"), 0)
    minimum_rank = ranks.get(request.get("min_rarity", "common"), 0)
    rarity_score = 1.0 if actual_rank >= minimum_rank else 0.5 if actual_rank == minimum_rank - 1 else 0.0

    parts = {
        "sound type": type_score,
        "mood": tag_score,
        "region": region_score,
        "rarity": rarity_score,
    }
    total = _clamp(type_score * 0.35 + tag_score * 0.30 + region_score * 0.15 + rarity_score * 0.20)
    notes = []
    if type_score < 1.0:
        notes.append("The sound type was not an exact match.")
    if tag_score < 0.5:
        notes.append("The requested mood was hard to hear.")
    if region_score == 0.0:
        notes.append("The seed came from a different region.")
    if rarity_score == 0.0:
        notes.append("The client asked for a rarer seed.")
    if not notes:
        notes.append("The seed matched every part of the request.")
    return ScoreBreakdown(total, total >= float(getattr(config, "STORY_PASS_SCORE", 0.55)),
                          parts, notes)
