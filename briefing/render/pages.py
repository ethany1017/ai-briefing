"""docs/YYYY-MM-DD.html (one <section id=anchor> per story) and docs/index.html."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .. import config
from . import links


def _env(templates_dir: Path = config.TEMPLATES_DIR) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def pretty_date(day: str) -> str:
    d = date.fromisoformat(day)
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}"


def render_day(record: dict) -> str:
    return _env().get_template("day.html.j2").render(
        day=record["date"],
        pretty=pretty_date(record["date"]),
        groups=links.grouped(record["items"]),
        count=len(record["items"]),
    )


def render_index(days: list[dict]) -> str:
    return _env().get_template("index.html.j2").render(
        days=[dict(d, pretty=pretty_date(d["date"])) for d in days]
    )


def write(record: dict, days: list[dict], docs_dir: Path = config.DOCS_DIR) -> list[Path]:
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / ".nojekyll").touch()
    day_path = docs_dir / f"{record['date']}.html"
    day_path.write_text(render_day(record))
    index_path = docs_dir / "index.html"
    index_path.write_text(render_index(days))
    return [day_path, index_path]
