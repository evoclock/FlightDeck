"""Boundary checks for optional host collection and widened lifecycle evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flightdeck import sync as S
from tests.test_repo_evidence import NOW, OLD, ROOT, record


class RepoEvidenceEdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = S.deep_merge(S.DEFAULTS, {'owner': 'acme', 'cache_dir': str(self.root)})
        env = patch.dict('os.environ', {'FLIGHTDECK_GH_OWNER': 'acme', 'FLIGHTDECK_CACHE': str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def store(self, name, value):
        S.write_json(self.root / name, value)

    def snapshot(self, rows):
        self.store('repo-evidence.json', {'owner': 'acme', 'collected_at': NOW, 'repos': rows})

    def test_only_allowlisted_workspaces_and_checkouts_are_inspected(self):
        """Why: optional host evidence must not inspect unconfigured or excluded resources."""
        from scripts import collect_repo_evidence as C
        calls = []

        def command(argv, cwd=None):
            calls.append((argv, cwd))
            if argv == ['herdr', 'workspace', 'list']:
                return {'result': {'workspaces': [{'id': n, 'label': 'product'}
                                                  for n in ('allowed', 'excluded', 'unrelated')]}}
            if argv[:3] == ['herdr', 'pane', 'list']:
                return {'panes': [{'cwd': 'checkouts/product', 'agent_status': 'working'}]}
            return {'worktrees': [{'status': 'leased', 'branch': 'feature'}]}

        host = {'workspaces': ['allowed', 'excluded'], 'exclude_workspaces': ['excluded'],
                'checkouts': {'acme/product': str(self.root), 'acme/unrelated': 'not-inspected'}}
        with patch.object(C, 'command_json', side_effect=command):
            panes, leases, errors = C.local_evidence(['acme/product'], host)
        self.assertEqual(errors, [])
        self.assertEqual(len(panes['acme/product']), 1)
        self.assertEqual(leases['acme/product'], [{'branch': 'feature'}])
        self.assertEqual(len(calls), 3)
        self.assertNotIn('excluded', json.dumps(calls, default=str))
        self.assertNotIn('not-inspected', json.dumps(calls, default=str))
        with patch.object(C, 'command_json', side_effect=AssertionError('must stay offline')):
            self.assertEqual(C.local_evidence(['acme/product'], {}), ({'acme/product': []}, {'acme/product': []}, []))

    def test_closed_snapshot_settles_existing_decision_without_legacy_cache(self):
        """Why: a PR that closes between legacy polls must settle its existing ask from repo evidence."""
        pr = dict(record()['open_prs'][0], state='closed', merged=True, merged_at=NOW)
        row = dict(record(), open_prs=[], closed_prs=[pr])
        self.snapshot([row])
        data = {'decisions': [{'id': 'dec-existing', 'src': 'ready-draft', 'state': 'open',
                              'pr': 'acme/product#7', 'title': 'Accept draft acme/product#7?',
                              'text': '- https://github.com/acme/product/pull/7'}]}
        S.reconcile_merges_lifecycle(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(data['decisions'][0]['state'], 'settled')
        self.assertEqual(data['decisions'][0]['settled_at'], S.iso_z(S.parse_time(NOW)))

    def test_no_bot_no_pr_repo_is_still_an_architecture_candidate(self):
        """Why: recently pushed repositories outside the old queue window need diagram discovery too."""
        row = dict(record(), open_prs=[])
        self.snapshot([row])
        data = {}
        with patch.object(S, 'import_product_bowers', return_value={}) as importer:
            S._upsert_architecture(data, self.cfg, [], [], now=S.parse_time(NOW))
        self.assertIn('product', {entry['id'] for entry in importer.call_args.args[0]})
        self.assertTrue(any(tab.get('repo') == 'product' and tab.get('status') == 'pending'
                            for tab in data['projects']['tabs']))

    def test_incremental_collection_resumes_each_repo_at_its_last_success(self):
        """Why: a global success date must not skip commits after a repository's failed poll."""
        from scripts import collect_repo_evidence as C
        self.snapshot([dict(record(), collected_at=OLD)])
        config = self.root / 'sync.json'
        config.write_text(json.dumps(self.cfg))
        metas = [{'name': 'product', 'pushedAt': NOW, 'isPrivate': False}]
        with patch.object(C.GitHub, 'repos', return_value=metas), \
             patch.object(C, 'collect_repo', return_value=record()) as collect:
            self.assertEqual(C.main(['--config', str(config), '--now', NOW]), 0)
        self.assertEqual(collect.call_args.args[2], OLD)

    def test_required_check_must_be_observed_before_green(self):
        """Why: a successful optional check cannot hide a required check that has not reported."""
        import inspect
        from scripts import collect_repo_evidence as C
        self.assertIn('required', inspect.signature(C.combined_checks).parameters)
        runs = [{'name': 'tests', 'status': 'completed', 'conclusion': 'success'}]
        self.assertEqual(C.combined_checks([], runs, required=['external/required']), 'pending')
        self.assertEqual(C.combined_checks([{'context': 'external/required', 'state': 'success'}], runs,
                                          required=['external/required']), 'success')

    def test_repository_freshness_preserves_independent_capture_diagnostics(self):
        """Why: live PR collection cannot prove that the independent response capture paths work."""
        from flightdeck import freshness as F
        from scripts import reconcile_repo_panes as R
        self.snapshot([record()])
        data = {'activity': {'at': NOW}}
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        F.check(data, self.cfg, now=S.parse_time(NOW))
        pane = data['freshness']['panes']['decisions']
        self.assertTrue(pane['stale'])
        self.assertTrue(pane.get('capture_items'))
        self.assertIn('capture', pane['reason'])

    def test_snapshot_validation_does_not_wipe_existing_data(self):
        """Why: a malformed or incomplete snapshot is not evidence that the active repository set is empty."""
        from scripts import reconcile_repo_panes as R
        self.store('repo-evidence.json', {'owner': 'acme', 'repos': []})
        data = {'streams': [['Worker', 'app', 'Keep', 'Nothing']]}
        before = json.loads(json.dumps(data))
        R.reconcile(data, self.cfg)
        self.assertEqual(data, before)

    def test_repeated_bot_overlay_deduplicates_and_settles_ladders(self):
        """Why: bot overlays must not duplicate a hand-authored ladder item or miss its observed merge."""
        from scripts import reconcile_repo_panes as R
        row = record()
        self.snapshot([row])
        self.store('bot-reports.json', [{'agent': 'Worker', 'repo': 'acme/product', 'at': OLD}])
        ladder = {'text': 'Review acme/product#7', 'state': 'next', 'src': 'ladder'}
        data = {'priorities': [{'stream': 'acme/product', 'items': [dict(ladder)]},
                               {'stream': 'Worker', 'items': [dict(ladder)]}]}
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(sum(i['text'] == ladder['text'] for i in data['priorities'][0]['items']), 1)
        row.update(open_prs=[], closed_prs=[dict(record()['open_prs'][0], merged=True, state='closed', merged_at=NOW)])
        self.snapshot([row])
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        items = [i for i in data['priorities'][0]['items'] if i['text'] == ladder['text']]
        self.assertEqual(items[0]['state'], 'done')

    def test_repository_architecture_reviews_share_the_normal_ready_path(self):
        """Why: a repository snapshot must not silently omit a green draft based on its title."""
        from scripts import reconcile_repo_panes as R
        row = record('acme/FlightDeck')
        row['open_prs'][0]['title'] = 'Update architecture map'
        self.snapshot([row])
        data = {}
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['decisions']), 1)
        self.assertEqual(data['steps'][0]['decision_id'], data['decisions'][0]['id'])
        self.assertTrue(data['steps'][0]['url'].startswith('#decisions:~:text='))

    def test_offline_copy_filters_without_renewing_dates(self):
        """Why: replay to another output must retain evidence dates and respect explicit filters."""
        from scripts import collect_repo_evidence as C
        self.snapshot([record(), record('acme/other')])
        config = self.root / 'sync.json'
        config.write_text(json.dumps(self.cfg))
        out = self.root / 'copy.json'
        self.assertEqual(C.main(['--config', str(config), '--offline', '--out', str(out),
                                 '--include', 'product', '--now', NOW]), 0)
        replay = S.read_json(out)
        self.assertIsNotNone(replay)
        self.assertEqual([r['repo'] for r in replay['repos']], ['acme/product'])
        self.assertEqual(replay['collected_at'], NOW)
        self.assertEqual(replay['repos'][0]['collected_at'], NOW)

    def test_malformed_snapshot_does_not_block_existing_panes(self):
        """Why: a damaged optional snapshot must not stop the legacy tracker from rendering."""
        from scripts import reconcile_repo_panes as R
        (self.root / 'repo-evidence.json').write_text('{invalid')
        data = {'streams': [['Worker', 'app', 'Keep', 'Nothing']]}
        before = json.loads(json.dumps(data))
        try:
            R.reconcile(data, self.cfg)
        except ValueError:
            self.fail('Malformed optional evidence blocked reconciliation')
        self.assertEqual(data, before)

    def test_reopened_pr_is_not_settled_by_old_close_cache(self):
        """Why: fresh open evidence must supersede an older close event from the legacy cache."""
        self.snapshot([record()])
        self.store('prs-closed.json', {'prs': [dict(record()['open_prs'][0], state='closed', closed_at=OLD)]})
        data = {'decisions': [{'id': 'dec-existing', 'src': 'ready-draft', 'state': 'open',
                              'pr': 'acme/product#7', 'text': '- acme/product#7'}]}
        S.reconcile_merges_lifecycle(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['decisions']), 1)
        self.assertEqual(data['decisions'][0]['state'], 'open')

    def test_repeated_built_page_preserves_response_and_ladder(self):
        """Why: an answered ask must not reopen at the same head and a changed head needs a new identity."""
        from scripts import reconcile_repo_panes as R
        row = record()
        self.snapshot([row])
        data = {}
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        identifier = data['decisions'][0]['id']
        S.apply_responses(data, [{'id': identifier, 'type': 'decision', 'value': 'accepted', 'timestamp': NOW}], set(), S.parse_time(NOW))
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        self.assertEqual(len(data['decisions']), 1)
        self.assertEqual(data['decisions'][0]['state'], 'settled')
        row['open_prs'][0]['head_sha'] = 'c' * 40
        self.snapshot([row])
        R.reconcile(data, self.cfg, now=S.parse_time(NOW))
        opened = [d for d in data['decisions'] if d['state'] == 'open']
        self.assertEqual(len(opened), 1)
        self.assertNotEqual(opened[0]['id'], identifier)


if __name__ == '__main__':
    unittest.main()
