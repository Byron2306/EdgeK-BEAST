"""Full-spectrum crystallization gauntlet across task difficulty and engines."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.kernel.compute.final_boss_crystallization_gauntlet import (
    FinalBossCrystallizationGauntlet,
    GoogleGeminiFinalBossTeacher,
)
from app.kernel.compute.hard_coding_crystallization_gauntlet import HardCodingCrystallizationGauntlet
from app.kernel.compute.nim_live_probe import NvidiaNIMLiveProbe
from app.kernel.security.secret_vault import SecretVault


class FullSpectrumCrystallizationGauntlet:
    """Run progressively harder crystallization tasks on reachable engines."""

    def __init__(
        self,
        root: Path,
        *,
        ollama_model: str = "qwen2.5:0.5b",
        google_model: str = "gemini-2.5-flash",
        nim_model: str = "",
        decoy_files: int = 24,
        replay_variants: int = 3,
        client: Optional[httpx.Client] = None,
        run_live: bool = True,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ollama_model = ollama_model
        self.google_model = google_model
        self.nim_model = nim_model
        self.decoy_files = max(0, int(decoy_files))
        self.replay_variants = max(1, int(replay_variants))
        self.client = client or httpx.Client()
        self.run_live = bool(run_live)
        self.secret_vault = SecretVault()

    def run(self) -> Dict[str, Any]:
        reachability = self._reachability()
        rows: List[Dict[str, Any]] = []
        rows.append(self._run_local_function_repairs(reachability))
        rows.extend(self._run_final_boss_engines(reachability))
        rows.extend(self._run_endpoint_smokes(reachability))
        receipt = {
            "beast_object_type": "full_spectrum_crystallization_gauntlet",
            "version": "1.0",
            "scope": "coding_repair_integration_architecture_endpoint_reachability",
            "difficulty_tiers": [
                "tier_1_function_repairs",
                "tier_2_multifile_integration_migration",
                "tier_3_scaled_far_transfer_negative_controls",
                "tier_4_reachable_external_endpoint_smokes",
            ],
            "engine_reachability": reachability,
            "rows": rows,
            "scoreboard": self._scoreboard(rows, reachability),
            "created_at_ms": int(time.time() * 1000),
        }
        receipt["receipt_hash"] = _hash(receipt)
        (self.root / "full_spectrum_crystallization_gauntlet.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        return receipt

    def _reachability(self) -> Dict[str, Any]:
        self.secret_vault.load(override=False)
        endpoints: Dict[str, Any] = {}
        endpoints["local_ollama"] = self._probe_ollama()
        endpoints["google_gemini"] = {
            "engine": "google_gemini",
            "configured": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "live_capable": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
            "model": self.google_model,
            "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        }
        endpoints["nvidia_nim"] = {
            "engine": "nvidia_nim",
            "configured": bool(os.environ.get("NVIDIA_API_KEY")),
            "live_capable": bool(os.environ.get("NVIDIA_API_KEY")),
            "model": self.nim_model or "auto",
            "endpoint": os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        }
        return {
            "beast_object_type": "full_spectrum_engine_reachability",
            "version": "1.0",
            "run_live": self.run_live,
            "endpoints": endpoints,
            "reachable_count": sum(1 for item in endpoints.values() if item.get("live_capable")),
        }

    def _probe_ollama(self) -> Dict[str, Any]:
        try:
            response = self.client.get("http://127.0.0.1:11434/api/tags", timeout=3)
            models = [str(item.get("name") or item.get("model") or "") for item in (response.json().get("models") or [])]
            return {
                "engine": "local_ollama",
                "configured": response.status_code < 400,
                "live_capable": response.status_code < 400 and self.ollama_model in models,
                "model": self.ollama_model,
                "model_count": len(models),
                "available_models": models[:16],
                "endpoint": "http://127.0.0.1:11434/api/generate",
            }
        except Exception as exc:
            return {
                "engine": "local_ollama",
                "configured": False,
                "live_capable": False,
                "model": self.ollama_model,
                "error": type(exc).__name__,
                "endpoint": "http://127.0.0.1:11434/api/generate",
            }

    def _run_local_function_repairs(self, reachability: Dict[str, Any]) -> Dict[str, Any]:
        endpoint = (reachability.get("endpoints") or {}).get("local_ollama") or {}
        if not self.run_live or not endpoint.get("live_capable"):
            return {
                "tier": "tier_1_function_repairs",
                "engine": "local_ollama",
                "status": "skipped",
                "reason": "local_ollama_not_live_capable" if self.run_live else "live_disabled",
            }
        try:
            result = HardCodingCrystallizationGauntlet(
                self.root / "tier_1_function_repairs" / "local_ollama",
                live_ollama=True,
                ollama_model=self.ollama_model,
            ).run()
            return {
                "tier": "tier_1_function_repairs",
                "engine": "local_ollama",
                "status": "passed" if result.get("adversarial_claims", {}).get("fresh_problem_variants_repaired") else "failed",
                "difficulty": 1,
                "receipt_hash": result.get("receipt_hash"),
                "metrics": result.get("metrics"),
                "claims": result.get("adversarial_claims"),
                "path": str(self.root / "tier_1_function_repairs" / "local_ollama" / "hard_coding_crystallization_gauntlet.json"),
            }
        except Exception as exc:
            return {
                "tier": "tier_1_function_repairs",
                "engine": "local_ollama",
                "status": "error",
                "error": type(exc).__name__,
                "message": str(exc)[:500],
            }

    def _run_final_boss_engines(self, reachability: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        endpoints = reachability.get("endpoints") or {}
        if self.run_live and (endpoints.get("local_ollama") or {}).get("live_capable"):
            rows.append(self._run_final_boss_local_ollama())
        else:
            rows.append({
                "tier": "tier_2_multifile_integration_migration",
                "engine": "local_ollama",
                "status": "skipped",
                "reason": "local_ollama_not_live_capable" if self.run_live else "live_disabled",
            })
        if self.run_live and (endpoints.get("google_gemini") or {}).get("live_capable"):
            rows.append(self._run_final_boss_google())
        else:
            rows.append({
                "tier": "tier_2_multifile_integration_migration",
                "engine": "google_gemini",
                "status": "skipped",
                "reason": "google_secret_missing_or_live_disabled",
            })
        return rows

    def _run_final_boss_local_ollama(self) -> Dict[str, Any]:
        return self._receipt_row(
            engine="local_ollama",
            tier="tier_3_scaled_far_transfer_negative_controls",
            runner=lambda: FinalBossCrystallizationGauntlet(
                self.root / "tier_3_final_boss" / "local_ollama",
                live_ollama=True,
                ollama_model=self.ollama_model,
                decoy_files=self.decoy_files,
                replay_variants=self.replay_variants,
            ).run(),
        )

    def _run_final_boss_google(self) -> Dict[str, Any]:
        return self._receipt_row(
            engine="google_gemini",
            tier="tier_3_scaled_far_transfer_negative_controls",
            runner=lambda: FinalBossCrystallizationGauntlet(
                self.root / "tier_3_final_boss" / "google_gemini",
                teacher=GoogleGeminiFinalBossTeacher(model=self.google_model),
                decoy_files=self.decoy_files,
                replay_variants=self.replay_variants,
            ).run(),
        )

    def _receipt_row(self, *, engine: str, tier: str, runner) -> Dict[str, Any]:
        try:
            receipt = runner()
            claims = receipt.get("claims") or {}
            metrics = receipt.get("metrics") or {}
            return {
                "tier": tier,
                "engine": engine,
                "status": "passed" if all(claims.values()) else "failed",
                "difficulty": 3,
                "receipt_hash": receipt.get("receipt_hash"),
                "quality_assessment": receipt.get("quality_assessment"),
                "final_final_boss_claims": receipt.get("final_final_boss_claims"),
                "metrics": metrics,
                "claims": claims,
                "replayable_bundle": receipt.get("replayable_bundle"),
                "path": str(self.root / "tier_3_final_boss" / engine / "final_boss_crystallization_gauntlet.json"),
            }
        except Exception as exc:
            return {
                "tier": tier,
                "engine": engine,
                "status": "error",
                "error": type(exc).__name__,
                "message": str(exc)[:500],
            }

    def _run_endpoint_smokes(self, reachability: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        endpoints = reachability.get("endpoints") or {}
        if self.run_live and (endpoints.get("nvidia_nim") or {}).get("live_capable"):
            try:
                receipt = NvidiaNIMLiveProbe(client=self.client).run(
                    requested_model=self.nim_model,
                    timeout_seconds=30,
                    max_tokens=32,
                    discover_models=True,
                )
                rows.append({
                    "tier": "tier_4_reachable_external_endpoint_smokes",
                    "engine": "nvidia_nim",
                    "status": "passed" if receipt.get("status") == "ok" else "failed",
                    "difficulty": 4,
                    "receipt_hash": receipt.get("receipt_hash"),
                    "model": receipt.get("model"),
                    "latency_ms": receipt.get("latency_ms"),
                    "endpoint_claim_boundary": receipt.get("claim_boundary"),
                    "path": "",
                    "receipt": {
                        key: value
                        for key, value in receipt.items()
                        if key not in {"attempted_models", "model_discovery"}
                    },
                })
            except Exception as exc:
                rows.append({
                    "tier": "tier_4_reachable_external_endpoint_smokes",
                    "engine": "nvidia_nim",
                    "status": "error",
                    "error": type(exc).__name__,
                    "message": str(exc)[:500],
                })
        else:
            rows.append({
                "tier": "tier_4_reachable_external_endpoint_smokes",
                "engine": "nvidia_nim",
                "status": "skipped",
                "reason": "nvidia_secret_missing_or_live_disabled",
            })
        return rows

    @staticmethod
    def _scoreboard(rows: List[Dict[str, Any]], reachability: Dict[str, Any]) -> Dict[str, Any]:
        passed = [row for row in rows if row.get("status") == "passed"]
        failed = [row for row in rows if row.get("status") in {"failed", "error"}]
        skipped = [row for row in rows if row.get("status") == "skipped"]
        engines = sorted({str(row.get("engine")) for row in rows if row.get("engine")})
        hard_claim_rows = [
            row for row in passed
            if row.get("tier") == "tier_3_scaled_far_transfer_negative_controls"
            and (row.get("claims") or {}).get("baseline_replayable")
            and (row.get("claims") or {}).get("negative_controls_blocked")
            and (row.get("claims") or {}).get("fresh_far_transfer_repaired")
        ]
        return {
            "beast_object_type": "full_spectrum_scoreboard",
            "version": "1.0",
            "row_count": len(rows),
            "passed": len(passed),
            "failed_or_error": len(failed),
            "skipped": len(skipped),
            "engines_attempted": engines,
            "reachable_endpoint_count": (reachability.get("reachable_count") or 0),
            "hard_claim_engine_count": len(hard_claim_rows),
            "max_difficulty_passed": max((int(row.get("difficulty") or 0) for row in passed), default=0),
            "reviewer_safe_claim": {
                "multi_task": any(row.get("tier") == "tier_1_function_repairs" and row.get("status") == "passed" for row in rows),
                "multi_file_architecture": bool(hard_claim_rows),
                "replayable_baselines": all((row.get("claims") or {}).get("baseline_replayable") for row in hard_claim_rows),
                "negative_controls": all((row.get("claims") or {}).get("negative_controls_blocked") for row in hard_claim_rows),
                "zero_replay_engine_calls": all((row.get("metrics") or {}).get("engine_calls_replay") == 0 for row in hard_claim_rows),
            },
        }


def _hash(payload: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

