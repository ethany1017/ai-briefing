from __future__ import annotations

import json

import pytest

from briefing import __main__ as cli
from briefing import config, pipeline, post
from briefing.errors import BriefingError

DAY = "2026-10-12"
ITEMS = [
    {"title": "OpenAI ships GPT-6", "url": "https://openai.com/gpt-6?utm_source=rss", "source": "OpenAI", "published": "2026-10-12T10:00:00+00:00", "snippet": "s1"},
    {"title": "EU passes AI rules", "url": "https://eu.example/ai", "source": "EU", "published": "2026-10-12T09:00:00+00:00", "snippet": "s2"},
    {"title": "Old seen story", "url": "https://seen.example/x", "source": "X", "published": "2026-10-12T08:00:00+00:00", "snippet": "s3"},
]
REPORT = [{"name": "OpenAI", "ok": True, "raw": 1, "kept": 1, "error": None}, {"name": "FTC", "ok": False, "raw": 0, "kept": 0, "error": "404"}]


@pytest.fixture
def paths(tmp_path):
    return pipeline.Paths(
        data=tmp_path / "data", docs=tmp_path / "docs", briefings=tmp_path / "briefings",
        tmp=tmp_path / ".tmp", seen=tmp_path / "data" / "seen.json", slack_status=tmp_path / "data" / "slack_status.json",
    )


class Calls:
    def __init__(self):
        self.rank_input = None
        self.explain_input = None

    def fetcher(self):
        return [dict(i) for i in ITEMS], REPORT

    def ranker(self, cands):
        self.rank_input = cands
        ids = {c["title"]: c["id"] for c in cands}
        return [
            {"id": ids["EU passes AI rules"], "category": "AI Government & Regulations", "headline": "EU passes AI rules"},
            {"id": ids["OpenAI ships GPT-6"], "category": "AI Models & Releases", "headline": "OpenAI ships GPT-6"},
        ]

    def extractor(self, chosen):
        return {c["id"]: "full text" for c in chosen}

    def explainer(self, stories):
        self.explain_input = stories
        return {s["id"]: {"what_happened": "a", "why_it_matters": "b", "what_it_means_for_you": "c"} for s in stories}

    def kw(self):
        return dict(fetcher=self.fetcher, ranker=self.ranker, extractor=self.extractor, explainer=self.explainer)


def seed(paths, data):
    paths.seen.parent.mkdir(parents=True, exist_ok=True)
    paths.seen.write_text(json.dumps(data))


def test_bootstrap_seeds_and_skips_claude(paths):
    calls = Calls()
    assert pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw()) == "bootstrap"
    assert calls.rank_input is None
    seen = json.loads(paths.seen.read_text())
    assert "https://openai.com/gpt-6" in seen and len(seen) == 3
    assert not (paths.data / f"{DAY}.json").exists()
    assert (paths.tmp / "run_state").read_text().strip() == "bootstrap"


def test_full_run_writes_everything_and_updates_seen(paths):
    seed(paths, {"https://seen.example/x": "2026-10-11", "https://ancient.example": "2026-01-01"})
    calls = Calls()
    assert pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw()) == "built"
    assert [c["title"] for c in calls.rank_input] == ["OpenAI ships GPT-6", "EU passes AI rules"]
    assert all(s["text"] == "full text" for s in calls.explain_input)
    rec = json.loads((paths.data / f"{DAY}.json").read_text())
    assert [i["category"] for i in rec["items"]] == ["AI Models & Releases", "AI Government & Regulations"]
    assert rec["items"][0]["url"] == "https://openai.com/gpt-6?utm_source=rss"
    assert rec["stats"]["sources_ok"] == 1 and rec["stats"]["failed_sources"] == ["FTC"]
    assert (paths.docs / f"{DAY}.html").exists() and (paths.docs / "index.html").exists()
    assert (paths.briefings / f"{DAY}.md").exists()
    seen = json.loads(paths.seen.read_text())
    assert "https://openai.com/gpt-6" in seen and "https://ancient.example" not in seen  # pruned


def test_rerun_skips_when_posted_or_built(paths):
    seed(paths, {})
    calls = Calls()
    pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw())
    assert pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw()) == "skipped-built"
    post.save_status({DAY: "2026-10-12T08:00:00-07:00"}, paths.slack_status)
    assert pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw()) == "skipped-posted"
    assert pipeline.run(pipeline.RunOptions(DAY, force=True), paths, **calls.kw()) == "built"
    assert DAY not in post.load_status(paths.slack_status)  # force => post again


def test_no_seen_ignores_and_never_writes(paths):
    calls = Calls()
    assert pipeline.run(pipeline.RunOptions(DAY, no_seen=True), paths, **calls.kw()) == "built"
    assert len(calls.rank_input) == 3
    assert not paths.seen.exists()


def test_dry_run_prints_payload_and_keeps_seen(paths, capsys):
    seed(paths, {})
    pipeline.run(pipeline.RunOptions(DAY, dry_run=True), paths, **Calls().kw())
    out = capsys.readouterr().out
    assert "Slack payload (dry run" in out and '"type": "header"' in out
    assert json.loads(paths.seen.read_text()) == {}


def test_hallucinated_url_guard(paths):
    calls = Calls()

    def evil_ranker(cands):
        for c in cands:  # simulate a bug that rewrites a URL after fetch
            c["url"] = "https://invented.example/" + str(c["id"])
        return Calls.ranker(calls, cands)

    kw = calls.kw()
    kw["ranker"] = evil_ranker
    with pytest.raises(BriefingError, match="not in the fetched set"):
        pipeline.run(pipeline.RunOptions(DAY, no_seen=True), paths, **kw)


def test_zero_candidates_builds_empty_day(paths):
    seed(paths, {"https://openai.com/gpt-6": "d", "https://eu.example/ai": "d", "https://seen.example/x": "d"})
    calls = Calls()
    assert pipeline.run(pipeline.RunOptions(DAY), paths, **calls.kw()) == "built"
    assert calls.rank_input is None
    assert json.loads((paths.data / f"{DAY}.json").read_text())["items"] == []


# ---- post -------------------------------------------------------------------

class Resp:
    def __init__(self, code, text="ok"):
        self.status_code, self.text = code, text


def write_day(paths):
    paths.data.mkdir(parents=True, exist_ok=True)
    (paths.data / f"{DAY}.json").write_text(json.dumps({"date": DAY, "items": [], "stats": {}}))


def test_post_success_records_status(paths):
    write_day(paths)
    sent = []
    res = post.post(DAY, False, data_dir=paths.data, status_path=paths.slack_status, webhook="https://hooks.example/x",
                    sender=lambda url, json, timeout: sent.append(json) or Resp(200), now_iso="T")
    assert res == "posted" and len(sent) == 1
    assert post.load_status(paths.slack_status) == {DAY: "T"}
    again = post.post(DAY, False, data_dir=paths.data, status_path=paths.slack_status, webhook="https://hooks.example/x",
                      sender=lambda *a, **k: pytest.fail("should not send"))
    assert again == "already-posted"


def test_post_dry_run_never_sends(paths, capsys):
    write_day(paths)
    assert post.post(DAY, True, data_dir=paths.data, status_path=paths.slack_status,
                     sender=lambda *a, **k: pytest.fail("sent")) == "dry-run"
    assert "No notable AI news today" in capsys.readouterr().out
    assert not paths.slack_status.exists()


def test_post_slack_4xx_fails_and_leaves_status(paths):
    write_day(paths)
    with pytest.raises(BriefingError, match="Slack returned 404"):
        post.post(DAY, False, data_dir=paths.data, status_path=paths.slack_status, webhook="https://hooks.example/x",
                  sender=lambda *a, **k: Resp(404, "no_service"))
    assert post.load_status(paths.slack_status) == {}


def test_post_requires_data_and_webhook(paths, monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    with pytest.raises(BriefingError, match="no briefing data"):
        post.post(DAY, False, data_dir=paths.data, status_path=paths.slack_status)
    write_day(paths)
    with pytest.raises(BriefingError, match="SLACK_WEBHOOK_URL is not set"):
        post.post(DAY, False, data_dir=paths.data, status_path=paths.slack_status)


# ---- CLI failure reason -------------------------------------------------------

def test_cli_writes_failure_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "TMP_DIR", tmp_path)
    monkeypatch.setattr(config, "FAILURE_FILE", tmp_path / "failure_reason")
    assert cli.main(["post", "--date", "nope"]) == 1
    assert (tmp_path / "failure_reason").read_text().strip() == "--date must be YYYY-MM-DD, got 'nope'"
    assert "Briefing failed:" in capsys.readouterr().err
