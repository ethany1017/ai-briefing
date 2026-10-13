from __future__ import annotations

import json
import subprocess

import pytest

from briefing import claude_cli, explain, extract, rank, store
from briefing.errors import BriefingError

CANDS = [
    {"id": 1, "title": "OpenAI ships GPT-6", "url": "https://openai.com/gpt-6", "source": "OpenAI", "published": "2026-10-12T10:00:00+00:00", "snippet": "New model."},
    {"id": 2, "title": "EU passes AI rules", "url": "https://eu.example/ai", "source": "EU", "published": "2026-10-12T09:00:00+00:00", "snippet": "Rules."},
    {"id": 3, "title": "Junior ML Engineer at Acme", "url": "https://jobs.example/1", "source": "Remotive", "published": "2026-10-12T08:00:00+00:00", "snippet": "Entry level."},
]


class FakeClaude:
    """Returns queued replies in order and records prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


# ---- claude_cli -------------------------------------------------------------

def test_parse_model_json_tolerates_fences_and_prose():
    assert claude_cli.parse_model_json('```json\n[{"id": 1}]\n```') == [{"id": 1}]
    assert claude_cli.parse_model_json('Here you go:\n[{"id": 2}]\nThanks') == [{"id": 2}]
    with pytest.raises(ValueError):
        claude_cli.parse_model_json("no json here")


def test_command_disables_tools():
    cmd = claude_cli.COMMAND
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-5-5"
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--output-format") + 1] == "json"


def test_run_cli_parses_envelope(monkeypatch):
    def fake_run(cmd, input, **kw):
        assert input == "PROMPT"
        return subprocess.CompletedProcess(cmd, 0, json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "[1]"}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert claude_cli.run_cli("PROMPT") == "[1]"


def test_run_cli_error_envelope(monkeypatch):
    def fake_run(cmd, input, **kw):
        return subprocess.CompletedProcess(cmd, 1, json.dumps({"subtype": "success", "is_error": True, "result": "Invalid API key"}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BriefingError, match="Invalid API key"):
        claude_cli.run_cli("x")


def test_run_cli_non_json_stdout(monkeypatch):
    def fake_run(cmd, input, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "OAuth token expired\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(BriefingError, match="OAuth token expired"):
        claude_cli.run_cli("x")


# ---- rank -------------------------------------------------------------------

def test_rank_drops_hallucinated_id_invalid_category_dupes_and_urls():
    reply = json.dumps([
        {"id": 1, "category": "AI Models & Releases", "headline": "OpenAI releases GPT-6"},
        {"id": 99, "category": "AI Models & Releases", "headline": "Hallucinated story"},
        {"id": 2, "category": "AI Politics", "headline": "Invalid category"},
        {"id": 1, "category": "AI Open Source", "headline": "Duplicate id"},
        {"id": "3", "category": "AI Jobs & Career Opportunities", "headline": "Acme hires junior ML engineers"},
        {"id": 2, "category": "AI Government & Regulations", "headline": "See https://evil.example"},
    ])
    fake = FakeClaude(reply)
    out = rank.rank(CANDS, runner=fake)
    assert out == [
        {"id": 1, "category": "AI Models & Releases", "headline": "OpenAI releases GPT-6"},
        {"id": 3, "category": "AI Jobs & Career Opportunities", "headline": "Acme hires junior ML engineers"},
    ]
    assert len(fake.prompts) == 1
    assert "https://openai.com" not in fake.prompts[0]  # Claude never sees URLs


def test_rank_retries_once_then_succeeds():
    fake = FakeClaude("sorry, I can't", '[{"id": 2, "category": "AI Government & Regulations", "headline": "EU passes AI rules"}]')
    out = rank.rank(CANDS, runner=fake)
    assert [o["id"] for o in out] == [2]
    assert len(fake.prompts) == 2 and "PREVIOUS REPLY WAS INVALID" in fake.prompts[1]


def test_rank_fails_after_two_bad_replies():
    with pytest.raises(BriefingError, match="rank: Claude returned invalid JSON twice"):
        rank.rank(CANDS, runner=FakeClaude("nope", '{"not": "a list", "x": 1}'))


def test_rank_caps_at_max(monkeypatch):
    monkeypatch.setattr(rank.config, "MAX_STORIES", 2)
    reply = json.dumps([{"id": i, "category": "AI Open Source", "headline": f"h{i}"} for i in (1, 2, 3)])
    assert len(rank.rank(CANDS, runner=FakeClaude(reply))) == 2


def test_rank_empty_day_is_valid():
    assert rank.rank(CANDS, runner=FakeClaude("[]")) == []
    assert rank.rank([], runner=FakeClaude()) == []


def test_rank_prompt_lists_all_categories():
    p = rank.build_prompt(CANDS)
    for c in rank.config.CATEGORIES:
        assert c in p


# ---- explain ----------------------------------------------------------------

STORIES = [dict(c, headline=c["title"], text="body " * 10) for c in CANDS[:2]]


def test_explain_prompt_is_generic_and_strips_nothing_personal():
    p = explain.build_prompt(STORIES)
    assert "a CS student / early-career software engineer" in p
    assert "Use ONLY the supplied text" in p
    assert "https://" not in p


def test_explain_validates_and_strips_urls():
    reply = json.dumps([
        {"id": 1, "what_happened": "A thing (https://x.example/y) happened.", "why_it_matters": "B.", "what_it_means_for_you": "C."},
        {"id": 2, "what_happened": "D.", "why_it_matters": "E.", "what_it_means_for_you": "F."},
        {"id": 77, "what_happened": "ghost", "why_it_matters": "ghost", "what_it_means_for_you": "ghost"},
    ])
    out = explain.explain(STORIES, runner=FakeClaude(reply))
    assert set(out) == {1, 2}
    assert "http" not in out[1]["what_happened"]
    assert out[1]["what_happened"] == "A thing happened."


def test_explain_retries_when_most_missing():
    bad = json.dumps([{"id": 1, "what_happened": "", "why_it_matters": "", "what_it_means_for_you": ""}])
    good = "```json\n" + json.dumps([{"id": i, "what_happened": "a", "why_it_matters": "b", "what_it_means_for_you": "c"} for i in (1, 2)]) + "\n```"
    fake = FakeClaude(bad, good)
    assert set(explain.explain(STORIES, runner=fake)) == {1, 2}
    assert len(fake.prompts) == 2


# ---- extract ----------------------------------------------------------------

def test_extract_caps_and_falls_back_to_snippet():
    long_html = ("<html><body><article><h1>T</h1>" + "<p>" + ("Sentence about models. " * 400) + "</p></article></body></html>").encode()
    texts = extract.extract_all(
        [{"id": 1, "url": "https://a", "snippet": "s1"}, {"id": 2, "url": "https://b", "snippet": "snippet two"}],
        getter=lambda url: long_html if url == "https://a" else (_ for _ in ()).throw(IOError("down")),
    )
    assert 1000 < len(texts[1]) <= 4000
    assert texts[2] == "snippet two"


# ---- store ------------------------------------------------------------------

def test_build_record_joins_by_id_orders_by_category_and_guards_urls(tmp_path):
    ranked = [
        {"id": 3, "category": "AI Jobs & Career Opportunities", "headline": "Acme hires"},
        {"id": 1, "category": "AI Models & Releases", "headline": "GPT-6 is out"},
        {"id": 2, "category": "AI Models & Releases", "headline": "GPT-6 is out"},
    ]
    explained = {i: {"what_happened": "a", "why_it_matters": "b", "what_it_means_for_you": "c"} for i in (1, 2, 3)}
    rec = store.build_record("2026-10-12", CANDS, ranked, explained, {"candidates": 3}, "2026-10-12T07:50:00-07:00")
    assert [i["id"] for i in rec["items"]] == [1, 2, 3]
    assert [i["anchor"] for i in rec["items"]] == ["gpt-6-is-out", "gpt-6-is-out-2", "acme-hires"]
    assert rec["items"][0]["url"] == "https://openai.com/gpt-6"
    assert rec["stats"] == {"candidates": 3, "selected": 3}
    store.assert_urls_fetched(rec, {c["url"] for c in CANDS})
    rec["items"][0]["url"] = "https://invented.example"
    with pytest.raises(BriefingError, match="not in the fetched set"):
        store.assert_urls_fetched(rec, {c["url"] for c in CANDS})
    store.write_record(rec, tmp_path)
    assert store.load_record("2026-10-12", tmp_path)["date"] == "2026-10-12"
    assert store.list_days(tmp_path) == [{"date": "2026-10-12", "count": 3}]


def test_build_record_skips_unexplained():
    ranked = [{"id": 1, "category": "AI Models & Releases", "headline": "x"}]
    rec = store.build_record("2026-10-12", CANDS, ranked, {}, {}, "t")
    assert rec["items"] == []


def test_slugify_cuts_on_word_boundary():
    s = store.slugify("Meta releases Muse Wonder, its first frontier model, larger and more capable than before")
    assert s == "meta-releases-muse-wonder-its-first-frontier-model-larger"
    assert len(s) <= 60 and store.slugify("!!!") == "story"
    assert store.slugify("x" * 80) == "x" * 60
