from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .classifier import (
    ApprovalRequirement,
    ApprovalRiskClassifier,
    ApprovalRiskPolicy,
    ToolClass,
)
from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .models import PermissionMode

MODE_ENGINE_VERSION = "4.8"
MODE_PROFILE_OBJECT_TYPE = "beast_permission_mode_profile"
MODE_DECISION_OBJECT_TYPE = "beast_permission_mode_decision"


@dataclass(frozen=True)
class PermissionModeProfile:
    mode: PermissionMode
    automatic_read_only: bool
    automatic_isolated_mutation: bool
    automatic_consequential_execution: bool
    mutation_allowed: bool
    execution_allowed: bool
    agent_enabled: bool
    worktree_required_for_mutation: bool = True
    file_allowlist_required: bool = True
    command_allowlist_required: bool = True
    cost_budget_required: bool = True
    turn_budget_required: bool = True
    network_restricted: bool = True
    sourceplan_promotion_approval_required: bool = True
    evidence_required: bool = True
    sensitive_access_requires_explicit_approval: bool = True
    version: str = MODE_ENGINE_VERSION
    beast_object_type: str = MODE_PROFILE_OBJECT_TYPE
    profile_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"profile_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["profile_digest"] = self.profile_digest or sha256_digest(self.semantic_dict())
        return payload


@dataclass(frozen=True)
class PermissionModeDecision:
    mode: PermissionMode
    tool_id: str
    tool_version: str
    tool_class: ToolClass
    policy_generation: str
    classification_digest: str
    requirement: ApprovalRequirement
    agent_enabled: bool
    may_create_approval: bool
    may_issue_capability: bool
    auto_authorized: bool
    denied: bool
    immutable_boundaries: Mapping[str, bool]
    reasons: tuple[str, ...] = field(default_factory=tuple)
    version: str = MODE_ENGINE_VERSION
    beast_object_type: str = MODE_DECISION_OBJECT_TYPE
    decision_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"decision_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["decision_digest"] = self.decision_digest or sha256_digest(self.semantic_dict())
        return payload


class PermissionModeEngine:
    """Turn BEAST permission modes into enforceable, fail-closed policy profiles.

    The engine does not persist approvals, issue capabilities, consume authority,
    resume runs, or execute tools. It produces a policy-bound decision that later
    approval and tool-runtime layers must verify.
    """

    _PROFILES: dict[PermissionMode, PermissionModeProfile] = {
        PermissionMode.REVIEW: PermissionModeProfile(
            mode=PermissionMode.REVIEW,
            automatic_read_only=False,
            automatic_isolated_mutation=False,
            automatic_consequential_execution=False,
            mutation_allowed=True,
            execution_allowed=True,
            agent_enabled=True,
        ),
        PermissionMode.GUIDED: PermissionModeProfile(
            mode=PermissionMode.GUIDED,
            automatic_read_only=True,
            automatic_isolated_mutation=False,
            automatic_consequential_execution=False,
            mutation_allowed=True,
            execution_allowed=True,
            agent_enabled=True,
        ),
        PermissionMode.BOUNDED_AUTONOMY: PermissionModeProfile(
            mode=PermissionMode.BOUNDED_AUTONOMY,
            automatic_read_only=True,
            automatic_isolated_mutation=True,
            automatic_consequential_execution=True,
            mutation_allowed=True,
            execution_allowed=True,
            agent_enabled=True,
        ),
        PermissionMode.OBSERVE_ONLY: PermissionModeProfile(
            mode=PermissionMode.OBSERVE_ONLY,
            automatic_read_only=True,
            automatic_isolated_mutation=False,
            automatic_consequential_execution=False,
            mutation_allowed=False,
            execution_allowed=False,
            agent_enabled=True,
        ),
        PermissionMode.LOCKED: PermissionModeProfile(
            mode=PermissionMode.LOCKED,
            automatic_read_only=False,
            automatic_isolated_mutation=False,
            automatic_consequential_execution=False,
            mutation_allowed=False,
            execution_allowed=False,
            agent_enabled=False,
        ),
    }

    def profile(self, mode: PermissionMode | str) -> dict[str, Any]:
        normalized = mode if isinstance(mode, PermissionMode) else PermissionMode(str(mode).upper())
        return self._PROFILES[normalized].to_dict()

    def verify_profile(self, profile: Mapping[str, Any]) -> bool:
        if profile.get("beast_object_type") != MODE_PROFILE_OBJECT_TYPE:
            return False
        if str(profile.get("version") or "") != MODE_ENGINE_VERSION:
            return False
        return verify_digest(
            semantic_payload(profile, exclude={"profile_digest"}),
            str(profile.get("profile_digest") or ""),
        )

    def evaluate(
        self,
        action: Mapping[str, Any],
        *,
        policy: ApprovalRiskPolicy,
    ) -> dict[str, Any]:
        mode = PermissionMode(str(action.get("permission_mode") or "REVIEW").upper())
        profile = self._PROFILES[mode]

        classification = ApprovalRiskClassifier().classify(action, policy=policy)
        requirement = ApprovalRequirement(str(classification["requirement"]))
        tool_class = ToolClass(str(classification["tool_class"]))

        reasons = list(classification.get("reasons") or [])
        denied = requirement in {
            ApprovalRequirement.POLICY_DENY,
            ApprovalRequirement.PERMANENTLY_DENIED,
        }
        auto_authorized = requirement == ApprovalRequirement.AUTO_ALLOW and not denied
        may_create_approval = requirement in {
            ApprovalRequirement.REQUIRE_APPROVAL,
            ApprovalRequirement.REQUIRE_SENSITIVE_APPROVAL,
        }

        # A later phase may issue a capability only after a durable human decision.
        may_issue_capability = may_create_approval and profile.agent_enabled

        if mode == PermissionMode.LOCKED:
            denied = True
            auto_authorized = False
            may_create_approval = False
            may_issue_capability = False
            if "LOCKED mode disables the agent" not in reasons:
                reasons.append("LOCKED mode disables the agent")

        if mode == PermissionMode.OBSERVE_ONLY and tool_class in {
            ToolClass.ISOLATED_MUTATION,
            ToolClass.CONSEQUENTIAL_EXECUTION,
            ToolClass.NEVER_MODEL_AUTHORIZED,
        }:
            denied = True
            auto_authorized = False
            may_create_approval = False
            may_issue_capability = False
            reasons.append("OBSERVE_ONLY cannot be widened by approval")

        if mode == PermissionMode.BOUNDED_AUTONOMY and auto_authorized:
            self._enforce_bounded_autonomy(action, tool_class=tool_class)
            reasons.append("bounded autonomy conditions satisfied")

        immutable = {
            "worktree_required_for_mutation": profile.worktree_required_for_mutation,
            "file_allowlist_required": profile.file_allowlist_required,
            "command_allowlist_required": profile.command_allowlist_required,
            "cost_budget_required": profile.cost_budget_required,
            "turn_budget_required": profile.turn_budget_required,
            "network_restricted": profile.network_restricted,
            "sourceplan_promotion_approval_required": profile.sourceplan_promotion_approval_required,
            "evidence_required": profile.evidence_required,
            "sensitive_access_requires_explicit_approval": profile.sensitive_access_requires_explicit_approval,
        }

        result = PermissionModeDecision(
            mode=mode,
            tool_id=str(classification["tool_id"]),
            tool_version=str(classification["tool_version"]),
            tool_class=tool_class,
            policy_generation=str(classification["policy_generation"]),
            classification_digest=str(classification["classification_digest"]),
            requirement=requirement,
            agent_enabled=profile.agent_enabled,
            may_create_approval=may_create_approval,
            may_issue_capability=may_issue_capability,
            auto_authorized=auto_authorized,
            denied=denied,
            immutable_boundaries=immutable,
            reasons=tuple(dict.fromkeys(reasons)),
        ).to_dict()
        if not self.verify_decision(result):
            raise RuntimeError("permission mode decision digest generation failed")
        return result

    def verify_decision(self, decision: Mapping[str, Any]) -> bool:
        if decision.get("beast_object_type") != MODE_DECISION_OBJECT_TYPE:
            return False
        if str(decision.get("version") or "") != MODE_ENGINE_VERSION:
            return False
        if not verify_digest(
            semantic_payload(decision, exclude={"decision_digest"}),
            str(decision.get("decision_digest") or ""),
        ):
            return False
        boundaries = decision.get("immutable_boundaries")
        if not isinstance(boundaries, Mapping):
            return False
        required_true = {
            "worktree_required_for_mutation",
            "file_allowlist_required",
            "command_allowlist_required",
            "cost_budget_required",
            "turn_budget_required",
            "network_restricted",
            "sourceplan_promotion_approval_required",
            "evidence_required",
            "sensitive_access_requires_explicit_approval",
        }
        return all(boundaries.get(name) is True for name in required_true)

    @staticmethod
    def _enforce_bounded_autonomy(action: Mapping[str, Any], *, tool_class: ToolClass) -> None:
        if tool_class == ToolClass.ISOLATED_MUTATION:
            if not bool(action.get("worktree_bound")):
                raise ValueError("bounded autonomy mutation requires a mission worktree")
            if not _nonempty_sequence(action.get("allowed_files")):
                raise ValueError("bounded autonomy mutation requires an explicit file allowlist")
        if tool_class == ToolClass.CONSEQUENTIAL_EXECUTION:
            if not _nonempty_sequence(action.get("allowed_commands")):
                raise ValueError("bounded autonomy execution requires an explicit command allowlist")
        if not isinstance(action.get("budget"), Mapping) or not action.get("budget"):
            raise ValueError("bounded autonomy requires explicit cost and turn budgets")
        if not bool(action.get("evidence_required", True)):
            raise ValueError("bounded autonomy cannot disable evidence")
        if bool(action.get("promotion_without_approval")):
            raise ValueError("bounded autonomy cannot bypass SourcePlan promotion approval")
        if bool(action.get("unrestricted_network")):
            raise ValueError("bounded autonomy cannot enable unrestricted network access")


def _nonempty_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and any(str(item).strip() for item in value)
