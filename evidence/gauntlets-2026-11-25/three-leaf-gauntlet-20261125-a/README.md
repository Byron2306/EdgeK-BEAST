# Three-leaf lattice gauntlet — 2026-11-25-a

Harder three-leaf live coding-crystal / lattice gauntlet. Fresh multi-file defect families (integer, string, boolean/branch) each sealed and promoted 3/3, reuse off/on passed for every leaf, a 3-way composite admitted on three-defect held-out variants with no model calls, and a nested composite of the earlier `d6408abd` edge plus the new boolean leaf.

## Headline

| item | result |
|---|---|
| Status | live 3-way and nested composites admitted |
| Model | `nvidia/nemotron-3.5-super-vl-120b-a12b` (hosted NIM trial) |
| Leaf int (retry-budget) | `coding-crystal:21c3949d1aeed9ddb1ecec1c` — promoted, admitted, 3/3 |
| Leaf str (error-prefix) | `coding-crystal:80da30d07663601262fa23bc` — promoted, admitted, 3/3 |
| Leaf bool (anonymous-access) | `coding-crystal:d1a2333153420620fb272839` — promoted, admitted, 3/3 |
| Reuse int (window-budget) | off 7/7 vs on 0/0 — pass |
| Reuse str (status-label) | off 11/11 vs on 0/0 — pass |
| Reuse bool (default-open) | off 7/7 vs on 0/0 — pass |
| 3-way composite | `coding-crystal:bab0e1056b3776569a69909a` — 3/3, `ADMIT` |
| Nested composite | `coding-crystal:ef42c64e5cde929000870a22` — 3/3, `ADMIT` |

## Edges

- `COMPOSES_WITH` `{21c3949d…, 80da30d0…, d1a23331…}` → `bab0e1056b3776569a69909a` (`fix-three-assertions`)
- `VERIFIED_BY` `bab0e105…` → `verifier:41c388f78c510e1aa6b7e8e1`
- 3-way evidence root: `sha256:e504dfe0ebc22cb53e748456acaf49f41970a7128b658fd21ffd15eb87e81c53`
- `COMPOSES_WITH` `{191dd910…, eb814eff…}` → `d6408abd53c27ec6a8a58507` (imported from the 2-leaf run)
- `VERIFIED_BY` `d6408abd…` → `verifier:5e4592f604a1918cab21ad15`
- `COMPOSES_WITH` `{d6408abd…, d1a23331…}` → `ef42c64e5cde929000870a22` (`fix-nested-assertions`)
- `VERIFIED_BY` `ef42c64e…` → `verifier:0cc2bfb36fb1f4048f2f33cf`
- nested evidence root: `sha256:c138f1a3e006a7ad44bc50c14721be59aa8d8beb13b2e22c91ec7282331fac4c`
- held-out variants (all passed, both composites): `retries-prefix-anon`, `window-status-open`, `ttl-label-guest`

## Lattice / hashes

- lattice valid: `true`
- hypergraph valid: `true`
- tampered nodes: none
- leaves admitted: 5 (3 new + 2 imported)
- composites admitted: 3
- lattice ledger head: `sha256:8c876044b1a194fb372013175782ef3f04d91e4621a2471cd3826127b4ee5515`
- crystal-chain head: `sha256:cc8ff26db9235b4910cbb0c2057019a74ca993baeed017f5e31d15ed8ae809fd`

## Spend (as recorded in `report.json`)

- billed: `$0.00` (free NIM trial)
- prompt tokens: 157,545 (includes an early integer-leaf spin that fixed tests but did not seal)
- completion tokens: 5,740
- `estimated_usd`: 0.0
- commercial-equivalent footnote: ~$0.0115 (public list prices $0.06 / $0.35 per 1M)
- 3-way and nested phases made 0 model calls

## Notes

Refactor-only tasks still will not form crystals: the extractor requires `failures_before_pass >= 1` around an exact replacement.

Credential files and worktree copies over ~5 MB were excluded. See `SKIPPED.md`.
