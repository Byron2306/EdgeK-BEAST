from __future__ import annotations
from dataclasses import dataclass
from .capsule_rollout import CapsuleRolloutMode, CapsuleRolloutPolicy

LOW_RISK_DEFAULT=('read_only_repo_inspection','bounded_formatting','non_destructive_file_generation','temporary_workspace_transform')
HIGH_RISK_DEFAULT=('network_mutation','process_kill','mount_operation','privileged_filesystem_change','destructive_cleanup')

@dataclass(frozen=True, slots=True)
class CapsuleEnforcementPlan:
    policy: CapsuleRolloutPolicy
    allowed_task_classes: tuple[str,...]
    excluded_task_classes: tuple[str,...]

class CapsuleEnforcementPlanner:
    def plan(self, stage: str, *, low_risk=LOW_RISK_DEFAULT, high_risk=HIGH_RISK_DEFAULT) -> CapsuleEnforcementPlan:
        if stage=='shadow': p=CapsuleRolloutPolicy(CapsuleRolloutMode.SHADOW)
        elif stage=='dual': p=CapsuleRolloutPolicy(CapsuleRolloutMode.DUAL_VERIFY)
        elif stage=='canary': p=CapsuleRolloutPolicy(CapsuleRolloutMode.CANARY,tuple(low_risk),True)
        elif stage=='primary': p=CapsuleRolloutPolicy(CapsuleRolloutMode.CAPSULE_PRIMARY,tuple(low_risk),True)
        elif stage=='required': p=CapsuleRolloutPolicy(CapsuleRolloutMode.CAPSULE_REQUIRED,tuple(low_risk),False)
        else: raise ValueError('unknown rollout stage')
        return CapsuleEnforcementPlan(p,tuple(low_risk),tuple(high_risk))
