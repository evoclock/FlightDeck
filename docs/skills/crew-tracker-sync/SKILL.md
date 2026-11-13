---
name: Crew tracker sync
description: >-
  Use when an orchestrator must keep a team tracker current from live GitHub and
  agent evidence — every open PR, every in-flight repo, every unblock — and
  republish.
---
# Crew tracker sync

Keep a human's tracker current from structured evidence, not chat prose. Every run reconciles the tracker's data file against live sources. Completeness is the product: if the human has to ask whether an open PR, draft, new repo, or unblock is on the tracker, the last run failed.


**Sync-only panes:** discover active repositories from GitHub, without requiring a bot. The repository evidence snapshot supplies visibility and readiness. Without that snapshot, legacy public Decisions still require explicit `private=false` evidence in `repos.json`.

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

Publish from the git checkout. `./publish.sh` (or `scripts/publish_local.sh`) runs `hooks/pre-render.d` before render. `./publish.sh --build` refreshes the tracker and writes local HTML. `./publish.sh --deploy` also uploads a Worker, and only from a machine that has `site/site.json`. Never publish from a box-only tree. Optional `architecture_kv_id` in the gitignored `site/site.json` binds `CREW_ARCHITECTURE`; deploy stages and uploads only changed architecture HTML views before the Worker deploy. When unset, the upload is skipped. Check planned writes with `python3 scripts/upload_architecture_kv.py --source dist/local/assets/architecture --dist site/dist --site site/site.json --data examples/demo/data.json --dry-run`; this never writes KV. On deploy, `CLOUDFLARE_API_TOKEN` takes precedence. If unset, `CREW_TRACKER_CF_TOKEN_FILE` (default `~/.cloudflare_token`) is read when present and passed only to KV upload and Wrangler commands. Set token-file permissions to mode 600; an absent file is ignored.

## Inputs (set by the routine or repo config, not here)
Copy `config/sync.example.json` to `config/sync.json` (gitignored). Environment variables override the file.
- `tracker_data`: `FLIGHTDECK_DATA`, or `./data.json` when that file exists. The demo file is not the default.
- `owner`: `FLIGHTDECK_GH_OWNER` or `owner` in the sync config. Unset: hooks that need GitHub skip.
- `public_repos`: `FLIGHTDECK_PUBLIC_REPOS` (comma-separated) or `public_repos`. Optional fallback for unauthenticated REST when hook 01 has no `gh`/token. Ready-merge Decisions use live `repos.json` `private=false` evidence, not this list.
- `primary_stream`: `label` (else `agent`) is the stream row name. `FLIGHTDECK_STREAM_LABEL`, `FLIGHTDECK_PRIMARY_AGENT`, `FLIGHTDECK_PRIMARY_AREA`. Empty label: inflight does not write a stream row.
- `responses`: `account_id`, `kv_namespace_id`, `key`, or `FLIGHTDECK_ACCOUNT_ID` / `CLOUDFLARE_ACCOUNT_ID`, `FLIGHTDECK_RESPONSES_KV_ID`, `FLIGHTDECK_RESPONSES_KEY`. Token: `CLOUDFLARE_API_TOKEN`.
- `agents`: `.cache/bot-reports.json`, fields copied from each bot's own report. Optional `CREW_TRACKER_SIDECAR_DIRS` is a colon-separated list of read-only directories holding `bot-reports.json` and/or `responses.json`; hook 02b merges them into the local evidence caches before reconciliation. Unset or missing directories skip cleanly.
- `repo_evidence`: `days` sets the active window; optional `include` and `exclude` filter repository names. `local.enabled` defaults to false. Local evidence only reads configured `local.workspaces` and `local.checkouts`; `local.exclude_workspaces` always wins. Keep real identifiers and paths in ignored instance config.
- `publish_cmd`: `./publish.sh --build` or `./publish.sh --deploy`.

## Data shape (tracker_data)
- `streams`: one row per active repository, with current facts, collection time, and the next human action. Fresh bot notes can supplement repository facts. Unmapped bot-only rows remain visibly stale. Without a repository snapshot, legacy agent rows remain unchanged.
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
| `01b-collect-repo-evidence` | `scripts/collect_repo_evidence.py` | `.cache/repo-evidence.json` | All repositories pushed within configured `repo_evidence.days` (14 by default), including repositories without bots. GitHub GETs only; local evidence requires explicit configuration. Failures retain prior success dates |
| `02-collect-cluster` | `collectors/metrics_generic.py` or `collectors/spark.py` | `metrics` or `spark` | `FLIGHTDECK_CLUSTER=metrics` or `spark`. Unset: skip. Spark reads `FLIGHTDECK_SPARK_FILE` or `.cache/spark.json` and does not open SSH |
| `02b-merge-sidecars` | `scripts/merge_sidecars.py` | `.cache/bot-reports.json`, `.cache/responses.json` only | `CREW_TRACKER_SIDECAR_DIRS`; newest report per agent and response per id, with Undo tombstones retained. Invalid input warns and skips; sidecars stay untouched |
| `03-reconcile-responses` | `scripts/record_chat_accept.py --ingest-pending`, then `scripts/reconcile_responses.py` | Decisions → settled, Settled entries, step ticks | KV when `CLOUDFLARE_API_TOKEN` and the responses ids in sync config are set, else `.cache/responses.json`; plus chat answers in `.cache/responses-chat.json` (`scripts/record_chat_accept.py`) |
| `05-reconcile-inflight` | `scripts/reconcile_inflight.py` | Merges (open PRs + synthetic rows), primary stream, new-repo Decisions | `.cache/repos.json`, `.cache/prs.json` |
| `07-reconcile-merges-lifecycle` | `scripts/reconcile_merges_lifecycle.py` | Drops open rows for merged/closed PRs, ticks steps, settles Decisions, Settled entries | `.cache/prs-closed.json` |
| `10-reconcile-ready-decisions` | `scripts/reconcile_ready_decisions.py` | Ready-merge and green-draft Decisions | Repository snapshot widens coverage to public and private repositories. Current head and checks identify each ask. Legacy fallback uses explicit public visibility |
| `30-reconcile-steps-evidence` | `scripts/reconcile_steps_evidence.py` | Steps for ready+green PRs, install tick, release guard | prs cache, `.cache/omb-install.json`, `.cache/omb-releases.json`, `guards` in sync config |
| `40-apply-bot-reports` | `scripts/apply_bot_reports.py` | Other bots' stream rows, verbatim | `.cache/bot-reports.json` |
| `45-reconcile-repo-panes` | `scripts/reconcile_repo_panes.py` | Repository streams, priorities, green-draft steps, architecture evidence labels | Repository snapshot, optional bot notes, existing diagram imports. Does not fabricate diagrams or answers |
| `50-reconcile-priorities` | `scripts/reconcile_priorities.py` | One priorities block per stream; `src:"stream"` items rebuilt; ladder items kept | streams |
| `90-pin-ids` | `scripts/pin_ids.py` | Explicit unique `id` on every decision and step | — |
| `92-freshness` | `scripts/freshness.py` | Per-pane `freshness` and one generated summary warning | Evidence timestamps compared with Activity; advisory, never blocks publish |

`scripts/tracker_evidence.py` runs after the hooks. It prints one line: PR count, in-flight count, gaps. Exit 2 when a cache is present and incomplete. No caches: it prints offline and exits 0.

Cache writers the watch must run (structured JSON only):
- `.cache/prs.json` / `.cache/prs-closed.json` / `.cache/repos.json`: hook 01 writes these when `gh` or a token can see the owner. Repos rows may arrive camelCase (`pushedAt`/`createdAt`/`isPrivate`); readers accept both shapes via `norm_repo`. A fresh list that is empty or drops every private repo keeps the prior `repos.json`. Include `merge_state` (`mergeStateStatus`) and `checks` so "ready + green" is evidence, never a guess. Private repos need `gh` or a token. Without a token, hook 01 can only refresh `public_repos`, marks the cache incomplete, and exits 2.
- `.cache/responses.json`: the raw KV value for the configured responses key when no `CLOUDFLARE_API_TOKEN` is set. Chat Accepts must be merged into this store (same shape as a tracker tap) before publish: run `scripts/record_chat_accept.py`, never a hand edit. Handled ids live in `.cache/responses-handled.json`.
- `.cache/responses-chat.json`: chat answers written by `scripts/record_chat_accept.py`, one entry per Decision id. Live KV reads do not include an answer that only reached the cache, so hook 03 merges this file back in on every publish.
- `.cache/bot-reports.json`: `[{agent, area, current, next, at}]`, fields copied from each bot's own report or pane. Missing file = other streams unchanged. Reports older than one hour get a dated stale prefix, also carried into derived priorities. The newest report per agent wins; duplicate display names warn without deleting rows. Never summarise chat into it.
- `.cache/pending-chat-answers.json`: trusted, owner-authenticated capture with `captured_at` and an `answers` list, even when empty. Hook 03 consumes this before responses. Each answer needs a known Decision id, explicit value, zoned timestamp, reference, and `author` matching the configured `responses/<email>` key. The producer authenticates the human; a self-reported author is not authentication. Missing capture warns and writes `chat-capture-status.json`; `CREW_CHAT_STRICT=1` makes it fatal. Malformed or stale captures fail. `CREW_CHAT_ANSWERS` can override the path.
- `freshness.panes`: Decisions, Streams, Your steps, Priorities and Architecture carry `newest`, `age_h`, `stale`, `reason`, and full per-source `items`. Counted reasons stay short without truncating evidence. Unknown or more-than-one-hour-old evidence is flagged relative to Activity. A fresh row cannot hide an old source; undated completed legacy steps alone do not flag Your steps. The page displays stale badges; older data without `freshness` renders unchanged.
- Completed steps carry `done_at`; ready steps carry `opened_at`. Dated completed steps older than one day are pruned. Open and undated legacy steps remain, as do configured release guards. Architecture imports carry `imported_at`, preserved until the source commit or diagram hash changes. Pending tabs preserve the earliest `pending_since` across builds and worker changes. Legacy imports can use cached dates only for the exact source repository and commit.
- `.cache/omb-install.json`: `{app, version, checked_at}` from the machine that has the app installed. `omb.install_step_contains` in sync config names the step text to tick.
- `.cache/omb-releases.json`: GitHub releases for `omb.repo`. A guard with `needs: "nondraft_release"` stays undone until a real non-draft release is in that file. No tick, cache, or agent can mark that step done otherwise.
- `.cache/spark.json`: a reading shaped like data.json `spark` (`nodes` list). Hook 02 copies it only when `FLIGHTDECK_CLUSTER=spark`.

## Completeness invariants (every run)
The hooks above enforce these. A gap means a script or cache writer is missing; fix that, not the pane.
1. **Every open PR** has exactly one `merges` row (drafts count).
2. **Recently merged/closed** (last day) update their row; matching merge steps tick done.
3. **Every in-flight repo** (open PR, or pushed in 48h, or created in 7d) is discovered from the owner's full GitHub list — never typed from chat. No-PR in-flight repos get one synthetic merges row. New repos (created ≤48h) appear in an open Decision (or are named by an existing open Decision).
4. **Streams stay readable.** Each active repository gets its own current facts and next human action. A bot is optional. Do not combine unrelated repositories in one row.
5. **Decisions-only OK.** Ready merges, new-repo cutovers, spend, scope — open Decision with PR links before any chat ask.
   - Repository evidence supplies public or private visibility. Unknown visibility creates no automatic ask. Without a snapshot, public Decisions require `repos.json` `private=false`.
6. **Your steps** include ready PRs and green drafts. Draft actions say Undraft and merge; pending, failing, and closed PRs are not actionable.
7. **Priorities** blocks match each active stream's current/next from evidence; do not wipe done items.
8. **Settled today** only from the human's recorded responses and merged-PR evidence (hook 07), never invented. Recorded responses are tracker taps (KV) and chat answers written by `scripts/record_chat_accept.py`; hook 03 applies both as first-class answers.
9. **Architecture:** crew streams and optional registry entries select products. Import only rich product-owned `docs/diagrams/*.bower.json` diagrams; never invent a stub or rewrite product nodes. Record source commit, content hash and node status in `.cache/architecture-sync.json`. A diagram becomes visible only when its source hash matches and both flat and iso views are rendered. Missing or unrendered sources stay pending, with a verified draft PR link when available; `projects.pending` is emptied. Retire a product only on explicit completion evidence for every overlay node at the current product head. Retain the last tab by policy (Never blank Architecture); retention does not bypass source or view guards.
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
