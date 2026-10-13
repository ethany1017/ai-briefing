"""RSS/Atom adapter (feedparser)."""
from __future__ import annotations

import calendar
from datetime import datetime, timezone

import feedparser

from .. import config
from .text import clean


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        st = entry.get(key)
        if st:
            try:
                return datetime.fromtimestamp(calendar.timegm(st), tz=timezone.utc)
            except (OverflowError, ValueError, TypeError):
                continue
    return None


def parse(content: bytes) -> list[dict]:
    feed = feedparser.parse(content)
    if not feed.entries and feed.get("bozo"):
        raise ValueError(f"unparseable feed: {feed.get('bozo_exception')!r}")
    items = []
    for e in feed.entries:
        summary = e.get("summary") or ""
        if not summary and e.get("content"):
            summary = e["content"][0].get("value", "")
        items.append(
            {
                "title": clean(e.get("title")),
                "url": (e.get("link") or "").strip(),
                "published": _entry_date(e),
                "snippet": clean(summary, config.SNIPPET_CHARS),
            }
        )
    return items
