"""Every in-flight product on Merges, Streams, or a New repo Decision gets an Architecture tab."""
import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from flightdeck.sync import reconcile_inflight
from flightdeck.widgets.architecture import load_diagram
from tests.test_sync import cfg, write

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
RECENT = "2026-10-25T10:00:00Z"
OLD = "2020-01-01T00:00:00Z"


def repo(name, pushed=RECENT, created=OLD):
    return {"name": name, "full_name": f"acme/{name}", "pushed_at": pushed, "created_at": created}


class ArchitectureTabs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.assets = self.tmp / "assets"
        self.loaded = cfg(self.tmp, owner="acme", assets_dir=str(self.assets),
                          primary_stream={"agent": "lead", "area": "Board", "label": "Lead"})
        self.cache = Path(self.loaded["cache_dir"])
        self.render("openmausbot", ["acme/OpenMausBot"], 10)
        self.render("pi-bowerbird", ["acme/pi-bowerbird"], 9)
        self.render("aim-2", ["acme/aim-2", "acme/mus-clockeome-aim-2"], 10)
        self.render("old-thing", ["acme/old-thing"], 1)

    def tearDown(self):
        self.dir.cleanup()

    def render(self, stem, repos, nodes):
        doc = {"schema": "bowerbird/v1", "meta": {"title": stem, "repos": repos},
               "nodes": [{"id": f"n{i}"} for i in range(nodes)], "edges": []}
        raw = json.dumps(doc).encode()
        arch = self.assets / "architecture"
        arch.mkdir(parents=True, exist_ok=True)
        (arch / f"{stem}.bower.json").write_bytes(raw)
        rendered = arch / "rendered"
        for view in ("flat", "iso"):
            (rendered / view).mkdir(parents=True, exist_ok=True)
            (rendered / view / f"{stem}.html").write_text("<html><body>x</body></html>", encoding="utf-8")
        manifest_path = rendered / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"diagrams": {}}
        manifest["diagrams"][f"{stem}.bower.json"] = {"sha256": hashlib.sha256(raw).hexdigest()}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def run_inflight(self, data, repos, prs):
        write(self.cache / "repos.json", {"complete": True, "repos": repos})
        write(self.cache / "prs.json", {"complete": True, "prs": prs})
        self.assertEqual(reconcile_inflight(data, self.loaded, now=NOW), 0)
        return data

    def tabs(self, data):
        return {t["id"]: t["diagram"] for t in data["projects"]["tabs"]}

    def test_every_inflight_product_gets_a_tab(self):
        repos = [repo("pi-bowerbird"), repo("electric-twin-ces", created="2026-10-24T12:00:00Z"),
                 repo("mus-clockeome-aim-2"), repo("old-thing", pushed=OLD), repo("streamed", pushed=OLD),
                 repo("decided", pushed=OLD)]
        prs = [{"number": 69, "title": "Keep sessions", "repo": "acme/OpenMausBot", "author": "ada",
                "url": "https://github.com/acme/OpenMausBot/pull/69", "state": "open"}]
        data = {
            "merges": [],
            "streams": [{"bot": "Tot", "project": "streamed parity", "now": "", "waiting": ""}],
            "decisions": [{"state": "open", "title": "New repo: decided"}],
            "projects": {"tabs": [
                {"id": "omb", "diagram": "architecture/openmausbot.bower.json"},
                {"id": "aim2", "diagram": "architecture/aim-2.bower.json"},
                {"id": "old-thing", "diagram": "architecture/old-thing.bower.json", "auto": True},
                {"id": "curated", "diagram": "architecture/aim-2.bower.json"},
            ]},
        }
        tabs = self.tabs(self.run_inflight(data, repos, prs))
        # Existing tabs that already draw the repo are reused, not duplicated.
        self.assertEqual(tabs["omb"], "architecture/openmausbot.bower.json")
        self.assertEqual(tabs["aim2"], "architecture/aim-2.bower.json")
        self.assertNotIn("openmausbot", tabs)
        self.assertNotIn("mus-clockeome-aim-2", tabs)
        # A rich diagram with no tab gets one.
        self.assertEqual(tabs["pi-bowerbird"], "architecture/pi-bowerbird.bower.json")
        # A repo no diagram draws gets a stub tab and a loadable stub file.
        self.assertEqual(tabs["electric-twin-ces"], "architecture/stubs/electric-twin-ces.bower.json")
        diagram = load_diagram(self.assets, tabs["electric-twin-ces"])[0]
        self.assertEqual(diagram["meta"]["repos"], ["acme/electric-twin-ces"])
        # Repos named only in Streams or an open New repo Decision get tabs too.
        self.assertIn("streamed", tabs)
        self.assertIn("decided", tabs)
        # Tabs whose repos left the in-flight window drop (auto or curated keep-set gone).
        self.assertNotIn("old-thing", tabs)
        self.assertNotIn("curated", tabs)
        self.assertEqual(data["projects"]["pending"], [])

    def test_new_repo_title_without_colon(self):
        data = {"merges": [], "streams": [], "decisions": [{"state": "open", "title": "New repo quiet"}]}
        tabs = self.tabs(self.run_inflight(data, [repo("quiet", pushed=OLD)], []))
        self.assertEqual(tabs["quiet"], "architecture/stubs/quiet.bower.json")

    def test_stub_tab_upgrades_when_a_rich_diagram_lands(self):
        repos = [repo("fresh")]
        data = self.run_inflight({"merges": [], "streams": [], "decisions": []}, repos, [])
        self.assertEqual(self.tabs(data)["fresh"], "architecture/stubs/fresh.bower.json")
        self.render("fresh", ["acme/fresh"], 6)
        tabs = self.tabs(self.run_inflight(data, repos, []))
        self.assertEqual(tabs, {"fresh": "architecture/fresh.bower.json"})

    def test_unrendered_diagram_is_not_used(self):
        (self.assets / "architecture" / "raw.bower.json").write_text(json.dumps(
            {"schema": "bowerbird/v1", "meta": {"repos": ["acme/raw"]}, "nodes": [{"id": "a"}], "edges": []}))
        tabs = self.tabs(self.run_inflight({"merges": [], "streams": [], "decisions": []}, [repo("raw")], []))
        self.assertEqual(tabs["raw"], "architecture/stubs/raw.bower.json")

    def test_rerun_is_idempotent(self):
        repos = [repo("electric-twin-ces", created="2026-10-24T12:00:00Z"), repo("pi-bowerbird")]
        first = self.run_inflight({"merges": [], "streams": [], "decisions": [], "projects": {"tabs": []}}, repos, [])
        snapshot = json.loads(json.dumps(first["projects"]["tabs"]))
        second = self.run_inflight(json.loads(json.dumps(first)), repos, [])
        self.assertEqual(snapshot, second["projects"]["tabs"])
        ids = [t["id"] for t in second["projects"]["tabs"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
