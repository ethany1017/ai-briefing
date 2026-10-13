"""Load sources.yaml into a list of plain source dicts."""
from __future__ import annotations

from pathlib import Path

import yaml

from . import config

REQUIRED = ("name", "url", "kind")


def load_sources(path: Path = config.SOURCES_FILE) -> list[dict]:
    doc = yaml.safe_load(Path(path).read_text()) or {}
    defaults = doc.get("defaults") or {}
    out = []
    for raw in doc.get("sources") or []:
        src = {"ai_filter": False, "max_items": 25}
        src.update(defaults)
        src.update(raw)
        missing = [k for k in REQUIRED if not src.get(k)]
        if missing:
            raise ValueError(f"source {raw!r} missing {missing}")
        src["ai_filter"] = bool(src["ai_filter"])
        src["max_items"] = int(src["max_items"])
        out.append(src)
    names = [s["name"] for s in out]
    if len(names) != len(set(names)):
        raise ValueError("duplicate source names in sources.yaml")
    return out
