#!/usr/bin/env python3
"""Compare final-boss crystallization using local Ollama vs Google Gemini."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.final_boss_crystallization_gauntlet import (  # noqa: E402
    FinalBossCrystallizationGauntlet,
    GoogleGeminiFinalBossTeacher,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare final-boss local engine vs Google")
    parser.add_argument("--root", default="benchmarks/results/final_boss_engine_comparison")
    parser.add_argument("--ollama-model", default="qwen2.5:0.5b")
    parser.add_argument("--google-model", default="gemini-2.5-flash")
    parser.add_argument("--decoy-files", type=int, default=24)
    parser.add_argument("--replay-variants", type=int, default=3)
    args = parser.parse_args()

    root = Path(args.root)
    root.mkdir(parents=True, exist_ok=True)
    runs = {}
    errors = {}

    try:
        runs["local_ollama"] = FinalBossCrystallizationGauntlet(
            root / "local_ollama",
            live_ollama=True,
            ollama_model=args.ollama_model,
            decoy_files=args.decoy_files,
            replay_variants=args.replay_variants,
        ).run()
    except Exception as exc:
        errors["local_ollama"] = {"error": type(exc).__name__, "message": str(exc)[:500]}

    try:
        runs["google_gemini"] = FinalBossCrystallizationGauntlet(
            root / "google_gemini",
            teacher=GoogleGeminiFinalBossTeacher(model=args.google_model),
            decoy_files=args.decoy_files,
            replay_variants=args.replay_variants,
        ).run()
    except Exception as exc:
        errors["google_gemini"] = {"error": type(exc).__name__, "message": str(exc)[:500]}

    report = {
        "beast_object_type": "final_boss_engine_comparison",
        "version": "1.0",
        "runs": {name: summarize_receipt(receipt) for name, receipt in runs.items()},
        "errors": errors,
        "winner": choose_winner(runs),
        "interpretation": (
            "Quality is judged by verified integration repair, replay without engine calls, "
            "negative controls, replayable bundle presence, and raw teacher schema/concept quality."
        ),
    }
    (root / "final_boss_engine_comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if "local_ollama" in runs else 1


def summarize_receipt(receipt):
    training = receipt.get("training") or {}
    quality = receipt.get("quality_assessment") or {}
    raw = training.get("raw_quality") or {}
    return {
        "teacher_mode": receipt.get("teacher_mode"),
        "receipt_hash": receipt.get("receipt_hash"),
        "claims": receipt.get("claims") or {},
        "metrics": receipt.get("metrics") or {},
        "quality_score": quality.get("quality_score"),
        "quality_score_max": quality.get("quality_score_max"),
        "raw_schema_valid": raw.get("schema_valid"),
        "raw_patch_count": raw.get("patch_count"),
        "raw_required_concept_count": raw.get("required_concept_count"),
        "replayable_bundle_zip": (receipt.get("replayable_bundle") or {}).get("zip_path"),
        "replayable_bundle_sha256": (receipt.get("replayable_bundle") or {}).get("zip_sha256"),
    }


def choose_winner(runs):
    if not runs:
        return {"status": "no_successful_runs"}
    scored = []
    for name, receipt in runs.items():
        summary = summarize_receipt(receipt)
        claims = summary["claims"]
        metrics = summary["metrics"]
        raw_score = int(summary.get("raw_required_concept_count") or 0)
        score = 0
        score += 10 if claims.get("integration_tests_gate") else 0
        score += 10 if claims.get("fresh_far_transfer_repaired") else 0
        score += 10 if claims.get("no_engine_during_far_transfer_replay") or claims.get("no_provider_during_far_transfer_replay") else 0
        score += 10 if claims.get("negative_controls_blocked") else 0
        score += 5 if (receipt.get("replayable_bundle") or {}).get("baseline_replayable") else 0
        score += raw_score
        score -= int(metrics.get("engine_calls_replay") or metrics.get("live_provider_replay_calls") or 0) * 5
        scored.append({"engine": name, "score": score})
    scored.sort(key=lambda item: (-item["score"], item["engine"]))
    return {"status": "ranked", "ranking": scored, "winner": scored[0]["engine"]}


if __name__ == "__main__":
    raise SystemExit(main())
