#!/usr/bin/env python3
"""Stage architecture HTML and upload changed keys only, never delete remote keys."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def upload(source, dist, config, data, dry_run=False):
    cfg = json.loads(Path(config).read_text(encoding='utf-8'))
    namespace = cfg.get('architecture_kv_id')
    if not namespace:
        print('Architecture KV not configured; skipping upload')
        return 0
    if namespace.endswith('_ID') and not dry_run:
        raise SystemExit('Refusing to upload to a placeholder architecture_kv_id')
    source = Path(source)
    staged = Path(dist) / 'assets' / 'architecture'
    manifest = Path(dist) / 'architecture-kv-manifest.json'
    previous = json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else {}
    # A manifest from a different namespace cannot suppress uploads to this one.
    if previous.get('namespace') != namespace:
        previous = {}
    hashes = dict(previous.get('hashes', {}))
    if not source.is_dir():
        print('No architecture HTML to upload')
        return 0
    token = os.environ.get('CLOUDFLARE_API_TOKEN') if not dry_run else None
    tabs = json.loads(Path(data).read_text(encoding='utf-8')).get('projects', {}).get('tabs', [])
    for tab in tabs:
        if not tab.get('diagram'):
            continue
        diagram_id = tab['id']
        stem = Path(tab['diagram']).name.removesuffix('.bower.json')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', diagram_id) or not re.fullmatch(r'[A-Za-z0-9_-]+', stem):
            raise SystemExit('Invalid architecture id or diagram name')
        for view in ('iso', 'flat'):
            path = source / 'rendered' / view / (stem + '.html')
            if not path.is_file():
                raise SystemExit(f'Missing architecture view: {path}')
            key = f'architecture/{diagram_id}/{view}.html'
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if hashes.get(key) == digest:
                continue
            print(('Would upload ' if dry_run else 'Uploading ') + key)
            if dry_run:
                continue
            if not token:
                raise SystemExit('CLOUDFLARE_API_TOKEN is required for architecture uploads')
            destination = staged / diagram_id / (view + '.html')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            url = ('https://api.cloudflare.com/client/v4/accounts/' + quote(str(cfg['account_id']), safe='') +
                   '/storage/kv/namespaces/' + quote(str(namespace), safe='') + '/values/' + quote(key, safe='/'))
            request = Request(url, data=content, method='PUT', headers={
                'Authorization': 'Bearer ' + token,
                'Content-Type': 'text/html; charset=utf-8',
            })
            with urlopen(request, timeout=30) as response:
                result = json.load(response)
            if not result.get('success'):
                raise SystemExit(f'Architecture KV upload failed for {key}')
            hashes[key] = digest
            # Persist each successful key so a failed batch can safely resume.
            manifest.write_text(json.dumps({'namespace': namespace, 'hashes': hashes}, indent=2) + '\n', encoding='utf-8')

    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='freshly rendered architecture directory')
    parser.add_argument('--dist', required=True, help='built Worker directory')
    parser.add_argument('--site', required=True, help='site config')
    parser.add_argument('--data', required=True, help='tracker data used for the render')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    return upload(args.source, args.dist, args.site, args.data, args.dry_run)


if __name__ == '__main__':
    raise SystemExit(main())
