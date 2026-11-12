"""Advisory evidence ages relative to Activity; never blocks publishing.

Pane reasons are complete, counted clauses. Individual evidence stays in items.
Undated completed steps alone are not stale: open steps need dates, and dated
steps must not lag Activity by more than one hour.
"""
import datetime
import os
from pathlib import Path
import re
import sys

from flightdeck import sync as S

LABELS = {'decisions': 'Decisions', 'streams': 'Stream', 'steps': 'Your steps',
          'priorities': 'Priorities', 'architecture': 'Architecture'}


def newest(values):
    times = (S.aware(value) if isinstance(value, datetime.datetime) else S.parse_time(value) for value in values)
    return max((t for t in times if t), default=None)


def pane(rows, activity, issues=(), unit='items'):
    """Keep each source's evidence and summarize counts, never sliced prose."""
    items = []
    for label, when in rows:
        age = max(0, (activity - when).total_seconds() / 3600) if activity and when else None
        stale = when is None or (activity is not None and activity - when > S.FRESHNESS_WINDOW)
        reason = 'evidence unknown' if when is None else f'evidence at {S.iso_z(when)}'
        items.append({'label': label, 'newest': S.iso_z(when),
                      'age_h': round(age, 2) if age is not None else None,
                      'stale': stale, 'reason': reason})
    when = newest([item['newest'] for item in items])
    age = max(0, (activity - when).total_seconds() / 3600) if activity and when else None
    old = [item for item in items if item['stale'] and item['newest']]
    unknown = [item for item in items if item['newest'] is None]
    reasons = list(dict.fromkeys(issues))
    if old:
        oldest = min(S.parse_time(item['newest']) for item in old)
        reasons.append(f'{len(old)} of {len(items)} {unit} older than 1 h (oldest {oldest.day} {oldest:%b})')
    if unknown:
        reasons.append(f'{len(unknown)} of {len(items)} {unit} have no date')
    if not rows and not reasons:
        reasons.append(f'no {unit} evidence')
    if activity is None:
        reasons.append('activity time unknown')
    items.extend({'label': issue, 'newest': None, 'age_h': None, 'stale': True, 'reason': issue}
                 for issue in dict.fromkeys(issues))
    return {'newest': S.iso_z(when), 'age_h': round(age, 2) if age is not None else None,
            'stale': bool(reasons), 'reason': ' and '.join(reasons) or 'within 1 h of activity', 'items': items}


def steps_pane(steps, activity):
    rows = [(f'step {i + 1}', newest([step.get('done_at'), step.get('opened_at')]))
            for i, step in enumerate(steps)]
    result = pane(rows, activity, unit='steps')
    for step, item in zip(steps, result['items']):
        item['done'] = bool(step.get('done'))
        if item['done'] and item['newest'] is None:
            item['stale'] = False
            item['reason'] = 'completed legacy step has no date'
    open_items = [item for item in result['items'] if not item['done']]
    undated_open = [item for item in open_items if item['newest'] is None]
    old_open = [item for item in open_items if item['stale'] and item['newest']]
    latest = S.parse_time(result['newest'])
    behind = bool(activity and latest and activity - latest > S.FRESHNESS_WINDOW)
    result['stale'] = bool(undated_open or old_open or behind)
    if latest is None:
        result['reason'] = 'no step has a date yet' if open_items else 'no dated steps'
    elif undated_open:
        result['reason'] = f'{len(undated_open)} open steps have no date'
    elif behind:
        result['reason'] = 'latest step date is more than 1 h behind activity'
    elif old_open:
        result['reason'] = f'{len(old_open)} open steps older than 1 h'
    else:
        result['reason'] = 'within 1 h of activity' if activity else 'activity time unknown'
    return result


def cached_commit_time(cache, repo, sha, owner=''):
    """Only use cache dates tied to this repo and exact source SHA; never fetch."""
    if not repo or not sha:
        return None
    names = {repo, S.full_name(owner, repo)} if owner else {repo}
    times = []
    for filename in ('prs.json', 'prs-closed.json'):
        for row in S.cache_rows(S.read_json(cache / filename, []), 'prs') or []:
            if row.get('repo') in names and row.get('merge_sha') == sha:
                times.append(row.get('merged_at'))
    for row in S.cache_rows(S.read_json(cache / 'repos.json', []), 'repos') or []:
        name = row.get('full_name') or row.get('nameWithOwner') or row.get('name')
        if name in names and sha in (row.get('head_sha'), row.get('sha'), row.get('source_repo_sha')):
            times.extend(row.get(key) for key in ('committed_at', 'commit_date'))
    return newest(times)


def architecture_pane(tabs, sync, cache, activity, owner=''):
    rows, sources, pending = [], [], []
    for tab in tabs:
        records = []
        for record in sync.get('repos', []):
            repo = (record.get('repo') or '').lower()
            source = Path(record.get('source') or '').name.removesuffix('.bower.json')
            diagrams = {record.get('diagram'), f'architecture/{repo}.bower.json',
                        f'architecture/{repo}-{source}.bower.json'}
            if ((tab.get('id') and record.get('tab_id') == tab['id'])
                    or (tab.get('diagram') and tab['diagram'] in diagrams)
                    or (tab.get('status') == 'pending' and tab.get('repo') == record.get('repo'))):
                records.append(record)
        when = newest([record.get('imported_at') for record in records])
        source = 'imported_at'
        if when is None:
            when = newest([cached_commit_time(cache, record.get('repo'), record.get('source_repo_sha'), owner)
                           for record in records])
            source = 'cached source commit' if when else 'unknown'
        label = tab.get('repo') or tab.get('id') or 'tab'
        if tab.get('status') == 'pending':
            dates = [t for t in map(S.parse_time, [tab.get('pending_since')] +
                     [record.get('pending_since') for record in records]) if t]
            when = min(dates, default=None)
            label = f'{label} pending since {when.date() if when else "unknown"}'
            source = 'pending_since'
            pending.append(tab.get('repo') or tab.get('id'))
        rows.append((label, when))
        sources.append(source)
    result = pane(rows, activity, unit='architecture tabs')
    for item, source in zip(result['items'], sources):
        item['source'] = source
    if pending:
        count = len(set(pending))
        result['reason'] = f'{count} {"repo" if count == 1 else "repos"} pending a diagram'
    return result


def check(data, cfg, now=None):
    activity = S.parse_time((data.get('activity') or {}).get('at'))
    now = S.aware(now)
    cache = Path(cfg['cache_dir'])
    decision_times = []
    for card in data.get('decisions') or []:
        decision_times.extend(card.get(k) for k in ('settled_at', 'opened_at'))
        match = re.search(r'\bauto (\d{4}-\d{2}-\d{2} \d{2}:\d{2})', card.get('meta') or '', re.I)
        if match:
            local = datetime.datetime.strptime(match[1], '%Y-%m-%d %H:%M').replace(tzinfo=S.zone())
            decision_times.append(S.iso_z(local))
    decision_rows, decision_issues = [], []
    card_time = newest(decision_times)
    if card_time:
        decision_rows.append(('newest decision', card_time))
    capture = Path(os.environ.get('CREW_CHAT_ANSWERS') or cache / 'pending-chat-answers.json')
    for label, path in (('bot decision capture', cache / 'bot-decisions.json'), ('chat capture', capture)):
        if path.is_file():
            decision_rows.append((label, datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)))
        else:
            decision_issues.append(f'{label} missing')
    decisions = pane(decision_rows, activity, decision_issues, unit='decision sources')
    if decision_issues:
        decisions['reason'] = 'chat capture missing' if not capture.is_file() else 'bot decision capture missing'

    raw = S.read_json(cache / 'bot-reports.json', []) or []
    reports = raw.get('reports', []) if isinstance(raw, dict) else raw
    by_agent = {}
    for report in reports:
        if isinstance(report, dict) and report.get('agent'):
            by_agent.setdefault(report['agent'], []).append(report.get('at'))
    # Primary rows derive from discovery caches, not a hard-coded name or render time.
    discovery = [S.read_json(cache / filename, {}) for filename in ('prs.json', 'repos.json')]
    primary_at = newest([doc.get('at') for doc in discovery if isinstance(doc, dict)])
    stream_times = {}
    for row in data.get('streams') or []:
        agent = S.as_stream(row)['bot']
        stream_times[agent] = (newest(by_agent[agent]) if agent in by_agent
                               else primary_at if agent == S.primary_name(cfg) else None)
    stream_rows = [(f'{agent} report', at) for agent, at in stream_times.items()]
    priority_rows = [(f"{block.get('stream')} report", stream_times.get(block.get('stream')))
                     for block in data.get('priorities') or []]
    sync = S.read_json(cache / 'architecture-sync.json', {}) or {}
    panes = {'decisions': decisions,
             'streams': pane(stream_rows, activity, unit='bot reports'),
             'steps': steps_pane(data.get('steps') or [], activity),
             'priorities': pane(priority_rows, activity, unit='stream-derived blocks'),
             'architecture': architecture_pane((data.get('projects') or {}).get('tabs') or [], sync, cache, activity,
                                                cfg.get('owner') or '')}
    data['freshness'] = {'checked_at': S.iso_z(now), 'activity_at': S.iso_z(activity), 'panes': panes}
    summary = '\n'.join(line for line in (data.get('summary') or '').splitlines()
                        if not line.startswith('- Stale:'))
    flags = [f"{LABELS[name]}: {info['reason']}" for name, info in panes.items() if info['stale']]
    data['summary'] = summary + ('\n' if summary and flags else '') + ('- Stale: ' + '; '.join(flags) if flags else '')
    for name, info in panes.items():
        if info['stale']:
            print(f"freshness: WARNING {LABELS[name]}: {info['reason']}")
    return 0


def main(argv=None):
    try:
        return S.cli_data(check, argv)
    except Exception as exc:
        print(f'freshness: WARNING check unavailable ({type(exc).__name__})', file=sys.stderr)
        return 0
