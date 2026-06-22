"""Build the provenance-preserving master BEAST mega-test evidence bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.secret_vault import SecretVault
from benchmarks.package_xai_omni_evidence import scan_secrets


RESULTS = ROOT / "benchmarks" / "results"
RELEASE_NAME = "BEAST Definitive Mega-Test Master Evidence"
RELEASE_VERSION = "0.1"
DEFAULT_OUTPUT = "beast_definitive_mega_test_master_evidence_v0_1"

MEGA_SOURCES = [
    "beast_definitive_mega_test_cross_provider_nvidia_groq_scout",
    "beast_definitive_mega_test_cross_provider_nvidia_mistral",
    "beast_definitive_mega_test_cross_provider_nvidia_mistral_cohere_all_families",
    "beast_definitive_mega_test_dry_run",
    "beast_definitive_mega_test_first_live_routes_o1_all_families_live",
    "beast_definitive_mega_test_first_live_routes_o1_all_families_plan",
    "beast_definitive_mega_test_first_live_routes_o1_schema_batch0",
    "beast_definitive_mega_test_nvidia_mutation_o10",
    "beast_definitive_mega_test_nvidia_o1_batch0",
    "beast_definitive_mega_test_nvidia_o1_o2_o3_o5",
    "beast_definitive_mega_test_nvidia_smoke",
]

SUPPORTING_GAUNTLETS = [
    "beast_nim_first_provider_family_anchor_o1_full_gauntlet",
    "beast_mistral_first_provider_family_anchor_o1_full_gauntlet",
    "beast_cohere_first_provider_family_anchor_o1_full_gauntlet",
    "beast_groq_first_provider_family_anchor_o1_full_gauntlet",
    "beast_first_live_routes_schema_alias_secret_3task_gauntlet",
    "beast_first_real_schema_live_reachable_routes_gauntlet",
]

CANONICAL_ANALYSIS_RUNS = [
    "beast_definitive_mega_test_first_live_routes_o1_all_families_live",
    "beast_definitive_mega_test_nvidia_o1_o2_o3_o5",
    "beast_definitive_mega_test_nvidia_mutation_o10",
    "beast_definitive_mega_test_cross_provider_nvidia_mistral_cohere_all_families",
    "beast_definitive_mega_test_cross_provider_nvidia_groq_scout",
]

EVIDENCE_KINDS = [
    "evidence_cards",
    "patches",
    "raw_provider_responses",
    "rollback_snapshots",
    "compute_governor_receipts",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def annotated_rows(source: str, filename: str) -> list[dict[str, Any]]:
    rows = read_jsonl(RESULTS / source / filename)
    return [dict(row) | {"_source_bundle": source, "_source_path": filename} for row in rows]


def copy_source(source: str, destination: Path) -> None:
    origin = RESULTS / source
    if not origin.is_dir():
        raise FileNotFoundError(f"Required evidence source is missing: {origin}")
    shutil.copytree(origin, destination / source)


def copy_supporting_reports(destination: Path) -> list[dict[str, Any]]:
    patterns = [
        "beast_*_first_provider_family_anchor_o1_full.json",
        "beast_*_first_provider_family_anchor_o1_full.md",
        "beast_first_live_routes*.json",
        "beast_first_live_routes*.md",
        "beast_first_real_schema*.json",
        "beast_first_real_schema*.md",
    ]
    copied = []
    destination.mkdir(parents=True, exist_ok=True)
    for pattern in patterns:
        for source in sorted(RESULTS.glob(pattern)):
            target = destination / source.name
            if target.exists():
                continue
            shutil.copy2(source, target)
            copied.append({"path": source.name, "bytes": source.stat().st_size, "sha256": sha256(source)})
    return copied


def collate_evidence(source_names: list[str], output: Path) -> tuple[list[dict[str, Any]], dict[str, int]]:
    index = []
    counts: Counter[str] = Counter()
    for source_name in source_names:
        source = RESULTS / source_name
        for kind in EVIDENCE_KINDS:
            source_kind = source / kind
            if not source_kind.is_dir():
                continue
            for item in sorted(source_kind.rglob("*")):
                if not item.is_file():
                    continue
                relative = item.relative_to(source_kind)
                target = output / "evidence" / kind / source_name / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target)
                record = {
                    "kind": kind,
                    "source_bundle": source_name,
                    "source_path": str(item.relative_to(RESULTS)),
                    "master_path": str(target.relative_to(output)),
                    "bytes": item.stat().st_size,
                    "sha256": sha256(item),
                }
                index.append(record)
                counts[kind] += 1
    write_jsonl(output / "evidence" / "evidence_index.jsonl", index)
    return index, dict(counts)


def collate_structured(output: Path) -> dict[str, int]:
    all_rows = []
    canonical_rows = []
    natural_rows = []
    crystallization = []
    mutation = []
    ladder = []
    cross_provider = []
    provider_fitness = {}
    for source in MEGA_SOURCES:
        all_rows.extend(annotated_rows(source, "controlled_observations.jsonl"))
        natural_rows.extend(annotated_rows(source, "natural_observations.jsonl"))
        crystallization.extend(annotated_rows(source, "crystallization_events.jsonl"))
        if source in CANONICAL_ANALYSIS_RUNS:
            canonical_rows.extend(annotated_rows(source, "controlled_observations.jsonl"))
        for filename, destination in [
            ("mutation_recovery.json", mutation),
            ("mutation_ladder.json", ladder),
            ("cross_provider_reuse.json", cross_provider),
        ]:
            payload = read_json(RESULTS / source / filename, {}) or {}
            destination.extend(
                dict(case) | {"_source_bundle": source, "_source_path": filename}
                for case in payload.get("cases", [])
            )
        fitness = read_json(RESULTS / source / "provider_fitness.json", {}) or {}
        if fitness:
            provider_fitness[source] = fitness
    write_jsonl(output / "collated" / "all_controlled_observations.jsonl", all_rows)
    write_jsonl(output / "collated" / "canonical_analysis_observations.jsonl", canonical_rows)
    write_jsonl(output / "collated" / "natural_observations.jsonl", natural_rows)
    write_jsonl(output / "collated" / "crystallization_events.jsonl", crystallization)
    write_jsonl(output / "collated" / "mutation_recovery_cases.jsonl", mutation)
    write_jsonl(output / "collated" / "mutation_ladder_cases.jsonl", ladder)
    write_jsonl(output / "collated" / "cross_provider_reuse_cases.jsonl", cross_provider)
    write_json(output / "collated" / "provider_fitness_by_source.json", provider_fitness)
    return {
        "all_controlled_rows": len(all_rows),
        "canonical_analysis_rows": len(canonical_rows),
        "natural_rows": len(natural_rows),
        "crystallization_events": len(crystallization),
        "mutation_recovery_cases": len(mutation),
        "mutation_ladder_cases": len(ladder),
        "cross_provider_cases": len(cross_provider),
    }


def source_inventory(source_names: list[str]) -> list[dict[str, Any]]:
    inventory = []
    for source_name in source_names:
        source = RESULTS / source_name
        counts = {}
        for kind in EVIDENCE_KINDS:
            folder = source / kind
            counts[kind] = sum(item.is_file() for item in folder.rglob("*")) if folder.is_dir() else 0
        manifest = read_json(source / "run_manifest.json", {}) or {}
        integrity = read_json(source / "integrity_manifest.json", {}) or {}
        inventory.append({
            "source_bundle": source_name,
            "source_type": "definitive_mega" if source_name in MEGA_SOURCES else "supporting_gauntlet",
            "file_count": sum(item.is_file() for item in source.rglob("*")),
            "bytes": sum(item.stat().st_size for item in source.rglob("*") if item.is_file()),
            "controlled_rows": len(read_jsonl(source / "controlled_observations.jsonl")),
            "mode": manifest.get("mode"),
            "live": manifest.get("live"),
            "original_integrity_hash": integrity.get("manifest_hash"),
            "evidence_counts": counts,
        })
    return inventory


def primary_metrics() -> dict[str, Any]:
    first = read_jsonl(RESULTS / CANONICAL_ANALYSIS_RUNS[0] / "controlled_observations.jsonl")
    mature = read_jsonl(RESULTS / CANONICAL_ANALYSIS_RUNS[1] / "controlled_observations.jsonl")
    mutation = read_json(RESULTS / CANONICAL_ANALYSIS_RUNS[2] / "mutation_recovery.json", {}) or {}
    cross = read_json(RESULTS / CANONICAL_ANALYSIS_RUNS[3] / "cross_provider_reuse.json", {}) or {}
    scout = read_json(RESULTS / CANONICAL_ANALYSIS_RUNS[4] / "cross_provider_reuse.json", {}) or {}
    mature_qpccd = read_json(RESULTS / CANONICAL_ANALYSIS_RUNS[1] / "qpc_cloud_call_displacement.json", {}) or {}
    first_by_lane = defaultdict(Counter)
    for row in first:
        first_by_lane[str(row.get("lane"))]["rows"] += 1
        first_by_lane[str(row.get("lane"))]["completed"] += bool(row.get("completed"))
        first_by_lane[str(row.get("lane"))]["cloud_calls"] += int(row.get("cloud_calls") or 0)
    mature_lane_c = [row for row in mature if row.get("lane") == "full_beast_compute_governor"]
    receipts = list((RESULTS / CANONICAL_ANALYSIS_RUNS[3] / "compute_governor_receipts").glob("mega_cg_*.json"))
    scout_receipts = list((RESULTS / CANONICAL_ANALYSIS_RUNS[4] / "compute_governor_receipts").glob("mega_cg_*.json"))
    avoided = sum(int((read_json(path, {}) or {}).get("avoided_tokens_estimate") or 0) for path in receipts)
    scout_avoided = sum(int((read_json(path, {}) or {}).get("avoided_tokens_estimate") or 0) for path in scout_receipts)
    canonical_rows = []
    for source in CANONICAL_ANALYSIS_RUNS:
        canonical_rows.extend(read_jsonl(RESULTS / source / "controlled_observations.jsonl"))
    observed_cells = {
        (str(row.get("provider")), str(row.get("family")), int(row.get("occurrence") or 0), str(row.get("lane")))
        for row in canonical_rows
    }
    return {
        "designed_controlled_matrix_rows": 450,
        "controlled_design_cells_observed": len(observed_cells),
        "controlled_design_cells_remaining": 450 - len(observed_cells),
        "controlled_design_progress_rate": round(len(observed_cells) / 450, 6),
        "first_live_rows": len(first),
        "first_live_by_lane": {key: dict(value) for key, value in first_by_lane.items()},
        "mature_nvidia_rows": len(mature),
        "mature_lane_c_rows": len(mature_lane_c),
        "mature_lane_c_completed": sum(bool(row.get("completed")) for row in mature_lane_c),
        "mature_deterministic_reuse": sum(bool(row.get("deterministic_reuse")) for row in mature_lane_c),
        "mature_lane_c_cloud_calls": sum(int(row.get("cloud_calls") or 0) for row in mature_lane_c),
        "mature_qpccd": mature_qpccd,
        "mutation_case_count": mutation.get("case_count", 0),
        "mutation_reuse_blocked": mutation.get("reuse_blocked_count", 0),
        "mutation_recovered": mutation.get("recovered_count", 0),
        "mutation_false_reuse": mutation.get("false_reuse_count", 0),
        "primary_cross_provider_cases": cross.get("case_count", 0),
        "primary_cross_provider_false_reuse": cross.get("false_reuse_count", 0),
        "groq_scout_cases": scout.get("case_count", 0),
        "groq_scout_false_reuse": scout.get("false_reuse_count", 0),
        "primary_avoided_tokens_estimate": avoided,
        "groq_scout_avoided_tokens_estimate": scout_avoided,
    }


def provider_anchor_metrics() -> list[dict[str, Any]]:
    rows = []
    for label, preset in [("cohere", "cohere"), ("mistral", "mistral"), ("nim", "nvidia_nim"), ("groq", "groq")]:
        payload = read_json(RESULTS / f"beast_{label}_first_provider_family_anchor_o1_full.json", {}) or {}
        summary = (payload.get("live_summary") or {}).get(preset, {})
        fitness = (payload.get("live_provider_fitness") or {}).get(preset, {})
        rows.append({
            "provider": preset,
            "rows": int(fitness.get("sample_size") or 0),
            "completed": int(summary.get("completed") or 0),
            "clean_completed": int(summary.get("clean_completed") or 0),
            "rescued_completed": int(summary.get("rescued_completed") or 0),
            "fitness_score": fitness.get("score"),
            "json_validity_rate": (fitness.get("metrics") or {}).get("json_validity_rate"),
            "schema_valid_rate": (fitness.get("metrics") or {}).get("schema_valid_rate"),
            "patch_apply_rate": (fitness.get("metrics") or {}).get("patch_apply_rate"),
            "recommended_role": fitness.get("recommended_role"),
        })
    return rows


def academic_report(metrics: dict[str, Any], anchors: list[dict[str, Any]], coverage: dict[str, Any]) -> str:
    anchor_lines = "\n".join(
        f"| {row['provider']} | {row['completed']}/{row['rows']} | {row['clean_completed']} | "
        f"{row['rescued_completed']} | {row['fitness_score']} | {row['json_validity_rate']} | "
        f"{row['schema_valid_rate']} | {row['recommended_role']} |"
        for row in sorted(anchors, key=lambda item: float(item.get("fitness_score") or 0), reverse=True)
    )
    qpc = metrics["mature_qpccd"]
    return f"""# Academic Assessment of {RELEASE_NAME} v{RELEASE_VERSION}

Generated: `{utc_now()}`

## Abstract

This evidence program evaluates whether BEAST can transform repeated provider-assisted coding work into verified local inference capabilities while preserving task behavior. The strongest observed result is within-provider deterministic reuse on NVIDIA NIM: Lane C completed all 24 mature observations, displaced the cloud call in 12 occurrence-3/5 cases, and achieved QPCCD `{qpc.get('numerator')}/{qpc.get('denominator')} = {qpc.get('rate')}`. A second result demonstrates fingerprint-matched transfer from NVIDIA NIM to Mistral and Cohere across all six task families (`12/12` cases), plus a six-family Groq scout. A live occurrence-10 experiment blocked stale reuse in `6/6` mutation cases and recovered all six through fresh verification.

These results support a bounded claim: BEAST has demonstrated repository-bound deterministic reuse, stale-fingerprint blocking, and provider-independent consumption of an already verified local capability in this harness. They do not yet establish the complete 450-observation design, natural organic crystallization, raw-response-level reproducibility, or broad statistical generalization.

## Research Questions

1. Does governance improve verified completion relative to raw or schema-only provider output?
2. Can repeated verified work crystallize into a zero-cloud-call local path?
3. Does repository or contract drift make reuse unavailable before execution?
4. Can a capability verified under one provider be consumed under another provider identity without another provider call?
5. Are the resulting claims supported by inspectable evidence and explicit limitations?

## Experimental Structure

The intended controlled core is `6 families x 5 providers x 5 occurrence points x 3 lanes = 450` observations. The evidence is staggered rather than one monolithic independent run. Canonical analysis uses five runs containing `{coverage['structured']['canonical_analysis_rows']}` records, but those records are not an IID sample and some task/provider contexts recur across stages. Therefore, this report presents exact descriptive counts and does not attach inferential p-values or confidence intervals.

The three lanes are raw provider output, BEAST schema/governance without Compute Governor reuse, and full BEAST with Compute Governor. Occurrences 1 and 2 establish history; occurrences 3 and 5 permit reuse; occurrence 10 tests drift handling.

## Provider Anchor Results

| Provider | Completed | Clean | Rescued | Fitness | JSON valid | Schema valid | Recommended role |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
{anchor_lines}

Cohere leads this bounded 18-row anchor comparison because it produced four clean completions. Mistral is structurally stronger than NVIDIA NIM on JSON/schema validity but produced fewer clean completions than Cohere. NVIDIA NIM and Groq depended entirely on BEAST rescue in these anchors. These scores are route-role evidence, not universal model rankings.

## First-Live Five-Provider Pass

The occurrence-1 run contains `{metrics['first_live_rows']}` observations. Full BEAST recorded `30/30` completed, raw recorded `1/30`, and schema-only recorded `0/30`. This dramatic difference shows the harness's governance/rescue path dominates direct provider output on these fixtures. It should not be interpreted as a pure model-quality effect because Lane C includes repair and verification machinery absent from Lane A.

An important anomaly remains: Gemini occurrence-1 Lane C records six completions with zero cloud calls but no deterministic-reuse marker or Compute Governor receipt. Those six QPCCD positives are retained for provenance but should be excluded from the strongest displacement claim until their execution provenance is reconstructed.

## Mature Within-Provider Reuse

The NVIDIA maturity run contains `{metrics['mature_nvidia_rows']}` observations across occurrences 1, 2, 3, and 5. Lane C completed `{metrics['mature_lane_c_completed']}/{metrics['mature_lane_c_rows']}` and made `{metrics['mature_lane_c_cloud_calls']}` calls. Exactly `{metrics['mature_deterministic_reuse']}` Lane C observations were deterministic zero-call reuses. QPCCD was `{qpc.get('numerator')}/{qpc.get('denominator')} = {qpc.get('rate')}`.

The principal interpretation is temporal: calls occur while evidence is immature (occurrences 1 and 2), then disappear after the capability reaches eligibility (occurrences 3 and 5). The result is internally consistent across all six task families.

## Mutation Safety and Recovery

At occurrence 10, material drift blocked reuse in `{metrics['mutation_reuse_blocked']}/{metrics['mutation_case_count']}` cases, triggered live revalidation, recovered `{metrics['mutation_recovered']}/{metrics['mutation_case_count']}`, and recorded `{metrics['mutation_false_reuse']}` false reuses. Fingerprints include real target, test, semantic, symbol, tool-schema, and policy hashes.

The A-D ladder contains 24 policy decisions: A cosmetic drift remains active; B semantic-adjacent drift enters shadow revalidation; C tool-schema/structural drift enters shadow revalidation; D breaking target/test drift is demoted and requires cloud or human escalation. The ladder is policy-decision evidence. It is not equivalent to 24 new live mutation executions. The six occurrence-10 cases are the live recovery evidence.

## Cross-Provider Reuse

The primary transfer run records `{metrics['primary_cross_provider_cases']}/12` successful cases from NVIDIA NIM to Mistral and Cohere, with zero target-provider execution requests, zero cloud calls, fingerprint matches, preserved visible/hidden behavior, and `{metrics['primary_cross_provider_false_reuse']}` incorrect reuses. Estimated avoided tokens total `{metrics['primary_avoided_tokens_estimate']}`. The Groq scout adds `{metrics['groq_scout_cases']}/6` cases and `{metrics['groq_scout_avoided_tokens_estimate']}` estimated avoided tokens.

This proves provider-independent *consumption* of the stored capability under the harness. It does not compare fresh Mistral/Cohere/Groq generation against NVIDIA output because target providers were intentionally not called. The causal object is the repository-bound capability fingerprint, not model interchangeability.

## Evidence Completeness

The master contains `{coverage['evidence_counts'].get('evidence_cards', 0)}` evidence cards, `{coverage['evidence_counts'].get('patches', 0)}` patch files, `{coverage['evidence_counts'].get('rollback_snapshots', 0)}` rollback snapshots, and `{coverage['evidence_counts'].get('compute_governor_receipts', 0)}` receipt/credit files. Complete source directories are preserved under `source_runs/`, while normalized records are under `collated/`.

Raw provider response bodies are absent from the selected source artifacts. Evidence cards preserve response length, validation outcomes, token usage, latency, failure reasons, and compiled patches when available, but not the original response text. This is the most important artifact-level limitation for independent forensic reproduction.

Natural observations remain empty. Therefore the study has not yet demonstrated that capabilities crystallize organically in an uncontrolled coding workflow.

## Threats to Validity

- **Construct validity:** `completed` depends on the benchmark verifier and fixture tests; it is not a general software-correctness guarantee.
- **Internal validity:** Lane C combines multiple interventions, so the first-live completion gap cannot be attributed solely to Compute Governor.
- **External validity:** Six synthetic task families and a small provider set do not represent all repositories, languages, or provider behaviors.
- **Statistical validity:** Runs are staged, repeated, and non-independent. Descriptive rates are appropriate; significance claims are not.
- **Artifact validity:** Raw response bodies were not retained, and some earlier mega wrappers did not emit cards/patches directly.
- **Economic validity:** avoided-token values are estimates derived from comparable Lane B usage, not audited invoices or measured dollar savings.
- **Cross-provider interpretation:** zero-call transfer tests capability portability, not target-provider inference quality.
- **Mutation interpretation:** the A-D ladder is policy evidence; only the six occurrence-10 cases are live recovery trials.

## Claim Assessment

**Supported:** within-provider deterministic crystallization through occurrence 5; repository-bound impact fingerprints; six live stale-reuse blocks and recoveries; 12 primary cross-provider zero-call capability consumptions; six Groq scout consumptions; nonzero semantic-credit token estimates; secret-clean packaged evidence.

**Partially supported:** quality-preserving cloud-call displacement. It is strong for the NVIDIA maturity slice (`12/24`) but the full five-provider, five-occurrence controlled matrix is incomplete.

**Not yet supported:** completion of the 450-observation controlled core; natural organic crystallization; universal provider/model superiority; dollar-denominated economic savings; raw-response forensic reproducibility; production-scale durability across repository histories.

## Recommended Next Experiments

1. Persist redacted raw response bodies at generation time and bind each to its card with SHA-256.
2. Complete occurrences 2, 3, 5, and 10 for the remaining providers without mixing exploratory and confirmatory runs.
3. Execute live A-D mutations for every family, especially tier D escalation, rather than relying only on policy decisions.
4. Capture natural no-harness sessions separately and pre-register the organic crystallization criteria.
5. Repeat the controlled matrix on a held-out repository and task-family set.
6. Record actual provider billing or first-party cost counters alongside avoided-token estimates.

## Overall Assessment

The evidence is technically meaningful and stronger than a conventional prompt benchmark: it tests verified execution, recurrence, local reuse, mutation invalidation, and provenance. The mature NVIDIA and mutation results form the most persuasive core. Cross-provider results are valuable evidence that the stored capability is provider-agnostic at consumption time. The package is suitable for a preprint or systems artifact report if claims remain bounded as above. It is not yet sufficient for a definitive general claim about the full mega-test design or production economics.
"""


def readme(metrics: dict[str, Any], coverage: dict[str, Any]) -> str:
    return f"""# {RELEASE_NAME} v{RELEASE_VERSION}

Generated: `{utc_now()}`
Release status: `frozen`

This is the canonical collation of all definitive mega-test runs and their directly supporting provider gauntlets.

## Headline

- Designed controlled core: `{metrics['designed_controlled_matrix_rows']}` observations
- Distinct controlled design cells observed: `{metrics['controlled_design_cells_observed']}/{metrics['designed_controlled_matrix_rows']}`
- Canonical staged analysis records: `{coverage['structured']['canonical_analysis_rows']}` (not IID; overlaps disclosed)
- Mature NVIDIA deterministic reuses: `{metrics['mature_deterministic_reuse']}`
- Mature NVIDIA QPCCD: `{metrics['mature_qpccd'].get('numerator')}/{metrics['mature_qpccd'].get('denominator')} = {metrics['mature_qpccd'].get('rate')}`
- Live mutation blocks/recoveries: `{metrics['mutation_reuse_blocked']}/{metrics['mutation_recovered']}`
- Primary cross-provider cases: `{metrics['primary_cross_provider_cases']}/12`
- Groq scout cases: `{metrics['groq_scout_cases']}/6`
- Primary estimated avoided tokens: `{metrics['primary_avoided_tokens_estimate']}`
- Secret scan: see `secret_scan.json`

## Navigation

- `ACADEMIC_ASSESSMENT.md`: comprehensive scholarly interpretation and limitations
- `master_manifest.json`: source inventory and bundle metadata
- `coverage_matrix.json`: evidence availability and explicit gaps
- `collated/`: normalized machine-readable observations and cases
- `evidence/`: cards, patches, rollback snapshots, receipts, and evidence index
- `source_runs/definitive_mega/`: complete original mega directories
- `source_runs/supporting_gauntlets/`: complete underlying gauntlet directories
- `supporting_reports/`: provider summaries used in comparative analysis
- `integrity_manifest.json`: SHA-256 inventory for every packaged file

## Important Limitation

Raw provider response bodies were not persisted by the source runs. The master includes all available response metadata and derived artifacts, but it cannot reconstruct text that was never stored. This absence is explicit in `coverage_matrix.json` and the academic assessment.
"""


def master_integrity(output: Path) -> dict[str, Any]:
    files = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path == output / "integrity_manifest.json":
            continue
        files.append({
            "path": str(path.relative_to(output)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"))
    manifest = {
        "algorithm": "sha256",
        "generated_at": utc_now(),
        "file_count": len(files),
        "files": files,
        "manifest_hash": "sha256:" + hashlib.sha256(canonical.encode()).hexdigest(),
    }
    write_json(output / "integrity_manifest.json", manifest)
    return manifest


def build(output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing master bundle: {output}")
    output.mkdir(parents=True)
    mega_destination = output / "source_runs" / "definitive_mega"
    gauntlet_destination = output / "source_runs" / "supporting_gauntlets"
    mega_destination.mkdir(parents=True)
    gauntlet_destination.mkdir(parents=True)
    for source in MEGA_SOURCES:
        copy_source(source, mega_destination)
    for source in SUPPORTING_GAUNTLETS:
        copy_source(source, gauntlet_destination)
    reports = copy_supporting_reports(output / "supporting_reports")
    evidence_index, evidence_counts = collate_evidence(MEGA_SOURCES + SUPPORTING_GAUNTLETS, output)
    structured = collate_structured(output)
    inventory = source_inventory(MEGA_SOURCES + SUPPORTING_GAUNTLETS)
    metrics = primary_metrics()
    anchors = provider_anchor_metrics()
    coverage = {
        "schema_version": "1.0",
        "evidence_counts": evidence_counts,
        "structured": structured,
        "raw_provider_response_bodies": {
            "available": evidence_counts.get("raw_provider_responses", 0) > 0,
            "count": evidence_counts.get("raw_provider_responses", 0),
            "status": "not_persisted_by_source_runs" if not evidence_counts.get("raw_provider_responses", 0) else "present",
            "surviving_metadata": ["raw_chars", "validation status", "token usage", "latency", "failure reason"],
        },
        "natural_observations": {
            "available": structured["natural_rows"] > 0,
            "count": structured["natural_rows"],
        },
        "source_inventory": inventory,
    }
    write_json(output / "coverage_matrix.json", coverage)
    write_json(output / "analysis_metrics.json", metrics)
    write_json(output / "provider_anchor_comparison.json", anchors)
    write_json(output / "master_manifest.json", {
        "beast_object_type": "beast_definitive_mega_test_master_evidence_bundle",
        "schema_version": "1.0",
        "release_name": RELEASE_NAME,
        "release_version": RELEASE_VERSION,
        "release_status": "frozen",
        "generated_at": utc_now(),
        "definitive_mega_sources": MEGA_SOURCES,
        "supporting_gauntlets": SUPPORTING_GAUNTLETS,
        "canonical_analysis_runs": CANONICAL_ANALYSIS_RUNS,
        "supporting_reports": reports,
        "source_inventory": inventory,
        "evidence_index_records": len(evidence_index),
        "claims_policy": "descriptive_bounded_non_iid",
    })
    write_json(output / "release_manifest.json", {
        "beast_object_type": "beast_evidence_release",
        "release_name": RELEASE_NAME,
        "release_version": RELEASE_VERSION,
        "release_status": "frozen",
        "generated_at": utc_now(),
        "controlled_design": {
            "observed_cells": metrics["controlled_design_cells_observed"],
            "target_cells": metrics["designed_controlled_matrix_rows"],
            "remaining_cells": metrics["controlled_design_cells_remaining"],
            "progress_rate": metrics["controlled_design_progress_rate"],
        },
        "credibility_layers": [
            {"id": "redacted_raw_responses", "status": "pending", "evidence_count": 0},
            {"id": "complete_450_row_design", "status": "in_progress", "evidence_count": metrics["controlled_design_cells_observed"]},
            {"id": "natural_no_harness_sessions", "status": "pending", "evidence_count": structured["natural_rows"]},
            {"id": "held_out_repository_replication", "status": "pending", "evidence_count": 0},
            {"id": "actual_provider_billing", "status": "pending", "evidence_count": 0},
        ],
    })
    (output / "ACADEMIC_ASSESSMENT.md").write_text(academic_report(metrics, anchors, coverage), encoding="utf-8")
    (output / "README.md").write_text(readme(metrics, coverage), encoding="utf-8")
    SecretVault().load()
    matches = scan_secrets(output)
    write_json(output / "secret_scan.json", {
        "passed": not matches,
        "match_count": len(matches),
        "matches": matches,
    })
    if matches:
        raise RuntimeError(f"Master bundle secret scan found {len(matches)} matches")
    integrity = master_integrity(output)
    archive = shutil.make_archive(str(output), "zip", root_dir=str(output))
    return {
        "directory": str(output),
        "archive": archive,
        "integrity_hash": integrity["manifest_hash"],
        "file_count": integrity["file_count"],
        "evidence_counts": evidence_counts,
        "structured": structured,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = build(RESULTS / args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
