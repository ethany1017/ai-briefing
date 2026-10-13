from __future__ import annotations

from datetime import date

from briefing import seen
from briefing.dedupe import canonical_url, dedupe, normalize_title


def item(title, url, source="S"):
    return {"title": title, "url": url, "source": source, "published": "2026-10-12T10:00:00+00:00", "snippet": ""}


def test_canonical_strips_tracking_fragment_slash_www():
    assert canonical_url("http://www.Example.com/a/b/?utm_source=x&b=2&a=1#frag") == "https://example.com/a/b?a=1&b=2"
    assert canonical_url("https://example.com/a/") == canonical_url("https://example.com/a")
    assert canonical_url("https://example.com/?ref=hn") == "https://example.com"


def test_normalize_title():
    assert normalize_title("  OpenAI's GPT-6: Released!  ") == "openai s gpt 6 released"


def test_dedupe_by_url_keeps_first():
    out = dedupe([item("A", "https://x.com/1?utm_medium=rss", "first"), item("B", "https://x.com/1/", "second")])
    assert len(out) == 1 and out[0]["source"] == "first"
    assert out[0]["canonical"] == "https://x.com/1"
    assert out[0]["url"] == "https://x.com/1?utm_medium=rss"  # original URL preserved


def test_dedupe_by_near_identical_title():
    out = dedupe(
        [
            item("OpenAI releases GPT-6 today", "https://a.com/1"),
            item("OpenAI Releases GPT-6 Today!", "https://b.com/2"),
            item("OpenAI releases GPT-6 todays", "https://c.com/3"),
            item("Google releases Gemini 4", "https://d.com/4"),
        ]
    )
    assert [o["url"] for o in out] == ["https://a.com/1", "https://d.com/4"]


def test_dedupe_against_seen():
    out = dedupe([item("A", "https://x.com/1"), item("B", "https://x.com/2")], {"https://x.com/1": "2026-10-01"})
    assert [o["url"] for o in out] == ["https://x.com/2"]


def test_seen_roundtrip_add_prune(tmp_path):
    p = tmp_path / "data" / "seen.json"
    assert seen.load(p) is None
    s = seen.add({}, ["https://a", "https://b"], date(2026, 8, 1))
    s = seen.add(s, ["https://a", "https://c"], date(2026, 10, 12))
    assert s == {"https://a": "2026-08-01", "https://b": "2026-08-01", "https://c": "2026-10-12"}
    s = seen.prune(s, date(2026, 10, 12))
    assert s == {"https://c": "2026-10-12"}
    seen.save(s, p)
    assert seen.load(p) == s
