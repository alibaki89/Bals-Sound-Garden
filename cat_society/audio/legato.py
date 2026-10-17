"""Connected-phrase ("legato") rendering.

A phrase is an ordered set of clips on one track that the player has tied
together in the Music Maker.  This module turns a phrase into ONE mono float
buffer so the audio system can treat it as a single musical object: one
attack, a continuous body, smooth internal transitions and one final release.

The renderer classifies every component into a connection family and picks a
musically appropriate technique per family instead of forcing one trick onto
everything:

``sustain``
    Winds, brass, organs, pads, strings, choirs, leads and sustaining basses
    are re-synthesised continuously.  A single phase-integrated frequency
    curve runs through the whole phrase (with per-family portamento at note
    changes -- or none for organ/chiptune, which switch instantly), so a run
    of identical tiles is literally one oscillator ringing under one
    envelope.  There is no looping and no per-tile re-attack by construction.
    Different timbres on the same track morph through equal-power overlaps at
    sustain level.  ComponentDNA timbres with a real sustain segment build
    their profile straight from the patch data.

``ring``
    Plucks, bells, mallets, keys and other naturally decaying sounds are
    handled as a performer would: a run of identical tiles becomes one strike
    rendered at the full merged duration (their synthesis models scale decay
    with duration, so this is a genuine extended resonance, not a loop), and
    changing notes ring into each other with no gaps.

``hit`` / ``pattern``
    Drum one-shots, rhythm patterns and loops keep their rhythmic identity:
    connected playback places every event on one shared timeline so tails
    ring across old tile boundaries, with no stretching into drones.

``bed``
    Ambiences fill their span through seam-hidden crossfade tiling and join
    neighbours with long equal-power crossfades.

``sample``
    Imported WAVs use a safe sampler-style fallback: the sound plays once,
    sustains through a crossfaded body region when it must fill more time,
    and keeps its natural tail.  Missing buffers render silence instead of
    crashing.

Rendering is deterministic (seeded per phrase under the shared render lock),
so live playback and the WAV exporter produce identical audio.
"""

import hashlib
import threading
from collections import OrderedDict

import numpy as np

from . import synth
from .synth import SR

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
FAMILY_SUSTAIN = "sustain"
FAMILY_RING = "ring"
FAMILY_HIT = "hit"
FAMILY_PATTERN = "pattern"
FAMILY_BED = "bed"
FAMILY_SAMPLE = "sample"

# Voices whose synthesis model has a true sustain segment.  Everything melodic
# that is not listed here decays naturally and is treated as ``ring``.
_SUSTAIN_VOICES = {
    "organ", "flute", "clarinet", "oboe", "reed", "whistle",
    "brass", "muted_brass", "vox", "choir", "accordion",
    "warm_pad", "strings", "analog_pad", "dream_pad", "supersaw",
    "crystal_pad", "soft_lead", "chiptune",
    "warm_bass", "sub_bass", "synth_bass", "acid_bass", "fm_bass",
    "purr", "hoot", "croak",
}

_MIN_PROC_SUSTAIN = 0.25       # DNA patches below this behave like plucks


def _timbre_is_sustain(spec):
    try:
        sustain = float(spec.get("sustain", 0.62))
    except (TypeError, ValueError):
        sustain = 0.62
    return sustain >= _MIN_PROC_SUSTAIN


def classify(comp):
    """Connection family for one component."""
    typ = comp.get("type", "note")
    if typ == "user":
        return FAMILY_SAMPLE
    if typ == "ambience":
        return FAMILY_BED
    if typ in ("rhythm", "loop"):
        return FAMILY_PATTERN
    if typ == "drum":
        return FAMILY_HIT
    if typ in ("note", "chord"):
        spec = comp.get("timbre")
        if spec:
            return FAMILY_SUSTAIN if _timbre_is_sustain(spec) else FAMILY_RING
        voice = comp.get("voice", "music_box")
        return FAMILY_SUSTAIN if voice in _SUSTAIN_VOICES else FAMILY_RING
    return FAMILY_RING


# ---------------------------------------------------------------------------
# Sustain profiles.  Each mirrors the recipe of its ``synth._v_*`` voice so a
# connected flute still sounds like the flute, only continuous.  Fields:
#   osc      [(kind, freq multiple, gain, duty)]
#   detune   unison stack in cents (pads)
#   partials extra sine multiples [(ratio, gain)]
#   fm       (ratio, index) phase modulation on the fundamental
#   filt     ("lp", cutoff_fn) or ("bp", lo_fn, hi_fn) of the top phrase freq
#   breath   (gain, highpass_hz) constant air noise
#   noisebed (gain, lowpass_hz, am_rate_hz) gated noise body (purr)
#   vib      (rate_hz, depth_cents) real pitch vibrato, eased in
#   trem     (rate_hz, depth) amplitude tremolo
#   move     slow amplitude drift depth (pads)
#   attack / release   seconds for the ONE phrase attack and release
#   glide    portamento seconds at note changes (0 = instant, e.g. organ)
#   post     optional name of a gentle post effect ("dream_verb")
# ---------------------------------------------------------------------------
def _lp(fn):
    return ("lp", fn)


def _bp(lo, hi):
    return ("bp", lo, hi)


_P = {}


def _profile(name, **kw):
    kw.setdefault("osc", [("sine", 1.0, 1.0, 0.5)])
    kw.setdefault("detune", (0.0,))
    kw.setdefault("partials", ())
    kw.setdefault("fm", None)
    kw.setdefault("filt", None)
    kw.setdefault("breath", None)
    kw.setdefault("noisebed", None)
    kw.setdefault("vib", None)
    kw.setdefault("trem", None)
    kw.setdefault("move", 0.0)
    kw.setdefault("attack", 0.05)
    kw.setdefault("release", 0.3)
    kw.setdefault("glide", 0.04)
    kw.setdefault("post", None)
    _P[name] = kw


def _reed_profile(name, brightness, vib_rate, breath, attack, glide=0.045):
    _profile(name,
             osc=[("sine", 1.0, 1.0 - brightness, 0.5),
                  ("saw", 1.0, brightness * 0.65, 0.5),
                  ("square", 2.0, 0.22, 0.42)],
             filt=_lp(lambda f, b=brightness: min(9000.0, f * (5.0 + 4.0 * b) + 900.0)),
             breath=(breath, 1800.0),
             vib=(vib_rate, 7.0), attack=attack, release=0.30, glide=glide)


def _pad_profile(name, detunes, brightness, attack, move, release=0.5,
                 glide=0.09, post=None, extra_partials=(), trem=None):
    _profile(name,
             osc=[("triangle", 1.0, 1.0 - brightness, 0.5),
                  ("saw", 1.0, brightness, 0.5)],
             detune=tuple(detunes),
             partials=tuple(extra_partials),
             filt=_lp(lambda f, b=brightness: f * (2.6 + b * 4.0) + 650.0),
             move=move, attack=attack, release=release, glide=glide,
             post=post, trem=trem)


_profile("organ",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 2.0, 0.55, 0.5),
              ("sine", 3.0, 0.28, 0.5), ("sine", 4.0, 0.14, 0.5)],
         attack=0.035, release=0.16, glide=0.0)
_reed_profile("flute", 0.10, 5.1, 0.055, 0.08)
_reed_profile("clarinet", 0.30, 4.5, 0.018, 0.045)
_reed_profile("oboe", 0.62, 5.4, 0.025, 0.055)
_reed_profile("reed", 0.46, 4.2, 0.030, 0.040)
_profile("whistle",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 2.0, 0.12, 0.5)],
         breath=(0.02, 2600.0), vib=(5.0, 4.0),
         attack=0.035, release=0.24, glide=0.05)
_profile("brass",
         osc=[("saw", 1.0, 1.0, 0.5), ("square", 1.0, 0.38, 0.43)],
         filt=_lp(lambda f: f * 5.2 + 1000.0),
         attack=0.045, release=0.30, glide=0.035)
_profile("muted_brass",
         osc=[("saw", 1.0, 1.0, 0.5), ("square", 2.0, 0.24, 0.30)],
         filt=_bp(lambda f: 350.0, lambda f: min(7000.0, f * 7.0 + 1400.0)),
         attack=0.018, release=0.26, glide=0.03)
_profile("vox",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 2.0, 0.45, 0.5),
              ("sine", 3.0, 0.20, 0.5)],
         filt=_bp(lambda f: 250.0, lambda f: 3600.0),
         attack=0.14, release=0.34, glide=0.07)
_profile("choir",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 2.0, 0.38, 0.5),
              ("sine", 3.0, 0.18, 0.5)],
         filt=_bp(lambda f: max(80.0, f * 0.7), lambda f: min(7000.0, f * 6.0 + 1500.0)),
         trem=(4.2, 0.08), attack=0.22, release=0.36, glide=0.08)
_profile("accordion",
         osc=[("saw", 1.0, 0.62, 0.5), ("square", 2.0, 0.38, 0.42)],
         filt=_lp(lambda f: f * 6.0 + 1400.0),
         trem=(5.0, 0.06), attack=0.035, release=0.24, glide=0.0)
_profile("warm_pad",
         osc=[("saw", 1.0, 1.0, 0.5)], detune=(0.0, -7.0, 7.0, -3.0),
         filt=_lp(lambda f: f * 3.0 + 700.0),
         attack=0.30, release=0.45, glide=0.09)
_pad_profile("strings", (-7, -2, 2, 7), 0.46, 0.18, 0.08, release=0.40, glide=0.06)
_pad_profile("analog_pad", (-9, -3, 3, 9), 0.42, 0.26, 0.14)
_pad_profile("dream_pad", (-12, -5, 0, 5, 12), 0.22, 0.34, 0.22,
             release=0.60, glide=0.10, post="dream_verb")
_pad_profile("supersaw", (-14, -9, -4, 0, 4, 9, 14), 0.70, 0.07, 0.08,
             release=0.30, glide=0.03)
_pad_profile("crystal_pad", (-7, 0, 7), 0.22, 0.30, 0.16, release=0.50,
             glide=0.08, extra_partials=((4.0, 0.12), (6.01, 0.06)),
             trem=(9.0, 0.05))
_profile("soft_lead",
         osc=[("sine", 1.0, 1.0, 0.5), ("triangle", 1.0, 0.3, 0.5)],
         filt=_lp(lambda f: f * 6.0 + 1200.0),
         vib=(5.0, 4.0), attack=0.02, release=0.26, glide=0.03)
_profile("chiptune",
         osc=[("square", 1.0, 0.75, 0.25), ("square", 2.0, 0.25, 0.5)],
         attack=0.003, release=0.18, glide=0.0)
_profile("warm_bass",
         osc=[("sine", 1.0, 1.0, 0.5), ("saw", 1.0, 0.5, 0.5),
              ("sine", 0.5, 0.3, 0.5)],
         filt=_lp(lambda f: f * 4.0 + 250.0),
         attack=0.004, release=0.28, glide=0.025)
_profile("sub_bass",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 0.5, 0.42, 0.5)],
         filt=_lp(lambda f: max(220.0, f * 3.0)),
         attack=0.003, release=0.25, glide=0.02)
_profile("synth_bass",
         osc=[("sine", 1.0, 1.0, 0.5), ("triangle", 1.0, 0.45, 0.5)],
         filt=_lp(lambda f: max(500.0, f * 7.0)),
         attack=0.003, release=0.25, glide=0.02)
_profile("acid_bass",
         osc=[("saw", 1.0, 1.0, 0.5), ("square", 1.0, 0.35, 0.36)],
         filt=_lp(lambda f: max(900.0, f * 9.0)),
         attack=0.003, release=0.22, glide=0.06)
_profile("fm_bass",
         fm=(2.0, 1.8),
         filt=_lp(lambda f: max(1000.0, f * 8.0)),
         attack=0.003, release=0.24, glide=0.03)
_profile("purr",
         osc=[("sine", 1.0, 0.4, 0.5)],
         noisebed=(1.0, 220.0, 26.0),
         attack=0.30, release=0.30, glide=0.05)
_profile("hoot",
         osc=[("sine", 1.0, 1.0, 0.5), ("sine", 2.0, 0.2, 0.5)],
         filt=_lp(lambda f: f * 3.0 + 300.0),
         attack=0.25, release=0.30, glide=0.06)
_profile("croak",
         osc=[("square", 1.0, 1.0, 0.30), ("saw", 1.0, 0.5, 0.5)],
         filt=_lp(lambda f: f * 3.0 + 400.0),
         noisebed=(0.0, 220.0, 18.0), trem=(18.0, 0.35),
         attack=0.01, release=0.25, glide=0.05)


def _profile_from_timbre(spec):
    """Build a sustain profile from a ComponentDNA patch, clamped like
    :func:`synth.procedural_voice` so malformed data stays safe."""
    spec = spec or {}
    osc = []
    for item in (spec.get("oscillators") or [("sine", 1.0)])[:4]:
        try:
            kind, gain = item[0], float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        osc.append((str(kind), 1.0, max(0.0, min(gain, 1.5)), 0.5))
    if not osc:
        osc = [("sine", 1.0, 1.0, 0.5)]
    detunes = [0.0]
    for cents in (spec.get("detune_cents") or [])[:4]:
        try:
            detunes.append(max(-30.0, min(30.0, float(cents))))
        except (TypeError, ValueError):
            continue
    partials = []
    for item in (spec.get("partials") or [])[:5]:
        try:
            ratio, gain = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        partials.append((max(0.25, min(ratio, 12.0)), max(0.0, min(gain, 0.8))))
    fm = None
    try:
        fm_index = max(0.0, min(float(spec.get("fm_index", 0.0)), 4.0))
        if fm_index:
            fm = (max(0.25, min(float(spec.get("fm_ratio", 2.0)), 8.0)), fm_index)
    except (TypeError, ValueError):
        pass

    def _num(key, default, lo, hi):
        try:
            return max(lo, min(float(spec.get(key, default)), hi))
        except (TypeError, ValueError):
            return default

    cutoff = _num("cutoff", 6000.0, 80.0, SR * 0.44)
    highpass = _num("highpass", 20.0, 0.0, cutoff * 0.8)
    if highpass > 25.0:
        filt = _bp(lambda f, h=highpass: h, lambda f, c=cutoff: c)
    else:
        filt = _lp(lambda f, c=cutoff: c)
    vib_cents = _num("vibrato_cents", 0.0, 0.0, 35.0)
    vib = (_num("vibrato_rate", 5.0, 0.0, 16.0), vib_cents) if vib_cents else None
    trem_depth = _num("tremolo_depth", 0.0, 0.0, 0.9)
    trem = (_num("tremolo_rate", 4.0, 0.05, 24.0), trem_depth) if trem_depth else None
    return dict(osc=osc, detune=tuple(detunes), partials=tuple(partials),
                fm=fm, filt=filt, breath=(_num("noise", 0.0, 0.0, 0.4), 0.0) or None,
                noisebed=None, vib=vib, trem=trem, move=0.0,
                attack=_num("attack", 0.01, 0.001, 0.5),
                release=max(0.05, min(_num("release", 0.25, 0.005, 2.0), 1.2)),
                glide=0.04, post=None,
                drive=_num("drive", 1.0, 1.0, 5.0))


def _profile_for(comp):
    spec = comp.get("timbre")
    if spec and _timbre_is_sustain(spec):
        return _profile_from_timbre(spec)
    return _P.get(comp.get("voice", "music_box"))


# ---------------------------------------------------------------------------
# Small DSP helpers
# ---------------------------------------------------------------------------
def _cos_ramp(n, up=True):
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    x = np.linspace(0.0, np.pi, n, dtype=np.float32)
    r = 0.5 - 0.5 * np.cos(x)
    return r if up else r[::-1].copy()


def _eq_fade(n, up=True):
    """Equal-power (sqrt) fade window."""
    return np.sqrt(_cos_ramp(n, up)).astype(np.float32)


def _rms_normalize(buf, target=0.16):
    r = float(np.sqrt(np.mean(np.square(buf)))) if buf.size else 0.0
    if r > 1e-6:
        buf = buf * (target / r)
    return buf.astype(np.float32)


def _crossfade_tile(buf, target_n, xfade_s=0.30):
    """Fill ``target_n`` samples by overlapping copies of ``buf`` with
    equal-power crossfades, hiding the seam that plain tiling would leave."""
    buf = np.asarray(buf, dtype=np.float32)
    if target_n <= 0:
        return np.zeros(0, dtype=np.float32)
    if len(buf) == 0:
        return np.zeros(target_n, dtype=np.float32)
    if len(buf) >= target_n:
        return buf[:target_n].copy()
    xf = max(32, min(int(xfade_s * SR), len(buf) // 3))
    out = np.zeros(target_n + len(buf), dtype=np.float32)
    fade_in = _eq_fade(xf, True)
    fade_out = _eq_fade(xf, False)
    pos = 0
    first = True
    while pos < target_n:
        piece = buf.copy()
        if not first:
            piece[:xf] *= fade_in
        if pos + len(piece) < target_n:      # another copy will follow
            piece[-xf:] *= fade_out
        out[pos:pos + len(piece)] += piece
        pos += len(piece) - xf
        first = False
    return out[:target_n]


def _sample_sustain(base, target_n):
    """Sampler-style sustain for imported audio: play the natural start once,
    loop a mid ``body`` region with generous equal-power crossfades while more
    time is needed, then finish on the sample's own tail."""
    base = np.asarray(base, dtype=np.float32)
    if len(base) == 0:
        return np.zeros(max(0, target_n), dtype=np.float32)
    if target_n <= len(base):
        out = base[:target_n].copy()
        fade = min(len(out), int(0.12 * SR))
        if fade > 8 and target_n < len(base):     # cut mid-sound -> soften
            out[-fade:] *= _cos_ramp(fade, up=False)
        return out
    b0 = int(len(base) * 0.35)
    nominal = min(len(base), max(b0 + int(0.08 * SR), int(len(base) * 0.92)))
    if nominal - b0 < int(0.05 * SR):
        return _crossfade_tile(base, target_n, xfade_s=0.15)
    xf = max(32, min(int(0.08 * SR), (nominal - b0) // 3))
    # phase-align the loop joint: pick the wrap point whose waveform matches
    # the loop start, so crossfading identical material cannot cancel itself
    ref = base[b0:b0 + xf].astype(np.float64)
    lo = max(b0 + int(0.05 * SR), nominal - int(0.03 * SR))
    hi = min(len(base), nominal + int(0.03 * SR))
    b1 = nominal
    if hi - xf > lo:
        window = base[lo - xf:hi].astype(np.float64)
        scores = np.correlate(window, ref, mode="valid")
        b1 = lo - xf + int(np.argmax(scores)) + xf
        b1 = max(b0 + int(0.05 * SR), min(b1, len(base)))
    body = base[b0:b1]
    fade_in = np.linspace(0.0, 1.0, xf, dtype=np.float32)   # equal-gain:
    fade_out = fade_in[::-1].copy()                          # aligned material
    total = b1 + max(0, len(base) - b0 - xf)
    loops = 0
    while total < target_n:
        loops += 1
        total = b1 + loops * (len(body) - xf) + (len(base) - b0 - xf)
    out = np.zeros(max(total, target_n), dtype=np.float32)
    head = base[:b1].copy()                 # natural attack, once
    head[-xf:] *= fade_out
    synth._place(out, head, 0)
    pos = b1 - xf
    for _ in range(loops):
        piece = body.copy()
        piece[:xf] *= fade_in
        piece[-xf:] *= fade_out
        synth._place(out, piece, pos)
        pos += len(body) - xf
    last = base[b0:].copy()                 # body + natural tail, contiguous
    last[:xf] *= fade_in
    synth._place(out, last, pos)
    out = out[:target_n]
    cut = min(len(out), int(0.012 * SR))
    if cut > 8 and float(np.abs(out[-cut:]).max()) > 0.02:
        out[-cut:] *= _cos_ramp(cut, up=False)  # soften only a loud trim
    return out


# ---------------------------------------------------------------------------
# The sustained (truly continuous) renderer
# ---------------------------------------------------------------------------
def _freq_curve(freq_points, seg_ns, glide_s, tail_n):
    """Piecewise frequency track with cosine portamento at boundaries."""
    total = int(sum(seg_ns)) + int(tail_n)
    f = np.empty(max(1, total), dtype=np.float32)
    pos = 0
    for i, (fv, n) in enumerate(zip(freq_points, seg_ns)):
        n = int(n)
        f[pos:pos + n] = fv
        pos += n
    if tail_n:
        f[pos:pos + int(tail_n)] = freq_points[-1]
    # smooth glides across each internal boundary
    g = int(glide_s * SR)
    if g > 4:
        edge = 0
        for i in range(len(seg_ns) - 1):
            edge += int(seg_ns[i])
            a, b = freq_points[i], freq_points[i + 1]
            if a == b:
                continue
            half = min(g // 2, int(seg_ns[i]) // 2, int(seg_ns[i + 1]) // 2)
            if half < 3:
                continue
            ramp = _cos_ramp(half * 2, up=True)
            f[edge - half:edge + half] = a + (b - a) * ramp
    return f


def _render_sustain_line(profile, f_hz, top_freq):
    """One continuous voice line following the frequency curve ``f_hz``."""
    n = len(f_hz)
    t = np.arange(n, dtype=np.float32) / SR
    vib = profile.get("vib")
    if vib and vib[1] > 0.0:
        rate, cents = vib
        onset = np.clip(t / 0.4, 0.0, 1.0)
        f_hz = f_hz * np.power(2.0, (cents * onset *
                                     np.sin(2.0 * np.pi * rate * t)) / 1200.0)
    base_phase = np.cumsum(2.0 * np.pi * f_hz / SR).astype(np.float32)

    out = np.zeros(n, dtype=np.float32)
    total_gain = 0.0
    fm = profile.get("fm")
    for cents in profile["detune"]:
        ratio = 2.0 ** (cents / 1200.0)
        phase = base_phase * ratio
        if fm:
            phase = phase + fm[1] * np.sin(phase * fm[0])
        for kind, mult, gain, duty in profile["osc"]:
            if gain <= 0.0:
                continue
            p = phase * mult
            if kind == "square" and abs(duty - 0.5) > 1e-3:
                cyc = (p / (2.0 * np.pi)) % 1.0
                wave = np.where(cyc < duty, 1.0, -1.0).astype(np.float32)
            else:
                wave = synth._osc_from_phase(kind, p)
            out += wave * gain
            total_gain += gain
    for ratio, gain in profile["partials"]:
        out += np.sin(base_phase * ratio).astype(np.float32) * gain
        total_gain += gain
    if total_gain > 1e-6:
        out /= total_gain

    noisebed = profile.get("noisebed")
    if noisebed:
        gain, cutoff, am_rate = noisebed
        if gain > 0.0:
            bed = np.random.uniform(-1.0, 1.0, n).astype(np.float32)
            bed = synth._lowpass(bed, cutoff)
            am = 0.5 + 0.5 * (np.sin(2.0 * np.pi * am_rate * t) > 0)
            out = out + bed * am.astype(np.float32) * gain
    breath = profile.get("breath")
    if breath and breath[0] > 0.0:
        air = np.random.uniform(-1.0, 1.0, n).astype(np.float32)
        if breath[1] > 25.0:
            air = synth._highpass(air, breath[1])
        out += air * breath[0]

    filt = profile.get("filt")
    if filt:
        if filt[0] == "lp":
            out = synth._lowpass(out, filt[1](top_freq))
        else:
            out = synth._bandpass(out, filt[1](top_freq), filt[2](top_freq))
    move = profile.get("move", 0.0)
    if move:
        out *= (1.0 - 0.6 * move) + 0.6 * move * np.sin(2.0 * np.pi * 0.23 * t)
    trem = profile.get("trem")
    if trem:
        rate, depth = trem
        out *= (1.0 - depth + depth * (0.5 + 0.5 * np.sin(2.0 * np.pi * rate * t)))
    drive = profile.get("drive", 1.0)
    if drive > 1.001:
        out = np.tanh(out * drive).astype(np.float32) / np.tanh(drive)
    return _rms_normalize(out.astype(np.float32), 0.16)


def _sub_run_key(comp):
    return (comp.get("voice", "music_box"), repr(comp.get("timbre")),
            repr(comp.get("layers")))


def _sustain_freq_lists(segs):
    """Voice-leading lanes: chords glide tone-to-tone between segments."""
    counts = [len(s["freqs"]) for s in segs]
    lanes = max(counts)
    lists = []
    for s in segs:
        fr = sorted(s["freqs"])
        while len(fr) < lanes:
            fr.append(fr[-1])
        lists.append(fr)
    return lanes, lists


def _render_sustain_subrun(segs, first_of_phrase, last_of_phrase,
                           attack_n, morph_out_n):
    """Continuously synthesize one timbre stretch of a sustain run.

    Returns (buffer, release_tail_n).  The buffer covers the sub-run span
    plus its tail (final release or morph hand-over)."""
    comp = segs[0]["comp"]
    profile = dict(_profile_for(comp) or _P["soft_lead"])
    seg_ns = [s["n"] for s in segs]
    release_n = int(profile["release"] * SR) if last_of_phrase else morph_out_n
    lanes, freq_lists = _sustain_freq_lists(segs)
    top = max(max(fl) for fl in freq_lists)
    body = np.zeros(int(sum(seg_ns)) + release_n, dtype=np.float32)
    for lane in range(lanes):
        pts = [fl[lane] for fl in freq_lists]
        f_hz = _freq_curve(pts, seg_ns, profile["glide"], release_n)
        body[:len(f_hz)] += _render_sustain_line(profile, f_hz, top)
    if lanes > 1:
        body /= np.sqrt(float(lanes))

    # optional sustaining layers keep a component's stacked character
    weight = 1.0
    for layer in (comp.get("layers") or [])[:3]:
        if not isinstance(layer, dict):
            continue
        lspec = layer.get("timbre")
        lvoice = layer.get("voice", comp.get("voice", "music_box"))
        if lspec:
            if not _timbre_is_sustain(lspec):
                continue
            lprof = _profile_from_timbre(lspec)
        elif lvoice in _SUSTAIN_VOICES:
            lprof = dict(_P[lvoice])
        else:
            continue
        octave = max(-2, min(2, int(layer.get("octave", 0))))
        cents = max(-30.0, min(30.0, float(layer.get("detune_cents", 0.0))))
        mul = (2.0 ** octave) * (2.0 ** (cents / 1200.0))
        gain = max(0.0, min(float(layer.get("gain", 0.2)), 0.8))
        for lane in range(lanes):
            pts = [fl[lane] * mul for fl in freq_lists]
            f_hz = _freq_curve(pts, seg_ns, lprof["glide"], release_n)
            body[:len(f_hz)] += _render_sustain_line(lprof, f_hz, top * mul) * gain
        weight += gain
    body /= max(1.0, weight * 0.82)

    # loudness parity: a connected note should sit at the same level as the
    # discrete tile it came from, so match a short reference render's RMS
    ref = synth._component_tone(comp, freq=freq_lists[0][0], dur=1.0)
    mid = ref[int(0.35 * SR):int(0.78 * SR)]
    target = float(np.sqrt(np.mean(np.square(mid)))) if mid.size else 0.16
    target = max(0.03, min(target, 0.35))
    sus_lo = min(len(body) - 1, max(0, attack_n))
    sus_hi = max(sus_lo + 1, len(body) - max(1, release_n))
    cur = float(np.sqrt(np.mean(np.square(body[sus_lo:sus_hi]))))
    if cur > 1e-6:
        body *= target / cur

    # ONE envelope: attack (or morph hand-in), flat sustain, one tail
    env = np.ones(len(body), dtype=np.float32)
    a = min(attack_n, len(body))
    if a > 2:
        env[:a] = _cos_ramp(a, up=True)
    if release_n > 2:
        if last_of_phrase:
            env[-release_n:] = _cos_ramp(release_n, up=False)
        else:                                   # equal-power morph hand-over
            env[-release_n:] = _eq_fade(release_n, up=False)
    body *= env
    post = profile.get("post")
    if post == "dream_verb":
        body = synth._reverb(body, amount=0.22, decay=0.60)
    for fx in comp.get("effects", []) or []:
        body = synth.apply_effect(body, fx[0], fx[1] if len(fx) > 1 else None)
    return body.astype(np.float32), release_n


def _render_sustain_run(segs, sps, first_of_phrase, last_of_phrase):
    """A run of sustain-family segments: split into timbre sub-runs, morph
    between them at sustain level, keep one attack and one release."""
    # merge into timbre sub-runs
    subruns = []
    for seg in segs:
        key = _sub_run_key(seg["comp"])
        if subruns and subruns[-1][0] == key:
            subruns[-1][1].append(seg)
        else:
            subruns.append((key, [seg]))
    total_n = int(sum(s["n"] for s in segs))
    out = np.zeros(total_n + int(4.0 * SR), dtype=np.float32)
    pos = 0
    end = 0
    pending_in = 0
    for i, (_, group) in enumerate(subruns):
        last = last_of_phrase and (i == len(subruns) - 1)
        if i < len(subruns) - 1:
            nxt = subruns[i + 1][1][0]
            morph = int(min(0.22 * SR, 0.45 * group[-1]["n"], 0.45 * nxt["n"]))
        else:
            morph = int(min(0.22 * SR, 0.45 * group[-1]["n"]))
        first = first_of_phrase and (i == 0)
        prof = _profile_for(group[0]["comp"]) or _P["soft_lead"]
        attack_n = int(prof["attack"] * SR) if first else 0
        buf, _ = _render_sustain_subrun(group, first, last, attack_n, morph)
        if pending_in > 2:                      # complete the equal-power pair
            n = min(pending_in, len(buf))
            buf[:n] *= _eq_fade(n, up=True)
        synth._place(out, buf, pos, 1.0)
        end = max(end, pos + len(buf))
        pos += int(sum(s["n"] for s in group))
        pending_in = morph if not last else 0
    return out[:end]


# ---------------------------------------------------------------------------
# Ring / hit / pattern / bed / sample runs
# ---------------------------------------------------------------------------
_MAX_RING_SECONDS = 11.5           # matches procedural_voice's 12 s clamp


def _ring_tone(comp, seconds):
    """A single naturally-decaying strike rendered at ``seconds`` long: the
    voice models scale decay with duration, giving a genuine long resonance."""
    seconds = max(0.06, min(seconds, _MAX_RING_SECONDS))
    if comp.get("type") == "chord":
        if comp.get("notes"):
            freqs = [synth.note_freq(x) for x in comp["notes"]]
        else:
            freqs = synth.chord_freqs(comp.get("root", "C"),
                                      comp.get("quality", "major"),
                                      comp.get("octave", 4))
        strum = max(0.0, min(float(comp.get("strum_ms", 12.0)), 80.0)) / 1000.0
        direction = comp.get("strum_direction", "up")
        buf = np.zeros(int((seconds + strum * max(0, len(freqs) - 1)) * SR),
                       dtype=np.float32)
        ordered = list(freqs) if direction != "down" else list(reversed(freqs))
        for i, f in enumerate(ordered):
            snd = synth._component_tone(comp, f, seconds)
            synth._place(buf, snd, int(i * strum * SR),
                         0.78 / max(1.0, len(freqs) ** 0.25))
        buf = synth._normalize(buf, 0.85)
    else:
        notes = comp.get("notes") or ["C4"]
        buf = synth._component_tone(comp, synth.note_freq(notes[0]), seconds)
    for fx in comp.get("effects", []) or []:
        buf = synth.apply_effect(buf, fx[0], fx[1] if len(fx) > 1 else None)
    return buf.astype(np.float32)


def _ring_identity(comp):
    return (comp.get("id"), repr(comp.get("notes")), comp.get("root"),
            comp.get("quality"), comp.get("octave"))


def _render_ring_run(segs, sps):
    """Decaying instruments: identical consecutive tiles merge into one long
    strike; changing notes ring into each other with no silence."""
    merged = []
    for seg in segs:
        ident = tuple(sorted(_ring_identity(c) for c in seg["comps"]))
        if merged and merged[-1]["ident"] == ident:
            merged[-1]["n"] += seg["n"]
        else:
            merged.append(dict(ident=ident, comps=seg["comps"],
                               n=seg["n"], start=seg["start"]))
    total_n = int(sum(s["n"] for s in segs))
    out = np.zeros(total_n + int((_MAX_RING_SECONDS + 1.0) * SR), dtype=np.float32)
    end = 0
    pos = 0
    for i, m in enumerate(merged):
        seg_seconds = m["n"] / float(SR)
        ring_over = 1.2 if i == len(merged) - 1 else min(
            2.5, sum(x["n"] for x in merged[i + 1:]) / float(SR) + 0.8)
        for comp in m["comps"]:
            buf = _ring_tone(comp, seg_seconds + ring_over)
            if i > 0:                    # soften the joins, keep the pluck
                soft = min(len(buf), int(0.008 * SR))
                buf[:soft] *= _cos_ramp(soft, up=True)
            synth._place(out, buf, pos, 1.0 / max(1.0, len(m["comps"]) ** 0.5))
            end = max(end, pos + len(buf))
        pos += m["n"]
    return out[:end]


def _render_events_run(segs, bpm):
    """Drums, rhythms and loops: one shared timeline so every event's tail
    rings across old tile boundaries.  Nothing is stretched into a drone."""
    total_n = int(sum(s["n"] for s in segs))
    out = np.zeros(total_n + int(2.0 * SR), dtype=np.float32)
    end = 0
    pos = 0
    for seg in segs:
        for comp in seg["comps"]:
            buf = synth.render_component(comp, bpm=bpm)
            synth._place(out, buf, pos, 1.0)
            end = max(end, pos + len(buf))
        pos += seg["n"]
    return out[:end]


def _render_bed_run(segs, bpm):
    """Ambiences: fill each stretch with seam-hidden crossfade tiling and
    morph between different beds with long equal-power crossfades."""
    merged = []
    for seg in segs:
        ids = tuple(sorted(c.get("id") for c in seg["comps"]))
        if merged and merged[-1]["ids"] == ids:
            merged[-1]["n"] += seg["n"]
        else:
            merged.append(dict(ids=ids, comps=seg["comps"], n=seg["n"]))
    total_n = int(sum(s["n"] for s in segs))
    out = np.zeros(total_n + int(1.5 * SR), dtype=np.float32)
    pos = 0
    end = 0
    prev_xf = 0
    for i, m in enumerate(merged):
        xf_next = 0
        if i < len(merged) - 1:
            xf_next = int(min(0.6 * SR, 0.45 * m["n"], 0.45 * merged[i + 1]["n"]))
        for comp in m["comps"]:
            base = synth.render_component(comp, bpm=bpm)
            filled = _crossfade_tile(base, m["n"] + xf_next, xfade_s=0.35)
            if prev_xf > 2:
                k = min(prev_xf, len(filled))
                filled[:k] *= _eq_fade(k, up=True)
            if xf_next > 2:
                filled[-xf_next:] *= _eq_fade(xf_next, up=False)
            synth._place(out, filled, pos, 1.0 / max(1.0, len(m["comps"]) ** 0.5))
            end = max(end, pos + len(filled))
        pos += m["n"]
        prev_xf = xf_next
    seg_buf = out[:max(end, total_n)]
    return synth._edge_fade(seg_buf, ms=40.0)


def _render_sample_run(segs, samples):
    merged = []
    for seg in segs:
        ids = tuple(sorted(c.get("id") for c in seg["comps"]))
        if merged and merged[-1]["ids"] == ids:
            merged[-1]["n"] += seg["n"]
        else:
            merged.append(dict(ids=ids, comps=seg["comps"], n=seg["n"]))
    total_n = int(sum(s["n"] for s in segs))
    out = np.zeros(total_n + int(1.0 * SR), dtype=np.float32)
    pos = 0
    end = 0
    prev_xf = 0
    for i, m in enumerate(merged):
        xf_next = 0
        if i < len(merged) - 1:
            xf_next = int(min(0.25 * SR, 0.4 * m["n"], 0.4 * merged[i + 1]["n"]))
        for comp in m["comps"]:
            base = (samples or {}).get(comp.get("id"))
            if base is None:
                base = comp.get("_buffer")
            if base is None or len(base) == 0:
                continue                     # missing import -> quiet, never a crash
            filled = _sample_sustain(np.asarray(base, dtype=np.float32),
                                     m["n"] + xf_next)
            if prev_xf > 2:
                k = min(prev_xf, len(filled))
                filled[:k] *= _eq_fade(k, up=True)
            if xf_next > 2 and len(filled) >= xf_next:
                filled[-xf_next:] *= _eq_fade(xf_next, up=False)
            synth._place(out, filled, pos, 1.0 / max(1.0, len(m["comps"]) ** 0.5))
            end = max(end, pos + len(filled))
        pos += m["n"]
        prev_xf = xf_next
    return out[:max(end, min(total_n, len(out)))]


# ---------------------------------------------------------------------------
# Phrase assembly
# ---------------------------------------------------------------------------
def phrase_span_steps(members):
    """(first_step, span_steps) for drawing and placement.  ``members`` is a
    list of (comp, step); the final note keeps its natural clip length."""
    steps = sorted({int(s) for _, s in members})
    first = steps[0]
    last_len = max(max(1, int(synth.clip_length_steps(c)))
                   for c, s in members if int(s) == steps[-1])
    return first, (steps[-1] - first) + last_len


def _build_lane_segments(members, sps):
    """Group members by family lane; inside a lane each sound holds until the
    lane's next sound begins (so tile spacing sets note length)."""
    by_step = {}
    for comp, step in members:
        by_step.setdefault(int(step), []).append(comp)
    steps = sorted(by_step)
    span_first = steps[0]
    lanes = {}
    for step in steps:
        for comp in by_step[step]:
            lanes.setdefault(classify(comp), []).append((step, comp))
    lane_segs = {}
    for fam, items in lanes.items():
        items.sort(key=lambda x: x[0])
        grouped = []
        for step, comp in items:
            if grouped and grouped[-1]["step"] == step:
                grouped[-1]["comps"].append(comp)
            else:
                grouped.append(dict(step=step, comps=[comp]))
        segs = []
        for i, g in enumerate(grouped):
            if i + 1 < len(grouped):
                length = grouped[i + 1]["step"] - g["step"]
            else:
                length = max(max(1, int(synth.clip_length_steps(c)))
                             for c in g["comps"])
            n = max(1, int(round(length * sps * SR)))
            segs.append(dict(start=int(round((g["step"] - span_first) * sps * SR)),
                             n=n, comps=g["comps"], comp=g["comps"][0],
                             freqs=_seg_freqs(g["comps"])))
        lane_segs[fam] = segs
    return lane_segs


def _seg_freqs(comps):
    freqs = []
    for comp in comps:
        if comp.get("type") == "chord":
            if comp.get("notes"):
                freqs.extend(synth.note_freq(x) for x in comp["notes"])
            else:
                freqs.extend(synth.chord_freqs(comp.get("root", "C"),
                                               comp.get("quality", "major"),
                                               comp.get("octave", 4)))
        else:
            notes = comp.get("notes") or ["C4"]
            freqs.append(synth.note_freq(notes[0]))
    return freqs or [synth.note_freq("C4")]


def _phrase_seed(members, bpm):
    h = hashlib.blake2s(digest_size=4)
    h.update(("%.4f" % bpm).encode())
    for comp, step in members:
        h.update(str(comp.get("id")).encode())
        h.update(str(int(step)).encode())
    return int.from_bytes(h.digest(), "big")


def _render_phrase_inner(members, bpm, samples):
    sps = synth.sec_per_step(bpm)
    lane_segs = _build_lane_segments(members, sps)
    _, span_steps = phrase_span_steps(members)
    span_n = int(round(span_steps * sps * SR))
    out = np.zeros(span_n + int((_MAX_RING_SECONDS + 1.5) * SR), dtype=np.float32)
    end = span_n
    for fam, segs in lane_segs.items():
        if fam == FAMILY_SUSTAIN:
            buf = _render_sustain_run(segs, sps, True, True)
        elif fam == FAMILY_RING:
            buf = _render_ring_run(segs, sps)
        elif fam in (FAMILY_HIT, FAMILY_PATTERN):
            buf = _render_events_run(segs, bpm)
        elif fam == FAMILY_BED:
            buf = _render_bed_run(segs, bpm)
        else:
            buf = _render_sample_run(segs, samples)
        start = segs[0]["start"]
        synth._place(out, buf, start, 1.0)
        end = max(end, start + len(buf))
    out = out[:end]
    if not np.all(np.isfinite(out)):
        out = np.nan_to_num(out, nan=0.0, posinf=1.0, neginf=-1.0)
    peak = float(np.max(np.abs(out))) if out.size else 0.0
    if peak > 0.92:                       # only prevent clipping, keep dynamics
        out *= 0.92 / peak
    return synth._edge_fade(out.astype(np.float32), ms=4.0)


# ---------------------------------------------------------------------------
# Public API + bounded cache
# ---------------------------------------------------------------------------
_CACHE = OrderedDict()
_CACHE_BYTES = 0
_CACHE_LIMIT_BYTES = 32 * 1024 * 1024
_CACHE_ENTRY_LIMIT_BYTES = 8 * 1024 * 1024
_CACHE_LOCK = threading.Lock()


def cache_key(members, bpm, samples=None):
    """Stable identity of a phrase render.  ``members`` is (comp, step)."""
    steps = [int(s) for _, s in members]
    base = min(steps)
    key = [round(float(bpm), 6)]
    for comp, step in sorted(members, key=lambda m: (int(m[1]), str(m[0].get("id")))):
        cid = comp.get("id")
        key.append((cid, int(step) - base))
        if comp.get("type") == "user":
            buf = (samples or {}).get(cid)
            key.append(id(buf) if buf is not None else None)
    return tuple(key)


def clear_cache():
    global _CACHE_BYTES
    with _CACHE_LOCK:
        _CACHE.clear()
        _CACHE_BYTES = 0


def render_phrase(members, bpm=100.0, samples=None):
    """Render one connected phrase to a mono float32 buffer.

    The buffer starts at the phrase's first step; callers place it at
    ``first_step * sec_per_step(bpm) * SR``.  Results are deterministic and
    cached under a small byte budget, so replaying or exporting an unchanged
    phrase costs nothing and editing one phrase never re-renders the rest.
    """
    members = [(c, int(s)) for c, s in members if c is not None]
    if not members:
        return np.zeros(1, dtype=np.float32)
    key = cache_key(members, bpm, samples)
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit is not None:
            _CACHE.move_to_end(key)
    if hit is not None:
        return hit
    with synth._RENDER_LOCK:
        state = np.random.get_state()
        np.random.seed(_phrase_seed(members, bpm))
        try:
            buf = _render_phrase_inner(members, bpm, samples)
        finally:
            np.random.set_state(state)
    global _CACHE_BYTES
    if buf.nbytes <= _CACHE_ENTRY_LIMIT_BYTES:
        with _CACHE_LOCK:
            old = _CACHE.pop(key, None)
            if old is not None:
                _CACHE_BYTES -= old.nbytes
            _CACHE[key] = buf
            _CACHE_BYTES += buf.nbytes
            while _CACHE_BYTES > _CACHE_LIMIT_BYTES and _CACHE:
                _, dropped = _CACHE.popitem(last=False)
                _CACHE_BYTES -= dropped.nbytes
    return buf
