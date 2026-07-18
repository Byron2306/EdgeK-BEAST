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
