# Flightdeck Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the live crew-tracker into public `evoclock/flightdeck` (config-driven slots + widgets, scrubbed demo, Cloudflare + local deploy) and private `evoclock/flockmate-tracker` (real data, neuromancer banner, Nvidia collectors, submodule of flightdeck).

**Architecture:** Fixed ten slots filled by widget ids from `config.json`. Collectors write `data.json`; `render.py` loads config + widgets + data and emits static HTML. Public tree has no real work details. Instance pins flightdeck via git submodule.

**Tech Stack:** Python 3 stdlib (`render.py`, collectors, unittest), static HTML/CSS/JS, Cloudflare Workers (`site/`), optional KV bindings.

## Global Constraints

- Public product name is **flightdeck**; private instance is **flockmate-tracker**. Never brand the public product as “flock”.
- Banner asset for public demo is Claude-generated flightdeck art (Julen supplies the file). Private ADHD neuromancer `banner.webp` never ships in flightdeck.
- Ten locked slots: `banner`, `cluster`, `activity`, `streams`, `decisions`, `steps`, `merges`, `priorities`, `settled`, `architecture`.
- Banner pane never shrunk/cropped to fit other panes (`banner.webp` / default banner natural aspect).
- Instance→template link is **git submodule**.
- Deploy targets in v1: Cloudflare Workers example + local static/app push.
- Voice and prompt→widget are out of v1.
- Julen creates empty GitHub repos; agents push after that.
- Do not commit tracker work onto `tessellate-gorget` / `frontend-work` feature branches.

**Spec:** `docs/superpowers/specs/2026-10-25-flightdeck-design.md`

**Source tree to extract from:** `/workspace/crew-tracker` (box) and `~/frontend-work/crew-tracker` (Mac mirror).

---

## File map (target)

### `evoclock/flightdeck` (public)

| Path | Responsibility |
|------|----------------|
| `config.example.json` | Documented slot→widget map |
| `flightdeck/config.py` | Load/validate config; resolve widgets |
| `flightdeck/render.py` | Orchestrate HTML from config + data + widgets |
| `flightdeck/widgets/*.py` | One module per widget id family |
| `flightdeck/css_layout.py` (or section in render) | Locked top-row / pane grid CSS |
| `examples/demo/config.json` | Scrubbed demo config |
| `examples/demo/data.json` | Fake streams/decisions/merges only |
| `examples/demo/assets/banner.webp` | Julen’s Claude default banner |
| `examples/demo/fonts/` | Geist subset (same as today) |
| `collectors/activity.py` | GitHub activity (env token) |
| `collectors/metrics_generic.py` | CPU/RAM/disk stub for no-GPU |
| `site/` | Cloudflare Worker build (generic names, not crew-tracker) |
| `scripts/publish_cloudflare.sh` | CF deploy recipe |
| `scripts/publish_local.sh` | Copy build to local path / app folder |
| `tests/` | Config, widgets, banner invariant, demo render |
| `docs/` | Spec, this plan, user README |

### `evoclock/flockmate-tracker` (private)

| Path | Responsibility |
|------|----------------|
| `flightdeck/` | git submodule → evoclock/flightdeck |
| `config.json` | Live slot map (cluster.gpu enabled) |
| `data.json` | Real tracker state |
| `assets/banner.webp` | Neuromancer banner |
| `collectors/spark.py` | Nvidia SSH collectors |
| `site/site.json` | crew.flockmate.dev Access + KV ids |
| `hooks/`, `reconcile_ready_decisions.py` | Live sync helpers |
| `docs/skills/crew-tracker-sync/` | Private sync skill mirror |
| `publish.sh` | Existing publish path, pointed at this repo |

---

### Task 0: Empty GitHub repos (human)

**Files:** none in-repo

- [ ] **Step 1:** Julen creates `https://github.com/evoclock/flightdeck` (public, empty, no README).
- [ ] **Step 2:** Julen creates `https://github.com/evoclock/flockmate-tracker` (private, empty, no README).
- [ ] **Step 3:** Julen drops Claude default banner at a known path (e.g. Desktop `flightdeck-banner.webp`) and tells Flockmate.

**Done when:** both remotes exist; banner file path known.

---

### Task 1: Config loader + failing tests

**Files:**
- Create: `flightdeck/config.py`
- Create: `flightdeck/__init__.py`
- Create: `tests/test_config.py`
- Create: `config.example.json`

**Interfaces:**
- Produces: `load_config(path: Path) -> dict`, `SLOT_IDS: tuple[str, ...]`, `resolve_widget(config: dict, slot: str) -> str`, raises `ConfigError` on unknown slot/widget

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import json, tempfile, unittest
from pathlib import Path
from flightdeck.config import SLOT_IDS, load_config, resolve_widget, ConfigError

class TestConfig(unittest.TestCase):
    def test_slot_ids_locked(self):
        self.assertEqual(SLOT_IDS, (
            'banner', 'cluster', 'activity', 'streams', 'decisions',
            'steps', 'merges', 'priorities', 'settled', 'architecture',
        ))

    def test_resolve_widget(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS}}
        cfg['slots']['banner'] = 'banner.image'
        self.assertEqual(resolve_widget(cfg, 'banner'), 'banner.image')

    def test_unknown_widget_raises(self):
        cfg = {'slots': {s: 'empty' for s in SLOT_IDS}}
        cfg['slots']['banner'] = 'no.such'
        with self.assertRaises(ConfigError):
            load_config_dict(cfg)  # or validate(cfg)

    def test_load_example(self):
        p = Path('config.example.json')
        cfg = load_config(p)
        for s in SLOT_IDS:
            self.assertIn(s, cfg['slots'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd <flightdeck-checkout> && python3 -m unittest tests.test_config -v`  
Expected: FAIL (module missing)

- [ ] **Step 3: Minimal implementation**

```python
# flightdeck/config.py
SLOT_IDS = (
    'banner', 'cluster', 'activity', 'streams', 'decisions',
    'steps', 'merges', 'priorities', 'settled', 'architecture',
)
KNOWN_WIDGETS = frozenset({
    'banner.image', 'cluster.gpu', 'metrics.generic', 'activity.github',
    'streams.table', 'decisions.cards', 'steps.checklist', 'merges.table',
    'priorities.list', 'settled.list', 'architecture.diagrams', 'empty',
})

class ConfigError(ValueError):
    pass

def resolve_widget(config, slot):
    if slot not in SLOT_IDS:
        raise ConfigError(f'unknown slot: {slot}')
    wid = config['slots'][slot]
    if wid not in KNOWN_WIDGETS:
        raise ConfigError(f'unknown widget: {wid}')
    return wid

def validate(config):
    missing = [s for s in SLOT_IDS if s not in config.get('slots', {})]
    if missing:
        raise ConfigError(f'missing slots: {missing}')
    for s in SLOT_IDS:
        resolve_widget(config, s)
    return config

def load_config(path):
    import json
    from pathlib import Path
    return validate(json.loads(Path(path).read_text()))
```

- [ ] **Step 4: Run tests — expect PASS**
- [ ] **Step 5: Commit** `feat: config loader and locked slot ids`

---

### Task 2: Widget registry + empty/banner widgets

**Files:**
- Create: `flightdeck/widgets/__init__.py` (`render_slot(widget_id, ctx) -> str`)
- Create: `flightdeck/widgets/empty.py`
- Create: `flightdeck/widgets/banner.py`
- Create: `tests/test_widgets.py`

**Interfaces:**
- Consumes: `resolve_widget`
- Produces: `render_slot(widget_id: str, ctx: RenderContext) -> str` where `RenderContext` has `data`, `assets_dir`, `config`

- [ ] **Step 1: Failing tests** for `empty` → `""`, `banner.image` → `<figure class="banner">` with img, missing banner file raises clear error
- [ ] **Step 2: Implement registry dispatch + banner base64 embed (port from current `banner()` in crew-tracker `render.py`)**
- [ ] **Step 3: Tests pass; commit** `feat: widget registry with banner and empty`

---

### Task 3: Port layout CSS + remaining table widgets from crew-tracker

**Files:**
- Create: `flightdeck/layout_css.py` (extract locked CSS from crew-tracker `render.py` lines ~465–780)
- Create: `flightdeck/widgets/{streams,decisions,steps,merges,priorities,settled,activity,architecture,cluster,metrics}.py`
- Modify: `flightdeck/render.py` — assemble page using slots
- Test: `tests/test_layout_banner.py` — assert CSS contains `.banner img` with `object-fit:unset` / natural height rules; assert no rule that sets banner `max-height` for shrink-to-fit

**Porting rules:**
- Copy behaviour from `/workspace/crew-tracker/render.py`; rename localStorage keys from `crewTracker.*` to `flightdeck.*` in the public template.
- `cluster.gpu` ports `spark_panel` / trends; `metrics.generic` is a simple bars widget reading `data["metrics"]`.
- Keep nuthatch palette and Geist embed path under `assets/fonts/`.

- [ ] **Step 1: Banner invariant failing test**
- [ ] **Step 2: Extract CSS + wire `render.render(config_path, data_path, out_path)`**
- [ ] **Step 3: Port each widget module; demo render smoke test**
- [ ] **Step 4: `python3 -m unittest discover -s tests` PASS**
- [ ] **Step 5: Commit** `feat: render slots and port core widgets`

---

### Task 4: Scrubbed demo example

**Files:**
- Create: `examples/demo/config.json`, `data.json`, `assets/banner.webp` (Julen’s file), fonts copy
- Create: `tests/test_demo_render.py`

**Scrub rules for `data.json`:**
- Fake agent names (`Alpha`, `Beta`); fake repos (`example/app`); no evoclock private PR titles; no real hostnames (`node-a` not `spark-backend`); no real emails.

- [ ] **Step 1: Write scrubbed data + config (`cluster` → `metrics.generic` or `empty`)**
- [ ] **Step 2: Test: render demo offline; HTML contains “Alpha”; does not contain `evoclock/` or `spark-backend`**
- [ ] **Step 3: Commit** `feat: scrubbed examples/demo`

---

### Task 5: Collectors (activity + generic metrics)

**Files:**
- Create: `collectors/activity.py` (port `collect_activity.py`; env `FLIGHTDECK_GH_OWNER` default none — demo skips)
- Create: `collectors/metrics_generic.py` (stdlib: read `/proc` or `psutil` optional — prefer stdlib-only stub writing zeros + note when unsupported)
- Test: `tests/test_collectors.py` with mocked subprocess/HTTP

- [ ] Steps: failing tests → implement → pass → commit `feat: activity and generic metrics collectors`

---

### Task 6: Deploy recipes (Cloudflare + local)

**Files:**
- Port `site/` from crew-tracker; rename worker defaults to `flightdeck-demo`; strip Access emails to placeholders in `site/site.example.json`
- Create: `scripts/publish_cloudflare.sh`, `scripts/publish_local.sh`
- Docs: `docs/deploy-cloudflare.md`, `docs/deploy-local.md`

`publish_local.sh` sketch:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"$ROOT/dist/local"}
python3 -m flightdeck.render --config examples/demo/config.json --data examples/demo/data.json --out "$OUT/index.html"
cp -r examples/demo/assets "$OUT/" 2>/dev/null || true
echo "Local build at $OUT"
```

- [ ] **Step 1: Local script produces `dist/local/index.html` from demo**
- [ ] **Step 2: Cloudflare build dry-run (`site/build.py`) embeds that HTML**
- [ ] **Step 3: Commit** `feat: cloudflare and local publish scripts`

---

### Task 7: Public README + push flightdeck

**Files:**
- Create: `README.md` (install, config slots, widgets table, both deploy paths, link to design doc)
- Move design/plan under `docs/superpowers/`

- [ ] **Step 1: README written in plain language**
- [ ] **Step 2: `git remote add origin git@github.com:evoclock/flightdeck.git && git push -u origin main`**
- [ ] **Step 3: Confirm GitHub shows public repo with demo path**

---

### Task 8: Private flockmate-tracker instance

**Files:** (new repo)

- [ ] **Step 1:** `git clone` empty private repo; `git submodule add https://github.com/evoclock/flightdeck flightdeck`
- [ ] **Step 2:** Copy live `data.json`, neuromancer `banner.webp`, `collect_spark.py`, `reconcile_ready_decisions.py`, hooks, `site/site.json` (real Access), architecture diagrams from `/workspace/crew-tracker`
- [ ] **Step 3:** Root `config.json` points slots at live widgets; `cluster` → `cluster.gpu`
- [ ] **Step 4:** Thin `render_wrapper` or PATH that calls `python3 -m flightdeck.render` with instance paths
- [ ] **Step 5:** `publish.sh` updated; deploy crew.flockmate.dev once; verify Access still on
- [ ] **Step 6:** Commit + push private repo
- [ ] **Step 7:** Point Flockmate routines/skills at `flockmate-tracker` paths (box + Mac); stop writing tracker files under `frontend-work/crew-tracker`

---

### Task 9: Retire crew-tracker from frontend-work

- [ ] **Step 1:** On Mac, remove or replace `~/frontend-work/crew-tracker` with a short README pointing at the two repos (do this on a **new branch off main**, not `tessellate-gorget`)
- [ ] **Step 2:** Open PR; Decision on tracker for Julen to merge
- [ ] **Step 3:** Box `/workspace/crew-tracker` becomes a checkout of `flockmate-tracker` or a symlink — document in skill

---

### Task 10: Tracker Decision for “repos live”

- [ ] Open Decision on crew.flockmate.dev: public flightdeck URL + private instance URL + confirm publish path moved
- [ ] Settle only after Julen OKs

---

## Self-review vs spec

| Spec item | Task |
|-----------|------|
| Public flightdeck + private flockmate-tracker | 0, 7, 8 |
| Submodule | 8 |
| Ten slots + config.json | 1–3 |
| Widgets incl. metrics.generic | 2, 3, 5 |
| Scrubbed demo + Claude default banner | 4 (banner file from Julen) |
| CF + local deploy | 6 |
| No real details in public | 4 scrub tests |
| Banner never shrunk | 3 layout test |
| Retire frontend-work home | 9 |
| Voice / prompt widgets out of v1 | omitted |

