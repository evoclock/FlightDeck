# Flightdeck design — 2026-10-25

## Goal

Ship a **public** agent-ops tracker template people can customise (banner, widgets in fixed panes, monitors with or without Nvidia), plus a **private** Flockmate instance that runs crew.flockmate.dev without leaking real work details into the public tree.

## Names and repos

| Role | GitHub repo | Visibility |
|------|-------------|------------|
| Product template + scrubbed demo | `evoclock/flightdeck` | Public |
| Live Flockmate instance | `evoclock/flockmate-tracker` | Private |

- Avoid “flock” as a product brand (Flock Safety door-cam association).
- Instance depends on template via **git submodule** (pin a commit; update when wanted).
- Julen creates the empty GitHub repos (Cursor cannot create GitHub repositories).

## Product shape (v1)

**Approach A:** fixed pane skeleton + swappable widgets driven by `config.json`.

- Standard layout keeps cognitive load low (same balance as the live Flockmate tracker).
- Users pick which widget fills each slot.
- Some users have local compute; some do not — GPU/cluster widgets are optional.
- Day-one widgets are packaged; prompt→custom widget and voice accept/refuse are **out of v1** but slot IDs stay stable for later.

## Fixed slots (locked)

1. `banner` — image only; never shrunk/cropped for other panes
2. `cluster` — optional compute/GPU; hide or use `empty` when unused
3. `activity` — commits / PRs opened / PRs merged
4. `streams` — agent/work rows
5. `decisions` — open yes/no with links
6. `steps` — human action checklist
7. `merges` — PR queue
8. `priorities` — per-stream focus
9. `settled` — decided today
10. `architecture` — optional diagrams (full width)

## Config

`config.json` (sketch):

```json
{
  "banner": { "src": "assets/banner.webp" },
  "slots": {
    "banner": "banner.image",
    "cluster": "cluster.gpu",
    "activity": "activity.github",
    "streams": "streams.table",
    "decisions": "decisions.cards",
    "steps": "steps.checklist",
    "merges": "merges.table",
    "priorities": "priorities.list",
    "settled": "settled.list",
    "architecture": "architecture.diagrams"
  },
  "widgets": {
    "cluster.gpu": { "enabled": true },
    "metrics.generic": { "enabled": false }
  },
  "deploy": { "targets": ["cloudflare-workers", "local-static"] }
}
```

- Unknown widget ids fail render with a clear error.
- `empty` hides a slot without breaking layout rules for remaining panes.
- Non-GPU installs set `cluster` to `metrics.generic` or `empty`.

## Day-one widgets

| Widget id | Role |
|-----------|------|
| `banner.image` | User-chosen banner asset |
| `cluster.gpu` | Nvidia/Spark-style util + trends (optional) |
| `metrics.generic` | CPU/RAM/disk (or similar) for no-GPU hosts |
| `activity.github` | Hourly + weekly commit/PR counts |
| `streams.table` | Agent streams |
| `decisions.cards` | Open decisions with PR links |
| `steps.checklist` | Human steps |
| `merges.table` | Open/merged PRs |
| `priorities.list` | Priority items |
| `settled.list` | Settled today |
| `architecture.diagrams` | Optional architecture embeds |
| `empty` | Hide slot |

Later (not v1): prompt-generated widgets; voice for accept/refuse on decisions.

## Data flow

1. Collectors (or sync skill) write `data.json`.
2. `render.py` reads `config.json` + widgets + `data.json`.
3. Output is static HTML (and assets).
4. Deploy:
   - **Cloudflare Workers** example (same pattern as crew.flockmate.dev).
   - **Local static/app**: same build into a folder or thin local app shell; push/update without Cloudflare.

## Public vs private content

**Public `flightdeck` includes:**

- Core renderer, slot layout CSS rules (banner never shrunk), widget packages
- `examples/demo/` with **scrubbed** fake streams, no real PR titles, hostnames, or decisions
- Default public banner: a flightdeck-inspired asset (Claude-generated), not the private ADHD neuromancer `banner.webp`
- Deploy recipes for Cloudflare and local
- Docs and tests for config/widgets

**Private `flockmate-tracker` includes:**

- Real `data.json`, ADHD neuromancer `banner.webp`, Nvidia/Spark collectors
- Cloudflare project wiring for crew.flockmate.dev
- Architecture diagrams of Julen’s stack
- Submodule pin of `flightdeck`
- Sync skill / routines stay private or live in agents repos as today

Move path: extract from current `/workspace/crew-tracker` (and Mac `~/frontend-work/crew-tracker`) into `flightdeck` (cleaned) + `flockmate-tracker` (live overlay). Remove the mistaken home inside `frontend-work` / `tessellate-gorget` after the move.

## Testing (v1)

- Unit tests for config validation, slot→widget resolution, and “banner never shrunk” layout invariants (reuse/adapt current crew-tracker tests).
- Demo example renders offline without collectors.
- Cloudflare and local deploy scripts have dry-run / smoke paths where practical.
- Chrome headless view tests optional; must not block CI if they hang.

## Out of scope (v1)

- Prompt→widget generation
- Voice commands / voice accept-refuse
- Marketplace of third-party widgets
- Multi-tenant hosted SaaS
- Renaming live DNS away from crew.flockmate.dev (can stay; product name is flightdeck)

## Implementation order (after this spec is approved)

1. Julen creates empty `evoclock/flightdeck` (public) and `evoclock/flockmate-tracker` (private).
2. Cloud agent extracts cleaned template into `flightdeck` with demo example + both deploy recipes.
3. Cloud agent creates `flockmate-tracker` with submodule + live assets/data; point publish at it.
4. Retire `crew-tracker` under frontend-work (no further commits on tessellate-gorget for tracker).
5. Open tracker Decision for any public visibility or DNS change that still needs a yes.

## Success criteria

- Someone without Nvidia can run the demo with `metrics.generic` or `empty` cluster and see a balanced page.
- Flockmate’s live site keeps current behaviour and private data.
- Public repo has no real work details.
- Banner layout rule remains encoded in template tests/docs.
