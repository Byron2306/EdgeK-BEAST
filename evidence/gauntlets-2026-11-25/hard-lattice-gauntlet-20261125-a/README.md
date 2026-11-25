# Hard lattice gauntlet — 2026-11-25-a

First live attempt at the two-leaf coding-crystal gauntlet. Formation of leaf A (`burst-limit`) did not mutate or seal; the run was paused / `capture_not_proven`. No crystals were admitted. The successful rerun is `hard-lattice-gauntlet-20261125-b`.

## Headline

| item | result |
|---|---|
| Status | not proven (formation stopped) |
| Model | `nvidia/nemotron-3.5-super-vl-120b-a12b` (hosted NIM trial) |
| Leaf A | `capture_not_proven` (run `hard-lattice-leaf_a-347e748638c2`) |
| Leaves admitted | 0 |
| Composites admitted | 0 |

## Lattice / hashes

The empty lattice was valid but unused:

- lattice valid: `true`
- hypergraph valid: `true`
- tampered nodes: none
- lattice ledger head: `sha256:0000000000000000000000000000000000000000000000000000000000000000`
- crystal-chain head: `sha256:0000000000000000000000000000000000000000000000000000000000000000`

## Spend (as recorded in `report.json`)

- prompt tokens: 15,207
- completion tokens: 284
- `estimated_usd`: 0.003269 (this early report used list-price arithmetic; later runs record billed `$0.00` on the free trial plus a commercial-equivalent footnote)

## Notes

Credential files (`trial-key.pem` and similar) were excluded from this tracked copy. See `SKIPPED.md`.
