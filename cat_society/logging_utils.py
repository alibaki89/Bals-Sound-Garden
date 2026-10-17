"""Bounded release logging for recoverable game errors.

The game should show friendly messages to players while retaining technical
information for support. Logging is deliberately lightweight and never allowed
to become a second failure source.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from . import paths

_CONFIGURED = False
_LOGGER_NAME = "bals_sound_garden"


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        log_dir = os.path.join(paths.base_save_dir(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = RotatingFileHandler(
            os.path.join(log_dir, "game.log"),
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        ))
        logger.addHandler(handler)
    except Exception:
        # Logging must never prevent the game from starting or saving.
        logger.addHandler(logging.NullHandler())


def get_logger(name=None) -> logging.Logger:
    _configure()
    suffix = (name or "game").strip(".")
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}")
