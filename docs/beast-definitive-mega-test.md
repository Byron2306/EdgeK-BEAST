# BEAST Definitive Mega-Test

This design converts `/home/byron/Downloads/BEAST level test` into an executable
benchmark package. It is built to answer whether BEAST preserves quality while
displacing repeated cloud calls, and whether that displacement survives provider
changes, mutation, recovery, and natural agent workflows.

## Core Question

Does BEAST produce quality-preserving cloud-call displacement across real coding
work, repeated task families, multiple providers, and Compute Governor phases
1-7?

The primary metric is QPCCD: quality-preserving cloud-call displacement.

```text
QPCCD case =
  lane_c.verified_completion >= lane_b.verified_completion
  and lane_c.hidden_pass_rate >= lane_b.hidden_pass_rate
  and lane_c.cloud_calls < lane_b.cloud_calls

QPCCD rate =
  QPCCD cases / lane_c observations where lane_b.cloud_calls > 0
```

## Test Shape

The controlled core is exactly 450 lane-level observations:

```text
6 task families * 5 providers * 5 occurrence points * 3 lanes = 450
```

The extended package adds natural no-harness sessions, mutation/recovery trials,
cross-provider reuse trials, and durability retests. The target evidence package
should land above 500 total observations without blurring the 450-observation
controlled core.

## Lanes

Lane A is the raw provider baseline. It runs the provider in an isolated
disposable worktree with no BEAST input governance, no output governance, no
Compute Governor reuse, and no repair. It records raw response text, attempted
diffs, test results, tokens, latency, and failure bucket.

Lane B is BEAST without Compute Governor. It uses BEAST task envelopes, bounded
context, provider handoff, Action IR/schema validation, output repair, rollback,
hidden tests, and source-patching fitness scoring. It does not reuse
crystallized results.

Lane C is full BEAST with Compute Governor phases 1-7. It uses everything in
Lane B plus route calibration, closure capture, false-reuse guards, routing,
streaming/lifecycle evidence, and runtime reuse. Lane C is the only lane allowed
to convert a recurring task into a deterministic local path.

## Providers

The first controlled pass should use provider presets that already exist in
`benchmarks/beast_systems_benchmark.py`, with provider-specific models pinned in
the run manifest:

```text
nvidia_nim
gemini
groq
cerebras
cloudflare
```

These are the preferred first five because they are configured locally and have
documented zero-cost or free-tier access patterns suitable for bounded evals.
A second optional pass can add `openrouter/free`, `mistral`, `github_models`,
`llm7`, and `aion_labs` once presets and model pins are normalized.

Every run must record:

- provider preset
- base URL
- model id
- key environment variable name only
- account tier if known
- rate-limit headers when returned
- token and latency counters
- local rescue markers

## Task Families

The six controlled families map to current BEAST failure modes and existing
gauntlet fixtures:

| Family | Intent | Existing fixture anchor |
| --- | --- | --- |
| `schema_validation` | Validate structured output and fail closed on malformed action plans. | `output_governance_malformed_json`, `mcp_tool_schema_pinning` |
| `provider_alias_normalization` | Resolve provider/model aliases without mutating explicit overrides. | `deployment_route_resolution`, `provider_id_parser` |
| `patch_compilation` | Produce source patches that compile and pass visible tests. | `multi_file_hidden_decimal_fix`, `quality_cascade_language_matrix` |
| `syntax_check` | Catch language syntax errors before verification credit. | `patch_compilation`, `quality_matrix` derived variants |
| `route_diagnostics` | Separate route/network/auth failure from model capability. | `network_probe_failure_classification`, `route_diagnostics` |
| `secret_redaction` | Preserve useful evidence while excluding secrets/prompts/code paths. | `provider_config_secret_redaction`, `otel_attribute_secret_redaction` |

Each family gets one canonical task generator with five occurrence points:
`1`, `2`, `3`, `5`, and `10`. The generator emits equivalent-but-not-identical
instances at each occurrence so providers cannot simply memorize a literal
fixture.

## Occurrence Semantics

Occurrence 1 is cold start. No deterministic reuse is possible.

Occurrence 2 tests whether BEAST can recognize a repeated structure but should
still require enough evidence before crystallization.

Occurrence 3 is the earliest allowed crystallization point. A Lane C conversion
is valid only if the previous instances had passing visible and hidden tests,
stable Action IR, stable rollback, and no false-reuse warnings.

Occurrence 5 tests mature reuse. A valid Lane C result should use fewer provider
calls than Lane B while preserving hidden quality.

Occurrence 10 tests durability. A valid Lane C result should still avoid stale
reuse when the fixture mutates within the same family.

## Natural Before Synthetic

Mode A is natural no-harness capture. Cursor, Claude Code, or another coding
agent works actual backlog tasks while BEAST intercepts envelopes, provider
handoffs, output plans, verification, and Compute Governor receipts. Natural
sessions discover the recurring patterns and mutation types that should feed
the controlled generators.

Mode B is controlled ablation. It runs the 450-observation matrix against
frozen generators and pinned commits. Mode B is the only mode used for the main
QPCCD denominator.

Natural observations are reported separately and never mixed into controlled
completion rates.

## Runner Architecture

Add `benchmarks/beast_definitive_mega_test.py` as the top-level runner.

It should reuse:

- `LiveProvider` and `LIVE_PROVIDER_PRESETS`
- `SuiteTask` and `LaneResult`
- `run_systems_benchmark()` verification mechanics
- `live_provider_fitness()`
- `write_live_gauntlet_artifacts()`
- `SecretVault().load()`
- Compute Governor phase artifacts already emitted by phase 1-7 scripts

Recommended internal modules:

```text
benchmarks/mega_test_tasks.py
  task family generators and occurrence mutation schedule

benchmarks/mega_test_lanes.py
  lane A/B/C execution policy and lane-specific BEAST feature flags

benchmarks/mega_test_metrics.py
  QPCCD, crystallization, false reuse, durability, and provider fitness metrics

benchmarks/beast_definitive_mega_test.py
  CLI, orchestration, artifact packaging, manifest, and summary
```

## Data Model

Each lane observation is a JSONL record:

```json
{
  "run_id": "2026-06-20T000000Z",
  "commit": "git-sha",
  "mode": "controlled",
  "family": "schema_validation",
  "provider": "nvidia_nim",
  "model": "nvidia/nemotron-3-super-120b-a12b",
  "occurrence": 3,
  "lane": "lane_c_full_beast_compute_governor",
  "task_id": "schema_validation_o3_v1",
  "completed": true,
  "visible_passed": true,
  "hidden_passed": true,
  "cloud_calls": 0,
  "provider_prompt_tokens": 0,
  "provider_completion_tokens": 0,
  "latency_ms": 214.3,
  "cost_usd": null,
  "crystallized": true,
  "deterministic_reuse": true,
  "false_reuse_warning": false,
  "rollback_success": true,
  "rescued": false,
  "failure_bucket": null,
  "artifact_refs": {
    "patch": "patches/schema_validation_o3_lane_c.diff",
    "receipt": "compute_governor/schema_validation_o3.json",
    "raw_response": null
  }
}
```

Provider text, patches, rollback snapshots, and receipts are stored as separate
files referenced from JSONL. Secrets are never copied into records.

## Artifact Package

Each run writes:

```text
benchmarks/results/beast_definitive_mega_test_<stamp>/
  README.md
  run_manifest.json
  controlled_observations.jsonl
  natural_observations.jsonl
  qpc_cloud_call_displacement.json
  provider_fitness.json
  crystallization_events.jsonl
  false_reuse_audit.json
  mutation_recovery.json
  cross_provider_reuse.json
  cost_latency_summary.md
  failures_by_bucket.json
  raw_provider_responses/
  patches/
  rollback_snapshots/
  compute_governor_receipts/
  evidence_cards/
  integrity_manifest.json
```

The package is zipped after writing `integrity_manifest.json`.

## Metrics

Primary metrics:

- QPCCD rate
- verified completion by lane
- hidden pass rate by lane
- cloud calls per verified fix
- provider tokens per verified fix
- deterministic conversion rate
- crystallization occurrence distribution
- false reuse rate
- rollback success rate
- USD per verified fix when first-party cost evidence exists

Secondary metrics:

- clean provider completion
- BEAST-rescued completion
- schema validity rate
- patch apply rate
- syntax error rate
- out-of-scope edit rate
- timeout rate
- provider failure bucket distribution
- route confidence
- durability pass rate from occurrence 10 retests

## Acceptance Gates

The controlled run is valid only if:

- all 450 lane observations are present
- each observation has visible and hidden verification status
- each provider/model pair has a manifest entry
- raw provider responses are archived for Lane A and Lane B/C provider calls
- every source patch has a rollback snapshot
- every Lane C reuse has a Compute Governor receipt
- integrity manifest validates all artifact hashes
- secret scan passes for records and text artifacts

The headline BEAST claim is valid only if:

- Lane C QPCCD rate is reported over the explicit denominator
- Lane C hidden pass rate is not lower than Lane B for QPCCD cases
- false reuse rate is zero, or each false reuse is reported as a failure
- local rescue is separated from provider-clean completion
- natural no-harness outcomes are reported outside the controlled core

## CLI

Dry preflight:

```bash
python3 benchmarks/beast_definitive_mega_test.py \
  --mode controlled \
  --providers nvidia_nim,gemini,groq,cerebras,cloudflare \
  --dry-run \
  --output beast_definitive_mega_test_preflight
```

Controlled live run:

```bash
python3 benchmarks/beast_definitive_mega_test.py \
  --mode controlled \
  --providers nvidia_nim,gemini,groq,cerebras,cloudflare \
  --families schema_validation,provider_alias_normalization,patch_compilation,syntax_check,route_diagnostics,secret_redaction \
  --occurrences 1,2,3,5,10 \
  --lanes raw,beast_no_compute_governor,full_beast_compute_governor \
  --live \
  --timeout 240 \
  --max-tokens 1400 \
  --output beast_definitive_mega_test_live
```

Natural capture:

```bash
python3 benchmarks/beast_definitive_mega_test.py \
  --mode natural \
  --providers nvidia_nim,gemini,groq,cerebras,cloudflare \
  --watch .beast/intercepts \
  --output beast_definitive_mega_test_natural
```

Mutation/recovery extension:

```bash
python3 benchmarks/beast_definitive_mega_test.py \
  --mode mutation-recovery \
  --from-controlled benchmarks/results/beast_definitive_mega_test_live \
  --output beast_definitive_mega_test_mutation_recovery
```

## Implementation Steps

1. Add `mega_test_tasks.py` with deterministic generators for the six families.
2. Add lane policy wrappers that map Lane A/B/C to existing BEAST feature flags.
3. Add a dry-run planner that emits the 450-row matrix before any provider call.
4. Add controlled execution with randomized lane order per provider/family point.
5. Add QPCCD and crystallization metrics.
6. Add artifact packaging and integrity hashing.
7. Add tests for matrix cardinality, QPCCD math, secret redaction, and Lane C
   reuse gating.
8. Run one provider as a smoke pass, then the full five-provider matrix.

## First Smoke Pass

Use NVIDIA NIM Nemotron Super 120 first because the 24-task gauntlet has already
validated the endpoint and revealed a useful baseline: BEAST can complete tasks
with rescue, but provider-clean source patching fitness is low. That makes it a
good stress case for separating model fitness from system fitness.

Smoke command:

```bash
python3 benchmarks/beast_definitive_mega_test.py \
  --mode controlled \
  --providers nvidia_nim \
  --occurrences 1,2,3 \
  --live \
  --output beast_definitive_mega_test_nvidia_smoke
```

The smoke pass should produce 54 lane observations:

```text
6 families * 1 provider * 3 occurrence points * 3 lanes = 54
```

Only after that passes should the 450-observation run be started.
