"""Settled rows and settled Decision cards keep at most one day."""
import datetime
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flightdeck.sync import add_settled, load_config, prune_settled, reconcile_merges_lifecycle, reconcile_responses

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 26, 22, 55, tzinfo=UTC)


class SettledPrune(unittest.TestCase):
    def test_add_settled_carries_at(self):
        data = {"settled": []}
        add_settled(data, "T", "- x", NOW, "dec-1", "2026-10-26T22:00:00Z")
        self.assertEqual(data["settled"][0]["at"], "2026-10-26T22:00:00.000Z")
        self.assertEqual(data["settled"][0]["src_id"], "dec-1")

    def test_add_settled_defaults_at_to_now(self):
        data = {}
        add_settled(data, "T", "- x", NOW, "dec-1")
        self.assertEqual(data["settled"][0]["at"], "2026-10-26T22:55:00.000Z")

    def test_prune_drops_old_settled_and_cards(self):
        data = {
            "settled": [
                {"meta": "old", "title": "Old", "detail": "- o", "src_id": "dec-old", "at": "2026-10-20T12:00:00Z"},
                {"meta": "new", "title": "New", "detail": "- n", "src_id": "dec-new", "at": "2026-10-26T20:00:00Z"},
                {"meta": "undated", "title": "U", "detail": "- u", "src_id": "mystery"},
            ],
            "decisions": [
                {"id": "dec-old", "state": "settled", "title": "Old", "settled_at": "2026-10-20T12:00:00Z"},
                {"id": "dec-new", "state": "settled", "title": "New", "settled_at": "2026-10-26T20:00:00Z"},
                {"id": "dec-row", "state": "settled", "title": "Row only"},
                {"id": "dec-open", "state": "open", "title": "Open"},
            ],
        }
        data["settled"].append({"meta": "r", "title": "Row", "detail": "- r", "src_id": "dec-row",
                                "at": "2026-10-26T21:00:00Z"})
        notes = prune_settled(data, [], NOW)
        self.assertEqual([s["title"] for s in data["settled"]], ["New", "Row"])
        self.assertEqual({x["id"] for x in data["decisions"]}, {"dec-new", "dec-row", "dec-open"})
        self.assertTrue(any("pruned" in n for n in notes))

    def test_prune_resolves_undated_merge_row_from_closed_cache(self):
        row = {"meta": "10:00", "title": "Merged x", "detail": "- m", "src_id": "merged:acme/app#1"}
        fresh = [{"repo": "acme/app", "number": 1, "merged_at": "2026-10-26T10:00:00Z", "merged": True}]
        data = {"settled": [dict(row)]}
        prune_settled(data, fresh, NOW)
        self.assertEqual(len(data["settled"]), 1)
        stale = [{"repo": "acme/app", "number": 1, "closed_at": "2026-10-20T10:00:00Z", "merged": True}]
        data = {"settled": [dict(row)]}
        prune_settled(data, stale, NOW)
        self.assertEqual(data["settled"], [])

    def test_prune_is_a_noop_on_fresh_data(self):
        data = {"settled": [{"title": "N", "src_id": "dec-1", "at": "2026-10-26T22:00:00Z"}], "decisions": []}
        self.assertEqual(prune_settled(data, None, NOW), [])


class HooksPrune(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["FLIGHTDECK_CACHE"] = str(Path(self._tmp.name) / "cache")
        os.environ.pop("CLOUDFLARE_API_TOKEN", None)
        conf = Path(self._tmp.name) / "sync.json"
        conf.write_text("{}")
        self.cfg = load_config(str(conf))
        self.cache = Path(self.cfg["cache_dir"])
        self.cache.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        os.environ.pop("FLIGHTDECK_CACHE", None)
        self._tmp.cleanup()

    def test_responses_hook_prunes_without_a_responses_store(self):
        data = {"settled": [{"title": "Old", "src_id": "dec-1", "at": "2026-10-20T12:00:00Z"}], "decisions": []}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(reconcile_responses(data, self.cfg, now=NOW), 0)
        self.assertEqual(data["settled"], [])

    def test_responses_hook_stamps_answer_time(self):
        (self.cache / "responses.json").write_text(json.dumps({"responses": [
            {"id": "dec-1", "type": "decision", "value": "accepted", "timestamp": "2026-10-26T21:30:00Z"}]}))
        data = {"decisions": [{"id": "dec-1", "state": "open", "title": "Adopt?"}], "settled": []}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            reconcile_responses(data, self.cfg, now=NOW)
        self.assertEqual(data["decisions"][0]["settled_at"], "2026-10-26T21:30:00.000Z")
        self.assertEqual(data["settled"][0]["at"], "2026-10-26T21:30:00.000Z")

    def test_lifecycle_hook_drops_old_merge(self):
        (self.cache / "prs-closed.json").write_text(json.dumps({"prs": [
            {"number": 7, "title": "Old", "repo": "acme/app", "merged": True, "merged_at": "2026-10-20T10:00:00Z"},
            {"number": 8, "title": "New", "repo": "acme/app", "merged": True, "merged_at": "2026-10-26T20:00:00Z"}]}))
        data = {"merges": [], "decisions": [], "settled": []}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            reconcile_merges_lifecycle(data, self.cfg, now=NOW)
        self.assertEqual([r["src_id"] for r in data["settled"]], ["merged:acme/app#8"])

    def test_architecture_review_settles_only_after_observed_merge(self):
        """Why: closing a review without merging must not claim Architecture was delivered."""
        cache = self.cache / "prs-closed.json"
        pr = {"number": 9, "title": "Architecture diagrams", "repo": "acme/FlightDeck",
              "closed_at": "2026-10-26T22:50:00Z", "url": "https://github.com/acme/FlightDeck/pull/9"}
        cache.write_text(json.dumps({"prs": [pr]}))
        data = {"merges": [{"title": "Architecture diagrams", "repo": "acme/FlightDeck", "number": 9}],
                "steps": [], "decisions": [], "settled": []}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(reconcile_merges_lifecycle(data, self.cfg, now=NOW), 0)
        self.assertEqual(data["settled"], [])
        pr.update(merged=True, merged_at="2026-10-26T22:51:00Z")
        cache.write_text(json.dumps({"prs": [pr]}))
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(reconcile_merges_lifecycle(data, self.cfg, now=NOW), 0)
        self.assertEqual([r["src_id"] for r in data["settled"]], ["merged:acme/FlightDeck#9"])

    def test_merge_settled_card_is_dated_and_kept_for_its_day(self):
        """A card settled by a merge keeps settled_at, so the same-run prune does not drop it."""
        (self.cache / "prs-closed.json").write_text(json.dumps({"prs": [
            {"number": 21, "title": "Keep Settled", "repo": "acme/app", "merged": True,
             "merged_at": "2026-10-26T22:50:00Z", "url": "https://github.com/acme/app/pull/21"}]}))
        card = {"id": "dec-ready", "state": "open", "title": "Merge ready PRs",
                "text": "- [acme/app #21](https://github.com/acme/app/pull/21)", "opened_at": "2026-10-20T10:00:00Z"}
        data = {"merges": [], "steps": [], "settled": [], "decisions": [card]}
        with mock.patch("sys.stderr", io.StringIO()), mock.patch("sys.stdout", io.StringIO()):
            reconcile_merges_lifecycle(data, self.cfg, now=NOW)
        self.assertEqual([(x["id"], x["state"], x["settled_at"]) for x in data["decisions"]],
                         [("dec-ready", "settled", "2026-10-26T22:50:00.000Z")])
        self.assertIn("merged-dec:acme/app#21", [r["src_id"] for r in data["settled"]])
        later = NOW + datetime.timedelta(hours=23)
        self.assertEqual(prune_settled(data, None, later), [])
        self.assertEqual(len(data["decisions"]), 1)
        prune_settled(data, None, NOW + datetime.timedelta(hours=25))
        self.assertEqual(data["decisions"], [])


if __name__ == "__main__":
    unittest.main()
