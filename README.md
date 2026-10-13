# ai-briefing

A small daily AI news briefing. Every morning around 8:00 Phoenix time a GitHub Action
fetches AI news from known feeds, has Claude pick and categorize the most important
stories (up to 5 per category, never padded, so at most 60), publishes a plain-English
"Explained" page on GitHub Pages, and posts one-line bullets to Slack.

Code does the fetching. Claude only ranks, categorizes and writes, and only about
articles the code fetched. **Claude never outputs a URL**: it refers to stories by
numeric id, and code attaches the URL from the fetched item. The pipeline asserts that
every URL in the output was in that run's fetched set.

## How it works

```
sources.yaml (42 feeds/APIs)
      |
      v
fetch.py ------ parallel, 20s timeout, real User-Agent, gzip
      |         keep items from the last 36h; undated items dropped
      |         site-wide feeds pass an AI keyword filter
      v
dedupe.py ----- canonical URLs (no utm_*, fragments, trailing /),
      |         near-duplicate titles, and anything in data/seen.json
      v
rank.py ------- Claude call 1: [{id, category, headline}] (12 fixed categories,
      |         <= 5 per category best-first, <= 60 total; extras over the cap dropped
      |         in the model's order); unknown ids / bad categories dropped;
      |         bad JSON -> 1 retry -> fail
      v
extract.py ---- full article text for selected stories only (trafilatura), 4000 chars
      |         max, 8 parallel fetches
      v
explain.py ---- Claude calls 2..n: what happened / why it matters / what it means for
      |         you, in chunks of 12 stories (so up to 5 calls), each with 1 retry
      v
store.py ------ data/YYYY-MM-DD.json (URLs joined back by id) + data/seen.json
      v
render/ ------- briefings/YYYY-MM-DD.md, docs/YYYY-MM-DD.html, docs/index.html
      v
post.py ------- Slack Block Kit via incoming webhook; data/slack_status.json
```

Claude runs through the Claude Code CLI with every tool disabled:

```
claude -p --model claude-sonnet-5-5 --output-format json --tools "" --strict-mcp-config --setting-sources project
```

The prompt goes in on stdin. The CLI's JSON envelope `result` is parsed, then the
model's JSON (```json fences tolerated).

Categories, in Slack/page order: AI Models & Releases; AI Agents & Automation; AI Coding &
Developer Tools; AI Startups & Y Combinator; AI Business & Industry Adoption; AI Research &
Breakthroughs; AI Hardware & Infrastructure; AI Finance & Investments; AI Government &
Regulations; AI Open Source; AI Jobs & Career Opportunities; AI Security & Safety.

**How many stories:** each category gets up to 5 bullets (`MAX_PER_CATEGORY` in
`briefing/config.py`), 5 only when there are 5 genuinely worthwhile, distinct stories.
Nothing is padded: a category with 2 real stories shows 2, and a category with nothing
worth reading is left out. One item per real-world event. The ceiling is 12 x 5 = 60 a
day (`MAX_TOTAL`). In Slack that is one message (header, one section per category,
footer: at most 14 blocks); it only splits past Slack's 50-block limit.

### Daily schedule (`.github/workflows/daily.yml`)

Cron `45 14 * * *` UTC (07:45 Phoenix, so GitHub's usual scheduler lag lands near 08:00),
plus a "Run now" `workflow_dispatch` button with `force`, `dry_run` and `ignore_seen`.

1. Install Python 3.12 deps and `@anthropic-ai/claude-code`.
2. `python -m briefing run` (`--force` / `--no-seen` from the inputs).
3. Commit `data/ docs/ briefings/` as `briefing: YYYY-MM-DD`, `git pull --rebase`, push.
4. Wait up to ~3 min for the Pages build of that commit, so Explained links resolve.
5. `python -m briefing post`, then commit `data/slack_status.json` (pull --rebase, push).
6. On any failure, post `Briefing failed: <reason> (<run url>)` to Slack.

A `dry_run` dispatch builds and prints the Slack payload in the log, and commits and
posts nothing.

**First run (bootstrap):** if `data/seen.json` doesn't exist, the run records every
fetched URL in it and stops: no Claude call, no Slack post. Only `seen.json` is
committed. The next run produces a real briefing.

**Re-runs** use `data/slack_status.json` (`{date: posted_at}`):

| State for today | Plain re-run | `force` |
|---|---|---|
| Built and posted | does nothing | rebuilds and posts again |
| Built, not posted (e.g. Slack failed) | skips generation, posts the stored briefing | rebuilds and posts |
| Not built | builds and posts | builds and posts |

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env              # DRY_RUN=1 by default; leave the secrets empty for dry runs
.venv/bin/python -m pytest -q     # fixtures only, no network
.venv/bin/python -m briefing fetch                    # which sources work right now
.venv/bin/python -m briefing run --dry-run --no-seen  # full pipeline, prints the Slack payload
```

Locally the logged-in `claude` CLI is used, so no token is needed. A dry run writes
`data/`, `briefings/` and `docs/` files for today into the working tree. Don't commit
them from a laptop; delete them or `git restore` / `git clean` them.

### Commands and flags

| Command | What it does |
|---|---|
| `run [--date YYYY-MM-DD]` | Build the briefing. `--date` only labels the output; the 36h window is always relative to now. Default date is today in America/Phoenix. |
| `run --dry-run` | Always rebuild, never write `seen.json` (and never bootstrap), print the Slack payload. Also enabled by `DRY_RUN=1`. |
| `run --force` | Rebuild even if already built or posted, and clear today's Slack status so `post` sends again. |
| `run --no-seen` | Ignore `data/seen.json` for filtering and never write it. |
| `post [--date] [--dry-run]` | Post `data/<date>.json` to Slack unless already posted; `--dry-run` prints the payload. Also enabled by `DRY_RUN=1`. |
| `fetch` | Fetch all sources and print which succeeded. |

Any failure writes a one-line reason to `.tmp/failure_reason` and exits non-zero.
`.tmp/run_state` holds one of `bootstrap`, `built`, `skipped-built`, `skipped-posted`
for the workflow.

Optional env: `PAGES_BASE_URL` (default `https://ethany1017.github.io/ai-briefing/`),
`GITHUB_TOKEN` (raises the GitHub search API rate limit; the workflow passes it).

## Setup

### Secrets

Two repository secrets, both set by you. Never commit them; `.env` is gitignored.

```bash
claude setup-token                                               # prints a long-lived OAuth token
gh secret set CLAUDE_CODE_OAUTH_TOKEN -R ethany1017/ai-briefing  # paste it when prompted
gh secret set SLACK_WEBHOOK_URL -R ethany1017/ai-briefing        # Slack app > Incoming Webhooks
```

### GitHub Pages

Settings > Pages > Build and deployment > Source: "Deploy from a branch", branch `main`,
folder `/docs`. `docs/.nojekyll` is already committed. The site is
https://ethany1017.github.io/ai-briefing/.

Or with the CLI:

```bash
gh api -X POST repos/ethany1017/ai-briefing/pages -f 'source[branch]=main' -f 'source[path]=/docs'
```

## Dashboard

Ethan's local agent dashboard (the `My Ai` repo, `tools/dashboard_sync_bots.py`) pulls
from this repo. Nothing here pushes to it, and it needs no secrets. While the dashboard
server is running, every 15 minutes it:

- fetches `briefings/<date>.md` for today and yesterday (Phoenix time) from
  `raw.githubusercontent.com` into the News tab's `ai-news` column, posts "Daily briefing
  ready" with a link to the Pages page, and records the bot's daily heartbeat;
- reads `data/slack_status.json` to say whether the Slack post went out;
- checks the latest completed `daily.yml` run through the public Actions API and raises an
  error in its feed if the run failed, timed out or was cancelled.

If the dashboard isn't running, it catches up on today and yesterday the next time it
starts. Anything older than yesterday isn't back-filled.

## Later (skipped in v1)

- Paywalled: Bloomberg, The Information, Crunchbase, PitchBook, CB Insights
- Needs login or scraping: Reddit r/LocalLLaMA, X/xAI, Reuters, Artificial Analysis (needs an API key)
- No working feed or API: Anthropic News, Meta AI blog, Stanford HAI, The Batch, Claude docs release notes, YC Launches, VentureBeat (returns 429 to bots), Papers with Code (now redirects to HF Papers, which v1 already covers)
- Deferred: the YC companies directory (only an unofficial yc-oss mirror)

## Troubleshooting

**Expired or invalid OAuth token.** Slack shows `Briefing failed: claude CLI error ...`
or `claude CLI exit 1: ...` mentioning auth, login or the token. Run
`claude setup-token` again, `gh secret set CLAUDE_CODE_OAUTH_TOKEN`, then "Run now".

**A dead feed.** One bad source never fails the run; it shows as `FAIL` in the run log
(`python -m briefing fetch` locally). Fix or remove its line in `sources.yaml`. The run
only fails if fewer than 10 sources succeed or 0 items survive filtering. Known: the FTC
press-release feed (the URL FTC documents) returned 404 on 2026-10-12.

**Slack 4xx.** `Slack returned 403/404 ...` means the webhook was revoked or its channel
was deleted: create a new webhook and update `SLACK_WEBHOOK_URL`. `400 invalid_blocks`
is a payload bug; reproduce with `python -m briefing post --dry-run`. Today's status
isn't recorded on failure, so a plain "Run now" posts the stored briefing without
rebuilding it.

**Pages not updating.** Check Settings > Pages points at `main` `/docs` and look at the
"pages build and deployment" run in Actions. The workflow waits up to 3 min for the
build, then posts anyway with a warning, so links may 404 for a minute or two. The first
deploy can take longer.

**Cron didn't fire, or fired late.** GitHub's scheduled runs are best-effort and are
often 5–30 min late at busy times. They're also disabled after 60 days without repo
activity (the daily commits normally prevent that). Use "Run now"; re-runs never
double-post.

**Bad JSON from Claude.** Each call gets one retry with the parse error appended. A
second failure ends the run with `rank: Claude returned invalid JSON twice (...)` (or
`explain: ...`). Usually transient; "Run now" again. Individual bad entries (unknown ids,
invalid categories, URLs in text) are dropped rather than failing the run.

**Push rejected.** Every push does `git pull --rebase` first, and runs share one
concurrency group. If a push still fails (for example `main` was force-pushed, or a
manual edit conflicts with `data/seen.json`), resolve it locally, push, and "Run now".
