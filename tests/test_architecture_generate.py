"""Generated diagrams report observed files without inventing runtime links."""
import unittest

from flightdeck.architecture_generate import diagram_from_tree


class GeneratedArchitecture(unittest.TestCase):
    def test_observed_groups_and_stable_output(self):
        paths = [".github/workflows/check.yml", "src/main.py", "pyproject.toml", "tests/test_main.py"]
        result = diagram_from_tree("example", "service", "a" * 40, paths)
        self.assertEqual(result, diagram_from_tree("example", "service", "a" * 40, list(reversed(paths))))
        self.assertTrue(result["meta"]["generated"])
        self.assertEqual({n["id"] for n in result["nodes"]}, {"repo", "packages", "entry", "ci", "tests"})
        self.assertEqual({e["to"] for e in result["edges"]}, {"packages", "entry", "ci", "tests"})
        self.assertTrue(all("hint" not in n for n in result["nodes"]))

    def test_unavailable_tree_is_not_reported_as_empty(self):
        result = diagram_from_tree("example", "private", None, None)
        self.assertEqual(result["nodes"][1]["lines"], ["Inventory unknown"])

    def test_empty_tree_has_honest_inventory(self):
        result = diagram_from_tree("example", "empty", None, [])
        self.assertEqual([n["id"] for n in result["nodes"]], ["repo", "inventory"])
        self.assertIn("0 paths", result["nodes"][1]["lines"])
