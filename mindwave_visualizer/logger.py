"""
MindWave Visualizer — Logging
==============================
Rotating-file + console logger used by every module.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

from config import LOG_DIR, LOG_MAX_BYTES, LOG_BACKUP_COUNT


def setup_logger(name: str = "mindwave", level: int = logging.DEBUG) -> logging.Logger:
    """Return (or create) a named logger with rotating-file and console handlers."""
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file handler ──────────────────────────────────────────
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, f"{name}.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # ── Console handler ────────────────────────────────────────────────
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
