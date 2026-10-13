"""Claude call 1: choose and categorize the day's stories."""
from __future__ import annotations

import json
import logging
import re

from . import claude_cli, config

log = logging.getLogger(__name__)
URL_RE = re.compile(r"https?://|www\.", re.I)

PROMPT = """You are the editor of a daily AI news briefing.

Below is a JSON array of candidate items fetched today. Each has a numeric "id", "title", "source" and "snippet".

Choose the most important and genuinely newsworthy AI stories. Rules:
- Up to {per_category} stories per category. Aim for {per_category} in a category only when it has {per_category} genuinely worthwhile, distinct stories. Never pad: if a category has only 2 real stories, return 2; if it has none worth reading, return none for it. Quality over quantity, same bar for every slot; no filler to fill a category.
- One item per real-world event: if several candidates cover the same announcement, release or study (even from different angles), keep only the single most informative one. This holds within a category too: two angles on one launch (say its benchmarks and its pricing) are one story, not two, even when the category has room left.
- Skip minor product tweaks, listicles, marketing fluff, opinion without news, and anything not about AI.
- For "AI Jobs & Career Opportunities", favor internships, new-grad and entry-level roles and notable hiring trends; skip senior-only postings.
- Put each story in exactly one category, copied exactly from this list:
{categories}
- Write a "headline": one factual plain-English sentence, at most 110 characters, no hype, no URLs.
- Use only information in the candidates. Do not invent stories.

Reply with ONLY a JSON array. Within each category, order its stories best-first (the most important story in that category comes before the others in that category). Example:
[{{"id": 12, "category": "AI Models & Releases", "headline": "..."}}]

Candidates:
{candidates}
"""


def build_prompt(candidates: list[dict]) -> str:
    rows = [
        {"id": c["id"], "title": c["title"], "source": c["source"], "snippet": c["snippet"]}
        for c in candidates
    ]
    return PROMPT.format(
        per_category=config.MAX_PER_CATEGORY,
        categories="\n".join(f"  - {c}" for c in config.CATEGORIES),
        candidates=json.dumps(rows, ensure_ascii=False, indent=0),
    )


def cap(stories: list[dict]) -> list[dict]:
    """Keep at most MAX_PER_CATEGORY per category (in the model's order) and MAX_TOTAL overall."""
    per_cat: dict[str, int] = {}
    out = []
    for s in stories:
        n = per_cat.get(s["category"], 0)
        if n >= config.MAX_PER_CATEGORY:
            log.warning("rank: dropping id %s, %r already has %d stories", s["id"], s["category"], n)
            continue
        if len(out) >= config.MAX_TOTAL:
            log.warning("rank: total cap %d reached; dropping the rest", config.MAX_TOTAL)
            break
        per_cat[s["category"]] = n + 1
        out.append(s)
    return out


def make_validator(valid_ids: set[int]):
    def validate(obj) -> list[dict]:
        if isinstance(obj, dict):  # tolerate {"stories": [...]}
            lists = [v for v in obj.values() if isinstance(v, list)]
            if len(lists) != 1:
                raise ValueError("expected a JSON array")
            obj = lists[0]
        if not isinstance(obj, list):
            raise ValueError("expected a JSON array")
        out, used = [], set()
        for entry in obj:
            if not isinstance(entry, dict):
                continue
            sid = claude_cli.as_id(entry.get("id"))
            cat = str(entry.get("category") or "").strip()
            head = " ".join(str(entry.get("headline") or "").split())
            if sid is None or sid not in valid_ids:
                log.warning("rank: dropping unknown id %r", entry.get("id"))
                continue
            if sid in used:
                continue
            if cat not in config.CATEGORIES:
                log.warning("rank: dropping id %s with invalid category %r", sid, cat)
                continue
            if not head or URL_RE.search(head):
                log.warning("rank: dropping id %s with empty/URL headline", sid)
                continue
            used.add(sid)
            out.append({"id": sid, "category": cat, "headline": head[:200]})
        return cap(out)

    return validate


def rank(candidates: list[dict], runner=claude_cli.run_cli) -> list[dict]:
    """candidates must carry integer "id"s. Returns [{id, category, headline}], <= MAX_PER_CATEGORY per category, <= MAX_TOTAL."""
    if not candidates:
        return []
    validate = make_validator({c["id"] for c in candidates})
    return claude_cli.call_json(build_prompt(candidates), validate, "rank", runner)
