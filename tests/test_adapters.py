from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from briefing import adapters
from briefing.adapters.text import clean, parse_iso

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_bytes()


def test_rss_parses_title_link_date_and_strips_html():
    items = adapters.parse("rss", load("rss_sample.xml"))
    assert len(items) == 4
    first = items[0]
    assert first["title"] == "OpenAI ships a new model"
    assert first["url"] == "https://example.com/a?utm_source=rss"
    assert first["published"] == datetime(2026, 10, 12, 10, tzinfo=timezone.utc)
    assert first["snippet"] == "A new AI model."
    assert items[2]["published"] is None


def test_atom_parses():
    (item,) = adapters.parse("rss", load("atom_sample.xml"))
    assert item["url"] == "https://example.org/release/5"
    assert item["published"] == datetime(2026, 10, 12, 8, 30, tzinfo=timezone.utc)


def test_garbage_feed_raises():
    with pytest.raises(ValueError):
        adapters.parse("rss", b"this is not xml at all <<<")


def test_hn_algolia_falls_back_to_hn_link():
    a, b = adapters.parse("hn_algolia", load("hn_algolia.json"))
    assert a["url"] == "https://hn-example.com/x"
    assert a["published"].tzinfo is not None
    assert b["url"] == "https://news.ycombinator.com/item?id=222"
    assert b["published"] == datetime(2026, 10, 12, 7, tzinfo=timezone.utc)


def test_hf_daily_papers_links_to_hf_papers_and_skips_missing_id():
    (p,) = adapters.parse("hf_daily_papers", load("hf_daily_papers.json"))
    assert p["url"] == "https://huggingface.co/papers/2610.01234"
    assert p["published"].date().isoformat() == "2026-10-12"


def test_hf_trending_models_uses_created_then_last_modified():
    a, b = adapters.parse("hf_trending_models", load("hf_trending_models.json"))
    assert a["url"] == "https://huggingface.co/acme/tiny-llm-7b"
    assert a["published"] == datetime(2026, 10, 11, 18, tzinfo=timezone.utc)
    assert b["url"] == "https://huggingface.co/acme/old"
    assert b["published"] == datetime(2026, 10, 12, 1, tzinfo=timezone.utc)


def test_github_search():
    (r,) = adapters.parse("github_search", load("github_search.json"))
    assert r["url"] == "https://github.com/acme/agent-kit"
    assert "900 stars" in r["snippet"]


def test_federal_register_date_only():
    (d,) = adapters.parse("federal_register", load("federal_register.json"))
    assert d["published"] is not None and d["published"].tzinfo is not None
    assert "Commerce Department" in d["snippet"]


def test_remotive():
    (j,) = adapters.parse("remotive", load("remotive.json"))
    assert j["title"] == "Junior ML Engineer at Acme"
    assert "Entry level role" in j["snippet"]


def test_unknown_kind():
    with pytest.raises(ValueError):
        adapters.parse("nope", b"{}")


def test_clean_caps_length():
    assert len(clean("x" * 1000, 500)) == 500


def test_parse_iso_variants():
    assert parse_iso("2026-10-12T03:15:22.123456789Z").replace(microsecond=0) == datetime(2026, 10, 12, 3, 15, 22, tzinfo=timezone.utc)
    assert parse_iso("garbage") is None
    assert parse_iso(None) is None
