"""CLI: python -m briefing {fetch|run|post}."""
from __future__ import annotations

import argparse
import logging
import sys

from . import config, fetch, sources


def cmd_fetch(args) -> int:
    items, report = fetch.fetch_all(sources.load_sources())
    print(fetch.format_report(report))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="briefing")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="fetch all sources and report which worked")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    return {"fetch": cmd_fetch}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
