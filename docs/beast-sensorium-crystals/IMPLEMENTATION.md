# BEAST Sensorium and Proof-Carrying Crystals Implementation

The normative phased implementation is sections 16–18 of the
[Sensorium and Proof-Carrying Compute Crystal Plan](../beast-sensorium-proof-carrying-crystal-plan.md).
It is part of, and does not supersede, the
[BEAST DevSecOps, ARDA, Commons, and Control Evidence Master Plan](../beast-devsecops-arda-commons-master-plan.md).

## Phase summary

1. S0: terminology, contracts, claim boundaries, and ADRs.
2. S1: read-only Sensorium spine.
3. S2: pidfd process identity and cgroup capsules.
4. S3: SocketIdentity and Port Lease Broker.
5. S4: credentialed Crystal Bus and sealed capsules.
6. S5: Runtime crystallizer and typed hypergraph.
7. S6: Port Conflict Repair end-to-end proof.
8. S7: equality-engine laboratory.
9. S8: advanced physical optimization.

## Completed phase: S0

Tasks:

- [x] Define artifact classes and maximum-authority ceilings.
- [x] Define versioned SensorEvent, RuntimeEpisode, ProcessLease,
  SocketIdentity, and ComputeCrystal contracts.
- [x] Use canonical hashing and make identity tampering detectable.
- [x] Register contract shapes with Canon.
- [x] Record the five S0 architectural decisions.
- [x] Label existing crystal-like artifacts through migration adapters.
- [x] Preserve neighboring Canon, lattice, capability, reuse, and runtime
  behavior while adding contract fixtures.

Success means no new executable crystal can omit authority, applicability,
verification/evidence, topology, economics, decay, and a content-bound digest.

## Completed phase: S1

Tasks:

- [x] Implement a thread-safe bounded event sequencer.
- [x] Emit explicit loss events when retained events are displaced.
- [x] Apply privacy classification and redaction before admission.
- [x] Build hash-stable RuntimeEpisodes from ordered mission events.
- [x] Keep filesystem export downstream and atomically written.
- [x] Provide a payload-free read model and read-only API surface.
- [x] Add BEAST-owned event adapters without privileged attachment.
- [x] Verify overflow, privacy, failure, episode, export, and regression paths.

Success means a governed local mission can produce an ordered, hash-stable
episode; overload and adapter failure are visible; raw sensitive material does
not enter the retained bus; and the read model exposes no actuator.

## Completed phase: S2

Tasks:

- [x] Collect content-bound process identity from `/proc` without serializing
  live pidfd integers.
- [x] Acquire and verify pidfd-backed ProcessLeases.
- [x] Monitor exits through an epoll constellation.
- [x] Signal only through pidfds and explicit authorization.
- [x] Discover cgroup v2 controllers and lifecycle controls read-only.
- [x] Implement authorized mission capsule create, attach, freeze, kill, and
  cleanup receipts.
- [x] Emit process/cgroup lifecycle observations into the Sensorium.
- [x] Expose a read-only process/cgroup capability state.
- [x] Verify owned subprocess exit, tampering, authorization, and regressions.

Success means PID reuse cannot bind a new task to an old lease, ordinary state
inspection performs no cgroup mutation, signals target the held pidfd, and
freeze/kill operations fail closed without action-specific authorization.

The existing-process `cgroup.procs` attachment boundary verifies identity on
both sides of the write and fails on drift. Direct process birth into a cgroup
with `clone3(CLONE_INTO_CGROUP)` remains explicit later hardening.

### Milestone 7 destructive-retirement extension — in progress

- [x] Revalidate content-bound process identity immediately before every
  authorized pidfd signal.
- [x] Bind executable, cgroup, namespaces, owner scope, workspace, registry,
  service, and listener generation into the retirement request digest.
- [x] Require exact destructive operator approval, current ARDA appraisal,
  and a separately scoped durable one-use retirement capability.
- [x] Gracefully terminate through the held pidfd and emit a sealed outcome
  requiring exit, listener retirement, replacement identity/health, and no
  governed orphan descendants.
- [x] Refuse on timeout rather than implicitly escalating to `cgroup.kill`.
- [x] Replace listener retirement, rebind, generation, and health callbacks
  with kernel TCP probes plus live Guardian and ServiceRegistry integration.
- [x] Refuse a real child-retained-listener race and roll back an unhealthy
  Guardian replacement without leaving an active lease.
- [x] Snapshot governed descendant ProcessLeases before retirement and require
  their content-bound absence afterward.
- [x] Require a distinct exact operator approval, ARDA appraisal, and durable
  one-use capability for cgroup kill; revalidate exact membership twice and
  require `populated 0` confirmation.
- [x] Refuse last-moment identity drift/PID-reuse substitution, exited tasks,
  and ambiguous owners before pidfd actuation.
- [x] Verify signed Ed25519 operator decisions and complete signed ARDA
  appraisals over the exact destructive request and policy bindings.

## Current phase: Milestone 8 delegated isolation — started

- [x] Add a read-only delegation/namespace readiness report that cannot claim
  full isolation when race-free `clone3(CLONE_INTO_CGROUP)` is unavailable.
- [x] Apply and read back CPU, memory, PID, and I/O capsule limits under exact
  configure authority.
- [ ] Create a real delegated mission subtree and enable only granted parent
  controllers.
- [x] Resolve the effective systemd cgroup scope and refuse controller
  enablement on a populated domain parent without mutation.
- [x] Enable reviewed controllers and create a capsule on an empty delegated
  parent with readback evidence.
- [x] Establish and prove distinct user/mount/PID/network namespaces, private
  `/proc`, and absence of non-loopback routes for an authorized live worker.
- [ ] Obtain or launch under an empty real delegated systemd parent with all
  required CPU/memory/PID/I/O controllers.
- [ ] Birth workers directly into that subtree and
  namespaces, and prove containment, pressure, OOM, timeout, rollback, and
  cleanup with kernel observations.
- [x] Add a reviewed inherited-descriptor-only native
  `clone3(CLONE_INTO_CGROUP)` launcher with a pre-exec membership gate.
- [x] Prove live placement in a distinct child cgroup, observe `populated 0`,
  and remove the empty child afterward.
- [ ] Combine race-free cgroup birth and namespace establishment in the same
  worker, then prove resource enforcement and failure cleanup.
- [x] Combine race-free child placement, user mapping, mount/PID/network
  namespaces, PID 1, private `/proc`, and loopback-only networking in one live
  worker lineage.
- [x] Establish a private tmpfs root, prove selected host secret paths absent,
  and confirm proc/root/mountpoint cleanup.
- [x] Turn a transient `systemd --user` `Delegate=yes` service into an empty
  delegation root by moving its positively identified anchor to a leaf; enable
  CPU/memory/PID controllers and retain an explicit missing-I/O downgrade.
- [x] Move the exact transient anchor into a leaf, verify successor identity,
  enable controllers through the intermediate slice, and enforce/read back
  live CPU, memory, and PID limits.
- [x] Run the combined isolated worker under those limits, observe pressure and
  `populated 0`, and remove the mission capsule.
- [x] Bind isolation attestations into Compute Forge node profiles and prevent
  the distributed scheduler from assigning isolation/controller requirements
  the node cannot prove.
- [ ] Exercise actual CPU throttling, memory OOM, PID exhaustion, timeout,
  freeze, bus-peer death, and rollback outcomes; obtain system-level I/O
  delegation for an `io.max` enforcement claim.

## Current phase: S12 — completed

S0–S12 are implemented. The previously stale phase list has been reconciled
with `PROGRESS.md`; S3–S12 are not future work.

## Production composition root — completed

- [x] One `ComputePlane` owns Sensorium ingestion/closure, generalization,
  compilation, replay, promotion, applicability, authority, typed execution,
  evidence, Forge scheduling, and isolation admission.
- [x] Persist signed appraisals, promoted typed artifacts, lifecycle state,
  evidence, and consumed one-use capabilities beneath the plane state root.
- [x] Mount `POST /edgek/compute/missions` in the real FastAPI application.
- [x] Provide a standalone HTTP CLI mission submitter.
- [x] Prove restart loading and fail-closed selection of exactly one active,
  appraised artifact matching the requested task family.
- [x] Run a live CLI -> uvicorn -> composition root -> physical file/build
  recurrence -> HTTP response demonstration with complete phase counters.

Next physical domain: disk-pressure diagnosis and governed cleanup. It must use
delegated destructive isolation, mount/quota identities, protected-path
negatives, bounded deletion manifests, safe refusal, and cleanup/rollback
receipts. Net displacement accounting remains a separate subsequent gate.

### Disk-pressure candidate and runtime-independence update

- [x] Implement device/inode/size/mtime/content-bound cleanup manifests.
- [x] Refuse root/home scopes, protected paths, traversal, symlinks,
  hardlinks, cross-device targets, stale manifests, and identity drift.
- [x] Enforce file/byte limits and a separate high-volume approval class.
- [x] Quarantine before purge and restore exact files on pre-purge failure.
- [x] Learn a three-parameter typed candidate from natural positive and
  refusal episodes; pass five structured held-out variants.
- [x] Birth the fixed-purpose destructive cleanup worker directly into the
  delegated cgroup plus mount/PID/network namespace capsule with descriptor-only
  manifest/workspace access, all four controllers, no ambient network, no host
  secrets, `populated 0`, no orphans, and confirmed cleanup.
- [ ] Route ordinary ComputePlane disk missions through the supervised native
  runner; production promotion stays fail-closed until this product path binds
  applicability, one-use authority, isolation, execution, and displacement.
- [x] Build and identity-bind a separate official llama.cpp CPU runtime.
- [x] Repeat the same sealed uplift task set across Ollama and llama.cpp with
  exact shared GGUF and Crystal digests.
- [x] Pass all independent-runtime, provider-absent replay, and negative-control
  gates with complete attempt retention.

## S13 hardening — in progress

- [x] Route damping decays on read as well as on event recording.
- [x] Socket reconciliation prefers content-bound identity/topology keys over
  port-only lookup.
- [x] Crystal Bus uses AF_UNIX `SOCK_SEQPACKET` and supports `SCM_RIGHTS`.
- [x] Capsules inspect memfd seals and carry authority references/signatures.
- [x] Control Evidence Graph supports append-only persistence and replay.
- [x] RC4 visual audit navigates the real router; prior Studio-only captures
  were invalidated.
- [x] One-use signed capability consumption and a bounded socket-probe actuator
  are implemented and covered by focused tests.
- [x] A user-mode Socket Guardian retains sockets across broker/IDE/gateway
  process restarts and performs signed `SCM_RIGHTS` recovery after peer UID and
  ProcessLease validation.
- [x] Listener generations, lifecycle transitions, health, workspace,
  capability, appraisal, policy, and registry bindings are durable and
  reconciled.
- [x] Sensorium has a hash-chained SQLite journal with restart replay and
  fail-closed integrity checks.
- [x] Enterprise Commons operations emit payload-safe Sensorium observations
  and Control Evidence Graph nodes.
- [x] Guardian mutations can require exact signed one-use operation
  capabilities, atomically consumed from a durable ledger.
- [x] Externally retained listeners can be adopted from named systemd
  descriptors; Guardian replacement increments the durable listener generation
  without releasing the supervisor-owned port.
- [x] A fail-closed Guardian daemon/config loader and generated user-systemd
  units are implemented and unit-file validated.
- [x] BEAST and a path-restricted Commons service recover the exact signed
  Guardian descriptor and run Uvicorn without a second bind.
- [x] A different Uvicorn PID can restart on the same retained lease, port, and
  generation; readiness/shutdown update Guardian health state.
- [x] Consumer units use private systemd credentials for authority bearer
  material and durably persist signed handoff receipts.

## Claim boundary (release audit)

Implemented and tested: ordered Sensorium contracts, process/socket identity
adapters, PSI governance, route damping, topology-aware reconciliation,
credentialed local transport, sealed capsule inspection, signed capability
consumption, bounded port repair, append-only evidence reconstruction,
cross-process broker restart recovery, durable listener generations/lifecycle,
signed socket handoff receipts, durable Sensorium replay, and Commons evidence
integration.

Contract/skeleton only: generalized causal inference, equality saturation,
full VRF/network attribution, and host-provisioned production ARDA/Metatron
appraisal endpoints. The protected live builder now requires signed decisions,
one-use capabilities, appraisals, trust keys, and a durable ledger, but this
repository test run does not claim those external services are provisioned.
The runtime crystallizer now retains topology, resource
envelope, and negative-condition fields, but does not claim causal inference or
automatic promotion. The governed executor reports physical execution only
when an explicit actuator and postcondition verifier are provided.

Broker and service-process restart continuity are implemented. Guardian
replacement continuity is implemented and tested with an external descriptor
owner. Host-local provisioning, signed ARDA operation issuance, installed unit
activation, consumer replacement, and Guardian replacement are now live-tested.
The reboot-continuity protocol is implemented and test-armed: signed pre-boot
state, boot-ID-bound applicability proofs, fresh post-boot TPM/ARDA binding,
rollback detection, and recurrence verification are enforced. The live reboot
exit remains unclaimed until a fresh current-boot quote is collected and the
two physical phases complete. Managed production key custody also remains
unclaimed.

Second-domain generality is now implemented and live-proven for a deterministic
file/build repair. Natural Sensorium episodes generalize into the same typed
IR, replay, promotion, applicability, one-use authority, interpreter, and
ComputePlane lifecycle used by the port crystal. Workspace-root digest binding,
byte-exact output verification, malformed/schema refusal, and post-write
rollback are enforced. Provider-agnostic multi-adapter evaluation and paired
net displacement remain later milestones.

Live: the RC4 static/smoke checks and router navigation audit. Simulated or
fixture-bound: provider mutation probes, privileged kernel/BPF integrations,
and real destructive port takeover. See the S13 manifest for the reproducible
test command and dependency boundary.

## Enriched kernel control plane

The newly integrated kernel modules now include production-oriented contract
validation and observability rather than only happy-path scaffolding:

- workspace identities validate UUID and Git object bindings and require exact
  digest equality before cache reuse;
- inherited `.byron` manifests merge project, service, tool, workload, policy,
  and exclusion declarations;
- the service registry rejects duplicate ports/hosts and upstream mismatches;
- tool exposure records risk, approval, failed-tool suppression, and hidden
  schema counts;
- the resource executor uses per-lane bulkheads and exposes submitted,
  completed, and in-flight metrics;
- interference decisions validate pressure ranges and identify the dominant
  pressure/lane;
- one-use capability consumption can persist across process restarts;
- ARDA appraisal contracts bind authority, policy generation, audience, state,
  and expiry;
- equality groups reject duplicate/invalid alternatives and expose summaries;
- causal edges are de-duplicated and never create self-causation;
- rollback orchestration records and compensates apply/verification exceptions;
- network attribution validates typed socket/process identities before hashing.
- the Socket Guardian persists generations and state transitions atomically,
  validates peer identity, signs handoff receipts, and revokes registry drift;
- the Sensorium journal restores ordered sanitized events and refuses replay
  after hash-chain or contract fracture;
- Commons manifest replay revalidates content identity and signatures, while
  artifact/job/route/Space operations project into both Sensorium and the
  Control Evidence Graph.

S13 acceptance requires focused tests plus live Electron interaction checks;
route existence alone is not sufficient.

## Enterprise Commons control plane closure

- [x] `.byron/services.yaml` is the BEAST/Commons/ARDA/Seraph service and port
  source of truth; VAMP and Hivenance are outside this release scope.
- [x] CLI, Electron, renderer, generated hosts, and NGINX config converge on
  the BEAST `127.0.0.1:8101` upstream.
- [x] The active workspace identity is propagated by the desktop runtime and
  audited/enforced on Commons and control-plane mutations.
- [x] CapabilityPlane provides phase/risk-aware lazy bucket exposure.
- [x] ResourceExecutor provides bounded lane admission, rejection metrics,
  process-capable CPU isolation, exclusive keys, and a fail-closed hazardous
  sandbox contract.
- [x] Commons has persistent registry, vault, chunk, dataset, job, route, and
  Space composition surfaces.
- [x] Enterprise artifact/Space admission requires real Ed25519 verification;
  ARDA Space appraisal is signed and bound to the exact canonical request.
- [x] Missing trust/appraisal configuration is reported as
  `configuration_required` and denies admission.

The deployment and claim boundary is documented in
`docs/beast-commons-enterprise-control-plane.md`.
# Production hostile-mission enforcement (2026-07-15)

`ComputePlane.execute_user_mission` now publishes execution latency, joined
node-receipt identities, and a provider-call counter witness. A configured,
explicitly requested provider fallback uses the same five-phase lifecycle and
records a separate evidence node; absent configuration or opt-in, no-match is
refused. `tests/test_production_crystal_hostile_matrix.py` exercises the full
failure, drift, ambiguity, recurrence, and fallback matrix against the HTTP
product boundary and production-owned runtime objects.
