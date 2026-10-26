# Deploy on Cloudflare Workers

The Worker serves the rendered page and, when you attach KV, stores decision responses and cluster readings. Cloudflare Access sits in front of the hostname. The Worker also checks the Access JWT and the email allow-list.

A dry-run needs no token and no account. From the repo root:

```bash
scripts/publish_cloudflare.sh
```

That renders the demo to `dist/local/index.html`, then `site/build.py` embeds that HTML into `site/dist/`:

| File | Role |
|------|------|
| `worker.js` | Page plus `/api/responses`, `/api/chat-accept`, and `/api/spark` |
| `wrangler.json` | Wrangler config for the bundle |
| `deploy-mcp.js` | Optional Cloudflare API upload script |

The dry-run reads `site/site.example.json`. Every id in that file is a placeholder. Worker name: `flightdeck-demo`.

## Your own site

1. Copy `site/site.example.json` to `site/site.json`.
2. Replace `ACCOUNT_ID`, `ZONE_ID`, `ACCESS_AUD`, the hostname, the Access team domain, `allowed_emails`, and the KV ids.
3. Leave a KV id out of the file if you do not want that binding. `FLIGHTDECK_RESPONSES` stores `POST /api/responses` and `POST /api/chat-accept` (one chat answer merged in). `FLIGHTDECK_SPARK` stores `GET` and `POST /api/spark` under the key `spark/latest`.
4. `site/site.json` is gitignored. Do not commit it.

`scripts/publish_cloudflare.sh --deploy` refuses to upload while those placeholders are still in `site/site.json`. When they are filled in, it builds from that file and runs `npx wrangler@4 deploy` with `site/dist/wrangler.json`. Put a Cloudflare API token in the environment the way Wrangler expects. Do not write the token into the repo.

`site/access-setup-mcp.js` is a one-time Access setup script for the Cloudflare API. It ships with the same placeholders and returns an error until you edit them. Do not commit the edited copy.

Logs and traces are turned on in the generated Wrangler config (`observability.enabled` and `observability.traces.enabled`). The compatibility date in the example is `2026-10-25`.

You can rebuild without the shell wrapper:

```bash
python3 site/build.py --html dist/local/index.html --site site/site.example.json --out site/dist
```
