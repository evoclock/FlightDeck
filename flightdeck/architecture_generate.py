"""Deterministic Bowerbird maps from planned work, not from a file inventory.

A map lists real components: TASKS.md cards, specs or plans, open PRs, recent
merges, and README-described parts. Status is built (merged on the default
branch, or a completed card), partial (an open PR or pushed branch), or
planned (a TASKS card or a spec). Callers collect those sources first.
"""
import re

SCHEMA = "bowerbird/v1"
CATEGORIES = {
    "sage": {"label": "Interface / app"},
    "peach": {"label": "Orchestration / agents"},
    "slate": {"label": "Runners / compute"},
    "mauve": {"label": "Data / storage"},
    "mustard": {"label": "CI / release"},
    "teal": {"label": "Docs / contracts"},
}
TRACKER = {"implemented": "Built", "partial": "In progress", "planned": "Planned"}
BUILT_STATUS = frozenset({"implemented", "built", "done", "complete"})
PARTIAL_STATUS = frozenset({"partial", "in progress", "in-progress"})
PLANNED_STATUS = frozenset({"planned"})
DONE_SECTIONS = frozenset({"done", "complete", "completed", "finished", "shipped"})
TASK_PRIORITY = {"in progress": 0, "review": 1, "doing": 0, "backlog": 2, "todo": 2, "later": 3}
README_SKIP = frozenset({
    "installation", "install", "setup", "getting started", "quick start",
    "installation & setup", "clone repository", "install hillstar",
    "usage", "license", "contributing", "contributors", "changelog",
    "table of contents", "toc", "contents", "badges", "security",
    "disclaimer", "documentation", "acknowledgements", "screenshots",
    "what this is", "why it exists", "what it does", "build", "run",
    "themes", "status", "layout", "layout and maintenance",
})
DOC_PATH_RE = re.compile(
    r"(^|/)(TASKS\.md|specs?|plans?|contracts|docs/plans?|docs/specs?|decisions)/",
    re.I,
)
SPEC_PATH_RE = re.compile(
    r"(^|/)(specs?|plans?|contracts|docs/plans?|docs/specs?|decisions)/.+\.(md|markdown|txt)$",
    re.I,
)
HEADING_RE = re.compile(r"^#{1,3}\s+(.+?)\s*$")
SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")
CARD_RE = re.compile(r"^- \[([ xX])\]\s+(.+)$")
TAG_CUT_RE = re.compile(r"\s+(?:\[[a-zA-Z]+::|<!--)")
TITLE_CUT_RE = re.compile(r"\s+`[^`]+`|\s+@\S+")
WORD_RE = re.compile(r"[a-z0-9]+")
INVENTORY_RE = re.compile(r"file\s*inventory", re.I)
SPARSE_FLAG = "under-3-components"
MAX_TASKS = 8
MAX_PRS = 8
MAX_MERGES = 8
MAX_DOCS = 6
MAX_README = 6


def component_counts(nodes):
    """Return built/partial/planned/other/total counts for a node list."""
    built = partial = planned = other = 0
    for node in nodes or []:
        status = str(node.get("status") or "").lower()
        if status in BUILT_STATUS:
            built += 1
        elif status in PARTIAL_STATUS:
            partial += 1
        elif status in PLANNED_STATUS:
            planned += 1
        else:
            other += 1
    return {
        "built": built,
        "partial": partial,
        "planned": planned,
        "other": other,
        "total": len(nodes or []),
    }


def is_inventory_node(node):
    if not isinstance(node, dict):
        return False
    ident = str(node.get("id") or "").lower()
    title = str(node.get("title") or "")
    return ident == "inventory" or bool(INVENTORY_RE.search(title))


def is_inventory_diagram(doc):
    if not isinstance(doc, dict):
        return False
    if any(is_inventory_node(node) for node in doc.get("nodes") or []):
        return True
    subtitle = str((doc.get("meta") or {}).get("subtitle") or "")
    return "repository tree" in subtitle.lower() or "file inventory" in subtitle.lower()


def is_auto_stub(doc):
    if not isinstance(doc, dict):
        return False
    subtitle = str((doc.get("meta") or {}).get("subtitle") or "")
    return "auto stub" in subtitle.lower()


def is_authored_planned(doc):
    """True when a file is a real planned-work map and must stay unchanged."""
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        return False
    if is_inventory_diagram(doc) or is_auto_stub(doc):
        return False
    if (doc.get("meta") or {}).get("generated"):
        return False
    return bool(doc.get("nodes"))


def meta_flags(doc):
    flags = (doc.get("meta") or {}).get("flags") or []
    if isinstance(flags, str):
        return [flags]
    return [str(item) for item in flags]


def _slug(text, used):
    base = "-".join(WORD_RE.findall(str(text).lower())[:6]) or "component"
    ident = "component" if base in {"inventory", "file-inventory"} else base
    ident = ident[:40].rstrip("-") or "component"
    n = 2
    while ident in used or ident in {"inventory", "file-inventory"}:
        suffix = f"-{n}"
        ident = (ident[:40 - len(suffix)].rstrip("-") + suffix)
        if ident in {"inventory", "file-inventory"}:
            ident = f"component-{n}"
        n += 1
    used.add(ident)
    return ident


def _clean_title(text, limit=42):
    text = TAG_CUT_RE.split(str(text or ""), 1)[0]
    text = TITLE_CUT_RE.split(text, 1)[0]
    text = re.sub(r"\s+", " ", text).strip().strip("-–—: ")
    return (text[:limit].rstrip() or "Component")


def _details(summary, status, where):
    label = TRACKER[status]
    lines = [summary.strip(), "", "#### Tracker status", label, "", "#### Where", where]
    return "\n".join(lines)


def _node(ident, title, status, typ, category, hint, summary, where, col, row):
    return {
        "id": ident,
        "at": [col, row],
        "type": typ,
        "title": _clean_title(title, 28),
        "hint": hint,
        "category": category,
        "status": status,
        "details": _details(summary, status, where),
    }


def parse_tasks_md(text):
    """Parse Vogelkop-style TASKS.md cards into stable records."""
    cards = []
    section = "backlog"
    for raw in str(text or "").splitlines():
        heading = SECTION_RE.match(raw)
        if heading:
            section = heading.group(1).strip().lower()
            continue
        match = CARD_RE.match(raw)
        if not match:
            continue
        checked = match.group(1).lower() == "x"
        rest = match.group(2).strip()
        ident = None
        found_id = re.search(r"<!--\s*id:\s*(\S+)\s*-->", rest)
        if found_id:
            ident = found_id.group(1)
        title = _clean_title(rest, 80)
        if not title:
            continue
        done = checked or section in DONE_SECTIONS
        cards.append({
            "id": ident or title,
            "title": title,
            "section": section,
            "done": done,
            "priority": TASK_PRIORITY.get(section, 4),
        })
    cards.sort(key=lambda card: (0 if card["done"] else 1, card["priority"], card["title"].lower()))
    return cards


def parse_readme_components(text):
    """Take README component headings, skipping install and license sections."""
    components = []
    for raw in str(text or "").splitlines():
        heading = HEADING_RE.match(raw)
        if not heading:
            continue
        title = _clean_title(heading.group(1), 60)
        key = title.lower()
        if not title or key in README_SKIP or key.startswith("license"):
            continue
        if re.fullmatch(r"[a-z0-9._-]+", key) and key in {"readme", "overview", "about"}:
            continue
        if len(title.split()) == 1 and key in {"description", "intro", "introduction"}:
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key) or re.fullmatch(r"\d+\.", key):
            continue
        if key in README_SKIP or any(key.startswith(prefix) for prefix in ("install", "clone ")):
            continue
        components.append({"title": title, "summary": f"README section: {title}."})
    return components


def _readme_title_and_blurb(text):
    title = None
    blurb = []
    for raw in str(text or "").splitlines():
        heading = re.match(r"^#\s+(.+?)\s*$", raw)
        if heading and not title:
            title = _clean_title(heading.group(1), 42)
            continue
        if title is not None:
            if raw.startswith("#"):
                break
            if raw.strip():
                blurb.append(raw.strip())
            elif blurb:
                break
    return title, " ".join(blurb)[:240]


def _select_tasks(cards):
    chosen = []
    for card in cards:
        if len(chosen) >= MAX_TASKS:
            break
        chosen.append(card)
    return chosen


def diagram_from_planned_work(owner, name, sha, sources=None):
    """Build a planned-work map. Never emits a file-inventory node."""
    sources = sources if isinstance(sources, dict) else {}
    owner = str(owner or "evoclock")
    name = str(name or "repository")
    sha = sha or "main"
    used = set()
    nodes = []
    seen = set()

    def accept(key, node):
        norm = re.sub(r"[^a-z0-9]+", "", key.lower())
        if not norm or norm in seen:
            return
        seen.add(norm)
        nodes.append(node)

    repo_url = f"https://github.com/{owner}/{name}"
    default_branch = sources.get("default_branch") or "main"

    for card in _select_tasks(parse_tasks_md(sources.get("tasks_md") or "")):
        status = "implemented" if card["done"] else "planned"
        typ = "TASKS.md"
        hint = card.get("id") or "TASKS.md"
        where = f"- {name} · TASKS.md · {card.get('id') or card['title']}\n- [{repo_url}/blob/{default_branch}/TASKS.md]({repo_url}/blob/{default_branch}/TASKS.md)"
        ident = _slug(card.get("id") or card["title"], used)
        accept(card["title"], _node(ident, card["title"], status, typ, "teal", str(hint)[:28],
                                    card["title"], where, 0, 0))

    if sources.get("include_readme_overview") and sources.get("readme"):
        heading, blurb = _readme_title_and_blurb(sources["readme"])
        if heading:
            accept(heading, _node(_slug(heading, used), heading, "implemented", "main", "sage", "README",
                                  blurb or heading, f"- [{repo_url}/blob/{default_branch}/README.md]"
                                  f"({repo_url}/blob/{default_branch}/README.md)", 0, 0))
        paths = set(sources.get("paths") or [])
        for raw in sources["readme"].splitlines():
            match = re.match(r"^-\s+`([^`]+)`:\s*(.+)$", raw)
            if not match or match.group(1) not in paths:
                continue
            file_path, summary = match.groups()
            if not file_path.startswith("src/"):
                continue  # only README-named implementation components, never a tree inventory
            title = file_path.rsplit("/", 1)[-1].removesuffix(".py").replace("_", " ")
            where = f"- [{repo_url}/blob/{default_branch}/{file_path}]({repo_url}/blob/{default_branch}/{file_path})"
            accept(file_path, _node(_slug(file_path, used), title, "implemented", "main", "sage",
                                    file_path.rsplit("/", 1)[-1], summary, where, 0, 0))

    for doc in list(sources.get("docs") or [])[:MAX_DOCS]:
        if not isinstance(doc, dict):
            continue
        path = str(doc.get("path") or "")
        if not path or not SPEC_PATH_RE.search("/" + path):
            # still accept an explicit spec/plan path the collector already chose
            if not re.search(r"(spec|plan|contract|decision|approach|operating-notes)", path, re.I):
                continue
        title = _clean_title(doc.get("title") or path.rsplit("/", 1)[-1], 60)
        where = f"- {name} · {path}\n- [{repo_url}/blob/{default_branch}/{path}]({repo_url}/blob/{default_branch}/{path})"
        ident = _slug(path, used)
        accept(title, _node(ident, title, "planned", "spec", "teal", path.split("/")[-1][:28],
                            str(doc.get("summary") or title), where, 0, 0))

    for pr in list(sources.get("open_prs") or [])[:MAX_PRS]:
        if not isinstance(pr, dict):
            continue
        number = pr.get("number")
        title = _clean_title(pr.get("title") or f"PR {number}", 80)
        url = pr.get("url") or f"{repo_url}/pull/{number}"
        head = pr.get("head") or "branch"
        typ = f"PR #{number}" if number is not None else "PR"
        where = f"- {name} · {typ} · {head}\n- [{url}]({url})"
        ident = _slug(f"pr-{number or title}", used)
        accept(f"pr-{number}-{title}", _node(ident, title, "partial", typ, "peach", typ,
                                             title, where, 0, 0))

    for merge in list(sources.get("merges") or [])[:MAX_MERGES]:
        if not isinstance(merge, dict):
            continue
        number = merge.get("number")
        title = _clean_title(merge.get("title") or f"Merged {number}", 80)
        url = merge.get("url") or f"{repo_url}/pull/{number}"
        typ = f"merged #{number}" if number is not None else "merged"
        where = f"- {name} · {typ} · {default_branch}\n- [{url}]({url})"
        ident = _slug(f"merged-{number or title}", used)
        accept(f"merged-{number}-{title}", _node(ident, title, "implemented", typ, "sage", typ,
                                                 title, where, 0, 0))

    if len(nodes) < 6:
        for part in parse_readme_components(sources.get("readme") or "")[:MAX_README]:
                title = part["title"]
                if title.lower() in {name.lower(), "overview", "about", "readme"}:
                    continue
                ident = _slug(title, used)
                where = f"- {name} · README · {title}\n- [{repo_url}]({repo_url})"
                accept(title, _node(ident, title, "implemented", "main", "sage", "README",
                                    part.get("summary") or title, where, 0, 0))

    flags = []
    if not nodes:
        heading, blurb = _readme_title_and_blurb(sources.get("readme") or "")
        title = heading or name
        summary = blurb or (
            f"No TASKS.md cards, specs, open PRs, or recent merges were available for {owner}/{name}."
        )
        where = f"- {name} · {default_branch}\n- [{repo_url}]({repo_url})"
        ident = _slug(name, used)
        nodes.append(_node(ident, title, "planned", "main", "teal", default_branch,
                           summary, where, 0, 0))
        flags.append(SPARSE_FLAG)

    # Place on a 3-column grid after collection so the layout stays stable.
    for index, node in enumerate(nodes):
        node["at"] = [index % 3, index // 3]

    if len(nodes) < 3 and SPARSE_FLAG not in flags:
        flags.append(SPARSE_FLAG)

    edges = []
    root = nodes[0]["id"]
    for node in nodes[1:]:
        edges.append({"from": root, "to": node["id"]})

    meta = {
        "title": name,
        "kicker": "Flock master · architecture",
        "subtitle": f"Planned work for {owner}/{name}",
        "statusTracking": True,
        "generated": True,
        "kind": "architecture",
        "grid": {"col": 360, "row": 180, "gap": 44},
        "repository": {"url": repo_url, "ref": sha},
        "repos": [f"{owner}/{name}"],
    }
    if flags:
        meta["flags"] = flags
    return {
        "schema": SCHEMA,
        "meta": meta,
        "categories": CATEGORIES,
        "nodes": nodes,
        "edges": edges,
    }


# Kept only so older import sites fail loudly instead of drawing a file tree.
def diagram_from_tree(owner, name, sha, paths):
    """Removed. Maps come from planned work, never from a path inventory."""
    raise RuntimeError("diagram_from_tree is removed; use diagram_from_planned_work")
