"""The `run` command: fetch -> dedupe -> rank -> extract -> explain -> store -> render.

Writes the run's outcome to .tmp/run_state (one word) for the workflow:
  bootstrap | built | skipped-posted | skipped-built
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from . import config, dedupe, explain, extract, fetch, post, rank, seen, sources, store
from .errors import BriefingError
from .render import markdown, pages, slack

log = logging.getLogger(__name__)


@dataclass
class RunOptions:
    day: str
    dry_run: bool = False
    force: bool = False
    no_seen: bool = False


@dataclass
class Paths:
    data: Path = config.DATA_DIR
    docs: Path = config.DOCS_DIR
    briefings: Path = config.BRIEFINGS_DIR
    tmp: Path = config.TMP_DIR
    seen: Path = config.SEEN_FILE
    slack_status: Path = config.SLACK_STATUS_FILE


def _state(paths: Paths, state: str) -> str:
    Path(paths.tmp).mkdir(parents=True, exist_ok=True)
    (Path(paths.tmp) / "run_state").write_text(state + "\n")
    print(f"run state: {state}")
    return state


def run(opts: RunOptions, paths: Paths = Paths(), *, fetcher=None, ranker=None, explainer=None, extractor=None) -> str:
    fetcher = fetcher or (lambda: fetch.fetch_all(sources.load_sources()))
    ranker = ranker or rank.rank
    explainer = explainer or explain.explain
    extractor = extractor or extract.extract_all
    day = opts.day

    # Re-run handling (see README): skip when already built/posted unless forced.
    if not opts.force and not opts.dry_run:
        status = post.load_status(paths.slack_status)
        if day in status:
            print(f"{day} already built and posted; nothing to do (use --force to rebuild)")
            return _state(paths, "skipped-posted")
        if store.day_path(day, paths.data).exists():
            print(f"{day} already built but not posted; skipping generation, `post` will send it")
            return _state(paths, "skipped-built")

    items, report = fetcher()
    print(fetch.format_report(report))
    ok_sources = sum(1 for r in report if r["ok"])

    use_seen = not opts.no_seen
    seen_map = seen.load(paths.seen) if use_seen else None
    if use_seen and seen_map is None and not opts.dry_run:
        seeded = seen.add({}, {dedupe.canonical_url(i["url"]) for i in items}, date.fromisoformat(day))
        seen.save(seeded, paths.seen)
        print(f"bootstrap: seeded {paths.seen} with {len(seeded)} URLs; no Claude call, no Slack post")
        return _state(paths, "bootstrap")

    candidates = dedupe.dedupe(items, seen_map or {})
    for i, c in enumerate(candidates, 1):
        c["id"] = i
    print(f"{len(items)} fetched items -> {len(candidates)} candidates after dedupe")

    ranked = ranker(candidates) if candidates else []
    print(f"rank: {len(ranked)} stories selected")
    by_id = {c["id"]: c for c in candidates}
    chosen = [dict(by_id[r["id"]], headline=r["headline"]) for r in ranked]
    texts = extractor(chosen) if chosen else {}
    stories = [dict(c, text=texts.get(c["id"]) or c["snippet"]) for c in chosen]
    explained = explainer(stories) if stories else {}

    stats = {
        "sources_total": len(report),
        "sources_ok": ok_sources,
        "failed_sources": sorted(r["name"] for r in report if not r["ok"]),
        "fetched": len(items),
        "candidates": len(candidates),
        "ranked": len(ranked),
    }
    record = store.build_record(day, candidates, ranked, explained, stats, config.now().isoformat(timespec="seconds"))
    store.assert_urls_fetched(record, {i["url"] for i in items})

    store.write_record(record, paths.data)
    markdown.write(record, paths.briefings)
    pages.write(record, store.list_days(paths.data), paths.docs)
    print(f"wrote data/{day}.json, briefings/{day}.md, docs/{day}.html ({len(record['items'])} stories)")

    if use_seen and not opts.dry_run:
        updated = seen.add(seen_map or {}, {dedupe.canonical_url(i["url"]) for i in items}, date.fromisoformat(day))
        seen.save(seen.prune(updated, date.fromisoformat(day)), paths.seen)

    if opts.force and not opts.dry_run:
        status = post.load_status(paths.slack_status)
        if status.pop(day, None) is not None:
            post.save_status(status, paths.slack_status)
            print(f"--force: cleared Slack status for {day} so `post` sends again")

    if opts.dry_run:
        print("--- Slack payload (dry run, not posted) ---")
        print(json.dumps(slack.build(record), indent=2, ensure_ascii=False))
    return _state(paths, "built")
