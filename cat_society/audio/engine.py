"""The runtime audio engine: turns rendered float buffers into pygame Sounds
and plays them, with graceful fall-back to silent mode if no audio device is
available (so the game still runs on a headless box).

Two jobs:

* **Preview** a single component when the cat collects it or when the player
  clicks it in the Music Maker browser.  Preview renders are cached by id.
* **Play a whole project**.  The project is rendered to one buffer by
  :mod:`cat_society.audio.export` and played as a single looping Sound, so what
  you hear is exactly what gets exported.  A wall-clock timer gives the playhead.
"""

import time

import numpy as np

try:
    import pygame
except Exception:                       # pragma: no cover
    pygame = None

from . import SR
from . import synth
from . import export
from ..logging_utils import get_logger

_LOG = get_logger("audio_engine")

try:
    from .. import settings as _settings
except Exception:                       # pragma: no cover
    _settings = None


def _music_vol():
    try:
        return _settings.music_volume() if _settings else 1.0
    except Exception:
        return 1.0


def _to_stereo_int16(buf):
    """Mono float (-1..1) -> contiguous int16 stereo array shaped (n, 2)."""
    if buf is None or len(buf) == 0:
        buf = np.zeros(1, dtype=np.float32)
    buf = np.clip(buf, -1.0, 1.0)
    i16 = (buf * 32767.0).astype(np.int16)
    return np.ascontiguousarray(np.column_stack([i16, i16]))


# how world sounds fade with distance from Bal: full and warm up close,
# a smooth slope through the middle, gone past the far edge.
HEAR_NEAR = 170.0
HEAR_FAR = 820.0


def hearing(dist):
    """0..1 loudness for a world sound `dist` away from Bal."""
    if dist <= HEAR_NEAR:
        return 1.0
    if dist >= HEAR_FAR:
        return 0.0
    k = (dist - HEAR_NEAR) / (HEAR_FAR - HEAR_NEAR)
    return (1.0 - k) ** 1.7


class AudioEngine:
    def __init__(self):
        self.ok = False
        self._preview_cache = {}        # comp_id -> pygame.Sound
        self._music_sound = None
        self._music_started = 0.0
        self._music_len = 0.0
        self._music_loop = False
        self._preview_ch = None
        self._music_ch = None
        self._sprout_pool = []
        self._sprout_next = 0
        self._gramo_ch = None

        if pygame is None:
            return
        try:
            pygame.mixer.pre_init(SR, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(16)
            # reserve two channels so previews never cut the song and vice-versa
            self._preview_ch = pygame.mixer.Channel(0)
            self._music_ch = pygame.mixer.Channel(1)
            # a small polyphony pool for garden sprouts (world sound emitters),
            # plus one looping channel for the nearest gramophone
            self._sprout_pool = [pygame.mixer.Channel(i) for i in range(2, 8)]
            self._sprout_next = 0
            self._gramo_ch = pygame.mixer.Channel(8)
            self.ok = True
        except Exception:
            # no audio device (headless / CI) -- run silent but never crash
            self.ok = False
            _LOG.info("Audio mixer is unavailable; continuing in silent mode", exc_info=True)

    # -- component preview --------------------------------------------------
    def preview_component(self, comp, bpm=100):
        """Render (or reuse) a component and play it once on the preview channel."""
        if not self.ok or comp is None:
            return
        cid = comp.get("id")
        snd = self._preview_cache.get(cid)
        if snd is None:
            try:
                buf = synth.render_component(comp, bpm=bpm)
            except Exception:
                return
            snd = pygame.sndarray.make_sound(_to_stereo_int16(buf))
            self._preview_cache[cid] = snd
        try:
            self._preview_ch.stop()
            self._preview_ch.set_volume(_music_vol())
            self._preview_ch.play(snd)
        except Exception:
            pass

    def preview_buffer(self, buf):
        """Play a raw mono float buffer once (used for user samples)."""
        if not self.ok or buf is None or len(buf) == 0:
            return
        try:
            snd = pygame.sndarray.make_sound(_to_stereo_int16(buf))
            self._preview_ch.stop()
            self._preview_ch.play(snd)
        except Exception:
            pass

    def invalidate(self, comp_id=None):
        """Drop a cached preview (or all of them) -- e.g. after a tempo change."""
        if comp_id is None:
            self._preview_cache.clear()
        else:
            self._preview_cache.pop(comp_id, None)

    # -- garden sprouts -------------------------------------------------------

    # doppler is three gentle buckets, cached per component: a sound moving
    # toward Bal rings a shade brighter, moving away a shade lower.
    _PITCHES = {-1: 0.962, 0: 1.0, 1: 1.042}

    def _sprout_sound(self, comp, bpm, bucket):
        cid = (comp.get("id"), bucket)
        snd = self._preview_cache.get(cid)
        if snd is None:
            try:
                buf = synth.render_component(comp, bpm=bpm)
            except Exception:
                return None
            f = self._PITCHES.get(bucket, 1.0)
            if f != 1.0:
                import numpy as _np
                idx = _np.arange(0, len(buf) - 1, f)
                buf = buf[idx.astype(_np.int32)]
            snd = pygame.sndarray.make_sound(_to_stereo_int16(buf))
            self._preview_cache[cid] = snd
        return snd

    def trigger_sprout(self, comp, vol=1.0, bpm=104, pan=0.5, doppler=0):
        """Fire one sprout's sound on the polyphony pool, panned in place.

        Unlike previews this never steals a busy voice mid-ring: the pool is
        round-robin, so a whole row of bells can overlap into a phrase."""
        if not self.ok or comp is None:
            return
        snd = self._sprout_sound(comp, bpm, int(doppler))
        if snd is None:
            return
        try:
            ch = self._sprout_pool[self._sprout_next]
            self._sprout_next = (self._sprout_next + 1) % len(self._sprout_pool)
            v = _music_vol() * max(0.0, min(1.0, vol))
            p = max(0.0, min(1.0, pan))
            ch.set_volume(v * min(1.0, 2.0 * (1.0 - p)),
                          v * min(1.0, 2.0 * p))
            ch.play(snd)
        except Exception:
            pass

    # -- gramophone (a planted song looping in the world) --------------------
    def gramo_play(self, buf):
        """Loop a pre-rendered project buffer on the gramophone channel."""
        if not self.ok or buf is None or len(buf) == 0:
            return False
        try:
            snd = pygame.sndarray.make_sound(_to_stereo_int16(buf))
            self._gramo_ch.stop()
            self._gramo_ch.play(snd, loops=-1)
            return True
        except Exception:
            _LOG.exception("Could not start gramophone playback")
            return False

    def gramo_volume(self, vol, pan=0.5):
        if not self.ok:
            return
        try:
            v = _music_vol() * max(0.0, min(1.0, vol))
            p = max(0.0, min(1.0, pan))
            self._gramo_ch.set_volume(v * min(1.0, 2.0 * (1.0 - p)),
                                      v * min(1.0, 2.0 * p))
        except Exception:
            pass

    def gramo_stop(self):
        if not self.ok:
            return
        try:
            self._gramo_ch.stop()
        except Exception:
            pass

    # -- whole-project playback --------------------------------------------
    def play_project(self, project, samples=None, loop=False):
        """Render the project to one buffer and start playing it.

        Returns the buffer length in seconds (0 if nothing/no audio)."""
        self.stop_music()
        try:
            buf = export.render_project(project, loop=loop, samples=samples)
        except Exception:
            _LOG.exception("Could not render project for playback")
            return 0.0
        self._music_len = len(buf) / float(SR)
        # the grid's musical length: the audio buffer is longer (release
        # tails ring past the last bar), but the playhead lives on the grid
        spb = 60.0 / max(1, project.tempo) / synth.STEPS_PER_BEAT
        self._music_grid_len = max(0.001,
                                   project.bars * synth.STEPS_PER_BAR * spb)
        if not self.ok or self._music_len <= 0.0:
            # still report the length so a silent box can animate the playhead
            self._music_started = time.time()
            self._music_loop = loop
            self._music_sound = None
            return self._music_len
        try:
            self._music_sound = pygame.sndarray.make_sound(_to_stereo_int16(buf))
            self._music_ch.set_volume(_music_vol())
            self._music_ch.play(self._music_sound, loops=-1 if loop else 0)
        except Exception:
            self._music_sound = None
            _LOG.exception("Could not start project playback")
        self._music_started = time.time()
        self._music_loop = loop
        return self._music_len

    def stop_music(self):
        if self.ok and self._music_ch is not None:
            try:
                self._music_ch.stop()
            except Exception:
                pass
        self._music_sound = None
        self._music_len = 0.0

    def refresh_volume(self):
        """Re-apply the current music volume to the live channels."""
        if not self.ok:
            return
        try:
            if self._music_ch is not None:
                self._music_ch.set_volume(_music_vol())
            if self._preview_ch is not None:
                self._preview_ch.set_volume(_music_vol())
        except Exception:
            pass

    def shift_music_clock(self, seconds):
        """Exclude a mixer pause from playhead/end-time calculations."""
        if self._music_started > 0.0 and seconds > 0:
            self._music_started += float(seconds)

    def is_playing(self):
        if self._music_len <= 0.0:
            return False
        if self._music_loop:
            return True
        return (time.time() - self._music_started) < self._music_len

    def playhead_fraction(self):
        """Where the song is on the *grid*, 0..1.

        The rendered audio runs a little longer than the grid (tails ring
        out), so the head is timed against the musical length: it reaches
        the end exactly when the last bar ends and parks there while the
        tail fades.  Looping wraps on the grid length too."""
        g = getattr(self, "_music_grid_len", 0.0) or self._music_len
        if g <= 0.0:
            return 0.0
        elapsed = time.time() - self._music_started
        if self._music_loop:
            return (elapsed % g) / g
        return min(1.0, elapsed / g)

    def shutdown(self):
        self.stop_music()
        if self.ok:
            try:
                pygame.mixer.quit()
            except Exception:
                pass
