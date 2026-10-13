from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from briefing.render import markdown, pages, slack

FIX = Path(__file__).parent / "fixtures"
SNAP = Path(__file__).parent / "snapshots"
BASE = "https://ethany1017.github.io/ai-briefing/"


@pytest.fixture
def record():
    return json.loads((FIX / "record.json").read_text())


def check_snapshot(name: str, text: str):
    path = SNAP / name
    if os.environ.get("UPDATE_SNAPSHOTS") == "1":
        path.parent.mkdir(exist_ok=True)
        path.write_text(text)
    assert text == path.read_text(), f"snapshot {name} changed; rerun with UPDATE_SNAPSHOTS=1 if intended"


def test_markdown_snapshot(record):
    check_snapshot("2026-10-12.md", markdown.render(record, BASE))


def test_day_page_snapshot(record):
    html = pages.render_day(record)
    check_snapshot("2026-10-12.html", html)
    assert '<section class="story" id="acme-releases-model-x-friends">' in html
    assert "Model &lt;X&gt; &amp; friends" in html  # autoescaped
    assert "prefers-color-scheme: dark" in html and 'name="viewport"' in html


def test_index_snapshot():
    html = pages.render_index([{"date": "2026-10-12", "count": 2}, {"date": "2026-10-11", "count": 1}])
    check_snapshot("index.html", html)
    assert html.index("2026-10-12.html") < html.index("2026-10-11.html")


def test_slack_payload_snapshot(record):
    payloads = slack.build(record, BASE)
    check_snapshot("slack.json", json.dumps(payloads, indent=2, ensure_ascii=False) + "\n")
    (p,) = payloads
    assert p["text"].startswith("AI Briefing for 2026-10-12")
    assert p["blocks"][0]["type"] == "header"
    sections = [b["text"]["text"] for b in p["blocks"] if b["type"] == "section"]
    assert sections[0].startswith("*AI Models &amp; Releases*")  # fixed order: models before jobs
    assert sections[1].startswith("*AI Jobs &amp; Career Opportunities*")
    assert "• Acme releases Model &lt;X&gt; &amp; friends  <https://ethany1017.github.io/ai-briefing/2026-10-12.html#acme-releases-model-x-friends|Explained> · <https://acme.example/blog/model-x?a=1&b=2|Source>" in sections[0]
    assert "https://jobs.example/1%7C2|Source" in sections[1]


def test_slack_splits_long_categories(record):
    it = record["items"][0]
    record["items"] = [dict(it, headline=f"{'Long headline ' * 12}{n}", anchor=f"a{n}") for n in range(40)]
    payloads = slack.build(record, BASE)
    sections = [b for p in payloads for b in p["blocks"] if b["type"] == "section"]
    assert len(sections) > 1
    assert all(len(s["text"]["text"]) < 3000 for s in sections)
    assert sum(s["text"]["text"].count("•") for s in sections) == 40


def test_slack_empty_day(record):
    record["items"] = []
    (p,) = slack.build(record, BASE)
    assert p["text"] == "No notable AI news today (2026-10-12)."
    assert len(p["blocks"]) == 2


def test_pages_write(tmp_path, record):
    written = pages.write(record, [{"date": "2026-10-12", "count": 2}], tmp_path)
    assert (tmp_path / ".nojekyll").exists()
    assert {p.name for p in written} == {"2026-10-12.html", "index.html"}
