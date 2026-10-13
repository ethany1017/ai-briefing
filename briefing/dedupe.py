"""URL canonicalization and duplicate removal (within a run and against seen.json)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid"}
TITLE_SIMILARITY = 0.92


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if parts.port and not ((parts.scheme == "http" and parts.port == 80) or (parts.scheme == "https" and parts.port == 443)):
        host = f"{host}:{parts.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS
    ]
    path = parts.path.rstrip("/")
    scheme = "https" if parts.scheme in ("http", "https") else parts.scheme
    return urlunsplit((scheme, host, path, urlencode(sorted(query)), ""))


_NON_WORD = re.compile(r"[^a-z0-9]+")


def normalize_title(title: str) -> str:
    return _NON_WORD.sub(" ", title.lower()).strip()


def _near_dup(a: str, b: str) -> bool:
    if a == b:
        return True
    if abs(len(a) - len(b)) > max(len(a), len(b)) * (1 - TITLE_SIMILARITY):
        return False
    return SequenceMatcher(None, a, b).ratio() >= TITLE_SIMILARITY


def dedupe(items: list[dict], seen: dict | None = None) -> list[dict]:
    """Keep the first occurrence (sources.yaml order) of each story.

    Adds item["canonical"]. Drops: same canonical URL, near-identical normalized
    title, or canonical URL already in `seen`.
    """
    seen = seen or {}
    urls: set[str] = set()
    titles: list[str] = []
    out = []
    for it in items:
        canon = canonical_url(it["url"])
        if canon in seen or canon in urls:
            continue
        nt = normalize_title(it["title"])
        if nt and any(_near_dup(nt, t) for t in titles):
            continue
        urls.add(canon)
        if nt:
            titles.append(nt)
        out.append({**it, "canonical": canon})
    return out
