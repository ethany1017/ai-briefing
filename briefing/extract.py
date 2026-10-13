"""Fetch full article text for the selected stories only (trafilatura), capped per story."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import trafilatura

from . import config
from .fetch import http_get

log = logging.getLogger(__name__)


def extract_one(item: dict, getter=http_get) -> str:
    text = None
    try:
        html = getter(item["url"])
        text = trafilatura.extract(html.decode("utf-8", errors="replace"), include_comments=False)
    except Exception as e:  # fall back to the snippet on any failure
        log.warning("extract failed for %s: %s", item["url"], e)
    text = (text or "").strip()
    if len(text) < 200:
        text = text if len(text) > len(item.get("snippet") or "") else (item.get("snippet") or "")
    return text[: config.ARTICLE_CHARS]


def extract_all(items: list[dict], getter=http_get, workers: int = 8) -> dict[int, str]:
    """Return {id: text<=ARTICLE_CHARS} for each item."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        texts = list(pool.map(lambda it: extract_one(it, getter), items))
    return {it["id"]: t for it, t in zip(items, texts)}
