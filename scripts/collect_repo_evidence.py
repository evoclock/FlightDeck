#!/usr/bin/env python3
"""Collect read-only evidence for every recently pushed repository, not only bots.

GitHub requests are GETs. Host discovery is off unless explicitly configured.
Offline fixtures contain {repos: [...], api: {REST_path: response}}; replaying
without fixtures preserves the previous snapshot and its evidence dates.
"""
from concurrent.futures import ThreadPoolExecutor
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import quote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collectors import refuse_demo_write
from flightdeck import sync as S


class Unavailable(Exception):
    """A source could not be observed; never substitute empty success evidence."""


class GitHub:
    def __init__(self, offline=False, fixtures=None):
        self.offline = offline
        self.fixtures = fixtures or {}

    def get(self, path):
        if self.offline:
            if path not in self.fixtures.get('api', {}):
                raise Unavailable('fixture missing')
            return self.fixtures['api'][path]
        value = S.gh_runner(['api', '--method', 'GET', path]) if S.gh_available() else None
        if value is None:
            value = S.http_json(S.API + path, S.github_token())
        if value is None:
            raise Unavailable('GitHub GET unavailable')
        return value

    def pages(self, path, key=None):
        rows, page = [], 1
        while True:
            value = self.get(path + ('&' if '?' in path else '?') + f'per_page=100&page={page}')
            batch = value[key] if key else value
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            page += 1

    def repos(self, owner):
        if self.offline:
            return self.fixtures['repos']
        return [r for r in self.pages('/user/repos?affiliation=owner&sort=pushed')
                if (r.get('owner') or {}).get('login', '').casefold() == owner.casefold()]


def combined_checks(statuses, runs, required=()):
    """Every observed context must finish green; no checks means unknown."""
    states = [(s.get('state') or '').upper() for s in statuses]
    states += [(r.get('conclusion') or '').upper() if r.get('status') == 'completed'
               else 'PENDING' for r in runs]
    if set(states) & {'FAILURE', 'ERROR', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED', 'STARTUP_FAILURE', 'STALE'}:
        return 'failure'
    observed = {s.get('context'): (s.get('state') or '').upper() for s in statuses}
    observed.update({r.get('name'): (r.get('conclusion') or '').upper()
                     if r.get('status') == 'completed' else 'PENDING' for r in runs})
    if any(observed.get(name) not in {'SUCCESS', 'NEUTRAL', 'SKIPPED'} for name in required):
        return 'pending'
    if states and set(states) <= {'SUCCESS', 'NEUTRAL', 'SKIPPED'}:
        return 'success'
    return 'pending' if states else 'unknown'


def commit(row):
    info = row.get('commit') or {}
    return {'sha': row.get('sha'), 'title': (info.get('message') or '').split('\n')[0],
            'time': (info.get('committer') or {}).get('date')}


def normalize_pr(repo, row, checks='unknown'):
    return dict(S.normalize_pull(repo, row, checks), head_sha=(row.get('head') or {}).get('sha'))


def collect_repo(client, meta, since, cutoff, previous=None):
    repo = meta['repo']
    base = '/repos/' + repo
    result = dict(meta, since=since)
    opened = []
    pull_rows = client.pages(base + '/pulls?state=open')
    required_by_branch = {}
    for target in {r.get('base', {}).get('ref') or meta['default_branch'] for r in pull_rows}:
        target_path = quote(target, safe='')
        branch_info = client.get(base + '/branches/' + target_path)
        protection = (branch_info.get('protection') or {}).get('required_status_checks') or {}
        required = set(protection.get('contexts') or [])
        required.update(c['context'] for c in protection.get('checks', []))
        for rule in client.get(base + '/rules/branches/' + target_path):
            if rule.get('type') == 'required_status_checks':
                required.update(c['context'] for c in rule.get('parameters', {}).get('required_status_checks', []))
        required_by_branch[target] = required
    for row in pull_rows:
        required = required_by_branch[row.get('base', {}).get('ref') or meta['default_branch']]
        detail = client.get(base + f"/pulls/{row['number']}")
        sha = detail['head']['sha']
        statuses = client.pages(base + f'/commits/{sha}/status', 'statuses')
        runs = client.pages(base + f'/commits/{sha}/check-runs?filter=latest', 'check_runs')
        opened.append(dict(normalize_pr(repo, detail, combined_checks(statuses, runs, required)),
                      required_checks=sorted(required),
                      check_statuses=[{'context': s.get('context'), 'state': s.get('state')} for s in statuses],
                      check_runs=[{'name': r.get('name'), 'status': r.get('status'),
                                   'conclusion': r.get('conclusion')} for r in runs]))
    result['open_prs'] = opened
    closed, page = [], 1
    while True:
        rows = client.get(base + f'/pulls?state=closed&sort=updated&direction=desc&per_page=100&page={page}')
        closed.extend(normalize_pr(repo, r) for r in rows
                      if (S.parse_time(r.get('closed_at')) or cutoff) >= S.parse_time(since))
        last = S.parse_time(rows[-1].get('updated_at')) if rows else None
        if len(rows) < 100 or (last and last < S.parse_time(since)):
            break
        page += 1
    result['closed_prs'] = closed
    commits = client.pages(base + '/commits?' + urlencode({'sha': meta['default_branch'], 'since': since}))
    tip = client.get(base + '/commits?sha=' + quote(meta['default_branch'], safe='') + '&per_page=1')
    result['commits'] = {'count': len(commits), 'last': [commit(r) for r in commits[:5]],
                         'tip': commit(tip[0]) if tip else None}
    branches, branch_tips = [], {}
    prior_tips = (previous or {}).get('branch_tips', {})
    known_pr_heads = {p.get('head_sha') for p in opened + closed}
    for row in client.pages(base + '/branches'):
        if row['name'] == meta['default_branch']:
            continue
        sha = row['commit']['sha']
        prior = prior_tips.get(row['name'], {})
        same_tip = prior.get('sha') == sha
        when = prior.get('time') if same_tip else commit(client.get(base + f'/commits/{sha}'))['time']
        has_pr = prior.get('has_pr') if same_tip else None
        if sha in known_pr_heads:
            has_pr = True
        if S.parse_time(when) and S.parse_time(when) >= cutoff:
            if has_pr is None:
                has_pr = bool(client.pages(base + f'/commits/{sha}/pulls'))
            if not has_pr:
                branches.append({'name': row['name'], 'last_commit_at': when})
        branch_tips[row['name']] = {'sha': sha, 'time': when, 'has_pr': has_pr}
    result.update(branches=branches, branch_tips=branch_tips)
    return result


def command_json(argv, cwd=None):
    try:
        proc = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=15)
        return json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def list_result(payload, key):
    if isinstance(payload, list):
        return payload
    payload = payload or {}
    return (payload.get('result') or payload).get(key, [])


def local_evidence(names, config):
    """Only inspect explicitly listed workspaces/checkouts, using list/status verbs."""
    panes, leases, errors = {n: [] for n in names}, {n: [] for n in names}, []
    allowed = set(config.get('workspaces') or []) - set(config.get('exclude_workspaces') or [])
    if allowed:
        payload = command_json(['herdr', 'workspace', 'list'])
        if payload is None:
            errors.append('workspace list unavailable')
        for workspace in list_result(payload, 'workspaces'):
            wid = workspace.get('workspace_id') or workspace.get('id')
            if wid not in allowed:
                continue
            payload = command_json(['herdr', 'pane', 'list', '--workspace', wid])
            if payload is None:
                errors.append('pane list unavailable')
            for pane in list_result(payload, 'panes'):
                if pane.get('workspace_id', wid) not in allowed:
                    continue
                cwd = Path(pane.get('foreground_cwd') or pane.get('cwd') or '')
                label = (pane.get('label') or workspace.get('label') or '').casefold()
                for name in names:
                    short = name.rsplit('/', 1)[-1].casefold()
                    if short in {part.casefold() for part in cwd.parts} or label in {short, name.casefold()}:
                        panes[name].append({'agent_status': pane.get('agent_status', 'unknown')})
    for name, checkout in (config.get('checkouts') or {}).items():
        if name not in names:
            continue
        payload = command_json(['treehouse', 'status', '--json'], cwd=Path(checkout).expanduser())
        if payload is None:
            errors.append('checkout status unavailable')
        for lease in list_result(payload, 'worktrees'):
            if lease.get('status') == 'leased':
                leases[name].append({'branch': lease.get('branch')})
    return panes, leases, errors


def metadata(row, owner):
    name = row.get('repo') or row.get('full_name') or row.get('nameWithOwner') or row.get('name') or ''
    full = S.full_name(owner, name)
    visibility = (row.get('visibility') or '').lower()
    if visibility not in {'public', 'private'}:
        private = row.get('private', row.get('isPrivate'))
        visibility = 'private' if private is True else 'public' if private is False else 'unknown'
    return {'repo': full, 'visibility': visibility,
            'default_branch': row.get('default_branch') or (row.get('defaultBranchRef') or {}).get('name') or 'main',
            'pushed_at': row.get('pushed_at') or row.get('pushedAt')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config')
    parser.add_argument('--owner')
    parser.add_argument('--days', type=int)
    parser.add_argument('--since')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--no-mac', action='store_true', help='disable configured host evidence')
    parser.add_argument('--include', help='comma-separated repo names')
    parser.add_argument('--exclude', help='comma-separated repo names')
    parser.add_argument('--now', help='deterministic evidence time for offline verification')
    args = parser.parse_args(argv)
    cfg = S.load_config(args.config)
    config = cfg.get('repo_evidence') or {}
    owner = args.owner if args.owner is not None else cfg.get('owner')
    out = args.out or S.cache_path(cfg, 'repo-evidence.json')
    if refuse_demo_write(out):
        return 2
    if not owner:
        print('collect_repo_evidence: owner not set, skipping')
        return 0
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', owner):
        parser.error('invalid owner')
    days = args.days if args.days is not None else config.get('days', 14)
    if not isinstance(days, int) or days < 1:
        parser.error('days must be positive')
    try:
        old = S.read_json(out, {}) or S.read_json(S.cache_path(cfg, 'repo-evidence.json'), {}) or {}
        if old.get('owner', '').casefold() != owner.casefold():
            old = {}
        now = S.parse_time(args.now) if args.now else S.aware(None)
        if now is None:
            raise ValueError('invalid now')
        cutoff = now - datetime.timedelta(days=days)
        since = args.since or old.get('collected_at') or S.iso_z(cutoff)
        if not S.parse_time(since) or S.parse_time(since) > now:
            raise ValueError('invalid since')
        fixtures = S.read_json(S.cache_path(cfg, 'repo-evidence-fixtures.json')) if args.offline else None
        client = GitHub(args.offline, fixtures)
        include = set(args.include.split(',')) if args.include else set(config.get('include') or [])
        exclude = set(args.exclude.split(',')) if args.exclude else set(config.get('exclude') or [])
        if client.offline and fixtures is None:
            if old:
                replay = dict(old, repos=[r for r in old.get('repos', [])
                              if S.parse_time(r.get('pushed_at')) and S.parse_time(r['pushed_at']) >= cutoff
                              and (not include or {r['repo'], r['repo'].rsplit('/', 1)[-1]} & include)
                              and not {r['repo'], r['repo'].rsplit('/', 1)[-1]} & exclude])
                if not out.is_file() or S.read_json(out) != replay:
                    S.write_json(out, replay)
            print('collect_repo_evidence: offline replay; snapshot dates unchanged')
            return 0
        metas = [metadata(r, owner) for r in client.repos(owner) if not r.get('archived', r.get('isArchived', False))]
        metas = [m for m in metas if re.fullmatch(re.escape(owner) + r'/[A-Za-z0-9][A-Za-z0-9._-]*', m['repo'], re.I)
                 and S.parse_time(m['pushed_at']) and S.parse_time(m['pushed_at']) >= cutoff
                 and (not include or m['repo'] in include or m['repo'].split('/')[1] in include)
                 and not {m['repo'], m['repo'].split('/')[1]} & exclude]
        old_rows = {r['repo']: r for r in old.get('repos', [])}

        def one(meta):
            prior = old_rows.get(meta['repo'], {})
            # A failed repository resumes at its last success, not the global attempt time.
            repo_since = args.since or prior.get('collected_at') or S.iso_z(cutoff)
            try:
                return dict(collect_repo(client, meta, repo_since, cutoff, previous=prior), collected_at=S.iso_z(now))
            except Exception as exc:
                return dict(prior, **meta, error=type(exc).__name__, attempted_at=S.iso_z(now),
                            collected_at=prior.get('collected_at'))

        with ThreadPoolExecutor(max_workers=4) as pool:
            rows = list(pool.map(one, metas))
        local_errors = []
        host = config.get('local') or {}
        if host.get('enabled') is True and not args.no_mac and not client.offline:
            panes, leases, local_errors = local_evidence([m['repo'] for m in metas], host)
            for row in rows:
                row.update(panes=panes[row['repo']], leases=leases[row['repo']])
        S.write_json(out, {'version': 1, 'owner': owner, 'collected_at': S.iso_z(now),
                          'since': since, 'days': days, 'repos': rows, 'local_errors': local_errors})
        print(f"collect_repo_evidence: {len(rows)} active repos, {sum('error' in r for r in rows)} errors")
    except Exception as exc:
        print(f'collect_repo_evidence: WARNING {type(exc).__name__}; keeping previous snapshot', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
