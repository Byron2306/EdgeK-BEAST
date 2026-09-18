"""Bridge the live AgentRun planner to the canonical Phase 4 approval stack.

The Phase 4 approval subsystem predates its integration with the coding-agent
loop. This bridge deliberately reuses those contracts instead of inventing a
second approval dialect. It is opt-in per run while Phase 4 is being proven.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from app.kernel.agents.tool_models import ToolEffect, ToolSpec
from app.kernel.approvals.digests import canonicalize
from app.kernel.approvals.capability_runtime import CapabilityConsumptionStore, ExactStepResumeRuntime
from app.kernel.approvals import (
    ApprovalContractFactory,
    ApprovalRiskClassifier,
    ApprovalRiskPolicy,
    ApprovalScopeEngine,
    DurableApprovalCardStore,
    DurableApprovalStore,
    PermissionModeEngine,
    RequestBoundCapabilityIssuer,
    RevocationPolicyStore,
    RichApprovalEnvelopeBuilder,
)


def durable_approvals_enabled(run: Mapping[str, Any]) -> bool:
    request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
    return bool(request.get("durable_approvals") or request.get("phase4_durable_approvals"))


def _workspace_id(root: str | Path) -> str:
    value = str(Path(root).expanduser().resolve())
    return "workspace:sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tool_class(spec: ToolSpec) -> str:
    # worktree.bind creates the isolation boundary itself. Treating it as an
    # already-isolated mutation would make the prerequisite circular.
    if spec.tool_id == "worktree.bind":
        return "CONSEQUENTIAL_EXECUTION"
    if spec.effect is ToolEffect.READ:
        return "SENSITIVE_READ" if spec.requires_approval else "READ_ONLY"
    if spec.effect is ToolEffect.ISOLATED_MUTATION:
        return "ISOLATED_MUTATION"
    if spec.effect is ToolEffect.EXECUTION:
        return "CONSEQUENTIAL_EXECUTION"
    return "NEVER_MODEL_AUTHORIZED"


def _policy_generation(root: Path) -> str:
    current = RevocationPolicyStore(root).current_policy_generation()
    if isinstance(current, Mapping) and str(current.get("generation_id") or "").strip():
        return str(current["generation_id"])
    return "policy:phase4-runtime-v1"


def _permission_mode(run: Mapping[str, Any]) -> str:
    request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
    # GUIDED preserves Phase 3's proven semantics: ordinary reads stay
    # automatic while isolated mutation and consequential execution are gated.
    return str(request.get("permission_mode") or "GUIDED").strip().upper()


def _affected_resources(arguments: Mapping[str, Any]) -> list[str]:
    resources: list[str] = []
    for key in ("path", "target_path", "file", "source", "destination"):
        value = str(arguments.get(key) or "").strip()
        if value and value not in resources:
            resources.append(value)
    return resources


def _commands(arguments: Mapping[str, Any]) -> list[str]:
    command = arguments.get("command")
    if isinstance(command, list) and command and all(isinstance(item, str) for item in command):
        return [" ".join(command)]
    if isinstance(command, str) and command.strip():
        return [command.strip()]
    return []


def _allowed_files(run: Mapping[str, Any]) -> list[str]:
    request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
    values = request.get("allowed_files")
    if not isinstance(values, list):
        values = request.get("context_files") if isinstance(request.get("context_files"), list) else []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))


def _allowed_commands(run: Mapping[str, Any], spec: ToolSpec) -> list[str]:
    request = run.get("request") if isinstance(run.get("request"), Mapping) else {}
    values = request.get("allowed_commands") if isinstance(request.get("allowed_commands"), list) else []
    commands = list(dict.fromkeys(str(item).strip() for item in values if str(item).strip()))
    if spec.tool_id == "worktree.bind" and "worktree.bind" not in commands:
        commands.append("worktree.bind")
    return commands


def _command_identity(arguments: Mapping[str, Any]) -> str:
    command = arguments.get("command")
    if isinstance(command, list) and command and all(isinstance(item, str) for item in command):
        return " ".join(command)
    if isinstance(command, str):
        return command.strip()
    return ""


class DurableAgentApprovalRuntime:
    """Create and resolve Phase 4 authority for one live AgentRun tool step."""

    def __init__(self, workspace_root: str | Path):
        self.root = Path(workspace_root).expanduser().resolve()
        self.contracts = ApprovalContractFactory()
        self.classifier = ApprovalRiskClassifier()
        self.envelopes = RichApprovalEnvelopeBuilder()
        self.cards = DurableApprovalCardStore(self.root)
        self.store = DurableApprovalStore(self.root)
        self.scopes = ApprovalScopeEngine()
        self.issuer = RequestBoundCapabilityIssuer()
        self.modes = PermissionModeEngine()
        self.revocations = RevocationPolicyStore(self.root)

    def evaluate_for_tool(
        self,
        *,
        run: Mapping[str, Any],
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        execution_target: str,
        worktree_bound: bool,
    ) -> dict[str, Any]:
        root = Path(str(run.get("root_path") or self.root)).expanduser().resolve()
        resources = _affected_resources(arguments)
        mode = _permission_mode(run)
        generation = _policy_generation(root)
        action = {
            "tool_id": spec.tool_id,
            "tool_version": spec.version,
            "tool_class": _tool_class(spec),
            "workspace_id": _workspace_id(root),
            "execution_target": str(execution_target or "local"),
            "permission_mode": mode,
            "read_only": spec.effect is ToolEffect.READ,
            "trusted_workspace": True,
            "worktree_bound": bool(worktree_bound),
            "affected_resources": resources,
            "data_egress": [],
            "network_domains": [],
            "allowed_files": _allowed_files(run),
            "allowed_commands": _allowed_commands(run, spec),
            "budget": dict(run.get("budget") or {}),
            "evidence_required": True,
            "promotion_without_approval": False,
            "unrestricted_network": False,
        }
        policy = ApprovalRiskPolicy(
            generation=generation,
            trusted_targets=("local", "ssh", "container", "devcontainer"),
        )
        classification = self.classifier.classify(action, policy=policy)
        mode_decision = self.modes.evaluate(action, policy=policy)

        reasons = list(mode_decision.get("reasons") or [])
        denied = bool(mode_decision.get("denied"))
        if mode == "BOUNDED_AUTONOMY" and bool(mode_decision.get("auto_authorized")):
            if spec.effect is ToolEffect.ISOLATED_MUTATION and spec.tool_id != "worktree.bind":
                allowed = set(_allowed_files(run))
                if not resources or any(path not in allowed for path in resources):
                    denied = True
                    reasons.append("bounded autonomy mutation path is outside the explicit file allowlist")
            if spec.effect is ToolEffect.EXECUTION:
                identity = _command_identity(arguments)
                allowed_commands = set(_allowed_commands(run, spec))
                if not identity or identity not in allowed_commands:
                    denied = True
                    reasons.append("bounded autonomy command is outside the explicit command allowlist")
        return {
            "action": action,
            "policy": policy,
            "classification": classification,
            "mode_profile": self.modes.profile(mode),
            "mode_decision": {
                **mode_decision,
                "denied": denied,
                "auto_authorized": bool(mode_decision.get("auto_authorized")) and not denied,
                "reasons": list(dict.fromkeys(reasons)),
            },
            "requires_approval": bool(mode_decision.get("may_create_approval")) and not denied,
            "auto_authorized": bool(mode_decision.get("auto_authorized")) and not denied,
            "denied": denied,
        }

    def create_for_tool(
        self,
        *,
        run: Mapping[str, Any],
        step_id: str,
        approval_id: str,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        execution_target: str,
        worktree_bound: bool,
        budget_impact: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        evaluation = self.evaluate_for_tool(
            run=run,
            spec=spec,
            arguments=arguments,
            execution_target=execution_target,
            worktree_bound=worktree_bound,
        )
        if evaluation["denied"]:
            raise PermissionError(
                "; ".join(str(item) for item in evaluation["mode_decision"].get("reasons") or [])
                or f"{spec.tool_id} denied by Phase 4 permission mode"
            )
        if not evaluation["requires_approval"]:
            raise PermissionError(
                f"{spec.tool_id} does not require a durable approval under mode {_permission_mode(run)}"
            )
        root = Path(str(run.get("root_path") or self.root)).expanduser().resolve()
        resources = _affected_resources(arguments)
        mode = _permission_mode(run)
        generation = str(evaluation["classification"]["policy_generation"])
        classification = evaluation["classification"]
        mode_decision = evaluation["mode_decision"]
        request_payload = run.get("request") if isinstance(run.get("request"), Mapping) else {}
        request = {
            "approval_id": approval_id,
            "run_id": str(run.get("run_id") or ""),
            "step_id": str(step_id),
            "agent_id": "agent:beast-coding-agent",
            "model_id": str(run.get("model") or "model:unknown"),
            "provider_id": str(run.get("provider") or "provider:unknown"),
            "tool_id": spec.tool_id,
            "tool_version": spec.version,
            "arguments": dict(arguments),
            "workspace_id": action["workspace_id"],
            "execution_target": action["execution_target"],
            "affected_resources": resources,
            "data_egress": [],
            "expected_side_effects": [
                "Execute only this bounded tool step under the existing AgentRun authority boundary."
            ],
            "risk_class": classification["risk_class"],
            "reason": f"AgentRun requires {spec.tool_id} to advance the current objective.",
            "budget_impact": dict(budget_impact or {"tool_calls": 1}),
            "evidence_policy": {"level": str(spec.evidence_level or "summary")},
            "requested_scope": "ONCE",
            "permission_mode": mode,
            "policy_generation": generation,
            "expiry_seconds": max(30, min(int(request_payload.get("approval_timeout_seconds") or 900), 86400)),
        }
        envelope = self.envelopes.build({
            "classification": classification,
            "request": request,
            "affected_files": resources,
            "commands": _commands(arguments),
            "data_egress": [],
            "expected_side_effects": request["expected_side_effects"],
            "operator_summary": request["reason"],
        })
        canonical_request = envelope["approval_request"]
        durable = self.store.create(canonical_request)
        card = self.cards.create(envelope)
        return {
            "request": canonical_request,
            "classification": classification,
            "mode_profile": evaluation["mode_profile"],
            "mode_decision": mode_decision,
            "envelope": envelope,
            "durable_approval": durable,
            "card": card,
        }

    def resolve(
        self,
        *,
        approval_id: str,
        resolution: Mapping[str, Any],
        run: Mapping[str, Any],
    ) -> dict[str, Any]:
        card = self.cards.get(approval_id)
        envelope = card.get("envelope") if isinstance(card.get("envelope"), Mapping) else {}
        request = envelope.get("approval_request") if isinstance(envelope.get("approval_request"), Mapping) else {}
        classification = envelope.get("classification") if isinstance(envelope.get("classification"), Mapping) else {}
        if str(request.get("run_id") or "") != str(run.get("run_id") or ""):
            raise ValueError("approval card does not belong to this AgentRun")

        approved = bool(resolution.get("approved"))
        requested_decision = str(resolution.get("decision") or "").strip().upper()
        if not requested_decision:
            requested_decision = "APPROVE" if approved else "REJECT"
        scope = str(resolution.get("scope") or "ONCE").strip().upper() if requested_decision in {"APPROVE", "EDIT_AND_APPROVE"} else None
        decision_payload: dict[str, Any] = {
            "operator_id": str(resolution.get("operator_id") or "operator:beast-ide"),
            "decision": requested_decision,
            "reason": str(resolution.get("reason") or ""),
            "policy_generation": str(request.get("policy_generation") or ""),
        }
        if scope:
            decision_payload["scope"] = scope
        if requested_decision == "EDIT_AND_APPROVE":
            decision_payload["edited_arguments"] = dict(resolution.get("edited_arguments") or {})
            decision_payload["edited_resources"] = list(resolution.get("edited_resources") or [])

        decision = self.contracts.create_decision(request, decision_payload)
        updated_card = self.cards.decide(approval_id, decision)

        state_map = {
            "APPROVE": "APPROVED",
            "EDIT_AND_APPROVE": "EDITED_AND_APPROVED",
            "REJECT": "REJECTED",
            "REQUEST_REPLAN": "REJECTED",
            "PERMANENTLY_DENY": "REJECTED",
        }
        durable = self.store.transition(
            approval_id,
            to_state=state_map[requested_decision],
            actor=str(decision_payload["operator_id"]),
            reason=str(decision_payload.get("reason") or requested_decision.lower()),
            decision=decision,
        )

        result: dict[str, Any] = {
            "request": request,
            "classification": classification,
            "envelope": envelope,
            "card": updated_card,
            "decision": decision,
            "durable_approval": durable,
            "approved": requested_decision in {"APPROVE", "EDIT_AND_APPROVE"},
        }
        if not result["approved"]:
            return result

        grant = self.scopes.create_grant({
            "root_path": str(self.root),
            "envelope": envelope,
            "decision": decision,
        })
        match = self.scopes.evaluate({
            "root_path": str(self.root),
            "grant": grant,
            "candidate_request": request,
            "candidate_classification": classification,
        })
        capability = self.issuer.issue({
            "root_path": str(self.root),
            "classification": classification,
            "request": request,
            "decision": decision,
            "grant": grant,
            "scope_match": match,
        })
        result.update({
            "scope_grant": grant,
            "scope_match": match,
            "capability": capability,
        })
        return result


    def validate_consumed_call(
        self,
        *,
        run: Mapping[str, Any],
        approval_id: str,
        spec: ToolSpec,
        arguments: Mapping[str, Any],
        execution_target: str,
    ) -> dict[str, Any]:
        checkpoint = run.get("checkpoint") if isinstance(run.get("checkpoint"), Mapping) else {}
        resume = checkpoint.get("approval_resume") if isinstance(checkpoint.get("approval_resume"), Mapping) else {}
        if str(resume.get("status") or "") != "READY_FOR_EXACT_TOOL_EXECUTION":
            raise PermissionError("Phase 4 capability is not ready for exact tool execution")
        checks = {
            "approval_id": (resume.get("approval_id"), approval_id),
            "tool_id": (resume.get("tool_id"), spec.tool_id),
            "tool_version": (resume.get("tool_version"), spec.version),
            "execution_target": (resume.get("execution_target"), str(execution_target or "local")),
        }
        for field, (left, right) in checks.items():
            if str(left or "") != str(right or ""):
                raise PermissionError(f"Phase 4 consumed capability {field} mismatch")

        card = self.cards.get(approval_id)
        envelope = card.get("envelope") if isinstance(card.get("envelope"), Mapping) else {}
        request = envelope.get("approval_request") if isinstance(envelope.get("approval_request"), Mapping) else {}
        decision = card.get("decision") if isinstance(card.get("decision"), Mapping) else {}
        expected_arguments = request.get("arguments") if isinstance(request.get("arguments"), Mapping) else {}
        if str(decision.get("decision") or "") == "EDIT_AND_APPROVE":
            expected_arguments = decision.get("edited_arguments") if isinstance(decision.get("edited_arguments"), Mapping) else {}
        if canonicalize(dict(arguments)) != canonicalize(dict(expected_arguments)):
            raise PermissionError("Phase 4 consumed capability arguments do not match the approved call")

        capability_id = str(resume.get("capability_id") or "")
        if not capability_id:
            raise PermissionError("Phase 4 consumed capability id is missing")
        consumption = CapabilityConsumptionStore(self.root).get(capability_id)
        if not consumption or str(consumption.get("status") or "") != "RESUMED":
            raise PermissionError("Phase 4 capability has no durable RESUMED consumption receipt")
        receipt = consumption.get("receipt") if isinstance(consumption.get("receipt"), Mapping) else {}
        if not ExactStepResumeRuntime.verify_receipt(receipt):
            raise PermissionError("Phase 4 capability consumption receipt is invalid or tampered")
        if str(receipt.get("approval_id") or "") != approval_id:
            raise PermissionError("Phase 4 consumption receipt approval binding mismatch")
        if str(receipt.get("request_digest") or "") != str(request.get("request_digest") or ""):
            raise PermissionError("Phase 4 consumption receipt request binding mismatch")
        return {
            "card": card,
            "request": request,
            "decision": decision,
            "consumption": consumption,
            "receipt": receipt,
        }

    def consume_and_resume(self, *, capability: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        return ExactStepResumeRuntime(self.root).consume_and_resume(
            capability=capability,
            request=request,
        )
