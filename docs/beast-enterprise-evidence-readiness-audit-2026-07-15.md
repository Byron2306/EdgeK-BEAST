# BEAST Enterprise Evidence Readiness Audit — 2026-07-15

Status: repository evidence audit, not a certification, deployment approval, or
production attestation.

## Measurement method

This audit separates four facts that prior progress notes sometimes combined:

1. **Designed** — a normative contract or plan exists.
2. **Implemented** — executable product code exists in this repository.
3. **Tested** — a focused automated test exercised the claimed behavior.
4. **Live** — the behavior is provisioned and was observed in the current host
   runtime, using production-shaped authority rather than a fixture.

Roadmap percentages below use strict exit-gate counting. A partial gate earns
zero until every condition in that gate is evidenced. This makes the result
conservative, reproducible, and intentionally lower than a count of files or
classes.

## Executive result

| Workstream | Strict result | Meaning |
|---|---:|---|
| Full DevSecOps/Commons/ARDA master plan | **24/61 exit gates (39%)** | Strong control-plane foundations; release/build/deploy and auditor-export phases remain the largest gaps. |
| Sensorium target capability | **10/15 capabilities (67%)** | Ordered, private, durable BEAST-owned observation is real; privileged kernel/file/network sensing is not complete. |
| Proof-carrying crystal target | **10/15 capabilities (67%)** | Transport, sealing, evidence, replay gates, and one bounded physical crystal are real; generalization/e-graphs/autonomous promotion are not. |
| Enterprise Commons foundation | **12/15 capabilities (80%)** | Local signed storage, datasets, jobs, Spaces, damping, and evidence exist; OCI/ORAS, federated production nodes, and production trust provisioning remain. |
| SOC 2 evidence infrastructure | **5/12 evidence capabilities (42%)** | Integrity-preserving evidence primitives exist; operating-period control collection and auditor packs do not. |
| Audit-time production deployment | **0/5 production exit conditions (0%)** | BEAST/Commons/ARDA high-port services and Socket Guardian were not active at audit time. This does not negate the test evidence. |
| Current host-local Guardian validation | **4/5 validation checks (80%)** | Signed authority, installed Guardian, live consumers, and process/Guardian replacement pass; actual reboot acceptance remains. This does not change the production score. |

The percentages are not averaged into a single “BEAST completion” number.
Doing so would incorrectly imply that tested local primitives and an operating
SOC 2 control environment are interchangeable.

## Reproducible verification performed

The corrected focused acceptance suite completed with **143 passed** and one
Starlette pending-deprecation warning. It covered Sensorium, journal replay,
process/socket identity, Socket Guardian, exact signed one-use authorization,
external-listener restart adoption, Crystal Bus/capsules, crystallization,
causal/equality helpers, held-out replay, Port Conflict Repair, rollback,
Control Evidence Graph, ReleaseChain, ARDA/Metatron bridge contracts, Commons,
CapabilityPlane, PSI/memory/interference policy, Worktree Forge, and SourcePlan
evidence.

Additional gates completed:

- `python3 -m compileall` passed for the execution, Sensorium, Commons,
  compute, evidence, and integration packages.
- `git diff --check` passed.
- `systemd-analyze --user verify` passed for the generated Guardian service,
  five named socket units, and the BEAST and Commons consumer units.
- A post-audit integration family completed with **66 passed**, covering the
  Guardian, Sensorium, Commons, Evidence Graph, and ARDA bridge. Its focused
  consumer subset completed with **13 passed** and proved that two different
  Uvicorn process identities served HTTP from the same Guardian-retained lease
  and listener generation.
- The installed live-validation pass later completed with **76 BEAST tests**
  and **8 ARDA authority tests**. It produced durable consumer-restart and
  Guardian-replacement receipts with continuous port-ownership sampling.
- The first broad command exposed one stale test filename before collection;
  the command was corrected rather than counting a non-run.

The earlier **144-test** Commons/Sensorium run remains historical evidence from
2026-07-14. It is a different selection and is not added to 143 as if the
tests were disjoint.

## DevSecOps master-plan gate accounting

| Phase | Gates complete | Assessment |
|---|---:|---|
| 0 — boundaries, ownership, threat/evidence catalog | 2/4 | Claim boundaries and ownership are strong; complete control owners/frequencies and external scope review remain. |
| 1 — tool leases and negative capability memory | 1/4 | Semantic buckets/lazy exposure exist; one universal signed invocation lease authority and complete negative-store adversarial proof do not. |
| 2 — PSI shadow admission | 2/4 | PSI parsing and explainable decisions exist; calibrated representative overhead/SLO evidence does not. |
| 3 — bounded resource enforcement | 2/5 | Lane bulkheads and fail-closed hazardous contracts exist; host-class pressure/latency/oscillation acceptance is incomplete. |
| 4 — provider/API reliability | 2/4 | Route damping, read-time decay, persistence, and tests exist; cross-scope coalescing/idempotency and measured retry reduction remain. |
| 5 — ports and repository identity | 2/4 | Workspace/service identities and durable Guardian leases exist; health-projected DNS/proxy activation and universal request-envelope enforcement remain. |
| 6 — ARDA relying-party contract | 5/5 repository gates | Exact signed decisions, audience/policy/appraisal binding, expiry, and one-use replay control are tested. Production key/endpoints and measured host attestation are a separate live gate and are absent. |
| 7 — Release Governor | 0/5 | Worktrees, SourcePlan gates, artifact CAS, and graph primitives are inputs, not an end-to-end pinned build/SBOM/provenance/independent-verification release governor. |
| 8 — attested deployment/runtime reconciliation | 0/5 | Contracts and rollback helpers exist; deployment-by-digest through live ARDA/Metatron/Seraph has not been accepted end to end. |
| 9 — Commons Vault/River/Forge | 3/4 | Integrity, privacy, and local-authority gates are tested; retention/GC and OCI/ORAS closure remain. |
| 10 — Job Choir/Witness | 3/5 | Attestation expiry, input/output digests, deterministic selection, and signed witness receipts exist; cancellation/idempotency/quarantine production flow is incomplete. |
| 11 — Evidence Graph/SOC 2 exporter | 1/5 | Durable rebuild and tamper fracture detection pass; full populations, audit windows, scoped exports, and external review remain. |
| 12 — advanced hardware/network enforcement | 1/4 | Capability discovery and advisory memory policy exist; resctrl/DAMON enforcement, VRFs, and AF_XDP remain laboratory work. |
| 13 — `sched_ext` laboratory | 0/3 | Not implemented. |

Total: **24 complete gates out of 61**.

## Sensorium evidence

Complete and tested (10): versioned content-bound contracts; privacy before
admission; ordered bounded sequencing; explicit loss accounting; hash-chained
SQLite replay; RuntimeEpisode closure; ProcessLease/pidfd identity; governed
cgroup lifecycle; typed SocketIdentity/reconciliation; PSI and payload-free
read models.

Partial or outstanding (5): fanotify-grade file attribution; BPF ordered
fork/exec/exit ring; `sock_diag` IPv4/IPv6/TCP/UDP inventory (the current helper
reads IPv4 TCP `/proc/net/tcp`); live packet-to-socket-to-mission correlation;
complete Runtime Observatory visual acceptance.

The global Sensorium runtime and Commons evidence bridge are wired in product
code. At audit time the BEAST API itself was not listening, so the audit does
not claim a continuously operating host Sensorium.

## Proof-carrying crystal evidence

Complete and tested (10): authority-bounded Crystal IR contracts; ordered
episode extraction; topology/resource/negative-condition retention; typed
hypergraph; held-out all-variants replay gate; credentialled
`AF_UNIX/SOCK_SEQPACKET`/`SCM_RIGHTS` transport; sealed memfd inspection and
signature/authority bindings; exact signed one-use execution authorization;
bounded Port Conflict Repair planning/actuation with independent
postconditions; durable execution/evidence receipts and rollback helpers.

Partial or outstanding (5): the causal engine is evidence-bounded heuristics,
not general causal discovery; `EqualitySaturation` is verified alternative
selection, not an e-graph rewrite/saturation engine; destructive stale-process
retirement is intentionally not a bounded actuator; natural-task parameter
generalization and verifier synthesis are not automatic; no live autonomous
promotion/reuse recurrence has been accepted as production physical compute.

Therefore “BEAST can transport, authorize, replay-test, and execute one bounded
proof-carrying system transformation” is supported. “BEAST generally learns
new verified programs from arbitrary runtime behavior” is not yet supported.

## Commons evidence

Complete and tested (12): signed manifest registry; immutable vault; verified
chunk store; deterministic/lazy Dataset River and lineage; attestation-filtered
Job Choir; signed job witnesses; route damping with persistence and read-time
decay; appraisal-gated Space Forge; workspace/policy binding; Sensorium
projection; durable Control Evidence Graph projection; fail-closed readiness
when trust configuration is missing.

Outstanding (3): OCI/ORAS artifact transport; live federated node sessions
with production ARDA attestations; production trust keys, endpoints, buckets,
and service rollout. The current foundation is enterprise-shaped local code,
not a live multi-node Commons service.

## SOC 2 readiness evidence

Complete evidence capabilities (5): tamper-evident durable receipts; graph
reconstruction; basic release/digest/approval exception queries; privacy and
export gates; security/availability/processing-integrity event inputs from
Guardian, PSI, Commons, and crystal execution.

Outstanding evidence capabilities (7): a versioned control catalog with owner
and frequency; complete population/closure queries; audit-window snapshots;
retention and legal/redaction workflows; access-review/vulnerability/incident
evidence packs; backup/restore and disaster-recovery exercise packs;
access-controlled reproducible auditor exports with external usefulness review.

BEAST may accurately be called **SOC 2 readiness and evidence infrastructure
under development**. It cannot claim control operating effectiveness over an
observation period, compliance, certification, or an auditor-issued SOC 2
report.

## Socket Guardian production boundary completed in this pass

New repository evidence now proves:

- every mutating Guardian operation can be bound to the complete request,
  including ProcessLease/workspace/appraisal/policy/registry fields;
- an Ed25519 authority signature is verified and the capability is consumed
  atomically once in a durable SQLite ledger;
- an externally retained TCP listener survives complete Guardian process
  replacement and returns at the same port with an incremented generation;
- inherited descriptors require exact `LISTEN_FDNAME` mappings and complete
  deployment authority references;
- production daemon configuration rejects missing keys, permissive private-key
  modes, symlink keys, unresolved environment variables, and placeholder
  authority references;
- generated user-systemd units use named descriptors and pass unit validation.
- BEAST `gateway --socket-mode guardian` and the dedicated Commons gateway
  recover the signed listener through `SCM_RIGHTS` and pass it directly to
  Uvicorn; neither performs another bind in Guardian mode;
- a real child Uvicorn server was terminated and replaced by a different PID,
  which served successfully from the same Guardian lease, port, and generation;
- service readiness and shutdown are projected back into the Guardian health
  state, and authority or health rejection is not treated as a retryable
  listener race;
- the Commons listener exposes its UI root and Commons-owned route families
  while denying unrelated BEAST control-plane paths;
- consumer bearer material is loaded as a private systemd credential rather
  than committed or placed in the unit environment, and signed handoff receipts
  are atomically persisted with file and directory synchronization.

Current deployment boundary:

- generated units are in `.beast/generated/systemd-user/` but are not installed;
- `systemctl --user` reported the Guardian service `not-found`/`inactive`;
- no BEAST `8001`, BEAST upstream `8101`, Commons `8601`, or ARDA `8401`
  listener was present in the audit-time socket inventory;
- no production Guardian YAML, receipt private key, or ARDA/Metatron operation
  public-key trust set was generated automatically;
- no real ARDA/Metatron operation capability endpoint was provisioned, so the
  generated consumers were validated but not activated as production services.

Post-audit live validation changed the host state described above: the user
units are now installed, the ARDA Guardian endpoint is live on loopback, and
BEAST/Commons are active through signed handoffs. Consumer and Guardian
replacement both pass without a port-ownership gap. These use host-local file
keys and a static sovereign-proof digest, so the production exit score remains
unchanged. See `docs/beast-guardian-live-validation-2026-07-15.md`.

No sudo is required for the configured high ports or a per-user systemd unit.
Installing a system reverse proxy on port 80, editing system hosts/DNS, or
system-wide service installation remains an administrator action.

## Immediate critical path

1. Schedule the actual reboot acceptance, then replace local validation keys
   and static appraisal evidence with managed keys and fresh measured
   ARDA/Metatron attestation.
2. Route `beast.test` and `commons.test` through the reviewed generated proxy,
   enable workspace enforcement, and record live health/handoff evidence.
3. Build Phase 7 as a real release governor: pinned ephemeral builder, SBOM,
   signed provenance, independent verification, and artifact closure.
4. Bind Phase 8 deployment to approved digest plus live ARDA appraisal and
   reconcile the running digest through Sensorium/Seraph.
5. Add the SOC 2 control catalog, audit-window scheduler, complete population
   queries, and scoped evidence-pack exporter.
6. Replace heuristic crystal generalization/equivalence helpers with held-out
   natural-task extraction and a real e-graph laboratory before any broad
   autonomous-promotion claim.
