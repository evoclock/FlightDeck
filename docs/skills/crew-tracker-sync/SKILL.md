---
name: Crew tracker sync
description: >-
  Use when an orchestrator must keep a team tracker current from live GitHub and
  agent evidence — every open PR, every in-flight repo, every unblock — and
  republish.
---
# Crew tracker sync

Keep a human's tracker current from structured evidence, not chat prose. Every run reconciles the tracker's data file against live sources. Completeness is the product: if the human has to ask whether an open PR, draft, new repo, or unblock is on the tracker, the last run failed.

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
This skill lives in-repo at `docs/skills/crew-tracker-sync/` (mirrored in `evoclock/flock-master` and `evoclock/FlightDeck`). Publish from the git checkout — for the private instance that is `~/flock-master` → `./publish.sh` → Cloudflare Worker — never from a box-only tree.

## Inputs (set by the routine or repo config, not here)
- `tracker_data`: path to the tracker's data file, e.g. `data.json`.
- `publish_cmd`: the build and deploy command(s) for the tracker site.
- `agents`: the agents/bots whose work the tracker covers, and how to read their latest reports.
- `scm_query`: the source-control search for the owner's open and recently merged PRs (must cover every owned repo, not a shortlist).
- `responses_store`: where the human's tracker answers are saved.
- `snapshot_dir`: where dated snapshots of the data file are committed.

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

Hooks, in order:

| Hook | Script | Writes | Evidence |
|---|---|---|---|
| 00 | `collectors/activity.py` (via `00-collect-activity`) | `activity`, `activity_weekly` | `GITHUB_TOKEN` / `GH_TOKEN` / `GITHUB_PAT`, else `gh auth token` |
| 01 | `refresh_pr_cache.py` | `.cache/prs.json`, `prs-closed.json`, `omb-releases.json` | `gh`, else GitHub token, else unauthenticated REST (public repos only) |
| 03 | `reconcile_responses.py` | Decisions → settled, Settled entries, step ticks | KV `CREW_RESPONSES` (`CLOUDFLARE_API_TOKEN`), else `.cache/responses.json` |
| 05 | `reconcile_inflight.py` | Merges (open PRs + synthetic rows), Flockmate stream, New-repo Decisions, Architecture stubs | `.cache/repos.json`, `.cache/prs.json` |
| 07 | `reconcile_merges_lifecycle.py` | Drops open rows for merged/closed PRs, ticks steps, settles Decisions, Settled entries | `.cache/prs-closed.json` |
| 10 | `reconcile_ready_decisions.py` | Ready-merge Decisions | merges rows in state `Ready…` |
| 30 | `reconcile_steps_evidence.py` | Your steps for ready+green PRs, merge ticks, OMB install tick, item 14 guard | prs caches, `.cache/omb-install.json`, `.cache/omb-releases.json` |
| 40 | `apply_bot_reports.py` | Other bots' stream rows, verbatim | `.cache/bot-reports.json` |
| 50 | `reconcile_priorities.py` | One priorities block per stream; `src:"stream"` items rebuilt; ladder items kept | streams + PR evidence |
| 90 | `pin_ids.py` | Explicit unique `id` on every decision and step | — |

Cache writers the watch must run (structured JSON only):
- `.cache/prs.json` / `.cache/prs-closed.json`: from the Mac with `gh` when the box token fails. Include `merge_state` (`mergeStateStatus`) and `checks` so "ready + green" is evidence, never a guess. Private repos need this; hook 01 can only refresh public ones without a token.
- `.cache/responses.json`: the raw KV value of `responses/j.a.r.gamboa@gmail.com` (namespace `519a5896bd3a41e4b2d5696b051f147d`) when no `CLOUDFLARE_API_TOKEN` is set, e.g. via the Cloudflare MCP connector. Handled ids live in `.cache/responses-handled.json`.
- `.cache/bot-reports.json`: `[{agent, area, current, next, at}]`, fields copied from each bot's own report or pane. Missing file = other streams unchanged. Never summarise chat into it.
- `.cache/omb-install.json`: `{app, version, checked_at}` read from the Mac (`defaults read /Applications/OpenMausBot.app/Contents/Info CFBundleShortVersionString`).
- Item 14 (first evoclock OpenMausBot GitHub release) is done only when a real non-draft release exists. No tick, cache, or agent can mark it done otherwise.

## Completeness invariants (every run)
The hooks above enforce these. A gap means a script or cache writer is missing; fix that, not the pane.
1. **Every open PR** has exactly one `merges` row (drafts count).
2. **Recently merged/closed** (last day) update their row; matching merge steps tick done.
3. **Every in-flight repo** (open PR, or pushed in 48h, or created in 7d) is discovered from the owner's full GitHub list — never typed from chat. No-PR in-flight repos get one synthetic merges row. New repos (created ≤48h) appear in an open Decision (or are named by an existing open Decision).
4. **Streams stay readable.** Each agent row is short current work + next for the human. In-flight repos that no bot owns stay on **Merges** (and Architecture / Decisions), **not** dumped into Flockmate's stream as a link salad.
5. **Decisions-only OK.** Ready merges, new-repo cutovers, spend, scope — open Decision with PR links before any chat ask.
   - `reconcile_ready_decisions.py` `PUBLIC_REPOS` must list every public repo the human merges (include `FlightDeck`). Missing names = silent no-Decision bugs.
6. **Your steps** list ready+green phone actions; drafts never appear there.
7. **Priorities** blocks match each active stream's current/next from evidence; do not wipe done items.
8. **Settled today** only from the human's tracker responses (KV, hook 03) and merged-PR evidence (hook 07), never invented.
9. **Architecture:** every in-flight product named on Merges/Decisions/Streams gets a `projects.tabs` entry and a bower diagram (stub if missing) that is rendered before publish.
10. **Activity** refreshed every sync (Mac `gh` when box token fails).
11. Run `reconcile_inflight.py` and `reconcile_ready_decisions.py` every publish (hooks). Discovery failure (exit 2) must not be reported as complete — refresh `.cache/repos.json` + `.cache/prs.json` from a machine where `gh` works.

## Each run
1. Gather evidence (agents, panes, full open-PR set, full in-flight repo set, KV responses).
2. Human responses are applied first by hook 03 (`reconcile_responses.py`) → Settled / steps done.
3. Refresh `.cache/` evidence (prs, prs-closed, repos, responses, bot-reports, omb-install); run `./publish.sh`. The hooks reconcile every pane. Never hand-edit pane prose in `data.json`.
4. Diff; if unchanged, stop.
5. Publish + snapshot.
6. Log one line (PR count, in-flight count, gaps fixed). Message the human only for waiting-on results or new open Decisions already on the tracker.

## Rules
- Never invent state, ready/green, or activity numbers.
- Never wait for the human to name an obvious new repo in chat.
- Never dump every loose repo into Streams.
- Human only OKs via open Decisions on the tracker.
