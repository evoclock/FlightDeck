"""Sidecar evidence is merged before publish without changing its sources."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks/pre-render.d/02b-merge-sidecars"


def put(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def report(agent, at, current="working"):
    return {"agent": agent, "area": "area", "current": current, "next": "next", "at": at}


def response(rid, at, value="accepted"):
    return {"id": rid, "type": "decision", "value": value, "timestamp": at}


OLD = "2026-11-10T00:00:00Z"
NEW = "2026-11-11T00:00:00Z"


class MergeSidecarsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.root = Path(self.tmpdir.name)
        self.cache = self.root / "cache"
        self.a = self.root / "a"
        self.b = self.root / "b"
        self.a.mkdir()
        self.b.mkdir()

    def run_hook(self, dirs=None):
        env = {**os.environ, "FLIGHTDECK_CACHE": str(self.cache)}
        env.pop("CREW_TRACKER_SIDECAR_DIRS", None)
        if dirs is not None:
            env["CREW_TRACKER_SIDECAR_DIRS"] = dirs
        proc = subprocess.run([str(HOOK)], cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def test_unset_empty_and_missing_are_clean_no_ops(self):
        """Why: offline publishes must not create an evidence cache."""
        for dirs in (None, "", str(self.root / "missing")):
            proc = self.run_hook(dirs)
            self.assertEqual(len(proc.stdout.splitlines()), 1)
            self.assertIn("skipping", proc.stdout)
            self.assertFalse(self.cache.exists())

    def test_merges_newest_and_preserves_undo_and_inputs(self):
        """Why: newer evidence and Undo must survive without changing raw inputs."""
        put(self.cache / "bot-reports.json", {"reports": [report("one", NEW, "cached")]})
        put(self.cache / "responses.json", {"email": "local", "responses": [
            response("dec-one", NEW), response("dec-undo", OLD, "undone"),
            response("dec-update", OLD, "rejected")]})
        put(self.a / "bot-reports.json", [report("one", OLD, "stale"), report("two", OLD)])
        put(self.b / "bot-reports.json", {"reports": [report("two", NEW, "fresh")]})
        put(self.a / "responses.json", {"responses": [response("dec-one", OLD, "rejected"),
                                                   response("dec-undo", NEW), response("dec-two", NEW),
                                                   response("dec-update", NEW)]})
        put(self.b / "responses.json", [response("dec-two", OLD, "rejected")])
        inputs = {p: p.read_bytes() for d in (self.a, self.b) for p in d.iterdir()}
        self.run_hook(f"{self.a}:{self.b}")
        reports = json.loads((self.cache / "bot-reports.json").read_text())["reports"]
        answers = json.loads((self.cache / "responses.json").read_text())
        self.assertEqual({r["agent"]: r["current"] for r in reports},
                         {"one": "cached", "two": "fresh"})
        self.assertEqual({r["id"]: r["value"] for r in answers["responses"]},
                         {"dec-one": "accepted", "dec-undo": "undone", "dec-two": "accepted",
                          "dec-update": "accepted"})
        self.assertEqual(answers["email"], "local")
        snapshot = {p: p.read_bytes() for p in self.cache.iterdir()}
        self.run_hook(f"{self.a}:{self.b}")
        self.assertEqual(snapshot, {p: p.read_bytes() for p in self.cache.iterdir()})
        self.assertEqual(inputs, {p: p.read_bytes() for p in inputs})

    def test_bad_file_and_row_are_skipped_independently(self):
        """Why: corrupt sidecars must not block valid evidence from other files."""
        bad = self.a / "responses.json"
        bad.write_text("{broken", encoding="utf-8")
        put(self.a / "bot-reports.json", [report("good", NEW), {"agent": "bad"}])
        put(self.b / "responses.json", [response("dec-good", NEW), {"id": "dec-bad"}])
        proc = self.run_hook(f"{self.a}:{self.b}")
        self.assertIn(str(bad), proc.stderr)
        self.assertIn(str(self.a / "bot-reports.json"), proc.stderr)
        self.assertIn(str(self.b / "responses.json"), proc.stderr)
        self.assertEqual(len(json.loads((self.cache / "bot-reports.json").read_text())["reports"]), 1)
        self.assertEqual(len(json.loads((self.cache / "responses.json").read_text())["responses"]), 1)
        self.assertEqual(bad.read_text(), "{broken")

    def test_unreadable_cache_is_not_replaced(self):
        """Why: a damaged cache must not silently discard earlier human answers."""
        cache = self.cache / "responses.json"
        cache.parent.mkdir(parents=True)
        cache.write_text("{broken", encoding="utf-8")
        put(self.a / "responses.json", [response("dec-new", NEW)])
        proc = self.run_hook(str(self.a))
        self.assertIn(str(cache), proc.stderr)
        self.assertEqual(cache.read_text(), "{broken")


if __name__ == "__main__":
    unittest.main()
