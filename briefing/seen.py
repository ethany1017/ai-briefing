"""data/seen.json: canonical URL -> first-seen date (YYYY-MM-DD), pruned after 60 days."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from . import config


def load(path: Path = config.SEEN_FILE) -> dict | None:
    """Return the seen map, or None if the file does not exist (bootstrap)."""
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text() or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def add(seen: dict, urls, day: date) -> dict:
    stamp = day.isoformat()
    for u in urls:
        seen.setdefault(u, stamp)
    return seen


def prune(seen: dict, day: date, days: int = config.SEEN_PRUNE_DAYS) -> dict:
    cutoff = (day - timedelta(days=days)).isoformat()
    return {u: d for u, d in seen.items() if d >= cutoff}


def save(seen: dict, path: Path = config.SEEN_FILE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(seen.items())), indent=1) + "\n")
