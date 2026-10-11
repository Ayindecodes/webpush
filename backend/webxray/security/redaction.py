"""Redaction of credentials, tokens and personal data before anything is persisted.

Redaction runs on every string the worker stores: event messages, console
text, URLs, DOM snapshots and test output. A :class:`Redactor` additionally
knows the exact secret values in play for an investigation (e.g. the test
account password) and removes them wherever they appear.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

REDACTED = "[REDACTED]"

SENSITIVE_PARAM = re.compile(
    r"(pass(word)?|pwd|secret|token|auth|session|sess|sid|jwt|key|api[-_]?key|signature|sig|"
    r"code|otp|credential|cookie|bearer|access|refresh|card|cvc|cvv|ssn)",
    re.IGNORECASE,
)

_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), REDACTED),
    ("bearer", re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 " + REDACTED),
    ("aws_key", re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    ("api_key", re.compile(r"\b(sk|pk|rk)[-_](live|test)?[-_]?[A-Za-z0-9]{16,}\b"), REDACTED),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), REDACTED),
    (
        "kv_secret",
        re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|session[_-]?id)\b(\s*[=:]\s*)([^\s&\"',;]+)"),
        r"\1\2" + REDACTED,
    ),
]

_CARD_CANDIDATE = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact_text(text: str, known_secrets: Iterable[str] = ()) -> tuple[str, list[str]]:
    """Return ``(redacted_text, applied_rule_names)``."""
    applied: list[str] = []
    for secret in sorted({s for s in known_secrets if s and len(s) >= 4}, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, REDACTED)
            applied.append("known_secret")
    for name, pattern, repl in _PATTERNS:
        text, n = pattern.subn(repl, text)
        if n:
            applied.append(name)

    def _card(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return "[REDACTED-CARD]" if _luhn_ok(digits) else m.group(0)

    new_text = _CARD_CANDIDATE.sub(_card, text)
    if new_text != text:
        applied.append("card_number")
    return new_text, applied


def redact_url(url: str) -> str:
    """Redact sensitive query parameter values and any embedded userinfo."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return REDACTED
    netloc = parts.netloc
    if "@" in netloc:
        netloc = REDACTED + "@" + netloc.rsplit("@", 1)[1]
    query = parts.query
    if query:
        pairs = parse_qsl(query, keep_blank_values=True)
        query = urlencode(
            [(k, REDACTED if SENSITIVE_PARAM.search(k) else v) for k, v in pairs], safe="[]"
        )
    fragment = REDACTED if parts.fragment and SENSITIVE_PARAM.search(parts.fragment) else parts.fragment
    return urlunsplit((parts.scheme, netloc, parts.path, query, fragment))


class Redactor:
    def __init__(self, known_secrets: Iterable[str] = ()) -> None:
        self._secrets: set[str] = {s for s in known_secrets if s}

    def add_secret(self, value: str | None) -> None:
        if value:
            self._secrets.add(value)

    def text(self, value: str) -> str:
        return redact_text(value, self._secrets)[0]

    def text_with_rules(self, value: str) -> tuple[str, list[str]]:
        return redact_text(value, self._secrets)

    def url(self, value: str) -> str:
        return self.text(redact_url(value))

    def deep(self, value: Any) -> Any:
        """Redact every string inside a JSON-like structure."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {k: (REDACTED if _sensitive_key(k) else self.deep(v)) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [self.deep(v) for v in value]
        return value


def _sensitive_key(key: object) -> bool:
    return isinstance(key, str) and key.lower() in {
        "password",
        "passwd",
        "secret",
        "token",
        "cookie",
        "cookies",
        "authorization",
        "set-cookie",
        "storage_state",
    }
