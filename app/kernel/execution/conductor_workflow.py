"""
EdgeK BEAST Conductor Workflows.

Turns prepared BEAST artifacts into auditable workflow cards. The current swarm
kernel is treated as an advisory planning ledger, not an execution engine.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.execution.least_authority_tools import LeastAuthorityToolLoop


class ConductorWorkflowBuilder:
    """Build workflow cards from envelope, context, scorecard, and swarm advice."""

    def __init__(self, swarm_kernel: Any = None, data_dir: Optional[str] = None):
        self.swarm_kernel = swarm_kernel
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.workflow_dir = Path(data_dir) / "workflow_cards"
        self.dispatch_dir = Path(data_dir) / "workflow_dispatches"

    def build(
        self,
        envelope: Dict[str, Any],
        context_packet: Optional[Dict[str, Any]] = None,
        forge_scorecard: Optional[Dict[str, Any]] = None,
        route_card: Optional[Dict[str, Any]] = None,
        quality_report: Optional[Dict[str, Any]] = None,
        run_swarm: bool = True,
        persist: bool = False,
    ) -> Dict[str, Any]:
        swarm_run = self._swarm_advice(
            envelope,
            context_packet=context_packet,
            forge_scorecard=forge_scorecard,
            run_swarm=run_swarm,
        )
        gates = self._gates(envelope, forge_scorecard, swarm_run)
        steps = self._steps(envelope, context_packet, forge_scorecard, route_card, quality_report, swarm_run, gates)
        workflow = {
            "beast_object_type": "conductor_workflow_card",
            "version": "1.0",
            "workflow_id": "",
            "task_id": envelope.get("task_id"),
            "task_class": envelope.get("task_class"),
            "route_id": (route_card or {}).get("route_id") or (forge_scorecard or {}).get("route_id"),
            "context_packet_id": (context_packet or {}).get("packet_id"),
            "forge_scorecard_id": (forge_scorecard or {}).get("scorecard_id"),
            "execution_mode": "advisory_plan",
            "executor_binding": {
                "available": False,
                "reason": "Existing swarm kernel plans and gates work but does not dispatch real tool/model execution.",
                "future_binding": "MCP/tool executor or runtime action runner",
            },
            "swarm": self._swarm_summary(swarm_run),
            "decision": self._decision(gates, forge_scorecard, swarm_run),
            "required_gates": gates,
            "steps": steps,
            "verification_plan": self._verification_plan(envelope, forge_scorecard, quality_report),
            "chronicle_plan": {
                "required": True,
                "record_type": "workflow_outcome",
                "include": ["task_envelope", "context_packet", "forge_scorecard", "swarm_run", "verification"],
            },
            "promotion_check": {
                "eligible_after": "verified_success",
                "signals": ["same_task_class", "same_route", "stable_scorecard", "passing_verification"],
            },
            "created_at": self._utc_now(),
            "workflow_hash": "",
        }
        digest = self._hash(workflow)
        workflow["workflow_id"] = f"wf_{digest[:16]}"
        workflow["workflow_hash"] = f"sha256:{digest}"
        if persist:
            workflow["artifact"] = self._write(workflow)
        return workflow

    def list_workflows(self, task_class: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        cards = []
        for path in self.workflow_dir.glob("*.json"):
            try:
                card = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if task_class and card.get("task_class") != task_class:
                continue
            cards.append(card)
        cards.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        bounded = cards[: max(1, min(int(limit), 100))]
        return {
            "workflow_cards": bounded,
            "count": len(bounded),
            "total_matches": len(cards),
            "workflow_dir": str(self.workflow_dir),
        }

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        path = self.workflow_dir / f"{workflow_id}.json"
        if not path.exists():
            raise ValueError(f"Workflow card not found: {workflow_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def dispatch(
        self,
        workflow: Dict[str, Any],
        executors: Optional[Dict[str, Any]] = None,
        *,
        approved: bool = False,
        persist: bool = False,
    ) -> Dict[str, Any]:
        """Run a bounded inspect → verify → repair lifecycle.

        Executors are injected by the owning surface.  The dispatcher never
        receives a shell string or a source-write executor; a repair executor
        can only return a new draft SourcePlan for the normal review gate.
        """
        executors = executors or {}
        risk = str((workflow.get("forge_scorecard") or {}).get("risk_level") or "medium")
        loop = LeastAuthorityToolLoop()
        outcomes: List[Dict[str, Any]] = []
        stopped = "completed"
        verification_failed = False
        for step in workflow.get("steps") or []:
            if not isinstance(step, dict):
                continue
            step_id = str(step.get("id") or step.get("step_id") or "")
            status = str(step.get("status") or "pending")
            if status == "blocked":
                stopped = f"gate blocked: {step_id}"
                outcomes.append({"step_id": step_id, "status": "blocked", "reason": stopped})
                break
            if step_id in {"draft_patch", "draft_minimal_patch"}:
                # Model/provider work is owned by the caller and must be a
                # draft. It is intentionally never dispatched here.
                outcomes.append({"step_id": step_id, "status": "awaiting_draft_sourceplan"})
                continue
            executor = executors.get(step_id)
            if executor is None:
                outcomes.append({"step_id": step_id, "status": "not_bound"})
                continue
            tool = {
                "name": f"conductor:{step_id}", "category": "planning" if step_id != "run_verification" else "audit",
                "bucket": "Verify" if step_id == "run_verification" else "Reason", "mutating": False,
            }
            result = loop.execute(tool, executor, phase="review" if step_id == "run_verification" else "architect", risk=risk, approved=approved)
            outcomes.append({"step_id": step_id, "status": "executed" if result.get("ok") else "blocked", "receipt": result})
            if step_id == "run_verification" and result.get("result") is not None:
                verification_failed = not bool((result.get("result") or {}).get("ok", False))
                if verification_failed:
                    repair = executors.get("repair_draft")
                    if repair is None:
                        stopped = "verification failed; repair draft required"
                        break
                    repair_result = loop.execute({"name": "conductor:repair_draft", "category": "planning", "bucket": "Reason", "mutating": False}, repair, phase="architect", risk=risk, approved=approved)
                    outcomes.append({"step_id": "repair_draft", "status": "draft_ready" if repair_result.get("ok") else "blocked", "receipt": repair_result})
                    stopped = "repair draft returned for SourcePlan validation"
                    break
        receipt = {
            "beast_object_type": "conductor_dispatch_receipt", "version": "1.0",
            "workflow_id": workflow.get("workflow_id"), "execution_mode": "bounded_dispatch",
            "outcomes": outcomes, "stopped": stopped, "verification_failed": verification_failed,
            "source_write_rule": "No source write can be dispatched; repaired drafts re-enter SourcePlan validation and approval.",
        }
        if persist:
            receipt["artifact"] = self._write_dispatch(receipt)
        return receipt

    def list_dispatches(self, workflow_id: str = "", limit: int = 20) -> Dict[str, Any]:
        self.dispatch_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for path in self.dispatch_dir.glob("*.json"):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if workflow_id and str(row.get("workflow_id") or "") != workflow_id:
                continue
            rows.append({**row, "artifact": str(path)})
        rows.sort(key=lambda item: str(item.get("created_at") or item.get("timestamp") or ""), reverse=True)
        return {"beast_object_type": "conductor_dispatch_index", "workflow_id": workflow_id or None, "dispatches": rows[:max(1, min(int(limit), 100))], "count": len(rows)}

    def resume(
        self,
        workflow: Dict[str, Any], executors: Optional[Dict[str, Any]] = None, *, approved: bool = False,
    ) -> Dict[str, Any]:
        """Resume from the latest durable receipt without replaying writes.

        Only previously non-mutating, incomplete lifecycle steps are eligible;
        draft/apply steps remain outside this dispatcher.
        """
        history = self.list_dispatches(str(workflow.get("workflow_id") or ""), limit=1)
        prior = (history.get("dispatches") or [{}])[0]
        receipt = self.dispatch(workflow, executors, approved=approved, persist=True)
        receipt["resumed_from"] = str((prior.get("artifact") if isinstance(prior, dict) else "") or "")
        receipt["resume_rule"] = "Only bounded non-mutating lifecycle callbacks are replayed; source writes are never resumed."
        return receipt

    def _swarm_advice(
        self,
        envelope: Dict[str, Any],
        context_packet: Optional[Dict[str, Any]],
        forge_scorecard: Optional[Dict[str, Any]],
        run_swarm: bool,
    ) -> Optional[Dict[str, Any]]:
        if not run_swarm or not self.swarm_kernel:
            return None
        objective = envelope.get("intent") or (envelope.get("inputs") or {}).get("user_request") or "Prepare workflow"
        packet_stats = (context_packet or {}).get("packet_stats") or {}
        files = [
            item.get("source")
            for item in (context_packet or {}).get("included_evidence", [])
            if item.get("kind") == "file_snippet" and item.get("source")
        ]
        try:
            return self.swarm_kernel.run({
                "objective": objective,
                "task_type": envelope.get("task_class"),
                "risk_level": envelope.get("risk_level", "medium"),
                "files": files,
                "estimated_context_tokens": packet_stats.get("estimated_tokens", 0),
                "target_context_tokens": (envelope.get("context_budget") or {}).get("max_tokens", 8000),
                "success_criteria": envelope.get("success_criteria") or [],
                "metadata": {
                    "source": "conductor_workflow",
                    "task_id": envelope.get("task_id"),
                    "context_packet_id": (context_packet or {}).get("packet_id"),
                    "forge_scorecard_id": (forge_scorecard or {}).get("scorecard_id"),
                },
            })
        except Exception as exc:
            return {
                "status": "unavailable",
                "error": str(exc),
                "events": [],
                "plan": [],
                "gates": [],
                "value": {},
            }

    def _steps(
        self,
        envelope: Dict[str, Any],
        context_packet: Optional[Dict[str, Any]],
        forge_scorecard: Optional[Dict[str, Any]],
        route_card: Optional[Dict[str, Any]],
        quality_report: Optional[Dict[str, Any]],
        swarm_run: Optional[Dict[str, Any]],
        gates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        steps = [
            self._step("prepare_task", "conductor", "Use canonical task envelope and success criteria.", "completed"),
            self._step("apply_governance_gates", "sentinel", "Evaluate approval, dependency, compatibility, and policy gates.", "blocked" if self._has_blocking_gate(gates) else "ready"),
            self._step("pack_context", "cartographer", "Use bounded context packet evidence as the work boundary.", "completed" if context_packet else "pending"),
            self._step("score_patch_shape", "forge", "Use Forge scorecard to constrain scope and verification.", "completed" if forge_scorecard else "pending"),
            self._step("select_route", "pathfinder", "Follow route card order and avoided actions.", "completed" if route_card else "pending"),
        ]
        if forge_scorecard and forge_scorecard.get("minimal_patch_first"):
            steps.append(self._step("draft_minimal_patch", "executor_future", "Prepare the smallest behavior-preserving patch possible.", "ready", executes_now=False))
        else:
            steps.append(self._step("draft_patch", "executor_future", "Prepare the implementation patch inside evidence boundaries.", "ready", executes_now=False))
        steps.extend([
            self._step("run_verification", "verifier", "Run required local checks and compatibility tests.", "ready"),
            self._step("publish_chronicle", "archivist", "Record outcome, evidence ids, verification, and promotion signals.", "ready"),
        ])
        if quality_report:
            steps.insert(5, self._step("respect_quality_report", "verifier", f"Quality cascade status is {quality_report.get('status')}.", "completed"))
        for plan_item in (swarm_run or {}).get("plan", []):
            steps.append(self._step(
                f"swarm_{plan_item.get('role', 'role')}_{plan_item.get('action', 'action')}",
                plan_item.get("role", "swarm"),
                plan_item.get("action", "swarm advisory action"),
                "advisory",
            ))
        return steps

    def _gates(
        self,
        envelope: Dict[str, Any],
        forge_scorecard: Optional[Dict[str, Any]],
        swarm_run: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        gates = []
        score_gates = (forge_scorecard or {}).get("required_gates") or {}
        for name, required in score_gates.items():
            if required:
                gates.append({
                    "name": name,
                    "source": "forge_scorecard",
                    "decision": "approval_required" if name == "human_approval_required" else "required",
                })
        for gate in (swarm_run or {}).get("gates", []):
            gates.append({
                "name": gate.get("name"),
                "source": "swarm_kernel",
                "decision": gate.get("decision"),
                "reason": gate.get("reason"),
            })
        for approval in envelope.get("approval_required_for") or []:
            gates.append({
                "name": approval,
                "source": "task_envelope",
                "decision": "approval_if_action_requested",
            })
        return gates

    def _verification_plan(
        self,
        envelope: Dict[str, Any],
        forge_scorecard: Optional[Dict[str, Any]],
        quality_report: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        checks = ["syntax_or_static_check", "targeted_unit_tests"]
        gates = (forge_scorecard or {}).get("required_gates") or {}
        if gates.get("compatibility_tests_required"):
            checks.append("adapter_or_router_compatibility_tests")
        if gates.get("dependency_review_required"):
            checks.append("dependency_manifest_review")
        return {
            "required_checks": checks,
            "quality_cascade_status": (quality_report or {}).get("status"),
            "success_criteria": envelope.get("success_criteria") or [],
            "must_pass_before_chronicle_success": True,
        }

    def _decision(
        self,
        gates: List[Dict[str, Any]],
        forge_scorecard: Optional[Dict[str, Any]],
        swarm_run: Optional[Dict[str, Any]],
    ) -> str:
        if any(gate.get("decision") == "block" for gate in gates):
            return "blocked"
        if any(gate.get("decision") == "approval_required" for gate in gates):
            return "approval_required"
        if (swarm_run or {}).get("status") == "approval_required":
            return "approval_required"
        forge_decision = (forge_scorecard or {}).get("decision")
        if forge_decision in ("proceed_with_constraints", "needs_more_evidence"):
            return forge_decision
        return "ready"

    def _swarm_summary(self, swarm_run: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not swarm_run:
            return {
                "used": False,
                "execution_capability": "not_invoked",
                "note": "No swarm advisory run was requested.",
            }
        return {
            "used": True,
            "run_id": swarm_run.get("run_id"),
            "status": swarm_run.get("status"),
            "state": swarm_run.get("state"),
            "execution_capability": "planning_only",
            "roles": [event.get("role") for event in swarm_run.get("events", [])],
            "model_call_executed": any(
                bool((event.get("details") or {}).get("model_call_executed"))
                for event in swarm_run.get("events", [])
            ),
            "value": swarm_run.get("value", {}),
        }

    def _step(self, step_id: str, role: str, action: str, status: str, executes_now: bool = False) -> Dict[str, Any]:
        return {
            "step_id": step_id,
            "role": role,
            "action": action,
            "status": status,
            "executes_now": executes_now,
        }

    def _has_blocking_gate(self, gates: List[Dict[str, Any]]) -> bool:
        return any(gate.get("decision") in ("block", "approval_required") for gate in gates)

    def _write(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        self.workflow_dir.mkdir(parents=True, exist_ok=True)
        path = self.workflow_dir / f"{workflow['workflow_id']}.json"
        path.write_text(json.dumps(workflow, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"written": True, "path": str(path)}

    def _write_dispatch(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        self.dispatch_dir.mkdir(parents=True, exist_ok=True)
        stable = dict(receipt)
        stable.pop("artifact", None)
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        stable["created_at"] = self._utc_now()
        path = self.dispatch_dir / f"{str(receipt.get('workflow_id') or 'workflow')}_{digest[:16]}.json"
        path.write_text(json.dumps(stable, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        return {"written": True, "path": str(path), "receipt_hash": f"sha256:{digest}"}

    def _hash(self, workflow: Dict[str, Any]) -> str:
        stable = dict(workflow)
        stable["workflow_id"] = ""
        stable["workflow_hash"] = ""
        stable.pop("artifact", None)
        serialized = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
