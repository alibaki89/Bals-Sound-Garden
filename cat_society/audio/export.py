"""Project mixing and robust WAV export.

The Music Maker playback engine and the file exporter both call
:func:`render_project`, so the exported song remains identical to playback.
File writing is deliberately portable and transactional: the destination
folder is created when possible, audio is written to a temporary sibling file,
and the completed WAV atomically replaces the target.
"""

import os
import tempfile
import wave
from collections import OrderedDict

import numpy as np

from . import legato
from . import synth
from .synth import SR
from ..components import catalog

DEFAULT_TAIL_SECONDS = 1.6
MAX_TAIL_SECONDS = 12.0
MAX_RENDER_SECONDS = 15.0 * 60.0   # protects against corrupted save files
WRITE_CHUNK_FRAMES = 65536


class ExportError(RuntimeError):
    """A user-facing rendering or file-writing failure."""


def _component_buffer(comp, bpm, length_steps):
    buf = synth.render_component(comp, bpm=bpm)
    if comp.get("type") == "ambience":
        buf = synth.fit_to_steps(buf, length_steps, bpm)
    return np.asarray(buf, dtype=np.float32)


def _safe_float(value, default, lo=None, hi=None):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = float(default)
    if not np.isfinite(value):
        value = float(default)
    if lo is not None:
        value = max(float(lo), value)
    if hi is not None:
        value = min(float(hi), value)
    return value


def _effect_key(effect):
    if effect is None:
        return None
    # repr is deterministic for the data-only dict/list/number structures used
    # by curated and ComponentDNA effects, and avoids requiring hashable params.
    return (effect.get("id"), effect.get("fx", "reverb"),
            repr(effect.get("fx_params")))


def _cache_get(cache, key):
    value = cache.get(key)
    if value is not None:
        cache.move_to_end(key)
    return value


def _cache_put(cache, key, value, limit):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > limit:
        cache.popitem(last=False)


def _grow_mix_buffer(song, required, maximum):
    """Grow in one-second blocks, bounded by the allowed tail."""
    required = min(int(required), int(maximum))
    if required <= len(song):
        return song
    target = min(int(maximum), max(required, len(song) + SR))
    grown = np.zeros(target, dtype=np.float32)
    grown[:len(song)] = song
    return grown


def _resolve_phrases(track, samples):
    """Turn a track's phrase references into renderable (comp, step) lists.

    Members whose component vanished (or whose imported buffer is missing)
    drop out; anything left with fewer than two members falls back to the
    ordinary independent-clip path, so damaged data degrades gracefully
    instead of failing.  Returns (phrases, member_key_set).
    """
    phrases = []
    member_keys = set()
    clip_keys = {(c.comp_id, c.step) for c in getattr(track, "clips", []) or []}
    for refs in getattr(track, "phrases", []) or []:
        members = []
        for ref in refs:
            try:
                cid, step = ref[0], int(ref[1])
            except (TypeError, ValueError, IndexError):
                continue
            if (cid, step) not in clip_keys:
                continue
            comp = catalog.get(cid)
            if comp is None:
                continue
            if comp.get("type") == "user":
                buf = (samples or {}).get(cid)
                if buf is None:
                    continue
                comp = dict(comp)
                comp["_buffer"] = buf
            members.append((comp, step))
        if len(members) >= 2:
            members.sort(key=lambda m: m[1])
            phrases.append(members)
            member_keys.update((c.get("id"), s) for c, s in members)
    return phrases, member_keys


def render_project(project, loop=False, samples=None, progress=None):
    """Mix a project into a mono ``float32`` buffer.

    ``samples`` is an optional ``{component_id: float_buffer}`` mapping for
    imported sounds. ``progress(done, total)`` is optional and never required by
    the game UI. Repeated sounds are cached in a bounded LRU; unique sounds are
    mixed and released immediately so dense songs remain safe on modest RAM.
    """
    samples = samples or {}
    bpm = _safe_float(getattr(project, "tempo", 100), 100, 40, 300)
    total_steps = max(1, int(getattr(project, "total_steps", 1)))
    sps = synth.sec_per_step(bpm)
    loop_len = max(1, int(total_steps * sps * SR))
    if loop_len / float(SR) > MAX_RENDER_SECONDS:
        raise ExportError("Song is too long to render safely")

    tracks = list(getattr(project, "tracks", []) or [])
    total_clips = sum(len(getattr(t, "clips", []) or [])
                      for t in tracks if not getattr(t, "muted", False))
    completed = 0

    # Bounded caches give the common repeated-loop case its large speedup but
    # cannot retain an arrangement's entire unique sound library in RAM.
    component_cache = OrderedDict()
    effected_cache = OrderedDict()
    component_cache_limit = 64
    effect_cache_limit = 32

    initial_end = loop_len + int(DEFAULT_TAIL_SECONDS * SR)
    max_render_end = loop_len + int(MAX_TAIL_SECONDS * SR)
    song = np.zeros(max(1, initial_end), dtype=np.float32)
    actual_end = initial_end

    for track in tracks:
        if getattr(track, "muted", False):
            continue
        effect = catalog.get(getattr(track, "effect_id", None)) if getattr(track, "effect_id", None) else None
        effect_key = _effect_key(effect)
        gain = _safe_float(getattr(track, "volume", 0.85), 0.85, 0.0, 1.5)
        phrases, phrase_member_keys = _resolve_phrases(track, samples)

        for clip in list(getattr(track, "clips", []) or []):
            comp_id = getattr(clip, "comp_id", None)
            if (comp_id, getattr(clip, "step", None)) in phrase_member_keys:
                continue                      # rendered as part of its phrase
            completed += 1
            comp = catalog.get(comp_id)
            if comp is None:
                if progress:
                    progress(completed, total_clips)
                continue

            try:
                step = int(getattr(clip, "step", 0))
            except (TypeError, ValueError):
                step = 0
            offset = int(step * sps * SR)
            # A project can retain clips beyond its new end after Bars -.
            if offset >= max_render_end:
                if progress:
                    progress(completed, total_clips)
                continue

            steps = max(1, int(synth.clip_length_steps(comp)))
            cache_key = (comp_id, round(bpm, 6), steps)
            if comp.get("type") == "user":
                user_buf = samples.get(comp_id)
                if user_buf is None:
                    if progress:
                        progress(completed, total_clips)
                    continue
                cache_key = (comp_id, round(bpm, 6), steps, id(user_buf))

            buf = _cache_get(component_cache, cache_key)
            if buf is None:
                render_comp = comp
                if comp.get("type") == "user":
                    render_comp = dict(comp)
                    render_comp["_buffer"] = samples.get(comp_id)
                try:
                    buf = _component_buffer(render_comp, bpm, steps)
                except Exception as exc:
                    raise ExportError("Could not render '%s': %s" %
                                      (comp.get("name", comp_id), exc)) from exc
                if buf.ndim != 1:
                    buf = np.ravel(buf).astype(np.float32)
                if not np.all(np.isfinite(buf)):
                    buf = np.nan_to_num(buf, nan=0.0, posinf=1.0,
                                        neginf=-1.0).astype(np.float32)
                _cache_put(component_cache, cache_key, buf, component_cache_limit)

            if effect is not None:
                fx_cache_key = (cache_key, effect_key)
                effected = _cache_get(effected_cache, fx_cache_key)
                if effected is None:
                    try:
                        effected = synth.apply_effect(
                            buf, effect.get("fx", "reverb"), effect.get("fx_params"))
                    except Exception as exc:
                        raise ExportError("Could not apply '%s': %s" %
                                          (effect.get("name", "track effect"), exc)) from exc
                    effected = np.asarray(effected, dtype=np.float32)
                    if not np.all(np.isfinite(effected)):
                        effected = np.nan_to_num(
                            effected, nan=0.0, posinf=1.0,
                            neginf=-1.0).astype(np.float32)
                    _cache_put(effected_cache, fx_cache_key, effected,
                               effect_cache_limit)
                buf = effected

            if offset < max_render_end and offset + len(buf) > 0:
                desired_end = min(max_render_end, max(0, offset + len(buf)))
                song = _grow_mix_buffer(song, desired_end, max_render_end)
                actual_end = max(actual_end, desired_end)
                synth._place(song, buf, offset, gain)
            if progress:
                progress(completed, total_clips)

        for members in phrases:
            completed += len(members)
            first_step, _ = legato.phrase_span_steps(members)
            offset = int(first_step * sps * SR)
            if offset >= max_render_end:
                if progress:
                    progress(completed, total_clips)
                continue
            try:
                buf = legato.render_phrase(members, bpm=bpm, samples=samples)
            except Exception as exc:
                name = members[0][0].get("name", members[0][0].get("id"))
                raise ExportError("Could not render the phrase starting with "
                                  "'%s': %s" % (name, exc)) from exc
            if buf.ndim != 1:
                buf = np.ravel(buf).astype(np.float32)
            if not np.all(np.isfinite(buf)):
                buf = np.nan_to_num(buf, nan=0.0, posinf=1.0,
                                    neginf=-1.0).astype(np.float32)
            if effect is not None:
                fx_cache_key = (legato.cache_key(members, bpm, samples), effect_key)
                effected = _cache_get(effected_cache, fx_cache_key)
                if effected is None:
                    try:
                        effected = synth.apply_effect(
                            buf, effect.get("fx", "reverb"), effect.get("fx_params"))
                    except Exception as exc:
                        raise ExportError("Could not apply '%s': %s" %
                                          (effect.get("name", "track effect"), exc)) from exc
                    effected = np.asarray(effected, dtype=np.float32)
                    if not np.all(np.isfinite(effected)):
                        effected = np.nan_to_num(
                            effected, nan=0.0, posinf=1.0,
                            neginf=-1.0).astype(np.float32)
                    _cache_put(effected_cache, fx_cache_key, effected,
                               effect_cache_limit)
                buf = effected
            if offset + len(buf) > 0:
                desired_end = min(max_render_end, max(0, offset + len(buf)))
                song = _grow_mix_buffer(song, desired_end, max_render_end)
                actual_end = max(actual_end, desired_end)
                synth._place(song, buf, offset, gain)
            if progress:
                progress(completed, total_clips)

    song = song[:max(1, actual_end)]
    if loop and loop_len > 0 and len(song) > loop_len:
        overhang = song[loop_len:].copy()
        song = song[:loop_len]
        # Fold every tail segment, not just the first lap. This matters when a
        # long generated release exceeds a short two-bar loop.
        for start in range(0, len(overhang), loop_len):
            chunk = overhang[start:start + loop_len]
            song[:len(chunk)] += chunk

    if not np.all(np.isfinite(song)):
        song = np.nan_to_num(song, nan=0.0, posinf=1.0,
                             neginf=-1.0).astype(np.float32)

    # Gentle master: preserve dynamics and only prevent digital clipping.
    peak = float(np.max(np.abs(song))) if song.size else 0.0
    if peak > 0.98:
        song *= 0.98 / peak
    return song.astype(np.float32, copy=False)

def _normalise_output_path(out_path):
    if out_path is None:
        raise ExportError("No export destination was selected")
    try:
        path = os.path.abspath(os.path.expanduser(os.fspath(out_path)))
    except TypeError as exc:
        raise ExportError("Invalid export destination") from exc
    if not path.lower().endswith(".wav"):
        path += ".wav"
    parent = os.path.dirname(path) or os.getcwd()
    try:
        os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        raise ExportError("Cannot create the export folder: %s" % exc) from exc
    if os.path.isdir(path):
        raise ExportError("The selected export destination is a folder")
    return path


def _write_stereo_frames(writer, mono):
    """Write little-endian 16-bit stereo without allocating a full copy."""
    for start in range(0, len(mono), WRITE_CHUNK_FRAMES):
        block = np.asarray(mono[start:start + WRITE_CHUNK_FRAMES], dtype=np.float32)
        block = np.nan_to_num(block, nan=0.0, posinf=1.0, neginf=-1.0)
        block = np.clip(block, -1.0, 1.0)
        i16 = np.rint(block * 32767.0).astype("<i2", copy=False)
        stereo = np.empty((len(i16), 2), dtype="<i2")
        stereo[:, 0] = i16
        stereo[:, 1] = i16
        writer.writeframesraw(stereo.tobytes(order="C"))


def export_wav(project, samples=None, out_path=None, progress=None):
    """Render *project* and atomically write a standard PCM WAV.

    Returns the absolute path. The output is 44.1 kHz, 16-bit, stereo PCM and
    therefore opens on Windows, macOS, Linux, Android, iOS and common media
    players without extra codecs.
    """
    from .. import paths

    if out_path is None:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_"
                       for c in getattr(project, "name", "song")).strip().replace(" ", "_")
        safe = safe or "song"
        out_path = os.path.join(paths.exports_dir(), "%s_%s.wav" %
                                (safe, getattr(project, "id", "song")))
    out_path = _normalise_output_path(out_path)

    mono = render_project(project, loop=False, samples=samples, progress=progress)
    parent = os.path.dirname(out_path)
    fd, temp_path = tempfile.mkstemp(prefix=".bsg-export-", suffix=".wav.tmp", dir=parent)
    os.close(fd)
    try:
        with wave.open(temp_path, "wb") as writer:
            writer.setnchannels(2)
            writer.setsampwidth(2)
            writer.setframerate(SR)
            writer.setnframes(len(mono))
            _write_stereo_frames(writer, mono)
        # Ensure data reaches the filesystem before replacing an older export.
        try:
            with open(temp_path, "rb") as finished:
                os.fsync(finished.fileno())
        except OSError:
            pass
        os.replace(temp_path, out_path)
    except (OSError, wave.Error, ValueError) as exc:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise ExportError("Could not write the WAV file: %s" % exc) from exc
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    return out_path
