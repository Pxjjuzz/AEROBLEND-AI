from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.config import settings

_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """Minimal structured formatter. Keeps logs greppable and machine readable
    without pulling in a logging dependency."""

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            base.update(extra)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return " ".join(f'{k}={v!r}' for k, v in base.items())


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = logging.DEBUG if settings.DEBUG else logging.INFO
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn installs its own noisy access logger at INFO.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Third-party HTTP and DB drivers log every statement and frame at DEBUG.
    # Keep our own loggers verbose but silence the transport layers unless
    # explicitly asked for.
    noisy = (
        "httpcore",
        "httpx",
        "hpack",
        "asyncio",
        "urllib3",
        "sqlalchemy.engine",
        "aiosqlite",
        "sqlalchemy.pool",
    )
    for name in noisy:
        logging.getLogger(name).setLevel(
            logging.INFO if settings.DEBUG else logging.WARNING
        )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def log_event(logger: logging.Logger, level: int, msg: str, **context: Any) -> None:
    logger.log(level, msg, extra={"context": context})

