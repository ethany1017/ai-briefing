"""Fetch every source in parallel and normalize to dated, AI-relevant items."""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

from . import adapters, config
from .errors import BriefingError

log = logging.getLogger(__name__)

AI_PATTERN = re.compile(
    r"\bA\.?I\b|\bAGI\b|\bLLMs?\b|\bGPT|\bGenAI\b"
    r"|(?i:artificial intelligence|machine learning|deep learning|neural net|generative"
    r"|chatbot|large language model|language model|openai|anthropic|\bclaude\b|gemini"
    r"|chatgpt|copilot|\bagentic\b|deepfake)"
)


def is_ai(text: str) -> bool:
    return bool(AI_PATTERN.search(text or ""))


def resolve_url(url: str, today) -> str:
    since = (today - timedelta(days=7)).isoformat()
    return url.replace("{since}", since)


def http_get(url: str, timeout: int = config.FETCH_TIMEOUT) -> bytes:
    headers = {"User-Agent": config.USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    if "api.github.com" in url:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    if resp.status_code == 403:
        headers["User-Agent"] = config.BROWSER_UA
        resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def normalize(source: dict, raw_items: list[dict], now: datetime) -> list[dict]:
    """Drop undated / out-of-window / off-topic items; cap per source."""
    cutoff = now - timedelta(hours=config.WINDOW_HOURS)
    horizon = now + timedelta(hours=6)  # tolerate small clock skew, reject far-future dates
    keep = []
    for it in raw_items:
        url, title, pub = it.get("url") or "", it.get("title") or "", it.get("published")
        if not title or not url.startswith(("http://", "https://")):
            continue
        if pub is None or not (cutoff <= pub <= horizon):
            continue
        if source.get("ai_filter") and not is_ai(f"{title} {it.get('snippet', '')}"):
            continue
        keep.append(
            {
                "title": title,
                "url": url,
                "source": source["name"],
                "published": pub.astimezone(timezone.utc).isoformat(),
                "snippet": (it.get("snippet") or "")[: config.SNIPPET_CHARS],
            }
        )
    keep.sort(key=lambda x: x["published"], reverse=True)
    return keep[: source.get("max_items", 25)]


def fetch_one(source: dict, now: datetime, getter=http_get) -> tuple[dict, list[dict]]:
    url = resolve_url(source["url"], now.astimezone(config.TZ).date())
    try:
        body = getter(url)
        raw = adapters.parse(source["kind"], body)
        items = normalize(source, raw, now)
        return {"name": source["name"], "ok": True, "raw": len(raw), "kept": len(items), "error": None}, items
    except Exception as e:  # per-source failures are logged, never fatal
        msg = f"{type(e).__name__}: {e}"[:200]
        log.warning("source %s failed: %s", source["name"], msg)
        return {"name": source["name"], "ok": False, "raw": 0, "kept": 0, "error": msg}, []


def fetch_all(sources: list[dict], now: datetime | None = None, getter=http_get, workers: int = 12):
    """Return (items, report). Raises BriefingError if too few sources work or nothing survives."""
    now = now or datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda s: fetch_one(s, now, getter), sources))
    report = [r for r, _ in results]
    items = [it for _, its in results for it in its]
    ok = sum(1 for r in report if r["ok"])
    min_ok = min(config.MIN_SOURCES_OK, len(sources))
    if ok < min_ok:
        raise BriefingError(f"only {ok}/{len(sources)} sources fetched (need {min_ok})")
    if not items:
        raise BriefingError(f"0 items in the last {config.WINDOW_HOURS}h after filtering")
    return items, report


def format_report(report: list[dict]) -> str:
    lines = []
    for r in sorted(report, key=lambda r: (not r["ok"], r["name"])):
        if r["ok"]:
            lines.append(f"  ok    {r['name']:<26} raw={r['raw']:<4} kept={r['kept']}")
        else:
            lines.append(f"  FAIL  {r['name']:<26} {r['error']}")
    ok = sum(1 for r in report if r["ok"])
    lines.append(f"{ok}/{len(report)} sources ok, {sum(r['kept'] for r in report)} items kept")
    return "\n".join(lines)
