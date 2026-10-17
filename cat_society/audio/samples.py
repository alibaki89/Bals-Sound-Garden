"""Importing the player's own sounds (WAV files) as user components.

A user sample becomes a component with ``type == "user"`` so it can be placed
on the User track in the Music Maker.  The raw float buffer is cached in memory
and the WAV file is copied into ``save/samples/`` so it survives a restart.
"""

import json
import os
import shutil
import wave

import numpy as np

from . import synth
from .synth import SR
from .. import paths
from ..logging_utils import get_logger
from ..persistence import PersistenceError, atomic_write_json

_LOG = get_logger("samples")
from ..components import catalog

_INDEX = os.path.join(paths.samples_dir(), "_index.json")
_BUFFERS = {}            # comp_id -> float buffer


def _read_wav(path):
    with wave.open(path, "rb") as w:
        ch = w.getnchannels()
        sw = w.getsampwidth()
        fr = w.getframerate()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    if fr != SR and len(data) > 1:
        new_n = int(len(data) * SR / fr)
        data = np.interp(np.linspace(0, len(data) - 1, new_n),
                         np.arange(len(data)), data).astype(np.float32)
    # trim to a sane preview length and tidy the edges
    data = data[: int(8.0 * SR)]
    return synth._edge_fade(synth._normalize(data, 0.9), ms=8.0)


def _load_index():
    try:
        with open(_INDEX, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise TypeError("sample index must be an object")
            return data
    except (FileNotFoundError, ValueError, TypeError, OSError) as exc:
        if not isinstance(exc, FileNotFoundError):
            _LOG.exception("Could not load imported-sample index")
        return {}


def _save_index(idx):
    try:
        return atomic_write_json(_INDEX, idx, indent=1)
    except PersistenceError:
        _LOG.exception("Could not save imported-sample index")
        return False


def _register(comp_id, name, filename, buf):
    _BUFFERS[comp_id] = buf
    catalog._COMPONENTS.append(dict(
        id=comp_id, name=name, type="user", track="user", rarity="common",
        region="meadow", starter=True, icon="tape", color=(200, 230, 200),
        desc="Your imported sound."))
    catalog.BY_ID[comp_id] = catalog._COMPONENTS[-1]


def load_all():
    """Load previously imported samples so they are usable after a restart."""
    idx = _load_index()
    for comp_id, meta in idx.items():
        path = os.path.join(paths.samples_dir(), meta["file"])
        if comp_id in catalog.BY_ID or not os.path.exists(path):
            continue
        try:
            buf = _read_wav(path)
        except (wave.Error, OSError, ValueError):
            continue
        _register(comp_id, meta.get("name", "My Sound"), meta["file"], buf)


def import_wav(src_path, name=None):
    """Import a WAV file. Returns the new component id, or None on failure."""
    if not os.path.exists(src_path):
        return None
    try:
        buf = _read_wav(src_path)
    except (wave.Error, OSError, ValueError):
        return None
    base = name or os.path.splitext(os.path.basename(src_path))[0]
    comp_id = "user_" + "".join(c for c in base.lower() if c.isalnum())[:16]
    n = comp_id
    i = 2
    while n in catalog.BY_ID:
        n = f"{comp_id}{i}"
        i += 1
    comp_id = n
    filename = comp_id + ".wav"
    dst = os.path.join(paths.samples_dir(), filename)
    try:
        shutil.copyfile(src_path, dst)
    except OSError:
        return None
    _register(comp_id, base, filename, buf)
    idx = _load_index()
    idx[comp_id] = {"name": base, "file": filename}
    if not _save_index(idx):
        _LOG.error("Imported sample index update failed for %s", comp_id)
        _BUFFERS.pop(comp_id, None)
        catalog.BY_ID.pop(comp_id, None)
        catalog._COMPONENTS[:] = [c for c in catalog._COMPONENTS if c.get("id") != comp_id]
        try:
            os.remove(dst)
        except OSError:
            _LOG.exception("Could not remove uncommitted imported sample %s", filename)
        return None
    return comp_id


def buffer_for(comp_id):
    return _BUFFERS.get(comp_id)


def buffers():
    return dict(_BUFFERS)


def user_ids():
    """Component ids for every imported user sound (newest registration last)."""
    return list(_BUFFERS.keys())
