# Instance publish dirty-checkout guard

Private FlightDeck instances (for example a crew tracker) often keep a tracked
`data.json` as bootstrap state and rewrite it from hooks on every
`./publish.sh` / `./publish.sh --build`. Some also track generated architecture
imports, a registry, and rendered diagrams.

If the instance `publish.sh` refuses to run on a dirty checkout, those rewrites
self-block the next day-sync: the first build succeeds, then every later build
exits because generated files are dirty.

`crew-tracker.html` and `site/dist/` should stay gitignored. `data.json` usually
stays tracked.

## Recommended pattern

Restore known generated tracked files before the dirty check, and again after a
successful build. Also clear untracked diagram imports and rendered output
produced by hooks. These architecture paths are optional: instances that do not
track them have no tracked paths to restore. Use this pattern only where
`architecture/` contains generated overlays, not manually authored diagrams.
The guard still catches unrelated local edits; day-sync can loop.

```bash
# Generated bootstrap data and architecture overlays can change on each publish.
GENERATED_TRACKED=(data.json)

generated_tracked_paths() {
  local f
  for f in "${GENERATED_TRACKED[@]}"; do
    if git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
      printf '%s\n' "$f"
    fi
  done
  git ls-files -- 'architecture/*.bower.json' 'architecture/registry.json' 'architecture/rendered/**'
}

restore_generated_tracked() {
  local -a files=()
  local f
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    files+=("$f")
  done < <(generated_tracked_paths)
  if ((${#files[@]})); then
    git checkout -- "${files[@]}"
  fi
  # Remove only untracked hook outputs, not tracked or ignored files.
  while IFS= read -r f; do
    [[ -n "$f" ]] || continue
    rm -f -- "$f"
  done < <(git ls-files --others --exclude-standard -- 'architecture/*.bower.json' 'architecture/rendered/**')
}

restore_generated_tracked

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "publish: checkout is dirty; commit or clear local changes before building or deploying" >&2
  exit 1
fi

# ... hooks, render, site/build.py ...

restore_generated_tracked
```

An instance using `architecture/render_diagrams.mjs` may produce layout warnings.
The default is soft-fail: the renderer reports warnings but lets the publish
continue with the HTML it wrote. Set `CREW_DIAGRAM_STRICT=1` for fail-closed
local diagram authoring; warnings then stop the render. This setting does not
relax the dirty-checkout or current-tip guards. Do not copy a private instance's
`publish.sh` into FlightDeck or add generated product diagrams to the demo.

Do not hand-edit pane prose in `data.json`. If a pane is wrong, fix the hook
that writes it and publish again.
