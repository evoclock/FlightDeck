"""Reconcile a tracker data file from evidence caches.

Instance values (owner, public repos, stream label, responses KV) come from
config/sync.json or the environment. Nothing here is fetched when the owner
is unset. Tokens are read from the environment and never printed.

Stdlib only.
"""
import copy
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from collectors import load, save
from flightdeck.common import DEFAULT_TZ, item_id

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

API = "https://api.github.com"
UA = "flightdeck-sync"


class DiscoveryError(Exception):
    """A configured source could not be read. Publish must not report success."""


DEFAULTS = {
    "owner": "",
    "cache_dir": ".cache",
    "public_repos": [],
    "primary_stream": {"agent": "", "area": "", "label": ""},
    "responses": {"account_id": "", "kv_namespace_id": "", "key": ""},
    "inflight": {
        "pushed_within_hours": 48,
        "created_within_days": 7,
        "new_repo_within_hours": 48,
    },
    "closed_within_hours": 24,
    "guards": [],
    "omb": {"repo": "", "install_step_contains": ""},
    "assets_dir": "",
}


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def load_config(path=None):
    """Defaults, then config/sync.json (or FLIGHTDECK_SYNC_CONFIG), then env."""
    cfg = copy.deepcopy(DEFAULTS)
    file = path or os.environ.get("FLIGHTDECK_SYNC_CONFIG")
    if not file:
        candidate = Path("config/sync.json")
        if candidate.is_file():
            file = str(candidate)
    if file:
        cfg = deep_merge(cfg, json.loads(Path(file).read_text(encoding="utf-8")))
    env = os.environ
    if env.get("FLIGHTDECK_GH_OWNER"):
        cfg["owner"] = env["FLIGHTDECK_GH_OWNER"].strip()
    if env.get("FLIGHTDECK_PUBLIC_REPOS") is not None and env.get("FLIGHTDECK_PUBLIC_REPOS") != "":
        cfg["public_repos"] = [p.strip() for p in env["FLIGHTDECK_PUBLIC_REPOS"].split(",") if p.strip()]
    if env.get("FLIGHTDECK_CACHE"):
        cfg["cache_dir"] = env["FLIGHTDECK_CACHE"]
    if env.get("FLIGHTDECK_ASSETS_DIR"):
        cfg["assets_dir"] = env["FLIGHTDECK_ASSETS_DIR"]
    primary = cfg["primary_stream"]
    if env.get("FLIGHTDECK_PRIMARY_AGENT"):
        primary["agent"] = env["FLIGHTDECK_PRIMARY_AGENT"].strip()
    if env.get("FLIGHTDECK_PRIMARY_AREA"):
        primary["area"] = env["FLIGHTDECK_PRIMARY_AREA"].strip()
    if env.get("FLIGHTDECK_STREAM_LABEL"):
        primary["label"] = env["FLIGHTDECK_STREAM_LABEL"].strip()
    responses = cfg["responses"]
    if env.get("FLIGHTDECK_ACCOUNT_ID") or env.get("CLOUDFLARE_ACCOUNT_ID"):
        responses["account_id"] = (env.get("FLIGHTDECK_ACCOUNT_ID") or env.get("CLOUDFLARE_ACCOUNT_ID")).strip()
    if env.get("FLIGHTDECK_RESPONSES_KV_ID"):
        responses["kv_namespace_id"] = env["FLIGHTDECK_RESPONSES_KV_ID"].strip()
    if env.get("FLIGHTDECK_RESPONSES_KEY"):
        responses["key"] = env["FLIGHTDECK_RESPONSES_KEY"].strip()
    return cfg


def cache_path(cfg, name):
    return Path(cfg["cache_dir"]) / name


def resolve_data(arg=None):
    """Explicit --data or FLIGHTDECK_DATA, else ./data.json only when it exists."""
    if arg:
        return Path(arg)
    env = os.environ.get("FLIGHTDECK_DATA")
    if env:
        return Path(env)
    default = Path("data.json")
    return default if default.is_file() else None


def read_json(path, default=None):
    file = Path(path)
    if not file.is_file():
        return default
    return json.loads(file.read_text(encoding="utf-8"))


def write_json(path, doc):
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    save(file, doc)


def cache_rows(doc, key):
    if doc is None:
        return None
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        return list(doc.get(key) or [])
    return []


def read_cache_rows(cfg, filename, key):
    path = cache_path(cfg, filename)
    if not path.is_file():
        return None
    return cache_rows(read_json(path), key)


def zone():
    name = os.environ.get("FLIGHTDECK_TZ") or DEFAULT_TZ
    try:
        return ZoneInfo(name) if ZoneInfo else None
    except Exception:
        return None


def aware(now):
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return now


def parse_time(value):
    if not value or not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def format_meta(now):
    local = aware(now).astimezone(zone()) if zone() else aware(now).astimezone()
    return local.strftime("%a %H:%M")


def bullets(*lines):
    return "\n".join(f"- {line}" for line in lines if line)


def github_token():
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_PAT") or ""


def gh_available():
    if os.environ.get("FLIGHTDECK_GH_DISABLE") == "1":
        return False
    return shutil.which("gh") is not None


def gh_runner(args):
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip().splitlines()
        msg = err[-1] if err else f"gh exited {proc.returncode}"
        raise DiscoveryError(msg[:300])
    text = proc.stdout.strip()
    if not text:
        return []
    return json.loads(text)


def http_json(url, opener, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": UA,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        try:
            ctx = opener(req, timeout=20)
        except TypeError:
            ctx = opener(req)
        with ctx as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        path = urllib.parse.urlparse(url).path
        raise DiscoveryError(f"GitHub HTTP {exc.code} for {path}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise DiscoveryError(f"GitHub request failed ({type(exc).__name__})") from exc


def repo_full(repo):
    if isinstance(repo, str):
        return repo
    if isinstance(repo, dict):
        return repo.get("nameWithOwner") or repo.get("full_name") or repo.get("name") or ""
    return ""


def full_name(owner, name):
    return name if "/" in name else f"{owner}/{name}"


def checks_from_rollup(rollup):
    if not rollup:
        return ""
    states = []
    for item in rollup:
        if not isinstance(item, dict):
            continue
        states.append(str(item.get("conclusion") or item.get("state") or item.get("status") or "").upper())
    if not states:
        return ""
    bad = {"FAILURE", "CANCELLED", "TIMED_OUT", "ERROR", "STARTUP_FAILURE"}
    pending = {"PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "REQUESTED", "EXPECTED"}
    if any(s in bad for s in states):
        return "failure"
    if any(s in pending for s in states):
        return "pending"
    if "SUCCESS" in states:
        return "success"
    return ""


def pr_key(pr):
    return f"{pr.get('repo')}#{pr.get('number')}"


def pr_is_ready(pr):
    if pr.get("draft") or str(pr.get("merge_state") or "").upper() == "DRAFT":
        return False
    if str(pr.get("merge_state") or "").upper() != "CLEAN":
        return False
    return str(pr.get("checks") or "").lower() == "success"


def merge_label(pr):
    if pr.get("draft") or str(pr.get("merge_state") or "").upper() == "DRAFT":
        return "Draft"
    if pr_is_ready(pr):
        return "Ready to merge"
    return "In progress"


def normalize_pull(full, pr, checks=""):
    merged_at = pr.get("merged_at") or pr.get("mergedAt")
    state = pr.get("state") or "open"
    author = pr.get("user") or pr.get("author") or {}
    if isinstance(author, dict):
        author = author.get("login") or author.get("name") or ""
    return {
        "number": pr.get("number"),
        "title": pr.get("title") or "",
        "repo": full,
        "author": author or "",
        "url": pr.get("html_url") or pr.get("url") or "",
        "draft": bool(pr.get("draft") if "draft" in pr else pr.get("isDraft")),
        "state": str(state).lower(),
        "merge_state": str(pr.get("mergeable_state") or pr.get("mergeStateStatus") or "").upper(),
        "checks": checks,
        "updated_at": pr.get("updated_at") or pr.get("updatedAt"),
        "closed_at": pr.get("closed_at") or pr.get("closedAt"),
        "merged": bool(merged_at) or str(state).lower() == "merged",
    }


def as_merge(row):
    if isinstance(row, dict):
        return row
    padded = list(row) + ["", "", "", ""]
    return {"title": padded[0], "repo": padded[1], "bot": padded[2], "state": padded[3]}


def as_stream(row):
    if isinstance(row, dict):
        return {
            "bot": row.get("bot") or row.get("agent") or "",
            "project": row.get("project") or row.get("area") or "",
            "now": row.get("now") if row.get("now") is not None else (row.get("current") or ""),
            "waiting": row.get("waiting") if row.get("waiting") is not None else (row.get("next") or ""),
        }
    padded = list(row) + ["", "", "", ""]
    return {"bot": padded[0], "project": padded[1], "now": padded[2], "waiting": padded[3]}


def write_stream(original, bot, project, now, waiting):
    if isinstance(original, dict):
        updated = dict(original)
        updated.update({"bot": bot, "project": project, "now": now, "waiting": waiting})
        return updated
    return [bot, project, now, waiting]


def primary_name(cfg):
    block = cfg.get("primary_stream") or {}
    return (block.get("label") or block.get("agent") or "").strip()


def within(moment, now, **delta):
    parsed = parse_time(moment) if not isinstance(moment, datetime.datetime) else moment
    if not parsed:
        return False
    return aware(now) - parsed <= datetime.timedelta(**delta)


def repo_listed(repo, names):
    repo_l = (repo or "").lower()
    short = repo_l.split("/")[-1]
    for name in names:
        item = name.lower()
        if repo_l == item or short == item or repo_l.endswith("/" + item):
            return True
    return False


def add_settled(data, title, detail, now, src_id):
    rows = data.setdefault("settled", [])
    for row in rows:
        if isinstance(row, dict) and row.get("src_id") == src_id:
            return
    rows.append({"meta": format_meta(now), "title": title, "detail": detail, "src_id": src_id})


def mentions(pr, *parts):
    blob = "\n".join(str(p or "") for p in parts)
    url = pr.get("url") or ""
    key = pr_key(pr)
    number = f"#{pr.get('number')}"
    repo = pr.get("repo") or ""
    if url and url in blob:
        return True
    if key and key in blob:
        return True
    if repo and number != "#" and repo in blob and number in blob:
        return True
    return False


# --- caches -----------------------------------------------------------------

def fetch_all(cfg, opener=None, runner=None, now=None):
    now = aware(now)
    if runner is not None:
        return fetch_via_gh(cfg, runner, now)
    if opener is not None:
        return fetch_via_rest(cfg, opener, github_token(), now)
    if gh_available():
        return fetch_via_gh(cfg, gh_runner, now)
    return fetch_via_rest(cfg, urllib.request.urlopen, github_token(), now)


def fetch_via_gh(cfg, runner, now):
    owner = cfg["owner"]
    opened = runner([
        "search", "prs", "--author", owner, "--state", "open", "--limit", "200",
        "--json", "number,title,url,repository,isDraft,updatedAt,state",
    ])
    if len(opened) >= 200:
        raise DiscoveryError("open PR search truncated at 200")
    prs = []
    for item in opened:
        full = repo_full(item.get("repository"))
        view = runner([
            "pr", "view", item.get("url") or "", "--repo", full, "--json",
            "mergeStateStatus,statusCheckRollup,isDraft,title,number,url,state",
        ])
        if isinstance(view, list):
            view = view[0] if view else {}
        prs.append(normalize_pull(full, {**item, **view}, checks_from_rollup(view.get("statusCheckRollup"))))
    day = (now - datetime.timedelta(hours=int(cfg["closed_within_hours"]))).date().isoformat()
    closed_raw = runner([
        "search", "prs", "--author", owner, "--state", "closed", "--closed", f">={day}",
        "--limit", "200", "--json", "number,title,url,repository,closedAt,state",
    ])
    if len(closed_raw) >= 200:
        raise DiscoveryError("closed PR search truncated at 200")
    closed = []
    for item in closed_raw:
        full = repo_full(item.get("repository"))
        norm = normalize_pull(full, item)
        norm["state"] = str(item.get("state") or "closed").lower()
        norm["merged"] = norm["state"] == "merged"
        closed.append(norm)
    repos_raw = runner([
        "repo", "list", owner, "--limit", "200", "--json",
        "name,nameWithOwner,pushedAt,createdAt,isPrivate,url",
    ])
    if len(repos_raw) >= 200:
        raise DiscoveryError("repo list truncated at 200")
    repos = [_repo_from_gh(item) for item in repos_raw]
    releases = _releases_from_api(cfg, runner=runner)
    return {"prs": prs, "closed": closed, "repos": repos, "releases": releases, "complete": True, "since": day}


def _repo_from_gh(item):
    full = item.get("nameWithOwner") or item.get("name") or ""
    return {
        "name": item.get("name") or full.split("/")[-1],
        "full_name": full,
        "pushed_at": item.get("pushedAt") or item.get("pushed_at"),
        "created_at": item.get("createdAt") or item.get("created_at"),
        "private": bool(item.get("isPrivate") if "isPrivate" in item else item.get("private")),
        "url": item.get("url") or "",
    }


def _releases_from_api(cfg, runner=None, opener=None, token=""):
    repo = (cfg.get("omb") or {}).get("repo") or ""
    if not repo:
        return []
    if runner is not None:
        raw = runner(["api", f"repos/{repo}/releases"])
    else:
        raw = http_json(f"{API}/repos/{repo}/releases?per_page=100", opener, token)
    if isinstance(raw, dict):
        raise DiscoveryError("release list was not a list")
    out = []
    for rel in raw:
        out.append({
            "tag": rel.get("tag_name") or rel.get("tagName") or "",
            "name": rel.get("name") or "",
            "draft": bool(rel.get("draft") if "draft" in rel else rel.get("isDraft")),
            "published_at": rel.get("published_at") or rel.get("publishedAt"),
        })
    return out


def fetch_via_rest(cfg, opener, token, now):
    owner = cfg["owner"]
    if token:
        return _fetch_rest_token(cfg, opener, token, now)
    names = cfg.get("public_repos") or []
    if not names:
        raise DiscoveryError("no gh auth, no token, and public_repos is empty")
    prs, closed, repos = [], [], []
    since = now - datetime.timedelta(hours=int(cfg["closed_within_hours"]))
    for name in names:
        full = full_name(owner, name)
        meta = http_json(f"{API}/repos/{full}", opener, "")
        repos.append({
            "name": meta.get("name") or full.split("/")[-1],
            "full_name": meta.get("full_name") or full,
            "pushed_at": meta.get("pushed_at"),
            "created_at": meta.get("created_at"),
            "private": bool(meta.get("private")),
            "url": meta.get("html_url") or "",
        })
        prs.extend(_pulls(full, "open", opener, "", since, hydrate=True))
        closed.extend(_pulls(full, "closed", opener, "", since, hydrate=False))
    releases = _releases_from_api(cfg, opener=opener, token="")
    day = since.date().isoformat()
    return {"prs": prs, "closed": closed, "repos": repos, "releases": releases, "complete": False, "since": day}


def _pulls(full, state, opener, token, since, hydrate):
    listed = http_json(f"{API}/repos/{full}/pulls?state={state}&per_page=100", opener, token)
    if isinstance(listed, dict):
        raise DiscoveryError(f"pull list for {full} was not a list")
    if len(listed) >= 100:
        raise DiscoveryError(f"pull list for {full} truncated at 100")
    out = []
    for pr in listed:
        if state == "closed":
            closed_at = parse_time(pr.get("closed_at"))
            if closed_at and closed_at < since:
                continue
        checks = ""
        body = pr
        if hydrate:
            body = http_json(f"{API}/repos/{full}/pulls/{pr['number']}", opener, token)
            sha = ((body.get("head") or {}).get("sha")) or ""
            if sha:
                status = http_json(f"{API}/repos/{full}/commits/{sha}/status", opener, token)
                checks = str(status.get("state") or "")
                if checks == "success":
                    checks = "success"
        out.append(normalize_pull(full, body, checks))
    return out


def _fetch_rest_token(cfg, opener, token, now):
    owner = cfg["owner"]
    opened = _search_prs(owner, "is:open", opener, token)
    prs = []
    for item in opened:
        full = _search_repo(item)
        number = item.get("number")
        body = http_json(f"{API}/repos/{full}/pulls/{number}", opener, token)
        sha = ((body.get("head") or {}).get("sha")) or ""
        checks = ""
        if sha:
            status = http_json(f"{API}/repos/{full}/commits/{sha}/status", opener, token)
            checks = str(status.get("state") or "")
        prs.append(normalize_pull(full, body, checks))
    since = now - datetime.timedelta(hours=int(cfg["closed_within_hours"]))
    day = since.date().isoformat()
    closed_items = _search_prs(owner, f"is:closed closed:>={day}", opener, token)
    closed = []
    for item in closed_items:
        full = _search_repo(item)
        norm = normalize_pull(full, {
            "number": item.get("number"),
            "title": item.get("title"),
            "html_url": item.get("html_url"),
            "state": "closed",
            "closed_at": item.get("closed_at"),
        })
        # Search does not say merged. Hydrate so merged_at is evidence.
        body = http_json(f"{API}/repos/{full}/pulls/{item.get('number')}", opener, token)
        norm = normalize_pull(full, body)
        closed.append(norm)
    repos = []
    try:
        page = http_json(f"{API}/users/{owner}/repos?per_page=100&type=owner&sort=pushed", opener, token)
    except DiscoveryError as exc:
        if "HTTP 404" not in str(exc):
            raise
        page = http_json(f"{API}/orgs/{owner}/repos?per_page=100&sort=pushed", opener, token)
    if isinstance(page, dict):
        raise DiscoveryError("repo list was not a list")
    if len(page) >= 100:
        raise DiscoveryError("repo list truncated at 100")
    for item in page:
        repos.append({
            "name": item.get("name"),
            "full_name": item.get("full_name"),
            "pushed_at": item.get("pushed_at"),
            "created_at": item.get("created_at"),
            "private": bool(item.get("private")),
            "url": item.get("html_url") or "",
        })
    releases = _releases_from_api(cfg, opener=opener, token=token)
    return {"prs": prs, "closed": closed, "repos": repos, "releases": releases, "complete": True, "since": day}


def _search_repo(item):
    url = item.get("repository_url") or ""
    marker = "/repos/"
    if marker in url:
        return url.split(marker, 1)[1]
    return ""


def _search_prs(owner, qualifiers, opener, token):
    q = urllib.parse.quote(f"author:{owner} is:pr {qualifiers}")
    doc = http_json(f"{API}/search/issues?per_page=100&q={q}", opener, token)
    total = int(doc.get("total_count") or 0)
    items = list(doc.get("items") or [])
    if total > len(items):
        raise DiscoveryError("PR search truncated")
    return items


def write_payload(cfg, payload, now):
    now = aware(now)
    at = now.isoformat(timespec="seconds")
    owner = cfg["owner"]
    write_json(cache_path(cfg, "prs.json"), {
        "at": at, "owner": owner, "complete": bool(payload["complete"]), "prs": payload["prs"],
    })
    write_json(cache_path(cfg, "prs-closed.json"), {
        "at": at, "owner": owner, "since": payload.get("since"), "prs": payload["closed"],
    })
    write_json(cache_path(cfg, "repos.json"), {
        "at": at, "owner": owner, "complete": bool(payload["complete"]), "repos": payload["repos"],
    })
    repo = (cfg.get("omb") or {}).get("repo") or ""
    if repo:
        write_json(cache_path(cfg, "omb-releases.json"), {
            "at": at, "repo": repo, "releases": payload["releases"],
        })


def refresh_caches(cfg, opener=None, runner=None, now=None):
    now = aware(now)
    payload = fetch_all(cfg, opener=opener, runner=runner, now=now)
    write_payload(cfg, payload, now)
    if not payload["complete"]:
        print("refresh_pr_cache: public repos only; discovery is incomplete", file=sys.stderr)
        return 2
    print(f"refresh_pr_cache: prs={len(payload['prs'])} closed={len(payload['closed'])} repos={len(payload['repos'])}")
    return 0


# --- panes ------------------------------------------------------------------

def reconcile_responses(data, cfg, opener=None, now=None):
    now = aware(now)
    try:
        payload = load_responses(cfg, opener or urllib.request.urlopen)
    except DiscoveryError as exc:
        print(f"reconcile_responses: {exc}", file=sys.stderr)
        return 2
    if payload is None:
        print("reconcile_responses: no responses cache, skipping", file=sys.stderr)
        return 0
    responses = payload.get("responses") if isinstance(payload, dict) else payload
    if not isinstance(responses, list):
        print("reconcile_responses: responses payload has no list, skipping", file=sys.stderr)
        return 0
    handled_doc = read_json(cache_path(cfg, "responses-handled.json"), {"ids": []}) or {"ids": []}
    handled = set(handled_doc.get("ids") or [])
    applied = apply_responses(data, responses, handled, now)
    if applied:
        write_json(cache_path(cfg, "responses-handled.json"), {"ids": sorted(handled | set(applied))})
    print(f"reconcile_responses: applied={len(applied)}")
    return 0


def load_responses(cfg, opener):
    token = os.environ.get("CLOUDFLARE_API_TOKEN") or ""
    block = cfg.get("responses") or {}
    account, ns, key = block.get("account_id") or "", block.get("kv_namespace_id") or "", block.get("key") or ""
    cache = cache_path(cfg, "responses.json")
    if token and account and ns and key:
        quoted = urllib.parse.quote(key, safe="")
        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{ns}/values/{quoted}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": UA})
        try:
            try:
                ctx = opener(req, timeout=20)
            except TypeError:
                ctx = opener(req)
            with ctx as resp:
                return json.load(resp)
        except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            if cache.is_file():
                print("reconcile_responses: KV fetch failed; using cache", file=sys.stderr)
                return read_json(cache)
            raise DiscoveryError(f"responses KV fetch failed ({type(exc).__name__}) and no cache") from exc
    if cache.is_file():
        return read_json(cache)
    return None


def _find_by_id(rows, rid, prefix):
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("id") or "") == rid:
            return row
        text = row.get("text") or ""
        if item_id(prefix, {"text": text}) == rid:
            return row
    return None


def comment_detail(comment):
    lines = []
    for line in comment.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()
        lines.append(stripped)
    return bullets(*lines) if lines else "- Comment recorded."


def apply_responses(data, responses, handled, now):
    applied = []
    for resp in responses:
        if not isinstance(resp, dict):
            continue
        rid = str(resp.get("id") or "")
        if not rid or rid in handled:
            continue
        value = resp.get("value") or ""
        kind = resp.get("type") or ""
        if kind == "step" or value == "done":
            step = _find_by_id(data.get("steps"), rid, "step")
            if not step or value != "done":
                continue
            step["done"] = True
            applied.append(rid)
            continue
        decision = _find_by_id(data.get("decisions"), rid, "dec")
        if not decision:
            print(f"reconcile_responses: id not on the tracker ({rid})", file=sys.stderr)
            continue
        title = decision.get("title") or "Decision"
        if value == "accepted":
            decision["state"] = "settled"
            add_settled(data, title, "- Accepted.", now, rid)
        elif value == "rejected":
            decision["state"] = "settled"
            add_settled(data, title, "- Rejected.", now, rid)
        elif value == "comment":
            comment = (resp.get("comment") or "").strip()
            if not comment:
                continue
            decision["state"] = "settled"
            add_settled(data, title, comment_detail(comment), now, rid)
        else:
            continue
        applied.append(rid)
    return applied


def _inflight_repo(repo, open_full, now, windows):
    full = repo.get("full_name") or repo.get("name") or ""
    if full in open_full:
        return True
    if within(repo.get("pushed_at"), now, hours=int(windows["pushed_within_hours"])):
        return True
    if within(repo.get("created_at"), now, days=int(windows["created_within_days"])):
        return True
    return False


def reconcile_inflight(data, cfg, now=None):
    now = aware(now)
    prs = read_cache_rows(cfg, "prs.json", "prs")
    repos = read_cache_rows(cfg, "repos.json", "repos")
    if prs is None and repos is None and not cfg.get("owner"):
        print("reconcile_inflight: no caches, skipping", file=sys.stderr)
        return 0
    if prs is None or repos is None:
        print("reconcile_inflight: need both .cache/prs.json and .cache/repos.json", file=sys.stderr)
        return 2
    prs = prs or []
    open_prs = [p for p in prs if str(p.get("state") or "open").lower() == "open"]
    merges = []
    open_full = set()
    ready = 0
    for pr in open_prs:
        label = merge_label(pr)
        if label == "Ready to merge":
            ready += 1
        full = pr.get("repo") or ""
        open_full.add(full)
        merges.append({
            "title": pr.get("title") or f"{full}#{pr.get('number')}",
            "repo": full,
            "bot": pr.get("author") or "",
            "state": label,
            "url": pr.get("url") or "",
            "number": pr.get("number"),
        })
    windows = cfg["inflight"]
    synthetic = 0
    new_repos = []
    for repo in repos or []:
        full = repo.get("full_name") or ""
        if not full or full in open_full:
            continue
        if not _inflight_repo(repo, open_full, now, windows):
            continue
        name = repo.get("name") or full.split("/")[-1]
        merges.append({
            "title": f"{name} · active on main",
            "repo": full,
            "bot": primary_name(cfg),
            "state": "Active on main",
            "synthetic": True,
        })
        synthetic += 1
        if within(repo.get("created_at"), now, hours=int(windows["new_repo_within_hours"])):
            new_repos.append(repo)
    data["merges"] = merges
    _upsert_primary_stream(data, cfg, len(open_prs), synthetic, ready)
    _upsert_new_repo_decisions(data, new_repos)
    _upsert_architecture(data, cfg, merges)
    print(f"reconcile_inflight: prs={len(open_prs)} active={synthetic}")
    return 0


def _upsert_primary_stream(data, cfg, n_open, n_active, n_ready):
    name = primary_name(cfg)
    if not name:
        return
    area = (cfg.get("primary_stream") or {}).get("area") or "In flight"
    parts = []
    if n_open:
        parts.append("1 open PR." if n_open == 1 else f"{n_open} open PRs.")
    if n_active:
        parts.append("1 repo active on main." if n_active == 1 else f"{n_active} repos active on main.")
    now_line = " ".join(parts) or "Nothing in flight."
    if n_ready:
        waiting = "1 ready to merge." if n_ready == 1 else f"{n_ready} ready to merge."
    else:
        waiting = "Nothing"
    streams = data.setdefault("streams", [])
    for index, row in enumerate(streams):
        if as_stream(row)["bot"] == name:
            streams[index] = write_stream(row, name, area, now_line, waiting)
            return
    streams.append({"bot": name, "project": area, "now": now_line, "waiting": waiting})


def _upsert_new_repo_decisions(data, repos):
    decisions = data.setdefault("decisions", [])
    open_blob = "\n".join(
        "\n".join(str(d.get(k) or "") for k in ("title", "text", "recommendation", "why"))
        for d in decisions if isinstance(d, dict) and d.get("state") == "open"
    )
    for repo in repos:
        full = repo.get("full_name") or ""
        if full and full in open_blob:
            continue
        name = repo.get("name") or full
        decisions.append({
            "state": "open",
            "title": f"New repo {name}",
            "meta": "new repo",
            "src": "new-repo",
            "text": bullets(f"{full} was created.", "It is on Merges."),
            "recommendation": "Say if it should stay on the tracker.",
            "why": "- It showed up in the repo list.",
        })
        open_blob += f"\n{full}"


def _safe_assets(cfg):
    raw = (cfg.get("assets_dir") or "").strip()
    if not raw:
        return None
    path = Path(raw).resolve()
    demo = (Path.cwd() / "examples" / "demo").resolve()
    try:
        path.relative_to(demo)
    except ValueError:
        return path
    return None


def _upsert_architecture(data, cfg, merges):
    projects = data.get("projects") if isinstance(data.get("projects"), dict) else {}
    tabs = list(projects.get("tabs") or [])
    known = {t.get("id") for t in tabs if isinstance(t, dict)}
    pending = []
    assets = _safe_assets(cfg)
    seen_repos = []
    for row in merges:
        full = row.get("repo") or ""
        if not full or full in seen_repos:
            continue
        seen_repos.append(full)
        ident = _slug(full)
        if ident in known:
            continue
        if assets is None:
            pending.append({"id": ident, "repo": full})
            continue
        diagram = _write_stub(assets, ident, full)
        tabs.append({"id": ident, "diagram": diagram})
        known.add(ident)
    projects["tabs"] = tabs
    projects["pending"] = pending
    if not projects.get("rule"):
        projects["rule"] = "Every in-flight product keeps a diagram. A stub stands in until a real one is rendered."
    data["projects"] = projects


def _slug(full):
    raw = full.split("/")[-1].lower()
    chars = [c if c.isalnum() else "-" for c in raw]
    slug = "".join(chars).strip("-") or "repo"
    return slug


def _write_stub(assets, ident, full):
    diagram = Path("architecture") / "stubs" / f"{ident}.bower.json"
    doc = {
        "schema": "bowerbird/v1",
        "meta": {"title": full.split("/")[-1], "subtitle": "Stub until a real diagram is rendered.", "repos": [full]},
        "nodes": [{"id": ident, "name": full.split("/")[-1], "status": "planned", "unverified": True}],
        "edges": [],
    }
    target = assets / diagram
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(doc, indent=2) + "\n").encode()
    target.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    rendered = assets / "architecture" / "rendered"
    html = "<!doctype html><html><head><meta charset=\"utf-8\"><title>stub</title></head><body><p>Stub diagram.</p></body></html>\n"
    for view in ("flat", "iso"):
        page = rendered / view / f"{ident}.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(html, encoding="utf-8")
    manifest_path = rendered / "manifest.json"
    manifest = read_json(manifest_path, {"diagrams": {}}) or {"diagrams": {}}
    diagrams = manifest.setdefault("diagrams", {})
    diagrams[f"{ident}.bower.json"] = {"sha256": digest}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return diagram.as_posix()


def reconcile_merges_lifecycle(data, cfg, now=None):
    now = aware(now)
    closed = read_cache_rows(cfg, "prs-closed.json", "prs")
    if closed is None:
        print("reconcile_merges_lifecycle: no closed cache, skipping", file=sys.stderr)
        return 0
    merges = list(data.get("merges") or [])
    for pr in closed:
        key = pr_key(pr)
        merges = [row for row in merges if not _row_matches_pr(as_merge(row), pr)]
        title = pr.get("title") or key
        if pr.get("merged"):
            detail = f"- {key} merged."
            heading = f"Merged {title}"
        else:
            detail = f"- {key} closed."
            heading = f"Closed {title}"
        add_settled(data, heading, detail, now, f"merged:{key}")
        for step in data.get("steps") or []:
            if isinstance(step, dict) and _step_matches_pr(step, pr):
                step["done"] = True
        for decision in data.get("decisions") or []:
            if not isinstance(decision, dict) or decision.get("state") != "open":
                continue
            if mentions(pr, decision.get("text"), decision.get("recommendation"), decision.get("why"), decision.get("title")):
                decision["state"] = "settled"
                add_settled(data, decision.get("title") or heading, detail, now, f"merged-dec:{key}")
    data["merges"] = merges
    print(f"reconcile_merges_lifecycle: closed={len(closed)}")
    return 0


def _row_matches_pr(row, pr):
    if row.get("number") is not None and str(row.get("number")) == str(pr.get("number")) and row.get("repo") == pr.get("repo"):
        return True
    if row.get("url") and row.get("url") == pr.get("url"):
        return True
    if row.get("title") and row.get("title") == pr.get("title") and row.get("repo") == pr.get("repo"):
        return True
    return mentions(pr, row.get("title"), row.get("repo"))


def _step_matches_pr(step, pr):
    if step.get("pr") and step.get("pr") == pr_key(pr):
        return True
    return mentions(pr, step.get("text"), step.get("url"), step.get("pr"))


def reconcile_ready_decisions(data, cfg, now=None):
    del now
    names = cfg.get("public_repos") or []
    if not names:
        print("reconcile_ready_decisions: public_repos empty, skipping", file=sys.stderr)
        return 0
    decisions = data.setdefault("decisions", [])
    added = 0
    for row in data.get("merges") or []:
        info = as_merge(row)
        if not str(info.get("state") or "").lower().startswith("ready"):
            continue
        if not repo_listed(info.get("repo"), names):
            continue
        pr = {"repo": info.get("repo"), "number": info.get("number"), "url": info.get("url"), "title": info.get("title")}
        if info.get("number") is None:
            pr["number"] = ""
        if _open_mentions(decisions, pr):
            continue
        number = info.get("number")
        label = f"{info.get('repo')}#{number}" if number not in (None, "") else info.get("repo")
        url = info.get("url") or ""
        link = f"[{info.get('title') or label}]({url})" if url else (info.get("title") or label)
        decisions.append({
            "state": "open",
            "title": f"Merge {label}?",
            "meta": "ready to merge",
            "src": "ready",
            "text": bullets(f"{label} is ready to merge.", link),
            "recommendation": "Yes.",
            "why": bullets("The merge state is clean.", "Checks are green."),
        })
        added += 1
    print(f"reconcile_ready_decisions: added={added}")
    return 0


def _open_mentions(decisions, pr):
    for decision in decisions:
        if not isinstance(decision, dict) or decision.get("state") != "open":
            continue
        if mentions(pr, decision.get("text"), decision.get("recommendation"), decision.get("why"), decision.get("title")):
            return True
    return False


def reconcile_steps_evidence(data, cfg, now=None):
    del now
    prs = read_cache_rows(cfg, "prs.json", "prs")
    if prs is not None:
        ready = [p for p in prs if pr_is_ready(p)]
        ready_keys = {pr_key(p) for p in ready}
        steps = []
        for step in data.get("steps") or []:
            if isinstance(step, dict) and step.get("src") == "ready" and step.get("pr") not in ready_keys:
                continue
            steps.append(step)
        have = {step.get("pr") for step in steps if isinstance(step, dict)}
        for pr in ready:
            key = pr_key(pr)
            if key in have:
                continue
            steps.append({
                "text": f"Merge {key}",
                "url": pr.get("url") or "",
                "meta": "ready",
                "done": False,
                "src": "ready",
                "pr": key,
            })
        data["steps"] = steps
    _apply_install(data, cfg)
    _apply_guards(data, cfg)
    return 0


def _apply_install(data, cfg):
    needle = ((cfg.get("omb") or {}).get("install_step_contains") or "").strip()
    if not needle:
        return
    doc = read_json(cache_path(cfg, "omb-install.json"))
    if not isinstance(doc, dict) or not doc.get("version"):
        return
    for step in data.get("steps") or []:
        if isinstance(step, dict) and needle in (step.get("text") or ""):
            step["done"] = True


def _apply_guards(data, cfg):
    releases = read_cache_rows(cfg, "omb-releases.json", "releases")
    live = []
    if releases:
        live = [rel for rel in releases if not rel.get("draft")]
    for guard in cfg.get("guards") or []:
        needle = (guard.get("step_contains") or "").strip()
        if not needle or guard.get("needs") != "nondraft_release":
            continue
        for step in data.get("steps") or []:
            if not isinstance(step, dict) or needle not in (step.get("text") or ""):
                continue
            step["done"] = bool(live)


def apply_bot_reports(data, cfg, now=None):
    del now
    path = cache_path(cfg, "bot-reports.json")
    if not path.is_file():
        print("apply_bot_reports: no cache, skipping", file=sys.stderr)
        return 0
    doc = read_json(path, [])
    reports = doc if isinstance(doc, list) else (doc.get("reports") or [])
    streams = data.setdefault("streams", [])
    for report in reports:
        if not isinstance(report, dict):
            continue
        agent = report.get("agent") or ""
        if not agent:
            continue
        area = report.get("area") if report.get("area") is not None else ""
        current = report.get("current") if report.get("current") is not None else ""
        nxt = report.get("next") if report.get("next") is not None else ""
        replaced = False
        for index, row in enumerate(streams):
            if as_stream(row)["bot"] == agent:
                streams[index] = write_stream(row, agent, area, current, nxt)
                replaced = True
                break
        if not replaced:
            streams.append({"bot": agent, "project": area, "now": current, "waiting": nxt})
    print(f"apply_bot_reports: {len(reports)}")
    return 0


def reconcile_priorities(data, cfg, now=None):
    del cfg, now
    existing = list(data.get("priorities") or [])
    by_name = {block.get("stream"): block for block in existing if isinstance(block, dict)}
    out = []
    seen = set()
    for row in data.get("streams") or []:
        stream = as_stream(row)
        name = stream["bot"]
        if not name or name in seen:
            continue
        seen.add(name)
        block = by_name.get(name) or {"stream": name, "area": stream["project"], "items": []}
        kept = [item for item in (block.get("items") or []) if item.get("src") != "stream"]
        texts = {item.get("text") for item in kept}
        if stream["now"] and stream["now"] not in texts and stream["now"] != "Nothing in flight.":
            kept.insert(0, {"text": stream["now"], "state": "current", "src": "stream"})
            texts.add(stream["now"])
        waiting = stream["waiting"]
        if waiting and not str(waiting).lower().startswith("nothing") and waiting not in texts:
            kept.append({"text": waiting, "state": "next", "src": "stream"})
        out.append({"stream": name, "area": stream["project"] or block.get("area") or "", "items": kept})
    for block in existing:
        if isinstance(block, dict) and block.get("stream") not in seen:
            out.append(block)
    data["priorities"] = out
    return 0


def pin_ids(data, cfg=None, now=None):
    del cfg, now
    seen = set()
    for prefix, key in (("dec", "decisions"), ("step", "steps")):
        for item in data.get(key) or []:
            if not isinstance(item, dict):
                continue
            if "text" not in item:
                item["text"] = item.get("title") or key
            proposed = item.get("id") or item_id(prefix, item)
            ident = str(proposed)
            suffix = 2
            while ident in seen:
                ident = f"{proposed}-{suffix}"
                suffix += 1
            item["id"] = ident
            seen.add(ident)
    return 0


def check_evidence(data, cfg, now=None):
    moment = aware(now)
    prs_path = cache_path(cfg, "prs.json")
    repos_path = cache_path(cfg, "repos.json")
    if not prs_path.is_file() and not repos_path.is_file():
        print("tracker_evidence: offline, no caches")
        return 0
    gaps = []
    open_prs = []
    if prs_path.is_file():
        doc = read_json(prs_path, {})
        if isinstance(doc, dict) and doc.get("complete") is False:
            gaps.append("pr cache incomplete")
        open_prs = [p for p in (cache_rows(doc, "prs") or []) if str(p.get("state") or "open").lower() == "open"]
        rows = [as_merge(row) for row in (data.get("merges") or [])]
        for pr in open_prs:
            if not any(_row_matches_pr(row, pr) for row in rows):
                gaps.append(f"open PR missing {pr_key(pr)}")
    inflight = 0
    if repos_path.is_file():
        doc = read_json(repos_path, {})
        if isinstance(doc, dict) and doc.get("complete") is False:
            gaps.append("repo cache incomplete")
        open_full = {p.get("repo") for p in open_prs}
        for repo in cache_rows(doc, "repos") or []:
            if _inflight_repo(repo, open_full, moment, cfg["inflight"]):
                inflight += 1
    print(f"tracker_evidence: prs={len(open_prs)} inflight={inflight} gaps={len(gaps)}")
    if gaps:
        print("tracker_evidence: " + "; ".join(gaps), file=sys.stderr)
        return 2
    return 0


def cli_data(fn, argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=(fn.__doc__ or "").splitlines()[0] if fn.__doc__ else fn.__name__)
    parser.add_argument("--data", help="data.json (default $FLIGHTDECK_DATA or ./data.json when it exists)")
    parser.add_argument("--config", help="sync config JSON (default $FLIGHTDECK_SYNC_CONFIG or config/sync.json)")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    path = resolve_data(args.data)
    if path is None:
        print(f"{fn.__name__}: no data file, skipping", file=sys.stderr)
        return 0
    data = load(path) if path.is_file() else {}
    before = copy.deepcopy(data)
    code = fn(data, cfg)
    if data != before:
        save(path, data)
    return 0 if code is None else code


def main_refresh(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Refresh .cache PR, closed-PR, repo, and release evidence.")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    if not cfg.get("owner"):
        print("refresh_pr_cache: owner not set, skipping", file=sys.stderr)
        return 0
    try:
        return refresh_caches(cfg)
    except DiscoveryError as exc:
        print(f"refresh_pr_cache: {exc}", file=sys.stderr)
        return 2


def main_evidence(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Log PR and in-flight counts. Exit 2 when evidence has gaps.")
    parser.add_argument("--data")
    parser.add_argument("--config")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    path = resolve_data(args.data)
    data = load(path) if path and path.is_file() else {}
    return check_evidence(data, cfg)
