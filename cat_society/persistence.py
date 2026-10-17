"""Small atomic persistence helpers shared by all central JSON saves."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from .logging_utils import get_logger

_LOG = get_logger("persistence")


class PersistenceError(RuntimeError):
    """Controlled failure while serializing or atomically replacing a save."""

    def __init__(self, path: str, operation: str, cause: BaseException):
        self.path = path
        self.operation = operation
        self.cause = cause
        super().__init__(f"Could not {operation} {os.path.basename(path)}: {cause}")


def _fsync_directory(directory: str) -> None:
    """Best-effort directory sync after replacement on supporting platforms."""
    flags = getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(directory, os.O_RDONLY | flags)
    except (OSError, AttributeError):
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_json(path: str, payload: Any, *, indent: int = 1) -> bool:
    """Serialize *payload* and atomically replace *path*.

    Serialization happens before the destination directory is touched. The
    temporary file is created in the destination directory so ``os.replace``
    is atomic on the same filesystem. On any failure the original destination
    remains unchanged and the temporary file is removed.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path) or os.curdir
    temp_path = None
    try:
        text = json.dumps(payload, indent=indent, ensure_ascii=False)
        # Validate the exact serialized form before creating/replacing files.
        json.loads(text)
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.write("\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    # Some virtual/mobile filesystems do not support fsync.
                    pass
        except Exception:
            # fdopen owns and closes fd after it succeeds. If it failed before
            # taking ownership, close the raw descriptor safely.
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        # Re-read the temporary project/save before replacement. This catches
        # short writes and encoding problems without risking the old file.
        with open(temp_path, "r", encoding="utf-8") as handle:
            json.load(handle)
        os.replace(temp_path, path)
        temp_path = None
        _fsync_directory(directory)
        return True
    except Exception as exc:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
        _LOG.exception("Atomic JSON write failed for %s", os.path.basename(path))
        if isinstance(exc, PersistenceError):
            raise
        raise PersistenceError(path, "save", exc) from exc
