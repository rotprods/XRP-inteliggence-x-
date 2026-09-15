from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any


_KEY_VALUE_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|authorization|password)\s*[:=]\s*([^\s,&]+)"
)
_BEARER_SECRET = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_QUERY_SECRET = re.compile(
    r"(?i)([?&](?:api[_-]?key|token|secret|authorization|password)=)[^&#\s]+"
)


def redact_secrets(value: str) -> str:
    redacted = _KEY_VALUE_SECRET.sub(lambda match: f"{match.group(1)}=***", value)
    redacted = _BEARER_SECRET.sub("Bearer ***", redacted)
    return _QUERY_SECRET.sub(lambda match: f"{match.group(1)}***", redacted)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
