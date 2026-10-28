"""camelCase repos cache rows must still count as in-flight (mirrors flock-master #29)."""
from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flightdeck import sync
from flightdeck.sync import norm_repo, reconcile_inflight, refresh_caches
from tests.test_sync import cfg, write

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 28, 18, 0, tzinfo=UTC)


class InflightCacheFields(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.loaded = cfg(
            self.tmp,
            owner="evoclock",
            primary_stream={"agent": "lead", "area": "Board", "label": "Lead"},
        )
        self.cache = Path(self.loaded["cache_dir"])

    def tearDown(self):
        self.dir.cleanup()

    def test_norm_repo_reads_camel_case(self):
        row = norm_repo({
            "name": "etwin-ces",
            "nameWithOwner": "evoclock/etwin-ces",
            "pushedAt": "2026-10-28T12:40:00Z",
            "createdAt": "2026-10-28T12:40:00Z",
            "isPrivate": True,
            "url": "https://github.com/evoclock/etwin-ces",
        })
        self.assertEqual(row["full_name"], "evoclock/etwin-ces")
        self.assertEqual(row["pushed_at"], "2026-10-28T12:40:00Z")
        self.assertTrue(row["private"])

    def test_camelcase_only_repos_cache_marks_inflight(self):
        write(self.cache / "prs.json", {"complete": True, "prs": []})
        write(self.cache / "repos.json", {"complete": True, "repos": [{
            "name": "etwin-ces",
            "nameWithOwner": "evoclock/etwin-ces",
            "pushedAt": "2026-10-28T12:40:00Z",
            "createdAt": "2026-10-28T12:40:00Z",
            "isPrivate": True,
            "url": "https://github.com/evoclock/etwin-ces",
        }]})
        data = {"merges": [], "streams": [], "decisions": [], "projects": {"tabs": []}}
        self.assertEqual(reconcile_inflight(data, self.loaded, now=NOW), 0)
        titles = [m.get("title") for m in data["merges"]]
        self.assertTrue(
            any("etwin-ces" in (t or "") and "active on main" in (t or "") for t in titles),
            titles,
        )

    def test_refresh_keeps_repos_when_fresh_list_empty(self):
        write(self.cache / "repos.json", {"complete": True, "repos": [{
            "name": "etwin-ces",
            "full_name": "evoclock/etwin-ces",
            "pushed_at": "2026-10-28T12:40:00Z",
            "created_at": "2026-10-28T12:40:00Z",
            "private": True,
            "url": "https://github.com/evoclock/etwin-ces",
        }]})
        with mock.patch.object(sync, "fetch_all", return_value={
            "prs": [], "closed": [], "repos": [], "releases": [], "complete": True, "since": "2026-10-01",
        }):
            self.assertEqual(refresh_caches(self.loaded, now=NOW), 0)
        kept = json.loads((self.cache / "repos.json").read_text())["repos"]
        self.assertEqual(kept[0]["full_name"], "evoclock/etwin-ces")
        self.assertTrue(kept[0]["private"])


if __name__ == "__main__":
    unittest.main()
