from __future__ import annotations

import copy

from app.kernel.approvals.classifier import ApprovalRiskClassifier, ApprovalRiskPolicy


def action(**overrides):
    base = {
        "tool_id": "workspace.read_range",
        "tool_version": "1",
        "tool_class": "READ_ONLY",
        "workspace_id": "workspace:test",
        "execution_target": "local",
        "permission_mode": "GUIDED",
        "read_only": True,
        "trusted_workspace": True,
        "worktree_bound": False,
        "affected_resources": ["app/main.py"],
        "data_egress": [],
        "network_domains": [],
    }
    base.update(overrides)
    return base


def policy(**overrides):
    data = dict(generation="policy:43")
    data.update(overrides)
    return ApprovalRiskPolicy(**data)


def test_guided_safe_local_read_auto_allows():
    result = ApprovalRiskClassifier().classify(action(), policy=policy())
    assert result["requirement"] == "AUTO_ALLOW"
    assert result["risk_class"] == "LOW"


def test_review_mode_requires_approval_for_safe_read():
    result = ApprovalRiskClassifier().classify(action(permission_mode="REVIEW"), policy=policy())
    assert result["requirement"] == "REQUIRE_APPROVAL"


def test_sensitive_path_requires_sensitive_approval():
    result = ApprovalRiskClassifier().classify(action(affected_resources=[".env"]), policy=policy())
    assert result["requirement"] == "REQUIRE_SENSITIVE_APPROVAL"
    assert result["sensitive"] is True


def test_mutation_without_worktree_is_denied():
    result = ApprovalRiskClassifier().classify(action(tool_id="workspace.apply_patch", tool_class="ISOLATED_MUTATION", read_only=False), policy=policy())
    assert result["requirement"] == "POLICY_DENY"


def test_bounded_autonomy_can_auto_allow_worktree_mutation():
    result = ApprovalRiskClassifier().classify(action(tool_id="workspace.apply_patch", tool_class="ISOLATED_MUTATION", read_only=False, worktree_bound=True, permission_mode="BOUNDED_AUTONOMY"), policy=policy())
    assert result["requirement"] == "AUTO_ALLOW"
    assert result["risk_class"] == "HIGH"


def test_network_egress_requires_approval():
    result = ApprovalRiskClassifier().classify(action(data_egress=["source excerpt"], network_domains=["example.com"]), policy=policy())
    assert result["requirement"] == "REQUIRE_APPROVAL"


def test_locked_mode_denies_everything():
    result = ApprovalRiskClassifier().classify(action(permission_mode="LOCKED"), policy=policy())
    assert result["requirement"] == "POLICY_DENY"


def test_permanent_policy_deny_wins():
    result = ApprovalRiskClassifier().classify(action(tool_id="bad.tool"), policy=policy(permanently_denied_tools=("bad.tool",)))
    assert result["requirement"] == "PERMANENTLY_DENIED"


def test_never_model_authorized_is_denied():
    result = ApprovalRiskClassifier().classify(action(tool_id="git.push", tool_class="NEVER_MODEL_AUTHORIZED", read_only=False, worktree_bound=True), policy=policy())
    assert result["requirement"] == "POLICY_DENY"


def test_digest_is_deterministic_and_tamper_evident():
    classifier = ApprovalRiskClassifier()
    first = classifier.classify(action(), policy=policy())
    second = classifier.classify(action(), policy=policy())
    assert first["classification_digest"] == second["classification_digest"]
    assert classifier.verify(first)
    tampered = copy.deepcopy(first)
    tampered["requirement"] = "POLICY_DENY"
    assert not classifier.verify(tampered)
