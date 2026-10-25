import datetime
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from collectors import activity, metrics_generic

UTC = datetime.timezone.utc


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_returning(counts):
    """Fake urlopen: answers by query content, records requests."""
    calls = []

    def op(req, timeout=None):
        calls.append(req)
        url = req.full_url
        n = counts["commits"] if "/search/commits" in url else counts["merged"] if "is%3Amerged" in url else counts["opened"]
        return FakeResp(json.dumps({"total_count": n}).encode())
    op.calls = calls
    return op


def failing_opener(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data.json"
        self.data.write_text(json.dumps({"streams": [1]}))
        self.now = datetime.datetime(2026, 10, 25, 1, 0, tzinfo=UTC)  # Sunday

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, env, opener=None):
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                return activity.main(["--data", str(self.data)], now=self.now,
                                     opener=opener or failing_opener)

    def test_queries_scope_owner_and_since(self):
        q = activity.queries("acme", datetime.datetime(2026, 10, 23, 16, 0, tzinfo=UTC))
        self.assertEqual(q["commits"], ("commits", "user:acme committer-date:>=2026-10-23T16:00:00Z"))
        self.assertIn("is:merged merged:>=2026-10-23T16:00:00Z", q["prs_merged"][1])
        self.assertIn("is:pr created:>=", q["prs_opened"][1])

    def test_no_owner_skips_and_leaves_data_untouched(self):
        before = self.data.read_text()
        self.assertEqual(self.run_main({"GITHUB_TOKEN": "t"}), 0)
        self.assertEqual(self.data.read_text(), before)

    def test_success_writes_both_windows(self):
        op = opener_returning({"commits": 7, "opened": 2, "merged": 1})
        self.assertEqual(self.run_main({"FLIGHTDECK_GH_OWNER": "acme", "GITHUB_TOKEN": "tok"}, op), 0)
        d = json.loads(self.data.read_text())
        self.assertEqual(d["streams"], [1])
        for key, window in (("activity", "1h"), ("activity_weekly", "week")):
            sec = d[key]
            self.assertEqual(sec["window"], window)
            self.assertEqual((sec["commits"], sec["prs_opened"], sec["prs_merged"]), (7, 2, 1))
            self.assertTrue(sec["at"])
            self.assertIn("acme", sec["note"])
        # Friday 23 Oct 2026 17:00 London (BST) is 16:00 UTC
        self.assertEqual(datetime.datetime.fromisoformat(d["activity_weekly"]["since"]).astimezone(UTC),
                         datetime.datetime(2026, 10, 23, 16, 0, tzinfo=UTC))
        self.assertEqual(len(op.calls), 6)
        self.assertEqual(op.calls[0].get_header("Authorization"), "Bearer tok")
        self.assertFalse(list(Path(self.tmp.name).glob("*.tmp")))

    def test_pat_is_accepted_as_a_token(self):
        op = opener_returning({"commits": 1, "opened": 0, "merged": 0})
        self.assertEqual(self.run_main({"FLIGHTDECK_GH_OWNER": "acme", "GITHUB_PAT": "pat"}, op), 0)
        self.assertEqual(op.calls[0].get_header("Authorization"), "Bearer pat")

    def test_no_token_fills_zeros_with_note(self):
        self.assertEqual(self.run_main({"FLIGHTDECK_GH_OWNER": "acme"}), 0)
        d = json.loads(self.data.read_text())
        self.assertEqual(d["activity"]["commits"], 0)
        self.assertIsNone(d["activity"]["at"])
        self.assertIn("GITHUB_TOKEN", d["activity"]["note"])
        self.assertIn("since", d["activity_weekly"])

    def test_http_failure_keeps_collected_numbers_and_exits_2(self):
        old = {"window": "1h", "commits": 4, "prs_opened": 0, "prs_merged": 0, "at": "2026-10-25T00:00:00+01:00"}
        self.data.write_text(json.dumps({"activity": old}))
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(self.run_main({"FLIGHTDECK_GH_OWNER": "acme", "GH_TOKEN": "t"}), 2)
        d = json.loads(self.data.read_text())
        self.assertEqual(d["activity"], old)
        self.assertIn("401", d["activity_weekly"]["note"])


MEMINFO = "MemTotal:       16777216 kB\nMemFree:  1000000 kB\nMemAvailable:    6291456 kB\n"  # 16 GiB, 6 GiB free


class MetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "data.json"
        self.data.write_text(json.dumps({"streams": []}))

    def tearDown(self):
        self.tmp.cleanup()

    def proc(self):
        p = self.root / "proc"
        p.mkdir()
        (p / "meminfo").write_text(MEMINFO)
        return p

    def test_cpu_pct_from_two_samples(self):
        a = (100, 0, 100, 800, 0, 0, 0, 0)   # busy 200 / total 1000
        b = (150, 0, 150, 1100, 0, 0, 0, 0)  # +100 busy over +400 total
        self.assertAlmostEqual(metrics_generic.cpu_pct(a, b), 25.0)
        self.assertIsNone(metrics_generic.cpu_pct(a, a))

    def test_mem_from_meminfo(self):
        pct, detail = metrics_generic.mem(self.proc())
        self.assertAlmostEqual(pct, 62.5)
        self.assertEqual(detail, "10.0 / 16 GB")

    def test_collect_linux_like(self):
        p = self.proc()
        samples = iter([(100, 0, 100, 800), (150, 0, 150, 1100)])
        with mock.patch.object(metrics_generic, "cpu_sample", lambda root: next(samples)):
            m = metrics_generic.collect(proc=p, disk_path=str(self.root), interval=0)
        items = {i["key"]: i for i in m["items"]}
        self.assertEqual(set(items), {"cpu", "mem", "disk"})
        self.assertAlmostEqual(items["cpu"]["pct"], 25.0)
        self.assertAlmostEqual(items["mem"]["pct"], 62.5)
        self.assertIsNotNone(items["disk"]["pct"])
        self.assertTrue(m["at"])
        self.assertNotIn("note", m)

    def test_unsupported_host_writes_null_pct_and_note(self):
        m = metrics_generic.collect(proc=self.root / "missing", disk_path=str(self.root / "missing"), interval=0)
        self.assertEqual(len(m["items"]), 3)
        for i in m["items"]:
            self.assertIsNone(i["pct"])
        self.assertIn("not supported", m["note"])

    def test_main_writes_metrics_and_keeps_other_keys(self):
        with mock.patch.object(metrics_generic, "collect", return_value={"items": [{"key": "cpu", "label": "CPU", "pct": 1.0}]}):
            with mock.patch("sys.stdout", io.StringIO()):
                self.assertEqual(metrics_generic.main(["--data", str(self.data)]), 0)
        d = json.loads(self.data.read_text())
        self.assertEqual(d["streams"], [])
        self.assertEqual(d["metrics"]["items"][0]["pct"], 1.0)


if __name__ == "__main__":
    unittest.main()
