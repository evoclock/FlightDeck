"""Complete offline collector round trips with required checks and cached branch tips."""
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flightdeck import sync as S
from scripts import collect_repo_evidence as C
from tests.test_repo_evidence import NOW, OLD, ROOT


class RepoCollectorTests(unittest.TestCase):
    def test_conditional_read_reuses_only_confirmed_unchanged_response(self):
        """ETag reuse saves quota without turning failed reads into fresh evidence."""
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = '/repos/acme/product/branches?per_page=100&page=1'
            ok = b'HTTP/2.0 200 OK\nETag: "one"\r\n\r\n[{"name":"main"}]'
            unchanged = b'HTTP/2.0 304 Not Modified\nETag: "one"\r\n\r\n'
            with patch.object(C.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess([], 0, ok, b''),
                    subprocess.CompletedProcess([], 1, unchanged, b'gh: HTTP 304'),
                    subprocess.CompletedProcess([], 1, b'', b'API rate limit exceeded')]) as runner:
                client = C.GitHub(cache_dir=Path(tmp) / 'gh-conditional')
                self.assertEqual(client.get(path), [{"name": "main"}])
                self.assertEqual(client.get(path), [{"name": "main"}])
                self.assertIn('If-None-Match: "one"', runner.call_args_list[1].args[0])
                with self.assertRaises(C.Unavailable):
                    client.get(path)
                with self.assertRaises(C.Unavailable):
                    client.get(path)
                self.assertEqual(runner.call_count, 3)

    def test_collects_required_checks_and_reuses_immutable_branch_tips(self):
        """Why: normalized PRs need all required contexts and unchanged branch tips must not be refetched."""
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            root = Path(tmp)
            config = root / 'sync.json'
            config.write_text(json.dumps({'owner': 'acme', 'cache_dir': str(root)}))
            base = '/repos/acme/product'
            sha = 'a' * 40
            loose = 'c' * 40
            pr = {'number': 1, 'title': 'Change', 'draft': True, 'state': 'open', 'updated_at': NOW,
                  'user': {'login': 'contributor'}, 'head': {'sha': sha}, 'base': {'ref': 'main'},
                  'mergeable_state': 'clean', 'html_url': 'https://github.com/acme/product/pull/1'}
            tip = {'sha': sha, 'commit': {'message': 'One line\nMore', 'committer': {'date': NOW}}}
            fixtures = {'repos': [{'name': 'product', 'pushedAt': NOW, 'visibility': 'private'}], 'api': {
                base + '/pulls?state=open&per_page=100&page=1': [pr],
                base + '/pulls/1': pr,
                base + '/branches/main': {'protection': {'required_status_checks': {'contexts': ['external/ci']}}},
                base + '/rules/branches/main': [{'type': 'required_status_checks', 'parameters': {
                    'required_status_checks': [{'context': 'tests'}]}}],
                base + f'/commits/{sha}/status?per_page=100&page=1': {'statuses': [{'context': 'external/ci', 'state': 'success'}]},
                base + f'/commits/{sha}/check-runs?filter=latest&per_page=100&page=1': {'check_runs': [
                    {'name': 'tests', 'status': 'completed', 'conclusion': 'success'}]},
                base + '/pulls?state=closed&sort=updated&direction=desc&per_page=100&page=1': [],
                base + '/commits?sha=main&since=2026-11-01T12%3A00%3A00Z&per_page=100&page=1': [tip],
                base + '/commits?sha=main&per_page=1': [tip],
                base + '/branches?per_page=100&page=1': [{'name': 'main', 'commit': {'sha': sha}},
                    {'name': 'loose', 'commit': {'sha': loose}}],
                base + '/commits/' + loose: dict(tip, sha=loose),
                base + '/commits/' + loose + '/pulls?per_page=100&page=1': []}}
            fixture_path = root / 'repo-evidence-fixtures.json'
            fixture_path.write_text(json.dumps(fixtures))
            with patch.dict('os.environ', {'FLIGHTDECK_CACHE': str(root), 'FLIGHTDECK_GH_OWNER': 'acme'}):
                args = ['--config', str(config), '--offline', '--since', OLD, '--now', NOW]
                self.assertEqual(C.main(args), 0)
                row = S.read_json(root / 'repo-evidence.json')['repos'][0]
                self.assertNotIn('error', row)
                self.assertEqual(row['open_prs'][0].get('required_checks'), ['external/ci', 'tests'])
                self.assertEqual(row['open_prs'][0]['checks'], 'success')
                self.assertEqual(row['open_prs'][0]['head_sha'], sha)
                self.assertEqual(row['open_prs'][0]['author'], 'contributor')
                self.assertEqual(row['visibility'], 'private')
                self.assertEqual(row['commits']['count'], 1)
                self.assertEqual(row['commits']['tip']['title'], 'One line')
                self.assertEqual(row['branches'], [{'name': 'loose', 'last_commit_at': NOW}])
                fixtures['api'].pop(base + '/commits/' + loose)
                fixtures['api'].pop(base + '/commits/' + loose + '/pulls?per_page=100&page=1')
                fixture_path.write_text(json.dumps(fixtures))
                self.assertEqual(C.main(args), 0)
                cached = S.read_json(root / 'repo-evidence.json')['repos'][0]
                self.assertNotIn('error', cached)
                self.assertEqual(cached['branches'], row['branches'])
                self.assertEqual(C.main(args + ['--exclude', 'product']), 0)
                self.assertEqual(S.read_json(root / 'repo-evidence.json')['repos'], [])


if __name__ == '__main__':
    unittest.main()
