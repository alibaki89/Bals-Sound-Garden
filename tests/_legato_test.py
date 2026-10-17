"""Regressions for connected phrases (legato) in the Music Maker.

Covers the audio contract (one attack, continuous body, one release, per
family behaviour), the mouse/keyboard workflow through real pygame events,
persistence, healing, determinism and WAV export, plus full backward
compatibility with plain v24 projects.
"""
import os
import tempfile

_TMP_DATA = tempfile.mkdtemp(prefix="bsg-legato-test-")
os.environ["BAL_SOUND_GARDEN_DATA_DIR"] = _TMP_DATA
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
import traceback

import numpy as np
import pygame

FAILS = []


def check(label, condition):
    tag = "PASS" if condition else "FAIL"
    print(f"[{tag}] {label}")
    if not condition:
        FAILS.append(label)


# --------------------------------------------------------------------------
# signal helpers
# --------------------------------------------------------------------------
SR = 44100


def rmsw(buf, w=0.03):
    n = max(8, int(w * SR))
    return np.sqrt(np.convolve(buf.astype(np.float64) ** 2,
                               np.ones(n) / n, mode="same"))


def onset_count(buf, span_s):
    """Attacks = threshold crossings of the RMS envelope with re-arming."""
    r = rmsw(buf)
    body = r[int(0.2 * SR):int(span_s * SR)]
    if not len(body):
        return 0
    th = 0.5 * np.median(body)
    count, armed = 0, True
    for v in r[:int(span_s * SR)]:
        if armed and v > th:
            count, armed = count + 1, False
        elif v < th * 0.35:
            armed = True
    return count


def fft_peak_hz(seg):
    seg = seg * np.hanning(len(seg))
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1.0 / SR)
    keep = freqs < 2500
    return float(freqs[keep][int(np.argmax(spec[keep]))])


def span_secs(members, bpm=100):
    from cat_society.audio import legato, synth
    _, steps = legato.phrase_span_steps(members)
    return steps * synth.sec_per_step(bpm)


def find_note(voice):
    from cat_society.components import catalog
    return next(c for c in catalog.ALL
                if c.get("type") == "note" and c.get("voice") == voice)


def variant(base, note):
    return {**base, "notes": [note], "id": base["id"] + "#" + note}


# --------------------------------------------------------------------------
# 1) the audio contract, waveform by waveform
# --------------------------------------------------------------------------
def run_waveform_tests():
    from cat_society.audio import legato, synth

    print("\n--- Sustained phrases (the core promise) ---")
    sps = synth.sec_per_step(100)
    flute = find_note("flute")

    # (1) repeated identical tiles become ONE continuous note
    legato.clear_cache()
    members = [(flute, s) for s in range(4)]
    buf = legato.render_phrase(members, bpm=100)
    span = span_secs(members)
    check("identical tiles render as a single sustained note (one onset)",
          onset_count(buf, span - 0.05) == 1)

    r = rmsw(buf)
    body = r[int(0.25 * SR):int((span - 0.05) * SR)]
    med = float(np.median(body))

    # (2) no second attack at any internal tile boundary: near a boundary,
    # energy never steps up by more than 15% of the sustain level within
    # any 20 ms window (the real attack rises by ~100%)
    h = int(0.02 * SR)
    worst_rise = 0.0
    for b in (1, 2, 3):
        t = b * sps
        seg = r[int((t - 0.06) * SR):int((t + 0.06) * SR) + h]
        worst_rise = max(worst_rise, float((seg[h:] - seg[:-h]).max()))
    check("no new attack transient at tile boundaries",
          worst_rise < 0.15 * med)

    # (3) energy stays stable across every boundary (no dips, no bumps)
    stable = True
    for b in (1, 2, 3):
        t = b * sps
        seg = r[int((t - 0.06) * SR):int((t + 0.06) * SR)]
        stable &= (seg.max() / max(seg.min(), 1e-9)) < 1.15
    check("boundary energy varies by less than 15%", stable)
    check("sustain body is flat (std under 4% of level)",
          float(body.std()) < 0.04 * med)

    # (4) a single smooth attack into the sustain plateau
    a_end = int(0.12 * SR)
    rise = r[:a_end]
    check("attack rises smoothly into the plateau",
          np.all(np.diff(rmsw(buf, 0.05)[:a_end][::220]) > -0.02 * med)
          and abs(r[a_end] - med) < 0.25 * med)

    # (5) exactly one release, at the very end
    check("body never decays early (no per-tile release)",
          float(body.min()) > 0.6 * med)
    tail = r[int((span + 0.6) * SR):int((span + 1.0) * SR)]
    check("one final release fades to silence", len(tail) == 0
          or float(tail.max()) < 0.05 * med)

    # (6) different pitches connect as performed legato
    seq = [(variant(flute, "C4"), 0), (variant(flute, "D4"), 2),
           (variant(flute, "E4"), 4)]
    buf2 = legato.render_phrase(seq, bpm=100)
    span2 = span_secs(seq)
    r2 = rmsw(buf2)
    body2 = r2[int(0.25 * SR):int((span2 - 0.05) * SR)]
    check("changing notes stay connected (no silence between notes)",
          float(body2.min()) > 0.5 * np.median(body2))
    check("changing notes still make one attack",
          onset_count(buf2, span2 - 0.05) == 1)
    f1 = fft_peak_hz(buf2[int(0.8 * sps * SR):int(1.6 * sps * SR)])
    f2 = fft_peak_hz(buf2[int(2.8 * sps * SR):int(3.6 * sps * SR)])
    f3 = fft_peak_hz(buf2[int(4.4 * sps * SR):int(4.9 * sps * SR)])
    check("pitch actually moves C4 -> D4 -> E4 (ratio check)",
          abs(f2 / f1 - 2 ** (2 / 12)) < 0.03
          and abs(f3 / f1 - 2 ** (4 / 12)) < 0.04)

    # loudness parity with a plain tile of the same instrument
    single = synth.render_component(flute, bpm=100)
    lone = float(rmsw(single)[int(0.4 * SR)])
    check("a connected note sits at the same loudness as a lone tile",
          abs(med - lone) < 0.25 * lone)

    # (7) different instruments morph without a gap or a restart
    brass, choir = find_note("brass"), find_note("choir")
    mem3 = [(flute, 0), (brass, 3), (choir, 6)]
    buf3 = legato.render_phrase(mem3, bpm=100)
    span3 = span_secs(mem3)
    body3 = rmsw(buf3)[int(0.3 * SR):int((span3 - 0.05) * SR)]
    check("instrument changes morph smoothly (no dropout)",
          float(body3.min()) > 0.4 * np.median(body3))
    check("instrument changes never re-attack",
          onset_count(buf3, span3 - 0.05) == 1)

    print("\n--- Ringing, percussive and textural families ---")
    from cat_society.components import catalog
    mbox = catalog.get("mb_c4")
    legato.clear_cache()
    ring = legato.render_phrase([(mbox, s) for s in (0, 1, 2, 3)], bpm=100)
    check("repeated plucks/bells merge into ONE strike",
          onset_count(ring, 4 * sps) == 1)
    rr = rmsw(ring)
    check("the merged strike keeps ringing past old tile boundaries",
          float(rr[int(2.5 * sps * SR)]) > 0.02 * float(rr.max()))
    ring2 = legato.render_phrase(
        [(variant(mbox, n), i * 2) for i, n in enumerate(("C4", "E4", "G4"))],
        bpm=100)
    rbody = rmsw(ring2)[int(0.05 * SR):int(5.5 * sps * SR)]
    check("changing plucked notes ring into each other",
          float(rbody.min()) > 0.03 * np.median(rbody))

    drum = next(c for c in catalog.ALL if c.get("type") == "drum")
    hits = legato.render_phrase([(drum, 0), (drum, 2), (drum, 4)], bpm=100)
    check("drums are never stretched: connected hits stay discrete",
          onset_count(hits, 5 * sps) >= 3)

    rhythm = next(c for c in catalog.ALL if c.get("type") == "rhythm")
    pat = legato.render_phrase([(rhythm, 0), (rhythm, 8)], bpm=100)
    check("rhythms connect as one continuous pattern",
          np.all(np.isfinite(pat)) and float(np.abs(pat).max()) > 0.05)

    ambs = [c for c in catalog.ALL if c.get("type") == "ambience"]
    memb = [(ambs[0], 0), (ambs[1 % len(ambs)], 16)]
    bed = legato.render_phrase(memb, bpm=100)
    spanb = span_secs(memb)
    rb = rmsw(bed, 0.1)[int(0.8 * SR):int((spanb - 0.3) * SR)]
    check("ambience beds join seamlessly", float(rb.min()) > 0.3 * np.median(rb))

    print("\n--- Imported sounds and edge cases ---")
    tone = (0.5 * np.sin(2 * np.pi * 440 *
                         np.arange(int(0.6 * SR)) / SR)).astype(np.float32)
    ucomp = {"id": "user_test", "type": "user", "track": "user", "name": "T"}
    umem = [(ucomp, 0), (ucomp, 4)]
    ub = legato.render_phrase(umem, bpm=100, samples={"user_test": tone})
    uspan = span_secs(umem)
    um = rmsw(ub)[int(0.05 * SR):int((uspan - 0.05) * SR)]
    check("imported sounds sustain safely (looped body, no dropouts)",
          float(um.min()) > 0.4 * np.median(um))
    safe = legato.render_phrase(umem, bpm=100, samples={})
    check("a missing sample buffer renders silence instead of crashing",
          isinstance(safe, np.ndarray) and np.all(np.isfinite(safe)))

    # (9) many members, mixed spacing, still one object
    big = [(variant(flute, n), s) for n, s in
           (("C4", 0), ("C4", 1), ("E4", 2), ("G4", 4), ("A4", 7))]
    bb = legato.render_phrase(big, bpm=100)
    bspan = span_secs(big)
    check("a five-tile phrase is one connected note stream",
          onset_count(bb, bspan - 0.05) == 1)
    check("phrase output is always finite and headroom-safe",
          np.all(np.isfinite(bb)) and float(np.abs(bb).max()) <= 0.95)

    procs = [c for c in (catalog.get("proc2.%d" % s) for s in range(100, 160))
             if c and c.get("type") == "note"]
    if len(procs) >= 2:
        pb = legato.render_phrase([(procs[0], 0), (procs[0], 2),
                                   (procs[1], 4)], bpm=100)
        check("procedural (DNA) instruments connect too",
              np.all(np.isfinite(pb)) and float(np.abs(pb).max()) > 0.02)
    else:
        check("procedural (DNA) instruments connect too", False)

    legato.clear_cache()
    x1 = legato.render_phrase([(flute, 0), (brass, 3)], bpm=100).copy()
    legato.clear_cache()
    x2 = legato.render_phrase([(flute, 0), (brass, 3)], bpm=100)
    check("phrase rendering is fully deterministic",
          len(x1) == len(x2) and np.array_equal(x1, x2))


# --------------------------------------------------------------------------
# 2) the Music Maker workflow through real pygame events
# --------------------------------------------------------------------------
class StubEngine:
    def __init__(self):
        self.playing = False

    def is_playing(self):
        return self.playing

    def stop_music(self):
        self.playing = False

    def play_project(self, project, samples=None, loop=False):
        self.playing = True

    def preview_component(self, comp, bpm=100):
        pass

    def invalidate(self):
        pass

    def playhead_fraction(self):
        return 0.0


class StubCollection:
    def owned_on_track(self, track):
        from cat_society.components import catalog
        return [c for c in catalog.ALL
                if c.get("starter") and c.get("track") == track]

    def owned_effects(self):
        return []

    def discovery_order(self, cid):
        return 0


class StubProjects:
    def list_projects(self):
        return []

    def save(self, project):
        return project


class StubApp:
    def __init__(self):
        self.window = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self.engine = StubEngine()
        self.collection = StubCollection()
        self.projects = StubProjects()
        self.pending_project = None
        self.goto_calls = []

    def goto(self, name):
        self.goto_calls.append(name)

    def refresh_projects(self):
        return []


def mouse_down(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=pos, button=button)


def mouse_up(pos, button=1):
    return pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=button)


def click(screen, pos):
    screen.handle_event(mouse_down(pos))
    screen.handle_event(mouse_up(pos))


def key(screen, k, uni=""):
    screen.handle_event(pygame.event.Event(pygame.KEYDOWN, key=k, unicode=uni))


def chip_center(screen, cid):
    for rect, comp_id in screen._chip_rects:
        if comp_id == cid:
            return rect.center
    raise AssertionError(f"chip {cid} is not visible")


def grid_center(screen, row, col):
    return (int(screen.grid.x + col * screen._step_w() - screen.time_scroll
                + screen._step_w() * 0.5),
            int(screen._row_y(row) + screen.row_h * 0.5))


def run_ui_tests():
    from cat_society.screens.maker import MakerScreen

    print("\n--- Connect tool: selection, edit, feedback ---")
    app = StubApp()
    m = MakerScreen(app)
    m.on_enter()
    m.draw(app.window)

    click(m, chip_center(m, "mb_c4"))
    for col in (2, 3, 4):
        click(m, grid_center(m, 0, col))
    tr = m.project.tracks[0]
    check("setup: three tiles placed", len(tr.clips) == 3)

    m.draw(app.window)
    check("the Connect chip is visible on the timeline",
          m._connect_rect is not None)
    click(m, m._connect_rect.center)
    check("clicking the chip enters Connect mode and disarms placement",
          m.connect_mode and m.armed is None)
    check("entering the tool explains itself",
          "first and last tile" in (m.message or ""))

    # (10) select a phrase by clicking its first and last tile
    click(m, grid_center(m, 0, 2))
    check("first click anchors the selection",
          m.link_anchor == 2 and m.link_track == 0)
    click(m, grid_center(m, 0, 4))
    check("second click completes the range", m.link_range == (2, 4))
    m.draw(app.window)
    check("a floating pill offers Connect / Cancel",
          any(a == "connect" for _, a in m._pill_rects)
          and any(a == "cancel" for _, a in m._pill_rects))
    key(m, pygame.K_RETURN, "\r")
    check("Enter connects the tiles into one phrase",
          len(tr.phrases) == 1 and len(tr.phrases[0]) == 3)
    check("the flash message confirms the connection",
          "Connected 3" in (m.message or ""))

    # clicking a member re-selects the phrase for editing
    click(m, grid_center(m, 0, 3))
    check("clicking a phrase selects it with its real ends",
          m.link_editing == 0 and m.link_range == (2, 4))
    m.draw(app.window)
    check("editing offers Apply / Disconnect / Cancel",
          any(a == "disconnect" for _, a in m._pill_rects))

    # (11) shorten, then extend, by moving the nearest end
    click(m, grid_center(m, 0, 3))
    check("clicking inside moves the nearest end (shorten)",
          m.link_range == (2, 3))
    key(m, pygame.K_RETURN, "\r")
    check("Apply rebuilds the shorter phrase",
          len(tr.phrases) == 1 and len(tr.phrases[0]) == 2)
    click(m, grid_center(m, 0, 2))
    click(m, grid_center(m, 0, 4))
    check("clicking outside moves the far end (extend)",
          m.link_range == (2, 4))
    key(m, pygame.K_RETURN, "\r")
    check("the phrase grows back to three tiles",
          len(tr.phrases) == 1 and len(tr.phrases[0]) == 3)

    # (12) disconnect keeps every tile in place
    click(m, grid_center(m, 0, 3))
    m.draw(app.window)
    btn = next(r for r, a in m._pill_rects if a == "disconnect")
    click(m, btn.center)
    check("Disconnect removes the phrase but keeps the tiles",
          len(tr.phrases) == 0 and len(tr.clips) == 3)
    check("disconnecting is confirmed in words",
          "disconnected" in (m.message or "").lower())

    # (13) invalid selections explain themselves
    click(m, grid_center(m, 0, 2))
    key(m, pygame.K_RETURN, "\r")
    check("connecting one tile asks for at least two",
          "at least two" in (m.message or "").lower())
    click(m, grid_center(m, 0, 2))          # same tile again -> deselect
    check("clicking the anchor again clears it",
          not m._link_selection_active())
    click(m, grid_center(m, 1, 2))
    check("starting on an empty cell asks for a tile",
          "existing tile" in (m.message or "").lower())

    key(m, pygame.K_ESCAPE)
    check("Esc leaves the Connect tool", not m.connect_mode)
    key(m, pygame.K_c, "c")
    check("C re-enters the Connect tool", m.connect_mode)
    key(m, pygame.K_c, "c")

    # normal editing still behaves exactly as before
    click(m, chip_center(m, "mb_c4"))
    before = len(tr.clips)
    click(m, grid_center(m, 0, 6))
    check("normal placement is untouched by the feature",
          len(tr.clips) == before + 1)
    tr.connect_range(2, 4)
    click(m, grid_center(m, 0, 3))
    check("normal-mode removal still works on a phrase member",
          not any(c.step == 3 for c in tr.clips))
    check("removing a middle tile heals the phrase around it",
          len(tr.phrases) == 1 and len(tr.phrases[0]) == 2)
    m.draw(app.window)


# --------------------------------------------------------------------------
# 3) persistence, healing and structure operations
# --------------------------------------------------------------------------
def run_structure_tests():
    from cat_society.audio import export
    from cat_society.music import store
    from cat_society.music.project import Project

    print("\n--- Saving, loading, duplicating, healing ---")
    flute = find_note("flute")

    p = Project("Legato Save", tempo=100, bars=2)
    mel = p.tracks[0]
    for s in (0, 2, 4, 6):
        mel.add(flute["id"], s)
    check("setup: connect_range ties four tiles",
          mel.connect_range(0, 6) == 4)

    # (14) save -> reload keeps the phrase and the sound
    a = export.render_project(p)
    check("save() writes the project", store.save(p))
    p2 = store.load(p.id)
    check("reload restores the phrase structure",
          p2 is not None and len(p2.tracks[0].phrases) == 1
          and len(p2.tracks[0].phrases[0]) == 4)
    b = export.render_project(p2)
    check("a reloaded project sounds byte-identical",
          len(a) == len(b) and np.array_equal(a, b))

    # (15) duplicating a track deep-copies its phrases
    p.duplicate_track(0)
    copy = p.tracks[1]                    # duplicates land right after the source
    check("duplicate keeps the phrase",
          len(copy.phrases) == 1 and len(copy.phrases[0]) == 4)
    copy.remove_at(0, flute["id"])
    check("edits to the copy never touch the original",
          len(copy.phrases[0]) == 3 and len(mel.phrases[0]) == 4)
    p.remove_track(1)

    # (16) deletion heals: 3 -> 2 keeps the phrase, 2 -> 1 dissolves it
    q = Project("Heal", tempo=100, bars=2)
    t = q.tracks[0]
    for s in (0, 2, 4):
        t.add(flute["id"], s)
    t.connect_range(0, 4)
    t.remove_at(2, flute["id"])
    check("removing one of three members keeps a two-tile phrase",
          len(t.phrases) == 1 and len(t.phrases[0]) == 2)
    t.remove_at(4, flute["id"])
    check("a one-tile phrase dissolves automatically",
          len(t.phrases) == 0 and len(t.clips) == 1)

    # bars reduction trims members that fell off the grid
    r = Project("Trim", tempo=100, bars=2)
    t2 = r.tracks[0]
    for s in (0, 2, 12, 14):
        t2.add(flute["id"], s)
    t2.connect_range(0, 14)
    r.bars = 1
    for track in r.tracks:
        track.trim_phrases(r.total_steps)
    check("shrinking Bars trims the phrase to surviving tiles",
          len(t2.phrases) == 1
          and all(ref[1] < r.total_steps for ref in t2.phrases[0]))

    # (20) plain v24 data (no phrase keys) loads and behaves identically
    legacy = {
        "id": "legacy01", "name": "Old Song", "tempo": 100, "bars": 2,
        "created": 0, "modified": 0,
        "tracks": [{
            "name": "Melody", "kind": "melody", "muted": False,
            "volume": 0.85, "effect_id": None,
            "clips": [[flute["id"], 0], [flute["id"], 2]],
        }],
    }
    lp = Project.from_dict(legacy)
    check("a v24 dict without phrase keys loads cleanly",
          len(lp.tracks) == 1 and len(lp.tracks[0].clips) == 2
          and lp.tracks[0].phrases == [])
    check("old projects never gain phrase keys on resave",
          "phrases" not in lp.to_dict()["tracks"][0])
    corrupt = dict(legacy)
    corrupt["tracks"] = [dict(legacy["tracks"][0],
                              phrases=[[[flute["id"], 0], ["ghost", 99]],
                                       [[flute["id"], 2]]],
                              phrases_v=1)]
    cp = Project.from_dict(corrupt)
    check("dangling or tiny phrase data heals itself on load",
          cp.tracks[0].phrases == [])


# --------------------------------------------------------------------------
# 4) full project rendering, playback/export parity
# --------------------------------------------------------------------------
def run_render_tests():
    from cat_society.audio import export, samples, synth
    from cat_society.components import catalog
    from cat_society.music.project import Project

    print("\n--- Whole-project rendering and export ---")
    flute = find_note("flute")
    drum = next(c for c in catalog.ALL if c.get("type") == "drum")

    # (8) a project with no phrases renders exactly like the singles path
    p = Project("Plain", tempo=100, bars=2)
    for s in (0, 2, 4, 6):
        p.tracks[0].add(flute["id"], s)
    for s in (0, 4, 8, 12):
        p.tracks[2].add(drum["id"], s)
    mixed = export.render_project(p)
    sps = synth.sec_per_step(p.tempo)
    ref = np.zeros(int(p.total_steps * sps * SR), dtype=np.float32)
    for tr in p.tracks:
        for c in tr.clips:
            buf = synth.render_component(catalog.get(c.comp_id), bpm=p.tempo)
            synth._place(ref, buf, int(c.step * sps * SR), tr.volume)
    peak = float(np.abs(ref).max())
    if peak > 0.98:
        ref *= 0.98 / peak
    n = min(len(mixed), len(ref))
    check("unconnected clips render byte-identically to the old algorithm",
          np.array_equal(mixed[:n], ref[:n]))

    # connect the melody -> only that line changes
    p.tracks[0].connect_range(0, 6)
    with_phrase = export.render_project(p)
    check("connecting tiles changes the mix",
          not np.array_equal(mixed[:min(len(mixed), len(with_phrase))],
                             with_phrase[:min(len(mixed), len(with_phrase))]))
    drums_only = Project.from_dict(p.to_dict())
    drums_only.tracks[0].clips = []
    drums_only.tracks[0].phrases = []
    d = export.render_project(drums_only)
    m = min(len(with_phrase), len(d))
    melody_line = with_phrase[:m] - d[:m]
    rm = rmsw(melody_line)
    body = rm[int(0.25 * SR):int((7 * sps - 0.06) * SR)]
    check("inside the mix the phrase is one continuous note region",
          float(body.min()) > 0.5 * np.median(body))
    rd = rmsw(d, 0.01)
    th = 0.3 * float(rd.max())
    hits, armed = 0, True
    for v in rd:
        if armed and v > th:
            hits, armed = hits + 1, False
        elif v < th * 0.3:
            armed = True
    check("drums in the same project are untouched by the phrase", hits >= 4)

    # (17) deterministic playback == deterministic export
    again = export.render_project(p)
    check("render_project (the playback source) is deterministic",
          len(with_phrase) == len(again)
          and np.array_equal(with_phrase, again))
    with tempfile.TemporaryDirectory() as td:
        w1 = export.export_wav(p, out_path=os.path.join(td, "a.wav"))
        w2 = export.export_wav(p, out_path=os.path.join(td, "b.wav"))
        check("two WAV exports are byte-identical",
              open(w1, "rb").read() == open(w2, "rb").read())
        import wave
        with wave.open(w1, "rb") as wf:
            frames = np.frombuffer(wf.readframes(wf.getnframes()),
                                   dtype="<i2").reshape(-1, 2)[:, 0]
        ideal = np.clip(with_phrase, -1.0, 1.0)
        ideal = np.rint(ideal * 32767.0).astype(np.int16)
        check("the WAV contains exactly the playback buffer (16-bit)",
              len(frames) == len(ideal) and np.array_equal(frames, ideal))

    seen = []
    export.render_project(p, progress=lambda d_, t_: seen.append((d_, t_)))
    total = sum(len(t.clips) for t in p.tracks)
    check("export progress counts every tile exactly once",
          seen and seen[-1] == (total, total))

    # (18) a real imported WAV in a phrase, end to end
    import wave as wv
    tone = (0.4 * np.sin(2 * np.pi * 330 *
                         np.arange(int(0.5 * SR)) / SR)).astype(np.float32)
    src = os.path.join(_TMP_DATA, "import-me.wav")
    with wv.open(src, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes((tone * 32767).astype("<i2").tobytes())
    uid = samples.import_wav(src, name="testtone")
    check("setup: sample import registers a component", uid is not None)
    up = Project("Sampled", tempo=100, bars=2)
    ut = up.add_track("melody", name="Imported")
    ut.kind = "user"
    ut.clips = []
    ut.add(uid, 0)
    ut.add(uid, 4)
    ut.connect_range(0, 4)
    ubuf = export.render_project(up, samples=samples.buffers())
    urm = rmsw(ubuf)
    mid = urm[int(0.05 * SR):int((5 * sps - 0.05) * SR)]
    check("an imported-sound phrase sustains through the full mix",
          float(mid.min()) > 0.4 * np.median(mid))
    missing = export.render_project(up, samples={})
    check("a phrase whose sample vanished degrades to silence, no crash",
          isinstance(missing, np.ndarray) and np.all(np.isfinite(missing)))

    # (19) procedural instruments connect inside a project
    proc = next((catalog.get("proc2.%d" % s) for s in range(100, 200)
                 if (catalog.get("proc2.%d" % s) or {}).get("type") == "note"),
                None)
    check("setup: a procedural note exists", proc is not None)
    if proc is not None:
        pp = Project("Proc", tempo=100, bars=2)
        pt = pp.tracks[0]
        pt.kind = proc.get("track", pt.kind)
        for s in (0, 2, 4):
            pt.add(proc["id"], s)
        pt.connect_range(0, 4)
        pbuf = export.render_project(pp)
        check("a procedural phrase renders through the project pipeline",
              np.all(np.isfinite(pbuf)) and float(np.abs(pbuf).max()) > 0.02)

    # caching: rendering one phrase does not rebuild others (bounded cache)
    from cat_society.audio import legato
    legato.clear_cache()
    export.render_project(p)
    key1 = legato.cache_key(
        [(catalog.get(r[0]), r[1]) for r in p.tracks[0].phrases[0]],
        p.tempo, None)
    check("phrase renders land in the bounded cache",
          key1 in legato._CACHE)
    before_id = id(legato._CACHE[key1])
    export.render_project(p)
    check("unchanged phrases are reused, not re-rendered",
          id(legato._CACHE[key1]) == before_id)


def main():
    pygame.init()
    try:
        run_waveform_tests()
        run_ui_tests()
        run_structure_tests()
        run_render_tests()
    except Exception:
        traceback.print_exc()
        FAILS.append("unhandled exception")
    print("\n%d checks failed" % len(FAILS))
    for f in FAILS:
        print("  -", f)
    pygame.quit()
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
