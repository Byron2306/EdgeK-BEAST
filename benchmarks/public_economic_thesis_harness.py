#!/usr/bin/env python3
"""Build a public benchmark packet for the BEAST economic-thesis claim.

This harness does not declare the thesis proven. It publishes a reproducible
evaluation packet with:

- explicit governed and baseline rows
- blinded grading payloads
- first-party cost and token accounting
- a manifest that marks the claim as an open research question until grading is complete
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "benchmarks" / "results" / "public_economic_thesis_packet"
ROW_LIST_KEYS = (
    "live_results",
    "provider_results",
    "results",
    "rows",
    "items",
    "attempts",
)
SUPPORTED_STATUSES = {"supported", "falsified", "inconclusive", "open_research_question"}


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def discover_inputs(values: Iterable[str]) -> List[Path]:
    paths: List[Path] = []
    for raw in values:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            paths.extend(sorted(candidate for candidate in path.rglob("*.json") if candidate.is_file()))
        elif path.is_file() and path.suffix.lower() == ".json":
            paths.append(path)
    unique: List[Path] = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ROW_LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def extract_usage(row: Dict[str, Any]) -> Dict[str, Any]:
    return row.get("usage") if isinstance(row.get("usage"), dict) else {}


def extract_cost(row: Dict[str, Any], usage: Dict[str, Any]) -> float | None:
    for source in (row, usage):
        for key in ("first_party_cost_usd_total", "estimated_cost_usd", "estimated_cost", "total_cost_usd", "cost_usd", "cost"):
            value = source.get(key)
            try:
                if value is not None:
                    return round(float(value), 9)
            except (TypeError, ValueError):
                continue
    return None


def classify_lane(row: Dict[str, Any], source_path: Path) -> str:
    lane = str(row.get("lane") or row.get("route") or row.get("provider") or "").lower()
    source_name = source_path.stem.lower()
    if any(token in lane for token in ("_raw", "baseline")) or "baseline" in source_name:
        return "baseline"
    if any(token in lane for token in ("full_beast", "governed", "rescued", "beast")):
        return "governed"
    return "candidate"


def visible_output(row: Dict[str, Any]) -> str:
    for key in (
        "text",
        "assistant_text",
        "response_text",
        "output_text",
        "provider_text_excerpt",
        "diff_excerpt",
        "output",
        "final_text",
        "content",
    ):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def visible_prompt(row: Dict[str, Any]) -> str:
    for key in ("prompt", "objective", "task_prompt", "instruction", "task"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def normalize_row(row: Dict[str, Any], source_path: Path, index: int) -> Dict[str, Any]:
    usage = extract_usage(row)
    task = str(row.get("task") or row.get("name") or row.get("scenario") or f"row_{index + 1}")
    prompt = visible_prompt(row)
    output_text = visible_output(row)
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return {
        "source_path": str(source_path.relative_to(ROOT)) if source_path.is_relative_to(ROOT) else str(source_path),
        "task": task,
        "lane_class": classify_lane(row, source_path),
        "lane": str(row.get("lane") or row.get("route") or ""),
        "provider": str(row.get("provider") or row.get("omni_provider") or ""),
        "model": str(row.get("model") or row.get("provider_model") or ""),
        "completed": bool(row.get("completed", False)),
        "latency_ms": row.get("latency_ms"),
        "prompt": prompt,
        "output_text": output_text,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": extract_cost(row, usage),
        "verification": row.get("verification") if isinstance(row.get("verification"), dict) else {},
        "output_evidence": row.get("output_evidence") if isinstance(row.get("output_evidence"), dict) else {},
    }


def filter_rows_for_human_blind(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("lane_class") or "") not in {"governed", "baseline"}:
            continue
        if not str(row.get("output_text") or "").strip():
            continue
        filtered.append(row)
    return filtered


def build_alpha_packet(rows: List[Dict[str, Any]], *, lane_size: int, seed: int) -> Dict[str, Any]:
    lane_size = max(1, int(lane_size))
    rng = random.Random(seed)
    eligible = filter_rows_for_human_blind(rows)
    by_lane: Dict[str, List[Dict[str, Any]]] = {"governed": [], "baseline": []}
    for row in eligible:
        lane = str(row.get("lane_class") or "")
        if lane in by_lane:
            by_lane[lane].append(dict(row))
    selected: List[Dict[str, Any]] = []
    for lane in ("governed", "baseline"):
        pool = by_lane[lane]
        rng.shuffle(pool)
        selected.extend(pool[: min(lane_size, len(pool))])
    rng.shuffle(selected)
    return {
        "generated_at": utc_now(),
        "claim_status": "open_research_question",
        "claim_scope": "Short alpha blind packet for early human grading. Not a final verdict.",
        "row_count": len(selected),
        "rows": selected,
        "alpha": {
            "enabled": True,
            "lane_size": lane_size,
            "seed": seed,
            "eligible_governed": len(by_lane["governed"]),
            "eligible_baseline": len(by_lane["baseline"]),
        },
    }


def build_packet(paths: List[Path]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    for path in paths:
        payload = load_json(path)
        for index, row in enumerate(extract_rows(payload)):
            rows.append(normalize_row(row, path, index))
    return {
        "generated_at": utc_now(),
        "claim_status": "open_research_question",
        "claim_scope": "Economic and quality claims remain provisional until blinded grading and published cost ledgers are complete.",
        "row_count": len(rows),
        "rows": rows,
    }


def write_blind_grading(rows: List[Dict[str, Any]], output_dir: Path, *, seed: int) -> Dict[str, Any]:
    blinded: List[Dict[str, Any]] = []
    keyed_rows: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        blind_id = hashlib.sha256(f"{row['source_path']}|{row['task']}|{row['lane']}|{index}".encode("utf-8")).hexdigest()[:16]
        blind_payload = {
            "blind_id": blind_id,
            "task": row["task"],
            "prompt": row["prompt"],
            "output_text": row["output_text"],
            "verification_summary": {
                "completed": row["completed"],
                "latency_ms": row["latency_ms"],
            },
        }
        blinded.append(blind_payload)
        keyed_rows.append({"blind_id": blind_id, "row": row})
    rng = random.Random(seed)
    rng.shuffle(blinded)
    path = output_dir / "blind_grading.jsonl"
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in blinded), encoding="utf-8")
    key = {
        item["blind_id"]: {
            "task": item["row"]["task"],
            "lane_class": item["row"]["lane_class"],
            "provider": item["row"]["provider"],
            "model": item["row"]["model"],
            "source_path": item["row"]["source_path"],
        }
        for item in keyed_rows
    }
    key_path = output_dir / "blind_grading_key.json"
    key_path.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"packet_path": str(path), "key_path": str(key_path), "count": len(blinded), "seed": seed}


def write_grader_template(output_dir: Path) -> Dict[str, Any]:
    blind_rows = load_jsonl(output_dir / "blind_grading.jsonl")
    template_rows = []
    for item in blind_rows:
        template_rows.append({
            "blind_id": item["blind_id"],
            "passes_task": None,
            "quality_score": None,
            "notes": "",
        })
    template_path = output_dir / "grade_template.jsonl"
    template_path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in template_rows), encoding="utf-8")
    rubric = {
        "beast_object_type": "public_benchmark_grade_rubric",
        "version": "1.0",
        "fields": {
            "passes_task": "boolean; true only if the response satisfies the task as judged blindly",
            "quality_score": "number from 0.0 to 1.0 for quality/completeness",
            "notes": "optional freeform grading notes",
        },
    }
    rubric_path = output_dir / "grade_rubric.json"
    rubric_path.write_text(json.dumps(rubric, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"template_path": str(template_path), "rubric_path": str(rubric_path), "count": len(template_rows)}


def load_grades(paths: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    grades: Dict[str, Dict[str, Any]] = {}
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        rows = load_jsonl(path) if path.suffix.lower() == ".jsonl" else ([] if not path.exists() else [load_json(path)])
        for item in rows:
            blind_id = str(item.get("blind_id") or "").strip()
            if blind_id:
                grades[blind_id] = item
    return grades


def write_provisional_grades_from_verification(output_dir: Path) -> Dict[str, Any]:
    blind_rows = load_jsonl(output_dir / "blind_grading.jsonl")
    rows: List[Dict[str, Any]] = []
    for item in blind_rows:
        completed = bool(((item.get("verification_summary") or {}).get("completed")))
        rows.append({
            "blind_id": str(item.get("blind_id") or ""),
            "passes_task": completed,
            "quality_score": 0.8 if completed else 0.2,
            "notes": "provisional_verification_grade",
        })
    path = output_dir / "provisional_grades_from_verification.jsonl"
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8")
    return {"path": str(path), "count": len(rows), "source": "verification_summary.completed"}


def _structural_components(item: Dict[str, Any]) -> Dict[str, float]:
    text = str(item.get("output_text") or "")
    lowered = text.lower()
    verification = item.get("verification_summary") if isinstance(item.get("verification_summary"), dict) else {}
    completed = bool(verification.get("completed"))
    latency = verification.get("latency_ms")
    action_markers = text.count('"id"') + text.count('"op_id"') + text.count('"type"')
    components = {
        "structured_contract": 0.18 if any(token in lowered for token in ('"kind"', 'beast.action_intent', 'beast.patch_intent', 'beast.source_patch')) else 0.0,
        "operation_structure": 0.18 if any(token in lowered for token in ('"actions"', '"operations"')) else 0.0,
        "targeting": 0.12 if any(token in lowered for token in ('"target"', '"path"', 'anchor_ref', 'file_ref')) else 0.0,
        "verification_plan": 0.14 if any(token in lowered for token in ('pytest', 'verify', 'tests')) else 0.0,
        "multi_step_detail": 0.10 if action_markers >= 3 else 0.04 if action_markers >= 1 else 0.0,
        "readable_payload": 0.08 if 120 <= len(text) <= 8000 else 0.03 if len(text) >= 40 else 0.0,
        "verifier_outcome": 0.16 if completed else 0.0,
        "latency_evidence": 0.04 if latency is not None else 0.0,
    }
    total = round(min(1.0, sum(components.values())), 6)
    components["total"] = total
    return components


def write_structural_grades(output_dir: Path) -> Dict[str, Any]:
    blind_rows = load_jsonl(output_dir / "blind_grading.jsonl")
    rows: List[Dict[str, Any]] = []
    for item in blind_rows:
        components = _structural_components(item)
        score = float(components["total"])
        completed = bool(((item.get("verification_summary") or {}).get("completed")))
        rows.append({
            "blind_id": str(item.get("blind_id") or ""),
            "passes_task": bool(completed and score >= 0.60),
            "quality_score": score,
            "notes": "deterministic_structure_grade",
            "score_components": components,
        })
    path = output_dir / "structural_grades.jsonl"
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in rows), encoding="utf-8")
    return {"path": str(path), "count": len(rows), "source": "output_text+verification_summary"}


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "pass", "passed", "yes", "1"}:
            return True
        if lowered in {"false", "fail", "failed", "no", "0"}:
            return False
    return None


def _coerce_score(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        score = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(score, 1.0))


def build_verdict(output_dir: Path, grade_paths: Iterable[str]) -> Dict[str, Any]:
    key = load_json(output_dir / "blind_grading_key.json")
    cost_payload = load_json(output_dir / "cost_accounting.json")
    grades = load_grades(grade_paths)
    merged_rows: List[Dict[str, Any]] = []
    lane_summary: Dict[str, Dict[str, Any]] = {}
    for blind_id, key_row in key.items():
        grade = grades.get(blind_id, {})
        lane = str(key_row.get("lane_class") or "candidate")
        passes_task = _coerce_bool(grade.get("passes_task"))
        quality_score = _coerce_score(grade.get("quality_score"))
        bucket = lane_summary.setdefault(lane, {"graded_rows": 0, "graded_passes": 0, "quality_sum": 0.0, "quality_rows": 0})
        if passes_task is not None:
            bucket["graded_rows"] += 1
            bucket["graded_passes"] += int(passes_task)
        if quality_score is not None:
            bucket["quality_sum"] += quality_score
            bucket["quality_rows"] += 1
        merged_rows.append({
            "blind_id": blind_id,
            **key_row,
            "passes_task": passes_task,
            "quality_score": quality_score,
            "notes": str(grade.get("notes") or ""),
        })
    for lane, bucket in lane_summary.items():
        cost_lane = ((cost_payload.get("lane_summary") or {}).get(lane) or {})
        bucket["graded_pass_rate"] = round(bucket["graded_passes"] / bucket["graded_rows"], 6) if bucket["graded_rows"] else None
        bucket["average_quality_score"] = round(bucket["quality_sum"] / bucket["quality_rows"], 6) if bucket["quality_rows"] else None
        bucket["total_tokens"] = cost_lane.get("total_tokens")
        bucket["cost_usd"] = cost_lane.get("cost_usd")
        bucket["rows"] = cost_lane.get("rows")
    governed = lane_summary.get("governed") or {}
    baseline = lane_summary.get("baseline") or {}
    status = "inconclusive"
    rationale = "Insufficient graded evidence to support or falsify the claim."
    if governed.get("graded_rows") and baseline.get("graded_rows"):
        governed_pass = governed.get("graded_pass_rate") or 0.0
        baseline_pass = baseline.get("graded_pass_rate") or 0.0
        governed_cost = governed.get("cost_usd")
        baseline_cost = baseline.get("cost_usd")
        if governed_pass > baseline_pass and governed_cost is not None and baseline_cost is not None:
            status = "supported"
            rationale = "Governed lane outperformed the baseline on blinded pass rate with published cost ledgers."
        elif governed_pass < baseline_pass:
            status = "falsified"
            rationale = "Governed lane underperformed the baseline on blinded pass rate."
        else:
            rationale = "Blinded pass rates were tied or did not separate enough to support the claim."
    verdict = {
        "beast_object_type": "public_economic_thesis_verdict",
        "version": "1.0",
        "generated_at": utc_now(),
        "claim_status": status,
        "rationale": rationale,
        "lane_summary": lane_summary,
        "graded_rows": merged_rows,
    }
    if status not in SUPPORTED_STATUSES:
        verdict["claim_status"] = "inconclusive"
    return verdict


def write_verdict(output_dir: Path, verdict: Dict[str, Any], *, basename: str = "verdict") -> Dict[str, Any]:
    path = output_dir / f"{basename}.json"
    path.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Public Economic Thesis Verdict",
        "",
        f"Generated: `{verdict['generated_at']}`",
        "",
        f"- Claim status: `{verdict['claim_status']}`",
        f"- Rationale: {verdict['rationale']}",
        "",
        "| Lane | Graded Rows | Pass Rate | Avg Quality | Cost USD |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for lane, bucket in sorted((verdict.get("lane_summary") or {}).items()):
        pass_rate = "n/a" if bucket.get("graded_pass_rate") is None else f"{bucket['graded_pass_rate']:.2%}"
        avg_quality = "n/a" if bucket.get("average_quality_score") is None else f"{bucket['average_quality_score']:.3f}"
        cost_usd = "n/a" if bucket.get("cost_usd") is None else f"{float(bucket['cost_usd']):.6f}"
        lines.append(f"| `{lane}` | {bucket.get('graded_rows', 0)} | {pass_rate} | {avg_quality} | {cost_usd} |")
    summary_path = output_dir / f"{basename}.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(path), "summary_path": str(summary_path)}


def write_cost_accounting(rows: List[Dict[str, Any]], output_dir: Path) -> Dict[str, Any]:
    by_lane: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        lane = row["lane_class"]
        bucket = by_lane.setdefault(lane, {"rows": 0, "completed": 0, "total_tokens": 0, "cost_usd": 0.0, "cost_rows": 0})
        bucket["rows"] += 1
        bucket["completed"] += int(bool(row["completed"]))
        bucket["total_tokens"] += int(row["total_tokens"] or 0)
        if row["cost_usd"] is not None:
            bucket["cost_usd"] += float(row["cost_usd"])
            bucket["cost_rows"] += 1
    summary = {
        "generated_at": utc_now(),
        "lane_summary": {
            lane: {
                **bucket,
                "cost_usd": round(bucket["cost_usd"], 9),
                "average_cost_usd": round(bucket["cost_usd"] / bucket["cost_rows"], 9) if bucket["cost_rows"] else None,
            }
            for lane, bucket in sorted(by_lane.items())
        },
        "rows": rows,
    }
    path = output_dir / "cost_accounting.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": str(path), "lane_count": len(summary["lane_summary"])}


def write_summary(packet: Dict[str, Any], blind_info: Dict[str, Any], cost_info: Dict[str, Any], output_dir: Path) -> None:
    rows = packet["rows"]
    lines = [
        "# Public Economic Thesis Packet",
        "",
        f"Generated: `{packet['generated_at']}`",
        "",
        "This packet standardizes public evaluation. It does not claim the thesis is proven.",
        "",
        f"- Claim status: `{packet['claim_status']}`",
        f"- Rows included: `{packet['row_count']}`",
        f"- Blind grading packet: `{Path(blind_info['packet_path']).name}` ({blind_info['count']} items)",
        "- Grader template: `grade_template.jsonl`",
        f"- Cost accounting: `{Path(cost_info['path']).name}`",
        "",
        "## Lane Summary",
        "",
        "| Lane | Rows | Completed | Tokens | Cost Rows |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    cost_payload = json.loads((output_dir / "cost_accounting.json").read_text(encoding="utf-8"))
    for lane, bucket in sorted((cost_payload.get("lane_summary") or {}).items()):
        lines.append(f"| `{lane}` | {bucket['rows']} | {bucket['completed']} | {bucket['total_tokens']} | {bucket['cost_rows']} |")
    lines.extend([
        "",
        "## Required Next Step",
        "",
        "Run blinded human or verifier grading against `blind_grading.jsonl`, fill `grade_template.jsonl`, then rerun this harness with `--grades` to generate `verdict.json` and `verdict.md`. Until then, external claims should stay framed as an open research question.",
    ])
    (output_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_manifest(packet: Dict[str, Any], blind_info: Dict[str, Any], cost_info: Dict[str, Any], output_dir: Path, inputs: List[Path]) -> None:
    manifest = {
        "beast_object_type": "public_economic_thesis_packet",
        "version": "1.0",
        "generated_at": packet["generated_at"],
        "claim_status": packet["claim_status"],
        "claim_scope": packet["claim_scope"],
        "inputs": [str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path) for path in inputs],
        "artifacts": {
            "blind_grading": blind_info,
            "grade_template": "grade_template.jsonl",
            "grade_rubric": "grade_rubric.json",
            "cost_accounting": cost_info,
            "summary": "README.md",
        },
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="Result JSON files or directories to package")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="Output directory for the public packet")
    parser.add_argument("--blind-seed", type=int, default=7, help="Deterministic shuffle seed for blind grading")
    parser.add_argument("--grades", nargs="*", default=[], help="Completed grader JSONL or JSON files to ingest for verdict generation")
    parser.add_argument("--alpha-lane-size", type=int, default=0, help="If > 0, build a short balanced alpha packet with this many rows per lane")
    parser.add_argument("--provisional-from-verification", action="store_true", help="Seed provisional grades from verification_summary.completed and emit provisional verdict artifacts")
    args = parser.parse_args(argv)

    input_paths = discover_inputs(args.inputs)
    if not input_paths:
        raise SystemExit("No JSON inputs found")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    base_packet = build_packet(input_paths)
    packet = build_alpha_packet(base_packet["rows"], lane_size=int(args.alpha_lane_size), seed=int(args.blind_seed)) if int(args.alpha_lane_size or 0) > 0 else base_packet
    blind_info = write_blind_grading(packet["rows"], output_dir, seed=int(args.blind_seed))
    write_grader_template(output_dir)
    cost_info = write_cost_accounting(packet["rows"], output_dir)
    write_summary(packet, blind_info, cost_info, output_dir)
    write_manifest(packet, blind_info, cost_info, output_dir, input_paths)
    if args.grades:
        verdict = build_verdict(output_dir, args.grades)
        write_verdict(output_dir, verdict)
    if args.provisional_from_verification:
        provisional_info = write_provisional_grades_from_verification(output_dir)
        provisional_verdict = build_verdict(output_dir, [provisional_info["path"]])
        provisional_verdict["claim_status_basis"] = "provisional_verification_grades"
        provisional_verdict["rationale"] = (
            provisional_verdict["rationale"]
            + " This verdict is preliminary because passes_task was seeded from objective verification outcomes rather than independent blind human grading."
        )
        write_verdict(output_dir, provisional_verdict, basename="provisional_verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())