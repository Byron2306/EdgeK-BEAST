# BEAST Extension Marketplace

BEAST plugin manifests describe extension behavior before an extension is installed or called.

Every manifest declares risk class, immutable SHA-256 tool-schema pins, permissions, token/cost/latency/call budgets, and explicit approval policy.

Use `beast_plugin_manifest_validate` with `prepare_hashes=true` to generate canonical pins and validate a draft. Installation is a governed write and requires `approved=true` with `dry_run=false`.

See [`beast-plugin.schema.json`](beast-plugin.schema.json) and the complete manifest under [`examples/`](examples/).
