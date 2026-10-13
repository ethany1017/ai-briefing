"""Adapters turn a fetched response body into raw items {title, url, published, snippet}."""
from __future__ import annotations

import json

from . import json_kinds, rss


def parse(kind: str, content: bytes) -> list[dict]:
    if kind == "rss":
        return rss.parse(content)
    fn = json_kinds.KINDS.get(kind)
    if fn is None:
        raise ValueError(f"unknown source kind: {kind}")
    return fn(json.loads(content))
