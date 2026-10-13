"""CLI: python -m briefing {run|post|fetch}. On failure writes .tmp/failure_reason and exits 1."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date

from . import config, fetch, pipeline, post, sources
from .errors import BriefingError


def _env_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes")


def _day(value: str | None) -> str:
    if value is None:
        return config.today().isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise BriefingError(f"--date must be YYYY-MM-DD, got {value!r}")


def cmd_fetch(args) -> int:
    _, report = fetch.fetch_all(sources.load_sources())
    print(fetch.format_report(report))
    return 0


def cmd_run(args) -> int:
    opts = pipeline.RunOptions(
        day=_day(args.date), dry_run=args.dry_run or _env_dry_run(), force=args.force, no_seen=args.no_seen
    )
    pipeline.run(opts)
    return 0


def cmd_post(args) -> int:
    post.post(_day(args.date), dry_run=args.dry_run or _env_dry_run())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m briefing")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="build today's briefing (data/, briefings/, docs/)")
    r.add_argument("--date", help="label for the briefing, YYYY-MM-DD (default: today in America/Phoenix)")
    r.add_argument("--dry-run", action="store_true", help="always rebuild, never write seen.json, print the Slack payload")
    r.add_argument("--force", action="store_true", help="rebuild even if already built/posted, and post again")
    r.add_argument("--no-seen", action="store_true", help="ignore data/seen.json and never write it")
    s = sub.add_parser("post", help="post a stored briefing to Slack")
    s.add_argument("--date", help="YYYY-MM-DD (default: today in America/Phoenix)")
    s.add_argument("--dry-run", action="store_true", help="print the payload instead of posting")
    sub.add_parser("fetch", help="fetch all sources and report which worked")
    return p


def write_failure(reason: str) -> None:
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    config.FAILURE_FILE.write_text(" ".join(reason.split())[:300] + "\n")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        from dotenv import load_dotenv

        load_dotenv(config.ROOT / ".env", override=False)
    except ImportError:
        pass
    args = build_parser().parse_args(argv)
    try:
        return {"run": cmd_run, "post": cmd_post, "fetch": cmd_fetch}[args.cmd](args)
    except BriefingError as e:
        reason = str(e)
    except Exception as e:  # unexpected bug: still leave a reason for the Slack alert
        logging.exception("unexpected error")
        reason = f"{args.cmd}: unexpected {type(e).__name__}: {e}"
    write_failure(reason)
    print(f"Briefing failed: {reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
