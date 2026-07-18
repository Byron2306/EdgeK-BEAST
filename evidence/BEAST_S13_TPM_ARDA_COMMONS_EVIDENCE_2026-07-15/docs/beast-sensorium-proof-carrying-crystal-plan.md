# BEAST Sensorium and Proof-Carrying Compute Crystal Plan

Status: proposed implementation companion to the BEAST master plan  
Scope: compression, interception, caches, semantic pages, crystal systems,
runtime sensing, process and socket identity, proof-carrying residual programs,
and the Port Conflict Repair proof  
Primary rule: observation does not grant authority

## 1. Executive decision

The proposed direction is sound and should become the lower, physical half of
BEAST's crystallized-compute architecture.

BEAST already has substantial pieces of the system:

- structured and AST-aware compression;
- inference and streaming interception;
- exact, semantic, prompt-prefix, and KV reuse;
- semantic compute pages;
- parameterized generative crystal templates;
- SourcePlan mission-lattice fingerprints;
- capability promotion, demotion, negative outcomes, and impact fingerprints;
- crystal forks, evidence exports, staleness checks, and runtime boundaries;
- an AF_PACKET `TPACKET_V3` receive ring plus DPDK and AF_XDP readiness probes.

Those pieces prove that BEAST can capture, index, gate, reuse, and account for
several kinds of local computation. They do not yet form a general system that
learns a parameterized transformation from ordered physical effects and then
replays it only when the same physical preconditions recur.

The missing bridge is:

```text
read-only sensors
        |
        v
ordered, attributable SensorEvents
        |
        v
RuntimeEpisode + causal execution graph
        |
        v
bounded candidate Crystal IR
        |
        v
isolated replay + held-out variants + negative cases
        |
        v
approval and promotion
        |
        v
descriptor-bound, evidence-producing execution
```

This plan therefore adopts the following definition:

> A compute crystal is a parameterized, proof-carrying residual program whose
> applicability, authority, execution graph, observable effects, verification,
> resource envelope, evidence requirements, and decay rules are explicit.

It is not merely a cached answer, embedding neighbor, similar SourcePlan,
prompt-prefix block, or successful historical trace.

## 2. The taxonomy BEAST needs

The word `crystal` currently covers artifacts with materially different
semantics. That is workable during exploration but unsafe at an execution
boundary. BEAST should preserve the useful existing names while assigning each
artifact an explicit class and maximum authority.

| Artifact | Existing purpose | Maximum authority |
|---|---|---|
| Exact answer entry | Reuse an exact response under exact identity | Return verified data within its validity boundary |
| Semantic cache entry | Find a related verified response | Candidate/context only unless an independent verifier proves the requested outcome |
| KV/prefill block | Reuse model execution state | Performance optimization only |
| Semantic compute page | Content-addressed computed material | Data artifact; no execution authority |
| Mission lattice cell | Compare privacy-safe SourcePlan and graph shapes | Advisory scaffold only |
| Generative crystal template | Bind parameters into bounded Action IR with verifier and rollback plans | Proposal until local verification and approval gates pass |
| Crystallized capability | Promoted deterministic/reuse/local-inference capability with impact fingerprint | Execute only inside its promoted transform and fingerprint boundary |
| Runtime episode | Ordered observed facts for one governed mission | Evidence; never an actuator |
| Compute Crystal IR | Parameterized residual program with physical pre/postconditions and evidence contract | Execute only through the Crystal Executor under a capability lease |
| Crystal capsule | Immutable local transport of one canonical Crystal IR instance | Carries bytes and identity, not authority |

Every stored object should expose:

```yaml
artifact_class: semantic_cache_entry | mission_lattice_cell | compute_crystal_ir | ...
authority: context_only | proposal_only | verify_only | bounded_execute
verification_state: unverified | candidate | heldout_validated | promoted | revoked
applicability_hash: sha256:...
policy_generation: ...
expires_at: ...
```

The runtime must reject an object whose class is absent or whose requested use
exceeds its maximum authority.

## 3. Honest map of the current implementation

### 3.1 Compression

`app/kernel/compute/compression_pipeline.py` already routes content through
structured JSON compression, Python-aware compression, and text pruning. It
creates content hashes and evidence envelopes. This is a useful canonicalizing
front end for Sensorium payloads and crystal inputs.

Current boundaries:

- Python top-level chunk recognition is pattern-driven rather than a complete
  symbol or call graph;
- text pruning removes blank and consecutive duplicate lines, which is useful
  compaction but not a semantic proof;
- chunks currently report `redaction_status: not_scanned`, so raw Sensorium
  payloads must not automatically enter durable or federated storage;
- compression cannot establish causal equivalence or safe replay.

`app/kernel/compute/ast_compressor.py` provides zlib storage, schema-row
structural encoding, `ast.unparse`, and AST summaries. Its semantic mode is a
structural summary of names, node classes, constants, and counts. It is not a
learned semantic mapper and should not be described as one.

Future role:

- canonicalize low-risk event payloads;
- produce deterministic hashes over normalized structures;
- create compact episode summaries;
- retain lossless source artifacts separately whenever reconstruction matters;
- run the privacy scanner before durable storage or Commons export.

### 3.2 Interception

`app/kernel/compute/inference_interceptor.py` already provides governed
begin/complete boundaries and routes requests through reusable, deterministic,
local, and cloud paths while recording receipts.

`app/kernel/compute/streaming_interceptor.py` already performs incremental JSON
extraction, bounded schema validation, repetition and explanation-leakage
detection, upstream cancellation, repair, and escalation.

Future role:

- emit ordered provider-call, stream-state, cancellation, schema-validation,
  repair, and verification SensorEvents;
- attach request, provider-route, schema, model, and policy fingerprints;
- never infer physical success merely because a provider stream completed;
- use postcondition events from tests, health probes, files, processes, and
  sockets to close an episode.

### 3.3 Cache and reusable inference

`app/kernel/compute/crystal_reuse_gateway.py` currently attempts durable replay,
semantic lookup, KV prefill, and then local CPU execution. Its inventory also
describes the larger intended order: exact answer, verified semantic credit,
local semantic match, memory recall, prompt-prefix prefill, local CPU, local
quality gate, and governed cloud escalation.

`app/kernel/compute/local_semantic_cache.py` uses exact matching or token-set
similarity, task class, repository fingerprint, confidence, verification, and
quarantine. This is valuable retrieval, but token similarity is not an
applicability proof.

`app/kernel/compute/kv_cache_transport.py` records unusually strong identity
metadata: model and tokenizer revisions, prompt and system hashes, engine,
precision, quantization, attention backend, tensor parallelism, RoPE, policy,
tool schema, skill tree, repository, and privacy identity. It also supports
digest-checked, mmap-backed engine payloads. This remains a physical inference
optimization, not a behavioral program.

Future role:

- preserve exact/cache paths as the cheapest rungs;
- use semantic matches to nominate candidates, not authorize mutation;
- treat KV reuse as a subordinate optimization selected after identity and
  staleness checks;
- feed reuse, miss, false-hit, and displacement outcomes into episodes;
- let the new lattice extractor compare a compute crystal against cache and
  local-model alternatives using hard policy constraints and resource cost.

### 3.4 Current crystal and lattice systems

`app/kernel/compute/mission_crystal_lattice.py` stores privacy-safe SourcePlan
fingerprints and compares task family, risk, mode, covenant, safety posture,
operation types, extensions, file-count buckets, and graph-shape buckets using
manual weights. It explicitly remains advisory. This is a mission-memory index,
not yet a physical compute lattice.

`app/kernel/data_processing/generative_crystals.py` is the closest existing seed
of a Compute Crystal IR. It already has:

- task family and a hashed applicability boundary;
- required parameters and deterministic Action IR rendering;
- verifier and rollback plans;
- approval and risk fields;
- expiry;
- privacy scanning;
- candidate, active, demoted, and expired states;
- false-hit counting and credit reversal;
- proposal-only authority until local verifiers pass.

It should be migrated, not discarded. Its missing dimensions are physical
preconditions and postconditions, a causal execution graph, process/socket/file
and resource topology, typed parameters, held-out variant history, evidence
requirements, and a descriptor-bound executor.

`app/kernel/capability/capability_crystallization.py` already implements shadow
runs, hidden-test and rollback thresholds, behavior preservation, impact
fingerprints, promotion, demotion, negative outcomes, and displacement proof.
It should remain the promotion authority and consume stronger evidence from the
new held-out replayer.

`app/kernel/compute/crystallized_compute_proof.py` demonstrates capture,
promotion, semantic pages, capability-lattice construction, tool/skill/crystal
fusion, and later provider displacement. Its default executor is deterministic
and its main prompt is deliberately synthetic. It proves plumbing and local
reuse, not autonomous discovery of naturally generalizable transformations.

`app/kernel/compute/crystal_forks.py` already models stable, candidate, and
experimental channels. A future socket-level fork must adapt to this state
machine rather than introduce a second, contradictory promotion system.

`app/kernel/observability/telemetry_outbox.py` is a small filesystem JSON
exporter. It should remain an exporter after the ordered event bus. It must not
be the primary runtime nervous system.

### 3.5 Network acceleration

`app/kernel/networking/os_bypass.py` contains a real AF_PACKET `TPACKET_V3`
mmap receive ring and DPDK/AF_XDP capability probes. The next useful step is not
more packet speed. It is attribution:

```text
packet -> socket -> process lease -> cgroup -> workspace -> mission -> crystal
```

Unattributed high-speed packets are telemetry volume, not causal evidence.

## 4. Architecture and authority separation

The permanent state transition is:

```text
OBSERVE -> INTERPRET -> RECOMMEND -> AUTHORIZE -> ACT -> VERIFY -> SEAL
```

Each arrow crosses a typed interface. No sensor owns an actuator. No retrieval
score becomes permission. No successful historical episode becomes a promoted
crystal without replay and held-out verification. No immutable capsule grants a
capability that its receiver did not already possess.

Principal services:

```text
Kernel/runtime sources
        |
        v
Sensor Adapters --read-only--> Sensorium Event Sequencer
                                  |
                                  +--> live Observatory projection
                                  +--> Runtime Episode Builder
                                               |
                                               v
                                     Crystal Candidate Extractor
                                               |
                                  isolated replay / held-out tests
                                               |
                                               v
                                   Capability Crystallization
                                               |
                                   approval + ARDA policy decision
                                               |
                                               v
Crystal Forge --sealed capsule--> Crystal Executor --effects--> Verifiers
                                                               |
                                                               v
                                                        Evidence Graph
```

ARDA remains the enforcement authority for execution identity and approved
digests. BEAST schedules and proves. Seraph observes behavioral discord and
campaign context. The Sensorium supplies ordered facts to all three without
silently acquiring their powers.

## 5. SensorEvent contract

All adapters emit one versioned envelope. Payload schemas vary by event type,
but identity, ordering, provenance, privacy, and loss reporting do not.

```yaml
sensor_event:
  version: "1.0"
  event_id: evt_...
  event_type: process.exec
  source: bpf_process_sensor
  source_instance: ...

  ordering:
    boot_id: ...
    source_sequence: 18491
    cpu_sequence: 812
    monotonic_ns: ...
    wall_time: ...

  attribution:
    process_identity_hash: sha256:...
    process_lease_id: process:...
    cgroup_id: ...
    workspace_id: ...
    mission_id: ...
    crystal_instance_id: ...

  confidence:
    value: 0.99
    method: kernel_tracepoint
    gaps_before: 0
    loss_counter: 0

  privacy:
    class: internal_sensitive
    raw_retention: ephemeral
    export_allowed: false
    redaction_status: passed

  payload_schema: beast.sensor.process.exec.v1
  payload: {...}
  payload_sha256: sha256:...
```

Requirements:

- monotonic time is used for ordering; wall time is presentation metadata;
- boot ID prevents cross-boot identity collisions;
- every source maintains a sequence and loss counter;
- ring-buffer loss, sampling, permission failure, and attribution gaps become
  explicit events rather than silent absence;
- raw command lines, paths, environment, file names, addresses, and content are
  classified and redacted before persistence;
- the event bus applies bounded buffers and backpressure; sensors may degrade
  detail but must report that degradation;
- canonical encoding and schema version are included in the event hash.

## 6. Sensor classes and rollout order

### 6.1 Process sensor

Observe fork/clone, exec, exit, parent relationships, start time, executable
digest, command fingerprint, working-directory identity, namespaces, cgroup,
effective identity, and descriptor counts.

Rollout:

1. BEAST-owned subprocess instrumentation and `/proc` snapshots;
2. pidfd acquisition and epoll lifecycle observation;
3. cgroup membership and empty-state events;
4. BPF ring-buffer lifecycle events with explicit drop counters;
5. optional privileged forensic descriptor access.

### 6.2 Socket sensor

Observe bind, listen, connect, accept, close, addresses, protocol, queue state,
duration, ownership changes, and repeated failures.

Rollout:

1. Port Lease Broker events for BEAST-owned listeners;
2. `NETLINK_SOCK_DIAG` inventory and socket-inode correlation;
3. `/proc/<pid>/fd` correlation as a compatibility path;
4. BPF lifecycle events where supported;
5. AF_PACKET attribution and only later AF_XDP/DPDK integration.

Inventory and lifecycle are separate. A point-in-time socket inventory can fill
gaps but cannot prove the exact order in which a conflict occurred.

### 6.3 File-effect sensor

Observe opens only where useful, and always observe writes, renames, deletes,
executable loads, configuration changes, and generated artifacts within
governed scopes.

The preferred evolution is BEAST-owned write receipts first, then fanotify with
PIDFD reporting where kernel and permissions permit. Content capture is not the
default. The normal event contains path identity or scoped relative path,
operation, process identity, before/after metadata, and artifact digest.

### 6.4 Pressure and resource sensor

Observe PSI CPU/memory/I/O stall, CPU throttling, `memory.events`, memory peaks,
OOM, I/O bytes, queue depth, and cgroup population. These events connect the
existing compute-breathing governor to actual episode economics.

### 6.5 Network-path sensor

Correlate packet/flow metadata to the SocketIdentity and ProcessLease. Retain
payload only under a specific forensic policy. Seraph may receive a privacy-
bounded behavioral projection rather than raw traffic.

## 7. ProcessLease: a process identity, not a PID

A PID is a recyclable coordinate. A ProcessLease is a live, scoped identity:

```yaml
process_lease:
  lease_id: process:sha256:...
  boot_id: ...
  pid_at_observation: 28411
  start_time_ticks: ...
  executable_digest: sha256:...
  cgroup_id: ...
  pid_namespace_inode: ...
  mount_namespace_inode: ...
  parent_identity_hash: sha256:...
  owner_scope: beast_mission
  acquired_at: ...
  exited_at: null
```

The pidfd is an internal live handle and is never serialized as if its integer
value were portable. The serialized identity hashes stable observed fields;
the process supervisor keeps the pidfd-to-lease mapping in memory.

One epoll constellation should monitor:

- pidfds for exit;
- Crystal Bus sockets;
- PSI threshold file descriptors;
- cgroup event files;
- Port Lease Broker sockets and health probes;
- Sensorium control and shutdown channels.

The implementation must account for descriptor limits, child reaping, event
coalescing, and the difference between process exit and complete cgroup
emptiness.

### 7.1 Process capsules with cgroup v2

Each governed mission or Commons job receives a cgroup subtree:

```text
/beast.slice/mission-91ad/
  scout/
  verifier/
  local-model/
  tool-workers/
```

The capsule records controller availability before claiming enforcement. It
uses `cgroup.events` population changes for cleanup, `cgroup.freeze` only under
a governed containment action, and `cgroup.kill` only through destructive
authorization. Killing a cgroup is reliable against concurrent forks, but it
is SIGKILL and therefore cannot be the default graceful shutdown path.

Lifecycle:

1. create subtree and record supported controllers;
2. apply resource and descendant policy;
3. spawn or move only BEAST-owned tasks;
4. observe population and pressure;
5. request graceful termination;
6. verify empty;
7. use cgroup kill only if policy permits escalation;
8. seal exit and cleanup receipts.

### 7.2 Privileged forensic viewing

`pidfd_getfd()` can duplicate a target descriptor and refers to the same open
file description. It is guarded by ptrace permissions and can alter underlying
objects if misused. BEAST therefore treats it as:

- Administer-bucket only;
- disabled by default;
- scoped to BEAST-owned or explicitly authorized targets;
- read-oriented wherever the descriptor type allows;
- fully receipt-bearing;
- unavailable to ordinary crystals.

### 7.3 Crystal-driven memory advice

`process_madvise()` is experimental and late-phase. Advice to another process
requires ptrace access and `CAP_SYS_NICE`, can be partially applied, and may
materially affect latency. It is restricted to BEAST-owned workers with an
explicit MemoryProfile and before/after pressure measurements.

## 8. Credentialed Crystal Bus

The local bus uses `AF_UNIX` plus `SOCK_SEQPACKET` because it is connected,
ordered, and preserves message boundaries.

Core messages:

```text
HELLO / CHALLENGE / ATTEST
SENSOR_EVENT
EPISODE_CLOSE
CRYSTAL_PROPOSE
CRYSTAL_VERIFY
CRYSTAL_PROMOTE
CRYSTAL_MATERIALIZE
CRYSTAL_EXECUTE
CRYSTAL_REVOKE
PROCESS_EXIT
SOCKET_BOUND
PRESSURE_ALERT
ACK / NACK / ERROR
```

Each message has a protocol version, type, message ID, correlation ID,
monotonic sequence, sender lease, capability lease, payload hash, optional
attached descriptors, and expiry.

Peer authentication is conjunctive:

```text
SO_PEERCRED
+ ProcessLease/pidfd match
+ executable digest
+ cgroup and workspace scope
+ ARDA attestation result
+ capability lease
```

`SO_PEERCRED` reports credentials captured at connection setup. It is useful
but not a complete workload identity. The bus pathname must be in a protected
directory, permissions and ownership must be checked, and abstract UNIX names
must not be assumed to have filesystem access control.

Operational requirements:

- maximum message and descriptor counts;
- bounded per-peer queues;
- explicit ACK for authority-changing messages;
- replay protection and expiry;
- protocol negotiation and fail-closed unknown fields at authority boundaries;
- safe handling of truncated ancillary data;
- closure of every unaccepted received descriptor;
- Seraph-visible authentication failures and flood behavior.

## 9. Sealed in-memory crystal capsules

Materialization sequence:

1. Crystal Forge validates and canonicalizes one Crystal IR instance.
2. It creates a memfd with `MFD_ALLOW_SEALING` and close-on-exec policy.
3. It writes the complete canonical IR and evidence references.
4. It computes a digest and signs the canonical representation.
5. It removes writable mappings.
6. It applies write, grow, shrink, and seal seals.
7. It verifies the seals with `F_GET_SEALS`.
8. It sends a reference through `SCM_RIGHTS` with capsule metadata.
9. The executor checks peer identity, descriptor type, size, seals, digest,
   signature, policy generation, expiry, and capability lease.
10. The executor maps the capsule read-only and executes only recognized IR.

Security boundary:

- seals protect immutability and prevent shrink/grow races;
- `SCM_RIGHTS` transfers a reference to the same open file description;
- a memfd is not secret memory;
- `/proc` visibility, core dumps, receiver compromise, and copied contents must
  be handled by ordinary confidentiality policy;
- the capsule contains no ambient authority and no raw credential;
- unknown opcodes or unbounded loops are rejected;
- all descriptor and mapping lifetimes are bounded and accounted.

The first Crystal IR should be declarative and finite. It should not embed
Python, shell, BPF, WASM, or arbitrary native code.

## 10. Compute Crystal IR v1

```yaml
crystal:
  schema: beast.compute_crystal.v1
  identity: crystal:port-conflict-repair:v3
  artifact_digest: sha256:...
  signer: ...

  task_family:
    - service_startup_failure
    - address_already_in_use

  authority:
    maximum: bounded_execute
    required_tool_bucket: Modify
    capability_lease: port_conflict_repair
    destructive_steps_require_approval: true
    arda_policy_generation: ...

  applicability:
    operating_system: linux
    kernel_features: [sock_diag, pidfd]
    error_class: EADDRINUSE
    socket_family: [AF_INET, AF_INET6]
    service_registry_schema: beast.port_registry.v1
    minimum_sensor_confidence: 0.90
    forbidden_scopes: [unknown_privileged_process]

  parameters:
    desired_service: {type: string, pattern: "^[a-z0-9._-]+$"}
    requested_port: {type: integer, minimum: 1, maximum: 65535}
    workspace_id: {type: workspace_identity}

  preconditions:
    - id: listener_identified
      verifier: socket_inventory_binding
    - id: owner_identified
      verifier: process_lease_binding
    - id: process_start_verified
      verifier: pidfd_start_time_consistency
    - id: registry_consulted
      verifier: port_registry_snapshot
    - id: policy_loaded
      verifier: current_policy_generation

  execution_graph:
    nodes:
      - {id: inventory, op: query_socket_inventory}
      - {id: bind_owner, op: bind_socket_to_process_identity}
      - {id: classify, op: classify_owner}
      - {id: decide, op: choose_reuse_reassign_or_retire}
      - {id: approve, op: request_approval_if_destructive}
      - {id: apply, op: apply_resolution}
      - {id: listen_verify, op: verify_listener}
      - {id: health_verify, op: verify_health_endpoint}
    edges:
      - [inventory, bind_owner]
      - [bind_owner, classify]
      - [classify, decide]
      - [decide, approve]
      - [approve, apply]
      - [apply, listen_verify]
      - [listen_verify, health_verify]

  postconditions:
    - expected_service_listening
    - previous_service_unharmed_or_explicitly_retired
    - no_orphan_processes
    - port_registry_reconciled
    - health_policy_satisfied

  topology:
    required_socket_roles: [target_listener]
    allowed_process_classes: [beast_owned, registered_shared_service]
    cgroup_scope: mission

  evidence_requirements:
    - sensor_episode_hash
    - process_identity_hash
    - socket_identity_hash
    - policy_receipt
    - approval_receipt_if_required
    - verification_receipt

  economics:
    cloud_calls_avoided: 1
    expected_repair_steps_avoided: 6
    expected_latency_ms: 220
    maximum_cpu_ms: 2000
    maximum_network_bytes: 65536

  decay:
    expires_after_days: 90
    revalidate_after_kernel_change: true
    revalidate_after_registry_schema_change: true
```

IR validation must include schema validation, graph acyclicity for v1, opcode
allowlisting, parameter bounds, required verifier coverage, destructive-path
approval coverage, rollback availability where applicable, resource maxima,
privacy checks, policy freshness, and signature verification.

## 11. RuntimeEpisode and crystallization

A RuntimeEpisode is an immutable logical view over ordered events, not a loose
telemetry dump:

```yaml
episode:
  mission_id: ...
  objective_hash: ...
  workspace_identity: ...
  initial_state_hash: ...
  event_range: {first: evt_..., last: evt_...}
  source_loss: {...}
  causal_graph: {...}
  resources:
    cpu_time: ...
    memory_peak: ...
    pressure_stall: ...
    bytes_read: ...
    bytes_written: ...
    network_bytes: ...
  outcome:
    status: verified_success
    effect_hash: ...
    rollback_tested: true
  episode_hash: sha256:...
```

Candidate extraction:

1. reject incomplete or low-confidence episodes for automatic promotion;
2. remove incidental PID, timestamp, ephemeral port, and temporary path values;
3. retain executable, policy, schema, service-role, cgroup, socket-role, and
   workspace identities where causally relevant;
4. compare repeated successful and failed episodes;
5. use structural anti-unification to separate constants from parameters;
6. infer candidate preconditions only from observed discriminators;
7. infer postconditions from independent verifiers, never from action intent;
8. attach counterexamples and negative applicability records;
9. generate a proposal-only Crystal IR candidate;
10. replay in an isolated worktree/process capsule;
11. run held-out variants and failure injections;
12. narrow the boundary after any false hit;
13. submit evidence to the existing capability promotion engine;
14. require human/policy approval for any elevated authority.

Lifecycle:

```text
observed_episode
  -> candidate
  -> replayable
  -> heldout_validated
  -> approved
  -> promoted
  -> active
  -> degraded | quarantined | superseded | revoked | expired
```

There is no direct `observed_episode -> active` transition.

## 12. SocketIdentity and physical lattice edges

```yaml
socket_identity:
  identity: socket:sha256:...
  family: AF_INET
  protocol: TCP
  local_address_class: loopback
  local_port: 8005
  remote_scope: none
  owning_process: process:sha256:...
  service_id: beast-api
  workspace_id: edgek-beast
  cgroup_id: ...
  listener_generation: 14
  opened_at_monotonic_ns: ...
  policy_class: operator
```

`listener_generation` is issued by the Port Lease Broker. A numeric address and
port alone do not identify a service across restarts.

The runtime graph can then express:

```text
VS Code Extension
  --authenticated socket--> BEAST API
  --governed socket-------> LiteLLM
  --attested route--------> Provider
```

A crystal whose required topology does not match is inapplicable even if its
task wording is similar.

### 12.1 BPF-selectable listeners

Linux BPF socket lookup can select a local TCP or UDP socket during local
delivery, and reuseport BPF can select among a listener group. This is a
laboratory optimization after the user-space fork controller is proven.

Rules:

- kernel logic remains tiny, deterministic, bounded, and policy-derived;
- stable and control traffic always retain a nonexperimental path;
- only preclassified low-risk requests enter candidate traffic;
- assignment uses a stable cohort key, not per-packet randomness;
- the existing `crystal_forks.py` state is the source of fork eligibility;
- socket maps are atomically replaceable and rollback-tested;
- Seraph deception is a distinct policy route, never an accidental fallback;
- no model or complex campaign reasoning runs in BPF.

## 13. Typed hypergraph and constrained extraction

The current mission lattice remains a fast candidate index. The new lattice is
a typed hypergraph that asks which verified combination can satisfy a mission.

Node types:

```text
TaskPattern, Crystal, Tool, Skill, Dataset, Model, ProcessProfile,
SocketTopology, MemoryProfile, Policy, Verifier, Artifact, FailurePattern,
ResourceEnvelope, AttestationState
```

Relation types:

```text
REQUIRES, PRODUCES, VERIFIED_BY, OBSERVED_BY, COMPOSES_WITH, CONFLICTS_WITH,
EQUIVALENT_TO, SPECIALISES, SUPERSEDES, FAILED_UNDER, SAFE_UNDER, DISPLACED,
DERIVED_FROM, ATTESTED_BY
```

Because one executable plan requires multiple nodes simultaneously, a plan is
a hyperedge with required participants, constraints, evidence, and cost.

Begin with SQLite tables and canonical JSON rather than a dedicated graph
database. Required operations are bounded lookup, joins, provenance traversal,
state transitions, and audit export. Move only after measured scale warrants it.

### 13.1 Equality saturation

An e-graph is useful only for deterministic Crystal IR fragments with sound,
versioned rewrite rules. It must not declare two plans equivalent because their
answers look similar or their embeddings are close.

Every equivalence rule includes:

```yaml
rewrite:
  id: ...
  lhs: ...
  rhs: ...
  assumptions: [...]
  proof_or_verifier: ...
  policy_scope: ...
  introduced_at: ...
  revoked_at: null
```

Extraction first enforces hard constraints:

- authority and approval;
- current policy and attestation;
- applicability and topology;
- privacy and data locality;
- verifier availability;
- resource maxima and PSI admission;
- staleness and negative capability records.

It then minimizes a cost vector:

```text
cloud cost, latency, CPU pressure, memory pressure, I/O pressure,
risk, verification cost, staleness, transfer cost
```

Locality, successful reproductions, and provider displacement are tie-breaking
benefits, not permission to violate a hard constraint. The extractor records
both selected and rejected alternatives in a decision receipt.

## 14. First integrated proof: Port Conflict Repair Crystal

This is the correct first physical crystal because the problem is bounded,
common, observable, safety-sensitive, and objectively verifiable.

### 14.1 Scope

The v1 proof manages BEAST-owned development services on Linux loopback. It does
not terminate unknown, privileged, production, or non-BEAST processes.

### 14.2 Execution

```text
service start returns EADDRINUSE
  -> snapshot Port Lease Registry
  -> query socket inventory
  -> bind socket inode/identity to ProcessLease
  -> recheck pidfd/start identity to close the race
  -> classify owner and service health
  -> lattice chooses one bounded branch:
       reuse healthy registered service
       allocate alternate leased port
       gracefully retire confirmed stale BEAST service
       request approval for anything destructive
       refuse unknown/privileged owner
  -> apply through Port Lease Broker/process supervisor
  -> verify listener identity and generation
  -> verify health contract
  -> reconcile registry
  -> verify no orphan cgroup descendants
  -> close and seal RuntimeEpisode
```

Every observation used for a decision is revalidated immediately before a
mutation. If the listener disappears or ownership changes, the branch aborts
and restarts from inventory.

### 14.3 Held-out matrix

Required variants:

- IPv4 and IPv6 listeners;
- dual-stack wildcard behavior;
- stale BEAST process;
- healthy registered shared service;
- Docker-published port;
- process exits during inspection;
- listener disappears and PID is reused;
- multiple `SO_REUSEPORT` listeners;
- unknown privileged process;
- port appears available but the health check fails;
- registry says free while kernel says occupied;
- registry says leased while kernel says free;
- child process retains the listener after parent exit;
- permission prevents owner attribution;
- high CPU, memory, or I/O pressure delays nonurgent repair;
- concurrent requests seek the same port;
- rollback after alternate-port startup failure.

### 14.4 Objective success criteria

- the intended service is listening and healthy;
- the listener maps to the expected ProcessLease and generation;
- no unrelated process is killed or degraded;
- any retired process was positively identified and authorized;
- registry and physical reality agree;
- no governed orphan descendants remain;
- all required receipts are present and hashes verify;
- race, ambiguity, or insufficient privilege causes safe refusal;
- held-out results meet the existing crystallization promotion thresholds;
- a later eligible recurrence is repaired without a cloud call.

## 15. Runtime Observatory

The IDE should show causal projections, not raw syscall rain.

Views:

### Process Forest

Show process lease, parent/cgroup, executable digest, trust, workspace, current
mission/crystal, CPU/memory/pressure, sockets, and exit state.

### Socket Constellation

Show service-role edges among local processes, providers, Commons nodes, and
deception routes. Encode local/remote, attested/unattested, encrypted,
unstable/suppressed, and deception state separately.

### Crystal Formation Chamber

Show observations, clean replays, held-out results, false hits, boundary
narrowing, cloud displacement, median resource saving, and promotion blockers.

### Lattice Heat View

Show successful cells, stale cells, negative applicability regions, disputed
equivalence classes, high-friction routes, candidate forks, and unavailable
verifiers.

### Time-travel mission view

Render episode milestones and allow drill-down to signed event references.
Default presentation aggregates; raw events require explicit forensic access.

The UI consumes a read model. It does not connect directly to privileged sensor
or actuator sockets.

## 16. Module ownership

Proposed additions:

```text
app/kernel/sensorium/
  event_contract.py
  event_sequencer.py
  bpf_event_ring.py
  process_sensor.py
  socket_sensor.py
  file_sensor.py
  pressure_sensor.py
  cgroup_sensor.py
  episode_builder.py
  sensor_policy.py
  read_model.py

app/kernel/execution/
  process_lease.py
  process_capsule.py
  epoll_constellation.py
  crystal_bus.py
  sealed_capsule.py
  crystal_executor.py

app/kernel/compute/
  crystal_ir.py
  runtime_crystallizer.py
  crystal_generalizer.py
  lattice_hypergraph.py
  equivalence_engine.py
  lattice_extractor.py
  heldout_replayer.py
  crystal_materializer.py

app/kernel/networking/
  socket_identity.py
  port_lease_broker.py
  socket_inventory.py
  listener_selector_lab.py
```

Existing module adaptations:

- compression pipeline: canonical event and episode projections;
- interceptors: structured SensorEvent producers;
- semantic cache and pages: candidate and artifact nodes;
- generative crystals: migration adapter to Crystal IR candidates;
- mission lattice: TaskPattern candidate index;
- capability crystallization: promotion/demotion authority;
- crystal forks: canonical experiment-state controller;
- reuse gateway: constrained extractor front door;
- runtime boundary: call Crystal Executor rather than execute arbitrary payload;
- evidence bridge: publish episode/crystal receipts to the evidence graph;
- telemetry outbox: downstream export sink.

## 17. Phased implementation

### Phase S0: terminology, contracts, and claim boundary

Implementation status: completed on 2026-07-14. The contract implementation,
ADRs, migration adapter, test record, and subsequent progress are tracked in
[`docs/beast-sensorium-crystals/PROGRESS.md`](beast-sensorium-crystals/PROGRESS.md).

Deliver:

- artifact taxonomy and authority enum;
- SensorEvent, RuntimeEpisode, ProcessLease, SocketIdentity, and Crystal IR
  schemas;
- schema registry and canonical hashing rules;
- ADRs for observation/actuation separation, PID identity, bus transport,
  capsule immutability, and equivalence soundness;
- adapters that label all existing crystal-like artifacts.

Exit:

- no runtime object called a crystal lacks artifact class and authority;
- existing tests preserve behavior;
- schemas have positive, negative, and forward-version fixtures.

### Phase S1: read-only Sensorium spine

Implementation status: completed on 2026-07-14. The delivery includes bounded
ordering, explicit displacement events, privacy-before-admission, RuntimeEpisode
assembly, atomic downstream export, BEAST-owned adapters, normal PREC lifecycle
observation, and a payload-free read model/API.

Deliver:

- in-process event sequencer with bounded queues and loss events;
- BEAST-owned process, Port Lease, interception, pressure, and file-effect
  adapters;
- episode correlation and read-only filesystem exporter;
- privacy/redaction gate before persistence;
- Observatory read model API without privileged actions.

Exit:

- a normal BEAST mission produces a complete, hash-stable episode;
- forced queue overflow is visible;
- sensor failure does not stop the governed workload or become silent success;
- TelemetryOutbox is demonstrably downstream.

### Phase S2: process identity and cgroup capsules

Implementation status: completed on 2026-07-14. The delivery includes
content-bound `/proc` identity, pidfd-backed ProcessLeases, epoll exit
observation, pidfd-only authorized signals, read-only cgroup v2 discovery,
authorized mission-capsule lifecycle receipts, orphan inspection,
graceful-first cleanup, Sensorium lifecycle events, Canon schemas, and a
read-only process-plane capability API. Existing-process attachment detects
identity drift around `cgroup.procs`; direct birth with
`clone3(CLONE_INTO_CGROUP)` remains later hardening.

Deliver:

- pidfd-backed ProcessLease supervisor;
- epoll lifecycle monitoring;
- cgroup v2 mission capsules with capability discovery;
- population, pressure, freeze, and kill receipts;
- orphan detection and graceful-first cleanup.

Exit:

- PID reuse tests cannot bind a new process to an old lease;
- concurrent forks cannot escape authorized capsule cleanup;
- destructive cgroup kill always requires the right bucket and approval.

### Phase S3: SocketIdentity and Port Lease Broker

Deliver:

- broker-issued listener generations and lease receipts;
- socket inventory via `NETLINK_SOCK_DIAG` plus compatibility correlation;
- process/socket/workspace/mission attribution;
- health and reconciliation state machine;
- concurrency and stale-lease tests.

Exit:

- BEAST-owned services never silently seize a known port;
- kernel inventory and registry disagreements are visible and repairable;
- unknown owners cause safe refusal.

### Phase S4: Crystal Bus and sealed capsules

Deliver:

- versioned SOCK_SEQPACKET protocol;
- peer identity handshake and capability lease binding;
- SCM_RIGHTS handling with strict ancillary limits;
- sealed memfd materializer and verifier;
- declarative no-loop Crystal Executor skeleton.

Exit:

- altered, unsealed, oversized, stale, replayed, or wrong-peer capsules fail;
- descriptor leaks and truncation cases pass stress tests;
- capsule transfer cannot elevate authority.

### Phase S5: Runtime crystallizer and typed hypergraph

Deliver:

- causal episode builder and normalization;
- structural generalizer and parameter inference;
- typed SQLite hypergraph with evidence provenance;
- migration adapters for mission and generative crystals;
- constrained extractor and decision receipts;
- negative applicability integration.

Exit:

- repeated natural episodes create a bounded candidate without synthetic retry
  tokens;
- incidental values parameterize while causal identities remain constrained;
- failed variants narrow or demote the candidate.

### Phase S6: Port Conflict Repair end-to-end proof

Deliver:

- complete Crystal IR and bounded opcodes;
- isolated replay harness and held-out matrix;
- broker/process supervisor actuators;
- independent listener, health, registry, and orphan verifiers;
- capability promotion and cloud-displacement evidence;
- Observatory views for the proof.

Exit:

- all objective success criteria in section 14 pass;
- destructive and ambiguous cases safely refuse;
- one later recurrence is resolved locally by a promoted crystal.

### Phase S7: equality engine laboratory

Deliver:

- small deterministic Crystal IR expression language;
- versioned, verified rewrite registry;
- bounded e-graph saturation and cost-vector extraction;
- equivalence and counterexample receipts;
- resource and node-count circuit breakers.

Exit:

- every selected equivalence has a proof/verifier chain;
- saturation cannot bypass policy or applicability;
- timeout returns the best already-valid plan or safely falls back.

### Phase S8: advanced physical optimization

Deliver only after the proof is stable:

- DAMON-informed MemoryProfiles;
- restricted `process_madvise()` experiments;
- BPF lifecycle correlation;
- BPF socket lookup/reuseport candidate forks;
- AF_XDP attribution path;
- NUMA/cache-local scheduling hints.

Exit:

- every optimization has a measured baseline, rollback, feature detection, and
  safe fallback;
- no experimental kernel path enters the production boot chain by default.

## 18. Verification strategy

Test layers:

- contract and canonical-hash tests;
- event ordering, loss, clock, and boot-boundary tests;
- PID reuse, exit/reap, namespace, and descriptor exhaustion tests;
- cgroup population, fork race, freeze, graceful exit, and kill tests;
- socket inventory race and attribution tests;
- bus peer-spoof, replay, flood, truncation, and FD leak tests;
- memfd seal, mutation, replacement, size, and signature tests;
- episode normalization and causal-ablation tests;
- crystal false-hit and applicability-boundary tests;
- destructive-path approval coverage tests;
- hypergraph constraint and negative-capability tests;
- equivalence-rule soundness and saturation-bound tests;
- held-out system integration tests;
- restart, crash recovery, and evidence-chain verification.

Fault injection must cover missing privileges, unsupported kernel features,
event drops, process exit during inspection, stale attestation, policy rotation,
health-probe ambiguity, registry corruption, disk full, memory pressure, and
Crystal Bus peer death.

## 19. Metrics

Correctness and safety:

- episode completeness and unattributed-event rate;
- sensor loss rate by source;
- ProcessLease misbinding count, target zero;
- crystal false-hit and unsafe-action counts;
- ambiguous cases safely refused;
- postcondition verification and rollback success rates;
- equivalence rules with complete proof chains.

Economy:

- cloud calls and tokens displaced;
- repair steps and median latency avoided;
- Sensorium CPU, memory, I/O, and storage overhead;
- bus copies and descriptor lifetime;
- crystal extraction and verification cost;
- PSI stall added or avoided;
- cache/KV/crystal/local-model/cloud route shares.

Lifecycle health:

- candidates by state and age;
- held-out coverage;
- promotion precision and demotion rate;
- stale, revoked, and negative applicability hits;
- policy and attestation freshness;
- evidence graph completeness.

## 20. Principal risks

Sensor overhead: start with BEAST-owned scopes, bounded events, adaptive detail,
and measured loss. Do not attach every possible hook on day one.

Privacy leakage: default to identities, hashes, and scoped metadata; make raw
command, path, content, and packet retention explicit and short-lived.

False causality: retain loss markers, compare negative episodes, use independent
postcondition verifiers, and require held-out variation.

PID/socket races: use pidfds, start times, listener generations, and revalidate
immediately before mutation.

Authority confusion: artifact class and authority are mandatory; immutable
transport, similarity, verification history, and attestation are separate
properties.

Kernel-version drift: feature-detect, version adapters, and keep `/proc`,
user-space, and normal-scheduler fallbacks.

E-graph unsoundness or explosion: accept only reviewed rewrite rules, bound
time/nodes, and keep equality optimization downstream of hard constraints.

Evidence volume: retain the signed episode root and required evidence; compact
or tier raw events by policy without breaking referential integrity.

Bus compromise: use pathname permissions, peer credentials, process identity,
attestation, leases, bounded queues, and message replay protection together.

## 21. Recommended immediate sequence

1. Ratify the taxonomy and Crystal IR authority boundary.
2. Implement SensorEvent and RuntimeEpisode schemas without privileged sensors.
3. Instrument the existing inference/streaming interceptors, Port Lease work,
   process supervisor, and PSI governor as event producers.
4. Implement pidfd ProcessLease and SocketIdentity correlation for BEAST-owned
   development services.
5. Build the Port Lease Broker user-space state machine.
6. Capture several naturally occurring port-conflict episodes, including
   failures and safe refusals.
7. Hand-author the first Port Conflict Repair Crystal from those episodes.
8. Prove isolated replay and the held-out matrix.
9. Only then automate candidate extraction/generalization.
10. Add sealed capsules after the declarative IR and executor contract settle.
11. Add equality saturation and BPF-selectable listeners last.

Hand-authoring the first crystal is intentional. It validates the sensing,
identity, execution, authority, and evidence contracts before asking a
generalizer to infer them.

## 22. Decision

Proceed with the Sensorium and proof-carrying compute crystal program as a
companion track to the broader BEAST DevSecOps/Commons/ARDA roadmap.

The current systems should be composed, not renamed into false completeness:

- compression canonicalizes;
- interception observes and governs route boundaries;
- caches and KV transport reuse data and model state;
- semantic pages preserve computed artifacts;
- the mission lattice retrieves analogous plans;
- generative crystals supply the bounded-template seed;
- capability crystallization owns evidence-based promotion;
- the Sensorium establishes ordered physical truth;
- Compute Crystal IR expresses a bounded transformation;
- ARDA and capability leases authorize execution;
- independent verifiers prove the effects;
- the evidence graph makes the complete chain auditable.

That is the point at which BEAST's lattice becomes a living map of computational
causality rather than a metaphor for similarity.

## 23. Primary technical foundations

- Linux pidfds: <https://man7.org/linux/man-pages/man2/pidfd_open.2.html>
- Descriptor duplication through pidfds:
  <https://man7.org/linux/man-pages/man2/pidfd_getfd.2.html>
- Remote memory advice:
  <https://man7.org/linux/man-pages/man2/process_madvise.2.html>
- Anonymous sealed files:
  <https://man7.org/linux/man-pages/man2/memfd_create.2.html>
- UNIX-domain credentials, sequenced packets, and descriptor passing:
  <https://man7.org/linux/man-pages/man7/unix.7.html>
- cgroup v2 population, freeze, kill, and pressure:
  <https://docs.kernel.org/admin-guide/cgroup-v2.html>
- BPF local socket selection:
  <https://docs.kernel.org/bpf/prog_sk_lookup.html>
- `egg` and equality saturation:
  <https://doi.org/10.1145/3434304>
