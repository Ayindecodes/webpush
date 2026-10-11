"""Structured logging with secret redaction applied to every record."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from webxray.security.redaction import redact_text


class RedactingJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact_text(message)[0],
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingJsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("sqlalchemy.engine", "asyncio", "httpx", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
