"""Public URLs for a day's page and a story's Explained anchor."""
from __future__ import annotations

from .. import config


def base(base_url: str | None = None) -> str:
    b = base_url or config.PAGES_BASE_URL
    return b if b.endswith("/") else b + "/"


def day_url(day: str, base_url: str | None = None) -> str:
    return f"{base(base_url)}{day}.html"


def explained_url(day: str, anchor: str, base_url: str | None = None) -> str:
    return f"{day_url(day, base_url)}#{anchor}"


def grouped(items: list[dict]) -> list[tuple[str, list[dict]]]:
    """[(category, items)] in the fixed category order, empty categories skipped."""
    return [(c, [i for i in items if i["category"] == c]) for c in config.CATEGORIES if any(i["category"] == c for i in items)]
