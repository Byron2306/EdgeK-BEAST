# BEAST Mammoth Layers Gauntlet

Date: 2026-06-28

Primary test file: `tests/test_mammoth_beast_layers_gauntlet.py`

## Purpose

This gauntlet verifies that the new BEAST production layers are not merely importable modules or TUI labels. It exercises local cryptographic trust, editable sealed memory, identity-gated policy, crystal reuse decisions, public integration export payloads, gateway endpoints, inference fabric registration, and every TUI subpage render.

## Coverage

| Area | What the gauntlet checks |
| --- | --- |
| Residue Seal | Signs canonical payloads, verifies purpose-bound signatures, rejects tampered payloads. |
| Memory Hull | Writes Markdown plus signed sidecar, verifies inventory, searches sealed residue. |
| Agent Passport | Allows memory append, denies unapproved cloud call, allows quality-cascade-approved governor escalation. |
| Crystal Reuse Gateway | Produces provider fallback, records verified provider response, reuses crystallized compute, registers KV block, exports integration bundle. |
| Thin Integration Harness | Exercises AgentPassport authorization, crystal reuse decisioning, provider verification, final residue seal, Memory Hull write, EnterpriseManager trace/budget recording, and readiness gate receipts. |
| Integrations | Confirms LMCache, GPTCache, LiteLLM, OpenLLMetry, Langfuse, TensorZero, Promptfoo payloads are present. |
| Inference Fabric | Confirms crystal reuse and public cache/telemetry/eval backends are advertised. |
| FastAPI Gateway | Checks `/health`, `/edgek/compute`, `/edgek/inference-engines`, `/edgek/crystal-compute`, `/edgek/kv-cache/state`, `/edgek/memory-security`, `/edgek/crystal-reuse`, `/edgek/crystal-reuse/integrations`, `/edgek/crystal-reuse/decide`, `/edgek/crystal-reuse/record`, `/edgek/crystal-reuse/export`, `/edgek/crystal-reuse/prefill`, and `/edgek/crystal-reuse/kv-block`. |
| TUI | Renders all fourteen pages and asserts the new Intelligence, Deployment, and Diagnostics layer panels appear. |

## Run

```bash
python3 -m pytest tests/test_mammoth_beast_layers_gauntlet.py -q
```

Focused run with the prior layer suites:

```bash
python3 -m pytest \
  tests/test_mammoth_beast_layers_gauntlet.py \
  tests/test_thin_integration_harness.py \
  tests/test_crystal_reuse_gateway.py \
  tests/test_memory_hull_residue_passport.py \
  tests/test_gateway.py::test_crystal_reuse_gateway_endpoints \
  tests/test_tui_intelligence.py::test_intelligence_summary_and_page_show_crystal_reuse_and_memory_security \
  -q
```

## Claim Boundary

The gauntlet is deterministic and local. It proves BEAST's contracts, endpoints, render paths, and export envelopes. It does not prove that a deployed LMCache/GPTCache/Langfuse/TensorZero/Promptfoo service accepted the payload, nor that cross-engine GPU KV restoration is safe in production. Those require explicit live probes and engine-specific restore correctness tests.
