from __future__ import annotations

import logging
from pathlib import Path

from .models import Settings
from .storage import logs_dir


def configure_logging(settings: Settings) -> logging.Logger:
    logger = logging.getLogger("adoptme_macro")

    if getattr(logger, "_configured", False):
        _apply_logger_settings(logger, settings)
        return logger

    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    level = logging.DEBUG if settings.debug_mode else logging.INFO

    if settings.enable_logs:
        log_path = _log_file_path()
        fh = logging.FileHandler(str(log_path), mode="w", encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    logger._configured = True  # type: ignore[attr-defined]
    return logger


def _apply_logger_settings(logger: logging.Logger, settings: Settings) -> None:
    level = logging.DEBUG if settings.debug_mode else logging.INFO

    file_handlers: list[logging.Handler] = []
    stream_handlers: list[logging.Handler] = []
    for h in list(getattr(logger, "handlers", []) or []):
        if isinstance(h, logging.FileHandler):
            file_handlers.append(h)
        elif isinstance(h, logging.StreamHandler):
            stream_handlers.append(h)

    for h in file_handlers:
        try:
            h.setLevel(level)
        except Exception:
            pass
    for h in stream_handlers:
        try:
            h.setLevel(level)
        except Exception:
            pass

    if settings.enable_logs:
        if not file_handlers:
            try:
                fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
                fh = logging.FileHandler(str(_log_file_path()), mode="a", encoding="utf-8")
                fh.setLevel(level)
                fh.setFormatter(fmt)
                logger.addHandler(fh)
            except Exception:
                pass
    else:
        for h in file_handlers:
            try:
                logger.removeHandler(h)
            except Exception:
                pass
            try:
                h.close()
            except Exception:
                pass


def _log_file_path() -> Path:
    return logs_dir() / "macro.log"
