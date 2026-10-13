"""Assemble the day's record, guard its URLs, and write data/YYYY-MM-DD.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import config
from .errors import BriefingError

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 60) -> str:
    s = _SLUG.sub("-", text.lower()).strip("-")
    if len(s) > max_len:
        cut = s[: max_len + 1]
        s = cut[: cut.rfind("-")] if "-" in cut else s[:max_len]
    return s.strip("-") or "story"


def build_record(day: str, candidates: list[dict], ranked: list[dict], explained: dict[int, dict], stats: dict, generated_at: str) -> dict:
    """Join Claude's picks back to fetched items by id. URLs come only from `candidates`."""
    by_id = {c["id"]: c for c in candidates}
    order = {c: i for i, c in enumerate(config.CATEGORIES)}
    items, anchors = [], set()
    for r in ranked:
        if r["id"] not in explained or r["id"] not in by_id:
            continue
        src = by_id[r["id"]]
        anchor = base = slugify(r["headline"])
        n = 2
        while anchor in anchors:
            anchor, n = f"{base}-{n}", n + 1
        anchors.add(anchor)
        items.append(
            {
                "id": r["id"],
                "category": r["category"],
                "headline": r["headline"],
                "url": src["url"],
                "source": src["source"],
                "published": src["published"],
                "explained": explained[r["id"]],
                "anchor": anchor,
            }
        )
    items.sort(key=lambda it: order[it["category"]])  # stable: keeps rank order within a category
    stats = dict(stats, selected=len(items))
    return {"date": day, "generated_at": generated_at, "items": items, "stats": stats}


def assert_urls_fetched(record: dict, fetched_urls: set[str]) -> None:
    bad = [it["url"] for it in record["items"] if it["url"] not in fetched_urls]
    if bad:
        raise BriefingError(f"{len(bad)} output URL(s) not in the fetched set, e.g. {bad[0][:120]}")


def day_path(day: str, data_dir: Path = config.DATA_DIR) -> Path:
    return Path(data_dir) / f"{day}.json"


def write_record(record: dict, data_dir: Path = config.DATA_DIR) -> Path:
    path = day_path(record["date"], data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    return path


def load_record(day: str, data_dir: Path = config.DATA_DIR) -> dict | None:
    path = day_path(day, data_dir)
    return json.loads(path.read_text()) if path.exists() else None


def list_days(data_dir: Path = config.DATA_DIR) -> list[dict]:
    """[{date, count}] newest first, for the index page."""
    out = []
    for p in sorted(Path(data_dir).glob("????-??-??.json"), reverse=True):
        try:
            rec = json.loads(p.read_text())
            out.append({"date": rec["date"], "count": len(rec.get("items", []))})
        except (ValueError, KeyError):
            continue
    return out
