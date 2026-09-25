"""Non-blocking logging setup (INFO, WARNING, ERROR, CRITICAL only)."""

from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
from pathlib import Path

from config.settings import settings

_LISTENER: logging.handlers.QueueListener | None = None


class _SkipDebugFilter(logging.Filter):
    """Drop DEBUG records so only the four required levels are emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= logging.INFO


def configure_logging() -> logging.Logger:
    """Configure a queue-backed logger and return the application logger.

    A QueueHandler is attached to the root logger so emit() never blocks
    request threads. A QueueListener writes to stdout and a rotating file.
    """
    global _LISTENER
    if _LISTENER is not None:
        return logging.getLogger("skillsprint")

    settings.ensure_runtime_dirs()
    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.addFilter(_SkipDebugFilter())

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%%Y-%%m-%%d %%H:%%M:%%S".replace("%%", "%"),
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.INFO)

    file_path: Path = settings.log_dir / "skillsprint.log"
    file_handler = logging.handlers.RotatingFileHandler(
        file_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    _LISTENER = logging.handlers.QueueListener(log_queue, stream_handler, file_handler, respect_handler_level=True)
    _LISTENER.start()
    atexit.register(shutdown_logging)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(queue_handler)
    return logging.getLogger("skillsprint")


def shutdown_logging() -> None:
    """Flush and stop the background log listener."""
    global _LISTENER
    if _LISTENER is not None:
        _LISTENER.stop()
        _LISTENER = None


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under the skillsprint namespace."""
    if name:
        return logging.getLogger(f"skillsprint.{name}")
    return logging.getLogger("skillsprint")
