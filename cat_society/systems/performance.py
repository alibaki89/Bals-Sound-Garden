"""Performing a song in the world -- the moment the garden gets to listen.

Press P in explore, pick one of your saved songs, and Bal sits down and plays
it right there.  While it plays:

* soft note glyphs drift up from the cat (drawn window-space, like the
  collect burst, so they stay crisp),
* every animal in earshot is offered a ``song`` context by the AI and drifts
  over to listen, bobbing on the actual beat,
* when the song ends (or the player stops it after a few bars), the nearest
  silent landmark in earshot gets to answer -- waking, or offering one warm
  nudge.  Never a grade, never a fail.

The audio path reuses :meth:`AudioEngine.play_project`, so what the garden
hears is exactly what the WAV export sounds like.
"""

import math
import random
import time

import pygame

from .. import config, ui
from ..projection import project
from ..ui.icons import draw_icon
from ..music import profile as profile_mod
from ..screens import exporting
from ..audio.synth import STEPS_PER_BAR

LISTEN_RADIUS = 640.0        # animals inside this hear the song
MIN_HEARD = 4.0              # seconds a stopped song must have played to count


class NoteFx:
    """One little note glyph drifting up from the performing cat."""

    __slots__ = ("x", "y", "t", "life", "sway", "col", "size", "drift")

    def __init__(self, x, y, col, size):
        self.x = x
        self.y = y
        self.t = 0.0
        self.life = random.uniform(1.6, 2.4)
        self.sway = random.uniform(0.0, math.tau)
        self.col = col
        self.size = size
        self.drift = random.uniform(26.0, 44.0)

    def update(self, dt):
        self.t += dt

    @property
    def done(self):
        return self.t >= self.life

    def draw(self, surf):
        k = self.t / self.life
        a = 1.0 - k * k
        px = self.x + math.sin(self.t * 2.2 + self.sway) * self.size * 0.55
        py = self.y - k * self.drift * (self.size / 14.0)
        s = int(self.size)
        icon = pygame.Surface((s * 2 + 2, s * 2 + 2), pygame.SRCALPHA)
        draw_icon(icon, s + 1, s + 1, s, self.col, style="note")
        icon.set_alpha(int(210 * a))
        surf.blit(icon, (int(px - s), int(py - s)))


_NOTE_COLS = [(255, 214, 130), (246, 176, 186), (150, 206, 224),
              (170, 214, 150), (212, 168, 236)]


class Performance:
    """Owns one performance at a time and its little cloud of note glyphs."""

    def __init__(self, app):
        self.app = app
        self.active = False
        self.project = None
        self.profile = None
        self.length = 0.0
        self.started = 0.0
        self.beat = 0.0              # quarter-note length in seconds
        self.listeners = set()       # species keys that came to listen
        self.x = 0.0                 # where in the world the song is played
        self.z = 0.0
        self._notes = []
        self._note_timer = 0.0
        self._ended = None           # set once per performance: dict result

    # -- control --------------------------------------------------------------
    def start(self, project, cat):
        self.stop(quiet=True)
        self.project = project
        self.profile = profile_mod.analyze(project)
        self.x, self.z = cat.x, cat.z
        length = self.app.engine.play_project(project, samples=exporting.sample_buffers(self.app), loop=False)
        if length <= 0.0:
            # silent box (headless) -- still animate the whole performance
            steps = project.bars * STEPS_PER_BAR
            length = steps * (60.0 / max(1, project.tempo) / 2.0) + 0.6
        self.length = length
        self.beat = 60.0 / max(1, project.tempo)
        self.started = time.time()
        self.listeners = set()
        self._notes = []
        self._note_timer = 0.0
        self._ended = None
        self.active = True
        cat.sleeping = False

    def stop(self, quiet=False):
        """Player pressed P/Esc, or the song reached its end."""
        if not self.active:
            return
        played = time.time() - self.started
        self.active = False
        try:
            self.app.engine.stop_music()
        except Exception:
            pass
        if not quiet and played >= MIN_HEARD:
            self._ended = dict(profile=self.profile,
                               song_name=self.project.name,
                               listeners=set(self.listeners),
                               x=self.x, z=self.z)

    def pop_result(self):
        """The finished performance, once, for the explore screen to judge
        the stump and the windmill listen to."""
        r, self._ended = self._ended, None
        return r

    # -- per-frame ---------------------------------------------------------------
    def elapsed(self):
        return time.time() - self.started if self.active else 0.0

    def shift_clock(self, seconds):
        """Exclude a paused interval from performance progress."""
        if self.active and seconds > 0:
            self.started += float(seconds)

    def beat_phase(self):
        """Continuous beat count; animals bob on ``sin(phase * pi)``."""
        return self.elapsed() / self.beat if self.beat > 0 else 0.0

    def song_ctx(self):
        """What the animal AI needs to know about the music in the air."""
        if not self.active:
            return None
        return dict(x=self.x, z=self.z,
                    beat=self.beat_phase(),
                    gentle=profile_mod.is_gentle(self.profile),
                    radius=LISTEN_RADIUS)

    def update(self, dt, game, window_size):
        for n in self._notes:
            n.update(dt)
        self._notes = [n for n in self._notes if not n.done]
        if not self.active:
            return
        if self.elapsed() >= self.length:
            self.stop()
            return
        # remember every animal that is actually sitting with us
        for a in game.animals.animals():
            if a.ai_state == "listen":
                self.listeners.add(a.key)
        # a new note glyph roughly every beat
        self._note_timer -= dt
        if self._note_timer <= 0.0:
            self._note_timer = self.beat * random.uniform(0.8, 1.3)
            pr = project(game.cat.x, game.cat.z, game.cam)
            if pr is not None:
                w, h = window_size
                px, py = config.canvas_to_window(
                    pr[0], pr[1] - 16 * pr[2] * config.SC)
                px += random.uniform(-10, 10)
                self._notes.append(NoteFx(px, py, random.choice(_NOTE_COLS),
                                          ui.scaled(h, random.randint(11, 16))))

    def draw_fx(self, surf):
        for n in self._notes:
            n.draw(surf)

    def progress(self):
        return min(1.0, self.elapsed() / self.length) if self.active else 0.0
