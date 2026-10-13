"""briefings/YYYY-MM-DD.md"""
from __future__ import annotations

from pathlib import Path

from .. import config
from . import links


def render(record: dict, base_url: str | None = None) -> str:
    day = record["date"]
    out = [f"# AI Briefing: {day}", ""]
    if not record["items"]:
        out += ["No notable AI news today.", ""]
    for cat, items in links.grouped(record["items"]):
        out += [f"## {cat}", ""]
        for it in items:
            ex = it["explained"]
            out += [
                f"### {it['headline']}",
                "",
                f"[Explained]({links.explained_url(day, it['anchor'], base_url)}) · [Source]({it['url']}) ({it['source']})",
                "",
                f"**What happened:** {ex['what_happened']}",
                "",
                f"**Why it matters:** {ex['why_it_matters']}",
                "",
                f"**What it means for you:** {ex['what_it_means_for_you']}",
                "",
            ]
    return "\n".join(out).rstrip() + "\n"


def write(record: dict, out_dir: Path = config.BRIEFINGS_DIR, base_url: str | None = None) -> Path:
    path = Path(out_dir) / f"{record['date']}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(record, base_url))
    return path
