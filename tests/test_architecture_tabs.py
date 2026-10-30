"""Architecture tabs require a registry, a real product diagram and rendered views."""
import datetime
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flightdeck.sync import _upsert_architecture, import_product_bowers, reconcile_inflight
from tests.test_sync import cfg, write

NOW = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=datetime.timezone.utc)


def diagram(name="product", nodes=3, auto=False):
    return {"schema": "bowerbird/v1", "meta": {"title": name, "auto": auto},
            "nodes": [{"id": name if i == 0 else f"n{i}"} for i in range(nodes)],
            "edges": [{"from": name, "to": "n1"}] if nodes > 1 else []}


class ArchitectureTabs(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.tmp = Path(self.dir.name)
        self.assets = self.tmp / "assets"
        self.loaded = cfg(self.tmp, owner="acme", assets_dir=str(self.assets),
                          primary_stream={"agent": "lead", "area": "Board", "label": "Lead"})
        self.cache = Path(self.loaded["cache_dir"])
        self.arch = self.assets / "architecture"
        self.arch.mkdir(parents=True)
        self.registry([{"id": "product", "source": "docs/diagrams/*.bower.json"}])
        self.products = self.tmp / "products"
        self.env = mock.patch.dict("os.environ", {"CREW_PRODUCT_ROOTS": str(self.products),
                                                 "CREW_TRACKER_OFFLINE": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def registry(self, entries):
        (self.arch / "registry.json").write_text(json.dumps({"version": 1, "repos": entries}))

    def product(self, name="product", file="system.bower.json", doc=None):
        folder = self.products / name / "docs" / "diagrams"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / file
        path.write_text(json.dumps(doc if doc is not None else diagram(name)))
        return path

    def render(self, name):
        raw = (self.arch / f"{name}.bower.json").read_bytes()
        for view in ("flat", "iso"):
            folder = self.arch / "rendered" / view
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{name}.html").write_text("<html>real diagram</html>")
        (self.arch / "rendered" / "manifest.json").write_text(json.dumps({
            "diagrams": {f"{name}.bower.json": {"sha256": hashlib.sha256(raw).hexdigest()}}}))

    def run_inflight(self, data=None, repos=None):
        write(self.cache / "repos.json", {"complete": True, "repos": repos or []})
        write(self.cache / "prs.json", {"complete": True, "prs": []})
        data = data if data is not None else {"merges": [], "streams": [], "decisions": [], "projects": {"tabs": []}}
        self.assertEqual(reconcile_inflight(data, self.loaded, now=NOW), 0)
        return data

    def test_empty_upsert_keeps_existing_tabs(self):
        """Why: an architecture upsert that produces no tabs must not blank the pane."""
        self.registry([])
        prior = [{"id": "omb", "diagram": "architecture/openmausbot.bower.json"}]
        data = {"merges": [], "streams": [], "decisions": [],
                "projects": {"tabs": list(prior), "rule": "tip rule", "verified": "kept"}}
        with mock.patch("flightdeck.sync.stream_architecture_entries", return_value=[]), \
             mock.patch("flightdeck.sync.import_product_bowers", return_value={}), \
             mock.patch("flightdeck.sync._demote_thin_architecture"):
            _upsert_architecture(data, self.loaded, [], [])
        self.assertEqual(data["projects"]["tabs"], prior)
        self.assertEqual(len(data["projects"]["tabs"]), 1)

    def test_opt_in_requires_product_source_and_rendered_views(self):
        """Why: no tab can show a stale page before the product's diagram is rendered."""
        source = self.product()
        self.product(name="unlisted")
        data = self.run_inflight()
        self.assertTrue(all(t.get("status") == "pending" for t in data["projects"]["tabs"]))
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), source.read_bytes())
        self.render("product")
        data = self.run_inflight(data)
        self.assertIn({"id": "product", "diagram": "architecture/product.bower.json", "stream": None},
                      data["projects"]["tabs"])
        [e] = [r for r in json.loads((self.cache / "architecture-sync.json").read_text())["repos"]
               if r.get("repo") == "product"]
        self.assertEqual((e["status"], e["node_count"], e["edge_count"]), ("imported", 3, 1))
        self.assertEqual(e["bower_hash"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse((self.arch / "unlisted.bower.json").exists())

    def test_missing_source_clears_old_tab(self):
        """Why: a cached rich diagram cannot replace missing product documentation."""
        self.arch.joinpath("product.bower.json").write_text(json.dumps(diagram()))
        data = self.run_inflight({"merges": [], "streams": [], "decisions": [], "projects": {
            "tabs": [{"id": "product", "diagram": "architecture/product.bower.json"}]}})
        self.assertTrue(all(t.get("status") == "pending" for t in data["projects"]["tabs"]))
        [e] = [r for r in json.loads((self.cache / "architecture-sync.json").read_text())["repos"]
               if r.get("repo") == "product"]
        self.assertEqual(e["status"], "pending diagram PR")

    def test_any_auto_or_thin_diagram_has_no_tab(self):
        """Why: no Architecture tab may ever reference an Auto or thin placeholder."""
        for kind, doc in (("auto", diagram(auto=True)),
                          ("subtitle", dict(diagram(), meta={"subtitle": "Auto stub for product"})),
                          ("thin", diagram(nodes=1))):
            with self.subTest(kind=kind):
                self.product(doc=doc)
                data = self.run_inflight()
                for tab in data["projects"]["tabs"]:
                    if not tab.get("diagram"):
                        continue
                    chosen = json.loads((self.assets / tab["diagram"]).read_text())
                    self.assertFalse(chosen.get("meta", {}).get("auto") or
                                     "Auto stub" in json.dumps(chosen) or
                                     (len(chosen.get("nodes") or []) <= 1 and not chosen.get("edges")))
                self.assertTrue(all(not t.get("diagram") for t in data["projects"]["tabs"]))
                self.assertFalse((self.arch / "product.bower.json").exists())

    def test_stream_auto_discovers_real_diagram_and_pending_pr(self):
        """Why: streams get a slot without hand registration or an invented placeholder."""
        self.registry([])
        rows = {"merges": [], "decisions": [], "streams": [{"bot": "Worker", "project": "product"}]}
        repo = [{"name": "product", "full_name": "acme/product"}]
        source = self.product()
        data = self.run_inflight(rows, repo)
        self.assertTrue(any(t.get("id") == "product" and t.get("status") == "pending"
                            for t in data["projects"]["tabs"]))
        self.render("product")
        data = self.run_inflight(rows, repo)
        self.assertTrue(any(t.get("id") == "product" and t.get("diagram") == "architecture/product.bower.json"
                            for t in data["projects"]["tabs"]))
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), source.read_bytes())
        deprecated = source.parents[2] / "deprecated"
        deprecated.mkdir()
        source.rename(deprecated / source.name)
        write(self.cache / "architecture-diagram-prs.json", [{"repo": "product", "isDraft": True,
              "url": "https://github.com/acme/product/pull/7"}])
        data = self.run_inflight(rows, repo)
        self.assertTrue(any(t.get("id") == "product" and t.get("pr_url") ==
                            "https://github.com/acme/product/pull/7" for t in data["projects"]["tabs"]))

    def test_done_requires_complete_overlay_at_current_head(self):
        """Why: done with incomplete evidence stays; a later product commit restores a dropped tab."""
        self.registry([])
        source = self.product()
        checkout = source.parents[2]
        subprocess.run(["git", "init", str(checkout)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(checkout), "add", "docs/diagrams"], check=True)
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=test", "-c", "user.email=test@example.com",
                        "commit", "-m", "diagram"], check=True, capture_output=True)
        data = {"merges": [], "decisions": [], "streams": [{"bot": "Worker", "project": "product", "done": True}]}
        repo = [{"name": "product", "full_name": "acme/product"}]
        self.run_inflight(data, repo)
        self.render("product")
        data = self.run_inflight(data, repo)
        self.assertTrue(any(t.get("id") == "product" for t in data["projects"]["tabs"]))
        evidence = json.loads((self.cache / "architecture-sync.json").read_text())
        [record] = [r for r in evidence["repos"] if r.get("stream") == "Worker"]
        record["overlay"] = {"product": {"completion": "complete"}}
        write(self.cache / "architecture-sync.json", evidence)
        data = self.run_inflight(data, repo)
        self.assertFalse(any(t.get("id") == "product" for t in data["projects"]["tabs"]))
        source.write_text(source.read_text() + "\n")
        subprocess.run(["git", "-C", str(checkout), "add", "docs/diagrams"], check=True)
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=test", "-c", "user.email=test@example.com",
                        "commit", "-m", "change"], check=True, capture_output=True)
        data = self.run_inflight(data, repo)
        self.assertTrue(any(t.get("id") == "product" for t in data["projects"]["tabs"]))

    def test_project_names_and_shared_repo_do_not_duplicate_tabs(self):
        self.registry([])
        rows = {"merges": [], "decisions": [], "streams": [
            {"bot": "Alpha", "project": "product + second"},
            {"bot": "Beta", "project": "product"}]}
        repos = [{"name": "product"}, {"name": "second"}]
        data = self.run_inflight(rows, repos)
        self.assertEqual([(t["id"], t["repo"]) for t in data["projects"]["tabs"] if t.get("repo")],
                         [("product", "product"), ("second", "second")])

    def test_main_tip_overrides_dirty_checkout(self):
        """Why: discovery follows the product commit, not a locally stale diagram."""
        source = self.product(doc=diagram("local"))
        raw = json.dumps(diagram("main")).encode()
        with mock.patch("flightdeck.sync._product_tip_bowers", return_value=("a" * 40, [("system.bower.json", raw)])):
            imported = import_product_bowers([{"id": "product", "source": "docs/diagrams/*.bower.json"}],
                                             self.assets, "acme")
        self.assertEqual(imported["product"]["source_repo_sha"], "a" * 40)
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), raw)
        self.assertNotEqual(source.read_bytes(), raw)

    def test_online_remote_failure_keeps_local_checkout_pending(self):
        """Why: an unverified local file cannot substitute for missing main evidence."""
        self.product()
        with mock.patch("flightdeck.sync._product_tip_bowers", return_value=None), \
             mock.patch.dict("os.environ", {"CREW_TRACKER_OFFLINE": "0"}):
            imported = import_product_bowers([{"id": "product", "source": "docs/diagrams/*.bower.json"}],
                                             self.assets, "acme")
        self.assertEqual(imported, {})
        self.assertFalse((self.arch / "product.bower.json").exists())

    def test_richest_wildcard_wins(self):
        """Why: selection follows authored richness rather than file ordering."""
        self.product(file="a.bower.json", doc=diagram(nodes=3))
        source = self.product(file="b.bower.json", doc=diagram(nodes=8))
        self.run_inflight()
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
