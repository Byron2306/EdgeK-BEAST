from __future__ import annotations

import copy

import pytest

from app.kernel.approvals.classifier import ApprovalRiskPolicy
from app.kernel.approvals.mode_engine import PermissionModeEngine


def policy() -> ApprovalRiskPolicy:
    return ApprovalRiskPolicy(generation="policy:48")


def action(**overrides):
    payload = {
        "tool_id": "workspace.read_range",
        "tool_version": "1",
        "tool_class": "READ_ONLY",
        "workspace_id": "workspace:repo",
        "execution_target": "local",
        "permission_mode": "GUIDED",
        "read_only": True,
        "trusted_workspace": True,
        "worktree_bound": False,
        "affected_resources": ["app/example.py"],
        "data_egress": [],
        "network_domains": [],
        "budget": {"max_tool_calls": 10, "max_cloud_cost": 1.0},
        "evidence_required": True,
    }
    payload.update(overrides)
    return payload


def test_review_requires_approval_even_for_safe_reads():
    decision = PermissionModeEngine().evaluate(action(permission_mode="REVIEW"), policy=policy())
    assert decision["requirement"] == "REQUIRE_APPROVAL"
    assert decision["may_create_approval"] is True
    assert decision["auto_authorized"] is False


def test_guided_auto_allows_safe_local_read():
    decision = PermissionModeEngine().evaluate(action(permission_mode="GUIDED"), policy=policy())
    assert decision["requirement"] == "AUTO_ALLOW"
    assert decision["auto_authorized"] is True
    assert decision["denied"] is False


def test_guided_requires_approval_for_mutation():
    decision = PermissionModeEngine().evaluate(
        action(
            permission_mode="GUIDED",
            tool_id="workspace.apply_patch",
            tool_class="ISOLATED_MUTATION",
            read_only=False,
            worktree_bound=True,
            allowed_files=["app/example.py"],
        ),
        policy=policy(),
    )
    assert decision["requirement"] == "REQUIRE_APPROVAL"
    assert decision["may_issue_capability"] is True


def test_bounded_autonomy_requires_explicit_file_allowlist():
    with pytest.raises(ValueError, match="file allowlist"):
        PermissionModeEngine().evaluate(
            action(
                permission_mode="BOUNDED_AUTONOMY",
                tool_id="workspace.apply_patch",
                tool_class="ISOLATED_MUTATION",
                read_only=False,
                worktree_bound=True,
            ),
            policy=policy(),
        )


def test_bounded_autonomy_allows_bounded_worktree_mutation():
    decision = PermissionModeEngine().evaluate(
        action(
            permission_mode="BOUNDED_AUTONOMY",
            tool_id="workspace.apply_patch",
            tool_class="ISOLATED_MUTATION",
            read_only=False,
            worktree_bound=True,
            allowed_files=["app/example.py"],
        ),
        policy=policy(),
    )
    assert decision["auto_authorized"] is True
    assert decision["immutable_boundaries"]["sourceplan_promotion_approval_required"] is True
    assert decision["immutable_boundaries"]["evidence_required"] is True


def test_bounded_autonomy_cannot_disable_evidence_or_promotion_approval():
    with pytest.raises(ValueError, match="disable evidence"):
        PermissionModeEngine().evaluate(
            action(
                permission_mode="BOUNDED_AUTONOMY",
                tool_id="workspace.apply_patch",
                tool_class="ISOLATED_MUTATION",
                read_only=False,
                worktree_bound=True,
                allowed_files=["app/example.py"],
                evidence_required=False,
            ),
            policy=policy(),
        )
    with pytest.raises(ValueError, match="promotion approval"):
        PermissionModeEngine().evaluate(
            action(
                permission_mode="BOUNDED_AUTONOMY",
                tool_id="workspace.apply_patch",
                tool_class="ISOLATED_MUTATION",
                read_only=False,
                worktree_bound=True,
                allowed_files=["app/example.py"],
                promotion_without_approval=True,
            ),
            policy=policy(),
        )


def test_observe_only_denies_mutation_without_creating_approval():
    decision = PermissionModeEngine().evaluate(
        action(
            permission_mode="OBSERVE_ONLY",
            tool_id="workspace.apply_patch",
            tool_class="ISOLATED_MUTATION",
            read_only=False,
            worktree_bound=True,
            allowed_files=["app/example.py"],
        ),
        policy=policy(),
    )
    assert decision["denied"] is True
    assert decision["may_create_approval"] is False
    assert decision["may_issue_capability"] is False


def test_locked_denies_all_agent_actions():
    decision = PermissionModeEngine().evaluate(action(permission_mode="LOCKED"), policy=policy())
    assert decision["agent_enabled"] is False
    assert decision["denied"] is True
    assert decision["may_create_approval"] is False


def test_sensitive_access_never_auto_authorizes():
    decision = PermissionModeEngine().evaluate(
        action(
            permission_mode="BOUNDED_AUTONOMY",
            tool_id="workspace.read_range",
            tool_class="SENSITIVE_READ",
            affected_resources=[".env"],
        ),
        policy=policy(),
    )
    assert decision["requirement"] == "REQUIRE_SENSITIVE_APPROVAL"
    assert decision["auto_authorized"] is False


def test_permission_mode_decision_digest_detects_tampering():
    engine = PermissionModeEngine()
    decision = engine.evaluate(action(permission_mode="GUIDED"), policy=policy())
    assert engine.verify_decision(decision) is True
    tampered = copy.deepcopy(decision)
    tampered["auto_authorized"] = False
    assert engine.verify_decision(tampered) is False
