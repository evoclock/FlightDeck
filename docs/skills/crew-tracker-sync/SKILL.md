---
name: Crew tracker sync
description: >-
  Use when an orchestrator must keep a team tracker current from live GitHub and
  agent evidence — every open PR, every in-flight repo, every unblock — and
  republish.
---
# Crew tracker sync

Keep a human's tracker current from structured evidence, not chat prose. Every run reconciles the tracker's data file against live sources. Completeness is the product: if the human has to ask whether an open PR, draft, new repo, or unblock is on the tracker, the last run failed.

## Chat Accept must still be recorded (hard — Julen, 26 Oct 2026)
- A chat Accept and a tracker Accept both count as authority. Do not wait for the second one.
- Recording is separate. Every Accept, Reject, or alternative must still appear on the tracker, even when the human chose in chat.
- On a chat answer that settles an open Decision (or an equivalent merge, spend, or scope OK), record it first:
  - `python3 scripts/record_chat_accept.py --id dec-… [--value accepted|rejected|comment] [--comment '…'] [--at <ISO time of the message>] [--ref 'chat <message id>']`.
  - It upserts one entry by id, in the tracker-tap shape, into `.cache/responses-chat.json` and `.cache/responses.json`.
  - With `CLOUDFLARE_API_TOKEN` and the `responses` ids in sync config, it also upserts the entry into the responses KV value. Without them, the cache files are the record; publish from that checkout.
  - The library call is `flightdeck.sync.record_chat_accept(cfg, id, value, comment, at, ref)`.
- Then run `./publish.sh` (`--deploy` when the instance publishes live) so Decisions, Settled, and steps update.
- Never skip the tracker settle because the human chose in chat. Never leave a Decision open on the tracker after a chat Accept already unblocked the work.
- Never invent Settled rows by hand-editing `data.json`. The responses store plus hook 03 are the record path.

## Settled hard ceiling = 1 day (hard — Julen, 26 Oct 2026)
- Settled rows and settled Decision cards keep at most 24 hours.
- Hooks 03 and 07 run `flightdeck.sync.prune_settled` on every publish.
- Every new Settled row carries ISO `at` (the answer or merge time). Settled Decisions carry `settled_at`.
- A row without `at` resolves through the closed-PR cache. A row that still has no time is dropped.
- This stops the Settled pane from growing to thousands of rows.

## Chat Accept wire (hard — Julen, 26 Oct 2026)
Every chat Accept must reach the responses store without a bot remembering:
1. Prefer `POST /api/chat-accept` on the Worker (Access JWT; body `{id, value?, comment?, timestamp?, ref?}`). It merges one answer into KV `FLIGHTDECK_RESPONSES` and keeps the other answers.
2. Otherwise always run `python3 scripts/record_chat_accept.py`, then `./publish.sh`.
- Never leave a chat Accept only in bot memory.

## Writing (hard requirement)
All human-facing text this skill produces — tracker `streams` / `decisions` / `steps` / `settled` / `merge_note` prose, and any chat report to the human — must follow **agentic_aidr (AI;DR) simple** and **pstack `/bro`** (or pi-agentic-driver `bro-pi`):

1. Start with the answer in one sentence.
2. Use plain words and short sentences (about one action per sentence; keep procedural sentences near ≤20 words).
3. **Each sentence is its own bullet** in `decisions[].text` and `settled[].detail` (markdown `- …` lines). No dense paragraphs.
4. Put steps, choices, and comparisons in bullets (same rule).
5. Keep technical terms, but explain each one at first use. Drop jargon that does not help the human act.
6. One precise term for each idea; make requirements and conditions explicit (`must`, not vague modals).
7. When restating a prior assistant message for the human, apply `/bro`: same meaning, fewer words, no new facts.

Scripts write pane prose in this style. If a script's output is dense or unclear, fix the script's template. Do not rewrite the pane by hand.

Never claim AI;DR or `/bro` ran unless that tool or skill was actually invoked.

## Repo home
This skill lives in FlightDeck at `docs/skills/crew-tracker-sync/`. FlightDeck owns the hooks, the scripts, and the collectors. A private instance stays a thin overlay: its config, `data.json`, assets, and `site/` Worker. It does not keep a second copy of the hooks.

Publish from the git checkout. `./publish.sh` (or `scripts/publish_local.sh`) runs `hooks/pre-render.d` before render. `./publish.sh --build` refreshes the tracker and writes local HTML. `./publish.sh --deploy` also uploads a Worker, and only from a machine that has `site/site.json`. Never publish from a box-only tree.

## Inputs (set by the routine or repo config, not here)
Copy `config/sync.example.json` to `config/sync.json` (gitignored). Environment variables override the file.
- `tracker_data`: `FLIGHTDECK_DATA`, or `./data.json` when that file exists. The demo file is not the default.
- `owner`: `FLIGHTDECK_GH_OWNER` or `owner` in the sync config. Unset: hooks that need GitHub skip.
- `public_repos`: `FLIGHTDECK_PUBLIC_REPOS` (comma-separated) or `public_repos`. Every public repo the human merges. A missing name means no ready-merge decision.
- `primary_stream`: `label` (else `agent`) is the stream row name. `FLIGHTDECK_STREAM_LABEL`, `FLIGHTDECK_PRIMARY_AGENT`, `FLIGHTDECK_PRIMARY_AREA`. Empty label: inflight does not write a stream row.
- `responses`: `account_id`, `kv_namespace_id`, `key`, or `FLIGHTDECK_ACCOUNT_ID` / `CLOUDFLARE_ACCOUNT_ID`, `FLIGHTDECK_RESPONSES_KV_ID`, `FLIGHTDECK_RESPONSES_KEY`. Token: `CLOUDFLARE_API_TOKEN`.
- `agents`: `.cache/bot-reports.json`, fields copied from each bot's own report.
- `publish_cmd`: `./publish.sh --build` or `./publish.sh --deploy`.

## Data shape (tracker_data)
- `streams`: one row per agent: `[agent, area, current work (with time), next for the human]`. **Streams are agent work, not a repo inventory.** Never paste a comma-separated list of every loose GitHub repo into a stream area or current line.
- `merges`: `[title, repo, owner agent, state]`. Open PRs plus one synthetic `{name} · active on main` row per in-flight repo with no open PR.
- `decisions`, `steps`, `settled`, `priorities`, `projects.tabs` (architecture), `activity` / `activity_weekly` — all reconciled every run from live evidence.

## Script-driven panes (hard — Julen, 25 Oct 01:53 GMT)
Julen: "I do not want things done manually … otherwise you always have to interpret what I need or want."
- Every pane is written by a script in `hooks/pre-render.d/`. `./publish.sh --build` alone refreshes the tracker.
- Agents **never hand-edit pane prose in `data.json`** (streams, merges, steps, decisions, settled, priorities). Agents never interpret Julen's wants into `data.json`.
- An agent's only job is to refresh the **evidence caches** in `.cache/`, as structured JSON copied from the source (not reworded), then run `./publish.sh`.
- If a pane is wrong, fix the script or the cache writer. Do not patch the pane.

Hooks, in order. The hook file name is what `hooks/run-pre-render.sh` runs:

| Hook | Script | Writes | Evidence |
|---|---|---|---|
| `00-collect-activity` | `collectors/activity.py` | `activity`, `activity_weekly` | `GITHUB_TOKEN` / `GH_TOKEN` / `GITHUB_PAT`, else `gh auth token`. No owner: skip |
| `01-refresh-pr-cache` | `scripts/refresh_pr_cache.py` | `.cache/prs.json`, `prs-closed.json`, `repos.json`, and `omb-releases.json` when `omb.repo` is set | `gh`, else a GitHub token, else unauthenticated REST for `public_repos` only. No owner: skip |
| `02-collect-cluster` | `collectors/metrics_generic.py` or `collectors/spark.py` | `metrics` or `spark` | `FLIGHTDECK_CLUSTER=metrics` or `spark`. Unset: skip. Spark reads `FLIGHTDECK_SPARK_FILE` or `.cache/spark.json` and does not open SSH |
| `03-reconcile-responses` | `scripts/reconcile_responses.py` | Decisions → settled, Settled entries, step ticks | KV when `CLOUDFLARE_API_TOKEN` and the responses ids in sync config are set, else `.cache/responses.json`; plus chat answers in `.cache/responses-chat.json` (`scripts/record_chat_accept.py`) |
| `05-reconcile-inflight` | `scripts/reconcile_inflight.py` | Merges (open PRs + synthetic rows), primary stream, new-repo Decisions, architecture stubs | `.cache/repos.json`, `.cache/prs.json` |
| `07-reconcile-merges-lifecycle` | `scripts/reconcile_merges_lifecycle.py` | Drops open rows for merged/closed PRs, ticks steps, settles Decisions, Settled entries | `.cache/prs-closed.json` |
| `10-reconcile-ready-decisions` | `scripts/reconcile_ready_decisions.py` | Ready-merge Decisions | merges rows in state `Ready…` whose repo is in `public_repos` |
| `30-reconcile-steps-evidence` | `scripts/reconcile_steps_evidence.py` | Steps for ready+green PRs, install tick, release guard | prs cache, `.cache/omb-install.json`, `.cache/omb-releases.json`, `guards` in sync config |
| `40-apply-bot-reports` | `scripts/apply_bot_reports.py` | Other bots' stream rows, verbatim | `.cache/bot-reports.json` |
| `50-reconcile-priorities` | `scripts/reconcile_priorities.py` | One priorities block per stream; `src:"stream"` items rebuilt; ladder items kept | streams |
| `90-pin-ids` | `scripts/pin_ids.py` | Explicit unique `id` on every decision and step | — |

`scripts/tracker_evidence.py` runs after the hooks. It prints one line: PR count, in-flight count, gaps. Exit 2 when a cache is present and incomplete. No caches: it prints offline and exits 0.

Cache writers the watch must run (structured JSON only):
- `.cache/prs.json` / `.cache/prs-closed.json` / `.cache/repos.json`: hook 01 writes these when `gh` or a token can see the owner. Include `merge_state` (`mergeStateStatus`) and `checks` so "ready + green" is evidence, never a guess. Private repos need `gh` or a token. Without a token, hook 01 can only refresh `public_repos`, marks the cache incomplete, and exits 2.
- `.cache/responses.json`: the raw KV value for the configured responses key when no `CLOUDFLARE_API_TOKEN` is set. Chat Accepts must be merged into this store (same shape as a tracker tap) before publish: run `scripts/record_chat_accept.py`, never a hand edit. Handled ids live in `.cache/responses-handled.json`.
- `.cache/responses-chat.json`: chat answers written by `scripts/record_chat_accept.py`, one entry per Decision id. Live KV reads do not include an answer that only reached the cache, so hook 03 merges this file back in on every publish.
- `.cache/bot-reports.json`: `[{agent, area, current, next, at}]`, fields copied from each bot's own report or pane. Missing file = other streams unchanged. Never summarise chat into it.
- `.cache/omb-install.json`: `{app, version, checked_at}` from the machine that has the app installed. `omb.install_step_contains` in sync config names the step text to tick.
- `.cache/omb-releases.json`: GitHub releases for `omb.repo`. A guard with `needs: "nondraft_release"` stays undone until a real non-draft release is in that file. No tick, cache, or agent can mark that step done otherwise.
- `.cache/spark.json`: a reading shaped like data.json `spark` (`nodes` list). Hook 02 copies it only when `FLIGHTDECK_CLUSTER=spark`.

## Completeness invariants (every run)
The hooks above enforce these. A gap means a script or cache writer is missing; fix that, not the pane.
1. **Every open PR** has exactly one `merges` row (drafts count).
2. **Recently merged/closed** (last day) update their row; matching merge steps tick done.
3. **Every in-flight repo** (open PR, or pushed in 48h, or created in 7d) is discovered from the owner's full GitHub list — never typed from chat. No-PR in-flight repos get one synthetic merges row. New repos (created ≤48h) appear in an open Decision (or are named by an existing open Decision).
4. **Streams stay readable.** Each agent row is short current work + next for the human. In-flight repos that no bot owns stay on **Merges** (and Architecture / Decisions), **not** dumped into the primary stream as a link salad. The primary stream's label comes from sync config. Empty label: do not write that row.
5. **Decisions-only OK.** Ready merges, new-repo cutovers, spend, scope — open Decision with PR links before any chat ask.
   - `public_repos` in sync config must list every public repo the human merges. Missing names = silent no-Decision bugs.
6. **Your steps** list ready+green phone actions; drafts never appear there.
7. **Priorities** blocks match each active stream's current/next from evidence; do not wipe done items.
8. **Settled today** only from the human's recorded responses and merged-PR evidence (hook 07), never invented. Recorded responses are tracker taps (KV) and chat answers written by `scripts/record_chat_accept.py`; hook 03 applies both as first-class answers.
9. **Architecture:** every in-flight product named on Merges gets a diagram. Set `assets_dir` in sync config (not the demo assets folder) and the hook writes a bower stub plus a rendered page, then adds `projects.tabs`. With no `assets_dir`, it records `projects.pending` and does not add a tab, because a missing diagram fails render.
10. **Activity** refreshed every sync (Mac `gh` when box token fails).
11. Run `reconcile_inflight.py` and `reconcile_ready_decisions.py` every publish (hooks). Discovery failure (exit 2) must not be reported as complete — refresh `.cache/repos.json` + `.cache/prs.json` from a machine where `gh` works.

## Each run
1. Gather evidence (agents, panes, full open-PR set, full in-flight repo set, KV responses). Record every chat Accept, Reject, or alternative since the last run with `scripts/record_chat_accept.py`.
2. Human responses (tracker taps and recorded chat answers) are applied first by hook 03 (`reconcile_responses.py`) → Settled / steps done.
3. Refresh `.cache/` evidence (prs, prs-closed, repos, responses, bot-reports, omb-install); run `./publish.sh`. The hooks reconcile every pane. Never hand-edit pane prose in `data.json`.
4. Diff; if unchanged, stop.
5. Publish + snapshot.
6. Log one line (PR count, in-flight count, gaps fixed). Message the human only for waiting-on results or new open Decisions already on the tracker.

## Rules
- Never invent state, ready/green, or activity numbers.
- Never wait for the human to name an obvious new repo in chat.
- Never dump every loose repo into Streams.
- Put every OK ask on the tracker as an open Decision first. The human may answer on the tracker or in chat; a chat answer is recorded with `scripts/record_chat_accept.py` before publish.
