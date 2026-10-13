"""Slack Block Kit payload(s) for an incoming webhook."""
from __future__ import annotations

from . import links
from .pages import pretty_date

SECTION_LIMIT = 3000
MAX_BLOCKS = 50


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link_url(url: str) -> str:
    return url.replace("|", "%7C").replace(">", "%3E").replace("<", "%3C").replace(" ", "%20")


def bullet(day: str, it: dict, base_url: str | None = None) -> str:
    ex = link_url(links.explained_url(day, it["anchor"], base_url))
    return f"• {esc(it['headline'])}  <{ex}|Explained> · <{link_url(it['url'])}|Source>"


def _sections(title: str, lines: list[str]) -> list[dict]:
    """One category -> one or more mrkdwn sections, each under SECTION_LIMIT chars."""
    blocks, buf = [], f"*{esc(title)}*"
    for line in lines:
        if len(buf) + 1 + len(line) > SECTION_LIMIT - 10:
            blocks.append(buf)
            buf = line[: SECTION_LIMIT - 10]
        else:
            buf += "\n" + line
    blocks.append(buf)
    return [{"type": "section", "text": {"type": "mrkdwn", "text": b}} for b in blocks]


def build(record: dict, base_url: str | None = None) -> list[dict]:
    """Return a list of webhook payloads (normally one; split only past Slack's 50-block cap)."""
    day, items = record["date"], record["items"]
    header = {"type": "header", "text": {"type": "plain_text", "text": f"AI Briefing · {pretty_date(day)}"[:150]}}
    if not items:
        text = f"No notable AI news today ({day})."
        return [{"text": text, "blocks": [header, {"type": "section", "text": {"type": "mrkdwn", "text": text}}]}]

    body = []
    for cat, cat_items in links.grouped(items):
        body.extend(_sections(cat, [bullet(day, it, base_url) for it in cat_items]))
    stats = record.get("stats") or {}
    footer = {
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"{len(items)} stories from {stats.get('sources_ok', '?')} sources · <{link_url(links.day_url(day, base_url))}|Full briefing>",
        }],
    }
    fallback = f"AI Briefing for {day}: {len(items)} stories. {links.day_url(day, base_url)}"

    payloads, chunk = [], [header]
    for b in body:
        if len(chunk) >= MAX_BLOCKS - 1:
            payloads.append(chunk)
            chunk = []
        chunk.append(b)
    chunk.append(footer)
    payloads.append(chunk)
    return [{"text": fallback, "blocks": blocks} for blocks in payloads]
