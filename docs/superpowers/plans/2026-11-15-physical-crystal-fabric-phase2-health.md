# Physical Crystal Fabric Phase 2 Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Commons health prove signed service identity, current trust evidence, and topology agreement instead of accepting process existence or a generic HTTP response.

**Architecture:** A dependency-light node health verifier validates the node's signed descriptor from inside each container and drives Docker health. The control plane aggregates fresh pinned-identity probes, records trust expiry and topology drift, and supersedes historical discovery origins only after signed reconciliation.

**Tech Stack:** Python 3.13 standard library, Ed25519 cryptography, FastAPI, SQLite, Docker Compose, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`

## Global Constraints

- Commons remains `verify_only`; health never grants execution or promotion authority.
- A healthy node must return a correctly signed descriptor for the configured node ID and an unexpired trust-evidence row.
- A generic `200`, process name, or container state is insufficient.
- Health probes never expose signing keys, raw prompts, native KV state, or credentials.
- Discovery candidates are history; only the admitted registry determines the current endpoint.

## Review Focus

- A validly signed descriptor for the wrong node ID must fail health.
- Expired or missing trust evidence must make Docker health fail even while `/health` returns `200`.
- A descriptor mutation without a matching node signature must fail health.
- A failed control-plane refresh must not erase the last admitted identity or endpoint.
- Reconciliation must supersede only older origins for the same node, never other nodes or subjects.

---

### Task 1: Signed Container Health Verifier

**Files:**
- Create: `app/kernel/commons/node_health.py`
- Create: `scripts/check_remote_commons_health.py`
- Modify: `Dockerfile.commons-node`
- Modify: `docker-compose.commons-lab.yml`
- Test: `tests/test_remote_commons_health.py`

**Interfaces:**
- Produces: `verify_node_health(document, *, expected_node_id, now=None) -> dict` and a zero/nonzero CLI exit contract.

- [ ] Write tests for valid, wrong-node, bad-signature, expired-evidence, missing-evidence, and CLI exit behavior.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_remote_commons_health.py` and verify RED.
- [ ] Implement verification and wire Docker `healthcheck` to the CLI.
- [ ] Re-run the test and verify GREEN.

### Task 2: Control-Plane Fabric Health

**Files:**
- Modify: `app/kernel/commons/remote_client.py`
- Modify: `app/routes/commons_remote.py`
- Test: `tests/test_remote_commons_gateway.py`

**Interfaces:**
- Consumes: existing signed `RemoteCommonsGateway.probe()`.
- Produces: `RemoteCommonsGateway.health(refresh: bool = False) -> dict` and `GET/POST /edgek/control-plane/commons/remote/health`.

- [ ] Write tests for all-healthy, stale, expired, refused, partial-network-failure, and local-only refresh behavior.
- [ ] Run focused health tests and verify RED.
- [ ] Implement aggregate health without weakening the last admitted endpoint on refresh failure.
- [ ] Re-run focused health tests and verify GREEN.

### Task 3: Discovery Supersession

**Files:**
- Modify: `app/kernel/commons/discovery.py`
- Modify: `app/kernel/commons/remote_client.py`
- Test: `tests/test_remote_commons_gateway.py`

**Interfaces:**
- Produces: `CommonsDiscoveryCatalog.supersede_origins(node_id, admitted_origin, subject_digest) -> int` and `superseded_candidate` state.

- [ ] Write tests proving same-node old origins are superseded after successful reconciliation while unrelated candidates remain unchanged.
- [ ] Run focused supersession tests and verify RED.
- [ ] Implement transactional supersession and invoke it only after registry reconciliation commits.
- [ ] Re-run focused tests and verify GREEN.

### Task 4: Live Health and IDE Evidence

**Files:**
- Modify: `desktop-ide/renderer/js/pages/beast-commons-page.js` only as needed to render aggregate health, expiry, and endpoint history.
- Test: `desktop-ide/scripts/smoke-desktop-ide.js`

**Interfaces:**
- Consumes: Tasks 1-3 health snapshot.
- Produces: live Docker health, control-plane health receipts, and operator-visible reconciliation state.

- [ ] Add a renderer smoke assertion and verify RED if UI changes are required.
- [ ] Render aggregate health and the latest endpoint transition without exposing pins or secrets.
- [ ] Rebuild/restart the Commons lab, refresh control-plane health, and verify all three containers and nodes are healthy.
- [ ] Run scoped pytest, Ruff, Compose validation, desktop smoke, live API checks, and `git diff --check`.
