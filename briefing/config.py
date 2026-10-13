"""Static configuration: paths, limits, categories, timezone."""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
BRIEFINGS_DIR = ROOT / "briefings"
TMP_DIR = ROOT / ".tmp"
TEMPLATES_DIR = ROOT / "templates"
SOURCES_FILE = ROOT / "sources.yaml"
SEEN_FILE = DATA_DIR / "seen.json"
SLACK_STATUS_FILE = DATA_DIR / "slack_status.json"
FAILURE_FILE = TMP_DIR / "failure_reason"

TZ = ZoneInfo("America/Phoenix")

MODEL = "claude-sonnet-5-5"
PAGES_BASE_URL = os.environ.get("PAGES_BASE_URL", "https://ethany1017.github.io/ai-briefing/")

WINDOW_HOURS = 36
ARTICLE_CHARS = 4000
SNIPPET_CHARS = 500
FETCH_TIMEOUT = 20
MIN_SOURCES_OK = 10
SEEN_PRUNE_DAYS = 60
CLAUDE_TIMEOUT = 600

USER_AGENT = "ai-briefing/1.0 (+https://github.com/ethany1017/ai-briefing)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)

CATEGORIES = [
    "AI Models & Releases",
    "AI Agents & Automation",
    "AI Coding & Developer Tools",
    "AI Startups & Y Combinator",
    "AI Business & Industry Adoption",
    "AI Research & Breakthroughs",
    "AI Hardware & Infrastructure",
    "AI Finance & Investments",
    "AI Government & Regulations",
    "AI Open Source",
    "AI Jobs & Career Opportunities",
    "AI Security & Safety",
]

# Selection caps: up to MAX_PER_CATEGORY stories per category (never padded), so at most
# MAX_TOTAL a day. MAX_TOTAL is a safety net derived from the per-category cap.
MAX_PER_CATEGORY = 5
MAX_TOTAL = MAX_PER_CATEGORY * len(CATEGORIES)  # 60

EXPLAIN_CHUNK = 12    # stories per explain call (keeps each prompt/reply a sane size)
EXPLAIN_WORKERS = 1   # explain calls in flight at once
EXTRACT_WORKERS = 8   # parallel article fetches in extract.py


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()
