# Superpowers Integration Atlas IDE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the completed coding-path integrations into Agent Coder, prove each invocation with durable evidence, and expose the full repository integration state through honest, navigable BEAST Desktop IDE surfaces.

**Architecture:** Add a bounded Agent Coder integration coordinator around the existing tested implementations, emitting one normalized event for every attempted or fired capability while preserving verifier/operator gates. Add one read-only IDE integration catalog that separates implementation availability, feature-flag activation, persisted run evidence, live observations, and claim boundaries. Systems Atlas renders the complete catalog and links each capability to its existing operational surface; existing domain pages consume the same store projection so there is no second source of truth.

**Tech Stack:** Python 3.13, FastAPI, vanilla JavaScript, Electron renderer, Node smoke tests, pytest

**Spec:** `docs/superpowers/specs/2026-11-15-physical-crystal-fabric-spine-design.md`, all completed ledgers under `.superpowers/sdd/*/progress.md`, and the source-of-record audit at `evidence/agent-coder-audit-2026-11-16/REPORT.md` with `superpowers-inventory.json`

## Global Constraints

- Preserve unrelated dirty evidence and generated configuration files.
- Never expose secret values, signing keys, raw prompts, file contents, pins, capabilities, or private payloads.
- Treat implementation, enabled state, persisted evidence, and live state as distinct facts.
- Default-off integrations remain visibly disabled; the IDE must not imply that tested code is active.
- Similarity, specialist adapters, crystals, and Commons artifacts are proposals or verify-only evidence until their existing verifier and operator gates admit them.
- No new execution or promotion authority is introduced by the IDE adapter.
- ML-KEM, XDP/eBPF, X7 LSM, and ARDA remain operator-loaded infrastructure. The IDE may map their state but must not load or activate them.
- Crystal production may create candidates, but admission/publication remains behind the existing verifier, lattice, and operator gates.
- Swarm output remains advisory and must rejoin the governed cascade before execution.
- Preserve the audit's three-way distinction: backend works, IDE wiring exists, and fires in a real Agent Coder run. A probe outside the run is never promoted to an in-run fire.
- The planned `app/kernel/compute/kv_transport.py` path is missing. Map that as a plan-path gap while naming the real tested `app/kernel/compute/kv_memfd_handoff.py` implementation and its host-local/synthetic claim boundary.

## Review Focus

- Missing optional databases/artifacts must produce an available-but-empty capability, not a gateway failure.
- Environment variables may be named but their values must never appear in the response or renderer.
- A disabled tested integration must not render as live, ready, admitted, or executing.
- Catalog entries must link only to registered IDE routes and every Superpowers delivery must have at least one surface.
- Renderer refresh failures must retain no seeded/demo replacement state and must show the error.

---

### Task 1: Canonical IDE integration catalog and route

**Files:**
- Create: `app/routes/ide_support/integration_catalog.py`
- Create: `app/routes/ide_routes/integrations.py`
- Modify: `app/routes/ide.py`
- Create: `tests/routes/test_ide_integration_catalog.py`

**Interfaces:**
- Produces: `build_integration_catalog(root: Path, environ: Mapping[str, str] | None = None) -> dict[str, Any]` and `GET /edgek/ide/integrations?root_path=...`.
- Consumes: completed Superpowers plan/ledger contracts, feature flags, safe local artifact metadata, and existing route names only.

- [ ] **Step 1: Write failing catalog tests**

Assert complete capability IDs, surface mappings, feature-flag state, missing-artifact tolerance, summary counts, and absence of supplied secret values.

- [ ] **Step 2: Run tests to verify RED**

Run: `.venv/bin/python -m pytest -q tests/routes/test_ide_integration_catalog.py`

Expected: FAIL because the catalog module and route registrar do not exist.

- [ ] **Step 3: Implement the catalog and register the route**

Use a declarative capability tuple plus bounded read-only probes. Return `implemented`, `enabled`, `evidence`, `live`, `claim`, `source`, `flags`, `surfaces`, `primary_surface`, and any explicit plan-path gap without returning environment values. Capability families must cover every audit-table row; detailed child integrations may share a family card but may not disappear.

- [ ] **Step 4: Run focused tests to verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/routes/test_ide_integration_catalog.py tests/routes/test_ide_support_common.py`

Expected: PASS.

### Task 2: Agent Coder integration firing contract

**Files:**
- Create: `app/kernel/agents/coder_integrations.py`
- Create: `tests/kernel/agents/test_coder_integrations.py`

**Interfaces:**
- Produces: a normalized integration result/event contract with `capability`, `status`, `mode`, `reason`, bounded metrics, and artifact references safe for run evidence.
- Consumes: existing compression, Vector RAG, memory hull/seal, crystal/family/bus, and swarm implementations without bypassing their feature flags or admission gates.

- [ ] **Step 1: Write failing coordinator tests**

Cover RTK/SQZ/longcodezip tier selection, Vector RAG retrieval, memory hull read/seal, crystal candidate/reuse/family lookup, crystal bus probe/transfer eligibility, and swarm advisory selection. Assert a normalized log event for fired, skipped, and failed paths.

- [ ] **Step 2: Run focused tests to verify RED**

Run: `.venv/bin/python -m pytest -q tests/kernel/agents/test_coder_integrations.py`

- [ ] **Step 3: Implement the coordinator using existing public contracts**

Keep execution bounded, redact payloads, reuse existing flags, and never auto-promote or auto-load infrastructure.

- [ ] **Step 4: Run focused tests to verify GREEN**

### Task 3: Wire the coordinator into Agent Coder and persist evidence

**Files:**
- Modify: `app/routes/ide_routes/agent_run_stream.py`
- Modify: `app/cli/api.py`
- Modify: `app/routes/sourceplan.py`
- Modify: `app/kernel/agents/run_store.py` only if the existing event API cannot store the normalized evidence
- Create: `tests/routes/test_agent_coder_integrations.py`

**Interfaces:**
- Consumes: Task 2 coordinator.
- Produces: pre-provider context events and post-run learning/seal events named `agent.integration.fired`, `agent.integration.skipped`, or `agent.integration.failed`, available both in the live IDE stream and durable run history.

- [ ] Write failing route/runtime tests proving every requested coding-path capability is invoked at the correct lifecycle point.
- [ ] Integrate preflight retrieval/compression/reuse/swarm before provider handoff.
- [ ] Integrate memory seal and crystal candidate production after a completed verified turn.
- [ ] Persist and stream normalized evidence without raw prompts, source contents, or secrets.
- [ ] Run focused tests and capture one evidence line per capability.

### Task 4: TGI model identity through LiteLLM

**Files:**
- Modify the smallest provider/model normalization module identified by the failing regression.
- Create or modify the corresponding provider regression test.

**Interfaces:**
- Consumes: the actual TGI model identity discovered from `/v1/models` or `/info`.
- Produces: a LiteLLM-safe provider/model pair without rewriting a valid TGI-served model into an unsupported identifier.

- [ ] Reproduce the rejection in a focused test before editing production code.
- [ ] Trace model discovery, Auto routing rename, and LiteLLM normalization end-to-end.
- [ ] Implement the narrow normalization fix and verify existing provider inventory tests.

### Task 5: Renderer integration store and bridge

**Files:**
- Modify: `desktop-ide/renderer/js/beast-store.js`
- Create: `desktop-ide/renderer/js/beast-integration-map.js`
- Modify: `desktop-ide/renderer/index.html`
- Modify: `desktop-ide/scripts/smoke-desktop-ide.js`

**Interfaces:**
- Consumes: `GET /edgek/ide/integrations`.
- Produces: `BeastIntegrationMap.refresh()`, `BeastIntegrationMap.bySurface(route)`, and `BeastStore.integrations` with no seeded capability data.

- [ ] **Step 1: Add failing renderer smoke assertions**

Assert the endpoint, script load, empty initial store, refresh/error handling, and implemented/enabled/live separation.

- [ ] **Step 2: Run smoke to verify RED**

Run: `node desktop-ide/scripts/smoke-desktop-ide.js`

Expected: FAIL on the new integration-map assertion.

- [ ] **Step 3: Implement the store projection and bridge**

Fetch through `BeastDesktopBridge.fetchJson`, normalize only server-supplied rows, preserve explicit false/null state, and surface errors without fallback demo entries.

- [ ] **Step 4: Run smoke to verify GREEN**

Run: `node desktop-ide/scripts/smoke-desktop-ide.js`

Expected: PASS.

### Task 6: Systems Atlas master map

**Files:**
- Modify: `desktop-ide/renderer/js/pages/beast-atlas-page.js`
- Modify: `desktop-ide/renderer/css/beast-restored-pages-polish.css`
- Modify: `desktop-ide/scripts/smoke-desktop-ide.js`

**Interfaces:**
- Consumes: Task 2 `BeastStore.integrations` and `BeastIntegrationMap.refresh()`.
- Produces: grouped integration cards, status filters, source/claim inspector, and navigation to each capability's registered primary surface.

- [ ] **Step 1: Add failing Atlas contract assertions**

Assert the full integration map container, implemented/enabled/live labels, claim-boundary inspector, refresh action, and route navigation.

- [ ] **Step 2: Run smoke to verify RED**

Run: `node desktop-ide/scripts/smoke-desktop-ide.js`

Expected: FAIL because Atlas does not consume the integration contract.

- [ ] **Step 3: Implement the Atlas map**

Render domains from the server contract, keep disabled items visible, show evidence counts without secret paths, and open the existing mapped surface on operator action.

- [ ] **Step 4: Run smoke to verify GREEN**

Run: `node desktop-ide/scripts/smoke-desktop-ide.js`

Expected: PASS.

### Task 7: Domain-page integration rails

**Files:**
- Modify: `desktop-ide/renderer/js/pages/beast-agents-page.js`
- Modify: `desktop-ide/renderer/js/pages/beast-compute-fabric-page.js`
- Modify: `desktop-ide/renderer/js/pages/beast-crystallization-page.js`
- Modify: `desktop-ide/renderer/js/pages/beast-commons-page.js`
- Modify: `desktop-ide/renderer/js/pages/beast-tooling-page.js`
- Modify: `desktop-ide/renderer/css/beast-restored-pages-polish.css`
- Modify: `desktop-ide/scripts/smoke-desktop-ide.js`

**Interfaces:**
- Consumes: Task 2 `BeastIntegrationMap.mountSurface(root, route)`.
- Produces: compact live integration rails on the operational pages, each linked back to the full Atlas inspector.

- [ ] **Step 1: Add failing smoke assertions for all five surface rails**
- [ ] **Step 2: Run smoke and verify RED**
- [ ] **Step 3: Mount the shared rail on each page without duplicating catalog logic**
- [ ] **Step 4: Run smoke and verify GREEN**

### Task 8: Verification and documentation

**Files:**
- Modify: `desktop-ide/README.md`
- Modify: `docs/BEAST_IDE_VSCODE_PARITY.md`

**Interfaces:**
- Consumes: Tasks 1-7.
- Produces: operator documentation for the integration states and mapped surfaces.

- [ ] Run focused Python tests and route-registration tests.
- [ ] Run desktop smoke, live-page contract verification, and JavaScript syntax parsing.
- [ ] Run Ruff on new Python files and `git diff --check`.
- [ ] Run the repository's full pytest command and report any unrelated failures by name.
- [ ] Run one controlled Agent Coder proof and retain a redacted event line for compression, Vector RAG, memory hull/seal, crystal production/bus/family lookup, and swarm.
