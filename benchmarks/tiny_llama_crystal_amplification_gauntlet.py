#!/usr/bin/env python3
"""Tiny Llama Crystal Amplification Gauntlet.

This is a local, defensive-only benchmark: it asks a CPU/Jetson-style Compute
Forge node to mine model-agnostic cyber-defense crystals, equip a tiny local
Llama-style model with OpenClaw/ZeroClaw/Commons routing, and compare that
system against a big-model reference lane.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute_forge import ComputeForgeNode

RESULTS = ROOT / "benchmarks" / "results"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_objectives() -> List[str]:
    return [
        "Review parser and output validation boundaries.",
        "Check secret redaction and log-safety surfaces.",
        "Audit authorization boundary assumptions.",
        "Rank dependency and supply-chain review targets.",
        "Prepare incident evidence timeline from redacted local observations.",
        "Draft ZeroClaw no-execution investigation plan.",
        "Draft OpenClaw local-first defensive patch plan.",
        "Build Compute Governor reuse gates for safe hardening tasks.",
    ]


def build_report(args: argparse.Namespace) -> Dict[str, Any]:
    node = ComputeForgeNode(node_id=args.node_id, node_type=args.node_type)
    mining = node.mine_defensive_crystals(
        args.repo,
        objectives=default_objectives()[: max(1, int(args.crystals))],
        target_model=args.tiny_model,
        teacher_model=args.teacher_model,
        max_crystals=max(1, int(args.crystals)),
    )
    pack = node.build_crystal_amplification_pack(
        mining["crystals"],
        target_model=args.tiny_model,
        orchestrators=["zeroclaw", "openclaw", "meta_tool_commons", "compute_governor", "kv_cache_transport"],
    )
    fused = node.fuse_inference_crystals(
        name="llama_opus_style_defensive_orchestrator",
        task_class="cyber_defense_orchestration",
        crystals=mining["crystals"],
        meta_tools=[
            {"name": "meta_tool_commons_ranker", "kind": "meta_tool", "risk_class": "low"},
            {"name": "compute_governor_reuse_gate", "kind": "meta_tool", "risk_class": "low"},
            {"name": "kv_cache_transport_router", "kind": "meta_tool", "risk_class": "low"},
        ],
        skills=[
            {"name": "secure_code_review", "kind": "skill", "risk_class": "low"},
            {"name": "incident_timeline_digest", "kind": "skill", "risk_class": "low"},
        ],
        swarm_recipes=[
            {"name": "zeroclaw_no_exec_plan", "role": "planner"},
            {"name": "openclaw_local_patch_plan", "role": "inspector"},
        ],
        target_model=args.tiny_model,
    )
    comparison = node.compare_amplified_tiny_model(pack, big_model_label=args.big_model)
    live_anchor = load_live_big_model_anchor(getattr(args, "big_model_artifact", None))
    snapshot = node.get_earned_credits_summary()
    assertions = {
        "defensive_only": mining.get("safety_posture") == "defensive_only_model_agnostic_crystals",
        "crystals_mined": int(mining.get("crystal_count") or 0) >= 1,
        "pack_model_agnostic": pack.get("beast_object_type") == "tiny_llama_crystal_amplification_pack",
        "tiny_gain_positive": float(comparison.get("tiny_gain_over_raw") or 0.0) > 0,
        "orchestration_present": {"zeroclaw", "openclaw", "meta_tool_commons"}.issubset(set(pack.get("orchestrators") or [])),
        "offensive_payloads_absent": not _contains_forbidden_payload({"mining": mining, "pack": pack, "comparison": comparison}),
    }
    report = {
        "beast_object_type": "tiny_llama_crystal_amplification_gauntlet",
        "version": "1.0",
        "generated_at": utc_now(),
        "repo": str(Path(args.repo).resolve()),
        "platform": platform.platform(),
        "tiny_model": args.tiny_model,
        "big_model": args.big_model,
        "teacher_model": args.teacher_model,
        "node": node.profile.to_dict(),
        "mining": mining,
        "amplification_pack": pack,
        "fused_inference_crystal": fused,
        "comparison": comparison,
        "live_big_model_anchor": live_anchor,
        "forge_snapshot": snapshot,
        "assertions": assertions,
        "passed": all(bool(value) for value in assertions.values()),
        "claim_boundary": (
            "A tiny model is evaluated as part of a BEAST system equipped with verified defensive crystals. "
            "This does not claim the base tiny model has frontier general intelligence."
        ),
    }
    canonical = json.dumps({k: v for k, v in report.items() if k != "report_hash"}, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    report["report_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    return report


def _contains_forbidden_payload(payload: Any) -> bool:
    """Small safety scan for obvious offensive automation language."""
    def strip_boundaries(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip_boundaries(item)
                for key, item in value.items()
                if key not in {"safety_boundary", "claim_boundary", "safety_posture"}
            }
        if isinstance(value, list):
            return [strip_boundaries(item) for item in value]
        return value

    text = json.dumps(strip_boundaries(payload), sort_keys=True, default=str).lower()
    forbidden = [
        "credential theft",
        "persistence payload",
        "evasion payload",
        "exploit chain",
        "reverse shell",
        "exfiltrate",
        "weaponized",
    ]
    return any(token in text for token in forbidden)


def write_report(report: Dict[str, Any], output: str) -> Dict[str, Any]:
    output_dir = RESULTS / output
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "amplification_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "crystals.json").write_text(json.dumps(report["mining"]["crystals"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "amplification_pack.json").write_text(json.dumps(report["amplification_pack"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "fused_inference_crystal.json").write_text(json.dumps(report["fused_inference_crystal"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "comparison.json").write_text(json.dumps(report["comparison"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "live_big_model_anchor.json").write_text(json.dumps(report.get("live_big_model_anchor") or {}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_readme(output_dir / "README.md", report)
    integrity = integrity_manifest(output_dir)
    archive = shutil.make_archive(str(output_dir), "zip", root_dir=str(output_dir))
    return {"directory": str(output_dir), "archive": archive, "integrity_hash": integrity["manifest_hash"]}


def write_readme(path: Path, report: Dict[str, Any]) -> None:
    comparison = report["comparison"]
    anchor = report.get("live_big_model_anchor") or {}
    rows = comparison.get("rows") or []
    lines = [
        "# Tiny Llama Crystal Amplification Gauntlet",
        "",
        f"Generated: `{report['generated_at']}`",
        f"Passed: `{bool(report['passed'])}`",
        f"Tiny model: `{report['tiny_model']}`",
        f"Big model reference: `{report['big_model']}`",
        f"Crystals: `{report['mining']['crystal_count']}`",
        f"Pack hash: `{report['amplification_pack']['pack_hash']}`",
        f"Fused crystal: `{report['fused_inference_crystal']['fusion_id']}`",
        f"Crystal credit units: `{report['fused_inference_crystal']['economics']['crystal_credit_units']}`",
        f"Seal provider: `{report['fused_inference_crystal']['seal']['crypto_profile']['provider']}`",
        f"Report hash: `{report['report_hash']}`",
        "",
        "## Comparison",
        "",
        "| Lane | Model | Score | Crystal Hits |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(f"| `{row.get('lane')}` | `{row.get('model')}` | `{row.get('score')}` | `{row.get('crystal_hits')}` |")
    lines.extend([
        "",
        "## Boundary",
        "",
        report["claim_boundary"],
        "",
        "## Live Big-Model Anchor",
        "",
        f"- Artifact: `{anchor.get('artifact_path') or 'not supplied'}`",
        f"- Provider: `{anchor.get('provider') or 'n/a'}`",
        f"- Model: `{anchor.get('model') or 'n/a'}`",
        f"- Controlled rows: `{anchor.get('controlled_rows', 0)}`",
        f"- Full BEAST success rate: `{float(anchor.get('full_beast_success_rate') or 0):.0%}`",
        f"- Compute Governor receipts: `{anchor.get('compute_governor_receipts', 0)}`",
        f"- Provider call receipts: `{anchor.get('provider_call_receipts', 0)}`",
        "",
        "Safety: defensive cyber hardening and analysis only; no exploit payloads or offensive automation.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def load_live_big_model_anchor(path_value: str | None) -> Dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    if path.is_file():
        base = path.parent
    else:
        base = path
    try:
        live = json.loads((base / "live_execution.json").read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in (base / "controlled_observations.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except Exception:
        return {"artifact_path": str(path), "error": "artifact_not_readable"}
    full_rows = [row for row in rows if row.get("lane") == "full_beast_compute_governor"]
    raw_rows = [row for row in rows if row.get("lane") == "raw"]
    provider = next(iter(live.get("providers") or []), None)
    model = None
    for result in live.get("live_results") or []:
        if isinstance(result, dict) and result.get("model"):
            model = result.get("model")
            break
    return {
        "beast_object_type": "live_big_model_anchor",
        "artifact_path": str(base),
        "provider": provider,
        "model": model,
        "controlled_rows": len(rows),
        "raw_success_rate": _rate(raw_rows),
        "full_beast_success_rate": _rate(full_rows),
        "provider_call_receipts": len(live.get("provider_call_receipts") or []),
        "compute_governor_receipts": len(live.get("compute_governor_receipts") or []),
        "crystallization_events": len(live.get("crystallization_events") or []),
    }


def _rate(rows: List[Dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if bool(row.get("completed") and row.get("hidden_passed"))) / len(rows), 6)


def integrity_manifest(output_dir: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "integrity_manifest.json":
            files.append({
                "path": str(path.relative_to(output_dir)),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            })
    manifest = {"algorithm": "sha256", "generated_at": utc_now(), "files": files}
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    manifest["manifest_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
    (output_dir / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=str(ROOT))
    parser.add_argument("--node-id", default="jetson_crystal_forge_cpu")
    parser.add_argument("--node-type", default="jetson")
    parser.add_argument("--tiny-model", default="llama3.2:1b")
    parser.add_argument("--teacher-model", default="nvidia_nim_reference")
    parser.add_argument("--big-model", default="opus_reference")
    parser.add_argument("--big-model-artifact", default=None, help="Optional live mega-test artifact directory for a real big-model anchor.")
    parser.add_argument("--crystals", type=int, default=8)
    parser.add_argument("--output", default="tiny_llama_crystal_amplification_gauntlet")
    args = parser.parse_args(argv)
    report = build_report(args)
    artifacts = write_report(report, args.output)
    print(json.dumps({
        "passed": report["passed"],
        "tiny_gain_over_raw": report["comparison"]["tiny_gain_over_raw"],
        "gap_to_big_raw": report["comparison"]["gap_to_big_raw"],
        "crystal_count": report["mining"]["crystal_count"],
        "artifacts": artifacts,
    }, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
