"""Post a stored briefing to Slack and record it in data/slack_status.json."""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from . import config, store
from .errors import BriefingError
from .render import slack


def load_status(path: Path = config.SLACK_STATUS_FILE) -> dict:
    path = Path(path)
    return json.loads(path.read_text() or "{}") if path.exists() else {}


def save_status(status: dict, path: Path = config.SLACK_STATUS_FILE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(status.items())), indent=1) + "\n")


def send(payloads: list[dict], webhook: str, sender=requests.post) -> None:
    for i, payload in enumerate(payloads, 1):
        try:
            resp = sender(webhook, json=payload, timeout=20)
        except requests.RequestException as e:
            raise BriefingError(f"Slack request failed: {type(e).__name__}")
        if resp.status_code // 100 != 2:
            raise BriefingError(f"Slack returned {resp.status_code} on message {i}/{len(payloads)}: {resp.text[:120]}")


def post(day: str, dry_run: bool, *, data_dir: Path = config.DATA_DIR, status_path: Path = config.SLACK_STATUS_FILE,
         webhook: str | None = None, sender=requests.post, now_iso: str | None = None) -> str:
    """Returns one of: "posted", "already-posted", "dry-run"."""
    status = load_status(status_path)
    if day in status and not dry_run:
        print(f"{day} already posted to Slack at {status[day]}; nothing to do")
        return "already-posted"
    record = store.load_record(day, data_dir)
    if record is None:
        raise BriefingError(f"no briefing data for {day} (data/{day}.json missing)")
    payloads = slack.build(record)
    if dry_run:
        print(json.dumps(payloads, indent=2, ensure_ascii=False))
        return "dry-run"
    webhook = webhook or os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        raise BriefingError("SLACK_WEBHOOK_URL is not set")
    send(payloads, webhook, sender)
    status[day] = now_iso or config.now().isoformat(timespec="seconds")
    save_status(status, status_path)
    print(f"posted {len(record['items'])} stories for {day} to Slack ({len(payloads)} message(s))")
    return "posted"
