# BEAST DevSecOps, Compute, Commons, ARDA, and Control Evidence Master Plan

Date: 2026-07-14  
Status: Phased implementation in progress; production exit gates remain  
Scope: BEAST, Metatron Triune Outbound Gate, ARDA, Seraph, Commons nodes,
local repositories, source-control providers, CI runners, artifact stores,
deployment targets, and audit-evidence consumers.

## 1. Executive Decision

This roadmap has a lower-level implementation companion for BEAST's existing
compression, interception, cache, semantic-page, crystal, and lattice systems:
[BEAST Sensorium and Proof-Carrying Compute Crystal Plan](beast-sensorium-proof-carrying-crystal-plan.md).
That companion defines the ordered Sensorium, RuntimeEpisode, ProcessLease,
SocketIdentity, Crystal Bus, sealed capsule, typed hypergraph, and first Port
Conflict Repair Crystal proof. Its artifact taxonomy and authority boundaries
are normative for any implementation described here as crystallized compute.
Companion phases S0 through S12 are implemented as repository foundations;
S13 production hardening is in progress. The exact designed/implemented/tested/
live boundary is measured in
[the 2026-07-15 evidence readiness audit](beast-enterprise-evidence-readiness-audit-2026-07-15.md).

The existing Metatron Triune Outbound Gate and ARDA implementation has now been
inspected read-only and mapped into this roadmap. The normative integration,
maturity gaps, cross-system contracts, and MA0–MA6 hardening sequence are in
[Metatron, ARDA, and BEAST Integration Assessment](metatron-arda-beast-integration-assessment.md).

BEAST should evolve into a local-first DevSecOps change, release, compute, and
evidence control plane. It should sit above repositories, source-control
providers, CI systems, build runners, deployment targets, Commons nodes, model
providers, and local tools without pretending to replace all of them.

The governing thesis is:

> CI can show that a pipeline ran. BEAST should prove why it was permitted to
> run, which identities and policies authorized it, which exact inputs it used,
> which evidence it produced, which immutable artifact was approved, whether
> that exact artifact was deployed, and whether the running workload remains
> attested and policy-conformant.

The target operating chain is:

```text
Developer / AI agent
  -> BEAST Change Governor
  -> Task Envelope + SourcePlan + risk classification
  -> isolated Worktree Forge mission
  -> deterministic checks, tests, scans, SBOM, and provenance
  -> independent verification
  -> human or policy approval
  -> signed immutable artifact
  -> attested deployment target
  -> ARDA execution permission
  -> Metatron consequential-action gate
  -> Seraph runtime observation
  -> BEAST Control Evidence Graph
  -> SOC 2 readiness and audit evidence package
```

This is an evolutionary extension of BEAST's existing canonical boundaries.
It must not create competing authorities for mutation, evidence, capability
selection, or compute routing.

## 2. Claim Boundaries

### 2.1 What BEAST may claim

When implemented and evidenced, BEAST may describe itself as:

- a DevSecOps change and release control plane;
- a software-supply-chain policy and provenance orchestrator;
- a local-first resource admission and compute-governance plane;
- a governed Commons artifact and job exchange;
- an ARDA-aware relying party for measured workload identity;
- SOC 2 readiness, control orchestration, and continuous evidence
  infrastructure;
- a system for producing auditor-consumable control evidence and exception
  reports.

### 2.2 What BEAST must not claim

BEAST must not claim that:

- installing BEAST makes an organization SOC 2 compliant or certified;
- BEAST can issue a SOC 2 report;
- a pipeline receipt proves the operating effectiveness of a control over an
  audit period by itself;
- an attestation proves a workload is harmless;
- a signature proves that an artifact is correct;
- a model-generated verdict is equivalent to an independent control owner;
- a local mock TPM, simulated cloud witness, or development bypass constitutes
  production attestation;
- SLSA, in-toto, Sigstore, SPDX, CycloneDX, RATS, EAT, or SPIFFE conformance
  exists until the corresponding schemas and verification behavior are
  implemented and tested.

An independent qualified practitioner performs a SOC 2 examination and issues
the report. Management defines the system, scope, commitments, risks, controls,
and assertions. BEAST can operate controls and preserve evidence; it does not
replace management or the auditor.

## 3. Architectural Principles

1. **One authority per concern.** Existing canonical owners remain canonical.
2. **Models propose; deterministic systems authorize and execute.**
3. **An artifact digest, not a branch name or mutable tag, crosses the release
   boundary.**
4. **Attestation is appraised evidence, not a self-asserted Boolean.**
5. **Pressure changes admission, never authorization.** Resource availability
   cannot grant a capability that policy denied.
6. **Trust and availability are different dimensions.** A recovered endpoint
   is not automatically a trusted endpoint.
7. **Shadow before enforcement.** New governors collect counterfactual evidence
   before suppressing, throttling, evicting, or denying work.
8. **Fail closed at authority boundaries, degrade gracefully at optimization
   boundaries.** Missing attestation blocks an attestation-required production
   deployment; missing resctrl support merely disables cache allocation.
9. **Evidence is immutable; indexes are rebuildable.** The Evidence Graph may
   be reconstructed from signed source receipts.
10. **Local reproduction creates authority.** Remote Commons contributions
    remain hypotheses until locally verified and approved.
11. **No hidden bypasses.** Development and simulation modes are explicit,
    visibly labelled, and cryptographically distinguishable from production.
12. **Privacy is part of provenance.** Receipts retain hashes, decisions, and
    bounded metadata instead of prompts, secrets, private source, or protected
    dataset rows unless policy explicitly requires encrypted retention.

## 4. Canonical Ownership Model

| Concern | Canonical owner | Important adapters or inputs |
| --- | --- | --- |
| Code context | Code Cortex | Workspace Graph, repository-family graph, local indexes |
| Source mutation | SourcePlan | Action IR, workbench, policy and verifier results |
| Change isolation | Worktree Forge | Git worktrees, ephemeral developer lanes |
| Normalized authorization | Policy Gate Result | Mode Router, Spec Covenant, Safety Governor, Agent Passport |
| Tool visibility and invocation | Tool Lease Governor | CapabilityPlane, mode, risk, ARDA identity, approval |
| Semantic compute decision | Compute Governor | Reuse, deterministic transforms, local/cloud inference |
| Resource admission | Resource Admission Governor | PSI, cgroups, workload envelopes, thermal/battery policy |
| Compute route planning | Agent Scheduler | Provider Economist, local engines, Commons candidates |
| Process execution | Resource Executor | Async, threads, processes, dedicated inference queues |
| Release governance | Release Governor | Source, build, verification, approval, provenance receipts |
| Artifact custody | Commons Artifact Vault | CAS, snapshots, manifests, signatures, OCI/ORAS adapter |
| Dataset access | Dataset River | Parquet/Arrow, filters, lineage, privacy labels |
| Node/workload attestation | ARDA verifier | TPM, secure boot, workload digest, event log, cloud evidence |
| Consequential outbound action | Metatron Outbound Gate | ARDA result, capability lease, governance epoch, transport |
| Runtime defense | Seraph | Behavioral observation, friction, containment, incidents |
| Network service identity | Port Lease Broker | Local DNS, reverse proxy, health, process identity |
| Evidence discovery | Control Evidence Graph / Evidence Bus | Pointers to native immutable receipts |
| Audit packaging | Control Evidence Exporter | Scoped graph queries, exceptions, retention and redaction |

The Control Evidence Graph extends the existing Evidence Bus. The Bus remains
a privacy-safe pointer index. Native SourcePlan, Chronicle, ARDA, Seraph,
Commons, build, and deployment receipts remain the durable proof objects.

## 5. Target Control Planes

### 5.1 Change and Release Control Plane

This plane governs the complete transition from intent to running workload:

```text
intent
  -> task envelope
  -> source context
  -> SourcePlan
  -> isolated worktree
  -> change verification
  -> source approval
  -> build request
  -> immutable artifact + provenance
  -> independent artifact verification
  -> release approval
  -> deployment by digest
  -> ARDA execution admission
  -> runtime observation and reconciliation
```

Every transition has an explicit input contract, decision, status, signer or
authenticated actor, timestamp, policy version, and evidence relationship.

### 5.2 Resource Admission Plane

The Resource Admission Governor answers:

> Given an already-authorized workload, should it start now, wait, run with
> reduced concurrency, move to a different lane, or be rejected because its
> resource deadline cannot be honored?

It consumes workload declarations, PSI, cgroup state, queue depth, thermal and
battery policy, optional resctrl observations, provider stability, and operator
lane reservations. It emits an admission receipt and actuator instructions.

It is separate from the semantic Compute Governor, which answers whether
probabilistic inference is needed at all.

### 5.3 Capability and Trust Plane

CapabilityPlane discovers capabilities. Tool Lease Governor decides which are
visible and invocable for one request. ARDA supplies measured node/workload
identity. Policy Gate supplies BEAST authorization. Metatron gates consequential
outbound effects.

No single score may erase a hard veto. Trust decisions use structured reasons:

- identity verified or unverified;
- boot/workload attestation accepted, expired, or rejected;
- capability allowed, approval-required, or denied;
- transport verified or unverified;
- behavioral state stable, strained, dissonant, or quarantined;
- resource state admitted, delayed, degraded, or unavailable.

### 5.4 Artifact and Data Plane

Commons stores and exchanges content-addressed artifacts, manifests, cards,
snapshots, chunks, signatures, attestations, and verification receipts. Dataset
River supports filtered and streamed access. Space Forge packages signed
runnable workloads. Job Choir selects eligible attested nodes. Witness Ledger
connects scheduling, execution, output, and reproduction evidence.

### 5.5 Network Identity Plane

Port Lease Broker owns local service ports and service identity. Local DNS is a
projection of live leases and trust state. Reverse proxying maps friendly `.test`
names to leased upstreams. Optional VRFs and network namespaces create stronger
trust-domain separation. AF_XDP remains an experimental Seraph observation
entrance rather than an AI decision point in kernel space.

## 6. DevSecOps Lane Model

### 6.1 Developer Lane

Purpose: coding, documentation, linting, unit tests, local analysis, and
SourcePlan preparation.

Default controls:

- isolated BEAST worktree for risky, parallel, or AI-authored changes;
- no production credentials;
- restricted outbound network;
- read-only mounts for approved datasets and reference artifacts;
- local CPU-first diagnostics;
- bounded tool bucket, normally Observe, Reason, Verify, and narrowly scoped
  Modify;
- explicit AI-generated-change marker in SourcePlan evidence;
- commit, dependency, tool-schema, and policy fingerprints;
- path-scoped mutation with rollback evidence;
- secrets scanning before promotion;
- no direct deployment authority.

Required evidence:

- task and requirement identifiers;
- authenticated human/agent identity;
- original commit and worktree branch;
- included/excluded context receipt;
- SourcePlan and policy decisions;
- changed paths and resulting digest;
- local checks and exceptions;
- AI contribution declaration;
- promotion or abandonment receipt.

### 6.2 Build Lane

Purpose: reproducibly convert an approved source revision and locked inputs into
immutable artifacts.

Default controls:

- ephemeral runner;
- pinned builder identity and toolchain;
- immutable source revision;
- locked dependency inputs;
- no interactive shell by default;
- no access to deployment credentials;
- content-addressed inputs and outputs;
- controlled, declared network access;
- SBOM generation;
- SLSA-shaped build provenance;
- build logs and relevant byproducts hashed and retained;
- output digest sealed before leaving the runner;
- provenance signing key inaccessible to tenant-controlled build steps;
- runner attestation when the target assurance level requires it.

The build output is a tuple, not merely a file:

```text
artifact digest
+ builder identity
+ source revision
+ build definition
+ resolved dependencies
+ SBOM digest
+ provenance envelope
+ policy and exception state
```

### 6.3 Verification Lane

Purpose: independently decide whether a built artifact satisfies release
expectations.

Default controls:

- separate identity and execution context from the build lane;
- verify artifact and provenance signatures;
- compare subject digest to the build output;
- verify expected builder, build type, inputs, and parameters;
- inspect SBOM and vulnerability-policy results;
- repeat critical tests;
- scan secrets, dependencies, containers, and infrastructure definitions;
- validate licensing and prohibited components when in scope;
- reproduce selected high-risk builds using an independently operated builder;
- record nondeterminism explicitly rather than hiding it;
- produce a verification summary attestation or BEAST equivalent;
- forbid verification results from mutating the artifact under review.

### 6.4 Deployment Lane

Purpose: place an approved immutable artifact into a declared environment.

Deployment accepts a release envelope such as:

```yaml
artifact_digest: sha256:...
source_commit: ...
build_receipt: receipt://...
verification_receipt: receipt://...
approval_receipt: receipt://...
target_environment: production
target_identity: arda://node/...
allowed_configuration_hash: sha256:...
policy_version: ...
rollback_artifact_digest: sha256:...
```

Default controls:

- deploy by digest, never by mutable tag alone;
- environment-scoped credentials supplied only to the deployment controller;
- two-person approval where policy requires it;
- separation between source approver, builder, verifier, and deployer for
  high-impact systems;
- target attestation freshness check;
- configuration digest verification;
- canary or staged rollout for eligible services;
- automatic reconciliation of requested versus observed digest;
- rollback readiness test and bounded rollback objective;
- deployment and rollback receipts.

### 6.5 Runtime Lane

Purpose: ensure the deployed object remains the approved object and operates
within declared policy.

Default controls:

- ARDA allows execution only for approved workload digests in protected lanes;
- ARDA attestation results are short-lived and audience-bound;
- Seraph observes behavior, identity drift, anomalous egress, privilege changes,
  and campaign relationships;
- BEAST reconciles approved, deployed, and observed digests;
- resource pressure is monitored before service failure;
- material drift creates an incident or quarantine event;
- expired attestation removes job/deployment eligibility;
- privileged runtime actions pass through Metatron Outbound Gate;
- rollback, containment, and recovery events enter the Evidence Graph.

## 7. Tool Bucketing and Capability Leases

The universal buckets are:

1. Observe: search, inspect, read, list, status.
2. Reason: retrieve bounded context, calculate, classify, compare.
3. Verify: test, lint, simulate, validate, scan.
4. Modify: patch, write, transform, package.
5. Connect: API, browser, email, database, remote host.
6. Execute: deploy, trade, contain, upload, merge.
7. Administer: secrets, policies, identities, privileged system actions.

Bucket selection is compiled from task phase, risk, mutation intent, data
classification, network need, workspace, prior failures, and current approval.
The model does not grant its own buckets.

Schema visibility and invocation authority are distinct. Hiding unused schemas
reduces context; the gateway still validates the lease on invocation.

A tool lease binds:

- lease ID and version;
- principal and ARDA identity result;
- workspace, repository family, and worktree;
- task, phase, and job;
- allowed buckets and exact tool/schema hashes;
- target paths, hosts, datasets, and environments;
- network and secret scopes;
- maximum calls, resource budget, and expiration;
- policy, approval, and governance epoch identifiers;
- revocation and evidence destinations.

Administrative, deployment, destructive, financial, identity, and production
secret operations require explicit capabilities even if their schemas become
visible accidentally.

## 8. Context-Aware Execution and PSI Compute Breathing

### 8.1 Workload declaration

Every executable job declares a resource profile:

```yaml
workload:
  class: document_parse
  trust_lane: verification
  cpu_weight: high
  io_weight: medium
  memory_mb: 750
  latency: background
  isolation: process
  executor_hint: process
  exclusive_keys: [client_job_142]
  timeout_seconds: 180
  checkpointable: true
  disposable_cache: true
```

### 8.2 Executor selection

- Network, filesystem, browser, and API waits use async I/O or bounded threads.
- Python CPU calculations and document parsing use processes.
- Isolated interpreters are capability-probed and remain optional until the
  supported Python runtime and dependencies are compatible.
- Stateful or hazardous actions are serialized.
- Local inference uses a dedicated model queue.
- UI/operator work uses a reserved interactive lane.
- Security experiments prioritize isolation over throughput.

### 8.3 PSI policy

PSI observations are global and per cgroup. Use threshold-triggered polling for
fast response and interval samples for trend evidence.

```text
low pressure
  -> admit local inference, verification, and indexing

rising CPU some pressure
  -> delay summaries, speculative agents, and background indexing

memory some/full pressure
  -> reduce model concurrency, evict disposable caches, pause new hydration

I/O some/full pressure
  -> merge scans, slow artifact hydration, prefer cached manifests

sustained full pressure or missed interactive SLO
  -> preserve operator, security, recovery, and evidence lanes only
```

System-wide CPU `full` is not a useful admission signal; CPU `some` and
per-cgroup signals should drive CPU policy. All thresholds require host-class
calibration.

### 8.4 Anti-oscillation and fairness

- separate enter and exit thresholds;
- minimum dwell and cooldown times;
- concurrency changes by one bounded step at a time;
- guaranteed operator and security reservations;
- maximum starvation time for background work;
- checkpoint or cancel only if the workload declares support;
- never kill evidence writers before their durable receipt boundary;
- record pressure, decision, actuator, latency, and outcome.

### 8.5 Target systems

- BEAST local inference, Code Cortex, verification, and indexing;
- Evidex/HOMS document processing;
- Seraph forensic workers;
- Metatron test buckets;
- Hivenance market-data and analytical workers;
- Commons node jobs and artifact transfer.

## 9. Advanced CPU and Memory Integrations

### 9.1 resctrl lanes

On supported hardware, monitor last-level-cache occupancy and memory bandwidth
before enforcing allocations. Candidate lanes are operator/UI, security,
inference, background indexing, Commons community jobs, and deception.

Important limitation: memory bandwidth allocation is normally a throttling
ceiling, not a guaranteed floor. A security "floor" is achieved by reserving
capacity and constraining competing lanes. Cache masks and bandwidth behavior
must be topology-aware.

Rollout:

1. capability probe and topology card;
2. monitor-only occupancy and bandwidth receipts;
3. replayed workload calibration;
4. operator/background separation experiment;
5. narrowly scoped allocation enforcement;
6. automatic disable on unsupported or anomalous behavior.

### 9.2 sched_ext Harmonic Scheduler

Keep sched_ext in a laboratory branch. Simulate dispatch queues and policy with
ordinary cgroups before loading a BPF scheduler.

Candidate queues:

- `DSQ_OPERATOR`
- `DSQ_SECURITY`
- `DSQ_LOCAL_INFERENCE`
- `DSQ_VERIFICATION`
- `DSQ_COMMONS_VOLUNTEER`
- `DSQ_BACKGROUND`
- `DSQ_QUARANTINE`

Inputs may include PSI, task class, urgency, provider availability, thermal
policy, Seraph discord, and ARDA trust state. Trust determines eligible queues;
it must not become a fuzzy scheduling weight that permits forbidden work.

Promotion requires a pinned lab kernel, watchdog and automatic fallback,
reproducible latency tests, starvation tests, and proof that operator/security
latency improves without destabilizing the host.

### 9.3 DAMON heat routing

DAMON provides sampled access-aware regions, not a perfect per-page oracle.
Begin with monitor-only heat classifications:

```yaml
memory_classes:
  operator: {residency: protected}
  active_model: {residency: hot}
  active_repo_index: {residency: warm}
  inactive_worktree: {residency: cold}
  community_job: {residency: reclaimable}
  deception_artifact: {residency: disposable}
```

Only reconstructible or explicitly disposable memory may be reclaimed
automatically in early enforcement. Migration/pageout schemes require quotas,
watermarks, and reversal tests.

### 9.4 Shared read-only model-page vault

The Model Vault verifies shards and manifests, exposes immutable file-backed
mappings, records runtime/format compatibility, and lets the kernel page cache
share touched pages naturally. It tracks mapped, resident, faulted, and evicted
bytes by model and trust class.

Do not use KSM across unrelated trust domains. Explicit mappings are preferred.
Runtimes that copy, dequantize, or transform weights privately must declare that
behavior so sharing claims remain honest.

### 9.5 Compressed pressure buffer

Treat zswap as a host capability and measured trade rather than extra RAM.
Receipts should report compressed pool size, compression ratio where available,
CPU cost, swap I/O avoided, writeback, rejection, and latency. Enabling or
changing zswap remains an operator-approved host action.

### 9.6 Negative capability memory

Store signed, scoped, TTL-bound negative results for unavailable models,
unsupported schemas, dead endpoints, missing optional files, denied
capabilities, incompatible artifacts, and absent hardware features.

The key includes subject, scope, policy version, hardware fingerprint, provider
configuration, reason class, first/last observation, expiry, and evidence. A
permanent incompatibility and a transient outage use different TTL and
invalidation policies.

## 10. Provider and API Reliability

### 10.1 Route-flap damping

Extend the current binary circuit breaker into independent penalty dimensions:

- availability: timeouts, 429s, transient service errors;
- contract: invalid schemas, malformed streams, phantom success;
- correctness: verifier-confirmed incorrect results;
- trust: identity, signature, or attestation failure.

Availability penalties decay relatively quickly. Contract and correctness
penalties decay more slowly. Trust penalties require fresh trusted evidence or
explicit recovery; successful health calls do not erase them.

Suggested initial penalty examples remain hypotheses until replay-calibrated:

```text
timeout              +200 availability
HTTP 429             +100 availability
invalid schema       +250 contract
incorrect result     +500 correctness
attestation failure +1000 trust
```

Thresholds create healthy, cautious, degraded, and suppressed routing states.
Each transition emits evidence, explains decay, and preserves manual recovery.

### 10.2 In-flight call coalescing

Single-flight identical safe requests such as manifests, repository summaries,
package metadata, status checks, and Commons advertisements.

The key includes provider, endpoint, canonical request hash, authorization
scope, workspace, privacy class, model/parameters, and freshness window.

Requirements:

- callers from different authorization/privacy scopes never coalesce;
- one caller cancellation does not cancel work needed by others;
- failures have bounded negative caching and do not create retry storms;
- mutating or non-idempotent calls are excluded unless an idempotency key and
  action contract make sharing safe;
- coalescing receipts report attached callers and avoided calls without
  exposing private request content.

### 10.3 Attested API sessions

ARDA should act as evidence producer and verifier; BEAST acts as relying party.

```text
node/workload
  -> nonce-bound ARDA evidence
  -> ARDA verification result
  -> BEAST workspace/job policy
  -> capability-scoped session token
  -> API gateway enforcement
```

The token binds node identity, boot/workload measurement, allowed capability,
job, output bucket, audience, expiration, resource ceiling, and governance
receipt. Raw TPM evidence should not be interpreted independently by every
BEAST service.

## 11. ARDA and Metatron Integration Contract

### 11.1 Roles

- ARDA Attester: collects TPM, secure-boot, event-log, workload, and node
  identity evidence.
- ARDA Verifier: validates signature, nonce, freshness, baseline, event-log
  reconstruction, revocation, and environment policy.
- BEAST Relying Party: decides what an accepted ARDA result authorizes for a
  workspace, tool, build, deployment, or Commons job.
- Metatron Outbound Gate: applies consequential-action, governance-epoch,
  transport, and approval rules.
- Seraph Observer: supplies behavioral evidence and containment outcomes.

### 11.2 ARDA Attestation Result v1

The versioned result should contain:

- result ID, issuer, version, and issued/expiry times;
- subject node and workload identities;
- evidence type and evidence digest;
- nonce/challenge binding;
- boot, secure-boot, event-log, and workload appraisal results;
- accepted reference-value/policy version;
- environment and assurance class;
- audience and permitted relying-party scope;
- warnings and non-fatal gaps;
- explicit simulation/mock indicator;
- revocation/status endpoint or epoch;
- cryptographic signature and verification material.

BEAST stores the result and evidence digest, not necessarily all sensitive raw
measurements.

### 11.3 Hardening prerequisites

Before production enforcement:

- remove default secrets and demo cryptography;
- perform actual Sigstore or local public-key verification;
- sign every authority-bearing token field;
- replace XOR secret storage with an approved authenticated-encryption/vault
  implementation;
- persist replay counters, revocation, and token consumption atomically;
- verify remote quotes, nonce, AK identity, PCR/event-log policy, freshness, and
  claimed workload binding;
- protect node private keys with TPM/HSM or strong filesystem and encryption
  controls;
- make production configuration incapable of enabling development bypasses;
- distinguish simulated, observed, and enforced evidence cryptographically;
- mutation-test each verifier fail-closed path.

### 11.4 Existing implementation adoption

Preserve and adapt the existing governance epoch, notation token, Outbound
Gate, Ainur Choir, TPM/formation/covenant, ARDA Fabric, BPF LSM, Mandos/Lórien,
and live isolation/rejoin boundaries. Do not treat their current presence as a
production attestation claim. The detailed assessment classifies which parts
are reusable and identifies mandatory replacements, including self-reported
remote attestation, label-only Sigstore acceptance, default HMAC secrets,
mock-safe required witnesses, gate-side authority minting, silent human veto
overrides, substring egress allowlists, and legacy inode/device projection that
does not consume the content-bearing harmony manifest.

The Sovereign Proof and the Linux 6.12 target establish that the intended ARDA
design can be content-bound at Ring 0. The target exposes
`bpf_get_fsverity_digest()` to BPF LSM programs. Therefore the production
design uses a kernel-retrieved fs-verity identity (algorithm plus digest) as
the allowlist key; inode/device remains only an explicitly labeled laboratory
compatibility mode. This distinction corrects the earlier shorthand without
weakening the finding about the legacy startup loader.

### 11.5 MA0–MA6 implementation status (2026-07-14)

Implemented in the Metatron hardening branch:

- versioned evidence, appraisal, capability, and outbound-decision contracts;
- independent fail-closed quote/event-log verifier interfaces with replay
  protection;
- production rejection of default signing secrets, label-only Sigstore
  acceptance, self-reported remote attestation, and hash-only node identity;
- transactional one-use capability consumption and revocation epochs;
- canonical DNS-boundary egress matching and non-overridable break-glass
  dimensions;
- removal of the live human attestation/transport veto bypass;
- strict fs-verity LSM mode and a signed projection contract bound to
  attestation, capability, policy generation, cgroup, namespaces, and expiry;
- a capability-to-notation handoff that binds the authority request, canonical
  action, target, audience, and one-use state before notation is minted;
- removal of gate-side prerequisite authority minting, with capability vetoes
  made ineligible for human override;
- transactional notation binding and executor-side consumption, including
  concurrent single-use tests;
- a projection reconciler with monotonic generations and removal on expiry,
  revocation, replacement, or cgroup/namespace drift;
- a strict recovery coordinator requiring fresh accepted appraisal, a signed
  one-use recovery capability, target isolation, current governance/world/
  quorum epochs, and two distinct non-compromised signed witnesses; and
- an explicit production recovery-runtime factory that requires five
  operator-provisioned PEM trust roots and fails closed when any is absent;
- a read-only importer for the native live recovery proof. The current bundle
  is classified as `observed`, never as production rejoin authority.

Still required before a production claim:

- audit and migrate every secondary executor and legacy router to the bound
  capability path; the primary governed dispatch, Outbound Gate, and
  governance executor are covered;
- replace remaining mock/override measurement routes with explicitly separate
  development issuers and audiences;
- provision production signing/verifier roots for the strict recovery runtime
  and exercise the privileged actuator on a dedicated validation host;
- validate the wired pinned-map projection sink against the target kernel with
  real fs-verity files and cgroup IDs; unit/native compilation is complete but
  this session did not enable host-wide LSM enforcement; and
- complete federation, attested Commons sessions, and Control Evidence Graph
  publication across BEAST, Metatron, ARDA, Seraph, and Commons.

The MA0–MA6 regression set currently contains 84 passing tests. The native
live recovery bundle imports as 23 hashed files with bundle root
`sha256:01e57f403c28f3310915454ad0f2ce9337b43405aa05a29694a633f45e452c6f`.
That digest is evidence of the inspected local bundle, not a certification or
an authorization token.

The MA0–MA6 workstream in the integration assessment is a prerequisite track
for this plan's Phase 6 and Phase 8 production exit gates.

## 12. Port, Hostname, Routing, and Deception Architecture

### 12.1 Port Lease Broker

Ports become leased capabilities. The broker reserves/binds a port, records
service and process identity, optionally hands off a socket, registers DNS and
proxy routes, tracks health, and revokes the lease when the process exits or
identity changes.

A lease receipt contains service ID, principal, executable/workload digest,
port/socket, hostname, upstream protocol, health contract, issue/expiry time,
workspace, ARDA result, and release reason.

Start with broker-controlled reverse-proxy listeners and upstream registration.
Cross-platform socket activation and descriptor handoff can follow.

Implemented S13 extension: a separate user-mode Socket Guardian now owns the
kernel descriptors while broker, IDE, and gateway processes restart. Brokers
authenticate over `AF_UNIX/SOCK_SEQPACKET`, bind peer credentials to a validated
ProcessLease, and recover duplicated descriptors through `SCM_RIGHTS`. Listener
generations and lifecycle/health transitions are durable in SQLite; operations
bind workspace, capability, appraisal, policy generation, and service-registry
digest. Registry drift revokes the listener and signed handoff receipts record
the transfer.

This proves broker-process restart continuity. A 2026-07-15 extension also
proves Guardian replacement continuity when an external supervisor retains the
listener: the replacement adopts a duplicate and atomically advances the
listener generation. Exact Ed25519-signed one-use operation capabilities bind
mutations to ProcessLease, workspace, appraisal, policy, and registry state.
Generated user-systemd units pass unit validation but are not installed, so
host reboot continuity is not yet a live claim. High BEAST ports can use a user
service without sudo; privileged port 80 and system-wide installation remain
deployment concerns.

BEAST and Commons now implement the consumer half of this contract. Guardian
mode requests an exact signed one-use operation capability, recovers the
workspace/policy/appraisal-bound descriptor through `SCM_RIGHTS`, and passes
the already-bound socket directly to Uvicorn. A real two-PID server restart
test retained the same lease, port, and generation. The dedicated Commons
consumer also enforces an outer ASGI path boundary. Deployment keys, the live
authority endpoint, installed units, proxy activation, and reboot acceptance
remain open production gates.

2026-07-15 host-local validation update: distinct file-backed authority and
receipt keys were provisioned outside the repository, the ARDA operation
endpoint and Guardian/BEAST/Commons user services were activated, and both
consumer replacement and Guardian replacement passed continuous port-retention
checks. Listener generations advanced correctly across Guardian replacement.
The appraisal binds the reviewed Metatron sovereign-proof manifest digest but
is deliberately labelled static local validation. Actual reboot acceptance,
fresh TPM/measured-boot appraisal, managed key custody, and proxy/DNS activation
remain production gates.

### 12.2 Local names

Use reserved `.test` names such as `beast.test`, `arda.test`, and
`api.seraph.test`. A hosts file maps names only to addresses, not ports, and
does not provide dynamic wildcard trust projection. Prefer a local DNS service
plus generated NGINX or Caddy routes.

### 12.3 Cryptographic node addressing

Names such as `node-q7f3.commons.test` are projections of a signed node identity
and live trust state, not the identity itself. Publish only while advertisement,
attestation, routing state, and capability remain acceptable. DNS withdrawal
must be accompanied by token revocation and routing enforcement.

### 12.4 VRF-per-trust-domain

Candidate domains are operator, production, Commons, quarantine, deception,
and witness. VRFs separate routing tables but are not complete security
boundaries. Combine them with network namespaces, nftables, service identity,
and least-privilege routes. Recovery/witness paths must not depend entirely on
the production domain they are meant to diagnose.

### 12.5 AF_XDP deception entrance

Keep XDP logic tiny and deterministic: coarse classification, sampling,
redirection, and dropping. Seraph userspace performs campaign correlation,
friction, decoy selection, and richer reasoning. The experimental path must
have ordinary-stack fallback and packet-loss/latency evidence.

## 13. Repository Families and Workspaces

Create a Repository Family Graph that identifies canonical, derivative,
packaging, documentation, experimental, and retired members. Store the family
manifest outside nested member repositories and generate VS Code multi-root
workspaces from it.

Every mission binds family ID, member ID, canonical remote, resolved root,
revision, and worktree. Never infer repository identity from directory name
alone. The parent directory should not become an ordinary Git repository unless
submodules are deliberately chosen.

Family relationships become Evidence Graph edges and allow queries across VAMP,
Seraph, Citesaga, Lilith, Lucifer, Prosper, WorkReady, Alice-Valkyrie, and other
project families without confusing canonical and derivative releases.

## 14. Local Hugging Face-Style Commons

### 14.1 Namespace

```text
commons://models/<owner>/<name>
commons://datasets/<owner>/<name>
commons://spaces/<owner>/<name>
commons://buckets/<owner>/<name>
commons://jobs/<job-id>
commons://nodes/<node-id>
```

Optional `hf+local://` compatibility is an adapter, not the canonical identity.

### 14.2 Artifact Vault

Implement content-addressed blobs/chunks, manifests, snapshots, refs, staging,
signatures, attestations, and quarantine. Benchmark chunk strategies rather
than adopting one universal size. Support resumable/range transfer, garbage
collection from live refs, verification before promotion, and per-trust-domain
encryption/access policy.

### 14.3 Dataset River

Support Parquet/Arrow fragments, row-group and column projection, deterministic
sharding, streaming, signed dataset cards, lineage, privacy labels, and local
transform receipts. Metadata and fingerprints may be shareable while restricted
rows remain local.

### 14.4 Space Forge

A Space is a signed runnable bundle with immutable image digest, resources,
mounts, network policy, entrypoint, health contract, minimum attestation, and
output policy. OCI/ORAS may transport Spaces, model manifests, cards, SBOMs,
SourcePlan recipes, and attestation bundles after the internal contract is
stable.

### 14.5 Job Choir

Nodes advertise architecture, engines, CPU features, optional kernel features,
pressure, capacity, attestation, data locality, reliability, privacy posture,
and supported job classes.

Selection combines capability fit, attestation, local reproduction reputation,
data locality, pressure budget, reliability, route penalty, transfer cost, and
privacy risk. Hard requirements filter nodes before scoring; a high score never
overrides a missing required capability or failed attestation.

### 14.6 Witness Ledger

Each job links scheduler, node, image, dataset snapshot, policy, tool lease,
attestation, output digest, and verification/reproduction. Begin with
in-toto-shaped statements and claim conformance only after schema and signature
verification are implemented.

### 14.7 Community aggregation

Aggregate signed manifests, cards, capability advertisements, chunk
availability, verification receipts, benchmark summaries, reproduction results,
revocations, and attestation results. Fetch bytes only after policy approval.

## 15. BEAST Control Evidence Graph

### 15.1 Graph model

Every significant action creates or references a signed evidence node. Nodes
are immutable proof objects; edges describe typed relationships.

Core node types:

- identity and attestation result;
- requirement, ticket, task envelope, and policy;
- repository, commit, review, branch protection, and SourcePlan;
- worktree and verification run;
- build invocation, builder, SBOM, provenance, and artifact;
- approval, exception, and separation-of-duties decision;
- deployment, target, configuration, and observed workload;
- ARDA execution decision and Metatron outbound decision;
- Seraph observation, incident, containment, recovery, and retrospective;
- resource pressure, route suppression, failover, backup, and restore test;
- Commons manifest, job, node, dataset, output, and reproduction.

Important edge types:

- `PROPOSED_BY`, `AUTHORIZES`, `DENIES`, `SUPERSEDES`;
- `BUILT_FROM`, `BUILT_BY`, `PRODUCED`, `DESCRIBES`;
- `VERIFIED_BY`, `APPROVED_BY`, `EXCEPTED_BY`;
- `DEPLOYED_TO`, `OBSERVED_AS`, `ATTESTED_BY`;
- `EXECUTED_UNDER`, `USED_DATASET`, `USED_TOOL_LEASE`;
- `TRIGGERED`, `CONTAINED_BY`, `ROLLED_BACK_TO`;
- `REPRODUCES`, `INVALIDATES`, `REVOKES`.

### 15.2 Integrity and storage

- canonical JSON serialization for hashing;
- purpose- and type-bound signatures;
- immutable native receipts in their owning stores;
- Evidence Bus/graph contains pointers, hashes, safe summaries, and edges;
- append-only graph event stream plus rebuildable query index;
- encrypted object storage for sensitive evidence;
- retention, legal hold, and deletion policy by evidence class;
- clock/source metadata and monotonic sequencing where available;
- explicit late-arriving evidence and correction nodes instead of silent edits;
- graph closure verification for every production release.

### 15.3 Required queries

- production releases without required two-person approval;
- deployed digests that differ from approved digests;
- Commons jobs run after node attestation expiry;
- privileged changes during an audit window;
- controls without evidence within their expected cadence;
- incidents without completed retrospectives;
- builds from unapproved runners or unpinned toolchains;
- artifacts missing SBOM or provenance;
- deployments whose configuration hash drifted;
- source changes lacking requirement/ticket relationships;
- expired exceptions still affecting production;
- pressure or provider failures that violated availability objectives;
- revoked identities that retained active leases;
- AI-authored changes without declared AI provenance.

### 15.4 Control health

Each control definition declares owner, objective, scope, evidence producers,
frequency, expected evidence cadence, exception procedure, retention, and test
method. Control health is not a vague percentage; it reports evidence present,
late, missing, contradictory, failed, excepted, or not applicable.

## 16. SOC 2 Readiness Mapping

### 16.1 Relationship to SOC 2

SOC 2 examinations concern controls at a service organization relevant to
Security, Availability, Processing Integrity, Confidentiality, or Privacy.
The selected categories and system boundary depend on the service and scope.
The examination and report belong to an independent qualified practitioner.

BEAST supports management by operating technical controls, preserving evidence,
tracking exceptions, demonstrating design, and showing operation over time. A
point-in-time control design assessment and an observation-period operating
effectiveness assessment have different evidence needs. BEAST should preserve
both configuration/design evidence and repeated operational samples.

### 16.2 Security

Candidate controls and evidence:

- strong administrator identity, MFA, and role/capability authorization;
- tool leases and least privilege;
- quarterly access reviews and termination revocation;
- signed commits, protected branches, independent reviews;
- SourcePlan and Worktree isolation;
- secret, dependency, SAST, container, and IaC scanning;
- vulnerability remediation SLAs and exceptions;
- signed builds, SBOMs, provenance, and artifact verification;
- network segmentation and egress policy;
- ARDA measured execution admission;
- Seraph runtime detection, friction, deception, and containment;
- privileged-action and policy-change receipts;
- incident-response exercises, evidence, and retrospectives.

### 16.3 Availability

Candidate controls and evidence:

- uptime and service-level measurements;
- backup success and restoration tests;
- capacity and queue thresholds;
- PSI CPU, memory, and I/O pressure;
- route-flap suppression and recovery;
- failover and disaster-recovery exercises;
- mean time to acknowledge and recover;
- deployment/canary health and rollback performance;
- resource-lane preservation of operator/security functions;
- provider and Commons node availability histories.

PSI is valuable because it can expose stalled useful work before total service
failure, but thresholds become controls only after they are tied to documented
objectives, tested response, ownership, and exception handling.

### 16.4 Processing Integrity

Candidate controls and evidence:

- intended input and dataset snapshot digests;
- approved pipeline/build definition;
- deterministic transforms or declared variance;
- idempotency keys and duplicate-action prevention;
- in-flight coalescing restricted to safe equivalent requests;
- model, prompt/template, tool schema, and policy versions;
- output reconciliation and completeness checks;
- independent verifier results;
- artifact digest continuity from build through deployment;
- retry, dead-letter, partial failure, and correction records;
- explicit human overrides and exception approvals.

### 16.5 Confidentiality

Candidate controls and evidence:

- data classification and workspace/privacy scopes;
- encryption in transit and at rest;
- secret broker and non-disclosure to models/agents;
- dataset mount and row/column access policy;
- egress controls and approved destinations;
- tenant/workspace isolation;
- redacted evidence exports;
- retention and destruction evidence;
- incident records for unauthorized disclosure.

### 16.6 Privacy

Privacy applies when included in the examination scope and requires more than
security controls. Candidate evidence includes purpose/authority, notice and
consent where applicable, minimization, data-subject workflows, retention and
deletion, disclosure records, correction processes, privacy incidents, and
processor/subprocessor governance. Dataset River privacy labels and Evidence
Graph redaction help operate these controls but do not define legal obligations.

### 16.7 Evidence quality requirements

Audit evidence should be attributable, complete, timely, tamper-evident,
scoped, reproducible where appropriate, understandable without source-code
archaeology, and linked to the control and population it supports. Screenshots
are supplemental; machine-verifiable receipts and population queries are
preferred.

## 17. Phased Delivery Plan

### Phase 0: Governance, terminology, and baseline inventory

Goal: establish boundaries before adding enforcement.

Deliverables:

- approve this architecture and canonical ownership additions;
- inventory BEAST, ARDA, Metatron, Seraph, CI, deployment, and Commons controls;
- classify each integration as production, shadow, simulated, or aspirational;
- define environment profiles that cannot silently cross modes;
- define repository-family manifests;
- define threat models for local developer, CI runner, Commons node, deployment
  target, malicious contributor, compromised provider, and insider;
- define initial SOC 2 system boundary and candidate categories with compliance
  counsel/auditor input;
- create ADRs for resource admission, ARDA reliance, release-by-digest, and
  evidence-graph authority.

Exit gates:

- every planned subsystem has one canonical owner;
- no production claim relies on mock evidence;
- high-risk bypasses and default secrets are inventoried;
- the initial control/evidence catalog has owners and frequencies.

### Phase 1: Tool leases and negative capability memory

Goal: reduce authority and context exposure immediately.

Deliverables:

- per-request bucket compiler above existing MCP profiles;
- invocation-time lease validation;
- signed lease receipt and revocation path;
- CapabilityPlane integration;
- negative capability store with TTL and invalidation;
- tests for hidden-but-invoked tools, schema drift, expired leases, path escape,
  network scope, and approval escalation.

Exit gates:

- unauthorized invocation fails even if a schema is manually supplied;
- admin/execute tools require explicit capabilities;
- schema/context reduction is measured;
- no false grants in adversarial tests.

### Phase 2: PSI Resource Admission shadow plane

Goal: understand host pressure without changing behavior.

Deliverables:

- workload resource envelope;
- PSI global/cgroup collector and threshold listener;
- Resource Admission decision model;
- operator/security lane definitions;
- shadow admission receipts in Evidence Bus;
- replay harness for inference, indexing, verification, and document jobs;
- dashboards for pressure, queue, proposed concurrency, and SLO impact.

Exit gates:

- representative workload coverage;
- negligible collector overhead;
- explainable decisions and no enforcement;
- calibrated host-class thresholds proposed from evidence.

### Phase 3: Resource Executor and bounded PSI enforcement

Goal: apply safe admission and concurrency changes.

Deliverables:

- async/thread/process/dedicated-inference adapters;
- cgroup placement and per-lane limits;
- hysteresis, cooldown, starvation bound, checkpoint/cancel contracts;
- cache-eviction interface for explicitly disposable caches;
- enforcement kill switch and automatic fallback;
- availability and latency acceptance tests.

Exit gates:

- UI/security latency protected under controlled pressure;
- no unauthorized work admitted;
- no loss of required evidence;
- false delay/rejection rate within agreed bounds;
- stable recovery without oscillation.

### Phase 4: Provider reliability and API economy

Goal: stop repeatedly paying for unstable or duplicate routes.

Deliverables:

- multidimensional flap ledger with decay;
- circuit-breaker compatibility adapter;
- safe in-flight call coalescer;
- idempotency and cancellation semantics;
- route state dashboards and recovery controls;
- negative endpoint/model/schema cache integration.

Exit gates:

- reduced duplicate calls and retry storms;
- trust failures cannot be erased by ordinary success;
- no cross-scope coalescing;
- provider selection remains explainable and reversible.

### Phase 5: Port Lease Broker and Repository Family Graph

Goal: make local identity and project identity deterministic.

Deliverables:

- lease registry, health, expiry, and process ownership;
- dynamic reverse-proxy configuration and local `.test` DNS;
- collision and stale-lease recovery;
- repository family manifests and generated multi-root workspaces;
- family/member identity in Task Envelope, Worktree Forge, and Evidence Graph.

Exit gates:

- services do not silently seize reserved known ports;
- names route only to current healthy lease owners;
- BEAST cannot confuse canonical and derivative repositories;
- lease revocation removes routes predictably.

### Phase 6: ARDA Attestation Result and BEAST relying-party adapter

Goal: create a trustworthy, narrow attestation contract.

Deliverables:

- ARDA Attestation Result v1 schema;
- strict signature, nonce, freshness, PCR/event-log, workload, audience, and
  revocation verification;
- explicit mock/simulation separation;
- BEAST read-only adapter and policy inputs;
- tool/job lease binding to attestation result;
- mutation and negative tests for verifier failures;
- hardening of token signatures, persistence, cryptography, and replay state.

Exit gates:

- no self-asserted `is_attested` acceptance;
- real verifier failure closes protected paths;
- development evidence cannot satisfy production policy;
- token authority fields are all integrity protected;
- expiry/revocation invalidates dependent capabilities.

### Phase 7: Release Governor and immutable artifact spine

Goal: govern source-to-artifact without deploying yet.

Deliverables:

- source/review/branch-protection evidence adapters;
- build request and builder identity contract;
- SBOM and SLSA-shaped provenance generation;
- immutable artifact registry and digest sealing;
- independent Verification Lane and verification summary;
- release approval and separation-of-duties policy;
- artifact closure query in Evidence Graph.

Exit gates:

- every release candidate traces to approved source and build inputs;
- verifier checks signer-builder expectations and artifact digest;
- missing SBOM/provenance blocks protected promotion;
- signed provenance cannot be modified undetected;
- selected builds reproduce or declare bounded variance.

### Phase 8: Attested deployment and runtime reconciliation

Goal: deploy only approved digests to eligible targets.

Deliverables:

- deployment-by-digest contract;
- target ARDA attestation requirement;
- configuration digest and environment policy;
- Metatron Outbound Gate integration;
- ARDA permitted-workload projection;
- Seraph runtime observation adapter;
- approved/deployed/observed reconciliation;
- canary, rollback, quarantine, and incident receipts.

Exit gates:

- production cannot deploy a mutable source reference alone;
- wrong digest or expired attestation is denied;
- runtime drift creates evidence and policy response;
- rollback meets documented objective in exercises;
- operator override is explicit, scoped, signed, and reviewed.

### Phase 9: Commons Artifact Vault, Dataset River, and Space Forge

Goal: establish governed local artifact and data exchange.

Deliverables:

- CAS, manifests, snapshots, refs, staging, quarantine, and signatures;
- transfer resumption and chunk-strategy benchmark;
- Dataset River streaming/filtering/lineage/privacy contracts;
- signed Space manifest and OCI/ORAS adapter;
- content and metadata retention/GC policy;
- import, verification, local reproduction, approval, and promotion flow.

Exit gates:

- tampered or incomplete artifacts fail verification;
- private/restricted bytes do not leak through metadata exchange;
- remote hypotheses cannot become local authority without reproduction;
- GC cannot remove live referenced artifacts.

### Phase 10: Commons Job Choir and Witness Ledger

Goal: execute governed jobs across attested nodes.

Deliverables:

- node flavour/capability/pressure advertisement;
- hard eligibility filters and scoring;
- job capability tokens and mounted input snapshots;
- attestation-aware DNS publication;
- resource ceilings, output buckets, and cancellation;
- job witness chain and local reproduction;
- route-flap and Seraph/ARDA trust integration.

Exit gates:

- expired/revoked nodes receive no new work;
- job inputs and outputs are digest-bound;
- failure/retry is idempotent;
- output remains quarantined until required verification;
- scheduling explanations reproduce from recorded inputs.

### Phase 11: Control Evidence Graph and SOC 2 readiness exporter

Goal: turn evidence archaeology into controlled retrieval.

Deliverables:

- graph schemas, edges, closure rules, and rebuildable index;
- control catalog with owner/frequency/evidence expectations;
- required exception and population queries;
- audit-window snapshots and redacted exports;
- missing/late/contradictory evidence alerts;
- access review, vulnerability, incident, backup/restore, change, deployment,
  and availability evidence packs;
- auditor-facing documentation of system boundary and evidence provenance.

Exit gates:

- graph rebuild matches native receipt population;
- production releases have complete closure or explicit exception;
- sample audit questions are answered without manual repository archaeology;
- evidence export is scoped, access-controlled, and reproducible;
- external audit/compliance review validates usefulness and claim language.

### Phase 12: Advanced memory, cache, and network enforcement

Goal: add hardware-specific efficiency and isolation after the control spine is
stable.

Deliverables:

- shared read-only Model Vault;
- DAMON monitor-only heat maps, then quota-bounded reclaim;
- zswap observability and operator-managed profiles;
- resctrl monitoring, calibration, then limited lane allocation;
- VRF/netns/nftables trust domains;
- cryptographic node DNS projection;
- AF_XDP Seraph lab entrance.

Exit gates:

- every feature capability-probes and fails back safely;
- performance gains are benchmarked against controls;
- no cross-trust memory sharing;
- routing isolation survives negative tests;
- host recovery remains possible when an advanced feature fails.

### Phase 13: Harmonic sched_ext laboratory

Goal: test custom scheduling without entering the production boot chain.

Deliverables:

- scheduler policy simulator;
- pinned lab kernel and build recipe;
- BPF dispatch queues and watchdog;
- automatic normal-scheduler fallback;
- starvation, latency, pressure, thermal, and failure gauntlets;
- explicit go/no-go ADR.

Exit gates:

- zero host lockups in extended soak;
- fallback verified under injected scheduler failure;
- meaningful improvement over cgroup/PSI policy;
- no production dependency on unstable sched_ext APIs.

## 18. Cross-Phase Metrics

### Security and authority

- unauthorized tool invocation rate;
- expired/revoked lease acceptance rate, target zero;
- production mock-attestation acceptance rate, target zero;
- privileged actions with complete approval evidence;
- mean time from trust degradation to token and route revocation;
- artifact/digest drift incidents.

### Availability and resource economy

- operator/security lane latency under pressure;
- PSI stall time by lane;
- false admission delay/rejection rate;
- queue starvation and deadline misses;
- route suppression/recovery quality;
- duplicate provider calls avoided;
- cache/memory bytes saved and CPU/I/O cost incurred;
- rollback and recovery time.

### Supply-chain integrity

- releases with SBOM and verified provenance;
- releases with complete source-to-runtime graph closure;
- builds from approved builders;
- reproduced high-risk builds;
- deployed digest match rate;
- unresolved vulnerability-policy exceptions;
- two-person approval coverage where required.

### Commons

- locally reproduced imports;
- tampered bundle rejection rate;
- bytes avoided through deduplication;
- jobs rejected for stale attestation;
- verified output rate;
- privacy-policy violations, target zero;
- scheduler decision reproducibility.

### Evidence operations

- expected evidence produced on schedule;
- late, missing, contradictory, and excepted control evidence;
- graph rebuild integrity;
- audit-query latency;
- percentage of audit samples answerable from signed primary evidence.

## 19. Principal Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Platform becomes too broad | Preserve canonical owners, versioned contracts, and phase exit gates |
| Evidence volume becomes unmanageable | Native immutable objects plus compact graph pointers, retention tiers, CAS |
| Attestation theater | Strict verifier, mock separation, nonce/freshness/baseline checks, negative tests |
| Compliance overclaim | Approved language, auditor involvement, control/evidence distinction |
| Resource governor harms latency | Shadow mode, host calibration, hysteresis, reserved lanes, kill switch |
| Trust score masks hard failure | Structured veto dimensions and hard eligibility filters |
| Token forgery or field substitution | Sign all authority fields, audience binding, atomic use/revocation state |
| Build signs attacker-controlled claims | Trusted builder generates provenance; verify expectations independently |
| Evidence contains secrets/private data | Allowlisted schemas, hashing, encryption, redaction, scoped exports |
| Commons becomes remote-code execution path | Quarantine, immutable images, no secrets, network policy, local reproduction |
| DNS name mistaken for identity | Cryptographic identity remains source; DNS is ephemeral projection |
| VRF mistaken for sandbox | Combine with netns, nftables, identity, and workload isolation |
| Experimental kernel feature destabilizes host | Capability probes, lab branches, watchdogs, automatic fallback |

## 20. Initial ADR Set

1. BEAST is the Change and Release Governor, not a replacement CI engine.
2. SourcePlan remains the only BEAST source-mutation authority.
3. Resource Admission is separate from semantic Compute Governance.
4. ARDA is the attestation evidence/verifier authority; BEAST is a relying
   party.
5. Metatron owns consequential outbound action gating.
6. Seraph owns runtime behavioral observation and containment evidence.
7. Protected deployment occurs by immutable digest only.
8. Evidence Graph indexes native receipts and is not a competing truth store.
9. Tool schemas and tool invocation authority are independently enforced.
10. Commons remote contributions remain hypotheses until local reproduction.
11. Hardware-specific optimization is optional and capability-probed.
12. SOC 2 language is readiness/evidence infrastructure, never self-certification.

## 21. Reference Foundations

These references inform terminology and interoperability targets. They do not
constitute a conformance claim.

- AICPA SOC suite and SOC 2 resources:
  <https://www.aicpa-cima.com/soc>
- AICPA SOC 2 examination guide description:
  <https://www.aicpa-cima.com/cpe-learning/publication/soc-2-reporting-on-an-examination-of-controls-at-a-service-organization-relevant-to-security-availability-processing-integrity-confidentiality-or-privacy-OPL>
- NIST Secure Software Development Framework, SP 800-218:
  <https://csrc.nist.gov/projects/ssdf>
- NIST DevSecOps SSDF reference model:
  <https://pages.nist.gov/nccoe-devsecops/notational-reference-model.html>
- SLSA specification 1.2 and provenance verification:
  <https://slsa.dev/spec/v1.2/>
- in-toto Attestation Framework:
  <https://github.com/in-toto/attestation>
- Linux PSI:
  <https://docs.kernel.org/accounting/psi.html>
- Linux resctrl:
  <https://docs.kernel.org/filesystems/resctrl.html>
- Linux DAMON:
  <https://docs.kernel.org/admin-guide/mm/damon/>
- Linux zswap:
  <https://docs.kernel.org/admin-guide/mm/zswap.html>
- Linux sched_ext:
  <https://docs.kernel.org/scheduler/sched-ext.html>

## 22. Final Product Position

The completed system should be described plainly:

> BEAST governs how software and AI-assisted changes move from intent to source,
> from source to immutable artifact, and from artifact to an attested running
> workload. ARDA supplies measured execution identity, Metatron gates
> consequential action, Seraph observes runtime behavior, Commons exchanges
> governed artifacts and compute, and the Control Evidence Graph preserves the
> proof chain for operations, investigations, and audit readiness.

That positioning is ambitious but bounded. It makes the extraordinary parts of
the platform testable one control boundary at a time.

## 23. Strict Recovery Validation Record (2026-07-14)

The first live production-shaped validation completed against the Metatron
Arda-Fabric Docker testbed. The run used provisioned Ed25519 PEM roots and the
strict `/lorien/recover-strict` path; legacy HMAC recovery remained disabled.

Evidence bundle: `/tmp/live_recovery_validation_strict3`.

All 15 assertions passed, including isolation, protected-asset blocking,
negative quorum and witness rejection, signed recovery authorization, rejoin,
ledger recording, WireGuard restriction/restoration, route restoration,
continuous Metatron heartbeat, lawful quorum transition, and packet capture.

The run also exposed and closed a real concurrency defect: the replay ledger
SQLite connection was thread-bound while FastAPI dispatched recovery on a
worker thread. `RecoveryReplayStore` now uses an explicit re-entrant lock and
`check_same_thread=False` while retaining atomic `BEGIN IMMEDIATE` nonce and
capability consumption.

## 24. Enterprise Commons Control Plane Implementation (2026-07-14)

The BEAST/Commons enterprise foundation is now implemented around five
inherited `.byron` manifests, one validated service/port registry, exact active
workspace identity, least-authority CapabilityPlane exposure, and a bounded
six-lane ResourceExecutor. This release intentionally excludes VAMP and
Hivenance.

Commons now composes a persistent signed Artifact Registry, immutable Artifact
Vault, verified Chunk Store, deterministic Dataset River, attested Job Choir,
persistent route-flap damping, and appraisal-gated Space Forge. Enterprise
admission verifies Ed25519 authority signatures and binds signed ARDA decisions
to the exact canonical Space body. Missing production trust material produces
`configuration_required` and denies admission rather than accepting a string
that merely claims to be a signature or appraisal.

The operational configuration, rollout sequence, endpoints, failure modes,
and remaining provisioning boundary are normative in
`docs/beast-commons-enterprise-control-plane.md`. Verification evidence is in
`docs/beast-commons-enterprise-verification-report.md`.

## 25. TPM Validation and Cross-Platform Commons Nodes (2026-07-15)

The local workstation now has genuine TPM evidence at a deliberately narrow
claim boundary. A fresh TPM-resident AK signed a verifier nonce and selected
SHA-256 PCR state; the quote verified locally. Secure Boot is enabled. The
firmware EK certificate public key matches the TPM-derived EK public key, and
the Nuvoton manufacturer chain validates to a pinned NPCTxxx ECC521 RootCA.

This does not yet make the host an attested Commons executor. A pinned offline
Debian 12 verifier now completes MakeCredential, and the physical TPM completes
ActivateCredential, proving the transient AK belongs to the certified EK. The
privileged firmware log also parses: PCRs `2,4,7,14` match its replay, PCR `0`
does not. All 267 IMA records parse and PCR `10` matches its independent replay.
No logged PCR 0 event subset or standard initial-state variant explains the
live value, so the evidence packet denies eligibility on the sole remaining
PCR 0 measurement anomaly. Evidence is stored outside the source tree with
mode 0600 and is not substituted for the existing ARDA appraisal.

Commons now owns a persistent one-use TPM challenge ledger. Challenges bind a
256-bit nonce, exact node identity, audience, SHA-256 PCR selection, issue time,
and expiry. A new challenge supersedes any prior active challenge for the same
node/audience, and consumption uses an atomic SQLite transaction. The live
Commons listener exposes challenge issuance but no acceptance endpoint.

The Windows colleague path uses the same protocol and gates:

1. authenticated transport and registered node identity;
2. verifier-issued one-use challenge;
3. EK certificate and non-exportable AK enrollment;
4. verifier MakeCredential and TPM ActivateCredential;
5. nonce-bound quote plus measured-boot event log;
6. independent EK chain/revocation, quote, PCR, Secure Boot, freshness, and
   event-log replay verification;
7. short-lived ARDA appraisal bound to the complete node advertisement; and
8. Job Choir eligibility only after appraisal verification.

PowerShell TPM status and Secure Boot commands remain preflight signals only.
They are never accepted as quotes or appraisals. The detailed live boundary and
remaining verifier work are recorded in
`docs/commons-tpm-remote-validation.md`.
