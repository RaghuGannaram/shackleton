# logger.py
from __future__ import annotations

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from contextvars import ContextVar

# ---------- context (accessible from any module) ----------
_room_id: ContextVar[str] = ContextVar("room_id", default="-")
_provider: ContextVar[str] = ContextVar("provider", default="-")
_voice: ContextVar[str] = ContextVar("voice", default="-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.room_id = _room_id.get()
        record.provider = _provider.get()
        record.voice = _voice.get()
        return True


# ---------- singleton logger ----------
_log: Optional[logging.Logger] = None
_initialized = False


def init_logger(
    log_level: str = "INFO",
    log_dir: str = "./logs",
    log_file: str = "output.log",
    max_bytes: int = 5_242_880,  # ~5MB
    backups: int = 5,
) -> logging.Logger:
    """
    Idempotent: safe to call multiple times (won't add duplicate handlers).
    """
    global _log, _initialized

    if _initialized and _log is not None:
        return _log

    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, log_file)

    log = logging.getLogger("shackleton")
    log.setLevel(log_level.upper())
    log.propagate = False

    if not log.handlers:
        # console
        consoleHandler = logging.StreamHandler(sys.stdout)
        consoleHandler.setLevel(log_level.upper())

        # rotating file
        fileHandler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
        fileHandler.setLevel(log_level.upper())

        log_format = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s "
            "[room=%(room_id)s provider=%(provider)s voice=%(voice)s] "
            "%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S%z",
        )
        consoleHandler.setFormatter(log_format)
        fileHandler.setFormatter(log_format)

        log.addHandler(consoleHandler)
        log.addHandler(fileHandler)

    # add context filter once
    has_filter = any(isinstance(filter, _ContextFilter) for filter in log.filters)
    if not has_filter:
        log.addFilter(_ContextFilter())

    _initialized = True
    _log = log
    return log


def get_logger() -> logging.Logger:
    if _log is None:
        return init_logger()
    return _log


def set_log_context(
    room: Optional[str] = None,
    provider: Optional[str] = None,
    voice: Optional[str] = None,
) -> None:
    if room is not None:
        _room_id.set(str(room))
    if provider is not None:
        _provider.set(str(provider))
    if voice is not None:
        _voice.set(str(voice))


def clear_log_context() -> None:
    _room_id.set("-")
    _provider.set("-")
    _voice.set("-")
