"""Read-only, integrity-checked projection of the final-boss benchmark receipt."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


RELATIVE_RECEIPT = Path("benchmarks/results/provider_tournament_full_v1/provider_competitors/google/final_boss_crystallization_gauntlet.json")


def final_boss_evidence(root: str | Path) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    path = (base / RELATIVE_RECEIPT).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        return {"receipts": [], "state": "UNAVAILABLE"}
    data = json.loads(path.read_text(encoding="utf-8"))
    payload = {key: value for key, value in data.items() if key not in {"receipt_hash", "receipt_hash_verification"}}
    actual = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    hash_valid = actual == data.get("receipt_hash")
    metrics = data.get("metrics") or {}
    quality = data.get("quality_assessment") or {}
    raw = quality.get("raw_teacher_quality") or {}
    replay = data.get("far_transfer_replay") or {}
    verified = bool(hash_valid and data.get("beast_object_type") == "final_boss_crystallization_gauntlet"
                    and metrics.get("integration_tests_passed") is True and replay.get("tests_passed_after_patch") is True)
    receipt = {
        "id": "benchmark-final-boss-google-v1",
        "path": str(RELATIVE_RECEIPT),
        "source": "benchmark_file",
        "type": "JSON",
        "status": "Verified Synthetic Benchmark" if verified else "Integrity Review Required",
        "validity": 100 if verified else 0,
        "schema": "Valid" if verified else "Warning",
        "hash": actual,
        "size": path.stat().st_size,
        "traces": len(data.get("replay_matrix") or []),
        "summary": "Synthetic gateway migration replay; not a live production capability.",
        "evidence": {
            "receipt_hash_valid": hash_valid,
            "integration_tests_passed": metrics.get("integration_tests_passed"),
            "replay_provider_calls": metrics.get("live_provider_replay_calls"),
            "raw_teacher_patch_count": raw.get("patch_count"),
            "normalized_recipe_used": bool((data.get("training") or {}).get("patch_tool")),
            "production_capability_promoted": False,
        },
    }
    return {"receipts": [receipt], "state": "VERIFIED_SYNTHETIC" if verified else "UNVERIFIED"}
