"""Shared, portable WAV-export helpers for every game screen."""

import os
import re

from .. import paths

_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *("COM%d" % i for i in range(1, 10)),
    *("LPT%d" % i for i in range(1, 10)),
}


def safe_filename(name):
    """Return a cross-platform, human-readable WAV filename."""
    text = str(name or "song").strip()
    # Windows' forbidden characters are also poor filename choices elsewhere.
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", "_", text).strip(" ._")
    if not text:
        text = "song"
    if text.upper() in _WINDOWS_RESERVED:
        text = "song_" + text
    # Leave room for extensions and filesystem bookkeeping on conservative FSes.
    text = text[:120].rstrip(" ._") or "song"
    return text + ".wav"


def ensure_wav_extension(path):
    path = os.fspath(path)
    return path if path.lower().endswith(".wav") else path + ".wav"


def short_path(path):
    """A truthful, compact view of the path actually written."""
    p = os.path.abspath(path)
    if len(p) <= 64:
        return p
    return "..." + p[-61:]


def ask_save_path(default_name):
    """Open a native save dialog when Tk is available.

    Returns a chosen path, ``""`` when cancelled, or ``None`` when this device
    has no desktop dialog support. Callers then use :func:`fallback_target`.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
    except (ImportError, RuntimeError):
        return None

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
            root.update_idletasks()
        except (tk.TclError, RuntimeError):
            pass
        chosen = filedialog.asksaveasfilename(
            parent=root,
            title="Export WAV",
            defaultextension=".wav",
            initialfile=default_name,
            initialdir=paths.exports_dir(),
            filetypes=[("WAV audio", "*.wav"), ("All files", "*.*")],
        )
        return ensure_wav_extension(chosen) if chosen else ""
    except (tk.TclError, OSError, RuntimeError):
        return None
    finally:
        if root is not None:
            try:
                root.destroy()
            except (tk.TclError, RuntimeError):
                pass


def fallback_target(default_name):
    """Writable destination used on devices without a native file dialog."""
    return os.path.join(paths.exports_dir(), safe_filename(
        os.path.splitext(default_name)[0]))



def sample_buffers(app):
    """Return imported-sample buffers when the host app exposes them."""
    registry = getattr(app, "samples", None)
    getter = getattr(registry, "buffers", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return {}
    return {}

def friendly_error(exc):
    """Keep technical export errors understandable in the compact game toast."""
    msg = str(exc).strip() or exc.__class__.__name__
    low = msg.lower()
    if "permission" in low or "access is denied" in low:
        return "No permission to write there. Choose another folder."
    if "no space" in low or "disk full" in low:
        return "The device does not have enough free storage."
    if "read-only" in low:
        return "That location is read-only. Choose another folder."
    if len(msg) > 120:
        msg = msg[:117] + "..."
    return msg

# ---------------------------------------------------------------------------
# Responsive background rendering
# ---------------------------------------------------------------------------

import copy
import threading


class ExportTask:
    """Thread-safe snapshot export used by the two music screens.

    The project is deep-copied before the worker starts, so the player can keep
    editing without changing the song halfway through a file. Sample arrays are
    immutable registry buffers and are shallow-copied through ``dict``.
    """

    def __init__(self, project, path, samples=None):
        self.project = copy.deepcopy(project)
        self.path = path
        self.samples = dict(samples or {})
        self.done = 0
        self.total = sum(len(getattr(t, "clips", []) or [])
                         for t in getattr(self.project, "tracks", [])
                         if not getattr(t, "muted", False))
        self.result = None
        self.error = None
        self.finished = False
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run,
                                        name="BalSoundGarden-WAV-Export",
                                        daemon=True)

    def start(self):
        self._thread.start()
        return self

    def _progress(self, done, total):
        with self._lock:
            self.done = int(done)
            self.total = int(total)

    def _run(self):
        try:
            from ..audio import export
            result = export.export_wav(self.project, samples=self.samples,
                                       out_path=self.path, progress=self._progress)
            with self._lock:
                self.result = result
        except Exception as exc:
            with self._lock:
                self.error = exc
        finally:
            with self._lock:
                self.finished = True

    def status(self):
        with self._lock:
            return {
                "done": self.done,
                "total": self.total,
                "result": self.result,
                "error": self.error,
                "finished": self.finished,
            }


def start_export(project, path, samples=None):
    return ExportTask(project, path, samples=samples).start()
