from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .digests import canonicalize, semantic_payload, sha256_digest, verify_digest
from .models import PermissionMode, RiskClass

CLASSIFIER_VERSION = "4.3"
CLASSIFICATION_OBJECT_TYPE = "beast_approval_risk_classification"


class ApprovalRequirement(str, Enum):
    AUTO_ALLOW = "AUTO_ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    REQUIRE_SENSITIVE_APPROVAL = "REQUIRE_SENSITIVE_APPROVAL"
    POLICY_DENY = "POLICY_DENY"
    PERMANENTLY_DENIED = "PERMANENTLY_DENIED"


class ToolClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    SENSITIVE_READ = "SENSITIVE_READ"
    ISOLATED_MUTATION = "ISOLATED_MUTATION"
    CONSEQUENTIAL_EXECUTION = "CONSEQUENTIAL_EXECUTION"
    NEVER_MODEL_AUTHORIZED = "NEVER_MODEL_AUTHORIZED"


@dataclass(frozen=True)
class ApprovalRiskPolicy:
    generation: str
    sensitive_patterns: tuple[str, ...] = (
        ".env", ".env.*", "*.pem", "*.key", "*credential*", "*secret*", "*signing*", "*policy*",
        ".ssh/*", ".aws/*", ".config/gcloud/*",
    )
    denied_tools: tuple[str, ...] = ()
    permanently_denied_tools: tuple[str, ...] = ()
    allowed_network_domains: tuple[str, ...] = ()
    trusted_targets: tuple[str, ...] = ("local", "devcontainer", "ssh")
    require_approval_for_remote_reads: bool = True
    require_approval_for_network: bool = True
    require_approval_for_execution: bool = True
    require_approval_for_mutation: bool = True


@dataclass(frozen=True)
class ApprovalRiskClassification:
    tool_id: str
    tool_version: str
    tool_class: ToolClass
    requirement: ApprovalRequirement
    risk_class: RiskClass
    permission_mode: PermissionMode
    policy_generation: str
    workspace_id: str
    execution_target: str
    read_only: bool
    sensitive: bool
    network_egress: bool
    worktree_bound: bool
    trusted_workspace: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)
    matched_sensitive_resources: tuple[str, ...] = field(default_factory=tuple)
    matched_policy_rules: tuple[str, ...] = field(default_factory=tuple)
    version: str = CLASSIFIER_VERSION
    beast_object_type: str = CLASSIFICATION_OBJECT_TYPE
    classification_digest: str = ""

    def semantic_dict(self) -> dict[str, Any]:
        return canonicalize(semantic_payload(asdict(self), exclude={"classification_digest"}))

    def to_dict(self) -> dict[str, Any]:
        payload = canonicalize(asdict(self))
        payload["classification_digest"] = self.classification_digest or sha256_digest(self.semantic_dict())
        return payload


class ApprovalRiskClassifier:
    """Deterministic, fail-closed approval risk classifier.

    It classifies authority requirements only. It never persists an approval,
    issues a capability, resumes a run, or executes a tool.
    """

    NEVER_AUTHORIZED_PREFIXES = (
        "workspace.apply_direct", "sourceplan.promote", "git.push", "package.publish",
        "credentials.rotate", "policy.disable", "evidence.disable", "audit.erase",
    )

    def classify(self, payload: Mapping[str, Any], *, policy: ApprovalRiskPolicy) -> dict[str, Any]:
        tool_id = _required(payload, "tool_id")
        tool_version = _required(payload, "tool_version")
        workspace_id = _required(payload, "workspace_id")
        target = _required(payload, "execution_target")
        mode = PermissionMode(str(payload.get("permission_mode") or "REVIEW").upper())
        tool_class = ToolClass(str(payload.get("tool_class") or "READ_ONLY").upper())
        read_only = bool(payload.get("read_only", tool_class in {ToolClass.READ_ONLY, ToolClass.SENSITIVE_READ}))
        worktree_bound = bool(payload.get("worktree_bound", False))
        trusted_workspace = bool(payload.get("trusted_workspace", False))
        resources = _strings(payload.get("affected_resources"))
        data_egress = _strings(payload.get("data_egress"))
        domains = _strings(payload.get("network_domains"))

        reasons: list[str] = []
        rules: list[str] = []
        sensitive_resources = tuple(sorted(r for r in resources if _matches_any(r, policy.sensitive_patterns)))
        sensitive = bool(sensitive_resources) or tool_class == ToolClass.SENSITIVE_READ
        network = bool(data_egress or domains)

        if tool_id in policy.permanently_denied_tools:
            requirement = ApprovalRequirement.PERMANENTLY_DENIED
            reasons.append("tool is permanently denied by active policy")
            rules.append("policy.permanent_tool_deny")
        elif tool_id in policy.denied_tools:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("tool is denied by active policy")
            rules.append("policy.tool_deny")
        elif tool_class == ToolClass.NEVER_MODEL_AUTHORIZED or tool_id.startswith(self.NEVER_AUTHORIZED_PREFIXES):
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("tool class is never model-authorized")
            rules.append("boundary.never_model_authorized")
        elif mode == PermissionMode.LOCKED:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("permission mode LOCKED disables AI actions")
            rules.append("mode.locked")
        elif mode == PermissionMode.OBSERVE_ONLY and not read_only:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("OBSERVE_ONLY forbids mutation and consequential execution")
            rules.append("mode.observe_only")
        elif not trusted_workspace and not read_only:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("untrusted workspace forbids consequential action")
            rules.append("workspace.untrusted_mutation")
        elif tool_class == ToolClass.ISOLATED_MUTATION and not worktree_bound:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("isolated mutation requires a bound mission worktree")
            rules.append("mutation.worktree_required")
        elif target.split(":", 1)[0] not in policy.trusted_targets:
            requirement = ApprovalRequirement.POLICY_DENY
            reasons.append("execution target type is not permitted by policy")
            rules.append("target.not_permitted")
        elif sensitive:
            requirement = ApprovalRequirement.REQUIRE_SENSITIVE_APPROVAL
            reasons.append("sensitive resource access requires explicit approval")
            rules.append("data.sensitive")
        elif network and policy.require_approval_for_network:
            unknown = [d for d in domains if d not in policy.allowed_network_domains]
            requirement = ApprovalRequirement.REQUIRE_APPROVAL
            reasons.append("network egress requires scoped approval")
            rules.append("network.egress")
            if unknown:
                reasons.append("one or more network domains are not pre-approved")
                rules.append("network.domain_unapproved")
        elif tool_class == ToolClass.CONSEQUENTIAL_EXECUTION and policy.require_approval_for_execution:
            requirement = _mode_requirement(mode, consequential=True)
            reasons.append("consequential execution classified under active permission mode")
            rules.append("tool.consequential_execution")
        elif tool_class == ToolClass.ISOLATED_MUTATION and policy.require_approval_for_mutation:
            requirement = _mode_requirement(mode, consequential=True)
            reasons.append("isolated mutation classified under active permission mode")
            rules.append("tool.isolated_mutation")
        elif target != "local" and read_only and policy.require_approval_for_remote_reads:
            requirement = ApprovalRequirement.REQUIRE_APPROVAL
            reasons.append("remote read requires target-scoped approval")
            rules.append("target.remote_read")
        elif mode == PermissionMode.REVIEW:
            requirement = ApprovalRequirement.REQUIRE_APPROVAL
            reasons.append("REVIEW mode requires approval for every agent action")
            rules.append("mode.review")
        else:
            requirement = ApprovalRequirement.AUTO_ALLOW
            reasons.append("action is read-only, non-sensitive, trusted, and allowed by mode")
            rules.append("policy.auto_allow_read")

        risk = _risk_for(tool_class, sensitive=sensitive, network=network, requirement=requirement)
        result = ApprovalRiskClassification(
            tool_id=tool_id, tool_version=tool_version, tool_class=tool_class,
            requirement=requirement, risk_class=risk, permission_mode=mode,
            policy_generation=policy.generation, workspace_id=workspace_id,
            execution_target=target, read_only=read_only, sensitive=sensitive,
            network_egress=network, worktree_bound=worktree_bound,
            trusted_workspace=trusted_workspace, reasons=tuple(reasons),
            matched_sensitive_resources=sensitive_resources,
            matched_policy_rules=tuple(rules),
        ).to_dict()
        if not verify_digest(semantic_payload(result, exclude={"classification_digest"}), result["classification_digest"]):
            raise RuntimeError("classification digest generation failed")
        return result

    def verify(self, classification: Mapping[str, Any]) -> bool:
        if classification.get("beast_object_type") != CLASSIFICATION_OBJECT_TYPE:
            return False
        return verify_digest(semantic_payload(classification, exclude={"classification_digest"}), str(classification.get("classification_digest") or ""))


def policy_from_payload(payload: Mapping[str, Any]) -> ApprovalRiskPolicy:
    return ApprovalRiskPolicy(
        generation=_required(payload, "generation"),
        sensitive_patterns=tuple(_strings(payload.get("sensitive_patterns"))) or ApprovalRiskPolicy.__dataclass_fields__["sensitive_patterns"].default,
        denied_tools=tuple(_strings(payload.get("denied_tools"))),
        permanently_denied_tools=tuple(_strings(payload.get("permanently_denied_tools"))),
        allowed_network_domains=tuple(_strings(payload.get("allowed_network_domains"))),
        trusted_targets=tuple(_strings(payload.get("trusted_targets"))) or ("local", "devcontainer", "ssh"),
        require_approval_for_remote_reads=bool(payload.get("require_approval_for_remote_reads", True)),
        require_approval_for_network=bool(payload.get("require_approval_for_network", True)),
        require_approval_for_execution=bool(payload.get("require_approval_for_execution", True)),
        require_approval_for_mutation=bool(payload.get("require_approval_for_mutation", True)),
    )


def _mode_requirement(mode: PermissionMode, *, consequential: bool) -> ApprovalRequirement:
    if mode in {PermissionMode.REVIEW, PermissionMode.GUIDED}:
        return ApprovalRequirement.REQUIRE_APPROVAL
    if mode == PermissionMode.BOUNDED_AUTONOMY:
        return ApprovalRequirement.AUTO_ALLOW
    return ApprovalRequirement.POLICY_DENY if consequential else ApprovalRequirement.REQUIRE_APPROVAL


def _risk_for(tool_class: ToolClass, *, sensitive: bool, network: bool, requirement: ApprovalRequirement) -> RiskClass:
    if requirement in {ApprovalRequirement.POLICY_DENY, ApprovalRequirement.PERMANENTLY_DENIED}:
        return RiskClass.CRITICAL
    if sensitive or tool_class == ToolClass.NEVER_MODEL_AUTHORIZED:
        return RiskClass.CRITICAL
    if tool_class in {ToolClass.ISOLATED_MUTATION, ToolClass.CONSEQUENTIAL_EXECUTION}:
        return RiskClass.HIGH
    if network:
        return RiskClass.MEDIUM
    return RiskClass.LOW


def _required(payload: Mapping[str, Any], name: str) -> str:
    value = str(payload.get(name) or "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return list(dict.fromkeys(str(v).strip() for v in value if str(v).strip()))


def _matches_any(resource: str, patterns: Sequence[str]) -> bool:
    path = PurePosixPath(resource.replace("\\", "/").lstrip("/"))
    return any(path.match(pattern) or path.name == pattern for pattern in patterns)
