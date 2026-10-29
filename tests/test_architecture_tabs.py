"""Architecture tabs require a registry, a real product diagram and rendered views."""
import datetime
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flightdeck.sync import reconcile_inflight
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
        self.env = mock.patch.dict("os.environ", {"CREW_PRODUCT_ROOTS": str(self.products)})
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

    def run_inflight(self, data=None):
        write(self.cache / "repos.json", {"complete": True, "repos": []})
        write(self.cache / "prs.json", {"complete": True, "prs": []})
        data = data if data is not None else {"merges": [], "streams": [], "decisions": [], "projects": {"tabs": []}}
        self.assertEqual(reconcile_inflight(data, self.loaded, now=NOW), 0)
        return data

    def test_opt_in_requires_product_source_and_rendered_views(self):
        """Why: no tab can show a stale page before the product's diagram is rendered."""
        source = self.product()
        self.product(name="unlisted")
        data = self.run_inflight()
        self.assertEqual(data["projects"]["tabs"], [])
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), source.read_bytes())
        self.render("product")
        data = self.run_inflight(data)
        self.assertEqual(data["projects"]["tabs"], [{"id": "product", "diagram": "architecture/product.bower.json"}])
        [e] = json.loads((self.cache / "architecture-sync.json").read_text())["repos"]
        self.assertEqual((e["status"], e["node_count"], e["edge_count"]), ("imported", 3, 1))
        self.assertEqual(e["bower_hash"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse((self.arch / "unlisted.bower.json").exists())

    def test_missing_source_clears_old_tab(self):
        """Why: a cached rich diagram cannot replace missing product documentation."""
        self.arch.joinpath("product.bower.json").write_text(json.dumps(diagram()))
        data = self.run_inflight({"merges": [], "streams": [], "decisions": [], "projects": {
            "tabs": [{"id": "product", "diagram": "architecture/product.bower.json"}]}})
        self.assertEqual(data["projects"]["tabs"], [])
        [e] = json.loads((self.cache / "architecture-sync.json").read_text())["repos"]
        self.assertEqual(e["status"], "missing diagram")

    def test_any_auto_or_thin_diagram_has_no_tab(self):
        """Why: no Architecture tab may ever reference an Auto or thin placeholder."""
        for kind, doc in (("auto", diagram(auto=True)),
                          ("subtitle", dict(diagram(), meta={"subtitle": "Auto stub for product"})),
                          ("thin", diagram(nodes=1))):
            with self.subTest(kind=kind):
                self.product(doc=doc)
                data = self.run_inflight()
                for tab in data["projects"]["tabs"]:
                    chosen = json.loads((self.assets / tab["diagram"]).read_text())
                    self.assertFalse(chosen.get("meta", {}).get("auto") or
                                     "Auto stub" in json.dumps(chosen) or
                                     (len(chosen.get("nodes") or []) <= 1 and not chosen.get("edges")))
                self.assertEqual(data["projects"]["tabs"], [])
                self.assertFalse((self.arch / "product.bower.json").exists())

    def test_richest_wildcard_wins(self):
        """Why: selection follows authored richness rather than file ordering."""
        self.product(file="a.bower.json", doc=diagram(nodes=3))
        source = self.product(file="b.bower.json", doc=diagram(nodes=8))
        self.run_inflight()
        self.assertEqual((self.arch / "product.bower.json").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
