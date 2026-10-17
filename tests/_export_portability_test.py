"""Focused regression tests for portable, reliable WAV export."""

import glob
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from cat_society.audio import export, synth
from cat_society.components import catalog
from cat_society.music.project import Project, Track, Clip
from cat_society.screens import exporting

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print("[PASS]", label)
    else:
        print("[FAIL]", label, detail)
        FAILURES.append(label)


def first_component(track="melody"):
    return next(c for c in catalog.ALL if c.get("track") == track and c.get("type") != "effect")


def one_clip_project(comp=None):
    comp = comp or first_component("melody")
    p = Project("Export Test", tempo=100, bars=2)
    tr = Track("Test", comp["track"])
    tr.add(comp["id"], 0)
    p.tracks = [tr]
    return p


def main():
    print("\n--- Filename and path behavior ---")
    check("unsafe filename characters are removed",
          exporting.safe_filename('A:B/C*D?') == "A_B_C_D.wav")
    check("Windows reserved filenames are avoided",
          exporting.safe_filename("CON").lower() != "con.wav")

    with tempfile.TemporaryDirectory() as td:
        nested = os.path.join(td, "new", "folder", "song")
        p = one_clip_project()
        out = export.export_wav(p, out_path=nested)
        check("missing parent folders are created", os.path.isdir(os.path.dirname(out)))
        check("WAV extension is added", out.endswith(".wav"))
        check("export returns an absolute path", os.path.isabs(out))
        check("output file exists", os.path.isfile(out))
        check("transaction temp files are cleaned", not glob.glob(os.path.join(os.path.dirname(out), ".bsg-export-*")))
        with wave.open(out, "rb") as w:
            params = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes())
            raw = w.readframes(w.getnframes())
        check("WAV is standard 44.1kHz 16-bit stereo PCM",
              params[0:3] == (2, 2, synth.SR), str(params))
        pcm = np.frombuffer(raw, dtype="<i2").reshape(-1, 2)
        check("left and right channels match", np.array_equal(pcm[:, 0], pcm[:, 1]))
        check("export contains audible data", int(np.max(np.abs(pcm))) > 0)

    print("\n--- Mixer safety and fidelity ---")
    comp = first_component("melody")
    p = Project("Cache", tempo=100, bars=2)
    tr = Track("Melody", "melody")
    for step in (0, 2, 4, 6):
        tr.add(comp["id"], step)
    p.tracks = [tr]
    original_render = synth.render_component
    calls = {"n": 0}

    def counted(*args, **kwargs):
        calls["n"] += 1
        return original_render(*args, **kwargs)

    synth.render_component = counted
    try:
        mixed = export.render_project(p)
    finally:
        synth.render_component = original_render
    check("repeated components synthesize only once per mix", calls["n"] == 1, str(calls))
    check("cached mix remains audible", float(np.max(np.abs(mixed))) > 0.0)

    # Shrinking bars can leave old clips outside the visible timeline.
    p2 = one_clip_project(comp)
    p2.tracks[0].clips.append(Clip(comp["id"], 999999))
    try:
        outside = export.render_project(p2)
        outside_ok = len(outside) > 0
    except Exception as exc:
        outside_ok = False
        print("      ", exc)
    check("fully out-of-range clips cannot crash export", outside_ok)

    p3 = one_clip_project(comp)
    p3.tracks[0].clips = [Clip(comp["id"], -1)]
    try:
        negative = export.render_project(p3)
        negative_ok = np.all(np.isfinite(negative))
    except Exception:
        negative_ok = False
    check("negative/corrupt clip positions are clipped safely", negative_ok)

    print("\n--- Imported sample support ---")
    user_id = "user_export_regression"
    user_comp = dict(id=user_id, name="Imported Test", type="user", track="user",
                     rarity="common", starter=True)
    old = catalog.BY_ID.get(user_id)
    catalog.BY_ID[user_id] = user_comp
    user = np.sin(2 * np.pi * 220 * np.arange(synth.SR * 3, dtype=np.float32) / synth.SR) * 0.3
    try:
        p4 = Project("Imported", tempo=120, bars=2)
        utr = Track("Imported", "user")
        utr.add(user_id, p4.total_steps - 1)
        p4.tracks = [utr]
        with_sample = export.render_project(p4, samples={user_id: user})
        without_sample = export.render_project(p4, samples={})
        start = int((p4.total_steps - 1) * synth.sec_per_step(p4.tempo) * synth.SR)
        check("imported samples are included when buffers are supplied",
              float(np.max(np.abs(with_sample[start:]))) > 0.1)
        check("missing imported sample is skipped safely",
              float(np.max(np.abs(without_sample))) == 0.0)
        check("a final long sample is not cut to the old 1.6-second tail",
              len(with_sample) >= start + len(user))
    finally:
        if old is None:
            catalog.BY_ID.pop(user_id, None)
        else:
            catalog.BY_ID[user_id] = old

    class Registry:
        def buffers(self):
            return {"x": np.ones(4, dtype=np.float32)}
    class App:
        samples = Registry()
    check("screen helper retrieves imported sample buffers",
          "x" in exporting.sample_buffers(App()))
    check("screen helper tolerates lightweight/headless app stubs",
          exporting.sample_buffers(object()) == {})

    print("\n--- Responsive background export ---")
    original_export_wav = export.export_wav
    entered = threading.Event()
    release = threading.Event()
    captured = {}

    def delayed_export(project, samples=None, out_path=None, progress=None):
        entered.set()
        release.wait(2.0)
        captured["clips"] = project.clip_count()
        if progress:
            progress(captured["clips"], captured["clips"])
        return os.path.abspath(out_path)

    export.export_wav = delayed_export
    try:
        original = one_clip_project()
        task = exporting.start_export(original, os.path.join(tempfile.gettempdir(), "snapshot.wav"))
        entered.wait(1.0)
        original.tracks[0].add(comp["id"], 3)
        release.set()
        deadline = time.time() + 3.0
        while not task.status()["finished"] and time.time() < deadline:
            time.sleep(0.01)
        task_status = task.status()
    finally:
        export.export_wav = original_export_wav
    check("background export completes without blocking the UI thread", task_status["finished"])
    check("background export uses an immutable project snapshot", captured.get("clips") == 1, repr(captured))
    check("background export reports its destination", bool(task_status["result"]))

    # Concurrent previews/exports must not corrupt the global RNG used by a few
    # legacy synthesis helpers.
    rendered = []
    render_errors = []
    def render_same():
        try:
            rendered.append(synth.render_component(comp, bpm=111))
        except Exception as exc:
            render_errors.append(exc)
    workers = [threading.Thread(target=render_same) for _ in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    concurrent_equal = (not render_errors and len(rendered) == 6 and
                        all(np.array_equal(rendered[0], buf) for buf in rendered[1:]))
    check("concurrent synthesis remains deterministic", concurrent_equal, repr(render_errors))

    print("\n--- Atomic failure behavior ---")
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "existing.wav")
        with open(target, "wb") as f:
            f.write(b"ORIGINAL")
        original_replace = export.os.replace
        export.os.replace = lambda *_: (_ for _ in ()).throw(OSError("simulated full disk"))
        failed = False
        try:
            export.export_wav(one_clip_project(), out_path=target)
        except export.ExportError:
            failed = True
        finally:
            export.os.replace = original_replace
        with open(target, "rb") as f:
            preserved = f.read() == b"ORIGINAL"
        check("write failure is reported", failed)
        check("failed replacement preserves the previous export", preserved)
        check("failed export removes temporary files", not glob.glob(os.path.join(td, ".bsg-export-*")))

    print("\n--- Packaged location behavior ---")
    with tempfile.TemporaryDirectory() as td:
        code = (
            "import os,sys; sys.frozen=True; "
            "from cat_society import paths; "
            "print(paths.root()); print(paths.exports_dir())"
        )
        env = os.environ.copy()
        env["XDG_DATA_HOME"] = os.path.join(td, "xdg")
        env["HOME"] = os.path.join(td, "home")
        env.pop("BAL_SOUND_GARDEN_DATA_DIR", None)
        env.pop("BAL_SOUND_GARDEN_EXPORTS_DIR", None)
        proc = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(__file__)),
                              env=env, text=True, capture_output=True)
        lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
        check("simulated packaged build uses per-user data, not package root",
              proc.returncode == 0 and lines and lines[0].startswith(os.path.join(td, "xdg")),
              proc.stderr)
        check("packaged fallback export folder is writable",
              len(lines) >= 2 and os.path.isdir(lines[1]) and os.access(lines[1], os.W_OK),
              repr(lines))

    print("\n--- Export/playback identity ---")
    with tempfile.TemporaryDirectory() as td:
        p = one_clip_project()
        expected = export.render_project(p)
        out = export.export_wav(p, out_path=os.path.join(td, "identity.wav"))
        with wave.open(out, "rb") as w:
            got = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2)[:, 0]
        expected_i16 = np.rint(np.clip(expected, -1, 1) * 32767).astype("<i2")
        check("WAV payload matches the playback mixer buffer",
              np.array_equal(got, expected_i16))

    print("\n" + "=" * 58)
    if FAILURES:
        print("RESULT: %d FAILURE(S)" % len(FAILURES))
        for item in FAILURES:
            print(" -", item)
        raise SystemExit(1)
    print("RESULT: ALL EXPORT REGRESSION TESTS PASSED")


if __name__ == "__main__":
    main()
