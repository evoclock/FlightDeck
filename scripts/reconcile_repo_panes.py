#!/usr/bin/env python3
"""Rebuild repository-scoped panes from read-only evidence, not bot presence.

Legacy decisions and response handling remain in FlightDeck's sync module.
Missing snapshots are a no-op. Collection errors never become green readiness.
"""
import argparse
import copy
import datetime
import json
from pathlib import Path
import re
import sys
import uuid
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collectors import load, refuse_demo_write, save
from flightdeck import sync as S

PANES = ('streams', 'priorities', 'steps', 'architecture')


def evidence(cfg):
    try:
        payload = S.read_json(S.cache_path(cfg, 'repo-evidence.json'))
    except (OSError, ValueError):
        return None
    if (not isinstance(payload, dict) or not cfg.get('owner')
            or not S.parse_time(payload.get('collected_at')) or not isinstance(payload.get('repos'), list)):
        return None
    if str(payload.get('owner', '')).casefold() != cfg['owner'].casefold():
        return None
    return payload


def repo_rows(cfg):
    payload = evidence(cfg)
    prefix = (cfg.get('owner') or '').casefold() + '/'
    return [r for r in (payload or {}).get('repos', [])
            if isinstance(r, dict) and str(r.get('repo', '')).casefold().startswith(prefix)]


def open_prs(cfg):
    """Widen discovery while failed repos fail closed, rather than reusing green cache rows."""
    if evidence(cfg) is None:
        return S.read_cache_rows(cfg, 'prs.json', 'prs')
    rows = repo_rows(cfg)
    active = {r['repo'].casefold() for r in rows}
    cached = S.read_cache_rows(cfg, 'prs.json', 'prs') or []
    return [p for p in cached if str(p.get('repo', '')).casefold() not in active] + [
        dict(p, repo=r['repo']) for r in rows if not r.get('error')
        for p in r.get('open_prs', []) if p.get('state', 'open').lower() == 'open']


def closed_prs(cfg):
    """Merge observed close events without hiding legacy repositories outside the active window."""
    cached = S.read_cache_rows(cfg, 'prs-closed.json', 'prs')
    if evidence(cfg) is None:
        return cached
    live = {S.pr_key(p) for p in open_prs(cfg) or []}
    combined = {S.pr_key(p): p for p in cached or [] if S.pr_key(p) not in live}
    for row in repo_rows(cfg):
        for pr in row.get('closed_prs', []):
            normalized = dict(pr, repo=row['repo'])
            if S.pr_key(normalized) not in live:
                combined[S.pr_key(normalized)] = normalized
    return list(combined.values())


def actionable(pr):
    return (str(pr.get('state') or 'open').lower() == 'open'
            and (S._green_draft_pr(pr) or S.pr_is_ready(pr)))


def reconcile_decisions(data, cfg, now=None):
    """Return None for legacy fallback, otherwise reconcile asks from live repository evidence."""
    if evidence(cfg) is None:
        return None
    now = S.aware(now)
    rows = repo_rows(cfg)
    active = {r['repo'] for r in rows}
    names = (set(S.public_repo_names(cfg)) - active) | {r['repo'] for r in rows if r.get('visibility') in {'public', 'private'}}
    checked = {r['repo']: r.get('collected_at') for r in rows}
    eligible = {S.pr_key(p): p for p in open_prs(cfg) or [] if actionable(p) and p.get('repo') in names}
    decisions = data.setdefault('decisions', [])
    auto = {'ready', 'ready-draft'}
    decisions[:] = [d for d in decisions if not (isinstance(d, dict) and d.get('state') == 'open'
                    and d.get('src') in auto and (d.get('pr') not in eligible
                    or d.get('src') != ('ready-draft' if eligible[d['pr']].get('draft') else 'ready')
                    or d.get('head_sha') != eligible[d['pr']].get('head_sha')))]
    for key, pr in eligible.items():
        existing = next((d for d in decisions if isinstance(d, dict) and d.get('src') in auto
                         and d.get('pr') == key and d.get('head_sha') == pr.get('head_sha')), None)
        if existing:
            existing['checked_at'] = checked.get(pr['repo'])
            continue
        if S._open_mentions(decisions, pr):
            continue
        draft = bool(pr.get('draft'))
        decisions.append({'id': 'dec-' + uuid.uuid4().hex, 'pr': key, 'head_sha': pr.get('head_sha'),
            'state': 'open', 'src': 'ready-draft' if draft else 'ready',
            'title': f"{'Accept draft' if draft else 'Merge'} {key}?",
            'meta': 'green draft' if draft else 'ready to merge',
            'text': S.bullets(f"{key} has green checks.", f"[{pr.get('title') or key}]({pr.get('url') or ''})"),
            'recommendation': 'Accept - undraft then merge.' if draft else 'Yes.',
            'why': S.bullets('The PR is still draft.' if draft else 'The merge state is clean.', 'Observed checks are green.'),
            'opened_at': S.iso_z(now), 'checked_at': checked.get(pr['repo'])})
    return 0


def architecture_candidates(candidates, cfg):
    """Widen product-owned diagram discovery without fabricating rendered diagrams."""
    rows = repo_rows(cfg)
    _, mapping = reports_and_mapping(rows, cfg)
    have = {str(c.get('id') or '').casefold() for c in candidates}
    return candidates + [{'id': r['repo'].rsplit('/', 1)[-1], 'label': r['repo'].rsplit('/', 1)[-1],
                          'stream': mapping.get(r['repo']), 'source': 'docs/diagrams/*.bower.json', 'done': False}
                         for r in rows if r['repo'].rsplit('/', 1)[-1].casefold() not in have]


def reports_and_mapping(rows, cfg):
    raw = S.read_json(S.cache_path(cfg, 'bot-reports.json'), []) or []
    reports = raw.get('reports', []) if isinstance(raw, dict) else raw
    reports = sorted((r for r in reports if isinstance(r, dict)),
                     key=lambda r: S.parse_time(r.get('at')) or S.parse_time('1970-01-01'), reverse=True)
    mapping = {}
    sync = S.read_json(S.cache_path(cfg, 'architecture-sync.json'), {}) or {}
    for item in sync.get('repos', []):
        if item.get('repo') and item.get('stream'):
            mapping.setdefault(S.full_name(cfg['owner'], item['repo']), item['stream'])
    for row in rows:
        name = row['repo']
        short = name.rsplit('/', 1)[-1]
        for report in reports:
            if report.get('repo') in {name, short} or re.search(r'(?<![\w.-])' + re.escape(short) + r'(?![\w.-])', report.get('area') or '', re.I):
                mapping.setdefault(name, report.get('agent'))
                break
    return reports, mapping


def as_bullets(bits, checked=None):
    """One markdown bullet per fact so Streams can render a real list."""
    lines = [bit if str(bit).lstrip().startswith("- ") else f"- {bit}" for bit in bits]
    if checked:
        lines.append(f"- Checked {checked}.")
    return "\n".join(lines)


def next_action(row):
    if row.get('error'):
        return 'Check evidence collection; readiness unknown.'
    prs = row.get('open_prs', [])
    actions = []
    for count, text in ((sum(bool(p.get('draft')) and actionable(p) for p in prs), 'Undraft and merge {} green draft PRs'),
                        (sum(not p.get('draft') and actionable(p) for p in prs), 'Merge {} ready PRs'),
                        (sum(p.get('checks') == 'failure' for p in prs), 'Fix failing checks on {} PRs')):
        if count:
            actions.append(text.format(count) + '.')
    return as_bullets(actions) if actions else 'Nothing right now.'


def current_facts(row):
    if row.get('error'):
        return as_bullets([f"Evidence unavailable ({row['error']})", f"last checked {row.get('collected_at') or 'unknown'}."])
    prs = row.get('open_prs', [])
    drafts = sum(bool(p.get('draft')) and actionable(p) for p in prs)
    ready = sum(not p.get('draft') and actionable(p) for p in prs)
    failing = sum(p.get('checks') == 'failure' for p in prs)
    bits = [f'{drafts} draft PRs green, {ready} ready, {failing} failing, {len(prs) - drafts - ready - failing} pending/unknown']
    commits = row.get('commits') or {}
    branch = row.get('default_branch', 'main')
    bits.append(f"{commits.get('count', 0)} commits on {branch} since {row.get('since') or 'unknown'}")
    tip = commits.get('tip') or next(iter(commits.get('last') or []), {})
    if tip.get('time'):
        bits.append(f"{branch} tip {tip['time']}")
    if row.get('branches'):
        bits.append(f"{len(row['branches'])} pushed branches without a PR")
    if row.get('panes'):
        bits.append(f"{len(row['panes'])} configured local panes")
    if row.get('leases'):
        bits.append(f"{len(row['leases'])} Treehouse leases")
    return as_bullets(bits, row.get('collected_at') or 'unknown')


def streams(data, rows, cfg, now):
    reports, mapping = reports_and_mapping(rows, cfg)
    result = []
    for row in rows:
        name, bot = row['repo'], mapping.get(row['repo'])
        current = current_facts(row)
        note = next((r for r in reports if r.get('agent') == bot and S.parse_time(r.get('at'))
                     and datetime.timedelta(0) <= now - S.parse_time(r['at']) <= datetime.timedelta(hours=24)), None)
        if note and note.get('current'):
            current += f"\n- {bot} note ({note['at']}): " + ' '.join(note['current'].split())
        result.append({'bot': name, 'repo': name, 'project': bot or row.get('visibility', 'unknown'),
                       'now': current, 'waiting': next_action(row), 'src': 'repo-evidence', 'at': row.get('collected_at')})
    # Only repository-backed streams survive; bot notes are annotations above.
    data['streams'] = result
    return mapping


def priorities(data, rows, mapping):
    old = data.get('priorities') or []
    blocks = []
    known = [dict(p, repo=r['repo']) for r in rows for p in r.get('open_prs', []) + r.get('closed_prs', [])]
    merged = {S.pr_key(dict(p, repo=r['repo'])) for r in rows for p in r.get('closed_prs', [])
              if p.get('merged') or p.get('state') == 'merged'}
    opened = {S.pr_key(dict(p, repo=r['repo'])) for r in rows if not r.get('error') for p in r.get('open_prs', [])}
    for row in rows:
        name = row['repo']
        ladder = [copy.deepcopy(i) for b in old if b.get('stream') == name
                  or (mapping.get(name) and b.get('stream') == mapping[name]
                      and sum(v == mapping[name] for v in mapping.values()) == 1)
                  for i in b.get('items', []) if i.get('src') not in {'stream', 'repo-evidence'}]
        ladder = list({i.get('text'): i for i in ladder}.values())
        for item in ladder:
            keys = {S.pr_key(p) for p in known if S.mentions(p, item.get('text'))}
            if keys and keys <= merged:
                item['state'] = 'done'
            elif item.get('state') == 'done' and keys & opened:
                item['state'] = 'current'
        items = []
        if row.get('error'):
            items.append({'text': 'Evidence unavailable; check collection.', 'state': 'blocked', 'src': 'repo-evidence'})
        else:
            for pr in row.get('open_prs', []):
                state = 'draft' if pr.get('draft') else 'ready' if actionable(pr) else 'open'
                items.append({'text': f"{name} #{pr['number']}: {pr.get('title', '')} ({state}, checks {pr.get('checks', 'unknown')})",
                              'state': 'blocked' if pr.get('checks') == 'failure' else 'next' if actionable(pr) else 'current',
                              'src': 'repo-evidence'})
            items.extend({'text': f"{name}: branch {b['name']} without a PR ({b.get('last_commit_at') or 'unknown'})",
                          'state': 'current', 'src': 'repo-evidence'} for b in row.get('branches', []))
            if not items:
                items.append({'text': current_facts(row).removeprefix('- '), 'state': 'current', 'src': 'repo-evidence'})
        blocks.append({'stream': name, 'area': mapping.get(name) or row.get('visibility'), 'items': items + ladder})
    data['priorities'] = blocks


def steps(data, rows, now):
    active = {r['repo'] for r in rows}
    eligible = {S.pr_key(p): dict(p, repo=r['repo']) for r in rows
                if not r.get('error') and r.get('visibility') in {'public', 'private'}
                for p in r.get('open_prs', []) if p.get('draft') and actionable(p)}
    old = data.get('steps') or []
    open_decisions = {d.get('id') for d in data.get('decisions', []) if d.get('state') == 'open'}
    kept = []
    for step in old:
        if not isinstance(step, dict) or step.get('done'):
            continue
        key = step.get('pr') or ''
        if step.get('src') in {'ready', 'repo-evidence'} and key.rsplit('#', 1)[0] in active:
            continue
        if (step.get('decision_id') in open_decisions and step.get('decision_id')
                or step.get('terminal') is True):
            kept.append(step)
    for key, pr in eligible.items():
        if any(isinstance(s, dict) and not s.get('done') and s.get('pr') == key for s in kept):
            continue
        decision = next((d for d in data.get('decisions', []) if d.get('pr') == key and d.get('state') == 'open'
                         and d.get('head_sha') == pr.get('head_sha')), {})
        previous = next((s for s in old if isinstance(s, dict) and s.get('pr') == key), {})
        identifier = decision.get('id')
        kept.append({'id': previous.get('id') or 'step-' + uuid.uuid4().hex,
            'text': f"{'Undraft and merge' if pr.get('draft') else 'Merge'} {key}: {pr.get('title', '')} (checks green)",
            'url': '#decisions:~:text=' + quote(decision['title'], safe='') if identifier else pr.get('url') or '',
            'pr_url': pr.get('url') or '', 'pr': key, 'head_sha': pr.get('head_sha'), 'decision_id': identifier,
            'meta': 'green draft' if pr.get('draft') else 'ready', 'done': False,
            'opened_at': previous.get('opened_at') or S.iso_z(now),
            'checked_at': next(r.get('collected_at') for r in rows if r['repo'] == pr['repo']), 'src': 'repo-evidence'})
    data['steps'] = kept


def architecture(data, rows, cfg, now):
    sync = (S.read_json(S.cache_path(cfg, 'architecture-sync.json'), {}) or {}).get('repos', [])
    for tab in (data.get('projects') or {}).get('tabs', []):
        rec = next((r for r in sync if r.get('tab_id') == tab.get('id') or
                    (tab.get('diagram') and r.get('diagram') == tab['diagram'])), {})
        name = S.full_name(cfg['owner'], tab.get('repo') or rec.get('repo') or tab.get('id') or '')
        row = next((r for r in rows if r['repo'].casefold() == name.casefold()), None)
        if row is None:
            continue
        tip = (row.get('commits') or {}).get('tip') or next(iter((row.get('commits') or {}).get('last') or []), {})
        imported = S.parse_time(rec.get('imported_at'))
        age = round(max(0, (now - imported).total_seconds() / 3600), 1) if imported else None
        text = f"{row.get('default_branch', 'main')} {tip.get('time') or 'unknown'}; diagram {str(age) + ' h old' if age is not None else 'age unknown'}"
        if tab.get('status') == 'pending':
            text += '; pending since ' + str(tab.get('pending_since') or 'unknown')[:10]
        tab.update(repo=row['repo'], main_commit_at=tip.get('time'), diagram_age_h=age,
                   evidence_at=row.get('collected_at'), text=text, label=f"{row['repo']} · {text}")


def reconcile(data, cfg, now=None, selected=PANES):
    payload = evidence(cfg)
    if payload is None:
        return 0
    now = S.aware(now)
    unique = {}
    for row in repo_rows(cfg):
        name = row['repo'].casefold()
        if name not in unique or (row.get('error') and not unique[name].get('error')):
            unique[name] = row
    rows = sorted((dict(row, branches=list({b['name'].casefold(): b for b in row.get('branches', [])}.values()))
                   for row in unique.values()), key=lambda r: (next_action(r).startswith('Nothing'),
                  -max([S.parse_time(r.get('pushed_at')) or S.parse_time('1970-01-01')] +
                       [S.parse_time(p.get('updated_at')) or S.parse_time('1970-01-01')
                        for p in r.get('open_prs', [])]).timestamp()))
    _, mapping = reports_and_mapping(rows, cfg)
    if 'streams' in selected:
        mapping = streams(data, rows, cfg, now)
    if 'priorities' in selected:
        priorities(data, rows, mapping)
    if 'steps' in selected:
        reconcile_decisions(data, cfg, now)
        steps(data, rows, now)
    if 'architecture' in selected:
        architecture(data, rows, cfg, now)
    stamps = data.setdefault('repo_evidence', {})
    for name in (*selected, *(['decisions'] if 'steps' in selected else [])):
        stamps[name] = {'collected_at': payload.get('collected_at'),
                        'repos': {r['repo']: {k: r.get(k) for k in ('collected_at', 'pushed_at', 'error')} for r in rows}}
    return 0


def apply_freshness(data, cfg, panes, activity):
    """Use successful collection clocks, retaining legacy sources and diagram diagnostics."""
    from flightdeck import freshness as F
    for name, stamp in data.get('repo_evidence', {}).items():
        if name not in panes:
            continue
        repos = stamp.get('repos', {})
        checked = [(repo, S.parse_time(row.get('collected_at'))) for repo, row in repos.items()]
        failed = [repo for repo, row in repos.items() if row.get('error')]
        issues = [f'{len(failed)} of {len(repos)} repo collections failed'] if failed else []
        if name == 'streams':
            stale_bots = {S.as_stream(r)['bot'] + ' report' for r in data.get('streams', [])
                          if str(S.as_stream(r)['now']).startswith('Stale since ')}
            checked += [(item['label'], None if item['label'] in stale_bots else S.parse_time(item['newest'])) for item in panes[name]['items']
                        if not any(item['label'] == repo + ' report' for repo in repos)]
        if name == 'steps':
            legacy = [s for s in data.get('steps', []) if s.get('src') != 'repo-evidence']
            if legacy and F.steps_pane(legacy, activity)['stale']:
                issues.append('legacy step evidence stale or unknown')
        result = F.pane(checked, activity, issues, unit='repo collections')
        for item in result['items']:
            if item['label'] in repos:
                item['pushed_at'] = repos[item['label']].get('pushed_at')
                if repos[item['label']].get('error'):
                    item.update(stale=True, error=repos[item['label']]['error'], reason='evidence collection failed')
        if name == 'decisions':
            captures = [i['reason'] for i in panes[name]['items'] if i['stale'] and 'capture' in i['label']]
            if captures:
                result.update(stale=True, reason=result['reason'] + '; ' + '; '.join(dict.fromkeys(captures)))
            result['capture_items'] = panes[name]['items']
        if name == 'architecture':
            result['diagram_items'] = panes[name]['items']
            if panes[name]['stale']:
                result.update(stale=True, reason=result['reason'] + '; ' + panes[name]['reason'])
        panes[name] = result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data')
    parser.add_argument('--config')
    parser.add_argument('--panes', default=','.join(PANES))
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--diff', action='store_true')
    args = parser.parse_args(argv)
    selected = args.panes.split(',')
    if set(selected) - set(PANES):
        parser.error('unknown pane')
    path = S.resolve_data(args.data)
    if path is not None and refuse_demo_write(path):
        return 2
    if path is None:
        print('reconcile_repo_panes: no data file, skipping')
        return 0
    before = load(path)
    after = copy.deepcopy(before)
    reconcile(after, S.load_config(args.config), selected=selected)
    for name in (*selected, 'decisions'):
        old = (before.get('projects') or {}).get('tabs', []) if name == 'architecture' else before.get(name, [])
        new = (after.get('projects') or {}).get('tabs', []) if name == 'architecture' else after.get(name, [])
        print(f'{name}: {len(old)} -> {len(new)}')
        if args.diff:
            for sign, left, right in (('+ ', new, old), ('- ', old, new)):
                for row in left:
                    if row not in right:
                        print(sign + json.dumps(row, ensure_ascii=False))
    if not args.dry_run and after != before:
        save(path, after)
    return 0


if __name__ == '__main__':
    sys.exit(main())
