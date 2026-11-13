"""Planned-work collectors read local files or gh payloads, never invent inventory."""
import json
import tempfile
import unittest
from pathlib import Path

from flightdeck.architecture_sources import collect_planned_sources, _decode_contents


class FakeGH:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, argv, timeout=20):
        path = argv[0]
        self.calls.append(path)
        if path not in self.routes:
            return 1, "", "missing"
        payload = self.routes[path]
        if isinstance(payload, (dict, list)):
            return 0, json.dumps(payload), ""
        return 0, payload, ""


class PlannedSources(unittest.TestCase):
    def test_local_checkout_reads_tasks_specs_and_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "TASKS.md").write_text("## Backlog\n- [ ] Write tests <!-- id: T-1 -->\n")
            (root / "README.md").write_text("# Demo\n\nA demo repo.\n")
            (root / "contracts").mkdir()
            (root / "contracts" / "handoff.md").write_text("# handoff\n")
            sources = collect_planned_sources("example", "demo", root=root, offline=True)
        self.assertIn("Write tests", sources["tasks_md"])
        self.assertIn("Demo", sources["readme"])
        self.assertEqual(sources["docs"][0]["path"], "contracts/handoff.md")
        self.assertEqual(sources["open_prs"], [])

    def test_gh_collects_prs_merges_and_docs(self):
        import base64
        tasks = base64.b64encode(b"## Done\n- [x] Land it <!-- id: T-9 -->\n").decode()
        fake = FakeGH({
            "repos/example/app": {"default_branch": "main"},
            "repos/example/app/contents/TASKS.md?ref=main": {"type": "file", "encoding": "base64", "content": tasks},
            "repos/example/app/contents/README.md?ref=main": {"type": "file", "encoding": "base64",
                "content": base64.b64encode(b"# App\n").decode()},
            "repos/example/app/git/trees/main?recursive=1": {
                "tree": [
                    {"type": "blob", "path": "src/main.py"},
                    {"type": "blob", "path": "specs/plan.md"},
                    {"type": "blob", "path": "README.md"},
                ]
            },
            "repos/example/app/pulls?state=open&per_page=20&sort=updated": [
                {"number": 4, "title": "Add tests", "head": {"ref": "feat/tests"}, "html_url": "https://x/4"}
            ],
            "repos/example/app/pulls?state=closed&per_page=20&sort=updated": [
                {"number": 3, "title": "Ship parser", "merged_at": "2026-11-01T00:00:00Z", "html_url": "https://x/3"},
                {"number": 2, "title": "Closed no merge", "merged_at": None, "html_url": "https://x/2"},
            ],
        })
        sources = collect_planned_sources("example", "app", runner=fake, offline=False)
        self.assertIn("Land it", sources["tasks_md"])
        self.assertEqual(sources["docs"][0]["path"], "specs/plan.md")
        self.assertEqual([pr["number"] for pr in sources["open_prs"]], [4])
        self.assertEqual([pr["number"] for pr in sources["merges"]], [3])
        # file-tree blobs that are not specs must not become docs
        self.assertEqual([doc["path"] for doc in sources["docs"]], ["specs/plan.md"])

    def test_decode_ignores_non_files(self):
        self.assertIsNone(_decode_contents({"type": "dir"}))


if __name__ == "__main__":
    unittest.main()
