"""Light, cozy game sound effects, synthesized so the game ships no audio files.

Everything is tiny, soft and balanced.  Volumes come from
:mod:`cat_society.settings` so the player can turn them down or mute.  If no
audio device is present the module simply does nothing.
"""

import numpy as np

try:
    import pygame
except Exception:                       # pragma: no cover
    pygame = None

from . import SR
from .. import settings
import os
_ok = False
_bank = {}                 # name -> pygame.Sound
_amb_ch = None             # explore ambience loop channel
_amb_name = None
_water_ch = None           # water wading loop channel
_water_on = False
_splash_ch = None          # one-shot splash channel


# ---------------------------------------------------------------------------
# small synthesis helpers (mono float, -1..1)
# ---------------------------------------------------------------------------
def _t(dur):
    return np.linspace(0, dur, int(SR * dur), endpoint=False)


def _env(n, attack=0.005, release=0.05):
    e = np.ones(n)
    a = min(int(SR * attack), n // 2)
    r = min(int(SR * release), n - a)
    if a > 0:
        e[:a] = np.linspace(0, 1, a)
    if r > 0:
        e[n - r:] = np.linspace(1, 0, r)
    return e


def _sine(freq, dur, amp=0.5, attack=0.005, release=0.06):
    t = _t(dur)
    s = np.sin(2 * np.pi * freq * t) * amp
    return s * _env(len(s), attack, release)


def _bell(freq, dur, amp=0.5):
    """A soft bell: sine with a fast exponential decay + a quiet octave."""
    t = _t(dur)
    decay = np.exp(-t * (3.2 / dur))
    s = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2 * t)) * decay
    return s * amp * _env(len(s), 0.003, 0.02)


def _glide(f0, f1, dur, amp=0.4):
    t = _t(dur)
    k = np.linspace(f0, f1, len(t))
    phase = 2 * np.pi * np.cumsum(k) / SR
    return np.sin(phase) * amp * _env(len(t), 0.02, 0.05)


def _lowpass(x, cutoff):
    """One-pole low-pass for soft, woody textures."""
    if cutoff >= SR / 2:
        return x
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    prev = 0.0
    for i in range(len(x)):
        prev = (1 - a) * x[i] + a * prev
        y[i] = prev
    return y


def _noise(dur):
    return np.random.default_rng(1).standard_normal(int(SR * dur))


def _tick(freq, dur, cutoff, amp=0.4, noise_mix=0.5):
    n = int(SR * dur)
    rng = np.random.default_rng(int(freq) + int(dur * 1000))
    nz = rng.standard_normal(n)
    nz = _lowpass(nz, cutoff)
    t = _t(dur)
    body = np.sin(2 * np.pi * freq * t) * np.exp(-t * 30)
    s = (noise_mix * nz / (np.max(np.abs(nz)) + 1e-9) + (1 - noise_mix) * body)
    return s * amp * _env(n, 0.001, max(0.01, dur * 0.5))


def _stagger(parts, gaps):
    """Lay several mono buffers onto a timeline at the given start times (s)."""
    starts = [int(g * SR) for g in gaps]
    total = max(s + len(p) for s, p in zip(starts, parts))
    out = np.zeros(total)
    for s, p in zip(starts, parts):
        out[s:s + len(p)] += p
    return out


def _mix(*bufs):
    """Sum buffers of possibly different lengths (zero-padded to the longest)."""
    n = max(len(b) for b in bufs)
    out = np.zeros(n)
    for b in bufs:
        out[:len(b)] += b
    return out


def _to_sound(mono):
    mono = np.clip(mono, -1.0, 1.0)
    i16 = (mono * 32767.0).astype(np.int16)
    stereo = np.ascontiguousarray(np.column_stack([i16, i16]))
    return pygame.sndarray.make_sound(stereo)


# ---------------------------------------------------------------------------
# loop + filter helpers
# ---------------------------------------------------------------------------
def _bandish(x, lo, hi):
    """Crude band-pass (difference of two one-pole low-passes)."""
    return _lowpass(x, hi) - _lowpass(x, lo)


def _loop_seamless(seg, xf):
    """Return a buffer that loops with no audible seam.

    ``seg`` is a continuous signal of length L+xf.  We keep the first L samples
    but blend the head with the segment just past L, so wrapping from the end
    back to the start lands on a continuous part of the signal."""
    xf = int(xf)
    L = len(seg) - xf
    out = seg[:L].astype(np.float64).copy()
    w = np.linspace(0.0, 1.0, xf)
    out[:xf] = seg[:xf] * w + seg[L:L + xf] * (1.0 - w)
    return out


# ---------------------------------------------------------------------------
# the sound bank  (only the water splash is a one-shot now)
# ---------------------------------------------------------------------------
def _build_water_splash():
    """A soft, natural droplet plop -- filtered noise only, no tone or sweep."""
    dur = 0.30
    n = int(SR * dur)
    t = _t(dur)
    # mid 'plip': band-passed noise with a quick percussive decay
    rng = np.random.default_rng(11)
    drop = _bandish(rng.standard_normal(n), 350, 2300)
    drop = drop / (np.max(np.abs(drop)) + 1e-9) * np.exp(-t * 21) * 0.5
    # low body 'plop': low-passed noise, short, gives weight with no pitch
    rng2 = np.random.default_rng(5)
    low = _lowpass(rng2.standard_normal(n), 260)
    low = low / (np.max(np.abs(low)) + 1e-9) * np.exp(-t * 30) * 0.38
    return (drop + low) * _env(n, 0.001, 0.07)

def _asset_path(*parts):
    """Asset path relative to the installed package, not the launch folder."""
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(package_dir, "assets", *parts)


def _load_sound_asset(*parts):
    """Load a bundled pygame sound asset, falling back cleanly if missing."""
    if pygame is None:
        return None

    path = _asset_path(*parts)

    if not os.path.exists(path):
        return None

    try:
        return pygame.mixer.Sound(path)
    except Exception:
        return None
def _build_bank():
    # Use the bundled splash sample when present. This keeps the game portable:
    # the path is resolved from this package file, never from the terminal cwd.
    splash = _load_sound_asset("sfx", "water_splash.wav")

    if splash is None:
        splash = _to_sound(_build_water_splash())  # safe synthesized fallback

    return {"water_splash": splash}

def _build_ambience():
    """A gentle, faintly shimmery meadow bed that loops seamlessly."""
    L = int(SR * 6.0)
    xf = int(SR * 1.0)
    n = L + xf
    t = np.arange(n) / SR
    drone = (0.5 * np.sin(2 * np.pi * 110 * t) + 0.3 * np.sin(2 * np.pi * 165 * t))
    drone *= 0.10 * (0.8 + 0.2 * np.sin(2 * np.pi * 0.1 * t))
    rng = np.random.default_rng(7)
    wind = _lowpass(rng.standard_normal(n), 600)
    wind = wind / (np.max(np.abs(wind)) + 1e-9) * 0.05
    wind *= (0.6 + 0.4 * np.sin(2 * np.pi * 0.07 * t + 1.0))
    shimmer = (np.sin(2 * np.pi * 1568 * t) + 0.6 * np.sin(2 * np.pi * 2093 * t))
    shimmer *= 0.012 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.13 * t))
    bed = drone + wind + shimmer
    return _to_sound(_loop_seamless(bed, xf) * 0.9)


def _build_water_loop():
    """A soft, gentle wading loop -- layered filtered noise that laps quietly."""
    L = int(SR * 4.0)
    xf = int(SR * 0.8)
    n = L + xf
    t = np.arange(n) / SR
    # mid movement layer + a softer low body layer, both just shaped noise
    rng = np.random.default_rng(21)
    mid = _bandish(rng.standard_normal(n), 300, 1200)
    mid = mid / (np.max(np.abs(mid)) + 1e-9)
    rng2 = np.random.default_rng(8)
    low = _lowpass(rng2.standard_normal(n), 480)
    low = low / (np.max(np.abs(low)) + 1e-9)
    # two slow, out-of-phase swells so it sounds like lapping, not a steady hiss
    s1 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.6 * t) * np.sin(2 * np.pi * 0.19 * t + 0.5)
    s2 = 0.5 + 0.5 * np.sin(2 * np.pi * 0.31 * t + 1.7)
    water = mid * (0.035 + 0.028 * s1) + low * (0.03 + 0.024 * s2)
    return _to_sound(_loop_seamless(water, xf))


# ---------------------------------------------------------------------------
# public api
# ---------------------------------------------------------------------------
def init():
    global _ok, _bank, _amb_ch, _water_ch, _splash_ch
    if pygame is None:
        return
    try:
        if pygame.mixer.get_init() is None:
            return
        # channels 0/1 are reserved by the engine (preview/music); use higher
        base = 8
        pygame.mixer.set_num_channels(base + 6)
        _amb_ch = pygame.mixer.Channel(base + 5)
        _water_ch = pygame.mixer.Channel(base + 4)
        _splash_ch = pygame.mixer.Channel(base + 3)
        _bank = _build_bank()
        _bank["_ambience"] = _build_ambience()
        _bank["_water"] = _build_water_loop()
        _ok = True
    except Exception:
        _ok = False


def play(name, vol=1.0):
    """UI / game one-shot sounds are intentionally disabled now -- this is a
    no-op so any remaining call sites stay silent.  Component previews come
    from the audio engine, and water/ambience use their own functions below."""
    return


def paw():
    pass        # pawstep sounds were removed; kept as a no-op for safety


# -- explore ambience ---------------------------------------------------
def start_ambience(name="_ambience", vol=0.7):
    global _amb_name
    if not _ok or _amb_ch is None:
        return
    snd = _bank.get(name)
    if snd is None:
        return
    if _amb_name == name and _amb_ch.get_busy():
        refresh_ambience(vol)
        return
    try:
        snd.set_volume(settings.sfx_volume() * vol)
        _amb_ch.play(snd, loops=-1)
        _amb_name = name
    except Exception:
        pass


def refresh_ambience(vol=0.7):
    if _ok and _amb_ch is not None and _amb_name:
        try:
            _bank[_amb_name].set_volume(settings.sfx_volume() * vol)
        except Exception:
            pass


def stop_ambience():
    global _amb_name
    if _ok and _amb_ch is not None:
        try:
            _amb_ch.fadeout(300)
        except Exception:
            pass
    _amb_name = None


# -- water --------------------------------------------------------------
def splash(vol=0.7):
    if not _ok or _splash_ch is None:
        return
    snd = _bank.get("water_splash")
    if snd is None:
        return
    try:
        snd.set_volume(settings.sfx_volume() * vol)
        _splash_ch.play(snd)
    except Exception:
        pass


def start_water(vol=0.6):
    global _water_on
    if not _ok or _water_ch is None:
        return
    snd = _bank.get("_water")
    if snd is None:
        return
    if _water_on and _water_ch.get_busy():
        refresh_water(vol)
        return
    try:
        snd.set_volume(settings.sfx_volume() * vol)
        _water_ch.play(snd, loops=-1)
        _water_on = True
    except Exception:
        pass


def refresh_water(vol=0.6):
    if _ok and _water_ch is not None and _water_on:
        try:
            _bank["_water"].set_volume(settings.sfx_volume() * vol)
        except Exception:
            pass


def stop_water():
    global _water_on
    if _ok and _water_ch is not None:
        try:
            _water_ch.fadeout(250)
        except Exception:
            pass
    _water_on = False
