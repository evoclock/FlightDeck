# Product architecture imports

A product owns its real diagrams at `docs/diagrams/<name>.bower.json`.
An instance opts into Architecture tabs with `assets/architecture/registry.json`.
List a product repository by ID and a source under `docs/diagrams/`.
`docs/diagrams/*.bower.json` selects the richest diagram by nodes, then edges.
The demo registry has no opt-ins; its static illustration is unchanged.

Sync imports only rich diagrams and writes `.cache/architecture-sync.json` with
source commit, content hash, node and edge counts, missing/imported status,
and a separate git/CI status overlay based on node ID or `meta.repos`.
It never rewrites product nodes or invents a placeholder. Render both HTML
views and update the diagram manifest before a newly imported diagram gets a
tab. Missing sources and unrendered diagrams produce no tab.
