from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from briefing import fetch
from briefing.errors import BriefingError
from briefing.sources import load_sources

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 12, 14, 45, tzinfo=timezone.utc)


def src(name="S", kind="rss", ai_filter=False, url="https://feed/{since}", max_items=25):
    return {"name": name, "url": url, "kind": kind, "ai_filter": ai_filter, "max_items": max_items}


def test_normalize_drops_old_undated_and_offtopic():
    getter = lambda url: (FIX / "rss_sample.xml").read_bytes()
    report, items = fetch.fetch_one(src(ai_filter=True), NOW, getter)
    assert report["ok"] and report["raw"] == 4
    assert [i["title"] for i in items] == ["OpenAI ships a new model"]
    assert items[0]["source"] == "S"


def test_no_ai_filter_keeps_offtopic_but_not_undated():
    getter = lambda url: (FIX / "rss_sample.xml").read_bytes()
    _, items = fetch.fetch_one(src(), NOW, getter)
    assert {i["title"] for i in items} == {"OpenAI ships a new model", "Quarterly earnings for a bank"}


def test_max_items_cap_keeps_newest():
    getter = lambda url: (FIX / "rss_sample.xml").read_bytes()
    _, items = fetch.fetch_one(src(max_items=1), NOW, getter)
    assert [i["title"] for i in items] == ["OpenAI ships a new model"]


def test_since_placeholder_resolved():
    assert fetch.resolve_url("q=created:>{since}", date(2026, 10, 12)) == "q=created:>2026-10-05"


def test_source_failure_is_reported_not_raised():
    def boom(url):
        raise TimeoutError("slow")

    report, items = fetch.fetch_one(src(), NOW, boom)
    assert not report["ok"] and "slow" in report["error"] and items == []


def test_fetch_all_requires_min_sources():
    sources = [src(name=f"s{i}") for i in range(12)]

    def getter(url):
        raise IOError("down")

    with pytest.raises(BriefingError, match="sources fetched"):
        fetch.fetch_all(sources, NOW, getter)


def test_fetch_all_fails_on_zero_items():
    sources = [src(name=f"s{i}") for i in range(12)]
    getter = lambda url: b"<rss version='2.0'><channel><title>x</title></channel></rss>"
    with pytest.raises(BriefingError, match="0 items"):
        fetch.fetch_all(sources, NOW, getter)


def test_fetch_all_success():
    sources = [src(name=f"s{i}") for i in range(12)]
    getter = lambda url: (FIX / "rss_sample.xml").read_bytes()
    items, report = fetch.fetch_all(sources, NOW, getter)
    assert len(report) == 12 and len(items) == 24


def test_ai_filter_keywords():
    assert fetch.is_ai("New AI rules")
    assert fetch.is_ai("artificial intelligence act")
    assert fetch.is_ai("LLMs are big")
    assert not fetch.is_ai("Haiti said hi to the main event")
    assert not fetch.is_ai("Quarterly earnings")


def test_sources_yaml_loads():
    sources = load_sources()
    assert len(sources) >= 40
    assert all(s["kind"] for s in sources)
    flagged = {s["name"] for s in sources if s["ai_filter"]}
    assert {"CNBC Tech", "Product Hunt", "White House", "NIST", "FTC", "Meta Engineering"} <= flagged
