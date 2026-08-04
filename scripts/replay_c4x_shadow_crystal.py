#!/usr/bin/env python3
"""Replay a C4-X proof crystal without production routing or providers.

This is a shadow-mode demonstration path. It reads the latest C4-X gauntlet
evidence, selects the best stored proof crystal for a query, verifies the
artifact digests against the joined receipt, and writes replayed text/SVG
artifacts to an evidence directory. It does not call ComputePlane, providers,
or production endpoints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_ROOT = REPO_ROOT / "evidence" / "deterministic-intelligence-ultimate-gauntlet"
DEFAULT_OUT_ROOT = REPO_ROOT / "evidence" / "c4x-shadow-crystal-replay"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def run_replay(
    *,
    query: str,
    evidence_root: str | Path = DEFAULT_EVIDENCE_ROOT,
    out_root: str | Path = DEFAULT_OUT_ROOT,
    run_id: str = "",
) -> dict[str, Any]:
    evidence_path = Path(evidence_root)
    latest_path = evidence_path / "latest.json"
    report = json.loads(latest_path.read_text(encoding="utf-8"))
    source_run = evidence_path / str(report["run_id"])
    if not source_run.is_dir():
        raise FileNotFoundError(f"C4-X run directory not found: {source_run}")
    entries = _crystal_entries(report, source_run)
    selected = max(entries, key=lambda item: _score(query, item))
    selected_dir = Path(selected["case_dir"])
    answer_path = selected_dir / "answer.json"
    svg_path = selected_dir / "diagram.svg"
    proof_graph = json.loads((selected_dir / "proof_graph.json").read_text(encoding="utf-8"))
    text_frame = json.loads((selected_dir / "text_frame.json").read_text(encoding="utf-8"))
    scene_plan = json.loads((selected_dir / "scene_plan.json").read_text(encoding="utf-8"))
    joined_receipt = json.loads((selected_dir / "joined_receipt.json").read_text(encoding="utf-8"))
    answer_bytes = answer_path.read_bytes()
    svg_bytes = svg_path.read_bytes() if svg_path.is_file() else b""
    text_digest_valid = sha256_bytes(answer_bytes) == joined_receipt["text_artifact_digest"]
    visual_digest_valid = (
        (not svg_bytes and joined_receipt["scene_render_valid"] is False)
        or sha256_bytes(svg_bytes) == joined_receipt["rendered_artifact_digest"]
    )
    graph_binding_valid = (
        text_frame["graph_digest"] == joined_receipt["proof_graph_digest"]
        and scene_plan["graph_digest"] == joined_receipt["proof_graph_digest"]
        and proof_graph["graph_digest"] == joined_receipt["proof_graph_digest"]
    )
    replay_verified = text_digest_valid and visual_digest_valid and graph_binding_valid and joined_receipt["joined_verification"] is True
    out_path = Path(out_root) / (run_id or _safe_run_id(query, selected["scenario_id"]))
    out_path.mkdir(parents=True, exist_ok=True)
    shutil.copy2(answer_path, out_path / "answer.json")
    if svg_bytes:
        shutil.copy2(svg_path, out_path / "diagram.svg")
    index = {
        "beast_object_type": "c4x_shadow_crystal_index",
        "version": "1.0",
        "source_gauntlet_run_id": report["run_id"],
        "source_receipt_digest": report["receipt_digest"],
        "entries": entries,
    }
    receipt = {
        "beast_object_type": "c4x_shadow_crystal_replay_receipt",
        "version": "1.0",
        "query": query,
        "selected_scenario_id": selected["scenario_id"],
        "selected_family": selected["family"],
        "selected_status": selected["joined_status"],
        "selected_claim_status": selected["claim_status"],
        "selection_score": _score(query, selected),
        "proof_graph_digest": joined_receipt["proof_graph_digest"],
        "text_frame_digest": joined_receipt["text_frame_digest"],
        "scene_plan_digest": joined_receipt["scene_plan_digest"],
        "text_artifact_digest": joined_receipt["text_artifact_digest"],
        "rendered_artifact_digest": joined_receipt["rendered_artifact_digest"],
        "rendered_artifact_media_type": joined_receipt["rendered_artifact_media_type"],
        "scene_render_valid": joined_receipt["scene_render_valid"],
        "current_claim_valid": joined_receipt["current_claim_valid"],
        "text_digest_valid": text_digest_valid,
        "visual_digest_valid": visual_digest_valid,
        "graph_binding_valid": graph_binding_valid,
        "replay_verified": replay_verified,
        "provider_calls_used": 0,
        "production_interference": "none_shadow_read_only_evidence_replay",
        "answer_path": str(out_path / "answer.json"),
        "diagram_path": str(out_path / "diagram.svg") if svg_bytes else "",
        "source_case_dir": str(selected_dir),
    }
    receipt["receipt_digest"] = _canonical_digest(receipt)
    (out_path / "crystal_index.json").write_text(json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (out_path / "replay_receipt.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (out_path / "README.md").write_text(_markdown(receipt), encoding="utf-8")
    (Path(out_root) / "latest.json").parent.mkdir(parents=True, exist_ok=True)
    (Path(out_root) / "latest.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (Path(out_root) / "latest.md").write_text(_markdown(receipt), encoding="utf-8")
    return receipt


def _crystal_entries(report: Mapping[str, Any], source_run: Path) -> list[dict[str, Any]]:
    entries = []
    for scenario_id, case in sorted(dict(report["cases"]).items()):
        scenario = dict(case["scenario"])
        joined = dict(case["joined_receipt"])
        proof_graph = dict(case["proof_graph"])
        conclusion = dict(proof_graph["claims"][-1])
        entries.append({
            "scenario_id": scenario_id,
            "family": str(scenario["family"]),
            "question": str(scenario["question"]),
            "source": str(scenario["source"]),
            "target": str(scenario["target"]),
            "joined_status": str(joined["status"]),
            "claim_status": str(conclusion["status"]),
            "current_claim_allowed": conclusion.get("current_claim_allowed") is True,
            "proof_graph_digest": str(proof_graph["graph_digest"]),
            "text_frame_digest": str(joined["text_frame_digest"]),
            "scene_plan_digest": str(joined["scene_plan_digest"]),
            "text_artifact_digest": str(joined["text_artifact_digest"]),
            "rendered_artifact_digest": str(joined["rendered_artifact_digest"]),
            "case_dir": str(source_run / "cases" / scenario_id),
        })
    return entries


def _score(query: str, entry: Mapping[str, Any]) -> int:
    query_tokens = set(_tokens(query))
    haystack = " ".join(str(entry.get(key, "")) for key in ("scenario_id", "family", "question", "source", "target", "claim_status", "joined_status"))
    entry_tokens = set(_tokens(haystack))
    score = len(query_tokens & entry_tokens) * 10
    family = str(entry.get("family") or "")
    if "restart" in query_tokens and family == "restart_risk":
        score += 25
    if "traffic" in query_tokens and family == "traffic_shift":
        score += 25
    if "deployment" in query_tokens or "rollout" in query_tokens:
        score += 25 if family == "deployment_safety" else 0
    if str(entry.get("joined_status")) == "composed":
        score += 2
    return score


def _tokens(value: str) -> list[str]:
    return [token for token in re.split(r"[^a-z0-9]+", value.casefold()) if len(token) > 1]


def _safe_run_id(query: str, scenario_id: str) -> str:
    slug = "-".join(_tokens(query)[:8]) or "query"
    return f"{scenario_id}-{slug}"


def _canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _markdown(receipt: Mapping[str, Any]) -> str:
    return "\n".join([
        f"# C4-X shadow crystal replay — {receipt['selected_scenario_id']}",
        "",
        f"- Query: `{receipt['query']}`",
        f"- Replay verified: `{receipt['replay_verified']}`",
        f"- Selected family: `{receipt['selected_family']}`",
        f"- Joined status: `{receipt['selected_status']}`",
        f"- Claim status: `{receipt['selected_claim_status']}`",
        f"- Current claim valid: `{receipt['current_claim_valid']}`",
        f"- Text digest valid: `{receipt['text_digest_valid']}`",
        f"- Visual digest valid: `{receipt['visual_digest_valid']}`",
        f"- Graph binding valid: `{receipt['graph_binding_valid']}`",
        f"- Provider calls used: `{receipt['provider_calls_used']}`",
        f"- Production interference: `{receipt['production_interference']}`",
        f"- Answer: `{receipt['answer_path']}`",
        f"- Diagram: `{receipt['diagram_path']}`",
        f"- Receipt digest: `{receipt['receipt_digest']}`",
        "",
    ]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default="Could restarting BEAST destabilize Commons?")
    parser.add_argument("--evidence-root", default=str(DEFAULT_EVIDENCE_ROOT))
    parser.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    receipt = run_replay(query=args.query, evidence_root=args.evidence_root, out_root=args.out_root, run_id=args.run_id)
    print(json.dumps({
        "replay_verified": receipt["replay_verified"],
        "selected_scenario_id": receipt["selected_scenario_id"],
        "selected_family": receipt["selected_family"],
        "answer_path": receipt["answer_path"],
        "diagram_path": receipt["diagram_path"],
        "receipt_digest": receipt["receipt_digest"],
    }, sort_keys=True, indent=2))
    return 0 if receipt["replay_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
