"""Structured run logging.

Every phase's run gets its own timestamped, append-safe log file under
logs/<phase>_<timestamp>.log via resolve_path("logs") — never a literal path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from src.utils.io import resolve_path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get_run_logger(phase: str, *, run_timestamp: str | None = None) -> logging.Logger:
    """Return a logger that writes to logs/<phase>_<run_timestamp>.log.

    Appends rather than truncates if the file already exists, so multiple
    calls within the same run (same `run_timestamp`) share one log file
    instead of clobbering each other. If `run_timestamp` is omitted, a fresh
    UTC timestamp is generated, so uncoordinated calls default to separate
    files rather than silently interleaving into one.
    """
    if not phase:
        raise ValueError("phase must be a non-empty string")

    ts = run_timestamp or _utc_timestamp()
    logs_dir = resolve_path("logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{phase}_{ts}.log"

    logger_name = f"vizag.{phase}.{ts}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    already_attached = any(
        isinstance(handler, logging.FileHandler) and Path(handler.baseFilename) == log_path
        for handler in logger.handlers
    )
    if not already_attached:
        handler = logging.FileHandler(log_path, mode="a")
        handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        logger.addHandler(handler)

    return logger
