"""Deterministic, operator-gated SourcePlan promotion for durable AgentRuns."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.kernel.agents.planning_integrations import PlanningIntegrationRuntime
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.agents.tool_models import ToolExecutionContext
from app.kernel.agents.tool_runtime import _remote_target_descriptor, _shell_quote


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> float:
    return time.time()


def _marker_section(stdout: str, start: str, end: str | None = None) -> str:
    if start not in stdout:
        return ""
    tail = stdout.split(start, 1)[1]
    if end and end in tail:
        tail = tail.split(end, 1)[0]
    return tail.strip()


@dataclass(frozen=True)
class PromotionPolicyResult:
    policy_id: str
    passed: bool
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "passed": self.passed,
            "detail": self.detail,
            "evidence": self.evidence,
        }


class PromotionEngine:
    """Evaluate evidence, bind operator approval, and create commit candidates.

    This class is deliberately not exposed as an agent tool. The agent may
    produce a SourcePlan draft, but only an operator-facing route may invoke
    ``promote`` with a separately resolved, receipt-bound approval.
    """

    VERSION = "1.0"

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.engine = AgentRunEngine(self.workspace_root)
        self.planning_integrations = PlanningIntegrationRuntime(str(self.workspace_root))

    def _run(self, run_id: str) -> dict[str, Any]:
        run = self.engine.store.get_run(run_id)
        if not run:
            raise KeyError(f"unknown agent run: {run_id}")
        return run

    @staticmethod
    def _checkpoint(run: dict[str, Any]) -> dict[str, Any]:
        return dict(run.get("checkpoint") or {})

    def _worktree_root(self, checkpoint: dict[str, Any]) -> Path:
        value = str(checkpoint.get("worktree_root") or "")
        if not value:
            raise PermissionError("promotion requires a bound isolated worktree")
        root = Path(value).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise PermissionError("bound worktree is missing")
        git_dir = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=10,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
        if git_dir.returncode != 0:
            raise PermissionError("bound worktree is not a Git worktree")
        return root

    @staticmethod
    def _is_remote_checkpoint(checkpoint: dict[str, Any]) -> bool:
        target = str((checkpoint.get("sourceplan") or {}).get("execution_target") or checkpoint.get("execution_target") or "").strip().lower()
        target_execution = str((checkpoint.get("sourceplan") or {}).get("target_execution") or checkpoint.get("target_execution") or "").strip().lower()
        return bool(checkpoint.get("worktree_remote")) or target in {"ssh", "container", "devcontainer"} or target_execution.startswith("remote_")

    def _remote_context(self, run_id: str, checkpoint: dict[str, Any]) -> ToolExecutionContext:
        sourceplan = checkpoint.get("sourceplan") if isinstance(checkpoint.get("sourceplan"), dict) else {}
        payload = sourceplan.get("execution_target_payload") if isinstance(sourceplan.get("execution_target_payload"), dict) else {}
        if not payload:
            payload = checkpoint.get("worktree_execution_target_payload") if isinstance(checkpoint.get("worktree_execution_target_payload"), dict) else {}
        execution_target = str(sourceplan.get("execution_target") or checkpoint.get("worktree_execution_target") or payload.get("kind") or "local")
        return ToolExecutionContext(
            run_id=run_id,
            workspace_root=str(self.workspace_root),
            execution_target=execution_target,
            execution_target_payload=dict(payload),
            worktree_root=str(checkpoint.get("worktree_root") or ""),
            engine=self.engine,
        )

    def _remote_descriptor(self, run_id: str, checkpoint: dict[str, Any]) -> dict[str, str]:
        descriptor = _remote_target_descriptor(self._remote_context(run_id, checkpoint))
        if descriptor.get("kind") not in {"ssh", "container"}:
            raise PermissionError("remote promotion requires an SSH or container target")
        return descriptor

    def _run_remote_shell(self, run_id: str, checkpoint: dict[str, Any], script: str, *, timeout: float = 30.0, output_limit: int = 512000) -> dict[str, Any]:
        descriptor = self._remote_descriptor(run_id, checkpoint)
        if descriptor["kind"] == "ssh":
            command = [
                "ssh",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=7",
                "-o", "StrictHostKeyChecking=yes",
            ]
            if descriptor.get("known_hosts"):
                command.extend(["-o", f"UserKnownHostsFile={descriptor['known_hosts']}"])
            if descriptor.get("identity_file"):
                command.extend(["-i", descriptor["identity_file"]])
            if descriptor.get("port"):
                command.extend(["-p", descriptor["port"]])
            command.extend([descriptor["host"], script])
        else:
            command = ["docker", "exec", "-i", "-w", descriptor["base"], descriptor["container"], "sh", "-lc", script]
        try:
            process = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"remote promotion command timed out after {timeout:g}s") from exc
        stdout = (process.stdout or "")[:output_limit]
        stderr = (process.stderr or "")[:output_limit]
        return {
            "ok": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(process.stdout or "") > output_limit or len(process.stderr or "") > output_limit,
            "target_execution": f"remote_{descriptor['kind']}",
        }

    def _remote_worktree_exists(self, run_id: str, checkpoint: dict[str, Any]) -> bool:
        root = str(checkpoint.get("worktree_root") or "")
        if not root:
            return False
        result = self._run_remote_shell(
            run_id,
            checkpoint,
            f"test -d {_shell_quote(root)} && git -C {_shell_quote(root)} rev-parse --git-dir >/dev/null",
            timeout=15.0,
            output_limit=12000,
        )
        return bool(result.get("ok"))

    def _collect(self, run_id: str) -> tuple[dict[str, Any], list[PromotionPolicyResult]]:
        run = self._run(run_id)
        checkpoint = self._checkpoint(run)
        verification = dict(checkpoint.get("verification") or {})
        sourceplan = dict(checkpoint.get("sourceplan") or {})
        planner = dict(checkpoint.get("planner") or {})
        mutation_epoch = max(0, int(checkpoint.get("worktree_mutation_epoch") or 0))
        verification_epoch = int(verification.get("mutation_epoch") if verification.get("mutation_epoch") is not None else -1)
        chain = self.engine.store.verify_chain(run_id)
        events = self.engine.store.events(run_id, after=0, limit=100000)
        approvals = self.engine.store.approvals(run_id)
        worktree_value = str(checkpoint.get("worktree_root") or "")
        remote_target = self._is_remote_checkpoint(checkpoint)
        worktree_exists = self._remote_worktree_exists(run_id, checkpoint) if remote_target else bool(worktree_value and Path(worktree_value).expanduser().resolve().is_dir())
        planner_status = str(planner.get("status") or "")
        repair_cycles = max(0, int(planner.get("repair_cycles") or 0))
        max_repairs = max(0, int(planner.get("max_repair_cycles") or 3))
        failed_tool_events = [event for event in events if str(event.get("event_type") or "") == "agent.tool.failed"]
        passed_verifications = [event for event in events if str(event.get("event_type") or "") == "agent.verification.passed"]

        policies = [
            PromotionPolicyResult(
                "VALID_HASH_CHAIN", bool(chain.get("ok")),
                "AgentRun event chain is valid" if chain.get("ok") else "AgentRun event chain is invalid",
                {"event_count": int(chain.get("event_count") or len(events)), "head_hash": chain.get("head_hash")},
            ),
            PromotionPolicyResult(
                "VALID_WORKTREE", worktree_exists and bool(checkpoint.get("worktree_task_id")),
                "Bound isolated worktree exists" if worktree_exists else "Bound isolated worktree is missing",
                {"task_id": checkpoint.get("worktree_task_id"), "root": worktree_value, "branch": checkpoint.get("worktree_branch")},
            ),
            PromotionPolicyResult(
                "CURRENT_VERIFICATION",
                bool(verification.get("ok")) and not bool(verification.get("stale")) and verification_epoch == mutation_epoch,
                "Verification is current for the latest mutation epoch",
                {"ok": bool(verification.get("ok")), "stale": bool(verification.get("stale")), "verification_epoch": verification_epoch, "mutation_epoch": mutation_epoch},
            ),
            PromotionPolicyResult(
                "SOURCEPLAN_READY",
                bool(sourceplan.get("plan_id")) and str(sourceplan.get("status") or "draft") == "draft",
                "A SourcePlan draft is bound to this run",
                {"plan_id": sourceplan.get("plan_id"), "status": sourceplan.get("status")},
            ),
            PromotionPolicyResult(
                "NO_OPERATOR_TRANSLATION_REQUIRED",
                not bool(sourceplan.get("requires_operator_translation")) or remote_target,
                "SourcePlan operations are machine-bounded" if not sourceplan.get("requires_operator_translation") else (
                    "Remote SourcePlan translation is bounded by target-side Git promotion" if remote_target else "SourcePlan still requires operator translation"
                ),
                {"requires_operator_translation": bool(sourceplan.get("requires_operator_translation")), "remote_target": remote_target},
            ),
            PromotionPolicyResult(
                "REPAIR_BUDGET_VALID", repair_cycles <= max_repairs,
                "Repair activity remained within its governed budget",
                {"repair_cycles": repair_cycles, "max_repair_cycles": max_repairs},
            ),
            PromotionPolicyResult(
                "RUN_NOT_CANCELLED", not bool(run.get("cancel_requested")) and str(run.get("state") or "") != "cancelled",
                "Run has not been cancelled",
                {"state": run.get("state"), "cancel_requested": bool(run.get("cancel_requested"))},
            ),
            PromotionPolicyResult(
                "VERIFICATION_EVIDENCE_PRESENT", bool(passed_verifications),
                "At least one passing verification event is present",
                {"passing_verification_events": len(passed_verifications)},
            ),
        ]
        evidence = {
            "run_id": run_id,
            "session_id": run.get("session_id"),
            "objective": run.get("objective"),
            "state": run.get("state"),
            "provider": run.get("provider"),
            "model": run.get("model"),
            "planner_status": planner_status,
            "planner_turns": int(planner.get("turn") or 0),
            "repair_cycles": repair_cycles,
            "mutation_epoch": mutation_epoch,
            "verification": verification,
            "sourceplan": sourceplan,
            "worktree": {
                "task_id": checkpoint.get("worktree_task_id"),
                "root": worktree_value,
                "branch": checkpoint.get("worktree_branch"),
                "base_commit": checkpoint.get("worktree_base_commit"),
                "remote": remote_target,
                "execution_target": sourceplan.get("execution_target") or checkpoint.get("worktree_execution_target"),
                "target_execution": sourceplan.get("target_execution") or checkpoint.get("target_execution"),
            },
            "events": {
                "count": len(events),
                "failed_tool_events": len(failed_tool_events),
                "passing_verification_events": len(passed_verifications),
            },
            "approvals": {"count": len(approvals)},
            "hash_chain": chain,
        }
        return evidence, policies

    def evaluate(self, run_id: str, *, requested_by: str = "operator") -> dict[str, Any]:
        evidence, policies = self._collect(run_id)
        eligible = all(policy.passed for policy in policies)
        receipt_core = {
            "beast_object_type": "beast_agent_promotion_receipt",
            "version": self.VERSION,
            "receipt_id": f"promotion-{uuid.uuid4().hex[:20]}",
            "run_id": run_id,
            "created_at": _now(),
            "requested_by": str(requested_by or "operator"),
            "status": "eligible" if eligible else "blocked",
            "eligible": eligible,
            "policies": [policy.as_dict() for policy in policies],
            "evidence": evidence,
        }
        receipt = {**receipt_core, "receipt_digest": _digest(receipt_core)}
        approval = None
        if eligible:
            approval_request = {
                "request_id": f"promotion-approval-{uuid.uuid4().hex[:16]}",
                "kind": "sourceplan_promotion",
                "summary": "Approve creation of a commit candidate in the isolated AgentRun worktree.",
                "receipt_id": receipt["receipt_id"],
                "receipt_digest": receipt["receipt_digest"],
                "mutation_epoch": evidence["mutation_epoch"],
                "plan_id": evidence["sourceplan"].get("plan_id"),
                "capabilities": [{"id": "sourceplan.promote", "paths": []}],
                "requires_human_operator": True,
            }
            approval = self.engine.store.create_approval(run_id, approval_request)
            receipt["approval_id"] = approval.get("approval_id")
        self.engine.merge_checkpoint(run_id, {"promotion": receipt})
        self.engine.emit(run_id, "agent.promotion.evaluated", {
            "receipt_id": receipt["receipt_id"],
            "receipt_digest": receipt["receipt_digest"],
            "eligible": eligible,
            "approval_id": receipt.get("approval_id", ""),
            "failed_policies": [policy.policy_id for policy in policies if not policy.passed],
        })
        try:
            self.planning_integrations.sync_phase7_handoff(run_id, "agent.promotion.evaluated", {
                "receipt_id": receipt["receipt_id"],
                "receipt_digest": receipt["receipt_digest"],
                "eligible": eligible,
                "approval_id": receipt.get("approval_id", ""),
                "failed_policies": [policy.policy_id for policy in policies if not policy.passed],
            }, run=self.engine.store.get_run(run_id))
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase7_handoff_promotion",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.promotion.evaluated",
            })
        return {"ok": True, "eligible": eligible, "receipt": receipt, "approval": approval}

    def _validate_approval(self, run_id: str, approval_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
        approval = self.engine.store.get_approval(run_id, approval_id)
        if not approval or approval.get("status") != "approved":
            raise PermissionError("promotion requires a resolved operator approval")
        request = dict(approval.get("request") or {})
        resolution = dict(approval.get("resolution") or {})
        capabilities = request.get("capabilities") if isinstance(request.get("capabilities"), list) else []
        ids = {str(item.get("id") or "") for item in capabilities if isinstance(item, dict)}
        if request.get("kind") != "sourceplan_promotion" or "sourceplan.promote" not in ids:
            raise PermissionError("approval does not grant SourcePlan promotion")
        if str(request.get("receipt_digest") or "") != str(receipt.get("receipt_digest") or ""):
            raise PermissionError("approval is not bound to the current promotion receipt")
        operator = str(resolution.get("resolved_by") or resolution.get("operator") or resolution.get("actor") or "").strip()
        if not operator:
            raise PermissionError("promotion approval must identify the human operator")
        return {"approval": approval, "operator": operator}

    def _validate_final_approval(self, run_id: str, approval_id: str, candidate: dict[str, Any]) -> dict[str, Any]:
        approval = self.engine.store.get_approval(run_id, approval_id)
        if not approval or approval.get("status") != "approved":
            raise PermissionError("final apply requires a resolved operator approval")
        request = dict(approval.get("request") or {})
        resolution = dict(approval.get("resolution") or {})
        capabilities = request.get("capabilities") if isinstance(request.get("capabilities"), list) else []
        ids = {str(item.get("id") or "") for item in capabilities if isinstance(item, dict)}
        if request.get("kind") != "sourceplan_final_apply" or "sourceplan.finalize" not in ids:
            raise PermissionError("approval does not grant SourcePlan final apply")
        if str(request.get("candidate_digest") or "") != str(candidate.get("candidate_digest") or ""):
            raise PermissionError("approval is not bound to the current commit candidate")
        operator = str(resolution.get("resolved_by") or resolution.get("operator") or resolution.get("actor") or "").strip()
        if not operator:
            raise PermissionError("final apply approval must identify the human operator")
        return {"approval": approval, "operator": operator}

    def promote(self, run_id: str, *, approval_id: str, commit_message: str = "") -> dict[str, Any]:
        run = self._run(run_id)
        checkpoint = self._checkpoint(run)
        receipt = dict(checkpoint.get("promotion") or {})
        if not receipt or not receipt.get("eligible"):
            raise PermissionError("run has no eligible promotion receipt")
        # Re-evaluate facts without issuing a replacement approval. Any drift blocks.
        evidence, policies = self._collect(run_id)
        if not all(policy.passed for policy in policies):
            raise PermissionError("promotion evidence is no longer eligible")
        if int(receipt.get("evidence", {}).get("mutation_epoch") or -1) != int(evidence.get("mutation_epoch") or -2):
            raise PermissionError("promotion receipt is stale after worktree mutation")
        approval_state = self._validate_approval(run_id, approval_id, receipt)
        plan_id = str((checkpoint.get("sourceplan") or {}).get("plan_id") or "")
        message = str(commit_message or f"BEAST: promote verified SourcePlan {plan_id}").strip()
        if not message or len(message) > 240:
            raise ValueError("commit message must contain 1 to 240 characters")

        if self._is_remote_checkpoint(checkpoint):
            return self._promote_remote(run_id, checkpoint, receipt, approval_state, evidence, plan_id, message, approval_id)

        worktree = self._worktree_root(checkpoint)
        status = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain"], capture_output=True, text=True, timeout=15)
        if status.returncode != 0:
            raise RuntimeError(status.stderr.strip() or "unable to inspect worktree")
        if not status.stdout.strip():
            raise RuntimeError("worktree contains no changes to promote")
        subprocess.run(["git", "-C", str(worktree), "add", "--all"], check=True, capture_output=True, text=True, timeout=20)
        commit = subprocess.run(
            ["git", "-C", str(worktree), "-c", "user.name=BEAST Operator", "-c", "user.email=beast@localhost", "commit", "-m", message],
            capture_output=True, text=True, timeout=30,
        )
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or commit.stdout.strip() or "commit candidate creation failed")
        head = subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=10).stdout.strip()
        candidate_core = {
            "beast_object_type": "beast_agent_commit_candidate",
            "version": self.VERSION,
            "candidate_id": f"candidate-{uuid.uuid4().hex[:20]}",
            "run_id": run_id,
            "plan_id": plan_id,
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "approval_id": approval_id,
            "approved_by": approval_state["operator"],
            "worktree_task_id": checkpoint.get("worktree_task_id"),
            "branch": checkpoint.get("worktree_branch"),
            "commit": head,
            "commit_message": message,
            "mutation_epoch": evidence.get("mutation_epoch"),
            "created_at": _now(),
            "status": "commit_candidate",
            "applied_to_operator_workspace": False,
        }
        candidate = {**candidate_core, "candidate_digest": _digest(candidate_core)}
        updated_receipt = {**receipt, "status": "promoted", "candidate_id": candidate["candidate_id"], "commit": head}
        self.engine.merge_checkpoint(run_id, {"promotion": updated_receipt, "commit_candidate": candidate})
        self.engine.emit(run_id, "agent.promotion.committed", candidate)
        try:
            self.planning_integrations.sync_phase7_handoff(run_id, "agent.promotion.committed", candidate, run=self.engine.store.get_run(run_id))
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase7_handoff_promotion",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.promotion.committed",
            })
        return {"ok": True, "candidate": candidate, "receipt": updated_receipt}

    def _collect_final_apply(self, run_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], list[PromotionPolicyResult]]:
        run = self._run(run_id)
        checkpoint = self._checkpoint(run)
        candidate = dict(checkpoint.get("commit_candidate") or {})
        receipt = dict(checkpoint.get("promotion") or {})
        evidence, policies = self._collect(run_id)
        candidate_ready = bool(candidate.get("candidate_digest") and candidate.get("commit"))
        remote_candidate = str(candidate.get("target_execution") or "").startswith("remote_")
        promoted = str(receipt.get("status") or "") in {"promoted", "remote_promoted"}
        final_policies = [
            PromotionPolicyResult(
                "PROMOTION_RECEIPT_READY",
                bool(receipt.get("eligible")) and promoted,
                "Promotion receipt has an approved commit candidate" if promoted else "Promotion receipt has not produced a commit candidate",
                {"receipt_id": receipt.get("receipt_id"), "status": receipt.get("status")},
            ),
            PromotionPolicyResult(
                "COMMIT_CANDIDATE_READY",
                candidate_ready,
                "Commit candidate is present" if candidate_ready else "Commit candidate is missing",
                {"candidate_id": candidate.get("candidate_id"), "commit": candidate.get("commit")},
            ),
            PromotionPolicyResult(
                "REMOTE_TARGET_CANDIDATE",
                remote_candidate,
                "Commit candidate belongs to a remote target" if remote_candidate else "Final target-side apply requires a remote commit candidate",
                {"target_execution": candidate.get("target_execution")},
            ),
            *policies,
        ]
        return candidate, receipt, evidence, final_policies

    def evaluate_final_apply(self, run_id: str, *, requested_by: str = "operator") -> dict[str, Any]:
        candidate, _receipt, evidence, final_policies = self._collect_final_apply(run_id)
        eligible = all(policy.passed for policy in final_policies)
        receipt_core = {
            "beast_object_type": "beast_agent_final_apply_receipt",
            "version": self.VERSION,
            "receipt_id": f"final-apply-{uuid.uuid4().hex[:20]}",
            "run_id": run_id,
            "created_at": _now(),
            "requested_by": str(requested_by or "operator"),
            "status": "eligible" if eligible else "blocked",
            "eligible": eligible,
            "policies": [policy.as_dict() for policy in final_policies],
            "evidence": evidence,
            "candidate": candidate,
        }
        final_receipt = {**receipt_core, "receipt_digest": _digest(receipt_core)}
        approval = None
        if eligible:
            approval_request = {
                "request_id": f"final-apply-approval-{uuid.uuid4().hex[:16]}",
                "kind": "sourceplan_final_apply",
                "summary": "Approve fast-forwarding the target workspace to the verified remote commit candidate.",
                "receipt_id": final_receipt["receipt_id"],
                "receipt_digest": final_receipt["receipt_digest"],
                "candidate_id": candidate.get("candidate_id"),
                "candidate_digest": candidate.get("candidate_digest"),
                "commit": candidate.get("commit"),
                "capabilities": [{"id": "sourceplan.finalize", "paths": []}],
                "requires_human_operator": True,
            }
            approval = self.engine.store.create_approval(run_id, approval_request)
            final_receipt["approval_id"] = approval.get("approval_id")
        self.engine.merge_checkpoint(run_id, {"final_apply": final_receipt})
        self.engine.emit(run_id, "agent.promotion.final_apply.evaluated", {
            "receipt_id": final_receipt["receipt_id"],
            "receipt_digest": final_receipt["receipt_digest"],
            "eligible": eligible,
            "approval_id": final_receipt.get("approval_id", ""),
            "candidate_id": candidate.get("candidate_id", ""),
            "failed_policies": [policy.policy_id for policy in final_policies if not policy.passed],
        })
        return {"ok": True, "eligible": eligible, "receipt": final_receipt, "approval": approval}

    def finalize(self, run_id: str, *, approval_id: str, target_branch: str = "") -> dict[str, Any]:
        run = self._run(run_id)
        checkpoint = self._checkpoint(run)
        final_receipt = dict(checkpoint.get("final_apply") or {})
        candidate = dict(checkpoint.get("commit_candidate") or {})
        if not final_receipt or not final_receipt.get("eligible"):
            raise PermissionError("run has no eligible final apply receipt")
        if not candidate.get("candidate_digest") or not candidate.get("commit"):
            raise PermissionError("run has no commit candidate to finalize")
        current_candidate, _promotion_receipt, _evidence, final_policies = self._collect_final_apply(run_id)
        if not all(policy.passed for policy in final_policies):
            raise PermissionError("final apply evidence is no longer eligible")
        if str(current_candidate.get("candidate_digest") or "") != str(candidate.get("candidate_digest") or ""):
            raise PermissionError("final apply evidence is stale after commit candidate drift")
        if str(final_receipt.get("candidate", {}).get("candidate_digest") or "") != str(candidate.get("candidate_digest") or ""):
            raise PermissionError("final apply receipt is stale after commit candidate drift")
        approval_state = self._validate_final_approval(run_id, approval_id, candidate)
        if not str(candidate.get("target_execution") or "").startswith("remote_"):
            raise PermissionError("target-side final apply requires a remote commit candidate")
        return self._finalize_remote(run_id, checkpoint, final_receipt, candidate, approval_state, approval_id, target_branch=target_branch)

    def _finalize_remote(
        self,
        run_id: str,
        checkpoint: dict[str, Any],
        final_receipt: dict[str, Any],
        candidate: dict[str, Any],
        approval_state: dict[str, Any],
        approval_id: str,
        *,
        target_branch: str = "",
    ) -> dict[str, Any]:
        descriptor = self._remote_descriptor(run_id, checkpoint)
        base = descriptor.get("base") or ""
        commit = str(candidate.get("commit") or "").strip()
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("commit candidate must be a full 40-character SHA")
        branch = str(target_branch or "").strip()
        if branch and not re.fullmatch(r"[A-Za-z0-9._/\-]{1,160}", branch):
            raise ValueError("target branch contains unsupported characters")
        run_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", run_id).strip("-._")[:80] or "run"
        checkout = f"git checkout {_shell_quote(branch)} && " if branch else ""
        script = (
            f"cd {_shell_quote(base)} && "
            "git rev-parse --git-dir >/dev/null && "
            f"git cat-file -e {_shell_quote(commit + '^{commit}')} && "
            f"{checkout}"
            "test -z \"$(git status --porcelain)\" && "
            "before=$(git rev-parse HEAD) && "
            "active_branch=$(git rev-parse --abbrev-ref HEAD) && "
            f"rollback_ref=refs/beast/rollback/{run_slug}-$(date +%s) && "
            "git update-ref \"$rollback_ref\" \"$before\" && "
            f"git merge --ff-only {_shell_quote(commit)} && "
            "after=$(git rev-parse HEAD) && "
            "printf 'BEAST_FINAL_APPLY_BEFORE\\n%s\\n' \"$before\" && "
            "printf 'BEAST_FINAL_APPLY_AFTER\\n%s\\n' \"$after\" && "
            "printf 'BEAST_FINAL_APPLY_BRANCH\\n%s\\n' \"$active_branch\" && "
            "printf 'BEAST_FINAL_APPLY_ROLLBACK\\n%s\\n' \"$rollback_ref\""
        )
        result = self._run_remote_shell(run_id, checkpoint, script, timeout=45.0, output_limit=128000)
        if not result.get("ok"):
            raise RuntimeError(result.get("stderr") or result.get("stdout") or f"remote final apply failed with exit {result.get('returncode')}")
        stdout = str(result.get("stdout") or "")
        before = _marker_section(stdout, "BEAST_FINAL_APPLY_BEFORE", "BEAST_FINAL_APPLY_AFTER").splitlines()[0].strip()
        after = _marker_section(stdout, "BEAST_FINAL_APPLY_AFTER", "BEAST_FINAL_APPLY_BRANCH").splitlines()[0].strip()
        applied_branch = _marker_section(stdout, "BEAST_FINAL_APPLY_BRANCH", "BEAST_FINAL_APPLY_ROLLBACK").splitlines()[0].strip()
        rollback_ref = _marker_section(stdout, "BEAST_FINAL_APPLY_ROLLBACK").splitlines()[0].strip()
        final_core = {
            "beast_object_type": "beast_agent_final_apply_result",
            "version": self.VERSION,
            "final_apply_id": f"finalized-{uuid.uuid4().hex[:20]}",
            "run_id": run_id,
            "candidate_id": candidate.get("candidate_id"),
            "candidate_digest": candidate.get("candidate_digest"),
            "commit": commit,
            "approval_id": approval_id,
            "approved_by": approval_state["operator"],
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": str((checkpoint.get("sourceplan") or {}).get("execution_target") or checkpoint.get("worktree_execution_target") or descriptor["kind"]),
            "execution_target_payload": dict((checkpoint.get("sourceplan") or {}).get("execution_target_payload") or checkpoint.get("worktree_execution_target_payload") or {}),
            "target_branch": applied_branch,
            "before": before,
            "after": after,
            "rollback_ref": rollback_ref,
            "applied_to_operator_workspace": False,
            "applied_to_remote_target": True,
            "created_at": _now(),
            "status": "finalized",
        }
        final_result = {**final_core, "final_apply_digest": _digest(final_core)}
        updated_candidate = {**candidate, "status": "remote_finalized", "applied_to_remote_target": True, "final_apply_id": final_result["final_apply_id"], "target_branch": applied_branch, "rollback_ref": rollback_ref}
        updated_receipt = {**final_receipt, "status": "finalized", "final_apply_id": final_result["final_apply_id"], "commit": commit, "rollback_ref": rollback_ref}
        self.engine.merge_checkpoint(run_id, {"final_apply": updated_receipt, "commit_candidate": updated_candidate, "final_apply_result": final_result})
        self.engine.emit(run_id, "agent.promotion.finalized", final_result)
        return {"ok": True, "final_apply": final_result, "candidate": updated_candidate, "receipt": updated_receipt}

    def _promote_remote(
        self,
        run_id: str,
        checkpoint: dict[str, Any],
        receipt: dict[str, Any],
        approval_state: dict[str, Any],
        evidence: dict[str, Any],
        plan_id: str,
        message: str,
        approval_id: str,
    ) -> dict[str, Any]:
        root = str(checkpoint.get("worktree_root") or "")
        if not root:
            raise PermissionError("remote promotion requires a target-side worktree")
        descriptor = self._remote_descriptor(run_id, checkpoint)
        script = (
            f"cd {_shell_quote(root)} && "
            "status=$(git status --porcelain) && "
            "test -n \"$status\" && "
            "git add --all && "
            f"git -c user.name={_shell_quote('BEAST Operator')} -c user.email={_shell_quote('beast@localhost')} commit -m {_shell_quote(message)} >/tmp/beast-remote-promotion-commit.out 2>/tmp/beast-remote-promotion-commit.err && "
            "printf 'BEAST_REMOTE_PROMOTION_STATUS\\n' && printf '%s\\n' \"$status\" && "
            "printf 'BEAST_REMOTE_PROMOTION_HEAD\\n' && git rev-parse HEAD && "
            "printf 'BEAST_REMOTE_PROMOTION_BRANCH\\n' && git rev-parse --abbrev-ref HEAD && "
            "printf 'BEAST_REMOTE_PROMOTION_COMMIT_OUT\\n' && tail -c 12000 /tmp/beast-remote-promotion-commit.out"
        )
        result = self._run_remote_shell(run_id, checkpoint, script, timeout=45.0, output_limit=128000)
        if not result.get("ok"):
            raise RuntimeError(result.get("stderr") or result.get("stdout") or f"remote promotion failed with exit {result.get('returncode')}")
        stdout = str(result.get("stdout") or "")
        head = _marker_section(stdout, "BEAST_REMOTE_PROMOTION_HEAD", "BEAST_REMOTE_PROMOTION_BRANCH").splitlines()[0].strip()
        branch = _marker_section(stdout, "BEAST_REMOTE_PROMOTION_BRANCH", "BEAST_REMOTE_PROMOTION_COMMIT_OUT").splitlines()[0].strip()
        status_before = _marker_section(stdout, "BEAST_REMOTE_PROMOTION_STATUS", "BEAST_REMOTE_PROMOTION_HEAD")
        if not head:
            raise RuntimeError("remote promotion did not return a commit head")
        candidate_core = {
            "beast_object_type": "beast_agent_commit_candidate",
            "version": self.VERSION,
            "candidate_id": f"candidate-{uuid.uuid4().hex[:20]}",
            "run_id": run_id,
            "plan_id": plan_id,
            "receipt_id": receipt.get("receipt_id"),
            "receipt_digest": receipt.get("receipt_digest"),
            "approval_id": approval_id,
            "approved_by": approval_state["operator"],
            "worktree_task_id": checkpoint.get("worktree_task_id"),
            "branch": branch or checkpoint.get("worktree_branch"),
            "commit": head,
            "commit_message": message,
            "mutation_epoch": evidence.get("mutation_epoch"),
            "created_at": _now(),
            "status": "remote_commit_candidate",
            "applied_to_operator_workspace": False,
            "applied_to_remote_target": False,
            "remote_worktree_root": root,
            "target_execution": f"remote_{descriptor['kind']}",
            "execution_target": str((checkpoint.get("sourceplan") or {}).get("execution_target") or checkpoint.get("worktree_execution_target") or descriptor["kind"]),
            "execution_target_payload": dict((checkpoint.get("sourceplan") or {}).get("execution_target_payload") or checkpoint.get("worktree_execution_target_payload") or {}),
            "promotion_status_before": status_before[-12000:],
        }
        candidate = {**candidate_core, "candidate_digest": _digest(candidate_core)}
        updated_receipt = {
            **receipt,
            "status": "remote_promoted",
            "candidate_id": candidate["candidate_id"],
            "commit": head,
            "target_execution": candidate["target_execution"],
        }
        self.engine.merge_checkpoint(run_id, {"promotion": updated_receipt, "commit_candidate": candidate})
        self.engine.emit(run_id, "agent.promotion.committed", candidate)
        try:
            self.planning_integrations.sync_phase7_handoff(run_id, "agent.promotion.committed", candidate, run=self.engine.store.get_run(run_id))
        except Exception as exc:
            self.engine.emit(run_id, "agent.plan.integration.failed", {
                "integration_id": "phase7_handoff_promotion",
                "reason": f"{type(exc).__name__}: {exc}",
                "event_type": "agent.promotion.committed",
            })
        return {"ok": True, "candidate": candidate, "receipt": updated_receipt}

    def state(self, run_id: str) -> dict[str, Any]:
        run = self._run(run_id)
        checkpoint = self._checkpoint(run)
        return {
            "ok": True,
            "run_id": run_id,
            "promotion": dict(checkpoint.get("promotion") or {}),
            "commit_candidate": dict(checkpoint.get("commit_candidate") or {}),
        }
