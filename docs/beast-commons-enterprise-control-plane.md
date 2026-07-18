# BEAST Commons Enterprise Control Plane

Status: implemented foundation with fail-closed production admission gates.

Scope: BEAST, Commons, ARDA, and Seraph. VAMP and Hivenance are deliberately
excluded from this control-plane release.

## 1. Operating model

BEAST is the policy and resource control plane. Commons is the governed
artifact, dataset, Space, and worker exchange. ARDA is the appraisal authority.
Seraph consumes runtime observation and containment evidence.

The control plane separates four decisions:

1. The Agent Scheduler chooses the semantic lane.
2. CapabilityPlane exposes only the tool buckets justified by phase and risk.
3. ResourceExecutor admits the job to a bounded physical workload lane.
4. Commons admission verifies authority, artifact identity, appraisal, route
   stability, and workspace binding before consequential operations.

Remote Commons contributions remain hypotheses. Local policy, reproduction,
and verification create trust.

## 2. Authoritative configuration

The repository root owns the five inherited manifests:

- `.byron/project.yaml`: family, canonical repository, identity fields, and
  scanner exclusions.
- `.byron/services.yaml`: hostname, unique upstream, health path, and trust
  domain for every local service.
- `.byron/tools.yaml`: semantic buckets and approval rules.
- `.byron/workloads.yaml`: lane widths, isolation, bounded admission, and PSI
  thresholds.
- `.byron/policy.yaml`: Commons, evidence, and workspace-identity policy.

Child repositories may add their own `.byron` directory. The loader walks from
the filesystem root to the activated workspace, merges manifests in that
order, and unions exclusions. A child cannot erase inherited exclusions by
omitting them.

## 3. Service and port authority

`.byron/services.yaml` is the source of truth:

| Service | Hostname | Upstream | Trust domain |
|---|---|---:|---|
| BEAST | `beast.test` | `127.0.0.1:8101` | operator |
| Commons | `commons.test` | `127.0.0.1:8601` | commons |
| ARDA | `arda.test` | `127.0.0.1:8401` | witness |
| Seraph UI | `seraph.test` | `127.0.0.1:8201` | operator |
| Seraph API | `api.seraph.test` | `127.0.0.1:8202` | production |

The registry rejects duplicate hostnames, duplicate ports, non-`.test` names,
non-loopback upstreams, upstream/port mismatches, invalid health paths, and
unknown trust domains. The BEAST CLI and Electron launcher now use `8101` for
the gateway instead of legacy `8000/8001` defaults.

`POST /edgek/control-plane/services/render` atomically writes:

- `.beast/control-plane/generated/hosts.generated`
- `.beast/control-plane/generated/nginx.generated.conf`

Rendering does not mutate `/etc/hosts`, install NGINX, or reload a live proxy.
Those remain explicit administrator/deployment actions. This prevents a UI
request from silently acquiring host authority.

For production-shaped local activation, generated user-systemd socket units
retain the registry listeners outside the server processes. The BEAST and
dedicated Commons consumer services obtain exact signed one-use
ARDA/Metatron capabilities, recover their already-bound descriptors from the
Socket Guardian through `SCM_RIGHTS`, and pass those descriptors directly to
Uvicorn. A server restart therefore does not release or reselect the port. The
Commons service permits its UI root and Commons-owned route families only;
unrelated BEAST routes return 404 at the outer ASGI boundary.

## 4. Workspace identity boundary

The identity digest binds:

- repository
- remote
- branch
- HEAD
- canonical root
- worktree ID
- stable workspace UUID

The desktop runtime obtains the digest from BEAST and sends
`X-BEAST-Workspace-Identity` on subsequent HTTP and Electron gateway calls.
Commons and control-plane mutations compare it with the active server identity.

Rollout is staged with `BEAST_WORKSPACE_IDENTITY_MODE`:

- `audit` (default): allow the request, mark `missing` or `mismatch`, and emit
  the status response header.
- `enforce`: return HTTP 409 before a governed mutation when identity is absent
  or different.

Exact identity equality is required before workspace-scoped cache reuse. A
matching path alone is not an identity match.

## 5. Semantic tool exposure

CapabilityPlane is the single read authority for the seven buckets:

`Observe → Reason → Verify → Modify → Connect → Execute → Administer`

`POST /edgek/capability-plane/expose` accepts phase, risk, network need,
mutation intent, approval state, failed tools, and schema mode. Lazy mode omits
full metadata/schema payloads. High-risk execution and critical mutation remain
hidden without approval. Failed tools are suppressed for the active decision.
The returned receipt records visible tools and the hidden count.

Exposure is not invocation authority. A visible schema still requires its
normal SourcePlan, capability, ARDA, Metatron, or operator gate.

## 6. Workload execution

ResourceExecutor provides six bounded bulkheads:

- interactive
- I/O
- CPU
- inference
- exclusive
- hazardous sandbox

Each lane has a fixed worker count and bounded admission capacity. Saturation
rejects new work instead of growing an unbounded memory queue. CPU work may opt
into process isolation when its callable is serialization-safe. Inference uses
its dedicated lane. Exclusive keys prevent concurrent jobs from mutating the
same declared resource. Hazardous work requires both explicit approval and an
acknowledged sandbox boundary.

PSI-derived interference decisions adjust CPU weight and memory concurrency.
Operator/security lanes are protected; quarantine/deception lanes are capped;
rising pressure throttles background work; full pressure constrains admission.
The executor exposes submitted, completed, rejected, in-flight, worker, and
capacity counts per lane.

## 7. Enterprise Commons composition

`CommonsEnterprisePlane` owns persistent state under
`.beast/commons-enterprise/`:

- Artifact Registry: authority-bound, content-addressed manifest records.
- Artifact Vault: digest-verified immutable bytes.
- Chunk Store: 64 KiB default chunks, per-chunk verification, resumable reads,
  missing-chunk detection, and cross-artifact deduplication.
- Dataset River: deterministic shards, exact dataset digest option, lineage,
  and public/internal/restricted/private labels.
- Job Choir: capability fit, verified attestation, advertisement expiry,
  pressure budget, reliability, and route penalty.
- Route Damping: persistent exponentially decayed instability scores.
- Space Forge: digest-bound image, bounded resources, `commons://` mounts,
  outbound policy, authority, signature, and ARDA appraisal.

Registry and Space signatures use detached Ed25519 verification over canonical
JSON. A mere signature string is not accepted in enterprise mode.

### Production admission provisioning

Set both variables before allowing artifact, node, or Space admission:

```text
BEAST_COMMONS_TRUST_STORE=/absolute/path/commons-trust.yaml
BEAST_ARDA_APPRAISAL_PUBLIC_KEY=/absolute/path/arda-appraisal-public.pem
```

Trust-store shape:

```yaml
authorities:
  beast.release:
    public_key_path: keys/beast-release-public.pem
```

Paths are resolved relative to the trust-store file and cannot escape that
directory. Inline `public_key_pem_b64` is also accepted. Private keys must not
be stored in the BEAST repository or audit bundle.

ARDA appraisals are bound to the exact canonical Space body, appraisal
reference, policy generation, audience `commons-space-forge`, expiry, authority,
request digest, nonce, and Ed25519 signed decision. Any body change invalidates
the appraisal.

Commons node evidence uses the same public ARDA root with the distinct audience
`commons-job-choir`. It binds node identity, capabilities, pressure budget,
reliability, route penalty, advertisement expiry, and appraisal reference. The
literal node field `attestation: verified` is only a declared state and is
never sufficient for enterprise selection by itself.

If either verifier is absent, `GET /edgek/control-plane/commons` reports
`configuration_required`; artifact/Space admission returns a fail-closed error.
Read-only inventory remains available for diagnosis.

## 8. Enterprise API surface

- `GET /edgek/control-plane/enterprise`
- `GET /edgek/control-plane/workspace-identity`
- `GET /edgek/control-plane/services`
- `POST /edgek/control-plane/services/render`
- `GET /edgek/control-plane/commons`
- `POST /edgek/control-plane/commons/artifacts`
- `POST /edgek/control-plane/commons/routes/events`
- `POST /edgek/control-plane/commons/jobs/select`
- `POST /edgek/control-plane/commons/spaces/validate`
- `POST /edgek/capability-plane/expose`

The mutation endpoints are workspace-identity governed. CORS defaults to local
Electron and loopback origins only. Additional origins require the explicit
`BEAST_CORS_ORIGINS` setting; credentials are not enabled by default.

## 9. Failure and recovery behavior

- Unknown signing authority: deny.
- Invalid or non-Ed25519 verification material: refuse startup configuration.
- Missing signature/appraisal verifier: keep reads online, deny admission.
- Expired or mismatched ARDA appraisal: deny.
- Expired/unverified Commons node: exclude from scheduling.
- Unstable route: decay penalty on reads and suppress above threshold.
- Missing workspace identity in audit mode: allow with visible status.
- Missing workspace identity in enforce mode: HTTP 409 before mutation.
- Full workload lane: reject admission; do not buffer indefinitely.
- Proxy render failure: preserve the last complete generated file via atomic
  replacement.

## 10. Rollout sequence

1. Keep identity mode at `audit`; collect missing/mismatch telemetry.
2. Provision public trust material and the signed ARDA appraisal verifier.
3. Validate local artifact, Space, route, and node fixtures.
4. Render and review hosts/NGINX files; install them through administrator
   change control.
5. Provision the Guardian/authority public keys, private systemd bearer
   credential, signed deployment bindings, and reviewed Guardian YAML.
6. Install and activate the generated user socket/Guardian/consumer units;
   verify BEAST `8101` and Commons `8601` survive consumer PID replacement.
7. Restart the Electron shell against the registry-owned `8101` upstream.
8. Change identity mode to `enforce` for Commons/control-plane mutations.
9. Exercise route suppression/recovery, worker expiry, capacity saturation,
   and appraisal tampering in a non-production environment.
10. Attach durable Evidence Graph receipts and Seraph observation to the
   deployed operations before claiming audit-period effectiveness.

## 11. Current claim boundary

Implemented and tested: authoritative manifests, unique local service registry,
generated proxy/hosts artifacts, exact workspace identity guard, lazy semantic
tool exposure, bounded workload bulkheads, persistent Commons registry/vault/
chunks/route state, deterministic Dataset River, attested Job Choir selection,
Ed25519 Commons verification, and cryptographically bound ARDA Space appraisal.
Guardian-mode BEAST/Commons FD consumption and service-process restart on the
same retained listener are also implemented and integration-tested.

The dedicated Commons listener is now live in host-local validation on 8601.
Its read surface responds and its outer route boundary is enforced. Its
admission status remains `configuration_required` because Commons artifact,
node-attestation, Space-appraisal, and witness trust roots were not fabricated
to make the dashboard green.

Provisioning-dependent: live authority keys, live ARDA appraisal issuance,
administrator installation of hosts/proxy configuration, actual cgroup/process
sandbox placement, installation/reboot acceptance of the generated user units,
and Seraph runtime containment. These are deliberately
reported as configuration requirements, not simulated successes.
