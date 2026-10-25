# FlightDeck

FlightDeck is a static dashboard for agent work. Ten slots stay in a fixed layout. `config.json` chooses which widget fills each slot. Collectors write `data.json`. One render command writes a single HTML file.

Python 3.11 or newer is enough. The renderer and collectors use the standard library only. Clone this repo and run the commands from the root.

## Render the demo

```bash
python3 -m flightdeck.render examples/demo/config.json examples/demo/data.json dist/local/index.html
```

Or `scripts/publish_local.sh`, which does that and copies the demo assets next to the file. The demo banner is `examples/demo/assets/banner.webp`, created by GPT Astra. Swap in your own `banner.webp` beside your config when you leave the demo. The banner keeps its natural aspect.

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

The demo sets `cluster` to `metrics.generic`. Use `cluster.gpu` when you have cluster readings, or `empty` to leave the slot out.

Refresh `data.json` before rendering again:

```bash
FLIGHTDECK_GH_OWNER=you GITHUB_TOKEN=... python3 -m collectors.activity --data data.json
python3 -m collectors.metrics_generic --data data.json
```

`FLIGHTDECK_GH_OWNER` has no default. Unset, the activity collector writes nothing, which is how the demo stays offline.

## Deploy

Local folder: [docs/deploy-local.md](docs/deploy-local.md). `scripts/publish_local.sh` writes `dist/local/index.html`.

Cloudflare Workers: [docs/deploy-cloudflare.md](docs/deploy-cloudflare.md). `scripts/publish_cloudflare.sh` is a dry-run that embeds that HTML into a `flightdeck-demo` Worker. Real account ids, zone ids, Access emails, and KV ids stay in `site/site.json` on your machine. The repo only has placeholders in `site/site.example.json`.

## CI

Product CI is Buildkite on the `mac-mini` queue. The org pipeline uploads `.buildkite/pipeline.yml`. This repo does not use a GitHub Actions workflow. The pipeline checks Python 3.11 or newer, runs the unit tests, and renders the demo.

## Design

The layout rules, slot list, and what is in and out of v1 are in [docs/superpowers/specs/2026-10-25-flightdeck-design.md](docs/superpowers/specs/2026-10-25-flightdeck-design.md).
