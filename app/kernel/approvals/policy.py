from __future__ import annotations

from dataclasses import dataclass

from .models import ApprovalScope, PermissionMode, RiskClass


@dataclass(frozen=True)
class ApprovalContractPolicy:
    maximum_expiry_seconds: int = 86400
    default_expiry_seconds: int = 900
    destructive_scopes: frozenset[ApprovalScope] = frozenset({ApprovalScope.ONCE, ApprovalScope.EDITED_SCOPE_ONCE})

    def permitted_scopes(self, *, risk: RiskClass, mode: PermissionMode, read_only: bool) -> frozenset[ApprovalScope]:
        if mode in {PermissionMode.LOCKED, PermissionMode.OBSERVE_ONLY} and not read_only:
            return frozenset()
        if risk in {RiskClass.HIGH, RiskClass.CRITICAL} and not read_only:
            return self.destructive_scopes
        scopes = {ApprovalScope.ONCE, ApprovalScope.EQUIVALENT_CALLS_THIS_RUN}
        if read_only:
            scopes.add(ApprovalScope.READ_ONLY_THIS_TARGET)
        if risk in {RiskClass.LOW, RiskClass.MEDIUM}:
            scopes.add(ApprovalScope.TOOL_SCOPE_THIS_WORKSPACE)
        return frozenset(scopes)
