# Deploy locally

FlightDeck renders to one HTML file. Nothing is uploaded.

From the repo root:

```bash
scripts/publish_local.sh
```

That writes `dist/local/index.html` from `examples/demo/` and copies `examples/demo/assets/` beside it. The banner and fonts are already embedded in the HTML, so opening the file works offline.

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
