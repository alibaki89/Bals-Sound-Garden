"""Programmatic sound synthesis.

Everything the game can hear is generated here from numpy: melodic voices
(music box, bell, toy piano, warm pad, plucks, ...), drum hits, looped
phrases, rhythm patterns, ambient beds and post effects (reverb, delay,
filters, tremolo, bitcrush, reverse, fades).

The public entry point is :func:`render_component`, which turns one component
definition (a plain dict from :mod:`cat_society.components.catalog`) into a
mono ``float32`` buffer.  The music maker and the WAV exporter both build their
output by mixing these buffers onto a timeline.

Design goals: pleasant, soft, cozy.  Nothing is meant to be a studio sample,
but nothing is a silent placeholder either.
"""

import math
import threading

import numpy as np

SR = 44100
_RENDER_LOCK = threading.RLock()


# ---------------------------------------------------------------------------
# Note / pitch helpers
# ---------------------------------------------------------------------------
_SEMI = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5,
         "F#": 6, "GB": 6, "G": 7, "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10,
         "B": 11}


def note_to_midi(name):
    """``"C4"`` / ``"F#5"`` / ``"Bb3"`` -> MIDI note number."""
    name = name.strip()
    i = 1
    if len(name) > 1 and name[1] in "#b":
        i = 2
    letter = name[:i].upper()
    octave = int(name[i:])
    return _SEMI[letter] + (octave + 1) * 12


def note_freq(name):
    return 440.0 * 2.0 ** ((note_to_midi(name) - 69) / 12.0)


_CHORD_INTERVALS = {
    "major": [0, 4, 7], "maj": [0, 4, 7],
    "minor": [0, 3, 7], "min": [0, 3, 7], "m": [0, 3, 7],
    "maj7": [0, 4, 7, 11], "min7": [0, 3, 7, 10], "m7": [0, 3, 7, 10],
    "dom7": [0, 4, 7, 10], "7": [0, 4, 7, 10],
    "sus2": [0, 2, 7], "sus4": [0, 5, 7], "add9": [0, 4, 7, 14],
}


def chord_freqs(root, quality="major", octave=4):
    """Return the frequencies of a named chord, e.g. ``("C", "major", 4)``."""
    base = note_to_midi(f"{root}{octave}")
    semis = _CHORD_INTERVALS.get(quality.lower(), [0, 4, 7])
    return [440.0 * 2.0 ** ((base + s - 69) / 12.0) for s in semis]


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def _t(dur):
    return np.arange(max(1, int(dur * SR)), dtype=np.float32) / SR


def _sine(freq, dur, phase=0.0):
    return np.sin(2.0 * np.pi * freq * _t(dur) + phase).astype(np.float32)


def _tri(freq, dur):
    x = (_t(dur) * freq) % 1.0
    return (2.0 * np.abs(2.0 * x - 1.0) - 1.0).astype(np.float32)


def _saw(freq, dur):
    x = (_t(dur) * freq) % 1.0
    return (2.0 * x - 1.0).astype(np.float32)


def _square(freq, dur, duty=0.5):
    x = (_t(dur) * freq) % 1.0
    return np.where(x < duty, 1.0, -1.0).astype(np.float32)


def _noise(dur, rng=None):
    n = max(1, int(dur * SR))
    rng = rng or np.random
    return (rng.uniform(-1.0, 1.0, n)).astype(np.float32)


def adsr(n, a=0.01, d=0.1, s=0.7, r=0.2):
    """Amplitude envelope of length ``n`` samples."""
    a_n = max(1, int(a * SR))
    d_n = max(1, int(d * SR))
    r_n = max(1, int(r * SR))
    sus_n = max(0, n - a_n - d_n - r_n)
    env = np.zeros(n, dtype=np.float32)
    p = 0
    a_n = min(a_n, n)
    env[:a_n] = np.linspace(0.0, 1.0, a_n, dtype=np.float32)
    p = a_n
    if p < n:
        dd = min(d_n, n - p)
        env[p:p + dd] = np.linspace(1.0, s, dd, dtype=np.float32)
        p += dd
    if p < n and sus_n > 0:
        ss = min(sus_n, n - p)
        env[p:p + ss] = s
        p += ss
    if p < n:
        rr = n - p
        env[p:] = np.linspace(env[p - 1] if p > 0 else s, 0.0, rr, dtype=np.float32)
    return env


def _butterworth2(buf, cutoff, highpass=False):
    """Apply the same digital second-order Butterworth biquad used here before.

    The coefficient form is algebraically equivalent to
    ``scipy.signal.butter(2, cutoff / Nyquist)`` followed by ``lfilter``. Keeping
    the tiny implementation local avoids shipping the rest of SciPy solely for
    three DSP helpers and makes frozen builds deterministic on every platform.
    """
    data = np.asarray(buf, dtype=np.float32)
    if data.size == 0:
        return data.copy()

    k = math.tan(math.pi * float(cutoff) / SR)
    norm = 1.0 / (1.0 + math.sqrt(2.0) * k + k * k)
    if highpass:
        b0 = norm
        b1 = -2.0 * norm
        b2 = norm
    else:
        b0 = k * k * norm
        b1 = 2.0 * b0
        b2 = b0
    a1 = 2.0 * (k * k - 1.0) * norm
    a2 = (1.0 - math.sqrt(2.0) * k + k * k) * norm

    out = np.empty_like(data)
    x1 = x2 = y1 = y2 = 0.0
    for index, sample in enumerate(data):
        x0 = float(sample)
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out[index] = y0
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def _lowpass(buf, cutoff):
    cutoff = max(40.0, min(cutoff, SR * 0.45))
    return _butterworth2(buf, cutoff, highpass=False)


def _highpass(buf, cutoff):
    cutoff = max(20.0, min(cutoff, SR * 0.45))
    return _butterworth2(buf, cutoff, highpass=True)


def _bandpass(buf, lo, hi):
    return _highpass(_lowpass(buf, hi), lo)


def _normalize(buf, peak=0.9):
    m = float(np.max(np.abs(buf))) if buf.size else 0.0
    if m > 1e-6:
        buf = buf * (peak / m)
    return buf.astype(np.float32)


def _edge_fade(buf, ms=6.0):
    """Tiny fade in/out to kill clicks."""
    n = int(SR * ms / 1000.0)
    if n * 2 < len(buf):
        buf[:n] *= np.linspace(0.0, 1.0, n, dtype=np.float32)
        buf[-n:] *= np.linspace(1.0, 0.0, n, dtype=np.float32)
    return buf


# ---------------------------------------------------------------------------
# Melodic voices  (freq, dur) -> mono float
# ---------------------------------------------------------------------------
def voice(name, freq, dur):
    name = name or "music_box"
    fn = _VOICES.get(name, _v_music_box)
    return _edge_fade(fn(freq, dur))


def _osc_from_phase(kind, phase):
    """Oscillator evaluated from an already-integrated phase array."""
    if kind == "triangle":
        cycle = (phase / (2.0 * np.pi)) % 1.0
        return (2.0 * np.abs(2.0 * cycle - 1.0) - 1.0).astype(np.float32)
    if kind == "saw":
        cycle = (phase / (2.0 * np.pi)) % 1.0
        return (2.0 * cycle - 1.0).astype(np.float32)
    if kind == "square":
        return np.where(np.sin(phase) >= 0.0, 1.0, -1.0).astype(np.float32)
    return np.sin(phase).astype(np.float32)


def procedural_voice(freq, dur, spec):
    """Render a bounded ComponentDNA synthesizer patch.

    The patch is intentionally data-only and conservative: all parameters are
    clamped here even if malformed save data reaches the renderer.  This keeps
    generated sounds musical, finite and inexpensive enough for live preview.
    """
    spec = spec or {}
    dur = max(0.04, min(float(dur), 12.0))
    t = _t(dur)
    vibrato_rate = max(0.0, min(float(spec.get("vibrato_rate", 5.0)), 16.0))
    vibrato_cents = max(0.0, min(float(spec.get("vibrato_cents", 0.0)), 35.0))
    bend = np.sin(2.0 * np.pi * vibrato_rate * t) * vibrato_cents
    inst_freq = float(freq) * np.power(2.0, bend / 1200.0)
    base_phase = np.cumsum(2.0 * np.pi * inst_freq / SR).astype(np.float32)

    oscillators = spec.get("oscillators") or [("sine", 1.0)]
    detunes = [0.0] + [float(x) for x in (spec.get("detune_cents") or [])[:4]]
    fm_ratio = max(0.25, min(float(spec.get("fm_ratio", 2.0)), 8.0))
    fm_index = max(0.0, min(float(spec.get("fm_index", 0.0)), 4.0))
    out = np.zeros(len(t), dtype=np.float32)
    total_gain = 0.0
    for cents in detunes:
        ratio = 2.0 ** (max(-30.0, min(30.0, cents)) / 1200.0)
        phase = base_phase * ratio
        if fm_index:
            phase = phase + fm_index * np.sin(phase * fm_ratio)
        for item in oscillators[:4]:
            try:
                kind, gain = item[0], float(item[1])
            except (TypeError, ValueError, IndexError):
                continue
            gain = max(0.0, min(gain, 1.5))
            out += _osc_from_phase(kind, phase) * gain
            total_gain += gain

    for item in (spec.get("partials") or [])[:5]:
        try:
            ratio, gain = float(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        ratio = max(0.25, min(ratio, 12.0))
        gain = max(0.0, min(gain, 0.8))
        out += np.sin(base_phase * ratio).astype(np.float32) * gain
        total_gain += gain

    if total_gain > 1e-6:
        out /= total_gain
    noise = max(0.0, min(float(spec.get("noise", 0.0)), 0.4))
    if noise:
        out += _noise(dur) * noise

    cutoff = max(80.0, min(float(spec.get("cutoff", 6000.0)), SR * 0.44))
    out = _lowpass(out, cutoff)
    highpass = max(0.0, min(float(spec.get("highpass", 20.0)), cutoff * 0.8))
    if highpass > 25.0:
        out = _highpass(out, highpass)

    attack = max(0.001, min(float(spec.get("attack", 0.01)), dur * 0.8))
    decay = max(0.005, min(float(spec.get("decay", 0.18)), dur * 0.8))
    release = max(0.005, min(float(spec.get("release", 0.25)), dur * 0.8))
    envelope_time = attack + decay + release
    if envelope_time > dur * 0.94:
        scale = dur * 0.94 / envelope_time
        attack *= scale
        decay *= scale
        release *= scale
    env = adsr(len(out), attack, decay,
               max(0.0, min(float(spec.get("sustain", 0.62)), 1.0)), release)
    out *= env
    trem_depth = max(0.0, min(float(spec.get("tremolo_depth", 0.0)), 0.9))
    if trem_depth:
        trem_rate = max(0.05, min(float(spec.get("tremolo_rate", 4.0)), 24.0))
        out *= (1.0 - trem_depth + trem_depth * (0.5 + 0.5 * np.sin(
            2.0 * np.pi * trem_rate * t))).astype(np.float32)
    drive = max(1.0, min(float(spec.get("drive", 1.0)), 5.0))
    if drive > 1.001:
        out = np.tanh(out * drive).astype(np.float32) / np.tanh(drive)
    return _edge_fade(_normalize(out, 0.88))


def _component_tone(comp, freq, dur):
    """Render the component's primary patch and optional instrument layers."""
    if comp.get("timbre"):
        primary = procedural_voice(freq, dur, comp.get("timbre"))
    else:
        primary = voice(comp.get("voice", "music_box"), freq, dur)
    out = primary.astype(np.float32).copy()
    weight = 1.0
    for layer in (comp.get("layers") or [])[:3]:
        if not isinstance(layer, dict):
            continue
        octave = max(-2, min(2, int(layer.get("octave", 0))))
        cents = max(-30.0, min(30.0, float(layer.get("detune_cents", 0.0))))
        layer_freq = freq * (2.0 ** octave) * (2.0 ** (cents / 1200.0))
        if layer.get("timbre"):
            snd = procedural_voice(layer_freq, dur, layer.get("timbre"))
        else:
            snd = voice(layer.get("voice", comp.get("voice", "music_box")), layer_freq, dur)
        gain = max(0.0, min(float(layer.get("gain", 0.2)), 0.8))
        n = min(len(out), len(snd))
        out[:n] += snd[:n] * gain
        weight += gain
    return _normalize(out / max(1.0, weight * 0.82), 0.88)


def _v_music_box(freq, dur):
    body = (_sine(freq, dur)
            + 0.45 * _sine(freq * 2.0, dur)
            + 0.22 * _sine(freq * 3.01, dur)
            + 0.10 * _sine(freq * 4.97, dur))
    env = adsr(len(body), a=0.002, d=dur * 0.7, s=0.0, r=dur * 0.28)
    return _normalize(body * env, 0.8)


def _v_bell(freq, dur):
    parts = [(1.0, 1.0), (2.76, 0.5), (5.40, 0.28), (8.93, 0.14)]
    out = np.zeros(int(dur * SR), dtype=np.float32)
    for mult, amp in parts:
        s = _sine(freq * mult, dur)
        e = adsr(len(s), a=0.001, d=dur * (0.55 + 0.1 * mult), s=0.0,
                 r=dur * 0.3)
        out += amp * s * e[:len(s)]
    return _normalize(out, 0.8)


def _v_glass(freq, dur):
    body = _sine(freq, dur) + 0.3 * _sine(freq * 4.02, dur) + 0.15 * _sine(freq * 6.5, dur)
    env = adsr(len(body), a=0.004, d=dur * 0.85, s=0.0, r=dur * 0.2)
    trem = 1.0 + 0.08 * np.sin(2.0 * np.pi * 6.0 * _t(dur))
    return _normalize(body * env * trem, 0.75)


def _v_celeste(freq, dur):
    body = _sine(freq * 2.0, dur) + 0.5 * _tri(freq * 2.0, dur) + 0.25 * _sine(freq * 4.0, dur)
    env = adsr(len(body), a=0.003, d=dur * 0.6, s=0.0, r=dur * 0.35)
    return _normalize(body * env, 0.72)


def _v_toy_piano(freq, dur):
    body = (0.7 * _tri(freq, dur) + 0.5 * _square(freq, dur, 0.45)
            + 0.3 * _sine(freq * 2.0, dur))
    body = _lowpass(body, freq * 6.0 + 1500.0)
    env = adsr(len(body), a=0.002, d=dur * 0.45, s=0.12, r=dur * 0.3)
    click = _noise(0.01) * np.linspace(1, 0, int(0.01 * SR))
    out = body * env
    out[:len(click)] += 0.25 * click
    return _normalize(out, 0.8)

def _v_warm_pad(freq, dur):
    detune = [0.0, -7.0, 7.0, -3.0]          # cents-ish, in Hz offsets below
    out = np.zeros(int(dur * SR), dtype=np.float32)
    for cents in detune:
        f = freq * (2.0 ** (cents / 1200.0))
        out += _saw(f, dur)
    out = _lowpass(out, freq * 3.0 + 700.0)
    env = adsr(len(out), a=dur * 0.25, d=dur * 0.2, s=0.75, r=dur * 0.3)
    return _normalize(out * env, 0.7)


def _v_pluck(freq, dur):
    body = _saw(freq, dur) + 0.4 * _square(freq, dur, 0.5)
    body = _lowpass(body, freq * 5.0 + 600.0)
    env = adsr(len(body), a=0.002, d=dur * 0.5, s=0.05, r=dur * 0.25)
    return _normalize(body * env, 0.78)


def _v_moon_pluck(freq, dur):
    body = _sine(freq, dur) + 0.4 * _tri(freq, dur)
    env = adsr(len(body), a=0.004, d=dur * 0.55, s=0.0, r=dur * 0.35)
    trem = 1.0 + 0.12 * np.sin(2.0 * np.pi * 5.5 * _t(dur))
    return _normalize(body * env * trem, 0.74)


def _v_warm_bass(freq, dur):
    body = _sine(freq, dur) + 0.5 * _saw(freq, dur) + 0.3 * _sine(freq * 0.5, dur)
    body = _lowpass(body, freq * 4.0 + 250.0)
    env = adsr(len(body), a=0.004, d=dur * 0.4, s=0.4, r=dur * 0.3)
    return _normalize(body * env, 0.85)


def _v_soft_lead(freq, dur):
    body = _sine(freq, dur) + 0.3 * _tri(freq, dur)
    body = _lowpass(body, freq * 6.0 + 1200.0)
    env = adsr(len(body), a=0.02, d=dur * 0.2, s=0.6, r=dur * 0.25)
    vib = 1.0 + 0.01 * np.sin(2.0 * np.pi * 5.0 * _t(dur))
    return _normalize(body * env * vib, 0.78)


# ---- animal-flavoured voices (musical, not silly) -------------------------
def _v_meow(freq, dur):
    t = _t(dur)
    gl = freq * (1.0 + 0.25 * np.sin(np.pi * t / max(dur, 1e-3)))   # gentle glide
    ph = np.cumsum(2.0 * np.pi * gl / SR)
    body = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    body = _bandpass(body.astype(np.float32), 300.0, freq * 5.0 + 1500.0)
    env = adsr(len(body), a=0.03, d=dur * 0.25, s=0.5, r=dur * 0.35)
    return _normalize(body * env, 0.7)


def _v_purr(freq, dur):
    base = _noise(dur)
    base = _lowpass(base, 220.0)
    am = 0.5 + 0.5 * (np.sin(2.0 * np.pi * 26.0 * _t(dur)) > 0)     # ~26 Hz buzz
    tone = 0.4 * _sine(max(freq, 60.0), dur)
    out = (base * am + tone)
    env = adsr(len(out), a=dur * 0.15, d=0.05, s=0.85, r=dur * 0.2)
    return _normalize(out * env, 0.6)


def _v_croak(freq, dur):
    body = _square(max(freq, 70.0), dur, 0.3) + 0.5 * _saw(max(freq, 70.0), dur)
    am = 0.4 + 0.6 * (np.sin(2.0 * np.pi * 18.0 * _t(dur)) > 0)
    body = _lowpass(body * am, freq * 3.0 + 400.0)
    env = adsr(len(body), a=0.005, d=dur * 0.4, s=0.2, r=dur * 0.3)
    return _normalize(body * env, 0.8)


def _v_quack(freq, dur):
    body = _saw(freq, dur)
    body = _bandpass(body, 600.0, 2200.0)
    env = adsr(len(body), a=0.004, d=dur * 0.5, s=0.1, r=dur * 0.2)
    return _normalize(body * env, 0.78)


def _v_hoot(freq, dur):
    body = _sine(freq, dur) + 0.2 * _sine(freq * 2.0, dur)
    body = _lowpass(body, freq * 3.0 + 300.0)
    env = adsr(len(body), a=dur * 0.2, d=dur * 0.2, s=0.6, r=dur * 0.3)
    return _normalize(body * env, 0.74)


def _v_chirp(freq, dur):
    t = _t(dur)
    gl = freq * (1.0 + 0.6 * t / max(dur, 1e-3))
    ph = np.cumsum(2.0 * np.pi * gl / SR)
    body = np.sin(ph).astype(np.float32)
    body = _highpass(body, 1200.0)
    env = adsr(len(body), a=0.002, d=dur * 0.6, s=0.0, r=dur * 0.2)
    return _normalize(body * env, 0.62)


def _v_shimmer(freq, dur):
    body = _sine(freq * 4.0, dur) + 0.5 * _sine(freq * 6.01, dur)
    env = adsr(len(body), a=0.004, d=dur * 0.7, s=0.0, r=dur * 0.25)
    trem = 1.0 + 0.2 * np.sin(2.0 * np.pi * 9.0 * _t(dur))
    return _normalize(body * env * trem, 0.6)


# ---- expanded Sound Atlas voices -----------------------------------------
def _v_key_family(freq, dur, partials, attack=0.003, decay=0.55,
                  sustain=0.08, release=0.28, cutoff=None, noise=0.0):
    out = np.zeros(max(1, int(dur * SR)), dtype=np.float32)
    for mult, amp in partials:
        out += amp * _sine(freq * mult, dur)
    if noise > 0.0:
        click = _noise(min(0.018, dur))
        n = min(len(click), len(out))
        out[:n] += noise * click[:n] * np.linspace(1.0, 0.0, n, dtype=np.float32)
    if cutoff is not None:
        out = _lowpass(out, cutoff(freq) if callable(cutoff) else cutoff)
    env = adsr(len(out), a=attack, d=max(0.02, dur * decay), s=sustain,
               r=max(0.02, dur * release))
    return _normalize(out * env, 0.78)


def _v_mallet_family(freq, dur, ratios, decay=0.62, tremolo=0.0,
                     cutoff=None):
    out = np.zeros(max(1, int(dur * SR)), dtype=np.float32)
    for mult, amp in ratios:
        out += amp * _sine(freq * mult, dur)
    if cutoff is not None:
        out = _lowpass(out, cutoff(freq) if callable(cutoff) else cutoff)
    env = adsr(len(out), a=0.0015, d=max(0.03, dur * decay), s=0.0,
               r=max(0.03, dur * 0.28))
    if tremolo:
        out *= 0.82 + 0.18 * np.sin(2.0 * np.pi * tremolo * _t(dur))
    return _normalize(out * env, 0.76)


def _v_reed_family(freq, dur, brightness=0.5, vibrato=5.0, breath=0.02,
                   attack=0.05):
    body = ((1.0 - brightness) * _sine(freq, dur)
            + brightness * 0.65 * _saw(freq, dur)
            + 0.22 * _square(freq * 2.0, dur, 0.42))
    body = _lowpass(body, min(9000.0, freq * (5.0 + 4.0 * brightness) + 900.0))
    if breath:
        body += breath * _highpass(_noise(dur), 1800.0)
    vib = 1.0 + 0.018 * np.sin(2.0 * np.pi * vibrato * _t(dur))
    env = adsr(len(body), a=attack, d=dur * 0.15, s=0.72, r=dur * 0.25)
    return _normalize(body * vib * env, 0.72)


def _v_pad_family(freq, dur, detunes=(-9.0, -3.0, 3.0, 9.0),
                  brightness=0.35, attack=0.22, movement=0.18):
    out = np.zeros(max(1, int(dur * SR)), dtype=np.float32)
    for cents in detunes:
        f = freq * (2.0 ** (cents / 1200.0))
        out += (1.0 - brightness) * _tri(f, dur) + brightness * _saw(f, dur)
    cutoff = freq * (2.6 + brightness * 4.0) + 650.0
    out = _lowpass(out, cutoff)
    t = _t(dur)
    out *= 0.88 + movement * np.sin(2.0 * np.pi * 0.23 * t)
    env = adsr(len(out), a=max(0.02, dur * attack), d=dur * 0.18,
               s=0.78, r=dur * 0.28)
    return _normalize(out * env, 0.68)


def _v_pluck_family(freq, dur, bright=0.5, buzz=0.0, body=0.25):
    out = ((1.0 - bright) * _tri(freq, dur)
           + bright * _saw(freq, dur)
           + body * _sine(freq * 2.0, dur))
    if buzz:
        out += buzz * _square(freq * 2.0, dur, 0.18)
    out = _lowpass(out, freq * (4.0 + bright * 5.0) + 700.0)
    env = adsr(len(out), a=0.0015, d=dur * 0.48, s=0.02, r=dur * 0.30)
    return _normalize(out * env, 0.78)


def _v_bass_family(freq, dur, shape="round", cutoff=700.0):
    if shape == "sub":
        body = _sine(freq, dur) + 0.42 * _sine(freq * 0.5, dur)
    elif shape == "fm":
        mod = np.sin(2.0 * np.pi * freq * 2.0 * _t(dur))
        body = np.sin(2.0 * np.pi * freq * _t(dur) + 1.8 * mod).astype(np.float32)
    elif shape == "acid":
        body = _saw(freq, dur) + 0.35 * _square(freq, dur, 0.36)
        cutoff = max(cutoff, freq * 7.0)
    elif shape == "pluck":
        body = _saw(freq, dur) + 0.3 * _sine(freq * 2.0, dur)
    elif shape == "rubber":
        t = _t(dur)
        glide = freq * (1.0 + 0.10 * np.exp(-t * 10.0))
        phase = np.cumsum(2.0 * np.pi * glide / SR)
        body = np.sin(phase).astype(np.float32) + 0.38 * _square(freq, dur, 0.45)
    else:
        body = _sine(freq, dur) + 0.45 * _tri(freq, dur)
    body = _lowpass(body, cutoff)
    sustain = 0.38 if shape not in ("pluck", "rubber") else 0.10
    env = adsr(len(body), a=0.003, d=dur * 0.36, s=sustain, r=dur * 0.28)
    return _normalize(body * env, 0.84)


def _v_grand_piano(freq, dur):
    return _v_key_family(freq, dur, ((1, 1.0), (2, 0.42), (3, 0.22), (4, 0.10)),
                         decay=0.62, sustain=0.07, cutoff=lambda f: f * 7 + 1800,
                         noise=0.08)


def _v_electric_piano(freq, dur):
    out = _v_key_family(freq, dur, ((1, 1.0), (2, 0.28), (3.01, 0.12)),
                        decay=0.52, sustain=0.20, cutoff=lambda f: f * 6 + 1300)
    return _tremolo(out, rate=4.8, depth=0.18)


def _v_harp(freq, dur):
    return _v_pluck_family(freq, dur, bright=0.34, buzz=0.0, body=0.42)


def _v_kalimba(freq, dur):
    return _v_mallet_family(freq, dur, ((1, 1.0), (2.06, 0.32), (3.9, 0.18)), decay=0.50)


def _v_marimba(freq, dur):
    return _v_mallet_family(freq, dur, ((1, 1.0), (3.9, 0.22), (9.2, 0.05)),
                            decay=0.36, cutoff=lambda f: f * 5 + 900)


def _v_vibraphone(freq, dur):
    return _v_mallet_family(freq, dur, ((1, 1.0), (4.0, 0.28), (10.0, 0.07)),
                            decay=0.82, tremolo=5.2)


def _v_organ(freq, dur):
    body = (_sine(freq, dur) + 0.55 * _sine(freq * 2.0, dur)
            + 0.28 * _sine(freq * 3.0, dur) + 0.14 * _sine(freq * 4.0, dur))
    env = adsr(len(body), a=0.035, d=0.05, s=0.88, r=dur * 0.22)
    return _normalize(body * env, 0.70)


def _v_flute(freq, dur):
    return _v_reed_family(freq, dur, brightness=0.10, vibrato=5.1, breath=0.055, attack=0.08)


def _v_clarinet(freq, dur):
    return _v_reed_family(freq, dur, brightness=0.30, vibrato=4.5, breath=0.018, attack=0.045)


def _v_oboe(freq, dur):
    return _v_reed_family(freq, dur, brightness=0.62, vibrato=5.4, breath=0.025, attack=0.055)


def _v_strings(freq, dur):
    return _v_pad_family(freq, dur, detunes=(-7, -2, 2, 7), brightness=0.46, attack=0.14, movement=0.08)


def _v_choir(freq, dur):
    body = (_sine(freq, dur) + 0.38 * _sine(freq * 2.0, dur)
            + 0.18 * _sine(freq * 3.0, dur))
    body = _bandpass(body, max(80.0, freq * 0.7), min(7000.0, freq * 6 + 1500))
    t = _t(dur)
    body *= 0.9 + 0.08 * np.sin(2 * np.pi * 4.2 * t)
    env = adsr(len(body), a=dur * 0.18, d=dur * 0.15, s=0.82, r=dur * 0.30)
    return _normalize(body * env, 0.66)


def _v_analog_pad(freq, dur):
    return _v_pad_family(freq, dur, brightness=0.42, attack=0.20, movement=0.14)


def _v_dream_pad(freq, dur):
    out = _v_pad_family(freq, dur, detunes=(-12, -5, 0, 5, 12), brightness=0.22,
                        attack=0.28, movement=0.22)
    return _reverb(out, amount=0.22, decay=0.60)


def _v_supersaw(freq, dur):
    return _v_pad_family(freq, dur, detunes=(-14, -9, -4, 0, 4, 9, 14),
                         brightness=0.70, attack=0.06, movement=0.08)


def _v_fm_bell(freq, dur):
    t = _t(dur)
    mod = np.sin(2 * np.pi * freq * 2.71 * t)
    body = np.sin(2 * np.pi * freq * t + 3.2 * mod).astype(np.float32)
    env = adsr(len(body), a=0.001, d=dur * 0.78, s=0.0, r=dur * 0.24)
    return _normalize(body * env, 0.72)


def _v_chiptune(freq, dur):
    body = 0.75 * _square(freq, dur, 0.25) + 0.25 * _square(freq * 2.0, dur, 0.5)
    env = adsr(len(body), a=0.002, d=dur * 0.28, s=0.38, r=dur * 0.20)
    return _normalize(body * env, 0.68)


def _v_nylon_guitar(freq, dur):
    return _v_pluck_family(freq, dur, bright=0.28, buzz=0.0, body=0.34)


def _v_koto(freq, dur):
    return _v_pluck_family(freq, dur, bright=0.58, buzz=0.10, body=0.22)


def _v_dulcimer(freq, dur):
    return _v_mallet_family(freq, dur, ((1, 1.0), (2.0, 0.45), (3.01, 0.22), (5.0, 0.10)), decay=0.66)


def _v_sitar(freq, dur):
    out = _v_pluck_family(freq, dur, bright=0.68, buzz=0.28, body=0.14)
    return _delay(out, time=0.035, feedback=0.16, mix=0.12)


def _v_steel_drum(freq, dur):
    return _v_mallet_family(freq, dur, ((1, 1.0), (2.4, 0.38), (3.6, 0.22), (5.4, 0.10)), decay=0.72)


def _v_reed(freq, dur):
    return _v_reed_family(freq, dur, brightness=0.46, vibrato=4.2, breath=0.03, attack=0.04)


def _v_whistle(freq, dur):
    body = _sine(freq, dur) + 0.12 * _sine(freq * 2.0, dur)
    body += 0.02 * _highpass(_noise(dur), 2600.0)
    env = adsr(len(body), a=0.035, d=dur * 0.10, s=0.72, r=dur * 0.22)
    return _normalize(body * env, 0.66)


def _v_brass(freq, dur):
    body = _saw(freq, dur) + 0.38 * _square(freq, dur, 0.43)
    body = _lowpass(body, freq * 5.2 + 1000)
    env = adsr(len(body), a=0.045, d=dur * 0.20, s=0.65, r=dur * 0.24)
    return _normalize(body * env, 0.74)


def _v_muted_brass(freq, dur):
    body = _saw(freq, dur) + 0.24 * _square(freq * 2, dur, 0.30)
    body = _bandpass(body, 350.0, min(7000.0, freq * 7 + 1400))
    env = adsr(len(body), a=0.018, d=dur * 0.32, s=0.30, r=dur * 0.24)
    return _normalize(body * env, 0.70)


def _v_vox(freq, dur):
    body = (_sine(freq, dur) + 0.45 * _sine(freq * 2.0, dur)
            + 0.20 * _sine(freq * 3.0, dur))
    body = _bandpass(body, 250.0, 3600.0)
    env = adsr(len(body), a=dur * 0.12, d=dur * 0.12, s=0.74, r=dur * 0.28)
    return _normalize(body * env, 0.68)


def _v_synth_pluck(freq, dur):
    out = _v_pluck_family(freq, dur, bright=0.74, buzz=0.05, body=0.18)
    return _delay(out, time=0.12, feedback=0.18, mix=0.16)


def _v_crystal_pad(freq, dur):
    base = _v_pad_family(freq, dur, detunes=(-7, 0, 7), brightness=0.22,
                         attack=0.25, movement=0.16)
    sparkle = 0.18 * _v_shimmer(freq, dur)
    return _normalize(base + sparkle, 0.66)


def _v_accordion(freq, dur):
    body = 0.62 * _saw(freq, dur) + 0.38 * _square(freq * 2.0, dur, 0.42)
    body = _lowpass(body, freq * 6 + 1400)
    env = adsr(len(body), a=0.035, d=dur * 0.12, s=0.72, r=dur * 0.22)
    trem = 0.94 + 0.06 * np.sin(2 * np.pi * 5.0 * _t(dur))
    return _normalize(body * env * trem, 0.70)


def _v_sub_bass(freq, dur):
    return _v_bass_family(freq, dur, "sub", cutoff=max(220.0, freq * 3.0))


def _v_synth_bass(freq, dur):
    return _v_bass_family(freq, dur, "round", cutoff=max(500.0, freq * 7.0))


def _v_acid_bass(freq, dur):
    return _v_bass_family(freq, dur, "acid", cutoff=max(900.0, freq * 9.0))


def _v_upright_bass(freq, dur):
    body = _v_bass_family(freq, dur, "pluck", cutoff=max(600.0, freq * 6.0))
    click = _lowpass(_noise(min(0.025, dur)), 900.0)
    n = min(len(click), len(body))
    body[:n] += 0.08 * click[:n] * np.linspace(1, 0, n, dtype=np.float32)
    return _normalize(body, 0.82)


def _v_fm_bass(freq, dur):
    return _v_bass_family(freq, dur, "fm", cutoff=max(1000.0, freq * 8.0))


def _v_pluck_bass(freq, dur):
    return _v_bass_family(freq, dur, "pluck", cutoff=max(700.0, freq * 8.0))


def _v_rubber_bass(freq, dur):
    return _v_bass_family(freq, dur, "rubber", cutoff=max(650.0, freq * 7.0))


_VOICES = {
    "music_box": _v_music_box, "bell": _v_bell, "glass": _v_glass,
    "celeste": _v_celeste, "toy_piano": _v_toy_piano, "warm_pad": _v_warm_pad,
    "pluck": _v_pluck, "moon_pluck": _v_moon_pluck, "warm_bass": _v_warm_bass,
    "soft_lead": _v_soft_lead, "meow": _v_meow, "purr": _v_purr,
    "croak": _v_croak, "quack": _v_quack, "hoot": _v_hoot, "chirp": _v_chirp,
    "shimmer": _v_shimmer,
    # Sound Atlas instruments
    "grand_piano": _v_grand_piano, "electric_piano": _v_electric_piano,
    "harp": _v_harp, "kalimba": _v_kalimba, "marimba": _v_marimba,
    "vibraphone": _v_vibraphone, "organ": _v_organ, "flute": _v_flute,
    "clarinet": _v_clarinet, "oboe": _v_oboe, "strings": _v_strings,
    "choir": _v_choir, "analog_pad": _v_analog_pad, "dream_pad": _v_dream_pad,
    "supersaw": _v_supersaw, "fm_bell": _v_fm_bell, "chiptune": _v_chiptune,
    "nylon_guitar": _v_nylon_guitar, "koto": _v_koto,
    "dulcimer": _v_dulcimer, "sitar": _v_sitar, "steel_drum": _v_steel_drum,
    "reed": _v_reed, "whistle": _v_whistle, "brass": _v_brass,
    "muted_brass": _v_muted_brass, "vox": _v_vox,
    "synth_pluck": _v_synth_pluck, "crystal_pad": _v_crystal_pad,
    "accordion": _v_accordion, "sub_bass": _v_sub_bass,
    "synth_bass": _v_synth_bass, "acid_bass": _v_acid_bass,
    "upright_bass": _v_upright_bass, "fm_bass": _v_fm_bass,
    "pluck_bass": _v_pluck_bass, "rubber_bass": _v_rubber_bass,
}


# ---------------------------------------------------------------------------
# Drum / percussion hits  -> mono float
# ---------------------------------------------------------------------------
def drum(name, gain=1.0):
    fn = _DRUMS.get(name, _d_kick)
    return _edge_fade(_normalize(fn(), 0.92) * gain, ms=2.0)


def procedural_drum(spec, gain=1.0):
    """Synthesize a deterministic drum/percussion hit from a bounded spec."""
    spec = spec or {}
    kind = str(spec.get("kind", "perc"))
    dur = max(0.025, min(float(spec.get("dur", 0.24)), 1.5))
    t = _t(dur)

    if kind == "kick":
        f0 = max(45.0, min(float(spec.get("f0", 120.0)), 240.0))
        f1 = max(24.0, min(float(spec.get("f1", 46.0)), f0))
        sweep = max(3.0, min(float(spec.get("sweep", 18.0)), 50.0))
        inst = f1 + (f0 - f1) * np.exp(-t * sweep)
        phase = np.cumsum(2.0 * np.pi * inst / SR)
        out = np.sin(phase).astype(np.float32) * np.exp(-t * 8.5).astype(np.float32)
        click = max(0.0, min(float(spec.get("click", 0.2)), 0.8))
        if click:
            n = min(len(out), max(1, int(0.008 * SR)))
            out[:n] += _highpass(_noise(n / SR), 2500.0)[:n] * np.linspace(1, 0, n) * click
        drive = max(1.0, min(float(spec.get("drive", 1.0)), 4.0))
        if drive > 1.001:
            out = np.tanh(out * drive).astype(np.float32) / np.tanh(drive)
    elif kind == "snare":
        tone = max(80.0, min(float(spec.get("tone", 190.0)), 420.0))
        brightness = max(500.0, min(float(spec.get("brightness", 1800.0)), 10000.0))
        decay = max(4.0, min(float(spec.get("decay", 20.0)), 80.0))
        noise_mix = max(0.0, min(float(spec.get("noise", 0.72)), 1.0))
        noise = _highpass(_noise(dur), brightness) * np.exp(-t * decay)
        body = (_sine(tone, dur) + 0.34 * _sine(tone * 1.77, dur)) * np.exp(-t * (decay * 1.25))
        out = noise * noise_mix + body * (1.0 - noise_mix * 0.52)
    elif kind in ("hat", "shaker"):
        brightness = max(1200.0, min(float(spec.get("brightness", 6500.0)), 14000.0))
        decay = max(6.0, min(float(spec.get("decay", 35.0)), 120.0))
        out = _highpass(_noise(dur), brightness) * np.exp(-t * decay)
        metal = max(0.0, min(float(spec.get("metal", 0.24 if kind == "hat" else 0.05)), 1.0))
        if metal:
            cluster = (_square(4210.0, dur) + _square(5740.0, dur) + _square(7130.0, dur)) / 3.0
            out += _highpass(cluster, 4500.0) * np.exp(-t * decay * 0.9) * metal
        if kind == "shaker":
            pulse = 0.72 + 0.28 * np.sin(2.0 * np.pi * 23.0 * t)
            out *= pulse.astype(np.float32)
    elif kind == "tom":
        freq = max(55.0, min(float(spec.get("freq", 150.0)), 480.0))
        bend = max(0.0, min(float(spec.get("bend", 0.18)), 0.8))
        decay = max(3.0, min(float(spec.get("decay", 12.0)), 50.0))
        inst = freq * (1.0 + bend * np.exp(-t * 18.0))
        phase = np.cumsum(2.0 * np.pi * inst / SR)
        out = (np.sin(phase) + 0.18 * np.sin(phase * 2.03)).astype(np.float32)
        out *= np.exp(-t * decay).astype(np.float32)
    elif kind == "metal":
        freq = max(120.0, min(float(spec.get("freq", 520.0)), 2400.0))
        ratio = max(1.05, min(float(spec.get("inharmonic", 1.73)), 4.5))
        decay = max(2.0, min(float(spec.get("decay", 10.0)), 60.0))
        out = (_sine(freq, dur) + 0.65 * _sine(freq * ratio, dur)
               + 0.36 * _sine(freq * ratio * 1.61, dur))
        out *= np.exp(-t * decay).astype(np.float32)
        out = _highpass(out, 220.0)
    elif kind == "clap":
        brightness = max(400.0, min(float(spec.get("brightness", 1600.0)), 9000.0))
        decay = max(5.0, min(float(spec.get("decay", 22.0)), 80.0))
        bursts = max(2, min(int(spec.get("bursts", 3)), 6))
        out = np.zeros(len(t), dtype=np.float32)
        for i in range(bursts):
            start = int(i * 0.012 * SR)
            burst_dur = max(0.01, dur - i * 0.012)
            burst = _bandpass(_noise(burst_dur), brightness, min(14000.0, brightness * 4.0))
            env = np.exp(-np.arange(len(burst), dtype=np.float32) / SR * decay)
            _place(out, burst * env, start, 1.0 / bursts ** 0.35)
    else:
        freq = max(70.0, min(float(spec.get("freq", 420.0)), 2600.0))
        ratio = max(1.05, min(float(spec.get("ratio", 2.13)), 6.0))
        decay = max(3.0, min(float(spec.get("decay", 18.0)), 90.0))
        noise_mix = max(0.0, min(float(spec.get("noise", 0.12)), 0.8))
        tonal = _sine(freq, dur) + 0.48 * _sine(freq * ratio, dur)
        out = tonal * np.exp(-t * decay)
        if noise_mix:
            texture = _bandpass(_noise(dur), max(80.0, freq * 0.5),
                                min(12000.0, freq * 5.0))
            out += texture * np.exp(-t * decay * 1.4) * noise_mix

    return _edge_fade(_normalize(out.astype(np.float32), 0.92) * gain, ms=2.0)


def _component_drum(comp, name=None):
    """Resolve a custom kit token or fall back to the curated drum palette."""
    if comp.get("drum_spec"):
        return procedural_drum(comp.get("drum_spec"), gain=1.0)
    kit = comp.get("drum_kit") or {}
    if name in kit:
        return procedural_drum(kit[name], gain=1.0)
    return drum(name or comp.get("drum", "kick"), gain=1.0)


def _d_kick(dur=0.35, f0=120.0, f1=45.0):
    t = _t(dur)
    sweep = f1 + (f0 - f1) * np.exp(-t * 18.0)
    ph = np.cumsum(2.0 * np.pi * sweep / SR)
    body = np.sin(ph).astype(np.float32)
    env = np.exp(-t * 9.0).astype(np.float32)
    click = _noise(0.005) * np.linspace(1, 0, int(0.005 * SR))
    out = body * env
    out[:len(click)] += 0.3 * click
    return out


def _d_deep_kick():
    return _d_kick(dur=0.45, f0=110.0, f1=38.0)


def _d_snare():
    dur = 0.22
    t = _t(dur)
    noise = _highpass(_noise(dur), 1400.0)
    tone = 0.5 * _sine(190.0, dur) + 0.3 * _sine(330.0, dur)
    env = np.exp(-t * 22.0).astype(np.float32)
    tenv = np.exp(-t * 30.0).astype(np.float32)
    return noise * env + tone * tenv


def _d_brush_snare():
    dur = 0.26
    t = _t(dur)
    noise = _bandpass(_noise(dur), 2000.0, 8000.0)
    env = np.exp(-t * 14.0).astype(np.float32)
    return noise * env


def _d_hat(dur=0.07, hp=7000.0):
    t = _t(dur)
    noise = _highpass(_noise(dur), hp)
    env = np.exp(-t * 60.0).astype(np.float32)
    return noise * env


def _d_open_hat():
    return _d_hat(dur=0.3, hp=6500.0)


def _d_shaker():
    dur = 0.16
    t = _t(dur)
    noise = _bandpass(_noise(dur), 4000.0, 9000.0)
    env = (np.exp(-t * 16.0) * (0.4 + 0.6 * np.sin(np.pi * t / dur) ** 2)).astype(np.float32)
    return noise * env


def _d_pebble():
    dur = 0.06
    t = _t(dur)
    noise = _bandpass(_noise(dur), 2500.0, 6000.0)
    env = np.exp(-t * 70.0).astype(np.float32)
    return noise * env


def _d_log():
    dur = 0.18
    t = _t(dur)
    body = _sine(220.0, dur) + 0.5 * _sine(440.0, dur) + 0.3 * _tri(330.0, dur)
    env = np.exp(-t * 24.0).astype(np.float32)
    return body * env


def _d_clap():
    dur = 0.2
    t = _t(dur)
    noise = _bandpass(_noise(dur), 1200.0, 5000.0)
    # three quick bursts
    env = np.zeros_like(t)
    for off in (0.0, 0.012, 0.026):
        k = int(off * SR)
        seg = np.exp(-(t) * 50.0)
        env[k:] += seg[:len(env) - k]
    env = np.clip(env, 0, 1)
    return noise * env


def _d_tick():
    dur = 0.05
    t = _t(dur)
    body = _sine(2200.0, dur)
    env = np.exp(-t * 90.0).astype(np.float32)
    return body * env


def _d_bell_tick():
    dur = 0.4
    t = _t(dur)
    body = _sine(1320.0, dur) + 0.5 * _sine(1980.0, dur)
    env = np.exp(-t * 9.0).astype(np.float32)
    return body * env


def _d_paw():
    dur = 0.1
    t = _t(dur)
    body = _lowpass(_noise(dur), 900.0) + 0.4 * _sine(160.0, dur)
    env = np.exp(-t * 30.0).astype(np.float32)
    return body * env


def _d_duck():
    return _v_quack(520.0, 0.16)


def _d_sheep_bell():
    dur = 0.5
    t = _t(dur)
    body = _sine(880.0, dur) + 0.6 * _sine(1170.0, dur) + 0.3 * _sine(1760.0, dur)
    env = np.exp(-t * 7.0).astype(np.float32)
    return body * env


def _d_frog_pop():
    dur = 0.12
    t = _t(dur)
    f = 320.0 - 180.0 * np.exp(-t * 40.0)
    ph = np.cumsum(2.0 * np.pi * f / SR)
    body = np.sin(ph).astype(np.float32) + 0.4 * _square(180.0, dur, 0.3)
    env = np.exp(-t * 26.0).astype(np.float32)
    return body * env


def _d_bark():
    dur = 0.16
    t = _t(dur)
    body = _saw(220.0, dur) + 0.5 * _square(330.0, dur, 0.4)
    body = _bandpass(body, 400.0, 2200.0)
    env = (np.exp(-t * 20.0) * (0.5 + 0.5 * np.sin(np.pi * t / dur))).astype(np.float32)
    return body * env


# ---- expanded Sound Atlas percussion -------------------------------------
def _d_punch_kick():
    out = _d_kick(dur=0.28, f0=155.0, f1=52.0)
    n = min(len(out), int(0.008 * SR))
    out[:n] += 0.28 * _highpass(_noise(n / SR), 3500.0)[:n] * np.linspace(1, 0, n)
    return out


def _d_sub_kick():
    return _d_kick(dur=0.58, f0=92.0, f1=31.0)


def _d_rimshot():
    dur = 0.10
    t = _t(dur)
    body = 0.7 * _sine(920.0, dur) + 0.45 * _sine(1510.0, dur)
    body += 0.34 * _bandpass(_noise(dur), 1800.0, 7000.0)
    return body * np.exp(-t * 52.0).astype(np.float32)


def _d_finger_snap():
    dur = 0.12
    t = _t(dur)
    noise = _bandpass(_noise(dur), 1500.0, 9500.0)
    env = np.exp(-t * 42.0)
    env += 0.55 * np.roll(env, int(0.012 * SR))
    env[:int(0.012 * SR)] = np.exp(-t[:int(0.012 * SR)] * 42.0)
    return noise * env.astype(np.float32)


def _d_brush_hat():
    dur = 0.18
    t = _t(dur)
    noise = _highpass(_noise(dur), 5200.0)
    return noise * np.exp(-t * 22.0).astype(np.float32) * 0.7


def _d_seed_shaker():
    dur = 0.22
    t = _t(dur)
    noise = _bandpass(_noise(dur), 2800.0, 8200.0)
    pulse = 0.30 + 0.70 * (np.sin(2 * np.pi * 34.0 * t) > 0.1)
    return noise * pulse.astype(np.float32) * np.exp(-t * 11.0).astype(np.float32)


def _d_tambourine():
    dur = 0.32
    t = _t(dur)
    noise = _highpass(_noise(dur), 5000.0)
    tone = 0.22 * _sine(4100.0, dur) + 0.18 * _sine(5250.0, dur)
    env = np.exp(-t * 14.0).astype(np.float32)
    return (noise * 0.65 + tone) * env


def _d_triangle():
    dur = 0.75
    t = _t(dur)
    body = _sine(2100.0, dur) + 0.38 * _sine(4205.0, dur)
    return body * np.exp(-t * 5.5).astype(np.float32)


def _d_ride():
    dur = 0.9
    t = _t(dur)
    noise = _highpass(_noise(dur), 4200.0)
    metal = (_sine(980.0, dur) + 0.45 * _sine(1477.0, dur)
             + 0.30 * _sine(2380.0, dur))
    return (0.45 * noise + 0.55 * metal) * np.exp(-t * 4.6).astype(np.float32)


def _d_crash():
    dur = 1.1
    t = _t(dur)
    noise = _highpass(_noise(dur), 2600.0)
    shimmer = 0.18 * _sine(3400.0, dur) + 0.12 * _sine(5100.0, dur)
    return (noise * 0.78 + shimmer) * np.exp(-t * 3.8).astype(np.float32)


def _d_tom(freq, dur=0.28):
    t = _t(dur)
    sweep = freq * (0.76 + 0.24 * np.exp(-t * 18.0))
    phase = np.cumsum(2 * np.pi * sweep / SR)
    body = np.sin(phase).astype(np.float32) + 0.18 * _noise(dur)
    return body * np.exp(-t * 13.0).astype(np.float32)


def _d_tom_low():
    return _d_tom(118.0, 0.38)


def _d_tom_mid():
    return _d_tom(176.0, 0.31)


def _d_tom_high():
    return _d_tom(252.0, 0.25)


def _d_hand_drum(freq=170.0, dur=0.24, bright=0.22):
    t = _t(dur)
    tone = _sine(freq, dur) + 0.45 * _sine(freq * 1.55, dur)
    slap = bright * _bandpass(_noise(dur), 900.0, 5200.0)
    return (tone + slap) * np.exp(-t * 17.0).astype(np.float32)


def _d_conga_low():
    return _d_hand_drum(150.0, 0.30, 0.16)


def _d_conga_high():
    return _d_hand_drum(245.0, 0.22, 0.22)


def _d_bongo_low():
    return _d_hand_drum(210.0, 0.19, 0.28)


def _d_bongo_high():
    return _d_hand_drum(330.0, 0.16, 0.34)


def _d_hand_drum_hit():
    return _d_hand_drum(185.0, 0.28, 0.25)


def _d_frame_drum():
    return _d_hand_drum(105.0, 0.42, 0.10)


def _d_woodblock():
    dur = 0.10
    t = _t(dur)
    body = _sine(760.0, dur) + 0.58 * _sine(1130.0, dur)
    return body * np.exp(-t * 48.0).astype(np.float32)


def _d_clave():
    dur = 0.09
    t = _t(dur)
    body = _sine(1450.0, dur) + 0.36 * _sine(2370.0, dur)
    return body * np.exp(-t * 60.0).astype(np.float32)


def _d_cowbell():
    dur = 0.42
    t = _t(dur)
    body = _square(540.0, dur, 0.46) + 0.55 * _square(845.0, dur, 0.48)
    body = _bandpass(body, 350.0, 4200.0)
    return body * np.exp(-t * 9.0).astype(np.float32)


def _d_metal_hit():
    dur = 0.48
    t = _t(dur)
    body = (_sine(430.0, dur) + 0.66 * _sine(711.0, dur)
            + 0.38 * _sine(1213.0, dur) + 0.20 * _sine(1897.0, dur))
    return body * np.exp(-t * 7.0).astype(np.float32)


def _d_glitch_click():
    dur = 0.055
    t = _t(dur)
    body = _square(2300.0, dur, 0.18) + 0.45 * _noise(dur)
    body = _highpass(body, 1400.0)
    return body * np.exp(-t * 85.0).astype(np.float32)


def _d_noise_hit():
    dur = 0.24
    t = _t(dur)
    noise = _bandpass(_noise(dur), 500.0, 6200.0)
    return noise * np.exp(-t * 18.0).astype(np.float32)


def _d_stomp():
    dur = 0.24
    t = _t(dur)
    body = _lowpass(_noise(dur), 650.0) + 0.65 * _sine(82.0, dur)
    return body * np.exp(-t * 16.0).astype(np.float32)


def _d_water_drop():
    dur = 0.28
    t = _t(dur)
    freq = 780.0 - 420.0 * (t / max(dur, 1e-3))
    phase = np.cumsum(2 * np.pi * freq / SR)
    body = np.sin(phase).astype(np.float32)
    return body * np.exp(-t * 17.0).astype(np.float32)


_DRUMS = {
    "kick": _d_kick, "deep_kick": _d_deep_kick, "snare": _d_snare,
    "brush_snare": _d_brush_snare, "hat": _d_hat, "open_hat": _d_open_hat,
    "shaker": _d_shaker, "pebble": _d_pebble, "log": _d_log, "clap": _d_clap,
    "tick": _d_tick, "bell_tick": _d_bell_tick, "paw": _d_paw, "duck": _d_duck,
    "sheep_bell": _d_sheep_bell, "frog_pop": _d_frog_pop, "bark": _d_bark,
    # Sound Atlas percussion
    "punch_kick": _d_punch_kick, "sub_kick": _d_sub_kick,
    "rimshot": _d_rimshot, "finger_snap": _d_finger_snap,
    "brush_hat": _d_brush_hat, "seed_shaker": _d_seed_shaker,
    "tambourine": _d_tambourine, "triangle": _d_triangle,
    "ride": _d_ride, "crash": _d_crash, "tom_low": _d_tom_low,
    "tom_mid": _d_tom_mid, "tom_high": _d_tom_high,
    "conga_low": _d_conga_low, "conga_high": _d_conga_high,
    "bongo_low": _d_bongo_low, "bongo_high": _d_bongo_high,
    "hand_drum": _d_hand_drum_hit, "frame_drum": _d_frame_drum,
    "woodblock": _d_woodblock, "clave": _d_clave, "cowbell": _d_cowbell,
    "metal_hit": _d_metal_hit, "glitch_click": _d_glitch_click,
    "noise_hit": _d_noise_hit, "stomp": _d_stomp, "water_drop": _d_water_drop,
}


# ---------------------------------------------------------------------------
# Post effects
# ---------------------------------------------------------------------------
def _make_ir(decay=0.4, pre=0.0):
    n = int(decay * SR)
    rng = np.random.RandomState(7)
    ir = rng.uniform(-1, 1, n) * np.exp(-np.linspace(0, 6, n))
    ir[0] = 1.0
    return ir.astype(np.float32)


_IR_CACHE = {}


def _reverb(buf, amount=0.3, decay=0.45):
    key = round(decay, 3)
    ir = _IR_CACHE.get(key)
    if ir is None:
        ir = _make_ir(decay)
        _IR_CACHE[key] = ir
    output_len = len(buf) + len(ir) - 1
    fft_len = 1 << max(0, output_len - 1).bit_length()
    wet = np.fft.irfft(
        np.fft.rfft(buf, fft_len) * np.fft.rfft(ir, fft_len),
        fft_len,
    )[:len(buf)].astype(np.float32)
    wet = _normalize(wet, float(np.max(np.abs(buf)) + 1e-6))
    return ((1.0 - amount) * buf + amount * wet).astype(np.float32)


def _delay(buf, time=0.25, feedback=0.35, mix=0.3):
    d = int(time * SR)
    out = buf.copy()
    if d <= 0:
        return out
    echo = np.zeros(len(buf) + d * 4, dtype=np.float32)
    echo[:len(buf)] = buf
    tap = buf.copy()
    g = feedback
    pos = d
    for _ in range(4):
        end = min(len(echo), pos + len(tap))
        echo[pos:end] += (tap * g)[:end - pos]
        g *= feedback
        pos += d
    wet = echo[:len(buf)]
    return ((1.0 - mix) * buf + mix * wet).astype(np.float32)


def _tremolo(buf, rate=6.0, depth=0.5):
    t = np.arange(len(buf), dtype=np.float32) / SR
    lfo = (1.0 - depth) + depth * (0.5 + 0.5 * np.sin(2.0 * np.pi * rate * t))
    return (buf * lfo).astype(np.float32)


def _bitcrush(buf, bits=6, down=3):
    levels = 2 ** bits
    q = np.round(buf * levels) / levels
    if down > 1:
        q = np.repeat(q[::down], down)[:len(buf)]
    return q.astype(np.float32)


# ---- expanded Sound Atlas effects ----------------------------------------
def _modulated_delay(buf, base=0.012, depth=0.004, rate=0.5, mix=0.3,
                     feedback=0.0):
    if len(buf) < 2:
        return buf.copy()
    t = np.arange(len(buf), dtype=np.float32) / SR
    delay_s = np.maximum(0.0, base + depth * np.sin(2.0 * np.pi * rate * t))
    src = np.arange(len(buf), dtype=np.float32) - delay_s * SR
    wet = np.interp(src, np.arange(len(buf), dtype=np.float32), buf,
                    left=0.0, right=0.0).astype(np.float32)
    if feedback > 0.0:
        wet = wet + feedback * np.roll(wet, max(1, int((base + depth) * SR)))
        wet[:max(1, int((base + depth) * SR))] *= 0.5
    return ((1.0 - mix) * buf + mix * wet).astype(np.float32)


def _phaser(buf, rate=0.45, depth=0.4):
    if len(buf) < 3:
        return buf.copy()
    t = np.arange(len(buf), dtype=np.float32) / SR
    delay = (0.0007 + (0.0035 * depth) * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t)))
    src = np.arange(len(buf), dtype=np.float32) - delay * SR
    shifted = np.interp(src, np.arange(len(buf), dtype=np.float32), buf,
                        left=0.0, right=0.0).astype(np.float32)
    return _normalize((0.78 * buf - 0.44 * shifted).astype(np.float32),
                      float(np.max(np.abs(buf)) + 1e-6))


def _overdrive(buf, drive=2.0, mix=0.35):
    wet = np.tanh(buf * max(1.0, drive)).astype(np.float32)
    wet = _normalize(wet, float(np.max(np.abs(buf)) + 1e-6))
    return ((1.0 - mix) * buf + mix * wet).astype(np.float32)


def _ring_mod(buf, freq=60.0, mix=0.4):
    t = np.arange(len(buf), dtype=np.float32) / SR
    wet = buf * np.sin(2.0 * np.pi * freq * t)
    return ((1.0 - mix) * buf + mix * wet).astype(np.float32)


def _vibrato(buf, rate=5.0, depth=0.002):
    if len(buf) < 2:
        return buf.copy()
    t = np.arange(len(buf), dtype=np.float32) / SR
    src = np.arange(len(buf), dtype=np.float32) + depth * SR * np.sin(2 * np.pi * rate * t)
    return np.interp(src, np.arange(len(buf), dtype=np.float32), buf,
                     left=0.0, right=0.0).astype(np.float32)


def _gate(buf, threshold=0.08, floor=0.1):
    amp = np.abs(buf)
    gain = np.where(amp >= threshold, 1.0, floor).astype(np.float32)
    # Smooth just enough to avoid zipper clicks while keeping the gated feel.
    gain = _lowpass(gain, 90.0)
    return (buf * gain).astype(np.float32)


def _compress(buf, threshold=0.4, ratio=3.0):
    threshold = max(0.02, min(0.95, float(threshold)))
    ratio = max(1.0, float(ratio))
    mag = np.abs(buf)
    over = np.maximum(0.0, mag - threshold)
    compressed_mag = np.minimum(mag, threshold) + over / ratio
    out = np.sign(buf) * compressed_mag
    return _normalize(out.astype(np.float32), min(0.92, float(np.max(mag)) + 1e-6))


def _resonator(buf, freq=440.0, decay=0.35, mix=0.3):
    delay = max(1, int(SR / max(40.0, float(freq))))
    wet = np.zeros_like(buf)
    wet[:] = buf
    gain = max(0.05, min(0.92, float(decay)))
    for tap in range(1, 7):
        off = delay * tap
        if off >= len(buf):
            break
        wet[off:] += buf[:-off] * (gain ** tap)
    wet = _normalize(wet, float(np.max(np.abs(buf)) + 1e-6))
    return ((1.0 - mix) * buf + mix * wet).astype(np.float32)


def _lo_fi(buf, bits=8, down=3, cutoff=3600.0):
    return _lowpass(_bitcrush(buf, bits=bits, down=down), cutoff)


def apply_effect(buf, name, params=None):
    p = params or {}
    if name in ("chain", "macro"):
        out = buf
        for stage in (p.get("chain") or [])[:6]:
            try:
                stage_name = stage[0]
                stage_params = stage[1] if len(stage) > 1 else None
            except (TypeError, IndexError):
                continue
            if stage_name in ("chain", "macro"):
                continue
            out = apply_effect(out, stage_name, stage_params)
        return out
    if name == "reverb":
        return _reverb(buf, p.get("amount", 0.3), p.get("decay", 0.45))
    if name == "echo" or name == "delay":
        return _delay(buf, p.get("time", 0.28), p.get("feedback", 0.4), p.get("mix", 0.35))
    if name == "ripple_delay":
        return _delay(buf, p.get("time", 0.14), p.get("feedback", 0.45), p.get("mix", 0.4))
    if name == "lowpass":
        return _lowpass(buf, p.get("cutoff", 900.0))
    if name == "highpass":
        return _highpass(buf, p.get("cutoff", 1200.0))
    if name == "tremolo":
        return _tremolo(buf, p.get("rate", 6.0), p.get("depth", 0.5))
    if name == "bitcrush":
        return _bitcrush(buf, p.get("bits", 6), p.get("down", 3))
    if name == "reverse":
        return buf[::-1].copy()
    if name == "fade_in":
        n = min(len(buf), int(p.get("time", 0.5) * SR))
        out = buf.copy()
        out[:n] *= np.linspace(0, 1, n, dtype=np.float32)
        return out
    if name == "fade_out":
        n = min(len(buf), int(p.get("time", 0.5) * SR))
        out = buf.copy()
        out[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
        return out
    if name == "chorus":
        return _modulated_delay(buf, base=0.012, depth=p.get("depth", 0.004),
                                rate=p.get("rate", 0.5), mix=p.get("mix", 0.3))
    if name == "flanger":
        return _modulated_delay(buf, base=p.get("base", 0.0025),
                                depth=p.get("depth", 0.004),
                                rate=p.get("rate", 0.5), mix=p.get("mix", 0.35),
                                feedback=0.18)
    if name == "phaser":
        return _phaser(buf, p.get("rate", 0.45), p.get("depth", 0.4))
    if name == "overdrive":
        return _overdrive(buf, p.get("drive", 2.0), p.get("mix", 0.35))
    if name == "distortion":
        return _overdrive(buf, p.get("drive", 5.0), p.get("mix", 0.65))
    if name == "ring_mod":
        return _ring_mod(buf, p.get("freq", 60.0), p.get("mix", 0.4))
    if name == "vibrato":
        return _vibrato(buf, p.get("rate", 5.0), p.get("depth", 0.002))
    if name == "wow_flutter":
        slow = _vibrato(buf, p.get("rate", 0.5), p.get("depth", 0.004))
        return _vibrato(slow, p.get("flutter_rate", 6.0),
                        p.get("flutter_depth", 0.0005))
    if name == "gate":
        return _gate(buf, p.get("threshold", 0.08), p.get("floor", 0.1))
    if name == "compressor":
        return _compress(buf, p.get("threshold", 0.4), p.get("ratio", 3.0))
    if name == "resonator":
        return _resonator(buf, p.get("freq", 440.0), p.get("decay", 0.35),
                          p.get("mix", 0.3))
    if name == "lo_fi":
        return _lo_fi(buf, p.get("bits", 8), p.get("down", 3),
                      p.get("cutoff", 3600.0))
    return buf


# ---------------------------------------------------------------------------
# Timeline rendering for patterned components
# ---------------------------------------------------------------------------
STEPS_PER_BEAT = 2          # 8th-note grid resolution
BEATS_PER_BAR = 4
STEPS_PER_BAR = STEPS_PER_BEAT * BEATS_PER_BAR     # = 8


def sec_per_step(bpm):
    return (60.0 / bpm) / STEPS_PER_BEAT


def _place(dst, src, offset, gain=1.0):
    """Mix ``src`` into ``dst`` safely, clipping at either timeline edge."""
    if len(dst) == 0 or len(src) == 0:
        return
    offset = int(offset)
    if offset < 0:
        cut = min(len(src), -offset)
        src = src[cut:]
        offset = 0
    if offset >= len(dst) or len(src) == 0:
        return
    end = min(len(dst), offset + len(src))
    count = end - offset
    if count > 0:
        dst[offset:end] += src[:count] * gain


def render_rhythm(comp, bpm):
    sps = sec_per_step(bpm)
    length = comp.get("length_steps", STEPS_PER_BAR)
    total = int(length * sps * SR) + int(0.4 * SR)
    out = np.zeros(total, dtype=np.float32)
    for ev in comp.get("pattern", []):
        name, step = ev[0], ev[1]
        g = ev[2] if len(ev) > 2 else 1.0
        hit = _component_drum(comp, name)
        _place(out, hit, int(float(step) * sps * SR), 0.9 * float(g))
    return _normalize(out, 0.9)


def render_loop(comp, bpm):
    sps = sec_per_step(bpm)
    length = comp.get("length_steps", STEPS_PER_BAR * 2)
    total = int(length * sps * SR) + int(1.2 * SR)
    out = np.zeros(total, dtype=np.float32)
    for ev in comp.get("pattern", []):
        notes, step, dur_steps = ev[0], ev[1], ev[2]
        g = float(ev[3]) if len(ev) > 3 else 1.0
        if isinstance(notes, (tuple, list)):
            note_names = list(notes)
        else:
            note_names = [notes]
        strum = max(0.0, min(float(comp.get("strum_ms", 0.0)), 80.0)) / 1000.0
        event_seconds = float(dur_steps) * sps + strum * max(0, len(note_names) - 1)
        event = np.zeros(max(1, int(event_seconds * SR)), dtype=np.float32)
        for index, note in enumerate(note_names):
            snd = _component_tone(comp, note_freq(note), float(dur_steps) * sps)
            direction = comp.get("strum_direction", "up")
            order_index = index if direction != "down" else len(note_names) - 1 - index
            _place(event, snd, int(order_index * strum * SR), 0.72 / max(1.0, len(note_names) ** 0.35))
        _place(out, event, int(float(step) * sps * SR), g)
    return _normalize(out, 0.85)


def render_ambience(comp):
    layers = comp.get("amb_layers") or []
    if layers:
        dur = max(0.5, min(float(comp.get("dur", 4.0)), 12.0))
        out = np.zeros(max(1, int(dur * SR)), dtype=np.float32)
        for layer in layers[:5]:
            if not isinstance(layer, dict):
                continue
            kind = layer.get("kind", "wind")
            gain = max(0.0, min(float(layer.get("gain", 0.3)), 1.0))
            bed = render_ambience({"amb": kind, "dur": dur})
            _place(out, bed, 0, gain)
        drone_notes = comp.get("drone_notes") or []
        if drone_notes:
            tone_comp = {"voice": comp.get("drone_voice", "dream_pad"),
                         "timbre": comp.get("drone_timbre")}
            for note in drone_notes[:4]:
                tone = _component_tone(tone_comp, note_freq(note), dur)
                _place(out, tone, 0, 0.13 / max(1.0, len(drone_notes) ** 0.4))
        for event in (comp.get("detail_events") or [])[:10]:
            if not isinstance(event, dict):
                continue
            try:
                note = event.get("note", "C5")
                when = max(0.0, min(float(event.get("time", 0.0)), dur - 0.02))
                gain = max(0.0, min(float(event.get("gain", 0.12)), 0.5))
            except (TypeError, ValueError):
                continue
            detail = voice(event.get("voice", "bell"), note_freq(note),
                           min(1.2, max(0.25, dur - when)))
            _place(out, detail, int(when * SR), gain)
        return _edge_fade(_normalize(out, 0.55), ms=40.0)

    dur = comp.get("dur", 4.0)
    kind = comp.get("amb", "wind")
    n = int(dur * SR)
    t = np.arange(n, dtype=np.float32) / SR
    if kind == "wind":
        bed = _lowpass(_noise(dur), 500.0)
        bed *= 0.4 + 0.3 * np.sin(2 * np.pi * 0.15 * t)
    elif kind == "river":
        bed = _bandpass(_noise(dur), 600.0, 3000.0) * 0.5
        bed += _lowpass(_noise(dur), 300.0) * 0.3
    elif kind == "birds":
        bed = _lowpass(_noise(dur), 400.0) * 0.2
        for k in range(int(dur * 1.5)):
            f = 1800.0 + 1200.0 * np.random.rand()
            chirp = _v_chirp(f, 0.18)
            _place(bed, chirp, int((k / 1.5 + np.random.rand() * 0.3) * SR), 0.5)
    elif kind == "crickets":
        bed = _highpass(_noise(dur), 4000.0)
        am = (np.sin(2 * np.pi * 22.0 * t) > 0.3).astype(np.float32)
        bed *= am * 0.25
    elif kind == "purr":
        bed = _v_purr(70.0, dur)
    elif kind == "crackle":
        bed = _lowpass(_noise(dur), 250.0) * 0.3
        spk = (np.random.rand(n) < 0.0008).astype(np.float32)
        bed += spk * np.random.uniform(-0.5, 0.5, n)
    elif kind == "owl":
        bed = _lowpass(_noise(dur), 300.0) * 0.15
        for k in range(int(dur / 1.5)):
            _place(bed, _v_hoot(300.0, 0.5), int((1.5 * k + 0.5) * SR), 0.6)
    elif kind == "rain":
        bed = _bandpass(_noise(dur), 900.0, 9000.0) * 0.36
        drops = (np.random.rand(n) < 0.0016).astype(np.float32)
        bed += _lowpass(drops, 2200.0) * 0.45
    elif kind == "storm":
        bed = _lowpass(_noise(dur), 420.0) * 0.34
        rain = _bandpass(_noise(dur), 1000.0, 8500.0) * 0.20
        bed += rain
        for k in range(max(1, int(dur / 2.6))):
            start = int((0.7 + k * 2.5 + np.random.rand() * 0.5) * SR)
            thunder = _lowpass(_noise(1.2), 180.0)
            env = np.exp(-np.arange(len(thunder), dtype=np.float32) / (SR * 0.45))
            _place(bed, thunder * env, start, 0.50)
    elif kind == "ocean":
        bed = _lowpass(_noise(dur), 850.0)
        swell = 0.25 + 0.45 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t))
        foam = _highpass(_noise(dur), 2500.0) * (0.08 + 0.12 * swell)
        bed = bed * swell + foam
    elif kind == "waterfall":
        bed = _bandpass(_noise(dur), 180.0, 7000.0) * 0.48
        bed += _highpass(_noise(dur), 5200.0) * 0.14
    elif kind == "cave":
        bed = _lowpass(_noise(dur), 380.0) * 0.22
        drone = 0.12 * _sine(82.0, dur) + 0.08 * _sine(123.0, dur)
        bed += _reverb(drone, amount=0.58, decay=0.95)
    elif kind == "night_forest":
        bed = _lowpass(_noise(dur), 330.0) * 0.13
        insects = _highpass(_noise(dur), 4200.0)
        insects *= (np.sin(2 * np.pi * 18.0 * t) > 0.5).astype(np.float32) * 0.10
        bed += insects
        if dur > 2.0:
            _place(bed, _v_hoot(270.0, 0.55), int(1.2 * SR), 0.28)
    elif kind == "leaves":
        bed = _bandpass(_noise(dur), 700.0, 6500.0)
        rustle = 0.18 + 0.22 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.37 * t))
        bed *= rustle
    elif kind == "vinyl":
        bed = _highpass(_noise(dur), 1800.0) * 0.035
        pops = (np.random.rand(n) < 0.00038).astype(np.float32)
        bed += pops * np.random.uniform(-0.55, 0.55, n).astype(np.float32)
        bed += 0.035 * _sine(60.0, dur)
    elif kind == "tape":
        bed = _bandpass(_noise(dur), 500.0, 9000.0) * 0.055
        bed += 0.025 * _sine(50.0, dur)
        bed *= 0.92 + 0.08 * np.sin(2 * np.pi * 0.42 * t)
    elif kind == "city":
        bed = _lowpass(_noise(dur), 720.0) * 0.20
        bed += _bandpass(_noise(dur), 900.0, 2800.0) * 0.07
        for k in range(max(1, int(dur / 1.7))):
            f = 280.0 + 90.0 * np.random.rand()
            honk = _sine(f, 0.18) * adsr(int(0.18 * SR), 0.01, 0.04, 0.5, 0.09)
            _place(bed, honk, int((0.5 + k * 1.7) * SR), 0.10)
    elif kind == "train":
        bed = _lowpass(_noise(dur), 420.0) * 0.22
        rumble = 0.16 * _sine(48.0, dur) + 0.10 * _sine(72.0, dur)
        rhythm = 0.55 + 0.45 * (np.sin(2 * np.pi * 2.2 * t) > 0.2)
        bed += rumble * rhythm.astype(np.float32)
    elif kind == "clock":
        bed = _lowpass(_noise(dur), 320.0) * 0.035
        for k in range(int(dur * 2)):
            _place(bed, _d_tick(), int(k * 0.5 * SR), 0.32 if k % 2 else 0.45)
    elif kind == "underwater":
        bed = _lowpass(_noise(dur), 520.0) * 0.26
        bed += 0.12 * _sine(96.0, dur) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.17 * t))
        for k in range(max(1, int(dur / 1.3))):
            _place(bed, _d_water_drop(), int((0.4 + k * 1.3) * SR), 0.16)
    elif kind == "snow":
        bed = _highpass(_noise(dur), 5200.0) * 0.055
        sparkle = (np.random.rand(n) < 0.0005).astype(np.float32)
        bed += _lowpass(sparkle, 6800.0) * 0.28
    elif kind == "bees":
        bed = _lowpass(_noise(dur), 300.0) * 0.06
        buzz = 0.10 * _sine(142.0, dur) + 0.07 * _sine(173.0, dur)
        buzz *= 0.7 + 0.3 * np.sin(2 * np.pi * 0.8 * t)
        bed += buzz
    elif kind == "distant_bells":
        bed = _lowpass(_noise(dur), 420.0) * 0.07
        notes = ("C5", "G5", "E5", "A5")
        for k in range(max(1, int(dur / 1.2))):
            bell = voice("bell", note_freq(notes[k % len(notes)]), 0.8)
            _place(bed, bell, int((0.35 + k * 1.2) * SR), 0.17)
        bed = _reverb(bed, amount=0.42, decay=0.78)
    elif kind == "drone":
        bed = (0.24 * _sine(65.4, dur) + 0.16 * _sine(98.0, dur)
               + 0.10 * _sine(130.8, dur))
        bed *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.12 * t)
    elif kind == "fireplace":
        bed = _lowpass(_noise(dur), 300.0) * 0.18
        crack = (np.random.rand(n) < 0.0012).astype(np.float32)
        bed += crack * np.random.uniform(-0.7, 0.7, n).astype(np.float32)
    elif kind == "meadow_night":
        bed = _lowpass(_noise(dur), 380.0) * 0.10
        insects = _highpass(_noise(dur), 4600.0)
        insects *= (np.sin(2 * np.pi * 20.0 * t) > 0.55).astype(np.float32) * 0.08
        bed += insects
    elif kind == "space":
        bed = 0.12 * _sine(55.0, dur) + 0.08 * _sine(82.5, dur)
        bed += _lowpass(_noise(dur), 250.0) * 0.08
        bed = _phaser(bed.astype(np.float32), rate=0.12, depth=0.65)
    elif kind == "heartbeat":
        bed = _lowpass(_noise(dur), 260.0) * 0.04
        beat = _d_kick(dur=0.22, f0=88.0, f1=46.0)
        for k in range(max(1, int(dur / 0.9))):
            off = int(k * 0.9 * SR)
            _place(bed, beat, off, 0.34)
            _place(bed, beat, off + int(0.19 * SR), 0.24)
    else:
        bed = _lowpass(_noise(dur), 600.0) * 0.4
    bed = _edge_fade(bed.astype(np.float32), ms=40.0)
    return _normalize(bed, 0.55)


# ---------------------------------------------------------------------------
# Public: one component -> mono float buffer
# ---------------------------------------------------------------------------
def _seed_from(comp):
    s = str(comp.get("id", "x"))
    h = 2166136261
    for ch in s:
        h = (h ^ ord(ch)) * 16777619 & 0xFFFFFFFF
    return h


def render_component(comp, bpm=100.0):
    """Public render: deterministic per component and safe across threads.

    A few legacy synthesis helpers use NumPy's process-global RNG.  Export may
    run in a worker while the player previews another sound, so seed/render/
    restore is protected as one critical section.  This preserves deterministic
    ComponentDNA audio without allowing two concurrent renders to corrupt each
    other's noise state.
    """
    with _RENDER_LOCK:
        state = np.random.get_state()
        np.random.seed(_seed_from(comp))
        try:
            return _render_component_inner(comp, bpm)
        finally:
            np.random.set_state(state)


def _render_component_inner(comp, bpm=100.0):
    typ = comp.get("type", "note")
    if typ == "note":
        dur = comp.get("dur", 1.3)
        notes = comp.get("notes") or ["C4"]
        buf = _component_tone(comp, note_freq(notes[0]), dur)
    elif typ == "chord":
        dur = comp.get("dur", 1.8)
        if comp.get("notes"):
            freqs = [note_freq(n) for n in comp["notes"]]
        else:
            freqs = chord_freqs(comp.get("root", "C"), comp.get("quality", "major"),
                                comp.get("octave", 4))
        strum = max(0.0, min(float(comp.get("strum_ms", 12.0)), 80.0)) / 1000.0
        direction = comp.get("strum_direction", "up")
        buf = np.zeros(int((dur + strum * max(0, len(freqs) - 1)) * SR), dtype=np.float32)
        ordered = list(freqs) if direction != "down" else list(reversed(freqs))
        for i, f in enumerate(ordered):
            snd = _component_tone(comp, f, dur)
            _place(buf, snd, int(i * strum * SR), 0.78 / max(1.0, len(freqs) ** 0.25))
        buf = _normalize(buf, 0.85)
    elif typ == "drum":
        buf = _component_drum(comp, comp.get("drum", "kick"))
    elif typ == "rhythm":
        buf = render_rhythm(comp, bpm)
    elif typ == "loop":
        buf = render_loop(comp, bpm)
    elif typ == "ambience":
        buf = render_ambience(comp)
    elif typ == "effect":
        buf = _effect_demo(comp)
    elif typ == "user":
        buf = comp.get("_buffer")
        if buf is None:
            buf = np.zeros(int(0.5 * SR), dtype=np.float32)
    else:
        buf = voice("music_box", note_freq("C4"), 1.0)

    for fx in comp.get("effects", []):
        buf = apply_effect(buf, fx[0], fx[1] if len(fx) > 1 else None)
    return _edge_fade(buf.astype(np.float32), ms=5.0)


def _effect_demo(comp):
    """Preview an effect by applying it to a short bell motif."""
    dur = 0.5
    motif = np.zeros(int(1.5 * SR), dtype=np.float32)
    for i, n in enumerate(["C5", "E5", "G5"]):
        _place(motif, voice("bell", note_freq(n), dur), int(i * 0.32 * SR), 0.8)
    motif = _normalize(motif, 0.8)
    return apply_effect(motif, comp.get("fx", "reverb"), comp.get("fx_params"))


def clip_length_steps(comp):
    """How many grid steps a placed clip of this component occupies."""
    typ = comp.get("type", "note")
    if typ in ("rhythm", "loop"):
        return comp.get("length_steps", STEPS_PER_BAR)
    if typ == "ambience":
        return comp.get("length_steps", STEPS_PER_BAR * 2)
    return 1


def fit_to_steps(buf, steps, bpm):
    """Tile or trim a buffer so it fills exactly ``steps`` grid steps."""
    target = int(steps * sec_per_step(bpm) * SR)
    if target <= 0:
        return buf
    if len(buf) >= target:
        return buf[:target]
    reps = int(np.ceil(target / len(buf)))
    return np.tile(buf, reps)[:target]
