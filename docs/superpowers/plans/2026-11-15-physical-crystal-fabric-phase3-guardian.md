# Physical Crystal Fabric Phase 3 Guardian Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Socket Guardian the live owner of BEAST and Commons listening sockets, with every bind driven by one topology source, descriptor custody held by the Guardian, and signed lifecycle receipts for each transition.

**Architecture:** A fabric topology contract derives Guardian service bindings and Commons node ports from the existing sources and fails closed on drift. The existing Guardian daemon (`socket_guardian_daemon.py`) adopts listeners for the bound services and hands them to `bin/beast gateway --socket-mode guardian` through `guardian_uvicorn.py`, which uses SCM_RIGHTS, ARDA/Metatron one-use operation capabilities and signed handoff receipts. Commons nodes running in Docker cannot receive Guardian descriptors across the container boundary, so they get signed custody evidence binding each published port to the node's signed descriptor (ruling D3.3: custody records only).

**Tech Stack:** Python 3.13, AF_UNIX SOCK_SEQPACKET, SCM_RIGHTS, Ed25519, SQLite, FastAPI/Uvicorn, systemd socket units (generated, never auto-installed), Docker Compose, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`
**Roadmap:** `docs/superpowers/plans/2026-11-15-physical-crystal-fabric-roadmap.md`

## Global Constraints

- Commons remains `verify_only`; Guardian custody never grants execution or promotion authority.
- The Guardian never binds, adopts, or hands off a listener whose port disagrees with the topology contract.
- Every Guardian operation needs an exact one-use ARDA/Metatron capability and produces a signed receipt. No development defaults, placeholder references, or unsigned receipts.
- The operator's running 8101 gateway is never restarted or relaunched by an agent. Live verification uses a temporary instance on a spare port.
- No writes to `~/.config`, systemd units, or other host locations, and no privileged changes, without an explicit operator decision.
- No signing keys, tokens, or capabilities in logs, receipts, API responses, or the repository.

## Review Focus

- Topology drift (manifest vs Compose vs registry vs Guardian bindings) must be reported and must block Guardian binding, never silently resolved.
- A port collision between a Guardian-owned service and a Commons node must fail closed.
- A recovered descriptor whose address differs from its signed lease must be refused (existing `recover_named_listener` check retained).
- Guardian restart must orphan, not revive, earlier leases (existing ledger behavior retained).
- Docker custody evidence must bind the published port to a freshly verified signed descriptor, not to container metadata alone.

## Operator Decisions (ruled 2026-11-15)

- **D3.1 Host trust roots and authority:** real host roots in `~/.config/beast` (`scripts/provision_guardian_validation.py` defaults) with ARDA as the Guardian operation authority. Provisioning and starting ARDA happen only when Guardian work resumes.
- **D3.2 Launch mode:** generated systemd user units (`scripts/generate_socket_guardian_units.py`). Units are generated for review and installed/enabled by the operator only. BEAST 8101 is relaunched with `--socket-mode guardian` by the operator only.
- **D3.3 Commons-in-Docker custody:** signed custody records only. Guardian/Sensorium sign receipts binding 127.0.0.1:811x → container → freshly verified descriptor digest; Docker keeps socket ownership.
- **Sequencing:** Tasks 2-4 resume after deliveries 5 and 6. Task 1 is complete, and the lab topology is aligned to 8111-8113.

---

### Task 1: Fabric Topology Contract (decision-independent)

**Files:**
- Create: `app/kernel/networking/fabric_topology.py`
- Create: `scripts/check_fabric_topology.py`
- Test: `tests/test_fabric_topology.py`

**Interfaces:**
- Consumes: `.byron/services.yaml` (via `ServiceRegistry`), `.beast/remote-commons-lab/manifest.json`, `docker-compose.commons-lab.yml` plus optional Compose override, optional live registry endpoints.
- Produces: `FabricTopology.load(...)`, `FabricTopology.drift(registry_endpoints=None) -> list[dict]`, `FabricTopology.guardian_bindings() -> dict`, `FabricTopology.require_consistent(...)`, `topology_digest`, and a read-only CLI with a zero/nonzero exit contract.

- [ ] Write tests for consistent sources, manifest/Compose port mismatch, override precedence, registry endpoint mismatch, Guardian/Commons port collision, Guardian bindings limited to `socket_guardian: true` loopback services, digest stability, and CLI exit codes.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_fabric_topology.py` and verify RED.
- [ ] Implement the contract (YAML `!override` aware, no Docker subprocess, read-only).
- [ ] Re-run and verify GREEN; run the CLI against the live sources and record findings.

### Task 2: Topology-Bound Guardian Daemon with Host Roots (D3.1, D3.2)

**Files:**
- Modify: `app/kernel/execution/socket_guardian_daemon.py`
- Modify: `scripts/generate_socket_guardian_units.py` (consume Task 1 bindings; generate only, never install)
- Test: `tests/test_socket_guardian_daemon.py`

**Interfaces:**
- Consumes: Task 1 `guardian_bindings()` and `require_consistent()`.
- Produces: a daemon that refuses to start on topology drift and binds only contract ports.

- [ ] Write tests: drift blocks startup; binding set equals the contract; placeholder references refused.
- [ ] Verify RED, implement, verify GREEN.

### Task 3: Guardian-Owned Gateway Listener (D3.1, D3.2)

**Files:**
- Modify: `bin/beast` (only if the guardian launch path needs a spare-port lab service id)
- Modify: `app/kernel/execution/guardian_uvicorn.py`
- Test: `tests/test_guardian_uvicorn.py`

**Interfaces:**
- Consumes: Task 2 daemon.
- Produces: a temporary gateway on a spare port served from a Guardian-recovered descriptor, with a persisted signed handoff receipt and a healthy lifecycle transition.

- [ ] Write tests for receipt persistence, health transition, and refusal on lease/topology mismatch.
- [ ] Verify RED, implement, verify GREEN.

### Task 4: Commons Signed Custody Records and Live Verification (D3.3)

**Files:**
- Modify: `app/kernel/commons/remote_client.py` (custody fields in fabric health)
- Modify: `desktop-ide/renderer/js/pages/beast-commons-page.js`
- Test: `tests/test_remote_commons_gateway.py`, `desktop-ide/scripts/smoke-desktop-ide.js`

**Interfaces:**
- Consumes: Tasks 1-3, Phase 2 fabric health.
- Produces: per-node custody receipts in `/remote/health`, live Guardian receipts for the temporary gateway, and exact operator commands for relaunching 8101 in guardian mode.

- [ ] Write tests and a smoke assertion, verify RED, implement, verify GREEN.
- [ ] Rebuild/restart the Commons lab, POST health on the temporary instance (3/3 healthy), verify Guardian receipts.
- [ ] Run scoped pytest, Ruff, Compose validation, desktop smoke, and `git diff --check`.
