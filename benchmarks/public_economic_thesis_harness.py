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
    for key in ("text", "assistant_text", "response_text", "output", "final_text", "content"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def normalize_row(row: Dict[str, Any], source_path: Path, index: int) -> Dict[str, Any]:
    usage = extract_usage(row)
    task = str(row.get("task") or row.get("name") or row.get("scenario") or f"row_{index + 1}")
    prompt = str(row.get("prompt") or row.get("objective") or row.get("task_prompt") or "")
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
    for index, row in enumerate(rows):
        blind_id = hashlib.sha256(f"{row['source_path']}|{row['task']}|{row['lane']}|{index}".encode("utf-8")).hexdigest()[:16]
        blinded.append({
            "blind_id": blind_id,
            "task": row["task"],
            "prompt": row["prompt"],
            "output_text": row["output_text"],
            "verification_summary": {
                "completed": row["completed"],
                "latency_ms": row["latency_ms"],
            },
        })
    rng = random.Random(seed)
    rng.shuffle(blinded)
    path = output_dir / "blind_grading.jsonl"
    path.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in blinded), encoding="utf-8")
    key = {
        item["blind_id"]: {
            "task": row["task"],
            "lane_class": row["lane_class"],
            "provider": row["provider"],
            "model": row["model"],
            "source_path": row["source_path"],
        }
        for item, row in zip(blinded, rows)
    }
    key_path = output_dir / "blind_grading_key.json"
    key_path.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"packet_path": str(path), "key_path": str(key_path), "count": len(blinded), "seed": seed}


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
        "Run blinded human or verifier grading against `blind_grading.jsonl`, then publish the unblinded key and graded results alongside `cost_accounting.json`. Until then, external claims should stay framed as an open research question.",
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
    args = parser.parse_args(argv)

    input_paths = discover_inputs(args.inputs)
    if not input_paths:
        raise SystemExit("No JSON inputs found")
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    packet = build_packet(input_paths)
    blind_info = write_blind_grading(packet["rows"], output_dir, seed=int(args.blind_seed))
    cost_info = write_cost_accounting(packet["rows"], output_dir)
    write_summary(packet, blind_info, cost_info, output_dir)
    write_manifest(packet, blind_info, cost_info, output_dir, input_paths)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())