"""Shared helpers for adapters: HTML-to-text and date parsing."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(text: str | None, limit: int | None = None) -> str:
    if not text:
        return ""
    out = _WS.sub(" ", html.unescape(_TAG.sub(" ", text))).strip()
    if limit is not None and len(out) > limit:
        out = out[: limit - 1].rstrip() + "\u2026"
    return out


def parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    if not value or not isinstance(value, str):
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        # Trim fractional seconds longer than Python 3.9/3.10 accept.
        m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(.*)$", v)
        if not m:
            return None
        try:
            dt = datetime.fromisoformat(m.group(1) + (m.group(3) or ""))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
