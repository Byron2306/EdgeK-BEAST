import json
import sqlite3
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from app.kernel.compute.kv_cache_transport import CrossEngineKVCacheTransport
from app.kernel.compute.local_execution_gateway import LocalExecutionGateway
from app.kernel.compute.local_prefix_kv_store import LocalPrefixKVStore
from app.kernel.compute.local_route_optimizer import LocalRouteOptimizer
from app.kernel.compute.local_semantic_cache import LocalSemanticCache
from app.kernel.evals.local_eval_gate import LocalEvalGate
from app.kernel.observability.local_trace_ledger import LocalTraceLedger
from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage

@dataclass(frozen=True)
class LocalCapabilityProfile:
    capability_id: str
    role: str
    storage: str
    cpu_first: bool
    hot_path: bool
    capabilities: Dict[str, bool]

    def to_dict(self):
        return {
            "beast_object_type": "beast_local_capability_profile",
            "version": "1.0",
            **asdict(self),
        }

class LocalCapabilityRegistry:
    def profiles(self) -> List[LocalCapabilityProfile]:
        return [
            LocalCapabilityProfile(
                "local_semantic_cache",
                "semantic answer reuse",
                "sqlite + optional local embeddings",
                True,
                True,
                {"exact": True, "semantic": True, "repo_scoped": True, "verified_only": True},
            ),
            LocalCapabilityProfile(
                "local_prefix_kv_store",
                "prompt-prefix and KV reuse",
                "beast kv transport",
                True,
                True,
                {"prefix_cache": True, "compatibility_guard": True, "raw_tensor_optional": True},
            ),
            LocalCapabilityProfile(
                "local_execution_gateway",
                "CPU model routing",
                "ollama / llama.cpp via InferenceEngineFabric",
                True,
                True,
                {"local_cpu": True, "cloud_disabled_by_default": True},
            ),
            LocalCapabilityProfile(
                "local_trace_ledger",
                "trace and observation ledger",
                "jsonl + sqlite",
                True,
                False,
                {"spans": True, "observations": True, "costs": True, "offline_export": True},
            ),
            LocalCapabilityProfile(
                "local_route_optimizer",
                "route feedback optimization",
                "sqlite",
                True,
                False,
                {"route_scores": True, "model_scores": True, "threshold_tuning": True},
            ),
            LocalCapabilityProfile(
                "local_eval_gate",
                "assertion and promotion gate",
                "json/yaml test specs",
                True,
                False,
                {"assertions": True, "regression": True, "promotion_blocking": True},
            ),
            LocalCapabilityProfile(
                "compute_forge",
                "idle CPU inference preparation",
                "forge snapshots + local ledgers",
                True,
                False,
                {"fingerprint": True, "secret_scan": True, "semantic_seed": True, "handoff_prep": True},
            ),
        ]

    def health(self, *, probe: bool = False, timeout_seconds: float = 0.45) -> Dict[str, Any]:
        profiles = self.profiles()
        rows = [
            {
                **p.to_dict(),
                "configured": True,
                "local_native": True,
                **self._status_fields(p, probe=probe),
                "claim_boundary": "BEAST-native local capability; no external service required.",
            }
            for p in profiles
        ]
        ready_count = sum(1 for row in rows if row["status"] == "ready")
        return {
            "beast_object_type": "beast_local_capability_health",
            "version": "1.0",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "capability_count": len(profiles),
            "configured_count": len(profiles),
            "ready_count": ready_count,
            "integration_count": len(profiles),
            "probe_enabled": bool(probe),
            "probe_timeout_seconds": max(0.05, min(float(timeout_seconds), 3.0)),
            "capabilities": rows,
            "integrations": rows,
            "claim_boundary": "BEAST-native local CPU capability registry; no external service dependency.",
        }

    def _status_fields(self, profile: LocalCapabilityProfile, *, probe: bool) -> Dict[str, Any]:
        if not probe:
            return {
                "status": "configured",
                "live_probe": {
                    "status": "not_attempted",
                    "ready": False,
                    "reason": "probe_not_requested",
                },
            }
        probe_result = self._probe(profile.capability_id)
        return {
            "status": "ready" if probe_result.get("ready") else "failed",
            "live_probe": probe_result,
        }

    def _probe(self, capability_id: str) -> Dict[str, Any]:
        try:
            with tempfile.TemporaryDirectory(prefix=f"beast_{capability_id}_") as tmp:
                root = Path(tmp)
                if capability_id == "local_semantic_cache":
                    return self._probe_semantic_cache(root)
                if capability_id == "local_prefix_kv_store":
                    return self._probe_prefix_kv_store(root)
                if capability_id == "local_execution_gateway":
                    return self._probe_execution_gateway()
                if capability_id == "local_trace_ledger":
                    return self._probe_trace_ledger(root)
                if capability_id == "local_route_optimizer":
                    return self._probe_route_optimizer(root)
                if capability_id == "local_eval_gate":
                    return self._probe_eval_gate()
                if capability_id == "compute_forge":
                    return self._probe_compute_forge(root)
        except Exception as exc:
            return {"status": "failed", "ready": False, "reason": type(exc).__name__, "detail": str(exc)[:200]}
        return {"status": "failed", "ready": False, "reason": "unknown_capability"}

    @staticmethod
    def _probe_semantic_cache(root: Path) -> Dict[str, Any]:
        cache = LocalSemanticCache(root / "semantic.db")
        cache.put(
            credit_id="probe_semantic_credit",
            prompt="summarize local capability health",
            task_class="probe",
            repo_fingerprint="repo_probe",
            answer="local semantic cache ok",
            confidence=0.91,
            verified=True,
            policy_version="probe_v1",
            metadata={"probe": True},
        )
        exact = cache.match(prompt="summarize local capability health", task_class="probe", repo_fingerprint="repo_probe")
        near = cache.match(prompt="summarize local capability health please", task_class="probe", repo_fingerprint="repo_probe", threshold=0.4)
        scoped_miss = cache.match(prompt="summarize local capability health", task_class="probe", repo_fingerprint="other")
        ok = bool(exact and near and scoped_miss is None)
        return {
            "status": "ready" if ok else "failed",
            "ready": ok,
            "reason": "sqlite_exact_semantic_scope_probe",
            "checks": {"exact": bool(exact), "semantic": bool(near), "repo_scope_miss": scoped_miss is None},
        }

    @staticmethod
    def _probe_prefix_kv_store(root: Path) -> Dict[str, Any]:
        from app.kernel.compute.crystal_reuse_gateway import CrystalReuseGateway, CrystalReuseRequest

        storage = DurableInferenceStorage(root / "durable")
        transport = CrossEngineKVCacheTransport(storage_dir=root / "kv")
        gateway = CrystalReuseGateway(storage=storage, kv_transport=transport, seal=ResidueSeal(root / "keys"))
        store = LocalPrefixKVStore(gateway)
        request = CrystalReuseRequest(
            prompt="prefix body",
            model="probe-model",
            tokenizer="probe-tokenizer",
            prompt_prefix="prefix",
            system_prompt="system",
            repo_fingerprint="repo_probe",
        )
        prefill = store.register_prefill(request, engine="ollama", metadata={"probe": True})
        block = store.register_block(request, engine="ollama", tensor_payload=b"probe-kv", metadata={"probe": True})
        decision = gateway.decide(request, seal_decision=False)
        exported = transport.export_tensor_payload(block["block"]["block_id"])
        ok = (
            prefill.get("credit_id")
            and block.get("block", {}).get("pinned") is True
            and decision.action == "reuse_kv_prefill"
            and exported == b"probe-kv"
        )
        return {
            "status": "ready" if ok else "failed",
            "ready": bool(ok),
            "reason": "prefill_and_kv_round_trip_probe",
            "checks": {
                "prefill_registered": bool(prefill.get("credit_id")),
                "kv_pinned": block.get("block", {}).get("pinned") is True,
                "reuse_decision": decision.action,
                "tensor_round_trip": exported == b"probe-kv",
            },
        }

    @staticmethod
    def _probe_execution_gateway() -> Dict[str, Any]:
        class FakeFabric:
            def cpu_candidates(self):
                return [SimpleNamespace(engine_id="llama_cpp"), SimpleNamespace(engine_id="ollama")]

            def generate(self, engine_id, **kwargs):
                return {
                    "beast_object_type": "inference_engine_execution",
                    "engine_id": engine_id,
                    "status": "succeeded",
                    "response": "local execution ok",
                    "prompt_tokens": 3,
                    "output_tokens": 3,
                }

        request = SimpleNamespace(model="probe", prompt="hello", system_prompt="", parameters={"max_tokens": 8}, preferred_engine=None, task_class="probe")
        gateway = LocalExecutionGateway(FakeFabric())
        selected = gateway.select_engine(request)
        result = gateway.complete(request)
        rejected = False
        try:
            gateway.select_engine(SimpleNamespace(**{**request.__dict__, "preferred_engine": "vllm"}))
        except RuntimeError:
            rejected = True
        ok = selected == "ollama" and result.get("cloud_used") is False and rejected
        return {
            "status": "ready" if ok else "failed",
            "ready": ok,
            "reason": "cpu_candidate_selection_and_cloud_rejection_probe",
            "checks": {"selected": selected, "cloud_used": result.get("cloud_used"), "non_cpu_rejected": rejected},
        }

    @staticmethod
    def _probe_trace_ledger(root: Path) -> Dict[str, Any]:
        ledger = LocalTraceLedger(root / "trace.db", root / "traces.jsonl")
        event = ledger.record("trace_probe", "observation", {"cost": 0, "decision": "probe"})
        with sqlite3.connect(root / "trace.db") as conn:
            row_count = conn.execute("SELECT COUNT(*) FROM trace_events WHERE trace_id = ?", ("trace_probe",)).fetchone()[0]
        jsonl_rows = [json.loads(line) for line in (root / "traces.jsonl").read_text().splitlines()]
        ok = event["event_id"] and row_count == 1 and len(jsonl_rows) == 1
        return {
            "status": "ready" if ok else "failed",
            "ready": bool(ok),
            "reason": "sqlite_jsonl_trace_round_trip_probe",
            "checks": {"sqlite_rows": row_count, "jsonl_rows": len(jsonl_rows)},
        }

    @staticmethod
    def _probe_route_optimizer(root: Path) -> Dict[str, Any]:
        optimizer = LocalRouteOptimizer(root / "routes.db")
        optimizer.record(task_class="probe", engine_id="ollama", model="m", success=True, latency_ms=50, tokens=10)
        optimizer.record(task_class="probe", engine_id="llama_cpp", model="m", success=False, latency_ms=10, tokens=10)
        chosen = optimizer.choose_route(SimpleNamespace(task_class="probe"))
        ok = chosen == "ollama"
        return {
            "status": "ready" if ok else "failed",
            "ready": ok,
            "reason": "sqlite_route_feedback_choice_probe",
            "checks": {"chosen": chosen},
        }

    @staticmethod
    def _probe_eval_gate() -> Dict[str, Any]:
        gate = LocalEvalGate()
        passed = gate.evaluate(
            request=SimpleNamespace(task_class="probe"),
            response="BEAST_NIM_LIVE_OK no secrets here",
            rules=[
                {"type": "must_contain", "value": "BEAST_NIM_LIVE_OK"},
                {"type": "must_not_contain", "value": "password="},
                {"type": "regex", "pattern": r"BEAST_[A-Z_]+_OK"},
                {"type": "max_length", "value": 128},
                {"type": "no_secret_patterns"},
            ],
        )
        failed = gate.evaluate(
            request=SimpleNamespace(task_class="probe"),
            response="password=abc",
            rules=[{"type": "no_secret_patterns"}],
        )
        ok = passed["passed"] is True and failed["passed"] is False and passed["promotion_allowed"] is True
        return {
            "status": "ready" if ok else "failed",
            "ready": ok,
            "reason": "assertion_gate_pass_and_block_probe",
            "checks": {"pass_gate": passed["passed"], "block_gate": not failed["passed"]},
        }

    @staticmethod
    def _probe_compute_forge(root: Path) -> Dict[str, Any]:
        from app.kernel.compute.compute_forge import ComputeForgeNode

        repo = root / "repo"
        repo.mkdir()
        (repo / "service.py").write_text("VALUE = 1\n", encoding="utf-8")
        node = ComputeForgeNode("probe_forge", storage=DurableInferenceStorage(root / "forge"))
        fingerprint = node.watch_repo(str(repo), target_paths=[])
        secret_scan = node.perform_secret_scan(str(repo))
        handoff = node.prepare_handoff_packet("probe", {"route_id": "route_probe"}, {"packet_id": "packet_probe"})
        summary = node.get_earned_credits_summary()
        ok = (
            bool(fingerprint.get("fingerprint_hash"))
            and secret_scan.get("work_type") == "secret_scan"
            and handoff.get("work_type") == "prepare_handoff"
            and summary.get("total_work_items", 0) >= 3
        )
        return {
            "status": "ready" if ok else "failed",
            "ready": bool(ok),
            "reason": "forge_fingerprint_secret_scan_handoff_probe",
            "checks": {
                "fingerprint": bool(fingerprint.get("fingerprint_hash")),
                "secret_scan": secret_scan.get("work_type"),
                "handoff": handoff.get("work_type"),
                "work_items": summary.get("total_work_items", 0),
            },
        }
