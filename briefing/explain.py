"""Claude call 2: plain-English explanations for each selected story."""
from __future__ import annotations

import json
import logging
import re

from . import claude_cli

log = logging.getLogger(__name__)

FIELDS = ("what_happened", "why_it_matters", "what_it_means_for_you")
URL_RE = re.compile(r"\(?\s*(?:https?://|www\.)\S+\s*\)?", re.I)

PROMPT = """You explain AI news to a CS student / early-career software engineer.

For each story below, write three short sections:
- "what_happened": 2-3 sentences on the facts.
- "why_it_matters": 2-3 sentences on why it is significant for the AI field or industry.
- "what_it_means_for_you": 2-3 sentences on what it means for a CS student / early-career software engineer (skills, tools, jobs, opportunities). Be concrete and honest; if it barely matters to them, say so briefly.

Style: plain language, short sentences, a helpful everyday analogy where it makes things clearer. No jargon; if a technical term is unavoidable, explain it in a few words. No hype. No URLs. No markdown.

Use ONLY the supplied text for each story. Do not add facts, numbers, names or dates that are not in it. If the text is thin, keep the explanation short rather than guessing.

Reply with ONLY a JSON array with one object per story, like:
[{{"id": 3, "what_happened": "...", "why_it_matters": "...", "what_it_means_for_you": "..."}}]

Stories:
{stories}
"""


def build_prompt(stories: list[dict]) -> str:
    rows = [
        {"id": s["id"], "headline": s["headline"], "title": s["title"], "source": s["source"], "text": s["text"]}
        for s in stories
    ]
    return PROMPT.format(stories=json.dumps(rows, ensure_ascii=False, indent=0))


def _clean(v) -> str:
    return " ".join(URL_RE.sub(" ", str(v or "")).split())


def make_validator(ids: list[int]):
    wanted = set(ids)

    def validate(obj) -> dict[int, dict]:
        if isinstance(obj, dict) and not any(k in obj for k in FIELDS):
            lists = [v for v in obj.values() if isinstance(v, list)]
            obj = lists[0] if len(lists) == 1 else obj
        if not isinstance(obj, list):
            raise ValueError("expected a JSON array")
        out: dict[int, dict] = {}
        for e in obj:
            if not isinstance(e, dict):
                continue
            sid = claude_cli.as_id(e.get("id"))
            if sid is None or sid not in wanted:
                log.warning("explain: dropping unknown id %r", e.get("id"))
                continue
            if sid in out:
                continue
            fields = {f: _clean(e.get(f)) for f in FIELDS}
            if not all(fields.values()):
                log.warning("explain: dropping id %s with missing fields", sid)
                continue
            out[sid] = fields
        if wanted and len(out) * 2 < len(wanted):
            raise ValueError(f"only {len(out)}/{len(wanted)} stories explained")
        missing = wanted - set(out)
        if missing:
            log.warning("explain: no explanation for ids %s; dropping them", sorted(missing))
        return out

    return validate


def explain(stories: list[dict], runner=claude_cli.run_cli) -> dict[int, dict]:
    """stories: [{id, headline, title, source, text}]. Returns {id: {what_happened, ...}}."""
    if not stories:
        return {}
    validate = make_validator([s["id"] for s in stories])
    return claude_cli.call_json(build_prompt(stories), validate, "explain", runner)
