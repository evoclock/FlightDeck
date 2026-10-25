"""`architecture.diagrams`: one pi-bowerbird diagram per project, flat and isometric, in a full-width pane.

data.json `projects` = {rule, verified, tabs: [{id, diagram}]}; `diagram` is a *.bower.json path relative to
assets_dir. Pre-rendered pages live in assets_dir/architecture/rendered/{flat,iso}/<name>.html with a
manifest.json of source sha256s; a render older than its source fails loudly. Geist variable for the frames is
read from assets_dir/fonts/geist-variable.ttf. No tabs: the pane renders with an empty-state note.
"""
import base64
import hashlib
import json
import re
from pathlib import Path

from flightdeck.common import e, pane

STATUS = {"built": "Built", "progress": "In progress", "planned": "Planned", "unverified": "Unverified"}
BB_STATUS = {"implemented": "built", "partial": "progress", "planned": "planned"}
BB_LEGEND = {"built": "implemented", "progress": "partial", "planned": "planned", "unverified": "planned, marked Unverified"}
VIEWS = {"iso": "Isometric", "flat": "Regular"}   # first is the default view
FONT_MARK = "<!--flightdeck-fonts-->"


class DiagramError(ValueError):
    pass


def tracker_status(n):
    return "unverified" if n.get("unverified") else BB_STATUS[n["status"]]


def bb_page(src):
    """Bowerbird's standalone page made self-contained: no web-font links, links open outside the frame."""
    out = re.sub(r'<link rel="(?:preconnect|stylesheet)" href="https://fonts\.[^"]*"[^>]*>\n?', "", src)
    out = out.replace("<head>", '<head><base target="_blank">', 1).replace("</head>", FONT_MARK + "</head>", 1)
    ext = [m for m in re.findall(r'<(\w+)\s[^>]*?\b(?:src|href)="https?://', out) if m != "a"]
    if ext or FONT_MARK not in out:
        raise DiagramError(f"bowerbird page would load external resources: {ext}")
    return out


def load_diagram(base, path):
    src = (base / path).read_bytes()
    dg = json.loads(src)
    if dg.get("schema") != "bowerbird/v1":
        raise DiagramError(f"{path}: not a bowerbird/v1 diagram")
    rendered = base / "architecture" / "rendered"
    name = Path(path).name
    entry = json.loads((rendered / "manifest.json").read_text())["diagrams"].get(name, {})
    if entry.get("sha256") != hashlib.sha256(src).hexdigest():
        raise DiagramError(f"{path} changed since it was rendered; render the diagrams again")
    stem = name.removesuffix(".bower.json")
    return dg, {v: bb_page((rendered / v / f"{stem}.html").read_text()) for v in VIEWS}


def bb_font(base):
    p = base / "fonts" / "geist-variable.ttf"
    if not p.exists():
        raise DiagramError(f"{p} is missing")
    return ("@font-face{font-family:Geist;font-weight:100 900;font-style:normal;"
            "src:url(data:font/ttf;base64,%s) format('truetype')}" % base64.b64encode(p.read_bytes()).decode())


def embed(i, s):
    blob = json.dumps(s).replace("<", "\\u003c")   # no "</script" or "<!--" inside the script element
    return f'<script type="application/json" id="{i}">{blob}</script>'


def render(ctx):
    base = Path(ctx.assets_dir)
    P = ctx.data.get("projects") or {}
    loaded = [(t, *load_diagram(base, t["diagram"])) for t in P.get("tabs") or []]
    tabs, panels, pages = [], [], []
    for i, (t, dg, html_) in enumerate(loaded):
        pid, name, st = e(t["id"]), dg["meta"]["title"], [tracker_status(n) for n in dg["nodes"]]
        sel = "true" if i == 0 else "false"
        tabs.append(f'<button role="tab" id="tab-{pid}" aria-selected="{sel}" aria-controls="arch-{pid}" '
                    f'tabindex="{0 if i == 0 else -1}" type="button">{e(name)}</button>')
        counts = " · ".join(f'{st.count(k)} {v.lower()}' for k, v in STATUS.items() if k in st)
        repos = " ".join(f'<a href="https://github.com/{e(r)}">{e(r)}</a>' for r in dg["meta"].get("repos", []))
        toggle = "".join(f'<button type="button" class="vt" data-view="{v}" aria-pressed="{str(j == 0).lower()}">{l}</button>'
                         for j, (v, l) in enumerate(VIEWS.items()))
        panels.append(f'<div role="tabpanel" id="arch-{pid}" aria-labelledby="tab-{pid}" class="tabpanel"{"" if i == 0 else " hidden"}>'
                      f'<p class="arch-sum">{e(dg["meta"].get("subtitle", ""))}</p>'
                      f'<div class="arch-bar"><p class="arch-meta">{counts} · {repos}</p>'
                      f'<div class="views" role="group" aria-label="{e(name)} view">{toggle}</div></div>'
                      f'<div class="bb-frame" data-p="{pid}" data-name="{e(name)}">'
                      f'<noscript><p class="muted">The diagram needs JavaScript.</p></noscript></div>'
                      f'<p class="note">Source: {e(t["diagram"])}, rendered by pi-bowerbird.</p></div>')
        pages += [embed(f"bb-{pid}-{v}", html_[v]) for v in VIEWS]
    legend = "".join(f'<span class="lg"><b>{v}</b> = {BB_LEGEND[k]}</span>' for k, v in STATUS.items())
    checked = f' Checked {e(P["verified"])}.' if P.get("verified") else ""
    note = f'<p class="note">{e(P.get("rule", ""))}{checked}</p>' if (P.get("rule") or checked) else ""
    if loaded:
        body = (f'<div class="arch-head"><div class="tabs" role="tablist" aria-label="Projects">{"".join(tabs)}</div>'
                f'<div class="legend">{legend}</div></div>{"".join(panels)}{note}{"".join(pages)}{embed("bb-font", bb_font(base))}')
    else:
        body = f'<p class="muted">No diagrams yet.</p>{note}'
    n_comp = sum(len(dg["nodes"]) for _, dg, _ in loaded)
    return pane("architecture", "Architecture", f"{len(loaded)} projects · {n_comp} parts", body)
