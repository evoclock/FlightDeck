"""Sync hooks reconcile data.json from caches and skip when the demo has no owner."""
import datetime
import io
import json
import os
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from flightdeck.sync import (
    apply_bot_reports,
    apply_responses,
    check_evidence,
    load_config,
    main_record_chat_accept,
    record_chat_accept,
    pin_ids,
    reconcile_inflight,
    reconcile_merges_lifecycle,
    reconcile_priorities,
    reconcile_ready_decisions,
    reconcile_responses,
    reconcile_steps_evidence,
    refresh_caches,
)
from flightdeck.widgets.architecture import load_diagram
from collectors import spark

ROOT = Path(__file__).resolve().parent.parent
UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def cfg(tmp, **extra):
    os.environ["FLIGHTDECK_CACHE"] = str(Path(tmp) / "cache")
    os.environ.pop("FLIGHTDECK_GH_OWNER", None)
    os.environ.pop("FLIGHTDECK_PUBLIC_REPOS", None)
    os.environ.pop("FLIGHTDECK_STREAM_LABEL", None)
    os.environ.pop("FLIGHTDECK_PRIMARY_AGENT", None)
    os.environ.pop("FLIGHTDECK_PRIMARY_AREA", None)
    os.environ.pop("FLIGHTDECK_DATA", None)
    os.environ.pop("CLOUDFLARE_API_TOKEN", None)
    base = load_config()
    base["cache_dir"] = str(Path(tmp) / "cache")
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key].update(value)
        else:
            base[key] = value
    return base


def write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class ConfigTests(unittest.TestCase):
    def test_example_matches_defaults_and_env_overrides(self):
        example = json.loads((ROOT / "config" / "sync.example.json").read_text())
        for key in ("owner", "public_repos", "primary_stream", "responses", "guards", "omb", "assets_dir"):
            self.assertIn(key, example)
        self.assertEqual(example["owner"], "")
        self.assertEqual(example["public_repos"], [])
        with mock.patch.dict(os.environ, {
            "FLIGHTDECK_GH_OWNER": "acme",
            "FLIGHTDECK_PUBLIC_REPOS": "app, lib",
            "FLIGHTDECK_STREAM_LABEL": "Lead",
            "FLIGHTDECK_RESPONSES_KV_ID": "ns",
            "FLIGHTDECK_RESPONSES_KEY": "responses/you@example.com",
        }, clear=False):
            loaded = load_config()
        self.assertEqual(loaded["owner"], "acme")
        self.assertEqual(loaded["public_repos"], ["app", "lib"])
        self.assertEqual(loaded["primary_stream"]["label"], "Lead")
        self.assertEqual(loaded["responses"]["kv_namespace_id"], "ns")
        self.assertEqual(loaded["responses"]["key"], "responses/you@example.com")


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.id().replace(".", "_"))
        # use a real temp dir
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_no_owner_skips(self):
        env = {k: v for k, v in os.environ.items() if k != "FLIGHTDECK_GH_OWNER"}
        proc = subprocess.run(
            ["python3", str(ROOT / "scripts" / "refresh_pr_cache.py")],
            cwd=self.tmp, env=env, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("skipping", proc.stderr)
        self.assertFalse((self.tmp / ".cache").exists())

    def test_public_repos_without_token_are_incomplete(self):
        seen = []

        def opener(req, timeout=None):
            url = req.full_url
            seen.append(url)
            if url.endswith("/repos/acme/app"):
                body = {"name": "app", "full_name": "acme/app", "pushed_at": "2026-10-25T00:00:00Z",
                        "created_at": "2026-01-01T00:00:00Z", "private": False, "html_url": "https://github.com/acme/app"}
            elif "/pulls?state=open" in url:
                body = [{"number": 2, "title": "Add", "html_url": "https://github.com/acme/app/pull/2",
                         "draft": False, "state": "open", "user": {"login": "ada"}}]
            elif url.endswith("/pulls/2"):
                body = {"number": 2, "title": "Add", "html_url": "https://github.com/acme/app/pull/2",
                        "draft": False, "state": "open", "user": {"login": "ada"},
                        "mergeable_state": "clean", "head": {"sha": "abc"}}
            elif url.endswith("/commits/abc/status"):
                body = {"state": "success"}
            elif "state=closed" in url:
                body = []
            else:
                raise AssertionError(url)
            return FakeResp(json.dumps(body).encode())

        loaded = cfg(self.tmp, owner="acme", public_repos=["app"])
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "", "GH_TOKEN": "", "GITHUB_PAT": ""}, clear=False):
            code = refresh_caches(loaded, opener=opener, now=NOW)
        self.assertEqual(code, 2)
        prs = json.loads((Path(loaded["cache_dir"]) / "prs.json").read_text())
        self.assertFalse(prs["complete"])
        self.assertEqual(prs["prs"][0]["checks"], "success")
        self.assertEqual(prs["prs"][0]["merge_state"], "CLEAN")
        self.assertEqual(prs["prs"][0]["author"], "ada")
        self.assertTrue((Path(loaded["cache_dir"]) / "repos.json").is_file())
        self.assertFalse(any("api.github.com/user" in url for url in seen))

    def test_gh_runner_marks_ready(self):
        def runner(args):
            if args[:3] == ["search", "prs", "--author"] and args[args.index("--state") + 1] == "open":
                return [{"number": 1, "title": "T", "url": "https://github.com/acme/app/pull/1",
                         "repository": {"nameWithOwner": "acme/app"}, "isDraft": False, "state": "open"}]
            if args[0] == "pr":
                return {"mergeStateStatus": "CLEAN", "statusCheckRollup": [{"conclusion": "SUCCESS"}],
                        "isDraft": False, "title": "T", "number": 1, "url": "https://github.com/acme/app/pull/1",
                        "state": "OPEN"}
            if args[0] == "search":
                return []
            if args[0] == "repo":
                return [{"name": "app", "nameWithOwner": "acme/app", "pushedAt": "2026-01-01T00:00:00Z",
                         "createdAt": "2026-01-01T00:00:00Z", "isPrivate": False, "url": ""}]
            raise AssertionError(args)

        loaded = cfg(self.tmp, owner="acme")
        self.assertEqual(refresh_caches(loaded, runner=runner, now=NOW), 0)
        prs = json.loads((Path(loaded["cache_dir"]) / "prs.json").read_text())
        self.assertTrue(prs["complete"])
        self.assertEqual(prs["prs"][0]["checks"], "success")
        self.assertEqual(prs["prs"][0]["state"], "open")


class InflightTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)
        self.loaded = cfg(
            self.tmp,
            owner="acme",
            public_repos=["app"],
            primary_stream={"agent": "lead", "area": "Board", "label": "Lead"},
            assets_dir=str(self.tmp / "assets"),
        )
        cache = Path(self.loaded["cache_dir"])
        write(cache / "prs.json", {"complete": True, "prs": [{
            "number": 7, "title": "Add settings", "repo": "acme/app", "author": "ada",
            "url": "https://github.com/acme/app/pull/7", "draft": False, "state": "open",
            "merge_state": "CLEAN", "checks": "success",
        }]})
        write(cache / "repos.json", {"complete": True, "repos": [
            {"name": "app", "full_name": "acme/app", "pushed_at": "2026-10-25T00:00:00Z", "created_at": "2026-01-01T00:00:00Z"},
            {"name": "lib", "full_name": "acme/lib", "pushed_at": "2026-10-25T00:00:00Z", "created_at": "2026-01-01T00:00:00Z"},
            {"name": "new", "full_name": "acme/new", "pushed_at": "2026-10-25T11:00:00Z", "created_at": "2026-10-25T10:00:00Z"},
            {"name": "old", "full_name": "acme/old", "pushed_at": "2020-01-01T00:00:00Z", "created_at": "2020-01-01T00:00:00Z"},
        ]})

    def tearDown(self):
        self.dir.cleanup()

    def test_open_pr_synthetic_row_and_short_stream(self):
        data = {"streams": [{"bot": "Other", "project": "Elsewhere", "now": "Reading", "waiting": "Nothing"}], "merges": []}
        self.assertEqual(reconcile_inflight(data, self.loaded, now=NOW), 0)
        titles = [row["title"] for row in data["merges"]]
        self.assertEqual(titles.count("Add settings"), 1)
        self.assertIn("lib · active on main", titles)
        self.assertIn("new · active on main", titles)
        self.assertNotIn("old · active on main", titles)
        self.assertEqual(data["merges"][0]["state"], "Ready to merge")
        self.assertEqual(data["merges"][0]["bot"], "ada")
        lead = next(row for row in data["streams"] if row["bot"] == "Lead")
        self.assertNotIn("acme/lib", lead["now"])
        self.assertNotIn(",", lead["now"])
        self.assertIn("open PR", lead["now"])
        self.assertIn("active on main", lead["now"])
        self.assertEqual(lead["waiting"], "1 ready to merge.")
        self.assertEqual(data["streams"][0]["bot"], "Other")
        opened = [d for d in data["decisions"] if d["state"] == "open"]
        self.assertEqual(len(opened), 1)
        self.assertIn("acme/new", opened[0]["text"])
        self.assertTrue(opened[0]["text"].startswith("- "))
        again = json.loads(json.dumps(data))
        reconcile_inflight(again, self.loaded, now=NOW)
        self.assertEqual(len([d for d in again["decisions"] if "acme/new" in d["text"]]), 1)
        # No rich authored diagram for acme/new → no Architecture stub tab.
        self.assertFalse(any(t.get("id") == "new" for t in data.get("projects", {}).get("tabs") or []))
        self.assertEqual(data["projects"]["pending"], [])

    def test_missing_cache_does_not_wipe(self):
        empty = cfg(self.tmp / "empty", owner="acme")
        data = {"merges": [{"title": "Keep", "repo": "acme/app", "bot": "ada", "state": "In progress"}]}
        self.assertEqual(reconcile_inflight(data, empty, now=NOW), 2)
        self.assertEqual(data["merges"][0]["title"], "Keep")

    def test_offline_skips(self):
        offline = cfg(self.tmp / "off")
        offline["owner"] = ""
        data = {"merges": [{"title": "Keep"}]}
        self.assertEqual(reconcile_inflight(data, offline, now=NOW), 0)
        self.assertEqual(data["merges"], [{"title": "Keep"}])


class PaneTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_lifecycle_drops_row_ticks_step_and_settles(self):
        loaded = cfg(self.tmp)
        write(Path(loaded["cache_dir"]) / "prs-closed.json", {"prs": [{
            "number": 7, "title": "Add settings", "repo": "acme/app",
            "url": "https://github.com/acme/app/pull/7", "merged": True, "state": "closed",
        }]})
        data = {
            "merges": [{"title": "Add settings", "repo": "acme/app", "bot": "ada", "state": "Ready to merge", "number": 7}],
            "steps": [{"text": "Merge acme/app#7", "pr": "acme/app#7", "done": False}],
            "decisions": [{"state": "open", "title": "Merge it?", "text": "- See https://github.com/acme/app/pull/7"}],
            "settled": [],
        }
        self.assertEqual(reconcile_merges_lifecycle(data, loaded, now=NOW), 0)
        self.assertEqual(data["merges"], [])
        self.assertTrue(data["steps"][0]["done"])
        self.assertEqual(data["decisions"][0]["state"], "settled")
        self.assertIn("acme/app#7 merged.", data["settled"][0]["detail"])

    def test_ready_decision_respects_public_repos(self):
        loaded = cfg(self.tmp, public_repos=[])  # evidence from repos.json, not config list
        write(Path(loaded["cache_dir"]) / "repos.json", {"complete": True, "repos": [
            {"name": "app", "full_name": "acme/app", "private": False, "pushed_at": "2026-10-25T10:00:00Z",
             "created_at": "2020-01-01T00:00:00Z", "url": "https://github.com/acme/app"},
            {"name": "lib", "full_name": "acme/lib", "private": True, "pushed_at": "2026-10-25T10:00:00Z",
             "created_at": "2020-01-01T00:00:00Z", "url": "https://github.com/acme/lib"},
        ]})
        data = {"merges": [
            {"title": "Add", "repo": "acme/app", "state": "Ready to merge", "number": 7, "url": "https://github.com/acme/app/pull/7"},
            {"title": "Other", "repo": "acme/lib", "state": "Ready to merge", "number": 3, "url": "https://github.com/acme/lib/pull/3"},
            {"title": "Draft", "repo": "acme/app", "state": "Draft", "number": 8},
        ], "decisions": []}
        self.assertEqual(reconcile_ready_decisions(data, loaded), 0)
        self.assertEqual(len(data["decisions"]), 1)
        self.assertIn("acme/app#7", data["decisions"][0]["text"])
        self.assertNotIn("acme/lib", data["decisions"][0]["text"])
        self.assertTrue(data["decisions"][0]["text"].startswith("- "))

    def test_ready_decisions_open_accept_for_green_drafts(self):
        loaded = cfg(self.tmp, public_repos=[])
        write(Path(loaded["cache_dir"]) / "repos.json", {"complete": True, "repos": [
            {"name": "app", "full_name": "acme/app", "private": False, "pushed_at": "2026-10-25T10:00:00Z",
             "created_at": "2020-01-01T00:00:00Z", "url": "https://github.com/acme/app"},
        ]})
        write(Path(loaded["cache_dir"]) / "prs.json", {"complete": True, "prs": [
            {"number": 26, "title": "Sync", "repo": "acme/app", "url": "https://github.com/acme/app/pull/26",
             "draft": True, "state": "open", "merge_state": "BLOCKED", "checks": "success"},
            {"number": 27, "title": "WIP", "repo": "acme/app", "url": "https://github.com/acme/app/pull/27",
             "draft": True, "state": "open", "merge_state": "BLOCKED", "checks": "pending"},
        ]})
        data = {"merges": [
            {"title": "Sync", "repo": "acme/app", "state": "Draft, checks green", "number": 26,
             "url": "https://github.com/acme/app/pull/26"},
            {"title": "WIP", "repo": "acme/app", "state": "Draft", "number": 27,
             "url": "https://github.com/acme/app/pull/27"},
        ], "decisions": []}
        self.assertEqual(reconcile_ready_decisions(data, loaded), 0)
        self.assertEqual(len(data["decisions"]), 1)
        self.assertIn("Accept draft", data["decisions"][0]["title"])
        self.assertIn("acme/app#26", data["decisions"][0]["text"])
        self.assertNotIn("acme/app#27", data["decisions"][0]["text"])

    def test_architecture_reviews_do_not_open_chat_merge_or_undraft_asks(self):
        """Why: architecture reviews belong to the reviewer's GitHub merge path, not chat Accept."""
        loaded = cfg(self.tmp)
        cache = Path(loaded["cache_dir"])
        write(cache / "repos.json", {"repos": [
            {"name": name, "full_name": f"acme/{name}", "private": False}
            for name in ("FlightDeck", "flock-master", "app")
        ]})
        write(cache / "prs.json", {"prs": [
            {"number": 6, "repo": "acme/FlightDeck", "draft": True, "checks": "success"},
        ]})
        data = {"merges": [
            {"title": "Architecture diagrams", "repo": "acme/FlightDeck", "state": "Draft, checks green", "number": 6,
             "url": "https://github.com/acme/FlightDeck/pull/6"},
            {"title": "Review Bowerbird layout", "repo": "acme/flock-master", "state": "Ready to merge", "number": 7,
             "url": "https://github.com/acme/flock-master/pull/7"},
            {"title": "Repair panel", "repo": "acme/FlightDeck", "state": "Ready to merge", "number": 8,
             "url": "https://github.com/acme/FlightDeck/pull/8"},
            {"title": "Architecture for app", "repo": "acme/app", "state": "Ready to merge", "number": 9,
             "url": "https://github.com/acme/app/pull/9"},
        ], "decisions": []}
        self.assertEqual(reconcile_ready_decisions(data, loaded), 0)
        titles = [d["title"] for d in data["decisions"]]
        self.assertEqual(len(titles), 2)
        self.assertTrue(any("FlightDeck#8" in title for title in titles))
        self.assertTrue(any("app#9" in title for title in titles))
        self.assertFalse(any("FlightDeck#6" in title or "flock-master#7" in title for title in titles))

    def test_existing_architecture_only_chat_ask_is_removed(self):
        """Why: a previous automatic chat ask must not linger after the new routing rule."""
        loaded = cfg(self.tmp)
        write(Path(loaded["cache_dir"]) / "repos.json", {"repos": [
            {"name": "FlightDeck", "full_name": "acme/FlightDeck", "private": False},
        ]})
        data = {"merges": [{"title": "Architecture diagrams", "repo": "acme/FlightDeck",
                            "state": "Ready to merge", "number": 6,
                            "url": "https://github.com/acme/FlightDeck/pull/6"}],
                "decisions": [{"src": "ready", "state": "open", "title": "Merge acme/FlightDeck#6?",
                               "text": "- https://github.com/acme/FlightDeck/pull/6"}]}
        self.assertEqual(reconcile_ready_decisions(data, loaded), 0)
        self.assertEqual(data["decisions"], [])

    def test_steps_skip_drafts_and_guard_the_release(self):
        loaded = cfg(self.tmp, guards=[{"step_contains": "first release", "needs": "nondraft_release"}],
                     omb={"repo": "acme/app", "install_step_contains": "Install the app"})
        write(Path(loaded["cache_dir"]) / "prs.json", {"complete": True, "prs": [
            {"number": 7, "title": "Add", "repo": "acme/app", "url": "https://github.com/acme/app/pull/7",
             "draft": False, "state": "open", "merge_state": "CLEAN", "checks": "success"},
            {"number": 8, "title": "Wip", "repo": "acme/app", "url": "https://github.com/acme/app/pull/8",
             "draft": True, "state": "open", "merge_state": "DRAFT", "checks": ""},
        ]})
        data = {"steps": [
            {"text": "Ship the first release", "done": True},
            {"text": "Install the app", "done": False},
            {"text": "Merge acme/app#8", "src": "ready", "pr": "acme/app#8", "done": False},
        ]}
        self.assertEqual(reconcile_steps_evidence(data, loaded), 0)
        texts = [step["text"] for step in data["steps"]]
        self.assertIn("Merge acme/app#7", texts)
        self.assertNotIn("Merge acme/app#8", texts)
        release = next(step for step in data["steps"] if "first release" in step["text"])
        self.assertFalse(release["done"])
        write(Path(loaded["cache_dir"]) / "omb-releases.json", {"releases": [{"tag": "v0", "draft": True}]})
        reconcile_steps_evidence(data, loaded)
        release = next(step for step in data["steps"] if "first release" in step["text"])
        self.assertFalse(release["done"])
        write(Path(loaded["cache_dir"]) / "omb-releases.json", {"releases": [{"tag": "v1", "draft": False}]})
        write(Path(loaded["cache_dir"]) / "omb-install.json", {"app": "Demo", "version": "1.2", "checked_at": "2026-10-25T00:00:00Z"})
        reconcile_steps_evidence(data, loaded)
        release = next(step for step in data["steps"] if "first release" in step["text"])
        install = next(step for step in data["steps"] if step["text"] == "Install the app")
        self.assertTrue(release["done"])
        self.assertTrue(install["done"])

    def test_bot_reports_are_verbatim_and_optional(self):
        loaded = cfg(self.tmp)
        data = {"streams": [
            {"bot": "Alpha", "project": "App", "now": "Tests", "waiting": "Nothing"},
            ["Beta", "Lib", "Old", "Wait"],
        ]}
        self.assertEqual(apply_bot_reports(data, loaded), 0)
        self.assertEqual(data["streams"][0]["now"], "Tests")
        write(Path(loaded["cache_dir"]) / "bot-reports.json", [
            {"agent": "Beta", "area": "Lib", "current": "Reviewing, still.", "next": "Approve the plan", "at": "t"},
        ])
        self.assertEqual(apply_bot_reports(data, loaded), 0)
        self.assertEqual(data["streams"][1], ["Beta", "Lib", "Reviewing, still.", "Approve the plan"])
        self.assertEqual(data["streams"][0]["now"], "Tests")

    def test_priorities_rebuild_stream_items_and_keep_done(self):
        data = {
            "streams": [{"bot": "Lead", "project": "Board", "now": "1 open PR.", "waiting": "Nothing"}],
            "priorities": [{"stream": "Lead", "area": "Old", "items": [
                {"text": "stale current", "state": "current", "src": "stream"},
                {"text": "Sketch the layout", "state": "done"},
            ]}],
        }
        self.assertEqual(reconcile_priorities(data, cfg(self.tmp)), 0)
        items = data["priorities"][0]["items"]
        self.assertEqual(items[0]["text"], "1 open PR.")
        self.assertEqual(items[0]["src"], "stream")
        self.assertEqual(items[1]["text"], "Sketch the layout")
        self.assertNotIn("stale current", [item["text"] for item in items])

    def test_pin_ids_are_stable_and_unique(self):
        data = {"decisions": [{"title": "Adopt?", "text": "- Yes", "state": "open"}],
                "steps": [{"text": "Same"}, {"text": "Same"}]}
        pin_ids(data)
        self.assertTrue(data["decisions"][0]["id"].startswith("dec-"))
        self.assertNotEqual(data["steps"][0]["id"], data["steps"][1]["id"])
        first = [data["decisions"][0]["id"], data["steps"][0]["id"], data["steps"][1]["id"]]
        pin_ids(data)
        self.assertEqual(first, [data["decisions"][0]["id"], data["steps"][0]["id"], data["steps"][1]["id"]])

    def test_responses_settle_and_tick(self):
        loaded = cfg(self.tmp)
        data = {
            "decisions": [{"id": "dec-1", "state": "open", "title": "Adopt?", "text": "- Yes"}],
            "steps": [{"id": "step-1", "text": "Read the notes", "done": False}],
            "settled": [],
        }
        write(Path(loaded["cache_dir"]) / "responses.json", {"responses": [
            {"id": "dec-1", "type": "decision", "value": "accepted", "comment": "", "timestamp": "2026-10-25T12:00:00Z"},
            {"id": "step-1", "type": "step", "value": "done", "timestamp": "2026-10-25T12:00:00Z"},
            {"id": "missing", "type": "decision", "value": "rejected"},
        ]})
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(reconcile_responses(data, loaded, now=NOW), 0)
        self.assertEqual(data["decisions"][0]["state"], "settled")
        self.assertTrue(data["steps"][0]["done"])
        self.assertEqual(data["settled"][0]["detail"], "- Accepted.")
        again = reconcile_responses(data, loaded, now=NOW)
        self.assertEqual(again, 0)
        self.assertEqual(len(data["settled"]), 1)

    def test_nonempty_comment_settles_open_decision_as_alternative(self):
        decision = {
            "id": "dec-1",
            "state": "open",
            "title": "Adopt?",
            "meta": "asked",
            "text": "- Yes\n- Your alternative at 09:15: hold the merge.\n- Your alternative at 09:16: again.",
            "recommendation": "Yes, ship it.",
        }
        data = {"decisions": [decision], "settled": []}
        resp = {
            "id": "dec-1",
            "type": "decision",
            "value": "comment",
            "comment": "Ship the parser first.",
            "timestamp": "2026-10-25T12:00:00Z",
        }
        applied = apply_responses(data, [resp], set(), NOW)
        self.assertEqual(applied, ["dec-1"])
        self.assertEqual(resp["value"], "comment")
        self.assertEqual(decision["state"], "settled")
        self.assertEqual(decision["meta"], "Alternative 12:00")
        self.assertEqual(decision["recommendation"], "Yes, ship it.")
        self.assertEqual(decision["text"].count("You authorised this alternative"), 1)
        self.assertIn("- You authorised this alternative at 12:00.", decision["text"])
        self.assertNotIn("Your alternative at", decision["text"])
        self.assertIn("- Yes", decision["text"])
        self.assertEqual(data["settled"][0]["title"], "Adopt? (alternative)")
        self.assertEqual(data["settled"][0]["detail"], "- Ship the parser first.")
        self.assertNotIn("Yes, ship it.", data["settled"][0]["detail"])
        self.assertNotIn("Yes, ship it.", data["settled"][0]["title"])
        again = apply_responses(data, [resp], set(), NOW)
        self.assertEqual(again, [])
        self.assertEqual(decision["text"].count("You authorised this alternative"), 1)
        self.assertEqual(len(data["settled"]), 1)

    def test_empty_comment_is_a_noop(self):
        decision = {"id": "dec-1", "state": "open", "title": "Adopt?", "meta": "asked", "text": "- Yes"}
        data = {"decisions": [decision], "settled": []}
        resp = {"id": "dec-1", "type": "decision", "value": "comment", "comment": "  \n"}
        self.assertEqual(apply_responses(data, [resp], set(), NOW), [])
        self.assertEqual(resp["value"], "comment")
        self.assertEqual(decision["state"], "open")
        self.assertEqual(decision["meta"], "asked")
        self.assertEqual(decision["text"], "- Yes")
        self.assertEqual(data["settled"], [])

    def test_accept_and_reject_stay_unlabelled(self):
        accept = {"id": "dec-a", "state": "open", "title": "Ship?", "meta": "asked", "text": "- Yes"}
        reject = {"id": "dec-r", "state": "open", "title": "Wait?", "meta": "asked", "text": "- No"}
        data = {"decisions": [accept, reject], "settled": []}
        apply_responses(data, [
            {"id": "dec-a", "type": "decision", "value": "accepted", "comment": ""},
            {"id": "dec-r", "type": "decision", "value": "rejected", "comment": "not this"},
        ], set(), NOW)
        self.assertEqual(accept["state"], "settled")
        self.assertEqual(accept["meta"], "asked")
        self.assertEqual(accept["text"], "- Yes")
        self.assertEqual(reject["meta"], "asked")
        self.assertEqual(reject["text"], "- No")
        self.assertEqual([row["detail"] for row in data["settled"]], ["- Accepted.", "- Rejected."])
        self.assertNotIn("(alternative)", " ".join(row["title"] for row in data["settled"]))

    def test_comment_does_not_rewrite_accept_settled_decision(self):
        decision = {
            "id": "dec-1",
            "state": "settled",
            "title": "Ship?",
            "meta": "asked",
            "text": "- Yes",
            "recommendation": "Yes, ship it.",
        }
        data = {"decisions": [decision], "settled": [
            {"meta": "Sun 12:00", "title": "Ship?", "detail": "- Accepted.", "src_id": "dec-1"},
        ]}
        resp = {"id": "dec-1", "type": "decision", "value": "comment", "comment": "Do the other thing."}
        self.assertEqual(apply_responses(data, [resp], set(), NOW), [])
        self.assertEqual(resp["value"], "comment")
        self.assertEqual(decision["state"], "settled")
        self.assertEqual(decision["meta"], "asked")
        self.assertEqual(decision["text"], "- Yes")
        self.assertEqual(data["settled"][0]["detail"], "- Accepted.")
        self.assertEqual(data["settled"][0]["title"], "Ship?")

    def test_reapply_handled_response_when_decision_still_open(self):
        loaded = cfg(self.tmp)
        data = {
            "decisions": [
                {"id": "dec-a", "state": "open", "title": "Ship?", "text": "- Yes"},
                {"id": "dec-r", "state": "open", "title": "Wait?", "text": "- No"},
                {"id": "dec-c", "state": "open", "title": "Adopt?", "meta": "asked", "text": "- Yes",
                 "recommendation": "Yes, ship it."},
            ],
            "settled": [],
        }
        responses = [
            {"id": "dec-a", "type": "decision", "value": "accepted", "comment": ""},
            {"id": "dec-r", "type": "decision", "value": "rejected", "comment": ""},
            {"id": "dec-c", "type": "decision", "value": "comment", "comment": "Ship the parser first."},
        ]
        write(Path(loaded["cache_dir"]) / "responses.json", {"responses": responses})
        write(Path(loaded["cache_dir"]) / "responses-handled.json", {"ids": ["dec-a", "dec-c", "dec-r"]})
        self.assertEqual(reconcile_responses(data, loaded, now=NOW), 0)
        by_id = {row["id"]: row for row in data["decisions"]}
        self.assertEqual(by_id["dec-a"]["state"], "settled")
        self.assertEqual(by_id["dec-r"]["state"], "settled")
        self.assertEqual(by_id["dec-c"]["state"], "settled")
        self.assertEqual(by_id["dec-c"]["meta"], "Alternative 12:00")
        self.assertEqual(responses[2]["value"], "comment")
        self.assertEqual(
            {row["src_id"]: row["detail"] for row in data["settled"]},
            {"dec-a": "- Accepted.", "dec-r": "- Rejected.", "dec-c": "- Ship the parser first."},
        )
        self.assertEqual(
            next(row["title"] for row in data["settled"] if row["src_id"] == "dec-c"),
            "Adopt? (alternative)",
        )

    def test_comment_does_not_act_as_ready_merge_accept(self):
        loaded = cfg(self.tmp, public_repos=[])
        write(Path(loaded["cache_dir"]) / "repos.json", {"complete": True, "repos": [
            {"name": "app", "full_name": "acme/app", "private": False, "pushed_at": "2026-10-25T10:00:00Z",
             "created_at": "2020-01-01T00:00:00Z", "url": "https://github.com/acme/app"},
        ]})
        decision = {
            "id": "dec-1",
            "state": "open",
            "title": "Merge acme/app#7?",
            "src": "ready",
            "meta": "ready to merge",
            "text": "- acme/app#7 is ready to merge.\n- [Add](https://github.com/acme/app/pull/7)",
            "recommendation": "Yes.",
        }
        data = {
            "decisions": [decision],
            "settled": [],
            "merges": [{
                "title": "Add",
                "repo": "acme/app",
                "state": "Ready to merge",
                "number": 7,
                "url": "https://github.com/acme/app/pull/7",
            }],
        }
        resp = {"id": "dec-1", "type": "decision", "value": "comment", "comment": "Wait for the notes."}
        apply_responses(data, [resp], set(), NOW)
        self.assertEqual(resp["value"], "comment")
        self.assertNotEqual(data["settled"][0]["detail"], "- Accepted.")
        self.assertEqual(reconcile_ready_decisions(data, loaded), 0)
        opened = [row for row in data["decisions"] if row.get("state") == "open"]
        self.assertEqual(len(opened), 1)
        self.assertIn("acme/app#7", opened[0]["text"])

    def test_responses_skip_without_cache(self):
        data = {"decisions": [{"id": "dec-1", "state": "open", "title": "A", "text": "- A"}]}
        self.assertEqual(reconcile_responses(data, cfg(self.tmp), now=NOW), 0)
        self.assertEqual(data["decisions"][0]["state"], "open")

    def test_evidence_line_and_gap(self):
        loaded = cfg(self.tmp)
        self.assertEqual(check_evidence({}, loaded), 0)
        write(Path(loaded["cache_dir"]) / "prs.json", {"complete": True, "prs": [
            {"number": 1, "title": "Add", "repo": "acme/app", "state": "open"},
        ]})
        write(Path(loaded["cache_dir"]) / "repos.json", {"complete": True, "repos": []})
        self.assertEqual(check_evidence({"merges": []}, loaded, now=NOW), 2)
        self.assertEqual(check_evidence({"merges": [{"title": "Add", "repo": "acme/app", "number": 1, "state": "In progress"}]}, loaded, now=NOW), 0)


class SparkTests(unittest.TestCase):
    def test_missing_cache_skips(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data.json"
            data.write_text("{}")
            with mock.patch.dict(os.environ, {"FLIGHTDECK_CACHE": str(Path(tmp) / "empty"), "FLIGHTDECK_SPARK_FILE": ""}, clear=False):
                with mock.patch("sys.stderr", io.StringIO()):
                    self.assertEqual(spark.main(["--data", str(data)]), 0)
            self.assertEqual(json.loads(data.read_text()), {})

    def test_nodes_are_copied(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "spark.json"
            src.write_text(json.dumps({"cluster": "lab", "nodes": [{"name": "a", "status": "online"}]}))
            data = Path(tmp) / "data.json"
            data.write_text(json.dumps({"streams": []}))
            with mock.patch.dict(os.environ, {"FLIGHTDECK_SPARK_FILE": str(src)}, clear=False):
                with mock.patch("sys.stdout", io.StringIO()):
                    self.assertEqual(spark.main(["--data", str(data)]), 0)
            doc = json.loads(data.read_text())
            self.assertEqual(doc["streams"], [])
            self.assertEqual(doc["spark"]["nodes"][0]["name"], "a")


class PublishTests(unittest.TestCase):
    def test_publish_local_runs_hooks_and_keeps_demo_data(self):
        demo = (ROOT / "examples" / "demo" / "data.json").read_bytes()
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            for key in ("FLIGHTDECK_GH_OWNER", "FLIGHTDECK_DATA", "FLIGHTDECK_CLUSTER", "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT", "CLOUDFLARE_API_TOKEN"):
                env.pop(key, None)
            env["FLIGHTDECK_GH_DISABLE"] = "1"
            proc = subprocess.run(
                ["bash", str(ROOT / "scripts" / "publish_local.sh"), str(Path(tmp) / "out")],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("pre-render: 00-collect-activity", proc.stdout)
            self.assertIn("pre-render: 02-collect-cluster", proc.stdout)
            self.assertIn("pre-render: 90-pin-ids", proc.stdout)
            self.assertIn("tracker_evidence: offline", proc.stdout)
            html = (Path(tmp) / "out" / "index.html").read_text()
            self.assertIn("OpenMausBot", html)
        self.assertEqual((ROOT / "examples" / "demo" / "data.json").read_bytes(), demo)

    def test_hook_table_matches_files(self):
        text = (ROOT / "docs" / "skills" / "crew-tracker-sync" / "SKILL.md").read_text()
        import re
        names = re.findall(r"^\| `(\d\d-[^`]+)`", text, re.M)
        on_disk = sorted(p.name for p in (ROOT / "hooks" / "pre-render.d").iterdir() if p.is_file())
        self.assertEqual(names, on_disk)
        for script in (
            "refresh_pr_cache.py", "reconcile_responses.py", "reconcile_inflight.py",
            "reconcile_merges_lifecycle.py", "reconcile_ready_decisions.py",
            "reconcile_steps_evidence.py", "apply_bot_reports.py", "reconcile_priorities.py",
            "pin_ids.py", "tracker_evidence.py", "record_chat_accept.py",
        ):
            self.assertTrue((ROOT / "scripts" / script).is_file(), script)
        self.assertTrue((ROOT / "publish.sh").is_file())
        self.assertNotIn("519a5896bd3a41e4b2d5696b051f147d", text)
        self.assertNotIn("gmail.com", text.lower())

    def test_new_surface_has_no_private_markers(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("examples/demo/assets/banner.webp", readme)
        blob = [readme]
        for path in [ROOT / "publish.sh", ROOT / "config" / "sync.example.json"]:
            blob.append(path.read_text(encoding="utf-8"))
        code = []
        for path in [ROOT / "publish.sh", ROOT / "config" / "sync.example.json"]:
            code.append(path.read_text(encoding="utf-8"))
        for folder in (ROOT / "hooks", ROOT / "scripts", ROOT / "collectors"):
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix in {".py", ".sh", ""} or path.parent.name == "pre-render.d":
                    if path.is_file():
                        text = path.read_text(encoding="utf-8")
                        blob.append(text)
                        code.append(text)
        low = "\n".join(blob).lower()
        for bad in ("gmail.com", "519a5896bd3a41e4b2d5696b051f147d", "flockmate", "j.a.r.gamboa"):
            self.assertNotIn(bad, low, bad)
        self.assertNotIn("neuromancer", "\n".join(code).lower())


class FakeKV:
    """Records KV GET and PUT calls. Starts with one tracker tap."""

    def __init__(self, live=None, fail=False):
        self.live = live if live is not None else {"at": "t", "responses": [
            {"id": "dec-tap", "type": "decision", "value": "accepted", "comment": "", "timestamp": "2026-10-25T09:00:00Z"}]}
        self.puts = []
        self.fail = fail

    def __call__(self, req, timeout=None):
        if self.fail:
            raise urllib.error.URLError("down")
        if req.get_method() == "PUT":
            self.puts.append(json.loads(req.data.decode()))
            self.live = self.puts[-1]
            return FakeResp(b"{}")
        return FakeResp(json.dumps(self.live).encode())


class ChatAcceptTests(unittest.TestCase):
    """A chat Accept counts, and it must still be recorded on the tracker."""

    TS = "2026-10-26T14:18:00Z"

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name
        self.cfg = cfg(self.tmp, responses={"account_id": "acct", "kv_namespace_id": "ns",
                                            "key": "responses/owner@example.com"})

    def tearDown(self):
        os.environ.pop("CLOUDFLARE_API_TOKEN", None)
        self._tmp.cleanup()

    def store(self, name):
        return json.loads((Path(self.cfg["cache_dir"]) / name).read_text())

    def test_writes_tracker_tap_shape_to_both_stores(self):
        entry, status = record_chat_accept(self.cfg, "dec-1", at=self.TS)
        self.assertEqual(status, "skipped")
        for name in ("responses.json", "responses-chat.json"):
            doc = self.store(name)
            self.assertEqual(doc["email"], "owner@example.com")
            self.assertEqual(doc["responses"], [entry])
        for key in ("id", "type", "value", "comment", "timestamp"):
            self.assertIn(key, entry)
        self.assertEqual((entry["type"], entry["value"], entry["channel"]), ("decision", "accepted", "chat"))

    def test_upsert_by_id_replaces_older_chat_answer(self):
        record_chat_accept(self.cfg, "dec-1", at=self.TS)
        record_chat_accept(self.cfg, "dec-1", "rejected", "Not this week.", at="2026-10-26T15:00:00Z")
        for name in ("responses.json", "responses-chat.json"):
            rows = self.store(name)["responses"]
            self.assertEqual([(r["value"], r["comment"]) for r in rows], [("rejected", "Not this week.")])

    def test_chat_accept_settles_open_decision_on_publish(self):
        data = {"decisions": [{"id": "dec-1", "state": "open", "title": "Adopt?", "text": "- Yes"}], "settled": []}
        record_chat_accept(self.cfg, "dec-1", at=self.TS)
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(reconcile_responses(data, self.cfg, now=NOW), 0)
        self.assertEqual(data["decisions"][0]["state"], "settled")
        self.assertEqual(data["settled"][0]["detail"], "- Accepted.")

    def test_chat_reject_settles_as_rejected(self):
        data = {"decisions": [{"id": "dec-1", "state": "open", "title": "Adopt?", "text": "- Yes"}], "settled": []}
        record_chat_accept(self.cfg, "dec-1", "rejected", at=self.TS)
        with mock.patch("sys.stderr", io.StringIO()):
            reconcile_responses(data, self.cfg, now=NOW)
        self.assertEqual(data["settled"][0]["detail"], "- Rejected.")

    def test_live_kv_without_the_chat_answer_still_settles(self):
        """Gap: hook 03 read live KV only, so an answer written to the cache alone was dropped."""
        record_chat_accept(self.cfg, "dec-1", at=self.TS, kv=False)
        os.environ["CLOUDFLARE_API_TOKEN"] = "dummy"
        data = {"decisions": [{"id": "dec-1", "state": "open", "title": "Adopt?", "text": "- Yes"}], "settled": []}
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(reconcile_responses(data, self.cfg, opener=FakeKV(), now=NOW), 0)
        self.assertEqual(data["decisions"][0]["state"], "settled")

    def test_kv_write_upserts_and_keeps_tracker_taps(self):
        os.environ["CLOUDFLARE_API_TOKEN"] = "dummy"
        kv = FakeKV()
        _, status = record_chat_accept(self.cfg, "dec-1", at=self.TS, opener=kv)
        _, again = record_chat_accept(self.cfg, "dec-1", at="2026-10-26T15:00:00Z", opener=kv)
        self.assertEqual((status, again), ("written", "written"))
        ids = [r["id"] for r in kv.live["responses"]]
        self.assertEqual(sorted(ids), ["dec-1", "dec-tap"])

    def test_kv_failure_keeps_the_cache_record(self):
        os.environ["CLOUDFLARE_API_TOKEN"] = "dummy"
        with mock.patch("sys.stderr", io.StringIO()):
            _, status = record_chat_accept(self.cfg, "dec-1", at=self.TS, opener=FakeKV(fail=True))
        self.assertEqual(status, "failed")
        self.assertEqual(len(self.store("responses-chat.json")["responses"]), 1)

    def test_never_touches_data_json(self):
        path = Path(self.tmp) / "data.json"
        path.write_text('{"decisions": []}\n')
        os.environ["FLIGHTDECK_DATA"] = str(path)
        try:
            before = path.read_bytes()
            record_chat_accept(self.cfg, "dec-1", at=self.TS)
            self.assertEqual(path.read_bytes(), before)
        finally:
            os.environ.pop("FLIGHTDECK_DATA", None)

    def test_cli_rejects_bad_input(self):
        os.environ["FLIGHTDECK_CACHE"] = self.cfg["cache_dir"]
        for argv in ([], ["--id", "dec-1", "--value", "maybe"], ["--id", "nope"],
                     ["--id", "dec-1", "--value", "comment"], ["--id", "dec-1", "--at", "soon"]):
            with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as cm:
                main_record_chat_accept(argv)
            self.assertNotEqual(cm.exception.code, 0, argv)

    def test_cli_records_and_prints_entry(self):
        os.environ["FLIGHTDECK_CACHE"] = self.cfg["cache_dir"]
        with mock.patch("sys.stdout", io.StringIO()) as out:
            self.assertEqual(main_record_chat_accept(["--id", "dec-9", "--at", self.TS, "--no-kv"]), 0)
        self.assertEqual(json.loads(out.getvalue())["id"], "dec-9")
        self.assertEqual(self.store("responses.json")["responses"][0]["id"], "dec-9")


if __name__ == "__main__":
    unittest.main()
