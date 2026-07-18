# BEAST Compute Production Reachability Audit

Date: 2026-07-15

## Scope and meaning

This audit covers the 80 top-level Python modules under `app/kernel/compute`.
It builds a static import graph from production Python under `app/`, treats an
import from outside `app/kernel/compute` as a production root, and computes the
transitive closure through compute-internal imports. Tests, benchmarks,
documentation, registry strings, and internal scripts are not production
roots.

Static reachability is necessary but not sufficient. An imported class may
still never be instantiated or called. Dynamic plugin loading can also produce
false negatives and must be proven separately with runtime receipts.

## Result

- top-level compute modules: **80**;
- directly imported by production code outside the package: **41**;
- transitively reachable from a production import root: **51**;
- not statically production-reachable: **29**.

## Compute Governor finding

The primary inference path is real: provider adapters and the execution
orchestrator reach `app/kernel/execution/execute.py`, which calls the global
`InferenceComputeInterceptor`; that interceptor constructs `ComputeGovernor`
and invokes `build_plan`, `evaluate`, route selection, and receipt completion.

However:

- the default mode is `shadow`; no production configuration in this repository
  changes `BEAST_COMPUTE_GOVERNOR_MODE`;
- only requests passing through `Executor.execute` receive the complete gate;
- the streaming interceptor accepts a Governor but the production singleton
  constructs it without one and labels the integration “future”;
- Compute Forge performs direct local Ollama calls and is not routed through
  the Governor/interceptor accounting boundary;
- several direct gauntlet/provider probes call HTTP endpoints independently;
- the proof-local endpoint invokes one specific Governor gate, not the full
  inference plan/evaluate/complete lifecycle.

Therefore the Governor is wired, but not universal, and enforcement is off by
default.

## Critical stranded enforcement modules

These modules have tests but no production composition root:

| Module or cluster | Consequence |
|---|---|
| `governed_crystal_executor` | General crystal authorization/actuation boundary is test-only. |
| `typed_crystal_interpreter` + `physical_crystal_lifecycle` | The promoted physical recurrence path exists but no production owner constructs the interpreter, applicability gate, registry, authority ledger, and Sensorium together. |
| `distributed_forge_scheduler` + `forge_isolation` | Forge scheduling and its new isolation admission gate are not started by the app, MCP runtime, CLI runtime, or a supervised service. |
| `ablation_harness` + `displacement` | Scientific ablation and displacement economics are benchmark/test tools rather than mandatory promotion evidence. |
| `port_conflict_crystal` + `port_conflict_fixture` | The learned physical domain remains a test/fixture path rather than a production mission entrypoint. |
| `local_compute_cascade` + `memory_policy` | Local cascade and memory policy do not govern live inference routing. |
| `crystal_hypergraph` + `equivalence_engine` | Equivalence/hypergraph reasoning has no production consumer. |

## Offline/research cluster

The following unreachable modules are mostly gauntlets or evidence builders.
They should remain offline jobs, but need an explicit supervised job entrypoint
and artifact-ingestion boundary if their evidence is intended to affect
promotion:

- `cloud_disabled_replay_benchmark`;
- `crystal_autopromotion_daemon`;
- `crystal_evidence_bridge`;
- `crystal_materializer`;
- `crystal_promotion_evidence_sources`;
- `crystallized_compute_proof`;
- `definitive_crystal_lane_proof`;
- `earth_shattering_proof_gauntlet`;
- `final_boss_crystallization_gauntlet`;
- `full_spectrum_crystallization_gauntlet`;
- `hard_coding_crystallization_gauntlet`;
- `provider_tournament_gauntlet`;
- `sealed_capsule`;
- `unified_evidence_packet`.

`crystal_integration_acceptance`, `crystal_integrations`, and
`crystal_materializer` also require ownership review: compatibility shims and
test-only builders must not be mistaken for live integration.

## Forge finding

`ComputeForgeNode` is reachable only through compute-internal probes/proof
objects and manually launched scripts under `internal/`. The persistent runner
is not supervised by the main application. `DistributedForgeScheduler` had no
non-test importer before the isolation work, so node registration, leases,
restart recovery, and isolation admission could all pass tests without
governing a live forge task.

The isolation attestation now prevents unsupported scheduling inside the
scheduler, but it cannot protect production until the scheduler and runner are
owned by a service composition root.

## Required repair order

1. Create one `ComputePlane` composition root that owns Governor, interceptor,
   streaming interceptor, Forge scheduler, isolation verifier, physical-crystal
   registry/interpreter, evidence graph, and Sensorium adapters.
2. Route every provider/local/Forge inference attempt through a common
   `begin -> authorize -> execute -> verify -> complete` contract.
3. Make streaming interception consume the same gate rather than an optional
   unused Governor field.
4. Start Forge scheduler/runner through Guardian/systemd supervision and admit
   nodes only with current isolation attestations.
5. Make held-out ablation and displacement receipts mandatory inputs to
   promotion, not optional benchmark files.
6. Expose a read-only runtime reachability report showing constructed
   components, call counters, last receipt IDs, mode, bypass counters, and
   explicit offline-only modules.
7. Add an integration test that fails when an enforcement module is merely
   importable but absent from the production composition root.

No module should be called “wired” based only on an import, registry card,
string mention, unit test, benchmark, or generated artifact.

## 2026-07-15 production composition milestone

The seven repairs above now have an executable first production slice:

- `ComputePlane` is the sole composition root for the Governor, ledger and
  inference interceptor, governed streaming, strict Forge scheduler and
  systemd supervisor, isolation verifier, physical promotion/applicability/
  interpreter path, evidence graph, and Sensorium runtime.
- Compatibility imports of `compute_interceptor` and `compute_ledger` resolve
  to that plane; `Executor` and `app.main` no longer construct competing
  compute singletons.
- Provider and local routes already passing through `Executor` are recorded by
  the plane. Forge uses the same five-phase lifecycle. A governed streaming
  call now refuses to consume a provider stream unless given the gate produced
  for that exact inference attempt.
- Production Forge node registration is strict. The attestation must be
  digest-valid, fully isolated, and inside its wall-clock validity interval;
  heartbeat makes an expired node offline. The runner is launched only through
  a delegated, hardened `systemd-run --user` boundary and receives the exact
  verified attestation used for its Ollama authorization.
- Physical-crystal promotion in the production registry additionally requires
  independently identified, verified held-out ablation and measured
  displacement receipts. Merely having replay benchmark files is insufficient.
- `GET /edgek/compute/reachability` reports constructed components, lifecycle
  counters, last receipt IDs, Governor mode, bypass counters, active attempts,
  and modules explicitly classified as offline-only.
- `tests/test_compute_plane_integration.py` fails if a required enforcement
  component is absent or streaming is detached from the common Governor.

The focused regression boundary passes 60 tests. This establishes production
reachability and fail-closed composition; it is not yet the scientific claim
that a small model gained a capability. That next claim requires preregistered
tasks, blinded held-out variants, baseline/small-model/crystal-assisted arms,
negative controls, provider-disabled replay, repeated trials with confidence
intervals, and signed raw receipts from a second physical domain.

## Post-composition truth audit

The answer to “are all compute/crystallize/Forge modules now actually helping
production crystallized local compute?” is **no**.

After the ComputePlane and mission-isolation integration, static production
reachability finds 83 top-level compute modules: 56 are transitively reachable
from `app.main`, `Executor`, or `ComputePlane`, and 27 are not. Excluding the
package `__init__`, the reachability report now explicitly names all 26 offline
modules rather than presenting a short illustrative list.

Even 56 reachable modules does not mean 56 useful runtime participants:

- the Governor/interceptor/ledger, streaming gate, existing deterministic and
  reuse routes, Sensorium, Forge scheduler/isolation boundary, physical
  registry/interpreter, evidence graph, and mission-isolation proof boundary
  have production owners;
- physical replay and Forge execution are deliberately dormant until their
  appraisal/isolation preconditions exist;
- ablation, displacement, equivalence, hypergraph, materialization,
  autopromotion, provider tournaments, port-conflict fixtures, several proof
  gauntlets, and unified evidence packaging remain offline jobs or stranded
  enforcement paths;
- importing a class, exposing its type from the plane, or requiring its receipt
  at promotion does not prove that it contributes compute on a live request.

Therefore the next wiring milestone is not “put every module in the plane.” It
is to assign each module one auditable disposition: online enforcement,
supervised offline experiment whose signed receipt feeds promotion, or removed/
archived code. Scientific uplift remains unproven until the blinded small-model
experiment consumes those receipts and replicates on a second physical domain.

## Consolidation result and first measured uplift

The disposition milestone is implemented in
`app/kernel/compute/module_dispositions.py`. Every present module has exactly
one disposition and production reachability exposes the report. Two proven
duplicates were consolidated: the retired external-integration compatibility
registry was removed, and the Forge-only aggregate was renamed
`ForgeCreditLedger` so it can no longer be confused with the authoritative
SQLite `ComputeLedger`.

Offline scientific work now has a hardened systemd supervisor. Central Forge
promotion rejects historical counters without verified held-out ablation and
displacement receipts. The first receipt generated through this boundary used
local Ollama `qwen2.5:0.5b` and a parameterized SHA-256 residual crystal:

- 24 paired blinded held-out trials;
- model-only exact successes: 0;
- crystal-assisted exact successes: 24;
- two of two negative applicability cases refused;
- provider-disabled replay passed;
- provider calls avoided: 24;
- exact paired McNemar p-value: `1.1920928955078125e-07`.

This is strong evidence that the composed local system can perform an exact
bounded operation the small model could not perform alone. It does not show
that the model weights learned SHA-256, does not establish general cognitive
uplift, and is not cross-domain proof. A second physical host must independently
run and verify the receipt protocol before that replication claim exists.

The previously blocked four-controller destructive isolation proof is now
complete. Corrected systemd delegation propagates `io` through the user slice
and lazily activates it at the user-manager subtree through a real delegated
child request. A live mission applied kernel-read-back CPU, memory, swap, OOM,
PIDs, and block-device I/O limits and passed all fault and cleanup cases. The
full receipt is `docs/evidence/mission-isolation-io-live-2026-07-15.json` with
digest `sha256:bbd6822be24d72d411685b85834071d861d37fa2b8f7de2109a90c127b486afc`.
