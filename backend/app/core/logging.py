from __future__ import annotations

import logging
import re


SENSITIVE_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|authorization|cookie)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
)


def redact_sensitive(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(0).split(':')[0].split('=')[0]}=[REDACTED]", redacted)
    return redacted


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

