# Physical Crystal Fabric — Delivery 9: Unified Adaptive Router (proposal-only)

**Source of truth:** IEI v0.9 §7.12 (Table 14 and Table 15) and §7.12.1 Unified Adaptive Router. PGEC §2.4 (Promotion
Sovereignty), §3.3 (similarity never confers authority), §4.3 (FRR redline).

**Goal:** a single `RouteDecision ∈ {crystal_replay, local_specialist_adapter, provider_fallback}`. Routing only
*selects a proposal route*. It never grants execution. D6 verifiers (held-out replay, capability ledger, reviewed
opcodes, verify command), hidden tests and policy decide.

## Survey (read-only, 2026-11-16)
| Site | Finding | Paper rule violated |
|---|---|---|
| `compute/adaptive_dispatcher.py` | Exact contract digest + 5 boundary fingerprints. Returns `local_specialist_adapter` or None. | OK as an *input* |
| `execution/execute.py` | Rewrites `ir.model` to the Ollama specialist and sets `adaptive_route_executed=True` | §7.12.1 / Table 14 "similarity never grants execution"; Table 15 "adapter cannot execute" |
| `compute/crystal_reuse_gateway.py::decide` | Semantic hit ≥ 0.82 → `reuse_*` action (answer served) | Table 15: < 0.95 must not replay. Verifier decides. |
| `compute/agent_scheduler.py` | `crystal_replay` lane is listed but the router is never called | — (gap) |

## Decision bands (Table 15)
| Similarity | Fingerprint compatible | Route | Who decides |
|---|---|---|---|
| ≥ 0.95 | yes, and a promoted D6 crystal is present | `crystal_replay` (zero-call proposal) | D6 activation gates and held-out-verified recipe, verify command. Stale fingerprints emit a demotion signal. |
| ≥ 0.95 | no | downgraded to the structural band | — |
| 0.80 – < 0.95 | — | `local_specialist_adapter` proposal, only if a boundary-checked local `ollama://` specialist exists; otherwise `provider_fallback` | Hidden tests and policy. The adapter cannot execute. |
| < 0.80 | — | `provider_fallback` | Action IR and full verification |

Every `RouteDecision` carries `proposal_only=True`, `execution_granted=False`, the `verifier` that must decide,
`envelope_digest` (the D5 source envelope of the crystal), fingerprints compared, reasons and a digest.

## D6/D5 fingerprints for coding crystals
- crystal side: `opcode_catalog_digest`, `crystal_digest` (stored record digest), `source_envelope_digest`.
- request side: the current `coding_catalog_digest()`, the record digest re-read through the tamper-checked registry,
  and the D5 envelope from the `EpisodeEnvelopeStore` for `source_run_id`. The envelope must validate and must have
  passed verification.
- If any key is missing or unequal, the crystal is not fingerprint compatible.

## Tasks
1. `app/kernel/compute/adaptive_router.py`: `RouteKind`, `RouteDecision`, `classify_band`, `AdaptiveRouter.route()`,
   `coding_crystal_fingerprints()`. Tests per band, fingerprint mismatch, and similarity-without-compat never
   executing.
2. Close the `execute.py` leak. The dispatcher output becomes a `RouteDecision` recorded at
   `ir.metadata["adaptive_route"]`. No model/provider rewrite, no `adaptive_route_executed`. Test: a ready specialist
   leaves `ir.model` and the provider untouched.
3. Subordinate `CrystalReuseGateway`. A semantic hit becomes a proposal (`execute_local_cpu` with
   `payload.semantic_proposal`) unless the injected `semantic_verifier(request, replay)` returns True. Exact durable
   replay and the KV payload checks are unchanged.
4. Wire the router behind `BEAST_ADAPTIVE_ROUTER=1` (default off):
   - Planner: `crystal_planner` activation is attempted only when the route is `crystal_replay`, and
     `agent.route.decision` is emitted.
   - `AgentScheduler.plan(route_decision=...)`: the `crystal_replay` lane is selected only from a `crystal_replay`
     RouteDecision when the flag is on. The legacy `crystal_match` keeps working when the flag is off.
5. Verification: 84 planner tests, D5/D6/D7 scoped tests, inversion suite, Ruff on new files, `git diff --check`.

## Claim boundary
The router lowers the number of paths that can reach execution. It does not prove savings (v0.9 Table 3, §9).
Specialist adapters are proposal-only and are not executed by any route in this delivery.
