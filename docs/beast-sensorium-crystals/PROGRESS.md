# BEAST Sensorium and Proof-Carrying Crystals Progress

## Status: Phase S13 hardening — in progress (S0–S12 completed)

## Quick reference

- Research: `docs/beast-sensorium-crystals/RESEARCH.md`
- Implementation: `docs/beast-sensorium-crystals/IMPLEMENTATION.md`
- Umbrella roadmap: `docs/beast-devsecops-arda-commons-master-plan.md`
- Detailed companion: `docs/beast-sensorium-proof-carrying-crystal-plan.md`

## Phase progress

### S0: Terminology, contracts, and claim boundaries

Completed:

- Artifact class and maximum-authority taxonomy.
- Versioned contracts for SensorEvent, RuntimeEpisode, ProcessLease,
  SocketIdentity, and ComputeCrystal.
- Content-bound process, socket, event, episode, and crystal identities.
- Canon catalog entries and focused contract tests.
- Five recorded Sensorium/crystal architecture decisions.
- Non-mutating migration descriptors for existing crystal-like artifacts.
- Focused and neighboring regression suites passed.

Next:

- Roadmap foundation complete; continue with production integration hardening.

Decisions:

- Contracts are frozen dataclasses matching existing BEAST conventions.
- Deep invariants live in contract validators; Canon provides baseline shape
  validation and discovery.
- A true maximum-authority check is only a ceiling check, never an execution
  grant.
- pidfd integers are explicitly excluded from serialized ProcessLease identity.
- Compute Crystal v1 execution graphs are finite DAGs.

## Session log

### 2026-07-15 — Milestone 1 causal-episode foundation

- Added an optional, validated `physical_effect` envelope for SensorEvents.
  It records typed operation, phase, subject, result, resource relations,
  descriptor identities, branch selection, explicit causes, and state
  transitions without carrying live descriptors or granting authority.
- RuntimeEpisode graphs now distinguish sequencer order from causality.
  `ordered_edges` are retained separately; `causal_edges` require explicit
  cause, producer/consumer resource evidence, or a verified state transition.
  The legacy `edges` field remains an explicitly order-only compatibility
  alias.
- Added payload-safe `event_facts` projections so an auditor can reconstruct
  operations, decisions, refusals, and verification branches from a sealed
  episode without retaining arbitrary event payloads.
- Wired socket reconciliation and durable Socket Guardian lease transitions
  into the stronger physical-effect contract.
- Added negative contract tests, a temporal-adjacency non-causality test, and
  an episode reconstruction test. The 35-test focused and neighboring
  Sensorium/socket regression family passes.

Claim boundary: this establishes honest causal episode evidence. It does not
yet infer parameters, generalize Crystal IR, or automate promotion.

### 2026-07-15 — Milestone 2 bounded candidate generalization

- Added a strict `CrystalGeneralizer` over sealed RuntimeEpisode families.
  Candidate formation requires at least three naturally closed successful
  episodes, one shared operation/phase signature, and one identical
  evidence-backed causal topology.
- Added structural template alignment, invariant retention, resource-envelope
  maxima, verification-derived postconditions, and deterministic family
  hashing independent of episode input order.
- Added allowlisted parameter inference for correlated requested-port and
  workspace values. Arbitrary varying strings fail closed. Varying live
  descriptor identities become reviewed descriptor-class requirements and are
  never exposed as caller-controlled parameters.
- Failed, denied, refused, and rolled-back episodes now contribute explicit
  negative outcome, branch, and effect conditions to the candidate.
- Added `SensoriumRuntime.generalize_episodes` so candidates are produced from
  closed retained episodes rather than caller-supplied trace dictionaries.
- Added adversarial coverage for insufficient natural evidence, arbitrary
  causal-identity variation, causal-topology mismatch, descriptor-class
  constraints, negative-condition capture, tamper rejection, and deterministic
  output. The 46-test focused and neighboring regression family passes.

Claim boundary: repeated typed episodes can now produce a bounded candidate
without caller-supplied parameter names. This does not yet prove isolated
physical replay, promotion, or recurrence-time applicability.

### 2026-07-15 — Milestone 3 canonical typed opcode IR

- Added a reviewed `OpcodeRegistry`. Each opcode declares its version, phase,
  authority ceiling, local handler identifier, input/output schemas, allowed
  parameters, descriptor requirements, resource limits, independent verifier,
  refusal behavior, and rollback behavior for bounded effects.
- Added a `TypedCrystalCompiler` that compiles generalized step templates only
  when every operation is registered and every parameter and descriptor class
  stays within the reviewed opcode contract. Unknown operations, arbitrary
  handler substitution, missing descriptor evidence, and bounded effects
  without a capability lease fail closed.
- Added content-bound `ExecutableCrystalIR` with an acyclic execution graph,
  explicit sequence and causal edges, maximum-authority derivation, opcode
  catalog binding, negative conditions, resource envelope, and no serialized
  code or callables.
- Integrated typed compilation through `SensoriumRuntime.compile_candidate`.
- Added materialization into the existing canonical `ComputeCrystal` proof
  envelope, preserving its applicability, authority, evidence, economics,
  decay, signer, and artifact-digest requirements rather than introducing an
  unrelated execution artifact.
- Added adversarial tests for unknown opcodes, catalog drift, handler
  substitution, authority tampering, cyclic graphs, duplicate registration,
  missing rollback, and missing capability leases. The 51-test focused and
  neighboring regression family passes.

Claim boundary: learned candidates now compile into declarative, reviewed,
proof-carrying programs. Handler identifiers are not yet interpreted by an
isolated replay engine, and compilation does not grant promotion or execution.

### 2026-07-15 — Milestone 4 structured isolated replay laboratory

- Added data-only `ReplayVariant` contracts and structured node, variant, and
  laboratory receipts. Variants declare exact parameters, descriptor classes,
  initial state, expected effects, negative boundaries, unrelated-state
  sentinels, and optional fault injection; they do not supply execution
  callbacks.
- Added a local `ReplayHandlerRegistry` that resolves only the handler,
  verifier, and rollback identifiers already sealed into the reviewed opcode
  catalog. Missing implementations fail before replay.
- Added private per-variant filesystem roots, deep-copied state, parameter and
  descriptor validation, node-level CPU/wall accounting, independent verifier
  results, reviewed rollback, unrelated-state invariants, evidence digests,
  and a content-bound laboratory evidence root.
- Negative variants pass only through the expected safe-refusal branch. Their
  receipts produce `SAFE_REFUSAL_UNDER` applicability boundaries; unexpected
  failures produce `FAILED_UNDER` boundaries and block promotion eligibility.
- Preserved structured evidence through the existing `ReplayReceipt` bridge
  and added candidate narrowing from laboratory receipts.
- Integrated replay through `SensoriumRuntime.replay_typed_crystal`, which
  accepts typed variants rather than caller-provided replay functions.
- Proved the read-only physical path against a real subprocess listener using
  `/proc/net/tcp`, socket-inode ownership correlation, and an independent live
  loopback health probe. Also covered successful held-out variants, unknown-
  owner refusal, missing inputs/handlers, injected failure, and reviewed
  rollback. The 60-test focused and neighboring regression family passes.

Claim boundary: replay now has genuine structured evidence and a real physical
read-only fixture, but isolation is currently a private filesystem/state
boundary. The receipt explicitly reports that process/network namespaces and a
delegated cgroup capsule were not established. Destructive takeover, full
namespace isolation, and automatic promotion remain unclaimed.

### 2026-07-15 — Milestone 5 promotion and recurrence applicability

- Added a single `PhysicalCrystalPromotionRegistry` for typed physical
  crystals. Promotion requires the exact typed artifact digest, a fully
  successful structured replay receipt and evidence root, an exact current
  appraisal, explicit approver and approval receipt, policy generation, and a
  bounded expiry. Boolean replay summaries cannot promote through this path.
- Promotion, degradation, demotion, revocation, and expiry use a constrained
  state machine. Records and transition reasons are content-bound and can be
  atomically persisted and integrity-checked on reload.
- Added `RecurrenceContext`, short-lived `ApplicabilityProof`, and a fail-closed
  `PhysicalApplicabilityGate`. It revalidates parameters, ProcessLeases,
  SocketIdentities, Port Leases, workspace, registry, policy, appraisal,
  descriptor requirements, opcode catalog, promoted artifact digest, and
  learned negative conditions on every recurrence.
- Bound `requested_port` to the freshly validated SocketIdentity or Port Lease
  instead of merely requiring an unrelated descriptor to be present.
- Kept matching separate from authority. Applicability produces a content-
  bound monotonic-expiry proof; a later authorization step atomically consumes
  a signed one-use capability against that exact proof request digest, policy,
  audience, and appraisal. Reuse of the capability fails.
- Integrated promotion and recurrence decisions through
  `SensoriumRuntime.promote_typed_crystal` and
  `SensoriumRuntime.evaluate_crystal_recurrence`.
- Added adversarial coverage for unbound appraisal, failed replay, duplicate
  promotion, policy rotation, negative-condition hits, stale process/socket
  identity, parameter-to-port mismatch, appraisal drift, proof expiry,
  capability reuse, demotion, and durable reload. The 74-test focused and
  neighboring regression family passes.

Claim boundary: BEAST can now promote a typed physical crystal and prove that
fresh recurrence conditions match without granting execution implicitly. The
one-use authorization is consumed and evidenced, but the next milestone must
bind that receipt into the typed interpreter and prove the full local
recurrence executes and verifies without a provider call.

### 2026-07-15 — Milestone 6 verified local recurrence

- Added an authorization-bound `TypedCrystalInterpreter`. It accepts only a
  validated promoted typed artifact, an unexpired applicability proof, and a
  content-bound receipt proving that the exact one-use execution capability
  was consumed for that proof request digest.
- The interpreter immediately reruns the physical applicability gate before
  the first handler and compares process, socket, port-lease, workspace,
  registry, policy, appraisal, promotion, parameter, and negative-condition
  bindings. Drift aborts before any opcode handler executes.
- Execution resolves only reviewed local handler, verifier, and rollback keys;
  enforces per-node CPU/wall envelopes; records node effects and independent
  verification; evaluates typed postconditions; and reruns physical
  applicability after execution.
- Added a content-bound `TypedCrystalExecutionReceipt` and Control Evidence
  Graph node linking the promoted artifact, applicability proof,
  authorization receipt, node evidence, postconditions, physical
  revalidation, rollback state, and provider-call witness.
- Proved a later, previously unseen real loopback listener recurrence. BEAST
  collected a fresh pidfd-compatible ProcessLease and content-bound
  SocketIdentity, matched the promoted crystal, consumed one-use authority,
  inventoried `/proc/net/tcp`, correlated the socket inode to the live owner,
  selected local healthy-service reuse, verified health over TCP, revalidated
  the physical state, and completed with zero provider calls.
- Added hostile coverage for post-authorization process drift, tampered
  authorization and execution receipts, and a provider call occurring inside
  an otherwise successful handler path. Each blocks the verified local-
  displacement claim.
- The 82-test focused and neighboring family passes. The known order-dependent
  streaming-provider circuit-breaker test also passes in isolation, for 83
  passing selected checks; when appended to the shared-state combined process
  it remains the sole unrelated failure.

Claim boundary: the complete learn -> type -> replay -> promote -> match ->
authorize -> execute -> verify -> evidence chain is now demonstrated for the
safe healthy-service-reuse branch of the Port Conflict Repair domain. Unknown
owners still refuse safely. Destructive stale-process retirement, delegated
namespace/cgroup isolation, workstation-reboot continuity, and generalization
to a second physical domain remain unclaimed.

## Continuation roadmap — physical closure, displacement, then Commons

Milestone 6 is the first complete local recurrence proof, not the end of the
Sensorium/crystal program. The remaining work is ordered as follows; later
layers may consume evidence from earlier layers but may not waive their exit
criteria.

### Milestone 7: authorized stale-process retirement

Status: complete for the host-process boundary. The destructive branch is implemented in
`StaleProcessRetirementCoordinator`: it binds the current ProcessLease,
executable, cgroup, PID/mount namespaces, owner scope, workspace, service,
registry digest, listener generation, policy, and appraisal into one request
digest. Exact destructive operator approval, a current ARDA appraisal, and a
separately scoped durable one-use capability are all required before graceful
pidfd-only `SIGTERM`. Process identity is re-collected immediately before the
pidfd signal. The resulting sealed receipt requires observed graceful exit,
listener retirement, absence of governed orphan descendants, replacement
listener identity, and replacement health. A timeout refuses and explicitly
does not acquire implicit `cgroup.kill` authority.

The live tests prove the positive BEAST-owned branch and pre-effect refusal for
an unknown owner scope, including durable capability consumption. The
`GuardianStaleListenerBoundary` now replaces the listener/rebind/health
fixtures with kernel TCP probes, the authoritative ServiceRegistry, and the
live Socket Guardian. Guardian replacement explicitly imports the retired
listener generation as a predecessor and must issue generation `N+1` or
greater. A real subprocess listener is retired and replaced on the same port;
the unhealthy lane releases the replacement, and a forked child retaining the
old descriptor prevents rebind even after the authorized parent exits.

Last-moment identity drift/PID-reuse substitution and already-exited process
paths refuse before pidfd signaling, while signed Ed25519 operator decisions
and full signed ARDA appraisals now bind the exact destructive request, policy,
audience, appraisal, and authority. Governed
descendant inspection now snapshots content-bound descendant ProcessLeases
before signaling and proves each is absent afterward. Separately authorized
cgroup escalation is implemented under a distinct `beast.cgroup.kill`
authority and audience: it binds the retirement request, capsule path, exact
member PIDs, policy, and appraisal; revalidates membership both before
consumption and immediately before the control write; and requires observed
`populated 0` before issuing a verified receipt. Real delegated-cgroup and
post-kill listener/replacement integration remain part of Milestone 8. This
closure does not claim delegated isolation or race-free worker birth.

- prove positive ownership using current ProcessLease, executable, cgroup,
  namespace, workspace, service-registry, and listener-generation bindings;
- revalidate immediately before signaling and use pidfd signaling only;
- attempt graceful shutdown before any destructive cgroup operation;
- require separately scoped operator, ARDA, and one-use destructive authority;
- prove unrelated processes and descriptors remain unchanged;
- verify listener retirement, replacement listener identity, service health,
  registry reconciliation, and absence of governed orphan descendants;
- exercise process-exit, PID-reuse, child-retained-listener, ambiguous-owner,
  and rollback races with safe refusal.

Exit: the stale BEAST-owned branch succeeds under exact authority, while every
unknown, privileged, production, drifted, or ambiguous owner refuses without
effect.

### Milestone 8: delegated namespace and cgroup isolation

Status: started. `IsolationReadinessProbe` now reports cgroup v2 controllers,
delegated subtree controls, writability, current mount/PID/network/user
namespace inodes, `unshare` availability, and the absence of a race-free
`clone3(CLONE_INTO_CGROUP)` wrapper without mutating state. Mission capsules
can apply and read back bounded `cpu.max`, `memory.max`, `pids.max`, and
`io.max` values under action-specific authorization. Full isolation remains
explicitly false until real delegated worker birth and namespace evidence are
implemented.

The first live host experiment resolved the effective systemd scope from
`/proc/self/cgroup` instead of incorrectly treating the cgroup mount root as
the delegation point. The scope is writable and offers `memory` and `pids`,
but is populated and has no enabled subtree controllers; BEAST therefore
refuses to enable domain controllers or rearrange the IDE scope. The refusal
is a Sensorium isolation-downgrade event. Separately, an authorized live worker
proved distinct user, mount, PID, and network namespace inodes, a private
mounted `/proc`, and zero non-loopback routes. A negative runner lane produces
reduced-authority evidence rather than an isolation claim.

`CgroupDelegationManager` now enables only reviewed CPU/memory/PID/I/O
controllers on an empty delegated parent, confirms readback, and creates the
mission capsule. A populated parent or unavailable controller produces no
mutation and no capsule. Direct worker birth into that capsule remains the
next hard boundary; namespace separation alone is not cgroup containment.

The direct-birth boundary is now implemented as a reviewed native helper using
`clone3(CLONE_INTO_CGROUP)`. Its entire interface is three inherited
descriptors: the cgroup directory, a pre-opened executable, and a one-byte gate
pipe. The child is born into the target cgroup and blocks before `execveat`;
BEAST must observe its PID in the target `cgroup.procs` before releasing the
gate. The child closes the cgroup and gate descriptors, marks the executable
descriptor close-on-exec, receives an empty environment, and accepts no path,
shell command, or arguments.

Two live probes pass on this workstation: gated placement in the current scope
and placement in a distinct temporary child cgroup. The distinct child reports
`populated 0` after worker exit and is removed successfully. This proves
race-free cgroup placement and cleanup, but not resource enforcement: the
populated parent still cannot delegate its available memory/PID controllers.
Combining direct cgroup birth with the proven namespace setup, then exercising
limits, pressure, OOM, timeout, and descriptor cleanup, remains open.

Direct birth and namespace setup are now combined in the same live worker
lineage. After pre-exec cgroup membership verification, a fixed reviewed native
worker creates and maps its user namespace, establishes private mount/network/
PID namespaces, becomes PID 1, and mounts a private `/proc`. Its namespace
inodes must differ from the parent and a netlink dump must show no non-loopback
interfaces. The worker also mounts a private 16 MiB tmpfs root, chroots before
evidence collection, proves host `/etc/shadow` and `/home` are absent, and then
confirms private `/proc`, tmpfs, and mountpoint cleanup. The distinct cgroup
returns to `populated 0` and is removed.

A controlled transient `systemd --user` service with `Delegate=yes` was also
measured. It provides a writable dedicated cgroup with CPU, memory, and PIDs
available, but no I/O controller; its main process initially populates the
delegation root. The next implementation must move that positively identified
anchor into a leaf before enabling the available controllers, and must retain
an explicit reduced claim because user-level I/O delegation is absent.

The owned-anchor transition now works live. BEAST acquires a pidfd-backed
ProcessLease for the transient service anchor, requires it to be the only task
in the delegation root, moves it into `beast-anchor`, and collects a successor
lease. Continuity must hold across boot ID, PID/start time, executable,
namespaces, parent identity, and owner scope, while cgroup identity must change
to exactly the anchor leaf. Controllers are enabled and read back at both the
service root and the empty intermediate `beast.slice` before the mission child
may claim resource controls.

A live mission then applied and read back `cpu.max=50000 100000`,
`memory.max=67108864`, and `pids.max=16`; launched the combined isolated worker
through `clone3`; observed namespace/root/secret isolation, CPU/memory/I/O
pressure files, and `populated 0`; and removed the capsule. I/O pressure is
observable, but `io.max` enforcement remains unavailable because the user
service did not receive the I/O controller.

Compute Forge is now joined to this boundary. Forge node profiles can carry a
content-bound `ForgeIsolationAttestation`, and the distributed scheduler keeps
work marked `requires_isolation` queued unless race-free birth, namespace and
filesystem/secret isolation, cleanup, and every requested controller are
attested. The present user-level forge lane admits CPU/memory/PID work and
refuses I/O-required work rather than silently weakening it.

A production-reachability audit is recorded in
`docs/beast-compute-production-reachability-audit.md`. Of 80 top-level compute
modules, 51 are statically reachable from an application import root and 29
are not. In particular, the Forge scheduler/isolation admission, typed
physical-crystal interpreter, governed crystal executor, and scientific
ablation/displacement modules still lack production composition ownership.
Passing unit and live harness tests is not counted as runtime wiring.

- create a real delegated cgroup v2 mission subtree with CPU, memory, PIDs,
  I/O, pressure, population, freeze, and cleanup evidence;
- birth replay/execution workers directly into the capsule where supported,
  with an explicit fallback boundary where `clone3(CLONE_INTO_CGROUP)` is not;
- establish mount, PID, and network namespaces for destructive held-out work;
- provide isolated loopback/service-registry fixtures and deny ambient network
  routes and secrets;
- prove descendant containment, descriptor cleanup, timeout, OOM, bus-peer
  death, rollback, and no-orphan postconditions.

Exit: replay receipts may claim namespace/cgroup isolation only when kernel
observations prove it; unavailable delegation remains an explicit refusal or
reduced-authority mode.

### Milestone 9: reboot continuity

- persist and integrity-check promotion records, Sensorium roots, Guardian
  leases/generations, registry state, consumed capabilities, and evidence links;
- perform an approved workstation reboot with pre-reboot and post-boot witness
  bundles;
- prove Guardian, BEAST, and Commons descriptor recovery without a port-
  ownership gap or generation rollback;
- prove expired appraisals/capabilities do not revive and stale applicability
  proofs cannot cross the boot boundary;
- run a new eligible recurrence after reboot and attach it to the pre-reboot
  promoted crystal chain.

Exit: continuity is supported by live boot-ID-changing evidence, not process-
restart simulation.

#### Milestone 9 implementation armed (2026-07-15)

- Added a two-phase, Guardian-key-signed pre-boot witness and post-boot
  continuity receipt in `app/kernel/execution/reboot_continuity.py`, driven by
  `scripts/run_reboot_continuity.py prepare|verify`.
- The witness binds the current kernel boot ID, nonce-bound TPM evidence and
  signed ARDA appraisal, Guardian generations/lease state, consumed and revoked
  capability rows, Sensorium journal head, and every promoted-record digest.
- Post-boot verification requires a changed kernel boot ID, a new eligible TPM
  evidence digest and ARDA appraisal, no promotion/Sensorium/capability/
  generation rollback, recovered active Guardian descriptors, and a fresh
  zero-provider-call recurrence receipt bound to the new boot.
- Applicability proofs now contain the kernel boot ID. Both authority
  consumption and typed execution validate it, so a monotonic proof captured
  before shutdown cannot authorize work after boot even if its serialized TTL
  appears usable.
- The learned-port experiment now persists its complete declarative typed
  Crystal IR and promotion appraisal beside its promotion registry and
  Sensorium journal, closing the prior receipt-only packaging gap for future
  rebootable capsules.
- Installed a mode-0600 durable capsule at
  `~/.local/state/beast/port-crystal-runtime/`. Its learned receipt is verified
  with digest
  `sha256:67b6ff6f2c5fdb8a200a3ca9ac8f63f6b6b577d175717dffd1b5d7889199a570`,
  typed artifact digest
  `sha256:b8a497434550c42884e6c791080bda594c3cfbe5ca8e4101f98f5718aeec4e34`,
  and promoted record digest
  `sha256:89e0eacdbe57ba598b17866a5640f30805f41355f9965326823e28774737bba1`.
- Focused continuity, physical lifecycle, interpreter, Sensorium port,
  TPM/appraisal, and Guardian boundary suite: **37 passed**.

Live exit status: **completed**. A Guardian-signed pre-boot witness bound boot
`f701d84f-1e91-4405-b4a5-7c511187877b`; the approved physical reboot produced
boot `67db0397-9de0-4ad0-9a3a-914075618192`. Fresh nonce-bound TPM quotes on
both sides reconciled PCRs `0,2,4,7,10,14`, including the bank-specific
SHA-256 IMA stream, and each received a distinct signed ARDA appraisal.

After Docker-restored ARDA became healthy, Guardian-authorized BEAST and
Commons handoffs recovered. The exact persisted typed artifact and promotion
record executed on a newly observed recurrence with zero provider calls. All
twelve aggregate checks passed: boot change, post-boot attestation freshness,
TPM/ARDA binding, promotion and Sensorium non-rollback, consumed/revoked
capability persistence, Guardian generation non-rollback, active descriptor
recovery, old-authority invalidation, and fresh recurrence verification.

- Final continuity receipt:
  `docs/evidence/reboot-continuity-receipt-2026-07-15.json`, canonical digest
  `sha256:242a4e56516ce4249d0fcb9dc6ac4f64a72e7c1a704981284364e6117c8878cd`.
- Pre-boot witness:
  `docs/evidence/reboot-continuity-preboot-2026-07-15.json`, witness digest
  `sha256:3de39dd4cfd2a17fa6f574f4470eb4e4932850418364c9f8ddeed0d59bcbfe69`.
- Post-boot recurrence:
  `docs/evidence/reboot-continuity-recurrence-2026-07-15.json`, receipt digest
  `sha256:67fa5cac83b0223326e65892aadf25a7a2b3f3e23507d7bf60ee96972f50052e`.

The exercise also corrected two production boundaries: ComputePlane runtime
state now defaults to `BEAST_STATE_ROOT/compute_plane` rather than the
systemd-read-only source tree, and the TPM collector is directly executable
from `scripts/`. A process restart still cannot satisfy the verifier.

### Milestone 10: second physical domain

- select a deterministic file/build transformation with objective byte/hash,
  test, filesystem-effect, and rollback verification;
- collect natural positive, failed, refused, and mutation episodes;
- reuse the same causal episode, generalizer, typed opcode, replay, promotion,
  applicability, authority, interpreter, and evidence components;
- prohibit domain-specific shortcuts in the generalizer or promotion gate;
- prove an unseen later recurrence locally and safely reject boundary changes.

Exit: one shared architecture proves both socket/process repair and file/build
transformation, establishing generality beyond a sophisticated port manager.

#### Milestone 10 completed: learned physical file/build crystal (2026-07-15)

- Added one reviewed deterministic transformer shared verbatim by held-out
  replay and live execution. It accepts only a bounded, non-symlink
  `source.json`, renders `generated.json` atomically, and verifies exact bytes,
  SHA-256, schema-derived count/sum, and build tests.
- Three natural successful filesystem episodes and two natural refusals flowed
  through the existing Sensorium sequencer, RuntimeEpisode causal graph, and
  `CrystalGeneralizer`. The shared four-step signature is
  `file.inspect_source -> build.select_branch -> build.render_artifact ->
  artifact.verify_build`; only `workspace_identity` was inferred.
- Extended the reviewed opcode catalog with observation, proposal, bounded
  actuation, verification, refusal, and rollback contracts for this domain.
  The bounded actuator cannot serialize commands or ambient authority.
- Closed a cross-domain authority gap by binding applicability proofs to a
  digest of the resolved, non-symlink workspace root. A proof for one workspace
  cannot be supplied with another filesystem root after authorization.
- Structured replay passed four unseen positive source variants and two
  malformed/schema negative cases in disposable private workspaces. A separate
  post-write verification failure restored the exact prior artifact bytes.
- Promotion required the same signed artifact/evidence-bound ARDA appraisal,
  held-out ablation input, displacement input, physical promotion registry,
  and one-use execution capability used by the port crystal.
- An unseen `omega` recurrence began with a stale artifact, traversed
  ComputePlane's exact `begin -> authorize -> execute -> verify -> complete`
  lifecycle, and finished at the independently computed expected byte digest
  with build tests passing and zero provider calls.
- Compact receipt:
  `docs/evidence/sensorium-learned-file-build-crystal-linux-2026-07-15.json`,
  digest
  `sha256:6ebcd00ff87a2f1837f18c6a6b952d4c6cc12b6175aabbe24a65ed34aef9806e`.
- Complete evidence packet:
  `docs/evidence/sensorium-file-build-evidence-packet-2026-07-15.json`,
  canonical digest
  `sha256:e5bdedb77e6eb625038c1178f4a50d7b0cc78f06184f3aca005de066ee0bfb13`.
- Focused file/build, port, typed IR/interpreter, lifecycle, ComputePlane, and
  reboot-continuity suite: **40 passed**.

Claim boundary: this establishes architectural generality across two physical
transformation classes on the local Linux host, supplemented by the earlier
Windows portable-contract replication. It does not yet prove net displacement
economics or provider-agnostic reuse across two live provider adapters. The
promotion displacement input is a gate receipt, not the paired net accounting
required by Milestone 12.

#### Production composition closure completed (2026-07-15)

- `ComputePlane` is now the explicit runtime composition root for Sensorium
  ingestion and episode closure, episode generalization, typed compilation,
  replay-laboratory submission, signed promotion lifecycle, recurrence
  applicability, durable one-use authority, descriptor-bound capsule
  admission, typed execution, evidence persistence, and attested Forge
  scheduling/isolation admission.
- Removed the former permanent-deny production wiring. The root now owns a
  durable local Ed25519 ARDA runtime identity, verifies artifact/evidence-bound
  appraisals, persists promoted typed artifacts beside the lifecycle registry,
  reloads them after restart, and atomically consumes signed capabilities in a
  SQLite ledger.
- Added the normal application endpoint `POST /edgek/compute/missions` and a
  standalone CLI submitter. Recurrence callers cannot promote artifacts or
  mint authority; operator admission remains a separate reviewed boundary.
- Added an operator admission command for the reviewed file/build crystal. It
  reruns structured positive and negative variants, requires held-out and
  displacement gates, issues a current appraisal, promotes the exact digest,
  and persists the result.
- The production mission path records attributable Sensorium events, closes a
  RuntimeEpisode, creates capsule, applicability, authorization, typed
  execution, mission, and route-displacement evidence, and returns one sealed
  response through the HTTP/CLI path.
- A real `uvicorn app.main:app` process was started against fresh durable
  state. The standalone CLI submitted `mission:live-production-closure-001`
  over HTTP (the final archived rerun is
  `mission:live-production-closure-002`). The application selected
  `crystal:sensorium-file-build:v1`, consumed capability
  `capability:385fa84f14e4405590e41dbdaf37965c`, replaced a stale physical
  artifact, verified the exact generated build, and returned
  `verified_local_recurrence` with response digest
  `sha256:5e99c79e1d3b37262999e5201c02536a0bda688737c1d347385f4af8273ab751`.
- Live reachability recorded one call for every
  `begin -> authorize -> execute -> verify -> complete` phase, two Sensorium
  ingestions, one episode closure, one API mission completion, no active
  attempts, and the promoted artifact visible after application restart.
- Fixture-free production-path and composition tests pass. They use the same
  router mounted by `app.main`, production replay laboratory, persistent
  registry, signed appraisal/capability path, typed interpreter, and physical
  file handlers; no experiment or test-fixture runtime is imported.
- Durable evidence:
  `docs/evidence/production-composition-admission-2026-07-15.json`,
  `docs/evidence/production-composition-live-mission-2026-07-15.json`, and
  `docs/evidence/production-composition-reachability-2026-07-15.json`.

Claim boundary: the capsule used for this bounded file transformer is a
descriptor-bound workspace capsule enforced by the reviewed opcode catalog;
it is not represented as a cgroup/PID/network namespace capsule. Destructive
disk cleanup must use the stronger delegated isolation path. The displacement
node proves a route-counter observation, not net economics; Milestone 12 must
account for local sensing, authorization, execution, and verification cost.

The earlier port and file/build results already cover two physical
transformation classes, but only file/build has now crossed the ordinary
production application boundary. The next deliberately different operational
domain is disk-pressure diagnosis and governed cleanup: quota/pressure sensing,
explicit deletion manifests, mount-bound applicability, negative protected
paths, approval thresholds, rollback/quarantine where possible, and isolated
held-out exhaustion variants. This strengthens rather than erases the existing
Milestone 11 provider-uplift work.

### Milestone 11: provider-agnostic reuse and capability-uplift proof

- define the claim as uplift of the fixed `model + BEAST` system, not learning
  by the model weights; record an independent weight-update claim only if a
  separately evaluated training procedure changes those weights;
- freeze model blob/digest, tokenizer, quantization, Ollama/runtime version,
  Modelfile, decoding parameters, prompts, policy, hardware class, crystal
  digest, verifier, and benchmark commit before evaluation;
- construct leakage-resistant task families with discovery/training,
  validation, and sealed held-out splits by physical variant and template
  family, including positive recurrences, boundary mutations, stale cases,
  semantically similar wrong cases, and negative controls;
- run a randomized paired ablation for every held-out case: raw small model,
  model plus ordinary context/retrieval, model plus BEAST with reuse disabled,
  full promoted-crystal reuse, and sham/wrong/stale-crystal controls, all from
  equivalent initial physical state;
- require the exact same content-addressed Crystal IR and applicability
  contract to execute across at least two runtime provider adapters, including
  a small Ollama model, without provider-specific token IDs, KV state, hidden
  state, prompts, or executable authority in the artifact;
- cross source and consumer lanes: a crystal discovered with provider A must
  be reproducible and usable with provider B, and a locally discovered crystal
  must remain usable when the proposing model/provider is absent;
- score objective verifier success, unsafe effects, false applicability,
  refusals, provider calls, tokens, latency, local resources, and calibration;
  retain every attempt, not only successful traces;
- preregister sample size and minimum useful uplift, then report paired effect
  size, exact McNemar significance for binary outcomes, bootstrap confidence
  intervals, and correction for multiple model/domain comparisons;
- issue an evidence packet containing initial-state digest, model/runtime and
  crystal identities, randomized lane assignment, prompt/output hashes,
  execution and authority receipts, physical observations, verifier output,
  and the complete negative-case ledger.

Exit: on a sealed set of unseen physical variants, the same frozen small
Ollama model is below the preregistered capability threshold without reusable
crystals and the `model + BEAST` system exceeds it with a confidence interval
above the minimum useful uplift; sham, stale, wrong-domain, and inapplicable
crystals do not improve success or cause unauthorized effects. The same
crystal digest also passes with an independent provider adapter. This proves
system capability acquisition and provider-agnostic reuse, not new knowledge
inside unchanged model weights.

#### Milestone 11 implementation and first sealed run (2026-07-15)

- Replaced the earlier two-lane demonstration as Milestone 11 evidence with a
  fail-closed seven-lane protocol: raw model, ordinary context, reuse disabled,
  promoted crystal, sham crystal, stale crystal, and wrong-domain crystal.
  Lane order is randomized and every attempt is retained.
- Frozen evidence now binds the Qwen `qwen2.5:0.5b` GGUF blob
  `sha256:c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515`,
  embedded tokenizer identity, quantization, complete Ollama manifest and
  Modelfile identity, runtime version, deterministic decoding, hardware,
  benchmark commit, policy, Crystal IR, verifier, prompt hashes, sealed task
  commitment, initial-state digests, outputs, authority receipts, tokens,
  latency, provider calls, and unsafe-effect counts.
- Ran twelve independent sealed SHA-256 residual cases through two real HTTP
  adapter implementations over the frozen local Ollama model: native
  `/api/generate` and OpenAI-compatible `/v1/chat/completions`. Raw model,
  ordinary-context, and reuse-disabled lanes each made a real provider call;
  promoted replay made none.
- Result: raw model **0/12**, promoted residual **12/12**, paired uplift
  **1.0**, bootstrap 95% CI **[1.0, 1.0]**, exact McNemar
  **p=0.00048828125**. The three corrected comparisons remain below 0.05.
  All sham, stale, and wrong-domain cases refused with zero unsafe effects.
- The verifier independently reconstructs lane cardinality, pairing, success
  totals, effect size, McNemar value, negative-control behavior, call
  accounting, and the canonical packet digest. Its `--require-complete` mode
  intentionally fails.
- Evidence packet:
  `docs/evidence/milestone11-provider-adapter-uplift-linux-2026-07-15.json`,
  digest
  `sha256:fa7aee6639763d4e34cb2dcecd72346a48bad833d6318e7bbff177ae021210d3`.

Claim boundary: this run proves statistically significant fixed-system uplift,
provider-absent residual replay, negative-boundary safety, and portability
between two protocol adapters. Both adapters terminate in the same Ollama
runtime, and the residual was reviewed rather than discovered by provider A.
Therefore `independent_runtime_adapter_verified`,
`source_consumer_crossing_verified`, and `milestone_11_complete` remain false.
Closure requires one genuinely independent live runtime/provider plus a sealed
provider-A discovery -> provider-B consumption run using the identical crystal
digest. Merely relabelling Ollama's OpenAI-compatible endpoint is not accepted
as provider independence.

#### Milestone 11 independent-runtime closure (2026-07-15)

- Built the official CPU-only `ggml-org/llama.cpp` `llama-server` from commit
  `a5822222909b785f23ddc74ce3c8f85bd0e38562`; installed binary digest
  `sha256:d630b6826b4db3173963dacd2a9270066f1db6e0ed64d75073b582fbc837ae3f`.
- Served the exact Ollama model file through llama.cpp on an independent
  endpoint. Both lanes bind model digest
  `sha256:c5396e06af294bd101b30dce59131a76d2b773e76950acc870eda801d3ab0515`
  and quantization `Q4_K_M`; no conversion or approximate weight-equivalence
  claim was needed.
- Repeated the identical twelve-case sealed task set and seven randomized
  lanes through native Ollama and the separate llama.cpp server: **168 complete
  attempts**, **72 real inference calls**, and **24 provider-absent promoted
  recurrences**.
- Ollama: raw **0/12**, promoted **12/12**, paired effect **1.0**, bootstrap
  95% CI **[1.0, 1.0]**, exact McNemar **p=0.00048828125**.
- llama.cpp: raw **0/12**, promoted **12/12**, paired effect **1.0**, bootstrap
  95% CI **[1.0, 1.0]**, exact McNemar **p=0.00048828125**.
- The final packet binds both binary digests and versions, the exact model
  file, quantization, decoding configuration, distinct adapter implementation
  digests, endpoint identities, identical Crystal digest
  `sha256:3758aeaa79983b8d4282580004a542f62f20b07063b41de60c7d6f12de7f5455`,
  verifier identity, every prompt/output hash, token count, latency, authority
  receipt, and all negative outcomes.
- Decisive gates: `distinct_runtime_families: 2`,
  `independent_runtime_adapter_verified: true`,
  `provider_absent_replay: true`, `negative_controls_safe: true`, and
  `milestone_11_runtime_independence_complete: true`.
- Evidence:
  `docs/evidence/milestone11-cross-runtime-ollama-llamacpp-2026-07-15.json`,
  digest
  `sha256:893a1440b25aa16ffe41a9c2cdc8d5f79833a7f34f2dcaa458bf408b2d5887a7`.

Scientific claim: **BEAST produced a statistically verified fixed-model system
uplift by replacing an unsuitable inference operation with an authorized,
promoted, provider-absent deterministic Crystal.** This is not a weight update
or a general reasoning claim. The earlier result generalized across two
independently implemented provider protocols backed by one Ollama runtime; the
new experiment additionally proves portability across Ollama and llama.cpp
runtime families. Provider-originated discovery -> independent-provider
consumption remains a distinct provenance experiment because this residual was
reviewed rather than proposed by either provider.

#### Disk-pressure diagnosis and governed-cleanup candidate (2026-07-15)

- Added a third physical resource model with read-only pressure/inventory,
  deterministic cleanup planning, bounded quarantine/purge actuation, and
  post-cleanup verification opcodes.
- Cleanup is limited to explicitly allowlisted cache roots beneath an absolute,
  non-symlink workspace. Root/home scopes, path traversal, protected parts
  (`.git`, `.beast`, `.ssh`, secrets, credentials, and source), symlinks,
  hardlinks, cross-device targets, unsupported policy fields, stale manifests,
  and identity drift fail closed.
- Every deletion entry binds relative path, filesystem device, inode, size,
  mtime, and content SHA-256. Planning is bounded by file and byte limits;
  large plans require a distinct high-threshold approval class. Files move to
  an atomic workspace-local quarantine before purge, and injected pre-purge
  failure restores exact bytes.
- Three natural successful episodes and two natural refusals produced a typed
  candidate with parameters `workspace_identity`, `cleanup_manifest_digest`,
  and `approval_receipt_digest`. Five held-out variants passed, including stale
  manifest and empty-cache safe refusals.
- Evidence:
  `docs/evidence/sensorium-disk-cleanup-candidate-2026-07-15.json`, digest
  `sha256:b5ceacac484e88e097422813086aa52f96376cc3bed8e78e62251c7a80565cad`.

The fixed-purpose descriptor-only native worker has now also passed a live
destructive-isolation proof. It was born with `clone3(CLONE_INTO_CGROUP)` under
a transient delegated systemd service with CPU, memory, PID, and I/O
controllers. Only workspace and sealed-manifest descriptors crossed the launch
boundary. The worker established distinct user/mount/PID/network namespaces,
private tmpfs root and `/proc`, no ambient route, isolated loopback, and no host
secret paths. It revalidated device/inode/size/mtime/SHA-256 identities,
quarantined and purged two exact targets (130 bytes), emitted postconditions,
exited with `populated 0` and no orphans, and the capsule was removed. Live
evidence: `docs/evidence/isolated-disk-cleanup-live-2026-07-15.json`, digest
`sha256:6bc2677598b9da27a1c637bc4abebe47657a8c4e0fa81a1579c04ab3ef45a308`.

Production closure: the disk crystal was promoted inside a transient
four-controller delegated service and executed from the ordinary ComputePlane
CLI mission boundary. ComputePlane built and bound the live manifest and
approval digests, consumed applicability-bound one-use authority, and invoked
the fixed native worker through the production isolation delegate rather than
the in-process disk actuator. The worker used `clone3(CLONE_INTO_CGROUP)`,
removed two exact files (88 bytes), proved namespace/root/secret/network
isolation, returned `populated 0` with no orphans, and the capsule was removed.
The joined mission/delegate receipt is independently verified by
`scripts/verify_production_disk_cleanup_mission.py`.

Evidence: `docs/evidence/production-disk-compute-plane-2026-07-15.json`,
digest `sha256:905fa691fa9f82af93a665527b71d03837873bad7bfd94e675f0ff8c1984a4f8`.
The lower-level repeated native proof is
`docs/evidence/production-isolated-disk-cleanup-2026-07-15.json`, digest
`sha256:f462ce083d118ef485ed456d626c19ec4c0d26f487cc9f7be6f100e273bdd2a0`.

Focused disk safety, native isolated worker, learned-candidate, cross-runtime, typed IR/interpreter,
module disposition, production mission, and ComputePlane suite: **42 passed**.

### Milestone 12: verified displacement economics

Status: **implemented, live locally exercised, and independently verified
(2026-07-15)**.

- Added production-owned paired occurrence accounting with exact task, initial
  state, verifier, policy, and postcondition equivalence gates. Receipts account
  for calls, tokens, provider cost, gross and net latency, repair steps, CPU,
  memory-time, I/O, optional energy/pressure, and sensing/applicability/
  authorization/replay/verification overhead.
- Added repeated-occurrence confidence intervals, mutation-invalidation,
  setup amortization and cost/latency break-even analysis. False hits,
  demotions, and negative outcomes are excluded from displacement and emitted
  as capability-impact/routing-economics feedback in the Control Evidence
  Graph. A zero-call observation cannot validate as net economics.
- `ComputePlane.admit_displacement_economics` now binds a validated economics
  receipt and its impact feedback into production evidence.
- The live paired harness made three real calls to local Ollama
  `qwen2.5:0.5b`, observed 255 provider tokens, and compared each
  provider-plus-governed-repair result with an identical deterministic local
  recurrence under the same task, initial-state, verifier, policy, and exact
  postcondition. All three equivalent pairs displaced one call; gross latency
  displacement was 4,658 ms and net displacement after local/governance work
  was 4,656 ms. The 95% net-latency interval remained positive. A real schema
  mutation refused locally and was excluded from credit.
- Evidence: `docs/evidence/milestones-12-14-live-closure-2026-07-15.json`,
  independently checked by `scripts/verify_milestones_12_14_closure.py`.
  Digest `sha256:3ff5d2cdf613142f4ba50b158bf25255fe02e0167f86493f2815afa3a58a664d`.
  Token cost uses the declared experiment rate; energy remained unavailable.

- compare a cold/provider or ordinary governed baseline against promoted local
  recurrence under the same task, initial state, verifier, and policy;
- bind provider-route counters, calls, tokens, latency, repair steps, CPU,
  memory, I/O, energy/pressure where available, and verification cost into the
  Control Evidence Graph;
- distinguish work avoided from work merely moved locally;
- require behavioral/postcondition equivalence and account for sensing,
  applicability, authorization, replay, and verification overhead;
- run repeated occurrences, mutation invalidation, confidence intervals, and
  break-even/amortization analysis;
- feed verified displacement, false hits, demotions, and negative outcomes back
  into capability impact fingerprints and routing economics.

Exit: BEAST can defend a net provider-call/token/cost/latency displacement claim
with paired evidence; a zero-call receipt alone is insufficient.

### Milestone 13: Commons artifact admission

Status: **implemented and locally admitted with immutable signed custody
(2026-07-15)**.

- Added a signed, content-addressed proof bundle containing the promoted
  crystal projection, opcode catalog, applicability and negative boundaries,
  replay summary, verified displacement, provenance, privacy projection,
  policy/attestation requirements, and decay rules.
- Admission requires explicit Space choice, positive ARDA appraisal, privacy
  scan, local Ed25519 signature, immutable vault custody, chunk reconstruction,
  and manifest validation. Ambient authority, raw SensorEvents, live
  descriptors, host identities, credentials, and host paths fail closed.
- Export authority is fixed to `remote_hypothesis` / `verify_only`.
- The live closure harness admitted one proof bundle to a named local Space,
  reconstructed it from immutable chunks, bound a positive signed local ARDA
  appraisal, and exported the complete signed manifest plus its Ed25519 public
  verification key. Receiving nodes now recompute the manifest digest and
  verify its detached signature before reproduction. Signature or content
  substitution fails closed.
- This is a real local artifact admission, not yet consequential admission by
  the separately deployed Commons service under production trust roots/HSM.

- package the promoted crystal, opcode catalog, applicability contract,
  negative boundaries, replay corpus summary, displacement receipt, provenance,
  privacy projection, policy/attestation requirements, and decay rules as a
  content-addressed Commons artifact;
- require local signature, immutable vault/chunk custody, manifest validation,
  privacy scanning, ARDA appraisal, and explicit Space admission;
- export no raw sensitive SensorEvents, live descriptors, capabilities,
  authority bearers, or host-specific identities;
- represent the artifact as a remote hypothesis with maximum proposal or
  verify-only authority until reproduced by the receiving node.

Exit: Commons can distribute the proof bundle without distributing ambient
execution authority.

### Milestone 14: Commons reproduction and federation

Status: **implemented and exercised across two distinct locally attested
logical nodes; remote physical reproduction remains pending (2026-07-15)**.

- Receiving nodes require fresh local attestation, local policy/verifier
  identity, held-out positive and negative-boundary reproduction, and a locally
  validated displacement receipt before node-local applicability, promotion,
  or execution authority is issued.
- Federation rejects stale attestations, policy mismatch, verifier
  substitution, failed/poisoned negative cases, route flapping, and revoked
  contributors. Aggregation counts only independently reproduced, unrevoked
  node-local receipts; advertised claims contribute zero.
- Focused proof: `tests/test_milestones_12_14.py` — **8 passed**. Python compile
  and `git diff --check` also pass. The broader hostile production run was
  stopped after it entered an existing long-running process case; no full-suite
  claim is made here.
- Two independently keyed logical node identities reproduced the signed
  verify-only hypothesis under node-local policy/verifier contexts, retained
  sovereign execution authority, and emitted independently identified local
  receipts. Federation summed only those receipts and counted zero advertised
  claims. The evidence packet explicitly sets
  `remote_physical_node_claimed: false`; a genuinely remote attested host is
  still required for the full federation exit claim.

- reproduce the crystal on an attested remote Commons node using local sensors,
  descriptors, policies, verifiers, negative cases, and resource envelopes;
- issue node-local applicability, promotion, and execution authority only after
  successful local held-out reproduction;
- bind contributor, node attestation, manifest, reproduction, displacement,
  and revocation receipts into the federated Control Evidence Graph;
- test malicious manifests, stale attestations, poisoned negative boundaries,
  verifier substitution, policy mismatch, route flapping, and contributor
  revocation;
- aggregate displacement only from independently verified node-local receipts,
  never from advertised claims.

Exit: Commons exchanges reproducible proof-carrying computation, each node
retains sovereign execution authority, and federation-level displacement is an
auditable sum of local verified outcomes.

The required order is therefore:

```text
safe local recurrence
  -> destructive physical closure
  -> real isolation
  -> reboot continuity
  -> second-domain generality
  -> provider-agnostic capability-uplift proof
  -> paired net displacement proof
  -> Commons artifact admission
  -> Commons local reproduction and federation
```

Equality saturation, BPF listener selection, AF_XDP execution, DAMON tuning,
and broader autonomous promotion remain downstream optimizations. They do not
replace displacement proof or Commons local reproduction.

### 2026-07-14

- Began implementation under both master plans.
- Established S0 contracts and test fixtures.
- Confirmed 36 focused/neighboring regression tests passed. One runtime test
  initially encountered the pre-existing shared provider circuit breaker; it
  passed after its reported cooldown expired.
- Closed Phase S0. Next phase: read-only Sensorium spine.
- Started Phase S1 with explicit synchronization, bounded retention, explicit
  loss accounting, privacy-before-admission, and atomic downstream export as
  implementation invariants.
- Implemented a bounded, explicitly locked event sequencer with global offsets
  and signed `sensorium.loss` events.
- Implemented privacy-before-admission redaction, including forced local-only
  treatment for sensitive and restricted events.
- Implemented RuntimeEpisode assembly, exact per-mission/per-source loss
  accounting, resource aggregation, downstream atomic export, and a payload-
  free read model.
- Added BEAST-owned process, pressure, interception, file-effect, and port-lease
  adapter factories without privileged attachment.
- Wired normal PREC cycles into four observation-only mission events and a
  closed episode. Sensorium failures are caught and cannot interrupt PREC.
- Added `GET /edgek/sensorium/state`; it exposes no event payload or actuator.
- Confirmed 53 focused and neighboring regression tests passed.
- Two unrelated gateway cases were bounded and recorded: static-media HEAD and
  an unmocked chat request each timed out at 90 seconds. The mocked normal PREC
  cycle, main application import, read-only endpoint, and adjacent gateway
  routes passed.
- Closed Phase S1. Next phase: process identity and cgroup capsules.
- Started Phase S2 with pidfd-only signaling, epoll lifecycle observation,
  read-only capability discovery, and action-specific cgroup authorization as
  implementation invariants.
- Implemented content-bound Linux process collection, pidfd-backed leases,
  epoll exit observation, pidfd-only authorized signaling, and lifecycle
  Sensorium events.
- Implemented read-only cgroup v2 discovery and authorized mission capsule
  create, lease-bound attach, freeze, destructive kill, orphan inspection,
  graceful-first cleanup, and removal receipts.
- Added `GET /edgek/process-plane/capabilities`; it is a read-only projection
  and advertises no actuator.
- Registered S2 receipts and process-plane capability objects with Canon.
- Made identity drift during `cgroup.procs` attachment an explicit failure and
  recorded `clone3(CLONE_INTO_CGROUP)` as later race-free birth hardening.
- Confirmed 32 focused process-plane, Sensorium, contract, and Canon tests
  passed before the neighboring regression pass.
- Closed Phase S2. Next phase: SocketIdentity and Port Lease Broker.
- Inspected the authorized Metatron Triune Outbound Gate tree read-only and
  added a normative BEAST/ARDA/Metatron integration assessment covering
  existing assets, maturity gaps, five cross-system contracts, MA0–MA6 phases,
  and a hostile test matrix.
- Confirmed 60 focused and neighboring process-plane, Sensorium, Canon,
  interception, lattice, capability-crystallization, and crystal-reuse tests
  passed; the scoped diff also passed `git diff --check`.
- Started Phase S3 with an explicit `PortLeaseBroker`: ports are retained by
  the broker, represented by content-bound receipts, and released explicitly.
- Added read-only `SocketIdentityReconciler`, which validates process/cgroup
  attribution, creates content-bound socket identities, and reports lease
  matches without opening, closing, or redirecting sockets. Twelve focused
  Sensorium/socket/lease tests now pass.
- Wired reconciliation into `SensoriumRuntime.observe_socket` and the
  payload-free Runtime Observatory topology projection. Socket observations
  now produce ordered `socket.reconciled` events while the read model remains
  explicitly non-actuating. Thirteen focused S3 tests pass; Phase S3 is
  complete.
- Started S4 with a portable PSI reader and policy-only `PsiGovernor`.
  Low pressure admits work, rising pressure delays background/indexing lanes,
  full pressure suppresses nonessential work, and operator/security lanes are
  preserved. The governor has no scheduler mutation authority.
- Integrated optional PSI admission into `RuntimeGovernor`: callers may supply
  a lane in execution metadata, and pressure-denied background work receives a
  normal bounded retry admission rather than scheduler-side mutation. Eight
  focused S4 integration tests pass; Phase S4 is complete.
- Implemented read-only resctrl, DAMON, and zswap capability discovery plus
  pressure-aware memory residency advice for operator, model, worktree,
  community, and deception classes. Six focused S5 tests pass; no memory
  advice performs mutation. Phase S5 is complete.
- Implemented typed Crystal Bus messages with strict framing and a sealed
  memfd capsule carrying a digest-bound immutable Crystal IR payload. Capsule
  verification is separate from execution authorization. Two focused S6 tests
  pass; Phase S6 is complete.
- Implemented typed crystal hypergraph nodes/edges and a held-out replay gate
  requiring every variant to succeed before promotion. Two focused S7 tests
  pass; Phase S7 is complete.
- Implemented content-addressed Control Evidence Graph nodes/links and a
  payload-free, explicitly non-actuating Runtime Observatory projection. Two
  focused S8 tests pass; Phase S8 is complete.
- Implemented the first proof-carrying system crystal, `crystal:port-conflict-repair:v1`.
  It distinguishes free ports, healthy leased services, stale/unknown owners,
  and approval-required destructive repair; every plan carries preconditions,
  postconditions, and an evidence digest. Nine focused S9 tests pass; Phase
  S9 is complete.
- Added `GovernedCrystalExecutor`: crystal plans require an explicit policy/ARDA
  authorization callback, denied effects are represented as veto receipts, and
  authorized effects emit content-addressed Control Evidence Graph nodes.
  Seven focused S10 tests pass; Phase S10 is complete.
- Added BGP-inspired Commons route-flap damping with exponential decay and
  suppression thresholds, plus a content-addressed Commons artifact manifest
  registry. Two focused S11 tests pass; Phase S11 is complete.
- Added `ReleaseChain` orchestration over the Control Evidence Graph, linking
  commit, build, verification, deployment, and runtime receipts. Added audit
  queries for digest drift, missing two-person approval, and privileged
  changes. Six focused S12 tests pass; the planned Sensorium/crystal roadmap
  is complete.

## S13 restart-safe broker and enterprise evidence hardening

- Added a protected user-mode `SocketGuardianServer` and
  `SocketGuardianClient` over `AF_UNIX/SOCK_SEQPACKET`. The guardian validates
  `SO_PEERCRED` plus the caller's `ProcessLease`, retains the original kernel
  socket, and returns duplicates through `SCM_RIGHTS`.
- Proved broker-process restart continuity with two real subprocesses: the
  first broker exited, the TCP listener remained reachable, and a replacement
  broker recovered the same lease from the still-running guardian.
- Moved listener generations and lifecycle transitions into a durable SQLite
  ledger with `WAL`, `synchronous=FULL`, atomic increments, health transitions,
  release reasons, and restart orphan classification.
- Bound reserve/recover/release/health operations to workspace, signed
  capability reference, ARDA appraisal reference, policy generation, registry
  digest, peer UID, and peer ProcessLease. Handoff receipts are content-bound
  and Ed25519-signed.
- Added IPv6/UDP guardian ownership, active health-probe transitions,
  authoritative service-registry reconciliation, registry-drift revocation,
  and signed descriptor-handoff receipts.
- Added a hash-chained SQLite `SensoriumJournal`. Sanitized events are durable,
  offsets restore across runtime restart, and replay fails closed on contract
  or chain tampering.
- Expanded the payload-free socket read model with namespace, VRF, listener
  generation, compatibility-hint state, thread-safe retirement, and guardian
  lifecycle ingestion.
- Hardened Commons manifest replay, immutable vault/chunk writes, symlink
  rejection, artifact-size verification, and concurrent route-damping state.
- Added Commons-to-Sensorium and Commons-to-Control-Evidence-Graph integration
  for artifact admission, route damping, job scheduling, signed job witnesses,
  and Space admission.
- Fixed the extracted Commons router's stale dependency capture: it now follows
  the active replaceable registry/economy/policy services. The web cache is
  also keyed to the active registry and learner rather than time alone.
- The expanded acceptance family passes 144 tests. It includes real peer
  credentials, cross-process FD recovery, loopback reachability, IPv6/UDP,
  tampering, registry drift, durable Sensorium replay, and Commons evidence.

Guardian-process replacement is now covered when an external supervisor owns
the listener. A test retained the original TCP listener outside Guardian,
replaced the complete Guardian process boundary, adopted a new duplicate, and
verified an increment from listener generation 1 to 2 without releasing the
port. Named `LISTEN_FDS` adoption, strict signed one-use operation capability
consumption, a fail-closed daemon configuration, and user-systemd unit
generation are implemented. The generated units pass `systemd-analyze verify`.

BEAST and Commons now have explicit Guardian consumer launch paths. In
Guardian mode they recover the exact workspace/policy/appraisal-bound listener
through `SCM_RIGHTS` and give the already-bound descriptor directly to Uvicorn.
A real integration test terminated one Uvicorn child, launched a different
PID, and served HTTP again from the same lease, port, and listener generation.
The server reports healthy/unhealthy transitions back to the Guardian; an
authorization, ambiguous-selection, or health failure is immediately fatal.
Only the transient absence of the expected adopted listener is retried.

The dedicated Commons listener is path restricted: it exposes the Commons UI
root and Commons-owned API families but denies unrelated BEAST routes. The two
generated consumer units load the authority bearer as a private systemd
credential. Their handoff receipts are mode-0600, atomically replaced, and
file/directory synchronized. The Guardian, five socket units, and both
consumer units pass host unit validation. A 66-test Guardian/Sensorium/Commons/
evidence/ARDA integration family and its 13-test consumer-focused subset pass.

At the initial audit boundary, the units were not installed and
production ARDA/Metatron keys, references, and the operation-capability
endpoint are not provisioned. High ports need no sudo; port 80 or system-wide
proxy/hosts changes remain administrator concerns.

### 2026-07-15 live Guardian validation

- Added a fail-closed ARDA `/authorize/socket-guardian` endpoint in the
  Metatron outbound-gate service. It binds the exact operation, workspace,
  ProcessLease/executable, deployment capability, registry, policy, appraisal,
  and static sovereign-proof evidence digest.
- Closed an appraisal integrity gap: decision and capability signatures no
  longer leave appraisal metadata unsigned. BEAST verifies the canonical
  Ed25519 appraisal before exposing a capability to the Guardian.
- Provisioned host-local distinct authority/receipt keys and a private bearer
  credential outside the repository. The appraisal is explicitly marked local
  validation, not measured boot or production HSM evidence.
- Installed/enabled the user units. BEAST is healthy on 8101 and the dedicated
  Commons service is responsive on 8601; its consequential admission remains
  fail-closed as `configuration_required` until Commons trust roots land.
- Corrected immutable-deployment state paths exposed by `ProtectSystem=strict`:
  plugin and `.beast` runtime state use `BEAST_STATE_ROOT`, and Commons Spaces
  use the service state directory rather than the source tree.
- Live consumer replacement changed both PIDs while retaining leases, ports,
  and generations with zero observed port-ownership gap.
- Live Guardian replacement changed the Guardian PID, advanced generations,
  retained ports continuously, and restored healthy signed handoffs.
- 76 BEAST integration tests and 8 ARDA authority tests pass. Installed unit
  verification and Python/Electron syntax checks pass.

Actual workstation reboot continuity remains unclaimed until an explicit
reboot window is approved. Full details and evidence hashes are recorded in
`docs/beast-guardian-live-validation-2026-07-15.md`.

### 2026-07-15 TPM and remote Commons challenge validation

- Confirmed a physical TPM 2.0 device through `/dev/tpmrm0`, with all 24
  SHA-256 PCRs active and Secure Boot enabled.
- Produced and cryptographically checked a fresh nonce-bound quote over PCRs
  `0,2,4,7,10,14` using a transient TPM-resident AK. No persistent TPM handle
  or private key file was created.
- Matched the TPM-derived EK public key to the firmware EK certificate and
  validated its Nuvoton intermediate/root chain using pinned host-local trust
  material outside the repository.
- Completed a real MakeCredential/ActivateCredential round trip. The offline
  verifier uses a digest-pinned Debian 12 base with `tpm2-tools 5.4`; the
  physical TPM recovered the verifier secret, binding the transient AK to the
  certified EK. The verifier image ID is recorded in the evidence packet.
- Parsed the privileged firmware event log and compared its replay with live
  PCR state. PCRs `2,4,7,14` match exactly; PCR `10` is assigned to the
  separate IMA replay channel.
- Replayed the staged IMA SHA-256 template measurements. PCR `10` matches the
  live TPM exactly with zero malformed records.
- Confirmed that HP's official V72 `01.11.00` SoftPaq history publishes PCR0 as
  `0886e6fc01b4b9c8fc427eb494c7fa477032d56991529621fe3e9865f532e92f`, matching
  the live TPM exactly. BEAST now records this as a durable vendor measurement
  source under `docs/evidence/tpm/vendor-baselines/`, not as a PCR0 waiver.
- Added a mode-0600 hardware evidence packet at
  `~/.local/state/beast/tpm-validation-latest.json`. The latest local packet
  reports `hardware_quote_valid_measurements_reconciled` and
  `eligible_for_commons: true` at the evidence collector layer.
- Added a durable SQLite TPM challenge ledger with 256-bit nonces, exact node/
  audience/PCR binding, expiry, supersession, and atomic one-use consumption.
- Exposed the safe challenge half of the protocol through
  `POST /edgek/control-plane/commons/attestation/challenges`. A real challenge
  was issued through the live Guardian-owned Commons listener on port 8601;
  the response correctly reported `admitted: false`.
- Documented one canonical Linux/Windows evidence flow in
  `docs/commons-tpm-remote-validation.md`. Remote quote submission and ARDA
  appraisal are not exposed until credential activation, EK revocation policy,
  quote verification, and event-log replay are independently implemented.
- The focused TPM/Commons suite passes 18 tests. Live BEAST/Commons consumer
  replacement again passed with no port-ownership gap.

The 2026-07-15 evidence audit is
`docs/beast-enterprise-evidence-readiness-audit-2026-07-15.md`. Its corrected
focused suite passed 143 tests and scores each roadmap against strict,
reproducible exit gates rather than file counts.

## Files changed

### ComputePlane production reachability slice (2026-07-15)

- Added one observable `ComputePlane` composition root and removed independent
  production inference/streaming singleton construction.
- Bound provider, local, streaming, and production Forge execution to the
  common `begin -> authorize -> execute -> verify -> complete` lifecycle.
- Added strict, expiring Forge isolation admission plus a hardened delegated
  systemd supervisor boundary.
- Made held-out ablation and measured displacement mandatory for physical
  crystal promotion in the production registry.
- Added the read-only `/edgek/compute/reachability` endpoint and an integration
  test that treats importable-but-unconstructed enforcement as failure.
- Focused compatibility and integration suite: **60 passed**.
- Scientific capability uplift remains a separate proof milestone: blinded
  provider-agnostic trials and a second physical-domain replication are still
  required before claiming that crystal assistance expands a small model's
  capability envelope.

### Delegated destructive mission proof (2026-07-15)

- Added one aggregate, tamper-evident mission-isolation receipt spanning
  controller/limit readback, pressure, resource events, freeze/thaw,
  namespace evidence, fault receipts, population, orphan state, and cleanup.
- Added five reviewed fixed-purpose native negative workers: bounded timeout,
  cgroup OOM, bus-peer death, rollback/descriptor cleanup, and descendant
  containment. They accept no arguments or environment-provided authority.
- Extended the combined native worker to bring up only its private loopback,
  prove a loopback service-registry round trip, observe zero non-loopback
  interfaces/routes, chroot into a private tmpfs, and deny host secrets.
- Added an explicit fallback receipt for kernels without
  `clone3(CLONE_INTO_CGROUP)`. The fallback records stopped-child attachment
  as weaker and refuses destructive execution; it is never labeled race-free.
- Ran the proof in a real transient `systemd --user` service with `Delegate=yes`.
  Kernel-observed results: clone3 placement, namespace isolation, freeze/thaw,
  descendant containment, descriptor cleanup, timeout signal 14, OOM kill with
  `memory.events: oom=1, oom_kill=2, oom_group_kill=1`, bus-peer EOF, rollback,
  `populated 0`, no orphans, and subtree cleanup all passed.
- The host user delegation exposes only `cpu memory pids`; `io` is withheld at
  `user.slice`. The receipt therefore correctly says
  `full_isolation_proven: false`, despite all other cases passing. Enabling the
  I/O controller above `user@1000.service` requires administrator authority and
  a new live run; BEAST does not treat `IOAccounting=yes` as delegation proof.
- Durable evidence:
  `docs/evidence/mission-isolation-live-2026-07-15.json`.
- Focused isolation and ComputePlane suite: **21 passed**; the expanded focused
  boundary including kill/rollback tests: **26 passed**.

### Compute consolidation and local uplift experiment (2026-07-15)

- Classified every present top-level compute module into exactly one of:
  online enforcement, supervised evidence, or offline reusable library. The
  machine-readable report has zero unclassified or missing modules and is
  embedded in `/edgek/compute/reachability`.
- Removed the retired `crystal_integrations` compatibility registry; callers
  use the canonical `local_capabilities` registry.
- Renamed the unrelated in-memory Forge aggregate from `ComputeLedger` to
  `ForgeCreditLedger`, eliminating its collision with the authoritative SQLite
  compute plan/gate/receipt ledger.
- Added a hardened systemd evidence-job supervisor. Offline gauntlets are not
  loaded into request handling; their receipts cross promotion only through an
  explicit ingestion boundary.
- Central Forge promotion now refuses shadow-run counts unless the proposal
  also carries independently identified verified held-out ablation and
  displacement receipts.
- Ran a preregistered, blinded paired experiment with local Ollama
  `qwen2.5:0.5b`: 12 held-out inputs, two repetitions, exact scoring, two
  negative applicability cases, and provider-disabled replay.
- Result: model-only **0/24**, same local system with the bounded SHA-256
  residual crystal **24/24**, exact paired McNemar
  `p=1.1920928955078125e-07`, and **24 provider calls avoided**. This proves a
  system-level capability expansion, not a change to the model's weights or a
  general reasoning uplift.
- Receipt:
  `docs/evidence/scientific-uplift-qwen-0.5b-2026-07-15.json`.
- Focused post-consolidation suite: **70 passed**.
- Independent replication on a second physical domain remains mandatory. No
  second host was available in this workspace, so cross-domain proof is not
  claimed.

The host I/O delegation blocker remains physical and administrative. A
root-only, non-sudoing installer and systemd drop-in now exist under
`scripts/install_beast_io_delegation.py` and
`deploy/systemd/user.slice.d/90-beast-io-delegation.conf`. They were not run
without administrator authority. After installation/readback and any required
controlled user-session restart, rerun `scripts/run_mission_isolation_proof.py`;
only a receipt containing all four controllers may set
`full_isolation_proven: true`.

#### I/O delegation correction

Live post-reboot diagnosis found the distribution's decisive restriction in
`/usr/lib/systemd/system/user@.service`: `Delegate=pids memory cpu` explicitly
omits `io`. `IOAccounting=yes` on `user.slice` alone cannot override that
controller allow-list. The installer now deploys three coordinated drop-ins:
`user.slice`, the `user-.slice` template, and `user@.service` with
`Delegate=cpu memory pids io`. It also has a non-mutating `--verify` mode that
checks `cgroup.controllers` and `cgroup.subtree_control` at all three live
boundaries. The corrected configuration requires one new administrator install
and reboot; the earlier reboot occurred before this corrected override existed.

#### Four-controller proof completed

After installation, `io` reached `user.slice` and `user-1000.slice`. The user
manager exposed it in `cgroup.controllers` but enabled it lazily in
`cgroup.subtree_control`; the verifier now requests a transient delegated I/O
unit through systemd to exercise that production activation path. All three
hierarchy boundaries subsequently passed exact readback.

The first full run also rejected the virtual root filesystem device with
`ENODEV`. The runner was corrected to select a kernel-attributed block device
from the nearest populated ancestor `io.stat`. The repeated real systemd-
delegated mission then passed with:

- controllers: `cpu memory pids io`;
- `cpu.max=50000 100000`;
- `memory.max=33554432`, `memory.swap.max=0`, `memory.oom.group=1`;
- `pids.max=16`;
- `io.max=259:0 rbps=10485760 wbps=10485760` with kernel readback;
- pressure, freeze/thaw, clone3 placement, namespaces, isolated loopback,
  ambient route/secret denial, timeout, OOM, bus-peer death, rollback,
  descendant and descriptor cleanup, populated-zero, no-orphan, and subtree
  removal evidence.

The durable receipt reports `full_isolation_proven: true`:
`docs/evidence/mission-isolation-io-live-2026-07-15.json`, digest
`sha256:bbd6822be24d72d411685b85834071d861d37fa2b8f7de2109a90c127b486afc`.
The focused final boundary passes **24 tests**.

### First naturally learned physical crystal (2026-07-15)

- Replaced the fixture-built candidate path with a supervised live experiment.
  Three independently started loopback processes produced positive physical
  episodes; a fourth live process produced the unknown-owner refusal episode.
- Linux `/proc` socket inventory, fd/inode owner attribution, ProcessLease
  collection, loopback health probes, and ordered Sensorium physical effects
  supplied the episode facts. No fixture helper constructed the candidate.
- `CrystalGeneralizer` inferred the sole parameter `requested_port`; the typed
  compiler accepted the learned `socket.inventory -> repair.select_branch ->
  service.verify_health` graph.
- Structured replay passed three unseen positive ports and one unknown-owner
  negative case. Promotion required the replay-bound held-out ablation and
  displacement inputs.
- A later, newly started listener satisfied recurrence. The promoted typed
  interpreter completed locally with zero provider calls. After that process
  exited, the same recurrence context failed freshness and was refused.
- Durable supervised Linux receipt:
  `docs/evidence/sensorium-learned-port-crystal-linux-2026-07-15.json`, digest
  `sha256:7e3d542d5153e3cb0f645894975b6c44580246624924a45f8f91ed48b6405d5e`.
- The Windows-native replication runner generates its own ports, episodes,
  blinded held-out cases, stale-listener negative case, and receipt. The
  cross-domain verifier rejects its explicit non-Windows self-test mode, so a
  Linux dry run cannot masquerade as physical replication.
- Focused natural-learning/lifecycle suite: **39 passed**.

#### Windows portable-contract replication received

Windows 11 host `DESKTOP-A0VN5FH` independently generated three positive
socket episodes, one negative episode, three unseen reuse trials, and one
stale-listener refusal. All trials passed with zero provider calls and
`self_test=false`. Canonical recomputation exactly matched receipt digest
`sha256:9149f3134c165e709b1178e704a0e67f6e4d642796a9133e94830b6f1e301ff6`.
The preserved artifact is
`docs/evidence/sensorium-learned-port-crystal-windows-2026-07-15.json`.

Claim boundary: this verifies the portable physical port-reuse contract on a
second machine and operating system. It does not yet reproduce BEAST's full
Sensorium sequencer, causal generalizer, typed compiler, replay laboratory,
promotion registry, ComputePlane, or Ollama ablation on Windows. Full
cross-domain BEAST equivalence therefore remains pending.

#### Windows Ollama capability-uplift replication received

The same physical Windows 11 host, `DESKTOP-A0VN5FH`, ran the preregistered
portable Ollama experiment with `qwen2.5:0.5b`. The small model succeeded on
0/16 exact held-out transformations alone; the bounded residual crystal
succeeded on 16/16, passed both applicability negative controls, made zero
Ollama calls during assisted replay, and replayed with the provider disabled.
The receipt's row-level exact McNemar result is `p=0.000030517578125`.

Because the 16 rows are two repetitions of eight unique inputs, the independent
bundle verifier also collapses repetitions before inference. The conservative
unique-task exact result remains significant at `p=0.0078125`. It verifies raw
manifest hashes, canonical receipt digests, physical-domain and machine
bindings, held-out/negative/staleness outcomes, and provider-call accounting.

- Port receipt: `docs/evidence/windows-port-crystal-receipt-2026-07-15.json`,
  canonical digest `sha256:1d5ca4543e3113c5bffcc642e27a8b85cba2121f1c579d8ed566132105ce0c04`.
- Uplift receipt: `docs/evidence/windows-ollama-uplift-receipt-2026-07-15.json`,
  canonical digest `sha256:26d7f35ceb32f02199de0ef2c46874687329be237a317bc85bd54884e873bc48`.
- Raw-hash manifest: `docs/evidence/windows-replication-manifest-2026-07-15.json`.
- Independent verifier: `scripts/verify_windows_replication_bundle.py`.

Claim boundary: this is evidence that a fixed small Ollama model plus a bounded,
applicable residual program performs this exact transformation class beyond
the model alone, and that recurrence can avoid the provider. It is not evidence
that model weights learned, that general reasoning improved, or that the full
BEAST Sensorium/ComputePlane stack executed on Windows. Those broader claims
still require native end-to-end runtime replication and additional task
families/providers.

- `app/kernel/sensorium/__init__.py`
- `app/kernel/sensorium/artifact_taxonomy.py`
- `app/kernel/sensorium/contracts.py`
- `app/kernel/sensorium/contracts_hash.py`
- `app/kernel/sensorium/architecture_decisions.py`
- `app/kernel/sensorium/privacy.py`
- `app/kernel/sensorium/event_sequencer.py`
- `app/kernel/sensorium/adapters.py`
- `app/kernel/sensorium/episode_builder.py`
- `app/kernel/sensorium/exporter.py`
- `app/kernel/sensorium/read_model.py`
- `app/kernel/sensorium/runtime.py`
- `app/kernel/sensorium/journal.py`
- `app/kernel/registry/canon_registry.py`
- `app/kernel/execution/orchestrator.py`
- `app/kernel/execution/__init__.py`
- `app/kernel/execution/process_identity.py`
- `app/kernel/execution/epoll_constellation.py`
- `app/kernel/execution/process_supervisor.py`
- `app/kernel/execution/cgroup_capsule.py`
- `app/kernel/execution/process_plane.py`
- `app/kernel/execution/socket_guardian.py`
- `app/kernel/execution/guardian_authorization.py`
- `app/kernel/execution/socket_guardian_daemon.py`
- `app/kernel/execution/port_lease_broker.py`
- `app/kernel/commons/evidence_bridge.py`
- `app/kernel/commons/enterprise_plane.py`
- `app/main.py`
- `tests/test_sensorium_contracts.py`
- `tests/test_sensorium_runtime.py`
- `tests/test_socket_guardian_production_boundary.py`
- `tests/test_socket_guardian_daemon.py`
- `docs/beast-sensorium-crystals/RESEARCH.md`
- `docs/beast-sensorium-crystals/IMPLEMENTATION.md`
- `docs/beast-sensorium-crystals/PROGRESS.md`
- `docs/beast-sensorium-crystals/ADRS.md`
- `docs/metatron-arda-beast-integration-assessment.md`

#### Milestone 10 completed: production composition and ownership

A user-initiated API mission traversed the production Compute Plane, selected an eligible promoted typed Crystal, revalidated applicability, consumed one-use authority, executed the reviewed local program, independently verified the resulting artifact, recorded Sensorium and Control Evidence Graph evidence, avoided one provider call, and returned through the normal API mission interface. Experimental and scientific modules remain explicitly separated into supervised-evidence or offline-library dispositions. Default mandatory routing across all interfaces, broad multi-Crystal operation and full namespace/cgroup isolation for this task family remain outside the claim.

#### Production enforcement hardening after Milestone 10

- A hostile production-mission matrix now covers repeated eligible recurrence,
  malformed input, stale appraisal, expired promotion, one-use capability
  replay, missing handlers, opcode-catalog drift, workspace-root identity
  drift, verifier failure, simultaneous eligible Crystals, and governed
  provider fallback when no Crystal applies.
- The public mission receipt now binds measured execution latency, joined
  capsule/execution/episode/displacement/mission node receipts, and provider
  counters immediately before and after local execution.
- No-match remains fail-closed by default. Provider fallback requires both an
  explicitly configured provider handler and a mission-level opt-in; it passes
  through the common lifecycle and produces its own provider-call witness and
  Control Evidence Graph node.

Production enforcement closure: applicable promoted-crystal routing now uses
the explicit `explicit_enforce` mode and revalidates the full production
composition on every dispatch. A deployed three-process Uvicorn drill routed
the same promoted file/build mission through CLI and IDE HTTP entry points.
Both returned verified local recurrence. Separate deployed children with the
evidence component removed and routing mode tampered returned HTTP 409 before
execution. Evidence:
`docs/evidence/deployed-enforcement-probe-2026-07-15.json`, digest
`sha256:77a6a74ca658cdb94f6da73bfc1287505e22c1349c15b55c4b2f043ee5796b52`.

The remaining production/federation claims are broader multi-Crystal routing,
full native Windows Sensorium/ComputePlane equivalence, provider-originated
discovery followed by independent-provider consumption, consequential Commons
service admission under production trust roots/HSM, and reproduction on a
genuinely remote attested physical node.

The Milestones 10/11 proof bundle is
`docs/evidence/beast-milestones-10-11-proof-bundle-2026-07-15.zip`. Its internal
manifest covers 166 source, test, evidence, report, and summary files. The
external digest summary and independent ZIP verifier are retained beside it;
private authority, live ledgers, and external model/runtime binaries are
deliberately excluded and represented by their bound identities.
