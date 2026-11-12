"""Isolated regressions mirrored from the shared tracker freshness repair."""
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from flightdeck import sync as S

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-11-12T19:00:00Z'
OLD = '2026-11-09T12:00:00Z'


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cfg = S.deep_merge(S.DEFAULTS, {
            'cache_dir': str(self.root),
            'primary_stream': {'label': 'Lead'},
            'responses': {'key': 'responses/owner@example.com'},
        })
        self.now = S.parse_time(NOW)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps(self.cfg))
        env = {'FLIGHTDECK_CACHE': str(self.root), 'FLIGHTDECK_GH_DISABLE': '1',
               'CREW_CHAT_ANSWERS': str(self.root / 'pending-chat-answers.json'),
               'CREW_CHAT_STRICT': '0', 'CLOUDFLARE_API_TOKEN': ''}
        self.patcher = patch.dict(os.environ, env)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def store(self, name, value):
        S.write_json(self.root / name, value)

    def check(self, data):
        path = self.root / 'data.json'
        self.store('data.json', data)
        result = subprocess.run([
            sys.executable, str(ROOT / 'scripts/freshness.py'), '--data', str(path),
            '--config', str(self.config)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return S.read_json(path)

    def test_old_reports_preserve_prose_warn_duplicates_and_recover(self):
        """Why: stale reports must be marked without destroying source wording or rows."""
        data = {'streams': [['Bot', 'product', '', ''], ['Bot · product', 'other', '', '']]}
        report = {'agent': 'Bot', 'current': 'At 12:00: exact wording\n- second line',
                  'next': 'Exact next', 'at': OLD}
        self.store('bot-reports.json', [report])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            S.apply_bot_reports(data, self.cfg, now=self.now)
        prefix = 'Stale since 2026-11-09: '
        self.assertEqual(S.as_stream(data['streams'][0])['now'], prefix + report['current'])
        self.assertEqual(S.as_stream(data['streams'][0])['waiting'], prefix + report['next'])
        self.assertIn('duplicate', err.getvalue().lower())
        self.assertEqual(len(data['streams']), 2)
        S.reconcile_priorities(data, self.cfg)
        self.assertTrue(all(i['text'].startswith(prefix) for i in data['priorities'][0]['items']))
        S.apply_bot_reports(data, self.cfg, now=self.now)
        self.assertEqual(S.as_stream(data['streams'][0])['now'].count(prefix), 1)
        self.store('bot-reports.json', [{**report, 'at': NOW}])
        S.apply_bot_reports(data, self.cfg, now=self.now)
        self.assertEqual(S.as_stream(data['streams'][0])['now'], report['current'])

    def test_priorities_carry_stale_marker_without_creating_nothing_action(self):
        """Why: derived priorities inherit source age but must not turn Nothing into an action."""
        prefix = 'Stale since 2026-11-09: '
        data = {'streams': [['Bot', 'product', prefix + 'Current work', 'Review next']],
                'priorities': [{'stream': 'Bot', 'items': [{'text': 'Keep ladder', 'src': 'ladder'}]}]}
        S.reconcile_priorities(data, self.cfg)
        derived = [i for i in data['priorities'][0]['items'] if i.get('src') == 'stream']
        self.assertEqual([i['text'] for i in derived], [prefix + 'Current work', prefix + 'Review next'])
        data['streams'][0][3] = prefix + 'Nothing'
        S.reconcile_priorities(data, self.cfg)
        self.assertFalse(any(i['state'] == 'next' for i in data['priorities'][0]['items'] if i.get('src') == 'stream'))
        self.assertIn({'text': 'Keep ladder', 'src': 'ladder'}, data['priorities'][0]['items'])

    def test_missing_report_cache_still_warns_on_duplicate_names(self):
        """Why: a missing feed must neither hide duplicates nor delete existing streams."""
        data = {'streams': [['Bot', '', 'Keep', 'Nothing'], ['Bot · product', '', 'Keep too', 'Nothing']]}
        before = json.loads(json.dumps(data))
        with contextlib.redirect_stderr(io.StringIO()) as err:
            S.apply_bot_reports(data, self.cfg, now=self.now)
        self.assertEqual(data, before)
        self.assertIn('duplicate stream names', err.getvalue())

    def test_newest_report_wins_with_dict_stream_rows(self):
        """Why: unordered caches must not replace current work with older evidence."""
        data = {'streams': [{'bot': 'Bot', 'project': 'product', 'now': '', 'waiting': ''}]}
        self.store('bot-reports.json', [{'agent': 'Bot', 'at': NOW, 'current': 'New'},
                                        {'agent': 'Bot', 'at': OLD, 'current': 'Old'}])
        S.apply_bot_reports(data, self.cfg, now=self.now)
        self.assertEqual(data['streams'][0]['now'], 'New')
        self.assertEqual(data['streams'][0]['at'], NOW)

    def test_each_pane_flags_old_evidence_and_summary_is_idempotent(self):
        """Why: an on-time Activity refresh must not disguise old pane evidence."""
        self.store('bot-reports.json', [{'agent': 'Bot', 'at': OLD}])
        self.store('architecture-sync.json', {'repos': [{'tab_id': 'product', 'imported_at': OLD}]})
        data = {'activity': {'at': NOW}, 'summary': '- Existing summary.',
                'streams': [['Bot', 'product', '', '']], 'priorities': [{'stream': 'Bot'}],
                'steps': [{'done': False, 'opened_at': OLD}], 'decisions': [{'opened_at': OLD}],
                'projects': {'tabs': [{'id': 'product'}]}}
        out = self.check(data)
        self.assertEqual(set(out['freshness']['panes']),
                         {'decisions', 'streams', 'steps', 'priorities', 'architecture'})
        self.assertTrue(all(p['stale'] for p in out['freshness']['panes'].values()))
        self.assertGreater(out['freshness']['panes']['streams']['age_h'], 1)
        self.assertTrue(out['summary'].startswith(data['summary']))
        self.assertEqual(self.check(out)['summary'].count('- Stale:'), 1)

    def test_fresh_primary_does_not_hide_stale_or_unknown_sources(self):
        """Why: one fresh primary row cannot mask stale reports or unstamped steps."""
        self.store('prs.json', {'at': NOW})
        self.store('bot-reports.json', [{'agent': 'Bot', 'at': OLD}])
        out = self.check({'activity': {'at': NOW},
                          'streams': [['Lead', '', '', ''], {'bot': 'Bot'}],
                          'priorities': [{'stream': 'Bot'}], 'steps': [{'done': False}]})
        panes = out['freshness']['panes']
        self.assertTrue(all(panes[p]['stale'] for p in ('streams', 'priorities', 'steps')))
        fresh = self.check({'activity': {'at': NOW}, 'streams': [['Lead', '', '', '']]})
        self.assertFalse(fresh['freshness']['panes']['streams']['stale'])

    def test_hour_boundary_and_recovery_preserve_other_summary_lines(self):
        """Why: exactly one hour is allowed and recovery clears only generated warnings."""
        boundary = '2026-11-12T18:00:00Z'
        for name in ('bot-decisions.json', 'pending-chat-answers.json'):
            self.store(name, {})
            os.utime(self.root / name, (S.parse_time(boundary).timestamp(),) * 2)
        self.store('bot-reports.json', [{'agent': 'Bot', 'at': boundary}])
        self.store('architecture-sync.json', {'repos': [{'tab_id': 'product', 'imported_at': boundary}]})
        data = {'activity': {'at': NOW}, 'summary': 'Keep this.\n- Stale: old warning\nKeep this too.',
                'decisions': [{'meta': 'Auto 2026-11-12 18:30'}], 'streams': [['Bot', '', '', '']],
                'priorities': [{'stream': 'Bot'}], 'steps': [{'opened_at': boundary}],
                'projects': {'tabs': [{'id': 'product'}]}}
        out = self.check(data)
        self.assertFalse(any(p['stale'] for p in out['freshness']['panes'].values()))
        self.assertEqual(out['summary'], 'Keep this.\nKeep this too.')
        self.assertEqual(out['freshness']['panes']['streams']['age_h'], 1)
        self.assertEqual(out['freshness']['panes']['decisions']['newest'], '2026-11-12T18:30:00.000Z')

    def test_newest_report_and_pending_clock_are_used(self):
        """Why: pending diagrams and unordered reports retain their true evidence ages."""
        self.store('bot-reports.json', [{'agent': 'Bot', 'at': NOW}, {'agent': 'Bot', 'at': OLD}])
        out = self.check({'activity': {'at': NOW}, 'streams': [['Bot', '', '', '']],
                          'projects': {'tabs': [{'id': 'product', 'status': 'pending', 'pending_since': OLD}]}})
        panes = out['freshness']['panes']
        self.assertFalse(panes['streams']['stale'])
        self.assertTrue(panes['architecture']['stale'])
        self.assertEqual(panes['architecture']['reason'], '1 repo pending a diagram')
        self.assertIn('pending since 2026-11-09', panes['architecture']['items'][0]['label'])

    def test_missing_chat_capture_warns_and_fresh_decision_cannot_hide_it(self):
        """Why: a rebuilt PR card is not proof that chat capture works."""
        self.store('data.json', {'decisions': [{'id': 'dec-one', 'opened_at': NOW}]})
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/record_chat_accept.py'),
                                 '--ingest-pending', '--config', str(self.config),
                                 '--data', str(self.root / 'data.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('WARNING', result.stderr)
        self.assertEqual(S.read_json(self.root / 'chat-capture-status.json')['status'], 'missing')
        pane = self.check({'activity': {'at': NOW}, 'decisions': [{'opened_at': NOW}]})['freshness']['panes']['decisions']
        self.assertTrue(pane['stale'])
        self.assertIn('chat capture missing', pane['reason'])

    def test_trusted_chat_capture_records_once_and_rejects_invalid_evidence(self):
        """Why: diagnostics must not weaken validation or invent chat answers."""
        data = {'decisions': [{'id': 'dec-one', 'state': 'open'}]}
        answer = {'id': 'dec-one', 'author': 'owner@example.com', 'value': 'accepted',
                  'timestamp': NOW, 'ref': 'chat message', 'comment': ''}
        feed = {'captured_at': NOW, 'answers': [answer]}
        self.store('pending-chat-answers.json', feed)
        self.assertTrue(callable(getattr(S, 'ingest_pending', None)))
        self.assertEqual(S.ingest_pending(self.cfg, data, now=self.now, kv=False), 1)
        self.assertEqual(S.ingest_pending(self.cfg, data, now=self.now, kv=False), 0)
        self.assertEqual(len(S.chat_responses(self.cfg)), 1)
        S.apply_responses(data, S.chat_responses(self.cfg), set(), self.now)
        self.assertEqual(data['decisions'][0]['state'], 'settled')
        invalid = [
            {**feed, 'captured_at': OLD},
            {**feed, 'captured_at': '2026-11-12T19:00:00'},
            {**feed, 'answers': [{**answer, 'author': 'other@example.com'}]},
            {**feed, 'answers': [{**answer, 'id': 'dec-unknown'}]},
            {**feed, 'answers': [{**answer, 'timestamp': '2026-11-12T19:00:00'}]},
            {**feed, 'answers': [answer, {**answer, 'value': 'rejected'}]},
            {**feed, 'answers': [{**answer, 'value': 'comment'}]},
        ]
        before = S.chat_responses(self.cfg)
        for value in invalid:
            with self.subTest(value=value):
                self.store('pending-chat-answers.json', value)
                with self.assertRaises(ValueError):
                    S.ingest_pending(self.cfg, data, now=self.now, kv=False)
                self.assertEqual(S.chat_responses(self.cfg), before)
        with patch.dict(os.environ, {'CREW_CHAT_ANSWERS': str(self.root / 'missing'), 'CREW_CHAT_STRICT': '1'}):
            with self.assertRaises(FileNotFoundError):
                S.ingest_pending(self.cfg, data, now=self.now, kv=False)

    def test_steps_prune_only_dated_done_and_keep_release_guards(self):
        """Why: open work, legacy dates and release safety must survive archive pruning."""
        self.cfg['guards'] = [{'step_contains': 'Release', 'needs': 'nondraft_release'}]
        data = {'steps': [{'text': 'old', 'done': True, 'done_at': OLD},
                          {'text': 'undone', 'done': False, 'done_at': OLD},
                          {'text': 'Release', 'done': True, 'done_at': OLD},
                          {'text': 'recent', 'done': True, 'done_at': NOW},
                          {'text': 'legacy', 'done': True}]}
        S.reconcile_steps_evidence(data, self.cfg, now=self.now)
        self.assertEqual([s['text'] for s in data['steps']], ['undone', 'Release', 'recent', 'legacy'])
        self.assertNotIn('done_at', data['steps'][1])
        S.reconcile_steps_evidence(data, self.cfg, now=self.now)
        self.assertEqual([s['text'] for s in data['steps']], ['undone', 'Release', 'recent', 'legacy'])

    def test_step_tick_creation_install_and_release_have_event_stamps(self):
        """Why: pruning must use event evidence rather than the latest page build time."""
        self.store('prs-closed.json', {'prs': [{'repo': 'example/product', 'number': 1,
                   'merged': True, 'merged_at': OLD}]})
        data = {'steps': [{'text': 'Merge example/product#1', 'pr': 'example/product#1'}]}
        S.reconcile_merges_lifecycle(data, self.cfg, now=self.now)
        self.assertEqual(data['steps'][0].get('done_at'), OLD)
        data = {'steps': [{'id': 'step-one', 'text': 'Check', 'done': False}]}
        S.apply_responses(data, [{'id': 'step-one', 'type': 'step', 'value': 'done', 'timestamp': NOW}], set(), self.now)
        self.assertEqual(data['steps'][0]['done_at'], '2026-11-12T19:00:00.000Z')
        self.store('prs.json', {'prs': [{'repo': 'example/product', 'number': 2,
                                       'merge_state': 'CLEAN', 'checks': 'success'}]})
        data = {}
        S.reconcile_steps_evidence(data, self.cfg, now=self.now)
        self.assertEqual(data['steps'][0]['opened_at'], '2026-11-12T19:00:00.000Z')
        self.cfg['omb']['install_step_contains'] = 'Install app'
        self.store('omb-install.json', {'version': '1.2.3', 'checked_at': NOW})
        data = {'steps': [{'text': 'Install app', 'done': False}]}
        S.reconcile_steps_evidence(data, self.cfg, now=self.now)
        self.assertEqual(data['steps'][0]['done_at'], NOW)
        self.cfg['guards'] = [{'step_contains': 'Release', 'needs': 'nondraft_release'}]
        self.store('omb-releases.json', {'releases': [{'draft': False, 'published_at': NOW}]})
        data = {'steps': [{'text': 'Release', 'done': False}]}
        S.reconcile_steps_evidence(data, self.cfg, now=self.now)
        self.assertEqual(data['steps'][0]['done_at'], NOW)

    def test_counted_reasons_keep_full_item_evidence_without_long_summary(self):
        """Why: long source names belong in evidence, not chopped page text."""
        names = ['Worker' + str(i) + 'x' * 90 for i in range(15)]
        self.store('bot-reports.json', [{'agent': name, 'at': OLD if i < 13 else NOW}
                                        for i, name in enumerate(names)])
        data = {'activity': {'at': NOW}, 'summary': 'Original prose.',
                'streams': [[name, '', '', ''] for name in names],
                'priorities': [{'stream': name} for name in names],
                'steps': [{'done': False} for _ in range(24)],
                'projects': {'tabs': [{'id': f'p{i}', 'repo': f'p{i}', 'status': 'pending',
                                        'pending_since': OLD} for i in range(5)]}}
        out = self.check(data)
        panes = out['freshness']['panes']
        self.assertEqual(panes['streams']['reason'], '13 of 15 bot reports older than 1 h (oldest 9 Nov)')
        self.assertEqual(panes['steps']['reason'], 'no step has a date yet')
        self.assertEqual(panes['architecture']['reason'], '5 repos pending a diagram')
        self.assertEqual(len(panes['streams']['items']), 15)
        self.assertEqual(panes['streams']['items'][0]['label'], names[0] + ' report')
        self.assertEqual(panes['streams']['items'][0]['newest'], S.iso_z(S.parse_time(OLD)))
        self.assertEqual(len(panes['steps']['items']), 24)
        self.assertNotIn(names[0], out['summary'])
        self.assertIn('Stream: ' + panes['streams']['reason'], out['summary'])
        self.assertLess(len(out['summary']), 500)
        self.assertEqual(self.check(out)['summary'], out['summary'])

    def test_undated_completed_steps_alone_are_not_stale(self):
        """Why: completed legacy work is not evidence of an unhandled human action."""
        for activity in ({}, {'at': NOW}):
            pane = self.check({'activity': activity, 'steps': [{'done': True}, {'done': True}]})['freshness']['panes']['steps']
            self.assertFalse(pane['stale'])
            self.assertEqual(pane['reason'], 'no dated steps')
            self.assertEqual(len(pane['items']), 2)
        for rows, stale in (([{'done': True}, {'done': True, 'done_at': NOW}], False),
                            ([{'done': True}, {'done': True, 'done_at': OLD}], True),
                            ([{'done': False}, {'done': True, 'done_at': NOW}], True)):
            pane = self.check({'activity': {'at': NOW}, 'steps': rows})['freshness']['panes']['steps']
            self.assertEqual(pane['stale'], stale)

    def test_legacy_architecture_uses_only_repo_and_sha_bound_cache_dates(self):
        """Why: an unrelated repository push must never refresh an old imported diagram."""
        sha = 'a' * 40
        self.store('architecture-sync.json', {'repos': [
            {'repo': 'product', 'source': 'docs/diagrams/map.bower.json', 'source_repo_sha': sha}]})
        data = {'activity': {'at': NOW}, 'projects': {'tabs': [
            {'id': 'product', 'diagram': 'architecture/product.bower.json'}]}}
        self.store('prs-closed.json', {'prs': [{'repo': 'product', 'merge_sha': sha, 'merged_at': NOW}]})
        pane = self.check(data)['freshness']['panes']['architecture']
        self.assertEqual(pane['newest'], S.iso_z(S.parse_time(NOW)))
        self.assertFalse(pane['stale'])
        self.assertEqual(pane['items'][0]['source'], 'cached source commit')
        self.store('prs-closed.json', [{'repo': 'other', 'merge_sha': sha, 'merged_at': NOW}])
        self.store('repos.json', {'repos': [{'name': 'product', 'pushed_at': NOW}]})
        unknown = self.check(data)['freshness']['panes']['architecture']
        self.assertIsNone(unknown['newest'])
        self.assertTrue(unknown['stale'])
        self.store('repos.json', [{'name': 'product', 'head_sha': sha, 'committed_at': NOW}])
        self.assertFalse(self.check(data)['freshness']['panes']['architecture']['stale'])
        self.store('architecture-sync.json', {'repos': [
            {'repo': 'product', 'source': 'docs/diagrams/map.bower.json', 'source_repo_sha': sha, 'imported_at': OLD}]})
        imported = self.check(data)['freshness']['panes']['architecture']
        self.assertEqual(imported['newest'], S.iso_z(S.parse_time(OLD)))
        self.assertEqual(imported['items'][0]['source'], 'imported_at')

    def test_hook_tolerates_failed_interpreter(self):
        """Why: a diagnostic hook must not block publishing when Python cannot start."""
        fake = self.root / 'python3'
        fake.write_text('#!/bin/sh\nexit 19\n')
        fake.chmod(0o755)
        result = subprocess.run(['bash', str(ROOT / 'hooks/pre-render.d/92-freshness')],
                                env={**os.environ, 'PATH': f'{self.root}:' + os.environ['PATH']},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('WARNING', result.stderr)

    def test_advisory_tolerates_bad_input_and_write_failure(self):
        """Why: freshness diagnostics must remain advisory on invalid data or disk failure."""
        for content in ('not json', '{"activity": []}', '{}'):
            (self.root / 'data.json').write_text(content)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/freshness.py'),
                                     '--data', str(self.root / 'data.json'), '--config', str(self.config)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((ROOT / 'flightdeck/freshness.py').is_file())
        from flightdeck import freshness
        with patch.object(S, 'save', side_effect=OSError('read only')):
            self.assertEqual(freshness.main(['--data', str(self.root / 'data.json'),
                                            '--config', str(self.config)]), 0)


if __name__ == '__main__':
    unittest.main()
