# BEAST System Improvement Roadmap

**Date:** 2026-06-20  
**Scope:** Post-Phase-7 implementation review  
**Status:** All 7 phase surfaces exist; safety-critical paths are tested, but production-hardening remains in progress

---

## Executive Summary

BEAST has evolved from a conceptual 7-phase architecture into a **working, CPU-first implementation** with:
- Real Ollama inference (not simulation)
- Real KV cache movement to disk (CPU↔STORAGE)
- File-coordinated scheduler prototype with capability routing and node degradation
- Real ablation harness executing pytest
- Runnable forge node entry point

The system is now **credible for a controlled CPU-first pilot** on a single host or trusted shared filesystem. It is not yet production-ready for unattended multi-node deployment. The remaining work includes repo-wide dependency migration, scheduler durability/concurrency, fault injection, packaging, and operational deployment evidence.

Validation completed during the Step 3 audit:

- Phase 2 enforcement is proof-bound and fails closed on empty, malformed, low-confidence, stale, mismatched, or absent proofs.
- The full CPU pipeline now asserts real scheduler completion, pytest ablation, crystallization state, KV disk artifacts, semantic-credit persistence, and ledger activity.
- Dependency/test fingerprint drift and deletion trigger rebuilds.
- Ablation workers execute with bounded real concurrency; missing security/scope tests fail closed.
- Failed Ollama calls earn no semantic credit and displace no tokens.
- Configuration typing, circuit-breaker behavior, scheduler capability routing, wrong-node rejection, and node degradation have deterministic tests.

---

## 1. Critical / High-Impact Improvements

### 1.1 Centralized Configuration System — **FOUNDATION COMPLETE; MIGRATION OPEN**
**Problem:** Hardcoded paths, URLs, thresholds scattered across 70+ modules.
```python
# Current (scattered)
ollama_url = "http://localhost:11434"
db_path = Path(__file__).resolve().parents[2] / "data" / "compute_ledger.db"
max_memory = 8 * 1024 * 1024 * 1024
```

**Solution:** Single `beast_config.py` + env var overrides.
```python
from app.kernel import beast_config as cfg
cfg.OLLAMA_URL
cfg.DATA_DIR / "kv_cache"
cfg.KV_MAX_MEMORY_BYTES
```
Typed environment parsing and non-duplicated `BEAST_*` keys are tested. Several older modules still construct paths and URLs directly and must migrate before this can be called complete.

**Files:** `app/kernel/beast_config.py`, `tests/unit/test_step3_operations.py`

### 1.2 Structured Logging + Observability — **FOUNDATION COMPLETE; ADOPTION OPEN**
**Problem:** `print()` statements and minimal error context in new Phase 7 modules.

**Solution:**
- JSON formatter with `correlation_id` context variable
- `get_correlation_id()` / `set_correlation_id()` helpers
- Auto-configures on import
The formatter and correlation context exist, but new and legacy modules still contain `print()` calls and unstructured exception paths. Repo-wide adoption remains open.

**Files:** `app/kernel/beast_logging.py`

### 1.3 Error Taxonomy + Circuit Breakers — **PARTIAL**
**Problem:** Some modules swallow exceptions or retry forever.

**Solution:**
- Typed hierarchy: `BeastError`, `OllamaUnavailable`, `LedgerCorrupt`, `AblationTimeout`, `KVTransportError`, `ForgeNodeError`, `SchedulerError`, `ConfigurationError`
- `CircuitBreaker` with threshold + timeout
The taxonomy exists and local Ollama forge inference now uses the circuit breaker. Scheduler, storage, ablation, and connector boundaries still need consistent typed-error adoption.

**Files:** `app/kernel/beast_errors.py`, `app/kernel/compute_forge.py`

### ~~1.4 Integration Test Harness~~ ✅ **COMPLETE**
**Problem:** 66 unit tests, but no end-to-end test of:
```
Forge Node → Scheduler → Ablation → Crystallization → KV Transport → Ledger
```

**Solution:** `tests/integration/test_full_pipeline.py` now verifies each CPU stage and its persisted evidence. It no longer treats “returned an object” as pipeline success.
**Files:** `tests/integration/test_full_pipeline.py`

---

## 2. Efficiency & Performance

### ~~2.1 Faster JSON (orjson)~~ ✅ **COMPLETE**
**Problem:** 50+ `json.dumps/loads` per work cycle in scheduler + forge.

**Solution:** `beast_json.py` with `orjson` fast path + stdlib fallback.
**Files:** `app/kernel/beast_json.py`

### ~~2.2 Context Caching in OllamaKVManager~~ ✅ **COMPLETE**
**Problem:** Every `get_or_create_context` may re-run the prefix prompt.

**Solution:** `OllamaContextCache` — LRU cache (size 50) keyed by `(model, prompt_prefix_hash, system_prompt_hash)`.
**Files:** `app/kernel/ollama_context_cache.py`

### ~~2.3 Batch Ablation Execution~~ ✅ **COMPLETE**
**Problem:** `run_batch` runs pytest N times sequentially.

**Solution:** `parallel` now uses bounded concurrent workers around independent pytest subprocesses. Result and crystallization writes are synchronized; concurrency is tested directly.
**Files:** `app/kernel/ablation_harness.py`

### ~~2.4 Incremental Fingerprinting~~ ✅ **COMPLETE**
**Problem:** `watch_repo` rebuilds entire fingerprint every cycle.

**Solution:** `incremental_fingerprint.py` uses working-tree diff plus mtimes across targets, dependencies, and tests. Dependency changes, test changes, and deletions are covered.
**Files:** `app/kernel/incremental_fingerprint.py`

---

## 3. Architecture & Maintainability

### 3.1 Canonical Module Facades (Completed; Backend Migration Open)
- `deterministic.py`, `ollama.py`, and `storage.py` are importable canonical façades.
- Existing implementation modules remain compatibility backends; they have not been physically merged or removed.
- New code should use the canonical façades while legacy imports are migrated incrementally.

### 3.2 Dependency Injection Container (Container Complete; Adoption Open)
- Implemented an importable frozen `BeastContext` dataclass.
- Added runtime structural validation against the real CPU components.
- Direct dependency creation remains in many modules and has not yet been replaced repo-wide.
- Example usage:
  ```python
  context = BeastContext(
      storage=kv_transport,
      scheduler=scheduler,
      ablation_runner=ablation_harness,
      credit_store=durable_storage,
  )
  context.validate()
  module = MyModule(context=context)
  ```

### 3.3 Protocol / Interface Definitions (Completed)
- Defined `Protocol` classes for:
  - `KVTransport`
  - `ForgeScheduler`
  - `AblationRunner`
  - `CreditStore`
- Protocol signatures now match the actual scheduler, ablation, KV, and credit-store surfaces.
- Real CPU components pass runtime structural validation.

### 3.4 Documentation (Updated)
- Added enforcement boundary documentation under Phase 2A
- Added test case requirements for proof validation
- Updated runbook section with Phase 2A/2B/2C rollout plan

### Phase 2: Enforcement Guard Implementation

Implement strict deterministic-displacement proof validation in `ComputeGovernor` using the `phase2_enforce` guard. Key components:
- Proof enforceability checks before capability displacement
- Cloud fallback for invalid proofs
- Test coverage for edge cases (empty proofs, mixed validity)

Status: Implemented with real governor tests in `tests/unit/test_compute_governor_phase2.py`. Bare metadata declarations cannot enforce; only complete proofs tied to detected allowlisted candidates can select deterministic execution.

---

## 4. Testing & Quality

### 4.1 Property-Based Testing (Hypothesis)
**High value targets:**
- `ComputeGovernor.evaluate()` — generate random plans, assert invariants
- `CrossEngineKVCacheTransport.lookup()` — generate (model, prefix, engine) tuples, verify only exact matches succeed
- `AblationHarness` — generate success rate distributions, assert promotion logic

### 4.2 Chaos / Fault Injection
- Kill Ollama mid-generation
- Corrupt a ledger JSON file
- Simulate node heartbeat timeout
- Measure: does the system degrade gracefully? (never silent suppression)

Completed deterministic fault cases:
- Ollama failure earns no credit and trips the circuit breaker at threshold.
- Scheduler rejects wrong-node completion and degrades a node after repeated failures.
- Missing security/scope tests prevent ablation promotion.

Still open: process termination during writes, corrupt persisted scheduler/credit state, disk exhaustion, and concurrent multi-process claims.

### 4.3 Mutation Testing
Run `mutmut` or `cosmic-ray` on core modules (`compute_governor.py`, `capability_crystallization.py`) to verify test quality.

### 4.4 Performance Benchmarks
Add `tests/bench/`:
- `test_forge_cycle_latency`
- `test_ablation_throughput`
- `test_kv_cache_lookup_p99`

---

## 5. Deployment & Operations

### 5.1 systemd / launchd Unit Files
Provide example units:
```ini
# /etc/systemd/system/beast-forge@.service
[Unit]
Description=BEAST Forge Node %i
After=network.target ollama.service

[Service]
Type=simple
User=beast
Environment=BEAST_OLLAMA_MODEL=llama3.2:3b
ExecStart=/opt/beast/venv/bin/python /opt/beast/scripts/run_forge_node.py --node-id %i
Restart=always
```

### 5.2 Health Endpoints
Expose:
- `GET /edgek/health` → `{status, ollama_ok, ledger_ok, kv_ok}`
- `GET /edgek/metrics` → Prometheus text format (node credits, ablation success rate, etc.)

### 5.3 Packaging
- `pyproject.toml` with optional deps: `[ollama]`, `[gpu]`, `[distributed]`
- Docker image (CPU-only) for easy deployment on edge devices

---

## 6. Strategic / Long-Term

### 6.1 GPU Path (Optional)
When a GPU host is available:
- Detect CUDA/ROCm at runtime
- Use `cupy` or `torch` for real KV tensor movement
- Keep CPU path as fallback (current code already does this pattern)

### 6.2 Real Network Transport
Replace file-based scheduler coordination with:
- NATS / Redis PubSub for work assignment
- S3 / MinIO for KV cache blob storage
- mTLS between nodes

### 6.3 Formal Verification (Stretch)
For the sacred invariants ("false suppression rate must be zero"), consider TLA+ or Lean specs of the core state machine.

---

## 7. Quick Wins (1-3 days each)

| Win | Effort | Impact |
|-----|--------|--------|
| Migrate remaining modules to `beast_config.py` | 1 day | High |
| Replace `json` with `orjson` | 2 hours | Medium |
| Add structlog | 1 day | High |
| ~~Write integration test pipeline~~ | Complete | High |
| Create systemd unit template | 2 hours | Medium |
| Document "add new transform" flow | 1 day | Medium |

---

## 8. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Ollama version drift breaks context API | Medium | High | Pin Ollama version in docs + CI |
| File-based scheduler races on NFS | Low | Medium | Document "single machine or use Redis" |
| Large ablation runs exhaust disk | Medium | Medium | Add size guard in harness |
| Credential leakage in forge manifests | Low | High | Never log full manifests; redact secrets |

---

## Conclusion

BEAST now has substantive CPU-first implementations across all seven phase surfaces and materially stronger proof-bound safety tests. It is suitable for a controlled single-host pilot, but production readiness would be an overclaim until scheduler concurrency, crash recovery, deployment packaging, and sustained operational evidence are complete.

**Recommended next milestone:** "Single-Host Soak Pilot" — package one forge runner, execute repeated real ablations under disk/network/Ollama faults, and publish crash-recovery plus non-counterfactual savings evidence. Advance to three edge devices only after that gate passes.

**After that:** GPU path + distributed scheduler v2 (NATS/Redis) would push the system to 9.0+.

---

*Originally generated by GitHub Copilot; corrected through implementation-level review and deterministic validation.*
