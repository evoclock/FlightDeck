# FlightDeck

FlightDeck is a static dashboard for agent work. Ten slots stay in a fixed layout. `config.json` chooses which widget fills each slot. Collectors write `data.json`. One render command writes a single HTML file.

Python 3.11 or newer is enough. The renderer and collectors use the standard library only. Clone this repo and run the commands from the root.

## Render the demo

The public demo is a static illustration of publicly released evoclock work. Streams are FlightDeck, OpenMausBot, pi-agentic-driver, pi-bowerbird, and Demeter. Pull requests and notes link to public GitHub pages. Activity counts and host bars are examples stored in `examples/demo/data.json`. That file is static. Rendering it does not collect from GitHub. The architecture slot stays empty until you add your own diagrams.

The banner is `examples/demo/assets/banner.webp`, created by GPT Astra. Keep that file for the public demo. Swap in your own `banner.webp` beside your config when you leave the demo. The banner keeps its natural aspect.

```bash
./publish.sh
```

That runs the pre-render hooks, then writes `dist/local/index.html` and copies the demo assets beside it. With no GitHub owner and no root `data.json`, the hooks skip and `examples/demo/data.json` stays as it is in git. Open `dist/local/index.html` in a browser. The same render is `scripts/publish_local.sh`.

```bash
python3 -m flightdeck.render examples/demo/config.json examples/demo/data.json dist/local/index.html
```

Do not deploy a Worker for this public demo.

The walkthrough of this static page is [examples/demo/assets/flock-tracker-demo.mp4](examples/demo/assets/flock-tracker-demo.mp4). The still of the same page is [examples/demo/demo-still.png](examples/demo/demo-still.png).

<video src="examples/demo/assets/flock-tracker-demo.mp4" controls playsinline width="100%"></video>

![FlightDeck demo illustration](examples/demo/demo-still.png)

To open the page itself, render locally and serve `http://127.0.0.1:8765/` (leave the file offline; do not upload a Worker):

```bash
./publish.sh
python3 -m http.server --directory dist/local 8765
```

## Config

Copy `config.example.json` to `config.json`. Every slot is required. An unknown slot or widget id stops the render with `ConfigError`. `empty` hides a slot. `assets_dir` is relative to the config file (the demo uses `assets/`). Optional `banner.alt` is the image description. Optional `timezone` is an IANA name (the demo uses `Europe/London`).

| Slot | What it holds |
|------|----------------|
| `banner` | Banner image |
| `cluster` | Host or GPU readings |
| `activity` | Commits and pull requests, this hour and this week |
| `streams` | Who is working on what |
| `decisions` | Open yes/no items |
| `steps` | Human checklist |
| `merges` | Pull request queue |
| `priorities` | Focus per stream |
| `settled` | Already decided |
| `architecture` | Optional diagrams |

## Widgets

| Widget id | Role |
|-----------|------|
| `banner.image` | Embeds `banner.webp` from the assets directory |
| `cluster.gpu` | GPU / cluster readings from `data.json` `spark` |
| `metrics.generic` | CPU, memory, and disk bars from `data.json` `metrics` |
| `activity.github` | Hourly and weekly commit and pull request counts |
| `streams.table` | Stream rows |
| `decisions.cards` | Open decisions |
| `steps.checklist` | Human steps |
| `merges.table` | Merge queue |
| `priorities.list` | Priority items |
| `settled.list` | Settled today |
| `architecture.diagrams` | Architecture embeds |
| `empty` | Hide the slot |

The demo sets `cluster` to `metrics.generic` and `architecture` to `empty`. Use `cluster.gpu` when you have cluster readings. Use `architecture.diagrams` when you have diagrams. `empty` leaves a slot out.

Weekly activity in the demo sets `activity_weekly.sample` so the example counts stay on the page after Friday 17:00. A live collector does not set `sample`. A weekly block from an earlier week, without `sample`, shows zeros and Collecting.

Refresh `data.json` before rendering again:

```bash
FLIGHTDECK_GH_OWNER=you GITHUB_TOKEN=... python3 -m collectors.activity --data data.json
python3 -m collectors.metrics_generic --data data.json
```

`FLIGHTDECK_GH_OWNER` has no default. Unset, the activity collector writes nothing. Collectors and sync hooks also refuse to write `examples/demo/data.json`, so the illustration stays static even if that path is passed as `--data`. Point collectors at your own `data.json`.

## Sync hooks

`./publish.sh` and `scripts/publish_local.sh` run `hooks/pre-render.d` before they render. Each hook calls a collector or a script in `scripts/`. The scripts reconcile `data.json` from files in `.cache/`. They do not invent counts, ready state, or activity.

Copy `config/sync.example.json` to `config/sync.json` (gitignored). Set the GitHub owner, the public repos you merge, the primary stream label, and the responses KV ids there, or set the same values in the environment (`FLIGHTDECK_GH_OWNER`, `FLIGHTDECK_PUBLIC_REPOS`, `FLIGHTDECK_STREAM_LABEL`, `FLIGHTDECK_RESPONSES_KV_ID`, `CLOUDFLARE_API_TOKEN`). The field list is in the sync skill at `docs/skills/`.

With `FLIGHTDECK_GH_OWNER` unset and no `data.json` in the repo root, every hook skips. `examples/demo/data.json` stays as it is in git, and the render still works offline.

`FLIGHTDECK_CLUSTER=metrics` collects CPU, memory, and disk. `FLIGHTDECK_CLUSTER=spark` copies `.cache/spark.json` into `data.json` `spark`. It does not open SSH. Unset, the cluster hook skips. The demo keeps the readings already in the demo data file.

`./publish.sh --build` is the local render. `./publish.sh --deploy` uploads a Worker and needs `site/site.json` on that machine. Do not point it at the public demo placeholders.

## Deploy

Local folder: [docs/deploy-local.md](docs/deploy-local.md). `scripts/publish_local.sh` writes `dist/local/index.html`.

Cloudflare Workers: [docs/deploy-cloudflare.md](docs/deploy-cloudflare.md). `scripts/publish_cloudflare.sh` is a dry-run that embeds that HTML into a `flightdeck-demo` Worker. Real account ids, zone ids, Access emails, and KV ids stay in `site/site.json` on your machine. The repo only has placeholders in `site/site.example.json`.

## CI

Product CI is Buildkite on the `mac-mini` queue. The org pipeline uploads `.buildkite/pipeline.yml`. This repo does not use a GitHub Actions workflow. The pipeline checks Python 3.11 or newer, runs the unit tests, and renders the demo.

## Design

The layout rules, slot list, and what is in and out of v1 are in [docs/superpowers/specs/2026-10-25-flightdeck-design.md](docs/superpowers/specs/2026-10-25-flightdeck-design.md).
