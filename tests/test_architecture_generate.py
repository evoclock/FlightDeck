"""Generated diagrams come from planned work, never from a file inventory."""
import unittest

from flightdeck.architecture_generate import (
    SPARSE_FLAG,
    component_counts,
    diagram_from_planned_work,
    diagram_from_tree,
    is_authored_planned,
    is_inventory_diagram,
    parse_tasks_md,
)


TASKS = """# Board

## Backlog

- [ ] Provision the linux backend `P1` @agent <!-- id: T-0001 -->
  Pin the environment.

## In Progress

- [ ] Ratify the scope baseline `P0` @julen <!-- id: T-0002 -->
  Decision file.

## Done

- [x] Land the collector rewrite `P1` @agent <!-- id: T-0003 -->
  Shipped on main.
"""


class PlannedArchitecture(unittest.TestCase):
    def test_tasks_prs_merges_and_specs_become_components(self):
        sources = {
            "tasks_md": TASKS,
            "docs": [{"path": "contracts/2a-rerun.contract.md", "title": "2a rerun", "summary": "Rerun contract."}],
            "open_prs": [{"number": 51, "title": "Render Stream facts as bullet lists", "head": "fix/streams",
                          "url": "https://github.com/example/app/pull/51"}],
            "merges": [{"number": 50, "title": "Generate architecture maps",
                        "url": "https://github.com/example/app/pull/50"}],
            "readme": "# App\n\nA tool.\n\n## Slot widgets\n\nReusable panes.\n",
            "default_branch": "main",
        }
        result = diagram_from_planned_work("example", "app", "a" * 40, sources)
        self.assertEqual(result, diagram_from_planned_work("example", "app", "a" * 40, sources))
        titles = [node["title"] for node in result["nodes"]]
        self.assertTrue(result["meta"]["generated"])
        self.assertFalse(is_inventory_diagram(result))
        self.assertNotIn("File inventory", titles)
        self.assertTrue(any("linux backend" in title.lower() for title in titles))
        self.assertTrue(any("scope baseline" in title.lower() for title in titles))
        self.assertTrue(any("collector rewrite" in title.lower() for title in titles))
        self.assertTrue(any("2a rerun" in title.lower() for title in titles))
        self.assertTrue(any("Stream facts" in title for title in titles))
        self.assertTrue(any("architecture maps" in title for title in titles))
        # README sections are reserved for thin maps; this source set is already full.
        self.assertFalse(any("Slot widgets" in title for title in titles))
        statuses = {node["title"]: node["status"] for node in result["nodes"]}
        self.assertEqual(statuses[[t for t in titles if "collector rewrite" in t.lower()][0]], "implemented")
        self.assertEqual(statuses[[t for t in titles if "Stream facts" in t][0]], "partial")
        self.assertEqual(statuses[[t for t in titles if "linux backend" in t.lower()][0]], "planned")
        counts = component_counts(result["nodes"])
        self.assertGreaterEqual(counts["total"], 6)
        self.assertGreaterEqual(counts["built"], 2)
        self.assertGreaterEqual(counts["partial"], 1)
        self.assertGreaterEqual(counts["planned"], 2)
        self.assertNotIn(SPARSE_FLAG, result["meta"].get("flags") or [])

    def test_opt_in_readme_components_use_verified_paths(self):
        """Why: a named, tracked implementation counts as built; an absent file cannot become a node."""
        sources = {"include_readme_overview": True,
                   "readme": "# Wholesum\n\nResearch tool.\n\n- `src/analyze_demand_did.py`: Demand comparison.\n- `src/missing.py`: Not built.\n",
                   "paths": ["README.md", "src/analyze_demand_did.py"],
                   "docs": [{"path": "approach.md", "title": "Approach"}]}
        result = diagram_from_planned_work("example", "wholesum", "a" * 40, sources)
        self.assertEqual([node["status"] for node in result["nodes"]],
                         ["implemented", "implemented", "planned"])
        self.assertFalse(any("missing" in node["title"] for node in result["nodes"]))

    def test_dated_operating_note_title_uses_its_source_name_without_date_prefix(self):
        """Why: a dated document heading must fit on a generated diagram card."""
        result = diagram_from_planned_work("example", "notes", "a" * 40, {
            "include_readme_overview": True, "readme": "# Notes\n\nOperating notes.\n",
            "docs": [{"path": "team/2026-11-09-operating-notes.md",
                      "title": "2026 11 09 operating notes"}],
        })
        self.assertIn("operating notes", [node["title"] for node in result["nodes"]])

    def test_empty_sources_make_a_minimal_component_not_an_inventory(self):
        result = diagram_from_planned_work("example", "empty", None, {})
        self.assertEqual([node["title"] for node in result["nodes"]], ["empty"])
        self.assertEqual(result["nodes"][0]["status"], "planned")
        self.assertIn(SPARSE_FLAG, result["meta"]["flags"])
        self.assertFalse(is_inventory_diagram(result))
        self.assertNotEqual(result["nodes"][0]["id"], "inventory")
        self.assertNotIn("File inventory", result["nodes"][0]["title"])
        self.assertIn("No TASKS.md cards", result["nodes"][0]["details"])

    def test_readme_only_avoids_file_inventory(self):
        result = diagram_from_planned_work("example", "service", "b" * 40, {
            "readme": "# Service\n\nDoes work.\n\n## Parser\n\nReads input.\n\n## License\n\nMIT.\n",
        })
        titles = [node["title"] for node in result["nodes"]]
        self.assertIn("Parser", titles)
        self.assertNotIn("License", titles)
        self.assertFalse(is_inventory_diagram(result))
        self.assertNotIn("File inventory", " ".join(titles))

    def test_readme_fills_a_thin_map_and_skips_install_headings(self):
        result = diagram_from_planned_work("example", "tool", "c" * 40, {
            "merges": [{"number": 1, "title": "Land the parser", "url": "https://x/1"}],
            "readme": "# Tool\n\n## Parser core\n\nDoes work.\n\n## Installation & Setup\n\nClone repository.\n\n## License\n\nMIT.\n",
        })
        titles = [node["title"] for node in result["nodes"]]
        self.assertIn("Land the parser", titles)
        self.assertIn("Parser core", titles)
        self.assertNotIn("Installation & Setup", titles)
        self.assertNotIn("License", titles)

    def test_long_spec_paths_keep_unique_ids(self):
        sources = {"docs": [
            {"path": "build-proofs/billing-handlers/docs/plans/checkout-split.md", "title": "checkout split"},
            {"path": "build-proofs/billing-handlers/docs/plans/search-v2.md", "title": "search v2"},
        ]}
        result = diagram_from_planned_work("example", "bench", "d" * 40, sources)
        ids = [node["id"] for node in result["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(any(a["from"] == a["to"] for a in result["edges"]))

    def test_tree_helper_is_removed(self):
        with self.assertRaises(RuntimeError):
            diagram_from_tree("example", "service", "a" * 40, ["src/main.py"])

    def test_authored_planned_maps_are_left_alone(self):
        authored = {"schema": "bowerbird/v1", "meta": {"title": "aim-2"}, "nodes": [{"id": "coord", "title": "Coordination repo"}]}
        generated = diagram_from_planned_work("example", "empty", None, {})
        inventory = {"schema": "bowerbird/v1", "meta": {"generated": True, "subtitle": "Generated from repository tree"},
                     "nodes": [{"id": "repo", "title": "repo"}, {"id": "inventory", "title": "File inventory"}]}
        stub = {"schema": "bowerbird/v1", "meta": {"subtitle": "Auto stub for x. Replace when the shape is known."},
                "nodes": [{"id": "repo", "title": "x", "status": "partial"}]}
        self.assertTrue(is_authored_planned(authored))
        self.assertFalse(is_authored_planned(generated))
        self.assertFalse(is_authored_planned(inventory))
        self.assertFalse(is_authored_planned(stub))
        self.assertTrue(is_inventory_diagram(inventory))

    def test_parse_tasks_md_reads_vogelkop_cards(self):
        cards = parse_tasks_md(TASKS)
        self.assertEqual([card["id"] for card in cards], ["T-0003", "T-0002", "T-0001"])
        self.assertTrue(cards[0]["done"])
        self.assertFalse(cards[1]["done"])


if __name__ == "__main__":
    unittest.main()
