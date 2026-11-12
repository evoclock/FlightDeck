"""Repository evidence uses generic fixtures, never operator data or services."""
import copy
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from flightdeck import freshness, sync as S

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-11-12T20:00:00Z'
OLD = '2026-11-01T12:00:00Z'


def record(name='acme/product', visibility='public'):
    return {'repo': name, 'visibility': visibility, 'default_branch': 'main',
            'pushed_at': NOW, 'collected_at': NOW, 'since': OLD,
            'open_prs': [{'repo': name, 'number': 7, 'title': 'Useful change',
                          'draft': True, 'checks': 'success', 'merge_state': 'BLOCKED',
                          'head_sha': 'a' * 40, 'state': 'open', 'updated_at': NOW,
                          'url': f'https://github.com/{name}/pull/7'}],
            'closed_prs': [], 'commits': {'count': 3, 'last': [],
                'tip': {'sha': 'b' * 40, 'title': 'Tip', 'time': NOW}},
            'branches': [{'name': 'feature', 'last_commit_at': NOW}]}


class RepoEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = S.deep_merge(S.DEFAULTS, {'owner': 'acme', 'cache_dir': str(self.root)})
        self.env = patch.dict(os.environ, {'FLIGHTDECK_GH_DISABLE': '1',
            'FLIGHTDECK_CACHE': str(self.root), 'FLIGHTDECK_GH_OWNER': 'acme'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def module(self, name):
        try:
            return importlib.import_module('scripts.' + name)
        except ModuleNotFoundError:
            self.fail('Missing repository evidence implementation: ' + name)

    def store(self, name, value):
        S.write_json(self.root / name, value)

    def snapshot(self, rows=None):
        payload = {'version': 1, 'owner': 'acme', 'collected_at': NOW,
                   'repos': [record()] if rows is None else rows}
        self.store('repo-evidence.json', payload)
        return payload

    def test_repo_without_bot_has_stream_priority_and_green_draft_step(self):
        """Why: active repositories must not need a bot report to reach each pane."""
        mod = self.module('reconcile_repo_panes')
        self.snapshot([record(), record('acme/internal', 'private')])
        data = {'priorities': [{'stream': 'acme/product', 'items': [
            {'text': 'Hand ladder', 'state': 'next', 'src': 'ladder'}]}]}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual({S.as_stream(r)['bot'] for r in data['streams']}, {'acme/product', 'acme/internal'})
        self.assertEqual({b['stream'] for b in data['priorities']}, {'acme/product', 'acme/internal'})
        self.assertTrue(any(i['text'] == 'Hand ladder' for i in data['priorities'][0]['items']))
        self.assertEqual(len(data['steps']), 2)
        self.assertTrue(all('Undraft and merge' in s['text'] for s in data['steps']))
        self.assertEqual(len(data['decisions']), 2)
        self.assertTrue(all(d['src'] == 'ready-draft' for d in data['decisions']))
        self.assertFalse((data.get('projects') or {}).get('tabs'))

    def test_duplicate_repository_and_branch_evidence_does_not_multiply_rows(self):
        mod = self.module('reconcile_repo_panes')
        row = record()
        row['branches'].append(dict(row['branches'][0]))
        self.snapshot([row, copy.deepcopy(row)])
        data = {}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['streams']), 1)
        self.assertEqual(len(data['priorities']), 1)
        self.assertEqual(sum('branch ' in i['text'] for i in data['priorities'][0]['items']), 1)
        self.assertEqual(len(data['steps']), 1)

    def test_non_draft_pr_does_not_create_a_draft_merge_step(self):
        mod = self.module('reconcile_repo_panes')
        row = record()
        row['open_prs'][0]['draft'] = False
        self.snapshot([row])
        data = {}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertFalse(any(s.get('src') == 'repo-evidence' for s in data.get('steps', [])))

    def test_finished_and_orphaned_steps_do_not_return(self):
        mod = self.module('reconcile_repo_panes')
        self.snapshot()
        data = {'streams': [['Old bot', 'old app', 'Old work', 'Old next']],
                'steps': [{'text': 'Merged old PR', 'done': True},
                          {'text': 'Old bot request', 'done': False},
                          {'text': 'At your desk', 'done': False, 'terminal': True}]}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual([s['bot'] for s in data['streams']], ['acme/product'])
        self.assertFalse(any(s['text'] in {'Merged old PR', 'Old bot request'} for s in data['steps']))
        self.assertTrue(any(s.get('terminal') for s in data['steps']))

    def test_green_draft_lifecycle_and_head_identity(self):
        """Why: red, closed, or changed-head PRs must not keep stale actionable asks."""
        mod = self.module('reconcile_repo_panes')
        payload = self.snapshot()
        data = {}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        first = data['decisions'][0]['id']
        opened = data['steps'][0]['opened_at']
        self.assertEqual(data['steps'][0]['decision_id'], first)
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['steps']), 1)
        self.assertEqual(data['decisions'][0]['id'], first)
        payload['repos'][0]['open_prs'][0]['head_sha'] = 'c' * 40
        self.store('repo-evidence.json', payload)
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertNotEqual(data['decisions'][0]['id'], first)
        self.assertEqual(data['steps'][0]['opened_at'], opened)
        payload['repos'][0]['open_prs'][0]['checks'] = 'pending'
        self.store('repo-evidence.json', payload)
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(data['steps'], [])
        self.assertEqual(data['decisions'], [])
        pr = dict(payload['repos'][0]['open_prs'][0], checks='success')
        payload['repos'][0]['open_prs'] = [pr]
        self.store('repo-evidence.json', payload)
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        payload['repos'][0].update(open_prs=[], closed_prs=[dict(pr, state='closed', merged=True, merged_at=NOW)])
        self.store('repo-evidence.json', payload)
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertFalse(any(not s.get('done') for s in data['steps']))
        self.assertTrue(all(s['done_at'] == NOW for s in data['steps']))

    def test_widened_decisions_do_not_depend_on_merges_or_legacy_visibility(self):
        """Why: live evidence covers green drafts outside legacy queue windows, including private repos."""
        self.snapshot([record(), record('acme/internal', 'private')])
        self.store('repos.json', {'repos': []})
        data = {}
        S.reconcile_ready_decisions(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual({d['pr'] for d in data['decisions']}, {'acme/product#7', 'acme/internal#7'})
        self.assertTrue(all(d.get('opened_at') and d.get('checked_at') for d in data['decisions']))

    def test_other_owner_and_unknown_visibility_do_not_create_asks(self):
        """Why: absent visibility and unrelated repositories must not inherit the configured owner's scope."""
        mod = self.module('reconcile_repo_panes')
        self.snapshot([record('other/product'), record('acme/unknown', 'unknown')])
        data = {}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(data.get('decisions', []), [])
        self.assertEqual(data.get('steps', []), [])

    def test_no_snapshot_is_a_noop_and_wrong_owner_snapshot_is_ignored(self):
        """Why: optional collection cannot replace existing panes with an empty or unrelated feed."""
        mod = self.module('reconcile_repo_panes')
        data = {'streams': [['Worker', 'app', 'Keep words', 'Nothing']]}
        before = copy.deepcopy(data)
        mod.reconcile(data, self.cfg)
        self.assertEqual(data, before)
        self.store('repo-evidence.json', {'owner': 'other', 'repos': [record('other/product')]})
        mod.reconcile(data, self.cfg)
        self.assertEqual(data, before)

    def test_fresh_collections_do_not_hide_failed_rows_or_old_bot_evidence(self):
        """Why: quiet repos can be fresh while failed collection and bot-only evidence stay visibly stale."""
        mod = self.module('reconcile_repo_panes')
        self.snapshot()
        data = {'activity': {'at': NOW}}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        freshness.check(data, self.cfg, now=S.parse_time(NOW))
        self.assertFalse(data['freshness']['panes']['streams']['stale'])
        self.assertFalse(data['freshness']['panes']['priorities']['stale'])
        self.assertFalse(data['freshness']['panes']['steps']['stale'])
        row = record()
        row.update(error='Unavailable', collected_at=OLD)
        self.snapshot([row])
        data['streams'].append(['Worker', 'old app', 'Keep words', 'Next'])
        self.store('bot-reports.json', [{'agent': 'Worker', 'at': OLD}])
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        freshness.check(data, self.cfg, now=S.parse_time(NOW))
        self.assertTrue(data['freshness']['panes']['streams']['stale'])
        self.assertTrue(all(s.get('done') for s in data['steps']))
        self.assertFalse(any(S.as_stream(s)['bot'] == 'Worker' for s in data['streams']))

    def test_architecture_keeps_diagram_clock_and_does_not_invent_tabs(self):
        """Why: recent repository checks do not prove that an old diagram matches the current source."""
        mod = self.module('reconcile_repo_panes')
        self.snapshot()
        self.store('architecture-sync.json', {'repos': [{'repo': 'acme/product', 'tab_id': 'product', 'imported_at': OLD}]})
        data = {'activity': {'at': NOW}, 'projects': {'tabs': [{'id': 'product', 'repo': 'acme/product'}]}}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['projects']['tabs']), 1)
        self.assertEqual(data['projects']['tabs'][0]['main_commit_at'], NOW)
        self.assertGreater(data['projects']['tabs'][0]['diagram_age_h'], 24)
        freshness.check(data, self.cfg, now=S.parse_time(NOW))
        self.assertTrue(data['freshness']['panes']['architecture']['stale'])
        self.assertTrue(data['freshness']['panes']['architecture']['diagram_items'])

    def test_later_priority_hook_preserves_repo_blocks(self):
        """Why: hook order must not restore bot-only priorities after repository reconciliation."""
        mod = self.module('reconcile_repo_panes')
        self.snapshot()
        data = {}
        mod.reconcile(data, self.cfg, now=S.parse_time(NOW))
        before = copy.deepcopy(data['priorities'])
        S.reconcile_priorities(data, self.cfg)
        self.assertEqual(data['priorities'], before)

    def test_dry_run_is_read_only_and_demo_is_protected(self):
        """Why: previews must not write data, caches, or response state and the shipped demo stays static."""
        self.module('reconcile_repo_panes')
        self.snapshot()
        config = self.root / 'sync.json'
        config.write_text(json.dumps(self.cfg))
        data = self.root / 'data.json'
        data.write_text('{}')
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        args = [sys.executable, str(ROOT / 'scripts/reconcile_repo_panes.py'), '--config', str(config)]
        result = subprocess.run(args + ['--data', str(data), '--dry-run', '--diff'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('streams: 0 -> 1', result.stdout)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})
        result = subprocess.run(args + ['--data', str(ROOT / 'examples/demo/data.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_combined_checks_include_status_contexts(self):
        """Why: Actions success must not mask a failing or pending external status context."""
        mod = self.module('collect_repo_evidence')
        runs = [{'name': 'tests', 'status': 'completed', 'conclusion': 'success'}]
        for state, expected in [('failure', 'failure'), ('pending', 'pending'), ('success', 'success')]:
            self.assertEqual(mod.combined_checks([{'context': 'external/ci', 'state': state}], runs), expected)
        self.assertEqual(mod.combined_checks([], []), 'unknown')

    def test_collector_offline_filters_and_preserves_failed_repo_clock(self):
        """Why: an inaccessible repo must neither erase another repo nor acquire a fresh success date."""
        mod = self.module('collect_repo_evidence')
        self.snapshot([dict(record('acme/bad'), collected_at=OLD)])
        fixtures = {'repos': [{'name': n, 'pushedAt': NOW, 'isPrivate': False,
                    'defaultBranchRef': {'name': 'main'}, 'isArchived': n == 'archived'}
                    for n in ('good', 'bad', 'archived')], 'api': {
            '/repos/acme/good/pulls?state=open&per_page=100&page=1': [],
            '/repos/acme/good/pulls?state=closed&sort=updated&direction=desc&per_page=100&page=1': [],
            '/repos/acme/good/commits?sha=main&since=2026-11-01T12%3A00%3A00Z&per_page=100&page=1': [],
            '/repos/acme/good/commits?sha=main&per_page=1': [],
            '/repos/acme/good/branches?per_page=100&page=1': []}}
        self.store('repo-evidence-fixtures.json', fixtures)
        config = self.root / 'sync.json'
        config.write_text(json.dumps(self.cfg))
        with patch.object(subprocess, 'run', side_effect=AssertionError('offline subprocess')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('offline network')):
            code = mod.main(['--config', str(config), '--offline', '--since', OLD, '--now', NOW])
        self.assertEqual(code, 0)
        rows = S.read_json(self.root / 'repo-evidence.json')['repos']
        self.assertEqual({r['repo'] for r in rows}, {'acme/good', 'acme/bad'})
        self.assertNotIn('error', rows[0])
        self.assertEqual(rows[1]['collected_at'], OLD)
        self.assertTrue(rows[1].get('error'))

    def test_default_collector_never_uses_host_tools(self):
        """Why: host evidence must require explicit configuration and an unset owner must never fetch."""
        mod = self.module('collect_repo_evidence')
        config = self.root / 'sync.json'
        config.write_text(json.dumps(self.cfg))
        with patch.object(mod.GitHub, 'repos', return_value=[]), \
             patch.object(mod, 'local_evidence', side_effect=AssertionError('unexpected host discovery')):
            self.assertEqual(mod.main(['--config', str(config), '--now', NOW]), 0)
        with patch.dict(os.environ, {'FLIGHTDECK_GH_OWNER': ''}), \
             patch.object(mod.GitHub, 'repos', side_effect=AssertionError('unexpected GitHub call')):
            self.assertEqual(mod.main(['--now', NOW]), 0)

    def test_offline_replay_never_renews_snapshot(self):
        """Why: replaying old evidence must not make stale rows appear freshly collected."""
        mod = self.module('collect_repo_evidence')
        self.snapshot()
        path = self.root / 'repo-evidence.json'
        before = path.read_bytes()
        self.assertEqual(mod.main(['--offline', '--out', str(path), '--now', NOW]), 0)
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
