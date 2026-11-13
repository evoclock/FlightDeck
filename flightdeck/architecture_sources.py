"""Collect planned-work sources for a repository map.

Looks at a local checkout first, then `gh api`. The tree listing is only used
to find TASKS, specs, plans, and contracts. It is never turned into a map.
"""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

from flightdeck.architecture_generate import SPEC_PATH_RE

DOC_NAMES = ("TASKS.md", "README.md", "README")
README_NAMES = frozenset({"readme.md", "readme"})
MAX_REMOTE_DOCS = 6
MAX_PULLS = 20


def _run_gh(argv, timeout=20):
    result = subprocess.run(
        ["gh", "api", *argv],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def _decode_contents(payload):
    if not isinstance(payload, dict) or payload.get("type") != "file":
        return None
    encoding = payload.get("encoding")
    content = payload.get("content") or ""
    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return None
    if isinstance(content, str) and content and encoding in (None, "utf-8", ""):
        return content
    return None


def _read_local(root):
    root = Path(root)
    sources = {"docs": [], "open_prs": [], "merges": [], "default_branch": "main"}
    tasks = root / "TASKS.md"
    if tasks.is_file():
        sources["tasks_md"] = tasks.read_text(encoding="utf-8", errors="replace")
    for name in ("README.md", "README"):
        path = root / name
        if path.is_file():
            sources["readme"] = path.read_text(encoding="utf-8", errors="replace")
            break
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".md", ".markdown", ".txt"}:
            continue
        rel = path.relative_to(root).as_posix()
        if rel in {"TASKS.md", "README.md", "README"}:
            continue
        if not SPEC_PATH_RE.search("/" + rel):
            continue
        if len(sources["docs"]) >= MAX_REMOTE_DOCS:
            break
        sources["docs"].append({
            "path": rel,
            "title": path.stem.replace("-", " ").replace("_", " "),
            "summary": f"Planning doc at {rel}.",
        })
    return sources


def _gh_json(runner, path, timeout=20):
    status, stdout, _stderr = runner([path], timeout) if _accepts_timeout(runner) else _call(runner, path, timeout)
    if status != 0 or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except ValueError:
        return None


def _accepts_timeout(runner):
    return runner is _run_gh or getattr(runner, "accepts_timeout", False)


def _call(runner, path, timeout):
    try:
        return runner([path], timeout)
    except TypeError:
        result = runner(["gh", "api", path] if False else [path])
        if isinstance(result, tuple) and len(result) == 3:
            return result
        raise


def _gh_file(runner, owner, name, path, ref):
    suffix = f"?ref={ref}" if ref else ""
    payload = _gh_json(runner, f"repos/{owner}/{name}/contents/{path}{suffix}")
    return _decode_contents(payload or {})


def _gh_pulls(runner, owner, name, state):
    payload = _gh_json(runner, f"repos/{owner}/{name}/pulls?state={state}&per_page={MAX_PULLS}&sort=updated")
    if not isinstance(payload, list):
        return []
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        head = item.get("head") or {}
        rows.append({
            "number": item.get("number"),
            "title": item.get("title") or "",
            "head": (head.get("ref") if isinstance(head, dict) else None) or "",
            "url": item.get("html_url") or item.get("url") or "",
            "merged_at": item.get("merged_at"),
        })
    return rows


def collect_planned_sources(owner, name, sha=None, root=None, runner=None, offline=None):
    """Return a sources dict for diagram_from_planned_work.

    `root` is an optional local checkout. When offline, network collection is skipped.
    """
    if offline is None:
        offline = os.environ.get("CREW_TRACKER_OFFLINE") == "1"
    sources = {"docs": [], "open_prs": [], "merges": [], "default_branch": "main"}
    if root and Path(root).is_dir():
        sources.update({k: v for k, v in _read_local(root).items() if v})
        sources.setdefault("docs", [])
        sources.setdefault("open_prs", [])
        sources.setdefault("merges", [])
    if offline:
        return sources
    runner = runner or _run_gh
    ref = sha or sources.get("default_branch") or "main"
    repo = _gh_json(runner, f"repos/{owner}/{name}")
    if isinstance(repo, dict) and repo.get("default_branch"):
        sources["default_branch"] = repo["default_branch"]
        if not sha:
            ref = repo["default_branch"]
    if not sources.get("tasks_md"):
        text = _gh_file(runner, owner, name, "TASKS.md", ref)
        if text:
            sources["tasks_md"] = text
    if not sources.get("readme"):
        for filename in ("README.md", "README"):
            text = _gh_file(runner, owner, name, filename, ref)
            if text:
                sources["readme"] = text
                break
    if not sources.get("docs"):
        status, stdout, _ = _invoke(runner, f"repos/{owner}/{name}/git/trees/{ref}?recursive=1", 30)
        tree = None
        if status == 0 and stdout.strip():
            try:
                tree = json.loads(stdout)
            except ValueError:
                tree = None
        paths = []
        for item in (tree or {}).get("tree") or []:
            if item.get("type") != "blob":
                continue
            path = item.get("path") or ""
            if SPEC_PATH_RE.search("/" + path):
                paths.append(path)
            if len(paths) >= MAX_REMOTE_DOCS:
                break
        docs = []
        for path in paths:
            docs.append({
                "path": path,
                "title": Path(path).stem.replace("-", " ").replace("_", " "),
                "summary": f"Planning doc at {path}.",
            })
        if docs:
            sources["docs"] = docs
    if not sources.get("open_prs"):
        sources["open_prs"] = [row for row in _gh_pulls(runner, owner, name, "open") if not row.get("merged_at")]
    if not sources.get("merges"):
        closed = _gh_pulls(runner, owner, name, "closed")
        sources["merges"] = [row for row in closed if row.get("merged_at")]
    return sources


def _invoke(runner, path, timeout):
    try:
        return runner([path], timeout)
    except TypeError:
        return runner([path])


def guess_local_root(name):
    home = Path.home()
    for candidate in (home / name, home / name.lower(), Path.cwd() / name):
        if candidate.is_dir() and (candidate / ".git").exists():
            return str(candidate)
    return None
