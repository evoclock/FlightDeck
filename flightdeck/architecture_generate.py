"""Deterministic Bowerbird maps from a verified repository tree.

The map describes observed paths, not inferred runtime connections. Callers pin
GitHub tree responses to a repository commit before passing them here.
"""
import re

GROUPS = (
    ("packages", "Packages", r"(^|/)(package\.json|pyproject\.toml|Cargo\.toml|go\.mod)$"),
    ("entry", "Entry points", r"(^|/)(main|index|app|cli)(\.[A-Za-z0-9]+)$"),
    ("ci", "CI workflows", r"^\.github/workflows/[^/]+\.ya?ml$|^\.buildkite/[^/]+\.ya?ml$"),
    ("tests", "Tests", r"(^|/)(tests?|specs?)/"),
    ("docs", "Documentation", r"(^|/)(README[^/]*|docs/[^/]+)$"),
)


def diagram_from_tree(owner, name, sha, paths):
    """Build a stable, non-speculative diagram from path names at a pinned head."""
    unknown = paths is None
    paths = sorted({p for p in (paths or []) if isinstance(p, str) and len(p) <= 240
                    and not p.startswith("/") and ".." not in p.split("/")})
    nodes = [{"id": "repo", "zone": "structure", "at": [0, 0], "type": "service",
              "title": name[:18], "lines": ["Repository structure"], "category": "slate",
              "status": "implemented", "details": f"Repository: {owner}/{name}. Head: {sha or 'unknown'}."}]
    edges = []
    for key, title, pattern in GROUPS:
        found = [p for p in paths if re.search(pattern, p, re.I)][:8]
        if not found:
            continue
        row = len(nodes)
        nodes.append({"id": key, "zone": "structure", "at": [1, row - 1],
                      "type": "service", "title": title, "lines": [f"{len(found)} observed paths"],
                      "category": "sage", "status": "implemented",
                      "details": "Observed files at the pinned head:\n" +
                                 "\n".join(f"- `{p}`" for p in found)})
        edges.append({"from": "repo", "to": key, "kind": "data", "label": "contains"})
    if not edges:
        nodes.append({"id": "inventory", "zone": "structure", "at": [1, 0],
                      "type": "service", "title": "File inventory", "lines": ["Inventory unknown" if unknown else f"{len(paths)} paths"],
                      "category": "sage", "status": "implemented",
                      "details": "Tree unavailable." if unknown else "Observed paths:\n" +
                                 "\n".join(f"- `{p}`" for p in paths[:8])})
        edges.append({"from": "repo", "to": "inventory", "kind": "data", "label": "contains"})
    return {"schema": "bowerbird/v1",
            "meta": {"title": f"{name} structure", "subtitle": "Generated from repository tree",
                     "generated": True, "kind": "architecture", "view": "flat",
                     "repository": {"url": f"https://github.com/{owner}/{name}", "ref": sha or "main"}},
            "zones": [{"id": "structure", "title": "Observed structure", "category": "slate"}],
            "nodes": nodes, "edges": edges}
