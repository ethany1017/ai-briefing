"""Run a prompt through the Claude Code CLI with every tool disabled and parse JSON out.

Command: claude -p --model <MODEL> --output-format json --tools "" --strict-mcp-config
         --setting-sources project      (prompt on stdin)
`--tools ""` disables all built-in tools; `--strict-mcp-config` with no --mcp-config
loads no MCP servers; `--setting-sources project` keeps user-level hooks out.
Auth: the logged-in CLI locally, CLAUDE_CODE_OAUTH_TOKEN in CI.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Callable, TypeVar

from . import config
from .errors import BriefingError

log = logging.getLogger(__name__)
T = TypeVar("T")

COMMAND = [
    "claude", "-p",
    "--model", config.MODEL,
    "--output-format", "json",
    "--tools", "",
    "--strict-mcp-config",
    "--setting-sources", "project",
]

_FENCE = re.compile(r"^\s*```(?:json|JSON)?\s*\n?(.*?)\n?\s*```\s*$", re.S)


def as_id(v) -> int | None:
    """Accept 7 or "7" as an id; anything else (bools, floats, junk) is None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def run_cli(prompt: str, timeout: int = config.CLAUDE_TIMEOUT) -> str:
    """Return the model's text (the envelope's `result`). Raises BriefingError."""
    try:
        proc = subprocess.run(
            COMMAND, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=config.ROOT
        )
    except FileNotFoundError:
        raise BriefingError("claude CLI not found on PATH")
    except subprocess.TimeoutExpired:
        raise BriefingError(f"claude CLI timed out after {timeout}s")
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["no output"]
        raise BriefingError(f"claude CLI exit {proc.returncode}: {tail[0][:200]}")
    if env.get("is_error") or env.get("subtype") != "success":
        raise BriefingError(f"claude CLI error ({env.get('subtype')}): {str(env.get('result'))[:200]}")
    return env.get("result") or ""


def parse_model_json(text: str):
    """Parse the model's JSON, tolerating ```json fences and stray prose around it."""
    s = text.strip()
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (s.find("["), s.find("{")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(s.rfind("]"), s.rfind("}"))
        if end > start:
            return json.loads(s[start : end + 1])
    raise ValueError("no JSON found in model output")


def call_json(
    prompt: str,
    validate: Callable[[object], T],
    what: str,
    runner: Callable[[str], str] = run_cli,
) -> T:
    """Call Claude, parse + validate JSON. One retry on invalid output, then BriefingError."""
    attempt_prompt = prompt
    last = ""
    for attempt in (1, 2):
        text = runner(attempt_prompt)
        try:
            return validate(parse_model_json(text))
        except (ValueError, TypeError, KeyError) as e:
            last = str(e)[:200]
            log.warning("%s: invalid model output (attempt %d): %s", what, attempt, last)
            attempt_prompt = (
                prompt
                + f"\n\nYOUR PREVIOUS REPLY WAS INVALID ({last}). "
                "Reply again with ONLY the JSON described above, no prose, no code fences."
            )
    raise BriefingError(f"{what}: Claude returned invalid JSON twice ({last})")
