"""Safe saving, loading, listing and deleting of music projects.

Each project is one JSON file under ``save/projects/<id>.json``. Files are
untrusted input: malformed projects are preserved on disk, skipped, logged and
reported through a non-blocking warning instead of crashing a screen.
"""

from __future__ import annotations

import json
import os
import re

from .. import paths
from ..logging_utils import get_logger
from ..persistence import PersistenceError, atomic_write_json
from .project import Project, ProjectValidationError

_LOG = get_logger("project_store")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_WARNINGS = []


def _warn(filename: str, reason: str) -> None:
    message = "Could not open saved song '%s'. The file was left unchanged." % filename
    if message not in _WARNINGS:
        _WARNINGS.append(message)
        del _WARNINGS[:-20]
    _LOG.warning("Project %s was skipped: %s", filename, reason)


def consume_warnings():
    warnings = list(_WARNINGS)
    _WARNINGS.clear()
    return warnings


def _validate_id(project_id) -> str:
    if not isinstance(project_id, str) or not _ID_RE.fullmatch(project_id):
        raise ProjectValidationError("invalid project id")
    return project_id


def path_for(project_id):
    return os.path.join(paths.projects_dir(), "%s.json" % _validate_id(project_id))


def _load_path(path, fallback_id=None):
    filename = os.path.basename(path)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return Project.from_dict(payload, fallback_id=fallback_id)
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError,
            KeyError, IndexError, ProjectValidationError) as exc:
        _warn(filename, str(exc))
        return None
    except Exception as exc:
        # A malformed external file must never take down the song browser.
        _warn(filename, str(exc))
        _LOG.exception("Unexpected project parsing failure for %s", filename)
        return None


def save(project, replace_ids=None):
    """Atomically save *project* and then remove superseded project ids.

    Existing content at the destination is never deleted first. If writing or
    replacement fails, the previous project remains byte-for-byte intact.
    """
    previous_modified = getattr(project, "modified", None)
    try:
        _validate_id(project.id)
        project.touch()
        payload = project.to_dict()
        # Validate the exact structure before any file is replaced.
        Project.from_dict(payload, fallback_id=project.id)
        atomic_write_json(path_for(project.id), payload, indent=1)
    except (PersistenceError, ProjectValidationError, TypeError, ValueError) as exc:
        if previous_modified is not None:
            project.modified = previous_modified
        _LOG.exception("Could not save song project %s", getattr(project, "id", "unknown"))
        return False

    # A name-conflict replacement removes the old, differently-id'd file only
    # after the new project is safely committed. Failure here leaves a harmless
    # duplicate rather than losing the user's old song.
    for project_id in replace_ids or ():
        if project_id == project.id:
            continue
        if not delete(project_id):
            _LOG.warning("Saved replacement but could not remove superseded project %s", project_id)
    return True


def load(project_id):
    try:
        safe_id = _validate_id(project_id)
    except ProjectValidationError as exc:
        _warn("%s.json" % str(project_id), str(exc))
        return None
    return _load_path(path_for(safe_id), fallback_id=safe_id)


def delete(project_id):
    try:
        os.remove(path_for(project_id))
        return True
    except FileNotFoundError:
        return True
    except (OSError, ProjectValidationError):
        _LOG.exception("Could not delete project %s", project_id)
        return False


def list_projects():
    """Return valid saved projects, newest first; preserve invalid files."""
    out = []
    try:
        filenames = os.listdir(paths.projects_dir())
    except OSError:
        _LOG.exception("Could not list saved song directory")
        return out
    for filename in filenames:
        if not filename.lower().endswith(".json"):
            continue
        fallback_id = filename[:-5]
        project = _load_path(os.path.join(paths.projects_dir(), filename), fallback_id=fallback_id)
        if project is not None:
            out.append(project)
    out.sort(key=lambda project: project.modified, reverse=True)
    return out
