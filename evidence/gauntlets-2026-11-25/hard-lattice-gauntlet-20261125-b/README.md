# Hard lattice gauntlet — 2026-11-25-b

Successful two-leaf live coding-crystal / lattice gauntlet. Two multi-file packages (integer `burst-limit`, string `voice-greeting`) were repaired on the free NIM trial, each sealed and promoted 3/3, then composed on held-out two-defect variants with no model calls.

## Headline

| item | result |
|---|---|
| Status | live composite admitted |
| Model | `nvidia/nemotron-3.5-super-vl-120b-a12b` (hosted NIM trial) |
| Leaf A (integer, burst-limit) | `coding-crystal:191dd9102ea2373933f777b1` — promoted, admitted, 3/3 |
| Leaf B (string, voice-greeting) | `coding-crystal:eb814eff3d78a76261e439e5` — promoted, admitted, 3/3 |
| Reuse A (quota-limit) | off 10/10 model calls vs on 0/0, crystal completed — pass |
| Reuse B (voice-salute) | off 9/9 model calls vs on 0/0, crystal completed — pass |
| 2-way composite | `coding-crystal:d6408abd53c27ec6a8a58507` — 3/3 held-out, `ADMIT` |

## Edges

- `COMPOSES_WITH` `{191dd9102ea2373933f777b1, eb814eff3d78a76261e439e5}` → `d6408abd53c27ec6a8a58507`
- `VERIFIED_BY` `d6408abd53c27ec6a8a58507` → `verifier:5e4592f604a1918cab21ad15`
- composite evidence root: `sha256:5fa4ae37ee40467821df89c51261d7592348a1d7a43e6c1449082c6c95dcd4ba`
- held-out variants (all passed): `tax-and-word`, `items-and-title`, `base-and-salute`

## Lattice / hashes

- lattice valid: `true`
- hypergraph valid: `true`
- tampered nodes: none
- leaves admitted: 2
- composites admitted: 1
- lattice ledger head: `sha256:0d58d59c32607eb3ee5e2a46f7f35a372907016c76b4259c045fac27c8c3fd24`
- crystal-chain head: `sha256:4da4f2b245b04ad8eeb3d6d0289e4481f967636a2ee6e1e00211ed268602bf74`

## Spend (as recorded in `report.json`)

- billed: `$0.00` (free NIM trial)
- prompt tokens: 69,867
- completion tokens: 1,777
- `estimated_usd`: 0.0

## Notes

Credential files (`trial-key.pem`, `residue_ed25519.pem`, and similar) and worktree copies over ~5 MB were excluded. See `SKIPPED.md`.
