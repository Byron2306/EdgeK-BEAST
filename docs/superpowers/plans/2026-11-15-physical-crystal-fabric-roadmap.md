# Physical Crystal Fabric Integration Roadmap (Deliveries 3-8)

> **For agentic workers:** This is the umbrella roadmap. Each delivery gets its own plan in `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-phaseN-*.md` and its own ledger in `.superpowers/sdd/`. Execute one delivery at a time, test-first, in the shared dirty workspace without commits.

**Goal:** Turn BEAST's existing but disconnected crystal machinery into one closed loop: an AgentRun produces an Episode Envelope, Sensorium extracts a candidate crystal, the candidate passes held-out replay and promotion, and a later AgentRun reuses it and does measurably less work.

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`

**Status of earlier deliveries:** Delivery 1 (signed endpoint reconciliation + topology contract) and Delivery 2 (descriptor-aware Docker and control-plane health) are complete; see the phase 1 and phase 2 ledgers.

## Global Constraints

- Commons stays `verify_only`; remote artifacts return as quarantined hypotheses and need node-local held-out reproduction before promotion.
- Crystals never carry ambient authority. Executable crystals hold reviewed opcode identifiers only, and every execution needs an expiring one-use local capability.
- Raw native KV state, memfd descriptors, raw prompts, secrets and unredacted workspace content never cross a node boundary.
- Every delivery is fail-closed and independently testable. Historical evidence never substitutes for a fresh live check.
- No host installs or privileged/system-level changes without an explicit operator decision. Scoped tests only, because a host-side `oqs` import triggers a native liboqs build.

## Current State Map

| Component | Where | What already works | How it connects (or doesn't) | Delivery |
|---|---|---|---|---|
| AgentRun | `app/kernel/agents/run_store.py`, `run_engine.py`, `routes/ide_routes/agent_runs.py` | Durable hash-chained event ledger, approvals, cancel, `ScriptedPlannerProvider` for deterministic runs | Mirrors events to Sensorium **metadata only** (`payload_included: False`), so nothing downstream can learn from the content. `merge_budget()` exists but is **never called**: no per-run token, turn, tool-call or wall-time accounting | 5 |
| Planner providers | `agents/planner_runtime.py`, `ollama_planner_provider.py`, `nim_planner_provider.py` | Ollama provider calls `CrystalReuseGateway.decide()` before the model, which gives prompt-level semantic-cache replay | Reuse happens at the prompt level only. Promoted typed crystals are never consulted when planning | 6 |
| Tool runtime / worktree forge | `agents/tool_runtime.py`, `worktree_tools.py`, `workspaces/worktree_forge.py` | Governed `worktree.bind/diff/replace_exact/write_file/verify/sourceplan_draft` | Tool calls are not represented as typed-IR opcodes, so a learned coding recipe cannot be replayed | 5, 6 |
| Verification / repair loop | `agents/verification_planner.py`, `verification_repair_loop.py` | Verification planning, repair budget | Results are not attached to an episode as postconditions or negative evidence | 5, 6 |
| Swarm lanes | `networking/swarm.py`, `agents/phase_e_learning.py` | Phase E `Scribe.compile_episode` / `Archivist` | Uses its own episode format, separate from AgentRun and Sensorium | 5 |
| Sensorium | `kernel/sensorium/runtime.py`, `episode_builder.py` | `crystallize_episode`, `replay_crystal`, `compile_candidate`, `replay_typed_crystal`, `promote_typed_crystal`, recurrence evaluate/execute | The whole pipeline exists, but only experiments call it (`sensorium_file_build_crystal_experiment.py`, `sensorium_port_crystal_experiment.py`). No production caller | 6 |
| Crystal IR / interpreter | `compute/runtime_crystallizer.py`, `typed_crystal_ir.py`, `typed_crystal_interpreter.py` | Reviewed opcode registry (14 opcodes: file, build, disk, socket, port lease, service health, repair branch) | No coding opcodes (worktree/verify/patch) | 6 |
| Held-out replay / promotion | `compute/heldout_replay.py`, `physical_crystal_lifecycle.py`, `crystal_autopromotion_daemon.py` | Gate needs at least 3 held-out successes with all passing; promotion registry, applicability proof, one-use execution authority, recurrence ledger | Only wired to experiments and a benchmark | 6 |
| Semantic reuse cache | `compute/crystal_reuse_gateway.py`, `local_semantic_cache.py` | Prompt replay with an eval gate (`no_secret_patterns`, length) | Separate from the physical/typed promotion registry, so there are two "crystal" notions with no shared identity | 6 |
| Context economizer | `app/context/economizer.py` | Shrinks oversized context before providers | Doesn't know about promoted crystals, which could replace context with a crystal reference | 6 |
| Compute forge / ForgeKV | `compute/compute_forge.py`, `forge_kv_*` (~40 modules) | KV registry, coordinator, publication, ML-KEM transport, level 6-8 gauntlets | `forge_kv_episode_bridge.py` is metadata-only and has no importers | 7 |
| Commons | `kernel/commons/*` | Signed nodes, lattice trust, reconciliation, fabric health, discovery supersession (D1-D2) | Doesn't yet receive or return crystal hypotheses from AgentRun promotion | 7 |
| Crystal Bus | `compute/crystal_bus.py` (310 lines) and `kernel/crystal_bus/` (fd_transport, capsule messages, sequence ledger) | SEQPACKET + SO_PEERCRED + SCM_RIGHTS, capsule codec/signing/verifier | Two parallel implementations; the spec calls for one consolidated bus | 4 |
| Socket Guardian | `execution/socket_guardian.py`, `socket_guardian_daemon.py`, `guardian_uvicorn.py`, `scripts/generate_socket_guardian_units.py` | Restart-safe listener custody, signed handoff receipts, ARDA/Metatron one-use operation capabilities, systemd socket units, `bin/beast gateway --socket-mode guardian` | **Never provisioned on this host**: no `~/.config/beast` roots, no ARDA guardian authority on 18401, no user units. BEAST 8101 runs in direct mode. Commons nodes run in Docker, where Guardian cannot hand descriptors across the container boundary under its peer-credential and process-lease checks | 3 |
| Topology | `.byron/services.yaml`, `.beast/remote-commons-lab/manifest.json`, `docker-compose.commons-lab.yml` | Phase 1 generates the Compose override from the lab manifest | Still two topology sources (gateway `services.yaml` and Commons lab manifest). The lab manifest lists 8121-8123 while the base Compose and live registry use 8111-8113 | 3 |
| IDE | `desktop-ide/renderer/js/pages/beast-commons-page.js` and others | Commons health, endpoint history, discovery (D2) | No topology, custody, compatibility or promotion views | 8 |

## Critical Path to the Closed Loop

The efficiency loop depends on **5 → 6** and needs nothing from 3, 4 or 7:

1. **D5 Episode Envelope**: one canonical, hash-bound envelope per AgentRun (and later swarm lanes, tools and providers). It carries the task family, ordered tool and verification steps with arguments digests, verified postconditions, failures as negative evidence, and the budget (model turns, tokens, tool calls, wall ms). This also wires the missing `merge_budget()` accounting.
2. **D6a Candidate extraction**: Sensorium turns a verified envelope into `CrystalIR`, then typed IR, using new reviewed coding opcodes (`worktree.inspect`, `worktree.replace_exact`, `worktree.verify`) that map to the existing governed tools. Failed envelopes become negative crystals.
3. **D6b Held-out replay and promotion**: replay the candidate on 3 or more held-out variants in disposable worktrees, then promote through `PhysicalCrystalPromotionRegistry` with an applicability proof.
4. **D6c Reuse**: before planning, the planner runtime asks the applicability gate. On a match it executes the promoted recipe through `TypedCrystalInterpreter` under a one-use capability, and the model only handles the residual. Reuse is recorded with `record_verified_reuse`, and a failed postcondition demotes the crystal.

D3 (Guardian) and D4 (Bus) harden local custody and transport. D7 publishes promoted crystals to Commons. D8 makes the whole thing visible. These follow the spec order but are **not** on the efficiency critical path.

## Delivery Plans (in spec order)

### Delivery 3: Live Socket Guardian ownership
- Plan: `2026-11-15-physical-crystal-fabric-phase3-guardian.md`.
- Exit: BEAST (and the local Commons gateway) serve from Guardian-owned listeners with signed lifecycle receipts, bound from one topology source, fail-closed on drift. Commons Docker nodes get signed custody evidence binding each published port to the node descriptor.
- Task 1 (topology contract) is complete. Tasks 2-4 are deferred until after D5/D6, with D3.1-D3.3 ruled.

### Delivery 4: Consolidated Crystal Bus
- Merge `app/kernel/compute/crystal_bus.py` and `app/kernel/crystal_bus/` behind one API (peer credentials, sequence ledger, capsule verify, one-use authority). Guardian already imports `peer_credentials` from the compute bus.
- Exit: one module, both test suites green (`tests/test_crystal_bus_capsule.py` plus the compute bus tests), custody receipts on every descriptor transfer.

### Delivery 5: Canonical Episode Envelope
- New `app/kernel/sensorium/episode_envelope.py` (contract plus builder from `AgentRunStore` events), budget accounting via `merge_budget()` from the planner runtime and tool runtime, and an adapter for the swarm `Scribe` episodes.
- Privacy: argument and result digests plus allow-listed structured fields only. No raw prompts or file contents, enforced by `SensorPrivacyGate`.
- Exit: every completed AgentRun yields exactly one verifiable envelope with non-zero budget counters, and envelopes are deterministic for scripted runs.

### Delivery 6: Extraction, negative evidence, held-out replay, promotion, reuse
- Coding opcodes in `typed_crystal_ir.py`, an extraction service `app/kernel/compute/agent_run_crystallizer.py`, replay in disposable worktrees (worktree forge), promotion via `physical_crystal_lifecycle.py`, a reuse hook in `planner_runtime.py`, and demotion on failed postconditions. Unify identity with `CrystalReuseGateway` so a prompt-replay hit and a typed-crystal hit share one promotion record.
- Exit: the end-to-end acceptance test below passes.

### Delivery 7: ForgeKV/Commons publication and local quarantine/reproduction
- **Retargeted (2026-11-15):** BEAST Commons, not HF. See the phase-7 plan: Space bundle, verify_only bucket revisions on nodes 8111-8113 via 8101, quarantined import, local reproduction, operator promotion, measured reduction receipts, and shadow-ledger credits (PGEC eq. 6; v0.9 §7.13).
- Publish promoted crystal manifests and portable chunks (never native KV) to Commons buckets. Remote hits come back `quarantined` and are promoted locally only after D6 held-out replay. Wire `forge_kv_episode_bridge.py` to D5 envelopes.
- Exit: crystal promoted on host A → published to commons-node-a → imported elsewhere as a quarantined hypothesis → locally reproduced → promoted. Verified against the live lab.

### Delivery 8: IDE observability
- Topology/custody (D3/D4), episode and budget (D5), candidate/replay/promotion/reuse with savings (D6), Commons publication state (D7). Smoke assertions per surface. No keys or pins rendered.

## End-to-End Acceptance Test (proves the loop)

`tests/test_crystal_fabric_closed_loop.py`, deterministic and offline (no LLM and no network), using `ScriptedPlannerProvider` and a temporary git fixture repo:

1. **Learn run.** Task family `fix-failing-assertion`: the fixture has a function with a wrong constant and a failing scoped test. A scripted planner explores (list/inspect files), runs the test, applies `worktree.replace_exact`, and re-verifies. Assert one Episode Envelope with a verified postcondition (test passes) and recorded budget `B1` (model turns, tool calls, tokens counted from scripted decisions, wall ms).
2. **Extract.** Sensorium extracts a candidate typed crystal (parameters: target file, symbol, expected/actual constant, test node id).
3. **Held-out replay.** Replay on 3 generated variants (different files, constants and test names) in disposable worktrees. All 3 must pass, then promote. A fourth variant whose precondition doesn't hold (no failing test) must be refused by the applicability gate.
4. **Reuse run.** A new instance of the same task family. The planner consults the gate, the interpreter executes the promoted recipe under a one-use capability, and the scripted planner is only asked for the residual. Assert the same verified outcome (test passes, diff digest equals the expected fix) and budget `B2`.
5. **Efficiency gate.** `B2.model_turns ≤ 0.5·B1.model_turns` **and** `B2.tool_calls ≤ 0.7·B1.tool_calls`, with tokens and wall ms reported. The test fails if reuse doesn't actually reduce work.
6. **Negative controls.** (a) A mutated fixture where the recipe's postcondition fails demotes the crystal and the run falls back to full planning. (b) A crystal never grants a tool outside its reviewed opcodes. (c) Reusing a consumed one-use capability is refused.

A live variant (`scripts/crystal_fabric_loop_benchmark.py`) repeats steps 1-5 against the real planner provider and reports measured savings. It is informational and not gating.

## Execution Order (operator ruling 2026-11-15)

1. Delivery 5, then Delivery 6: backend code and offline tests only. The finish line is `tests/test_crystal_fabric_closed_loop.py` passing with the scripted planner.
2. Delivery 3 (Guardian Tasks 2-4, decisions D3.1-D3.3 ruled), then Delivery 4, then Delivery 7.
3. **Last:** Delivery 8 IDE polish (all renderer/UI work) and live agentic-loop verification (real AgentRuns against real providers, `scripts/crystal_fabric_loop_benchmark.py`). Before that point, renderer changes are made only if the existing desktop smoke test breaks.

## Decisions Needed From the Operator

- **D3.1-D3.3:** ruled (host roots in `~/.config/beast` with ARDA, systemd user units, Docker custody records only). See the phase 3 ledger.
- **R1 (ordering):** ruled. See Execution Order.

## Alignment with the source papers (operator ruling 2026-11-15)
The papers win on any conflict; conflicts are logged in the phase-6/phase-7 ledgers.
- D5 = the PGEC runtime episode E = (S₀, T, C, M, A, G, V, S₁, R) (PGEC §2.3 eq. 1). The budget is R.
- D6 = experiential compilation K = (P, Θ, Gₖ, Q, Γ, 𝒱, 𝒜, Δ) (PGEC eq. 2). Reviewed opcodes are the authority
  envelope 𝒜 (eq. 3). Held-out replay is 𝒱 (eq. 4). Misfit refusal is eq. 5. Demotion is Δ. Promotion is a separate
  operator act (PGEC §2.4 Promotion Sovereignty). Reuse value is V_K (eq. 6), never "zero calls" by itself.
- D7 = the Verified Compute Commons (v0.9 §7.13): portable Spaces (§7.13.3), witness integrity (§7.13.2),
  credit reversal (§7.13.1), internal non-financial credits only (§7.13.3, §9).
- Metrics: false reuse is a redline (FRR, PGEC eq. 8). QPCCD (PGEC eq. 7; v0.9 §6.1, §7.6.4) is the economy signal.
  Estimated tokens are never realised savings (v0.9 Table 3, §9).
- D8 must render refusals and clawbacks as first-class outcomes (PGEC §6.3) and must not show credits as money.
