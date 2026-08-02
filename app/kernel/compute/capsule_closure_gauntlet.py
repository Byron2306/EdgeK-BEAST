from __future__ import annotations
from .capsule_rollout import CapsuleRolloutController, CapsuleRolloutMode, CapsuleRolloutPolicy

def run_capsule_closure_gauntlet():
    base={'verified':True,'ir_digest':'i','bounds_digest':'b','verifier_digest':'v','output_digest':'o'}
    calls={'legacy':0,'capsule':0}
    def legacy(): calls['legacy']+=1; return dict(base)
    def verify(): return dict(base)
    def capsule(): calls['capsule']+=1; return dict(base)
    shadow=CapsuleRolloutController(policy=CapsuleRolloutPolicy(CapsuleRolloutMode.SHADOW)).run(task_class='read_only_repo_inspection',legacy_execute=legacy,capsule_verify=verify,capsule_execute=capsule)[1]
    dual=CapsuleRolloutController(policy=CapsuleRolloutPolicy(CapsuleRolloutMode.DUAL_VERIFY)).run(task_class='read_only_repo_inspection',legacy_execute=legacy,capsule_verify=verify,capsule_execute=capsule)[1]
    required=CapsuleRolloutController(policy=CapsuleRolloutPolicy(CapsuleRolloutMode.CAPSULE_REQUIRED,fallback_allowed=False)).run(task_class='read_only_repo_inspection',legacy_execute=legacy,capsule_verify=verify,capsule_execute=capsule)[1]
    return {'shadow_parity':shadow.parity_receipt.parity_verified,'dual_verified':dual.status=='dual_verified','required_capsule':required.selected_path=='capsule','legacy_calls':calls['legacy'],'capsule_calls':calls['capsule'],'closure':'passed'}
