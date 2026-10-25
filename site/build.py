#!/usr/bin/env python3
"""Build a Cloudflare Worker that serves one rendered FlightDeck page.

Stdlib only. This does not deploy and does not read tokens from the environment.

Dry-run (placeholders in site/site.example.json):

    python3 site/build.py --html dist/local/index.html

The HTML is the file scripts/publish_local.sh writes. Pass --site site/site.json
only on a machine where that file is filled in. site.json is gitignored.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

KV_BINDINGS = (
    ('FLIGHTDECK_RESPONSES', 'responses_kv_id'),
    ('FLIGHTDECK_SPARK', 'spark_kv_id'),
)


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding='utf-8'))
    required = (
        'worker_name', 'hostname', 'zone_id', 'account_id', 'compatibility_date',
        'access_team_domain', 'access_aud', 'allowed_emails',
    )
    missing = [key for key in required if key not in cfg]
    if missing:
        raise SystemExit(f'site config missing keys: {", ".join(missing)}')
    if not isinstance(cfg['allowed_emails'], list):
        raise SystemExit('allowed_emails must be a list')
    return cfg


def build_worker(html, cfg):
    if '__HTML__' in html or '__CFG__' in html:
        raise SystemExit('page HTML contains a build token')
    wcfg = {
        'team': cfg['access_team_domain'],
        'aud': cfg['access_aud'],
        'emails': [str(item).lower() for item in cfg['allowed_emails']],
    }
    template = (HERE / 'worker.template.js').read_text(encoding='utf-8')
    src = template.replace('__CFG__', json.dumps(wcfg)).replace('__HTML__', json.dumps(html))
    if src.count('export default {') != 1:
        raise SystemExit('worker.template.js must have exactly one default export')
    src = src.replace('export default {', 'const page = {', 1)
    src += (HERE / 'api.js').read_text(encoding='utf-8')
    return src


def kv_bindings(cfg):
    found = []
    for binding, key in KV_BINDINGS:
        value = cfg.get(key)
        if value:
            found.append((binding, value))
    return found


def wrangler_config(cfg, kv):
    doc = {
        'name': cfg['worker_name'],
        'main': 'worker.js',
        'account_id': cfg['account_id'],
        'compatibility_date': cfg['compatibility_date'],
        'workers_dev': False,
        'observability': {
            'enabled': True,
            'traces': {'enabled': True},
        },
        'routes': [{'pattern': cfg['hostname'], 'custom_domain': True}],
    }
    if kv:
        doc['kv_namespaces'] = [{'binding': binding, 'id': namespace_id} for binding, namespace_id in kv]
    return doc


def deploy_mcp(src, cfg, meta):
    return f"""async () => {{
  const A = {json.dumps(cfg["account_id"])}, NAME = {json.dumps(cfg["worker_name"])};
  const HOST = {json.dumps(cfg["hostname"])}, ZONE = {json.dumps(cfg["zone_id"])};
  const src = {json.dumps(src)};
  const meta = {json.dumps(meta)};
  const b = "F" + Date.now();
  const body = ["--" + b, 'Content-Disposition: form-data; name="metadata"', "Content-Type: application/json", "", JSON.stringify(meta),
    "--" + b, 'Content-Disposition: form-data; name="worker.js"; filename="worker.js"', "Content-Type: application/javascript+module", "", src,
    "--" + b + "--", ""].join("\\r\\n");
  const up = await cloudflare.request({{ method: "PUT", path: `/accounts/${{A}}/workers/scripts/${{NAME}}`, body, contentType: `multipart/form-data; boundary=${{b}}`, rawBody: true }});
  let sub = null; try {{ sub = (await cloudflare.request({{ method: "POST", path: `/accounts/${{A}}/workers/scripts/${{NAME}}/subdomain`, body: {{ enabled: false }} }})).success; }} catch (e) {{ sub = "skip: " + e.message.slice(0, 120); }}
  const dom = await cloudflare.request({{ method: "PUT", path: `/accounts/${{A}}/workers/domains`, body: {{ hostname: HOST, service: NAME, zone_id: ZONE, environment: "production" }} }});
  return {{ uploaded: up.success, etag: up.result && up.result.etag, workers_dev_disabled: sub, domain: dom.result && dom.result.hostname, bytes: src.length }};
}}
"""


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python3 site/build.py', description=__doc__.splitlines()[0])
    parser.add_argument('--html', required=True, help='rendered page to embed (scripts/publish_local.sh output)')
    parser.add_argument('--site', default=str(HERE / 'site.example.json'), help='site config; default is the placeholder example')
    parser.add_argument('--out', default=str(HERE / 'dist'), help='directory for worker.js, wrangler.json, deploy-mcp.js')
    args = parser.parse_args(argv)
    html_path = Path(args.html)
    if not html_path.is_file():
        raise SystemExit(f'missing page HTML {html_path}; run scripts/publish_local.sh first')
    cfg = load_config(args.site)
    src = build_worker(html_path.read_text(encoding='utf-8'), cfg)
    kv = kv_bindings(cfg)
    meta = {'main_module': 'worker.js', 'compatibility_date': cfg['compatibility_date']}
    if kv:
        meta['bindings'] = [
            {'type': 'kv_namespace', 'name': binding, 'namespace_id': namespace_id}
            for binding, namespace_id in kv
        ]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'worker.js').write_text(src, encoding='utf-8')
    (out / 'deploy-mcp.js').write_text(deploy_mcp(src, cfg, meta), encoding='utf-8')
    (out / 'wrangler.json').write_text(json.dumps(wrangler_config(cfg, kv), indent=2) + '\n', encoding='utf-8')
    configured = bool(cfg['access_team_domain']) and bool(cfg['access_aud'])
    print(
        'built', out / 'worker.js', len(src), 'bytes;',
        'access', 'ON' if configured else 'NOT CONFIGURED (worker denies all)',
        file=sys.stderr,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
