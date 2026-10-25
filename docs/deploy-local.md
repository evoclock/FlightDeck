# Deploy locally

FlightDeck renders to one HTML file. Nothing is uploaded.

From the repo root:

```bash
scripts/publish_local.sh
```

That writes `dist/local/index.html` from the static illustration in `examples/demo/` and copies `examples/demo/assets/` beside it. The banner and fonts are already embedded in the HTML, so opening the file works offline. The copied assets include the walkthrough at `assets/flock-tracker-demo.mp4` (source path `examples/demo/assets/flock-tracker-demo.mp4`). The still of the page is `examples/demo/demo-still.png`. The demo lists public evoclock repos. Collectors refuse to overwrite `examples/demo/data.json`.

```bash
python3 -m flightdeck.render examples/demo/config.json examples/demo/data.json dist/local/index.html
```

is the same render step. `publish_local.sh` is that command plus the asset copy. Pass another directory if you want the files somewhere else:

```bash
scripts/publish_local.sh /path/to/folder
```

To publish your own board, point the render command at your `config.json` and `data.json`. Collectors, when you use them, only update `data.json` before the next render:

```bash
FLIGHTDECK_GH_OWNER=you GITHUB_TOKEN=... python3 -m collectors.activity --data data.json
python3 -m collectors.metrics_generic --data data.json
python3 -m flightdeck.render config.json data.json dist/local/index.html
```

Serve the folder with any static file server if you want the optional same-origin `/api/responses` and `/api/spark` calls. Opened as a file, the page keeps responses in the browser.

`./publish.sh` and `scripts/publish_local.sh` run `hooks/pre-render.d` before the render. With no `FLIGHTDECK_GH_OWNER` and no `data.json` in the repo root, the hooks skip and the demo data file is left as it is in git. An instance sets `FLIGHTDECK_DATA` (or keeps `data.json` at the root) and `config/sync.json`. See the sync section of the README.
