# Physical Crystal Fabric Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile stale remote Commons endpoints only after proving the live candidate has the same signed, governed node identity.

**Architecture:** Add a fail-closed reconciliation operation to the remote Commons gateway. It verifies the candidate endpoint with the existing descriptor verifier before atomically changing the registry, records endpoint history, and exposes the operation through the local operator API; the lab topology generator supplies one consistent port source.

**Tech Stack:** Python 3.13, FastAPI, httpx, SQLite, Ed25519, pytest, Docker Compose

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`

## Global Constraints

- Remote Commons maximum authority remains `verify_only`.
- Never update a registered endpoint before signature, node-key, workload, and configured trust-policy verification succeeds.
- Existing node identity pins are immutable during endpoint reconciliation.
- Reconciliation is restricted to the local operator boundary.
- Historical discovery evidence does not substitute for a fresh endpoint-possession check.
- No raw secrets, native KV arrays, or memfd descriptors cross the remote boundary.

## Review Focus

- A candidate serving a valid descriptor for another pinned node must be refused and the original endpoint retained.
- An unreachable or malformed candidate must leave registry state and endpoint unchanged while recording a refusal result.
- Reconciliation to the current endpoint must be idempotent and still perform a fresh probe.
- Concurrent endpoint updates must not create duplicate endpoints or partially update history.
- IPv4/IPv6 loopback and allowlisted HTTPS candidates must retain Gate-of-Night validation.

---

### Task 1: Atomic Registry Endpoint Reconciliation

**Files:**
- Modify: `app/kernel/commons/remote_client.py`
- Test: `tests/test_remote_commons_gateway.py`

**Interfaces:**
- Consumes: existing `RemoteCommonsRegistry.get()`, `record_probe()`, and `CommonsEgressGate.validate_base_url()`.
- Produces: `RemoteCommonsRegistry.reconcile_endpoint(node_id: str, endpoint: str, result: Mapping[str, Any]) -> dict[str, Any]` and endpoint history in registry snapshots.

- [ ] **Step 1: Write failing registry tests**

Add tests proving atomic endpoint replacement, immutable identity pins, endpoint-history recording, idempotence, and uniqueness under conflicting endpoints.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py -k 'reconcile_endpoint or endpoint_history'`

Expected: FAIL because `reconcile_endpoint` and endpoint history do not exist.

- [ ] **Step 3: Implement the registry transaction**

Add the history table and `reconcile_endpoint(...)`. The transaction must preserve the pinned key, workload digest, and trust policy; append old/new endpoint history; update the endpoint and verified probe together; and roll back on uniqueness conflicts.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py -k 'reconcile_endpoint or endpoint_history'`

Expected: PASS.

### Task 2: Signed Candidate Verification

**Files:**
- Modify: `app/kernel/commons/remote_client.py`
- Test: `tests/test_remote_commons_gateway.py`

**Interfaces:**
- Consumes: Task 1 `reconcile_endpoint(...)` and existing `_verify_node_document(...)`.
- Produces: `RemoteCommonsGateway.reconcile_endpoint(node_id: str, candidate_endpoint: str) -> dict[str, Any]`.

- [ ] **Step 1: Write failing gateway tests**

Add tests proving a verified same-identity candidate updates atomically, while wrong key/node/workload, malformed documents, unreachable candidates, and Gate-of-Night violations retain the original endpoint.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py -k 'gateway_reconcile'`

Expected: FAIL because the gateway operation does not exist.

- [ ] **Step 3: Implement candidate-first verification**

Add `reconcile_endpoint(...)`. Validate the candidate origin, fetch `/v1/node` directly without authentication, verify it against a copy of the pinned node record, enforce lattice monotonicity, then call the Task 1 transaction. Return a structured refusal without changing the endpoint on any failure.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py -k 'gateway_reconcile'`

Expected: PASS.

### Task 3: Local Operator API and Topology Contract

**Files:**
- Modify: `app/routes/commons_remote.py`
- Modify: `app/main.py`
- Modify: `scripts/provision_remote_commons_lab.py`
- Modify: `docker-compose.commons-lab.yml`
- Test: `tests/test_remote_commons_gateway.py`
- Test: `tests/test_remote_commons_node.py`

**Interfaces:**
- Consumes: Task 2 `RemoteCommonsGateway.reconcile_endpoint(...)`.
- Produces: `POST /edgek/control-plane/commons/remote/nodes/{node_id}/reconcile` with `{candidate_endpoint}` and a generated Compose override path in the provisioning manifest.

- [ ] **Step 1: Write failing route and topology tests**

Test local-only reconciliation, candidate validation, remote-operator refusal, manifest/Compose port agreement, and absence of duplicate manually declared remote routes in `app/main.py`.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py tests/test_remote_commons_node.py -k 'reconcile or topology_contract or remote_route_registration'`

Expected: FAIL because the route and unified topology output do not exist.

- [ ] **Step 3: Add the route and single topology output**

Mount reconciliation only through `build_remote_commons_router`, remove the duplicate manual remote route declarations, and make provisioning generate the Compose port override from the same manifest node list.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py tests/test_remote_commons_node.py -k 'reconcile or topology_contract or remote_route_registration'`

Expected: PASS.

### Task 4: Live Recovery and Verification

**Files:**
- Modify: `desktop-ide/renderer/js/pages/beast-commons-page.js` only if the existing page cannot render reconciliation status.
- Test: `tests/test_remote_commons_gateway.py`

**Interfaces:**
- Consumes: Tasks 1–3 API and live Docker nodes.
- Produces: three freshly probed lattice-attested registry rows on the running endpoints and visible reconciliation receipts.

- [ ] **Step 1: Run the non-PQ regression suite**

Run: `.venv/bin/python -m pytest -q tests/test_remote_commons_gateway.py tests/test_crystal_bus_capsule.py tests/test_socket_guardian.py tests/test_forge_kv_coordinator.py tests/test_forge_kv_level1.py`

Expected: PASS with no host-side liboqs bootstrap.

- [ ] **Step 2: Reconcile the three live candidates through the operator API**

Use `8111`, `8112`, and `8113`; do not edit SQLite directly. Confirm each receipt reports signed descriptor verification and the prior endpoint.

- [ ] **Step 3: Verify live registry and node identity**

Run read-only API checks for the registry snapshot, discovery snapshot, node buckets, and signed descriptors. Expected: all three registry rows are admitted on live endpoints; identity pins and workload digests are unchanged.

- [ ] **Step 4: Run repository verification**

Run the focused test suite, relevant lint, `git diff --check`, and the desktop smoke test if renderer code changed. Report any unrelated full-suite failures by name.
