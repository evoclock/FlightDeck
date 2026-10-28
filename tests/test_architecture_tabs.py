"""In-flight products get Architecture tabs only from rich authored diagrams."""
import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from flightdeck.sync import reconcile_inflight
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

    def render(self, stem, repos, nodes, auto_stub=False):
        meta = {"title": stem, "repos": repos}
        if auto_stub:
            meta["subtitle"] = f"Auto stub for {stem}. Replace when the shape is known."
        doc = {"schema": "bowerbird/v1", "meta": meta,
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
        self.assertEqual(tabs["omb"], "architecture/openmausbot.bower.json")
        self.assertEqual(tabs["aim2"], "architecture/aim-2.bower.json")
        self.assertNotIn("openmausbot", tabs)
        self.assertNotIn("mus-clockeome-aim-2", tabs)
        self.assertEqual(tabs["pi-bowerbird"], "architecture/pi-bowerbird.bower.json")
        # No rich authored diagram → no Architecture tab.
        self.assertNotIn("electric-twin-ces", tabs)
        self.assertFalse((self.assets / "architecture" / "electric-twin-ces.bower.json").exists())
        self.assertNotIn("streamed", tabs)
        self.assertNotIn("decided", tabs)
        self.assertNotIn("old-thing", tabs)
        self.assertNotIn("curated", tabs)
        # 1-node old-thing demoted
        self.assertTrue((self.assets / "architecture" / "stubs" / "old-thing.bower.json").exists()
                        or not (self.assets / "architecture" / "old-thing.bower.json").exists())

    def test_new_repo_title_without_colon_omits_without_rich(self):
        data = {"merges": [], "streams": [], "decisions": [{"state": "open", "title": "New repo quiet"}]}
        tabs = self.tabs(self.run_inflight(data, [repo("quiet", pushed=OLD)], []))
        self.assertNotIn("quiet", tabs)

    def test_stub_tab_upgrades_when_a_rich_diagram_lands(self):
        repos = [repo("fresh")]
        data = self.run_inflight({"merges": [], "streams": [], "decisions": []}, repos, [])
        self.assertNotIn("fresh", self.tabs(data))
        self.render("fresh", ["acme/fresh"], 6)
        tabs = self.tabs(self.run_inflight(data, repos, []))
        self.assertEqual(tabs, {"fresh": "architecture/fresh.bower.json"})

    def test_unrendered_or_thin_diagram_is_not_used(self):
        (self.assets / "architecture" / "raw.bower.json").write_text(json.dumps(
            {"schema": "bowerbird/v1", "meta": {"repos": ["acme/raw"], "subtitle": "Auto stub for raw."},
             "nodes": [{"id": "a"}], "edges": []}))
        tabs = self.tabs(self.run_inflight({"merges": [], "streams": [], "decisions": []}, [repo("raw")], []))
        self.assertNotIn("raw", tabs)
        self.assertTrue((self.assets / "architecture" / "stubs" / "raw.bower.json").exists())

    def test_three_node_auto_stub_demoted(self):
        self.render("frontend-work", ["acme/frontend-work"], 3, auto_stub=True)
        repos = [repo("frontend-work", created="2026-10-24T12:00:00Z")]
        data = {"merges": [], "streams": [], "decisions": [],
                "projects": {"tabs": [{"id": "frontend-work",
                                       "diagram": "architecture/frontend-work.bower.json", "auto": True}]}}
        tabs = self.tabs(self.run_inflight(data, repos, []))
        self.assertNotIn("frontend-work", tabs)
        self.assertFalse((self.assets / "architecture" / "frontend-work.bower.json").exists())
        self.assertTrue((self.assets / "architecture" / "stubs" / "frontend-work.bower.json").exists())

    def test_rerun_is_idempotent(self):
        repos = [repo("pi-bowerbird")]
        first = self.run_inflight({"merges": [], "streams": [], "decisions": [], "projects": {"tabs": []}}, repos, [])
        snapshot = json.loads(json.dumps(first["projects"]["tabs"]))
        second = self.run_inflight(json.loads(json.dumps(first)), repos, [])
        self.assertEqual(snapshot, second["projects"]["tabs"])
        ids = [t["id"] for t in second["projects"]["tabs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["pi-bowerbird"])


if __name__ == "__main__":
    unittest.main()
