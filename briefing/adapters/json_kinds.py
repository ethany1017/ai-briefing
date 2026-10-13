"""One small parser per JSON API. Each takes decoded JSON and returns raw items."""
from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .. import config
from .text import clean, parse_iso

S = config.SNIPPET_CHARS


def hn_algolia(data) -> list[dict]:
    out = []
    for h in data.get("hits", []):
        hn_url = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        ts = h.get("created_at_i")
        out.append(
            {
                "title": clean(h.get("title")),
                "url": h.get("url") or hn_url,
                "published": datetime.fromtimestamp(ts, tz=timezone.utc) if ts else parse_iso(h.get("created_at")),
                "snippet": clean(f"{h.get('points', 0)} points, {h.get('num_comments', 0)} comments on Hacker News. {h.get('story_text') or ''}", S),
            }
        )
    return out


def hf_daily_papers(data) -> list[dict]:
    out = []
    for row in data or []:
        paper = row.get("paper") or {}
        pid = paper.get("id")
        if not pid:
            continue
        out.append(
            {
                "title": clean(paper.get("title") or row.get("title")),
                "url": f"https://huggingface.co/papers/{pid}",
                "published": parse_iso(row.get("publishedAt") or paper.get("publishedAt")),
                "snippet": clean(paper.get("summary") or row.get("summary"), S),
            }
        )
    return out


def hf_trending_models(data) -> list[dict]:
    out = []
    for m in data or []:
        mid = m.get("id") or m.get("modelId")
        if not mid:
            continue
        tag = m.get("pipeline_tag") or "model"
        out.append(
            {
                "title": f"{mid} (trending on Hugging Face)",
                "url": f"https://huggingface.co/{mid}",
                "published": parse_iso(m.get("createdAt") or m.get("lastModified")),
                "snippet": clean(f"Trending {tag} on Hugging Face. Likes: {m.get('likes', 0)}, downloads: {m.get('downloads', 0)}.", S),
            }
        )
    return out


def github_search(data) -> list[dict]:
    out = []
    for r in data.get("items", []):
        out.append(
            {
                "title": f"{r.get('full_name')}: new LLM repo on GitHub",
                "url": r.get("html_url") or "",
                "published": parse_iso(r.get("created_at")),
                "snippet": clean(f"{r.get('description') or ''} ({r.get('stargazers_count', 0)} stars, {r.get('language') or 'n/a'})", S),
            }
        )
    return out


_ET = ZoneInfo("America/New_York")


def federal_register(data) -> list[dict]:
    out = []
    for d in data.get("results", []):
        pub = None
        raw = d.get("publication_date")
        if raw:
            try:
                day = datetime.strptime(raw, "%Y-%m-%d").date()
                pub = datetime.combine(day, time(6, 0), tzinfo=_ET).astimezone(timezone.utc)
            except ValueError:
                pub = None
        agencies = ", ".join(a.get("name", "") for a in d.get("agencies") or [] if a.get("name"))
        out.append(
            {
                "title": clean(d.get("title")),
                "url": d.get("html_url") or "",
                "published": pub,
                "snippet": clean(f"{d.get('type') or 'Document'} from {agencies or 'a federal agency'}. {d.get('abstract') or ''}", S),
            }
        )
    return out


def remotive(data) -> list[dict]:
    out = []
    for j in data.get("jobs", []):
        out.append(
            {
                "title": clean(f"{j.get('title')} at {j.get('company_name')}"),
                "url": j.get("url") or "",
                "published": parse_iso(j.get("publication_date")),
                "snippet": clean(f"{j.get('job_type') or ''} remote job, {j.get('candidate_required_location') or 'anywhere'}. {j.get('description') or ''}", S),
            }
        )
    return out


KINDS = {
    "hn_algolia": hn_algolia,
    "hf_daily_papers": hf_daily_papers,
    "hf_trending_models": hf_trending_models,
    "github_search": github_search,
    "federal_register": federal_register,
    "remotive": remotive,
}
