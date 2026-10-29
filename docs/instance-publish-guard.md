# Instance publish dirty-checkout guard

Private FlightDeck instances (for example a crew tracker) often keep a tracked
`data.json` as bootstrap state and rewrite it from hooks on every
`./publish.sh` / `./publish.sh --build`.

If the instance `publish.sh` refuses to run on a dirty checkout, that rewrite
self-blocks the next day-sync: the first build succeeds, then every later build
exits because `data.json` is dirty.

`crew-tracker.html` and `site/dist/` should stay gitignored. `data.json` usually
stays tracked.

## Recommended pattern

Restore known generated tracked files before the dirty check, and again after a
successful build. The guard still catches real local edits; day-sync can loop.

```bash
# data.json is tracked bootstrap state, but hooks rewrite it on every publish.
GENERATED_TRACKED=(data.json)

restore_generated_tracked() {
  local f
  for f in "${GENERATED_TRACKED[@]}"; do
    if git ls-files --error-unmatch -- "$f" >/dev/null 2>&1; then
      git checkout -- "$f"
    fi
  done
}

restore_generated_tracked

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "publish: checkout is dirty; commit or clear local changes before building or deploying" >&2
  exit 1
fi

# ... hooks, render, site/build.py ...

restore_generated_tracked
```

Do not hand-edit pane prose in `data.json`. If a pane is wrong, fix the hook
that writes it and publish again.
