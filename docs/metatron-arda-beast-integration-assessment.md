# Metatron, ARDA, and BEAST Integration Assessment

Date: 2026-07-14  
Source initially reviewed read-only and subsequently hardened with explicit
user authorization:
`/home/byron/Downloads/Metatron-triune-outbound-gate/`  
Governing roadmap:
[BEAST DevSecOps, Compute, Commons, ARDA, and Control Evidence Master Plan](beast-devsecops-arda-commons-master-plan.md)

## 1. Decision

The Metatron repository contains substantial architecture that should be
integrated, not rewritten inside BEAST. The correct authority chain is:

```text
BEAST
  issues intent/change/job authority and an immutable subject digest
    -> ARDA Attester
       collects measured node, boot, workload, and runtime evidence
    -> ARDA Verifier
       produces a short-lived, audience-bound appraisal result
    -> BEAST Relying Party
       binds the accepted result to a capability/job/deployment lease
    -> Metatron Outbound Gate
       independently evaluates each consequential edge
    -> executor
       consumes the one-use authority and performs the bounded action
    -> Sensorium + Seraph + native ledgers
       observe effects and publish linked evidence
```

No component may silently manufacture the evidence or authority it is meant to
verify. In particular:

- BEAST does not interpret raw PCRs independently.
- ARDA does not approve source changes, deployments, or business intent.
- Metatron does not mint its own prerequisite capability merely because an
  action reached the gate.
- Seraph behavioral confidence does not override a failed cryptographic or
  policy veto.
- The evidence graph indexes native receipts; it does not replace their
  signature verification.

## 2. Existing Metatron/ARDA assets worth preserving

### 2.1 Measured identity and formation chain

The repository already contains:

- TPM discovery, PCR snapshots, nonce-bound quote generation, quote checking,
  PCR extension, and PCR-bound seal/unseal plumbing;
- node public-key identity and a derived node fingerprint;
- secure-boot and TPM substrate measurements;
- formation manifests, formation verification, formation order, preboot
  covenant, runtime handoff covenant, and a derived SPIFFE-shaped runtime
  identity;
- a Manwë Herald bootstrap that links formation, covenant, attested node state,
  runtime identity, and heartbeat startup;
- an ARDA Fabric challenge/response flow that binds a peer session to a nonce,
  TPM quote, workload hash, and executable path.

These are valuable domain boundaries. They should become producers of strict,
versioned evidence objects rather than be collapsed into a single trust score.

### 2.2 Polyphonic appraisal

The Ainur Choir already models a tiered evidence appraisal:

```text
micro: Varda
  -> meso: Vairë, Mandos, Lórien
  -> macro: Manwë, Ulmo
  -> Aulë synthesis
```

The sweep binds evidence to a voice, sweep, covenant, epoch, node, and subject.
Lower-tier dissonance inhibits higher tiers. This is a good architecture for
explainable multi-dimensional appraisal if hard evidence requirements remain
separate from advisory resonance.

### 2.3 Governance epochs and notation tokens

Metatron already defines:

- governance epochs with scope, score, genre, strictness, world-state hash,
  start, expiry, status, and signature reference;
- escalation modes from pastoral/watchful through siege/containment;
- rotation on compromise and world-state changes;
- notation tokens bound to epoch, score, genre, voice role, capability class,
  world-state hash, recipient, response class, time window, sequence slot, and
  required companions;
- expiry, signature, epoch, score, genre, world-state, sequence, and companion
  validation;
- revocation, consumption, narrowing, reissue, and epoch-wide revocation.

This is a strong seed for BEAST capability leases. Notation remains a Metatron
edge-admission object; BEAST's capability lease remains the upstream grant.
The two are linked but are not synonyms.

### 2.4 Outbound Gate

The central Outbound Gate already combines:

- mandatory high-impact action classification;
- governance epoch and world-state binding;
- notation validation;
- attestation-state veto;
- transport-lock veto;
- world-manifold signature veto;
- harmonic drift/burst/discord observations;
- Triune review escalation;
- queue and decision records;
- world events and edge-participant observations.

This is the natural owner of consequential outbound action. BEAST should call
it through a narrow contract and receive a signed decision receipt.

### 2.5 Kernel and fabric enforcement

The repository contains a BPF LSM `bprm_check_security` hook with audit and
enforcement modes backed by an allow map, plus kernel-policy projection,
WireGuard-aware fabric state, nftables isolation/rejoin, and remediation-only
network access.

The live recovery/rejoin testbed is particularly useful. It records baseline,
isolation, rejected compromised quorum/recovery witnesses, lawful rejoin,
WireGuard and nftables state, heartbeat/quorum metrics, packet capture, and a
Mandos ledger. This should be retained as an integration conformance harness.

## 3. Honest maturity assessment

The presence of these components does not yet establish production-grade
remote attestation. The following are explicit blockers, not optional polish.

| Current behavior observed | Required production disposition |
| --- | --- |
| Remote attested-state verification accepts a self-reported boolean | Replace with a verifier that validates signature, nonce, AK chain, PCR selection/digest, event-log reconstruction, baseline, workload binding, freshness, audience, and revocation |
| Sigstore envelope verification returns success based on algorithm label | Perform cryptographic bundle, certificate identity, transparency inclusion, subject, and policy verification |
| HMAC services have checked-in development defaults | Refuse production startup when a default/missing secret is detected; prefer asymmetric keys protected by TPM/HSM/vault |
| Node signing falls back to an unkeyed SHA-256 digest when crypto is absent | Fail closed for identity/authority; label hash-only output as non-authenticating diagnostics |
| TPM mock unseal can relax PCR mismatch outside production | Cryptographically segregate mock evidence and make it impossible for mock issuers/audiences to satisfy protected policy |
| Fixed `/tmp` TPM artifact paths are reused | Use private temporary directories, restrictive permissions, cleanup, command timeouts, and concurrency-safe contexts |
| Choir collector failures receive mock-safe evidence | Required witnesses fail closed in protected modes; optional/advisory witnesses may be explicitly absent with confidence impact |
| Gate auto-mints a notation token when one is absent | Require a prior authorized grant for protected actions; the enforcement point must not mint its own prerequisite authority |
| Human override clears attestation and transport vetoes | Split emergency/break-glass into a separately authenticated, two-person, time-limited, fully evidenced policy; never silently clear hard vetoes |
| Development bypasses are controlled by runtime environment variables | Build separate dev/prod policy profiles and make production artifacts incapable of enabling bypasses |
| Egress sanctuaries use URL substring matching | Parse and canonicalize destination scheme/host/port/IP, resolve policy-safe addresses, and prevent suffix, redirect, DNS-rebinding, and alternate-representation bypass |
| The legacy BPF startup path projects device/inode only, despite a content-bearing harmony manifest and an fs-verity-capable target kernel | Make strict `bpf_get_fsverity_digest()` identity the production mode; retain inode/device only as labeled compatibility and reconcile generation/expiry |
| In-memory Mandos history is bounded and ephemeral | Persist signed append-only native receipts with hash linkage, retention policy, and replay/rebuild verification |
| Token lookup/consume/revoke can race across cache/database paths | Make issuance, single-use consumption, epoch rotation, and revocation atomic and durable |

## 4. Canonical cross-system contracts

### 4.1 BEAST Authority Request v1

BEAST sends ARDA and Metatron no free-form request as authority. The canonical
request includes:

- request, mission, workspace, SourcePlan, and actor identities;
- requested capability and maximum consequence class;
- immutable source/artifact/workload/configuration digests;
- target environment, node, route, output bucket, and data classifications;
- resource ceiling, network policy, validity window, and replay nonce;
- approval requirements and approval receipt references;
- BEAST policy generation and evidence root;
- explicit audience: ARDA verifier or Metatron gate.

### 4.2 ARDA Evidence Bundle v1

The Attester emits a signed evidence bundle containing or referencing:

- node public identity and attestation-key identity;
- challenge nonce and verifier session;
- quote, PCR bank/selection, and measured values;
- secure-boot state and measured-boot event log;
- formation manifest/covenant digests;
- workload artifact, executable, configuration, cgroup, and namespace identity;
- boot ID, governance epoch, monotonic/replay counter, and observation time;
- evidence-mode taxonomy: simulated, synthetic, observed, or enforced;
- collector identities, errors, and completeness indicators;
- privacy classification and encrypted/raw-evidence locations.

The bundle is evidence, not permission.

### 4.3 ARDA Attestation Result v1

Only the Verifier emits the appraisal result consumed by BEAST. It contains:

- result ID, issuer, version, issued-at, expires-at, status, and revocation
  epoch/endpoint;
- subject node and workload identities;
- evidence digest, nonce, AK, PCR/event-log, secure-boot, workload, and
  formation appraisal results;
- accepted reference-value and verifier-policy versions;
- assurance class, environment, audience, and relying-party scope;
- hard failures, warnings, missing optional evidence, and mock indicator;
- signature and verification material.

Raw `is_attested`, `harmonic`, or `lawful` fields are never sufficient.

### 4.4 BEAST Capability Lease v1

After relying-party policy accepts the ARDA result, BEAST may issue a lease
bound to:

- principal, process/workload, mission, workspace, and node;
- attestation result and evidence digest;
- capability, parameters, data scope, route scope, and output location;
- maximum resource and consequence ceilings;
- policy generation, approval receipts, issued/expiry times, nonce, and use
  count;
- revocation epoch and downstream audience.

The lease cannot exceed the Task Envelope, tool bucket, SourcePlan, approval,
or ARDA result that produced it.

### 4.5 Metatron Outbound Decision v1

Metatron evaluates the capability lease plus its own current state and emits:

- decision, queue, action, and correlation IDs;
- exact normalized action and canonical target;
- capability lease, attestation result, governance epoch, notation token,
  score, world-state, and manifold references;
- transport, attestation, notation, approval, replay, route, and consequence
  checks as separate veto dimensions;
- Triune/human approvals and break-glass receipt when applicable;
- decision status, expiry, one-use consumption state, and denial reasons;
- signature, policy version, and evidence root.

The executor accepts only an approved, unexpired, audience-correct,
single-use decision whose request digest matches the action it will perform.

## 5. Integration with BEAST's existing layers

| BEAST layer | Metatron/ARDA integration |
| --- | --- |
| Interception | Convert attempted consequential edges into Authority Requests; observe decisions without bypassing the gate |
| Tool bucketing | Observe/Reason remain low authority; Connect/Execute/Administer require capability lease plus appropriate Metatron decision |
| Schema mapping | Canon maps Metatron objects into versioned contracts without erasing native fields or signatures |
| Compression | Compress payload/context only after preserving signed roots, veto dimensions, and evidence references |
| Cache | Cache public verification material and negative capability results; never cache a live authorization beyond expiry/revocation |
| Route-flap damping | Attestation, malformed evidence, replay, transport, or incorrect-result failures penalize node/provider routes; hard trust failures remain vetoes |
| Sensorium | Observe attestation requests/results, epoch rotation, token lifecycle, gate decisions, BPF admission, isolation, rejoin, and effects |
| RuntimeEpisode | Link BEAST intent to ARDA appraisal, Metatron decision, process/socket topology, action effects, and verifier outcome |
| Crystal lattice | Treat current attestation, lease, route, policy, and topology as physical preconditions; a crystal cannot synthesize missing authority |
| Evidence graph | Index native BEAST, ARDA, Metatron, Seraph, Sensorium, build, deployment, and runtime receipts by digest |
| Commons | Require fresh node/workload appraisal and a job-scoped lease; remote contributions remain hypotheses until verified/reproduced |

## 6. Phased integration plan

### MA0: Freeze claims and classify evidence

- Inventory every attestation, covenant, witness, token, epoch, gate, BPF, and
  ledger object.
- Label each producer simulated, synthetic, observed, or enforced.
- Add issuer/environment/audience separation and ban ambiguous `lawful` or
  `attested` booleans at cross-system boundaries.
- Record golden and hostile fixtures from the live testbed.

Exit: no production policy can consume unlabeled or mock evidence.

### MA1: Canon contracts and read-only adapters

- Implement the five contracts in section 4 in BEAST Canon.
- Add read-only import/adapters for native Metatron queue/decision, epoch,
  notation, covenant, and recovery receipts.
- Preserve native digest/signature material and record transformation receipts.
- Feed payload-free summaries to the Sensorium Observatory.

Exit: BEAST can correlate existing Metatron/ARDA artifacts without granting or
executing authority.

### MA2: Verifier hardening

- Build a dedicated ARDA Verifier service separate from Attester state.
- Verify nonce, AK, quote signature, PCR bank/selection/digest, event-log
  replay, secure boot, reference values, workload/configuration binding,
  freshness, audience, environment, and revocation.
- Replace default secrets, unkeyed identity fallbacks, and label-only Sigstore
  acceptance.
- Create strict mock issuer roots that protected policies reject.

Exit: every mutated verifier dimension fails closed and no self-attested state
is accepted.

### MA3: Capability and notation separation

- Issue BEAST Capability Leases only after accepted ARDA appraisal and BEAST
  policy/approval.
- Require the lease at Metatron before notation issuance.
- Bind notation to the lease request digest, consequence class, audience,
  target, and one-use state.
- Atomically persist issuance, consumption, revocation, and epoch rotation.

Exit: the Outbound Gate cannot mint its own upstream authority and replayed or
  stale tokens are rejected.

### MA4: Outbound Gate hardening

- Replace heuristic human detection with authenticated principal claims.
- Remove silent hard-veto clearing; implement explicit break-glass workflow.
- Canonicalize network destinations and close redirect/DNS/suffix bypasses.
- Make production builds bypass-incapable.
- Sign the complete decision and bind it to the exact executor request.

Exit: every high/critical edge requires independent, current, matching BEAST,
ARDA, and Metatron authorization.

### MA5: Kernel/runtime projection

- Project only approved workload digests/generations into ARDA kernel maps.
- Bind projection receipts to attestation result, capability lease, policy
  generation, file identity, cgroup, namespace, and expiry.
- Reconcile stale inode/device entries and enforce map removal on expiry,
  revocation, replacement, or drift.
- Keep audit mode and enforcement mode cryptographically distinct in evidence.

Exit: protected execution admits the approved object, not merely a path or
recycled file coordinate.

### MA6: Recovery, federation, and continuous evidence

- Import the live recovery/rejoin harness as a cross-system conformance suite.
- Add replayed quote, stale epoch, split-brain, forged witness, compromised
  quorum, expired lease, wrong audience, wrong workload digest, and concurrent
  token-consumption cases.
- Publish linked native receipts to the Control Evidence Graph.
- Extend the same contracts to Commons nodes and attested API sessions.

Exit: isolation and rejoin require fresh multi-party evidence; audit queries
can trace intent through execution and recovery without trusting summaries.

## 7. Required negative test matrix

At minimum, protected workflows must reject:

- missing, replayed, wrong, expired, or cross-session nonce;
- unknown/revoked AK or invalid quote signature;
- wrong PCR bank, mask, digest, event log, baseline, or secure-boot state;
- workload/configuration digest substitution;
- development/mock issuer in a production audience;
- stale governance epoch or world-state hash;
- token field mutation, replay, double consumption, or post-revocation use;
- auto-issued authority at the enforcement point;
- human-identity spoofing and unauthorized break-glass;
- unverified transport, redirect, DNS rebinding, suffix confusion, or alternate
  IP encoding;
- stale BPF map entry after file replacement or policy expiry;
- compromised quorum/witness blessing its own recovery;
- missing required Ainur evidence masked by synthetic fallback;
- evidence export failure being reported as successful verification.

## 8. Immediate implementation order

1. Land read-only Canon schemas/adapters; do not connect actuators.
2. Create hostile fixtures for each currently observed trust shortcut.
3. Implement ARDA Verifier v1 and its mutation test suite.
4. Bind BEAST Capability Lease to the verified result.
5. Require that lease before Metatron notation issuance and gate evaluation.
6. Harden the signed Metatron decision and one-use executor handoff.
7. Project approved workload identity into ARDA enforcement with expiry and
   reconciliation.
8. Run the live isolation/rejoin harness as a release gate.
9. Only then enable Commons or production deployment reliance.

This sequence extracts the excellent structure already present while refusing
to promote prototypes, defaults, mock evidence, or semantic trust states into
cryptographic authority.

## 9. Implementation checkpoint — 2026-07-14

The hardening branch now implements the central MA2–MA6 enforcement skeleton:

- strict evidence/appraisal contracts and independent verifier interfaces;
- production rejection of self-reported appraisal, label-only Sigstore,
  development signing defaults, and hash-only identity fallback;
- signed Ed25519 capability verification, transactional registration,
  revocation, notation binding, and exact one-use executor consumption;
- removal of Outbound Gate authority minting and non-overridable capability,
  attestation, and transport vetoes;
- canonical action, target, and network destination binding;
- strict fs-verity execution identity plus signed projection generations and a
  reconciler for expiry, revocation, replacement, and runtime drift; and
- strict recovery authorization bound to isolation, current epochs, accepted
  appraisal, one-use recovery capability, and two distinct signed witnesses;
- a production runtime factory that rejects missing trust-root files and
  never accepts embedded or self-reported public keys.

The native `live_recovery_rejoin_proof` imports successfully as observed
conformance evidence: 23 files are hashed under bundle root
`sha256:01e57f403c28f3310915454ad0f2ce9337b43405aa05a29694a633f45e452c6f`.
Its lab HMAC and possible controller credential defaults are preserved as
limitations, so importing it cannot mint rejoin authority.

The focused hardening regression set passes 84 tests. Python modules, the BPF
LSM object, and the userspace loader compile successfully. Production exit is
still blocked on provisioning production recovery roots and privileged-host
validation of the now-wired cgroup/generation BPF map sink and recovery
actuator, migrating remaining legacy executor/router paths, and completing Commons plus
Control Evidence Graph federation.

## 10. Guardian authority integration checkpoint — 2026-07-15

The Metatron ARDA authorizer now exposes a fail-closed
`POST /authorize/socket-guardian` surface. It does not auto-mint prerequisite
deployment authority: callers must present the exact preconfigured workspace,
deployment capability reference, appraisal reference, policy generation,
service-registry digest, typed ProcessLease, allow-listed executable digest,
and a private bearer credential. Only `recover` and `mark_health` are admitted.

Each allowed request returns independently Ed25519-signed decision,
short-lived one-use capability, and appraisal objects over the exact canonical
operation digest. BEAST verifies the signed appraisal before the Guardian
atomically consumes the capability. Host-local live validation passed consumer
replacement and Guardian replacement without a port-ownership gap.

The current appraisal binds a reviewed sovereign-proof manifest digest and is
explicitly labelled static local validation. It is not a live TPM quote,
measured-boot event-log verification, external witness, HSM-backed production
root, or SOC 2 operating-effectiveness evidence.
