"""Offline, receipt-backed invoice repair closure for the wider swarm proof."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.kernel.agents.phase_d_execution import GovernedForgeExecutor, PhaseDCritic, PhaseDVerifier
from app.kernel.agents.phase_e_learning import Archivist, Scribe
from app.kernel.agents.patch_compiler import ResidualPatchCompiler
from app.kernel.agents.residual_solver import ResidualSolverBoundary
from app.kernel.agents.tiny_model_conductor import TinyModelConductor
from app.kernel.agents.sourceplan_approval import VerifiedDiffSourcePlan
from app.kernel.agents.ollama_planner_provider import OllamaPlannerProvider
from app.kernel.compute.crystal_assistance_compiler import CrystalAssistanceCompiler
from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.compute.crystal_strengthening import VerifiedCrystalStrengthener
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage
from app.kernel.compute.perceive import EdgeKIR
from app.kernel.data_processing.workspace_graph import WorkspaceGraph
from app.kernel.networking.swarm import SwarmKernel
from app.kernel.workspaces.worktree_forge import WorktreeForge
from app.kernel.commons.route_damping import RouteFlapDampener


INVOICE_FILES = {
    "pricing.py": "def apply_discount(amount, percent):\n    return amount - percent\n",
    "invoice.py": "from pricing import apply_discount\n\ndef invoice_total(amount, percent):\n    return apply_discount(amount, percent)\n",
    "README.md": "# Invoice fixture\n\nPercentage discounts are applied to invoice totals.\n",
    "tests/test_pricing.py": "from pricing import apply_discount\n\ndef test_percentage_discount_subtracts_percent_as_value():\n    assert apply_discount(200, 15) == 170\n",
}

EXPECTED_FAILURE_SIGNATURE = "pytest:percentage_discount:subtracts_percent_as_value"
CORRECTED_SOURCE = "def apply_discount(amount, percent):\n    return amount - (amount * percent / 100)\n"


class _ReceiptGate:
    reason = "local residual route permitted"


class _ReceiptInterception:
    gate = _ReceiptGate()


class _ReceiptInterceptor:
    """Minimal interceptor seam used by the deterministic offline closure."""

    def begin(self, request: EdgeKIR, route: str) -> _ReceiptInterception:
        self.request = request
        self.route = route
        return _ReceiptInterception()

    def execution_route(self, interception: _ReceiptInterception) -> str:
        return "provider"

    def complete(self, interception: _ReceiptInterception, **kwargs: Any) -> Any:
        class Receipt:
            def to_dict(self_inner) -> Dict[str, Any]:
                return {"receipt_id": "invoice-residual-1", "status": kwargs.get("status", "completed"), "route": "provider"}

        return Receipt()


class _InvoiceResidualProvider:
    model = "offline-deterministic-residual"

    def __init__(self) -> None:
        self.packets: list[Dict[str, Any]] = []

    async def solve_residual(self, payload: Dict[str, Any], *, run: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.packets.append(json.loads(json.dumps(payload, sort_keys=True)))
        return {"status": "solved", "fields": {"new": CORRECTED_SOURCE}, "reason": "percentage must be applied to amount"}


class _RecordingResidualProvider:
    """Preserve exact packet evidence around either fake or live provider."""

    def __init__(self, provider: Any):
        self.provider = provider
        self.model = getattr(provider, "model", "unknown")
        self.packets: list[Dict[str, Any]] = []

    async def solve_residual(self, payload: Dict[str, Any], *, run: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.packets.append(json.loads(json.dumps(payload, sort_keys=True)))
        return await self.provider.solve_residual(payload, run=run)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _run_pytest(root: Path) -> Dict[str, Any]:
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_pricing.py", "-q"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": process.stdout[-4000:],
        "stderr": process.stderr[-4000:],
        "command": [sys.executable, "-m", "pytest", "tests/test_pricing.py", "-q"],
    }


def _failure_signature(result: Dict[str, Any]) -> str:
    text = f"{result.get('stdout', '')}\n{result.get('stderr', '')}".lower()
    if "test_percentage_discount_subtracts_percent_as_value" in text and "assert" in text:
        return EXPECTED_FAILURE_SIGNATURE
    return "pytest:unclassified:baseline_failure"


def run_invoice_closure(*, root: Optional[str] = None, use_live_model: bool = False, model: Optional[str] = None) -> Dict[str, Any]:
    """Run the complete bounded invoice repair proof in an isolated worktree."""
    temporary = tempfile.TemporaryDirectory(prefix="beast-invoice-") if root is None else None
    base = Path(root or temporary.name).resolve()
    try:
        for relative, content in INVOICE_FILES.items():
            path = base / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        _git(base, "init", "-q")
        _git(base, "config", "user.email", "beast@example.invalid")
        _git(base, "config", "user.name", "BEAST Test")
        _git(base, "add", ".")
        _git(base, "commit", "-qm", "invoice fixture baseline")

        graph = WorkspaceGraph(db_path=str(base / ".graph.db"))
        conductor = TinyModelConductor()
        timeline = []
        indexed = graph.index_repository(str(base), max_files=10)
        snapshot = graph.graph_snapshot(node_limit=80, edge_limit=160)
        file_labels = {str(node.get("label")) for node in snapshot.get("nodes", []) if node.get("type") == "file"}
        selected_files = [path for path in ("pricing.py", "invoice.py") if path in file_labels]
        source_file_labels = {label for label in file_labels if not label.startswith(".crystals/")}
        if len(source_file_labels) != 4 or selected_files != ["pricing.py", "invoice.py"]:
            raise AssertionError(f"invoice graph selection failed: files={file_labels}, selected={selected_files}")
        timeline.append(conductor.complete_current(evidence={"repository_files": indexed["indexed_files"], "selected_files": selected_files, "primary_file": "pricing.py", "selected_symbol": "apply_discount"}))
        pricing_source = (base / "pricing.py").read_text(encoding="utf-8")

        forge = WorktreeForge(base)
        created = forge.create(objective="Repair invoice percentage discount", task_id="invoice-closure")
        if not created.get("ok"):
            raise RuntimeError(str(created.get("task", {}).get("error") or "worktree creation failed"))
        task = created["task"]
        worktree = Path(task["worktree_path"])
        timeline.append(conductor.complete_current(evidence={"task_id": task["task_id"], "worktree_root": str(worktree)}))
        baseline = _run_pytest(worktree)
        signature = _failure_signature(baseline)
        if baseline["ok"] or signature != EXPECTED_FAILURE_SIGNATURE:
            raise AssertionError(f"unexpected baseline: {baseline}")
        timeline.append(conductor.complete_current(evidence={"failure_signature": signature, "returncode": baseline["returncode"], "workspace_mutated": False}))

        forge_node = ComputeForgeNode("invoice-forge", storage=DurableInferenceStorage(base / ".forge-storage"))
        forge_assistance = forge_node.prepare_agent_assistance(
            objective="Fix the percentage discount failure in the invoice fixture",
            workspace=str(base),
            verifier_result=baseline,
            policy={"class": "local_first", "authority": "isolated_worktree"},
            target_paths=selected_files,
            target_symbol="apply_discount",
            old="return amount - percent",
        )
        timeline.append({
            "state": "FORGE_ASSISTANCE",
            "label": "Forge reduced repository to target symbol",
            "allowed_next_tools": ["residual.solve"],
            "status": "passed",
            "evidence": forge_assistance,
        })

        swarm = SwarmKernel(db_path=str(base / ".swarm.db"), workspace_graph=graph)
        mission = swarm.run({
            "objective": "Fix the percentage discount failure in the invoice fixture",
            "task_type": "test_repair",
            "files": selected_files,
            "target": {"path": "pricing.py", "symbol": "apply_discount"},
            "current_code": pricing_source,
            "failure": baseline["stdout"] + baseline["stderr"],
            "failure_signature": signature,
            "baseline_verified": True,
            "use_ollama": False,
            "allowed_output": {"new": "complete replacement source for pricing.py"},
        })
        events = {event["role"]: event for event in mission["events"]}
        compressor_packet = events["compressor"]["details"]["exact_model_payload"]
        crystal_compiler = CrystalAssistanceCompiler()
        crystal_request = {
            "task_family": "percentage_arithmetic_repair",
            "lifecycle_phase": "PATCH_REQUIRED",
            "failure_signature": signature,
            "target_file": "pricing.py",
            "target_symbol": "apply_discount",
            "target_files": selected_files,
            "old": pricing_source,
            "verifier_command": "python -m pytest tests/test_pricing.py -q",
            "repository_fingerprint": forge_assistance.get("fingerprint_hash"),
            "target_hash": forge_assistance.get("fingerprint_hash"),
        }
        crystal_probe = crystal_compiler.compile(crystal_request)
        crystal_strengthener = VerifiedCrystalStrengthener(base / ".crystals")
        crystal_lookup = crystal_strengthener.lookup({
            "task_family": "percentage_arithmetic_repair",
            "failure_signature": signature,
            "symbol_shape": "apply_discount:function",
            "operation_family": "replace_exact",
        })
        execution_crystals = []
        if crystal_lookup.get("execution_allowed"):
            record = crystal_lookup.get("record") if isinstance(crystal_lookup.get("record"), dict) else {}
            resolved = record.get("resolved_residual") if isinstance(record.get("resolved_residual"), dict) else {}
            replacement = resolved.get("replacement_pattern")
            if replacement:
                execution_crystals.append({
                    "applicability_key": record.get("applicability_key") or crystal_probe.applicability_key,
                    "compatible": True,
                    "replacement": replacement,
                    "confidence": 1.0,
                })
        assistance = crystal_compiler.compile({**crystal_request, "execution_crystals": execution_crystals})
        compiler = ResidualPatchCompiler()
        compiled = compiler.compile({
            "objective": mission["objective"],
            "target": {"path": "pricing.py", "symbol": "apply_discount"},
            "old": pricing_source,
            "verify": ["python -m pytest tests/test_pricing.py -q"],
        })
        provider = _RecordingResidualProvider(
            OllamaPlannerProvider(
                model=model or os.environ.get("BEAST_GOLDEN_PATH_MODEL") or os.environ.get("BEAST_OLLAMA_MODEL") or "qwen2.5-coder:1.5b",
                base_url=os.environ.get("BEAST_OLLAMA_BASE_URL") or "http://127.0.0.1:11434",
                timeout_seconds=120.0,
                route_dampener=RouteFlapDampener(path=base / ".route-damping.json"),
                route_id="invoice-residual-ollama",
            ) if use_live_model else _InvoiceResidualProvider()
        )
        residual = asyncio.run(ResidualSolverBoundary(provider=provider, interceptor=_ReceiptInterceptor()).solve({
            **compressor_packet,
            "crystal_assistance": assistance.to_dict(),
            "crystal_guidance": assistance.prior_effect_patterns,
            "action_ir": compiled["action_ir"],
            "unresolved_fields": assistance.unresolved_fields,
            "allowed_output": {"new": "complete replacement source for pricing.py"},
            "model_call_required": assistance.to_dict()["model_call_required"],
            "action_template": assistance.action_template,
            "resolved_fields": {"new": assistance.action_template["new"]} if assistance.assistance_mode == "deterministic_reuse" else {},
        }, task_class="test_repair", run_id=mission["run_id"]))
        solved_source = residual["fields"]["new"]
        contribution = residual["contribution_accounting"]
        timeline.append(conductor.complete_current(evidence={"provider": provider.model, "provider_calls": int(bool(residual["provider_called"])), "model_packet_digest": residual.get("model_packet_digest", ""), "allowed_response": ["new"], "crystal_assistance_compiled": True, "assistance_mode": assistance.assistance_mode, "compatible_crystals": len(assistance.compatible_crystals), "forge_assistance_digest": forge_assistance["assistance_digest"], "contribution_accounting": contribution, "model_usage": residual.get("usage", {}), "reuse_short_circuit": residual["status"] == "reused"}))
        action_ir = json.loads(json.dumps(compiled["action_ir"]))
        action_ir["actions"][0]["new"] = solved_source

        def mutate(_: Dict[str, Any], authority: Dict[str, Any]) -> Dict[str, Any]:
            path = worktree / authority["path"]
            before = path.read_text(encoding="utf-8")
            if before != pricing_source:
                raise ValueError("target source changed before mutation")
            path.write_text(solved_source, encoding="utf-8")
            return {"receipt_id": "invoice-mutation-1", "path": authority["path"], "before_sha256": hashlib.sha256(before.encode()).hexdigest(), "after_sha256": hashlib.sha256(solved_source.encode()).hexdigest()}

        execution = GovernedForgeExecutor(mutation_runner=mutate).execute(
            action_ir,
            approval_id="canonical-agent-tools",
            worktree_task_id=str(task["task_id"]),
            worktree_root=str(worktree),
            approved=True,
        )
        verification_raw = _run_pytest(worktree)
        verification = PhaseDVerifier().verify([{"status": "passed" if verification_raw["ok"] else "failed", "ok": verification_raw["ok"], "receipt": verification_raw}], mutation_epoch=1, verified_epoch=1)
        timeline.append(conductor.complete_current(evidence={"mutation_receipt": execution.get("result", {}).get("receipt_id"), "verification": verification["status"]}))
        critic = PhaseDCritic().review(execution, verification, allowed_paths=["pricing.py"])
        episode = Scribe().compile_episode(task_class="test_repair", events=mission["events"], execution=execution, verification=verification, critic=critic)
        archive = Archivist().archive(episode, execution=execution, verification=verification, critic=critic)
        diff = forge.diff(str(task["task_id"]))
        source_plan = VerifiedDiffSourcePlan().build(
            action_ir=action_ir,
            diff=diff,
            execution=execution,
            verification=verification,
            forge_assistance=forge_assistance,
            crystal_assistance=assistance.to_dict(),
            model_contribution={"model_packet_digest": residual["model_packet_digest"]},
        )
        crystal_strengthening = crystal_strengthener.strengthen({
            "task_family": "percentage_arithmetic_repair",
            "failure_signature": signature,
            "symbol_shape": "apply_discount:function",
            "operation_family": "replace_exact",
            "resolved_residual": {"replacement_pattern": solved_source},
            "verifier_contract": "pytest tests/test_pricing.py -q",
            "visible_pass": True,
            "verification_status": verification["status"],
            "authority": ["worktree_mutation", "worktree_verification"],
            "applicability_key": assistance.applicability_key,
        })
        timeline.append(conductor.complete_current(evidence={"changed_files": ["pricing.py"], "diff": diff.get("diff", "")[:4000], "approval_required": True}))
        timeline.append(conductor.complete_current(evidence={"archive_hash": archive["receipt"]["packet_hash"]}))
        forge.archive(str(task["task_id"]), reason="invoice closure proof complete")
        return {
            "status": "passed" if verification["passed"] and critic["passed"] else "failed",
            "fixture": {"repository_files": indexed["indexed_files"], "selected_files": selected_files, "primary_file": "pricing.py", "selected_symbol": "apply_discount"},
            "baseline": {"ok": baseline["ok"], "failure_signature": signature},
            "residual": {
                "status": residual["status"],
                "provider_called": residual["provider_called"],
                "model_mode": "live_ollama" if use_live_model else "deterministic_test_provider",
                "model": provider.model,
                "packet_digest": residual["model_packet_digest"],
                "packet_body_matches_boundary": residual["status"] == "reused" or (bool(provider.packets) and json.loads(residual["model_packet"]) == provider.packets[0]),
                "usage": residual.get("usage", {}),
                "crystal_assistance": assistance.to_dict(),
                "forge_assistance": forge_assistance,
                "contribution_accounting": contribution,
            },
            "execution": execution,
            "verification": verification,
            "critic": critic,
            "archive": archive["receipt"],
            "source_plan": source_plan,
            "crystal_strengthening": crystal_strengthening,
            "swarm_proof": {
                "route": events.get("hermes", {}).get("details", {}).get("route_decision", {}),
                "context": events.get("compressor", {}).get("details", {}),
                "interception": {
                    "assistance_mode": assistance.assistance_mode,
                    "model_packet_digest": residual["model_packet_digest"],
                    "provider_called": residual["provider_called"],
                    "model_usage": residual.get("usage", {}),
                    "reuse_short_circuit": residual["status"] == "reused",
                },
                "isolation": execution.get("authority", {}),
                "verification": verification,
                "archive": archive["receipt"],
                "source_plan": {"status": source_plan["status"], "plan_digest": source_plan["plan_digest"], "operator_decision": source_plan["operator_decision"]},
                "crystal_strengthening": crystal_strengthening,
            },
            "golden_timeline": timeline,
            "mission_run_id": mission["run_id"],
        }
    finally:
        if temporary is not None:
            temporary.cleanup()
