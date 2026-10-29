# Product architecture imports

A product owns its real diagrams at `docs/diagrams/<name>.bower.json`.
Every crew stream gets an Architecture slot automatically. The small
`assets/architecture/registry.json` file is an optional non-stream allowlist.
`docs/diagrams/*.bower.json` selects the richest diagram by nodes, then edges.
The demo registry has no non-stream opt-ins; its static illustration is unchanged.

Sync imports only rich diagrams and writes `.cache/architecture-sync.json` with
source commit, content hash, node and edge counts, pending/imported status,
and a separate git/CI status overlay based on node ID or `meta.repos`.
It never rewrites product nodes or invents a placeholder. Render both HTML
views and update the diagram manifest before a newly imported diagram gets a
tab. Missing sources and unrendered diagrams remain pending with a verified
product draft PR link when available. A stream drops only when explicitly done
and every overlay node is complete at the current product head.
