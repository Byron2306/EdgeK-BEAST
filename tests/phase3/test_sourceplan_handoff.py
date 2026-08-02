from app.kernel.evidence.sourceplan_handoff import SourcePlanReuseHandoffEngine, digest_object


def signed(value):
    result = dict(value); result["receipt_digest"] = digest_object(result); return result


def outcome(disposition="VERIFIED_EQUIVALENT"):
    return signed({
        "version":"3.7", "beast_object_type":"beast_evidence_reuse_outcome_receipt",
        "evidence_id":"crystal-1", "reuse_receipt_digest":"sha256:reuse",
        "verification_receipt_digest":"sha256:verify", "disposition":disposition,
        "sourceplan_synthesis_eligible": disposition in {"VERIFIED_EQUIVALENT","VERIFIED_ADAPTED"},
        "worktree_id":"wt-1", "worktree_root_digest":"sha256:root",
        "current_fingerprint_digest":"sha256:current", "candidate_fingerprint_digest":"sha256:candidate",
        "outcome_evidence_ref":"sha256:outcome", "workspace_mutation_authorized":False,
        "promotion_authorized":False, "phase2_governance_bypass_allowed":False,
    })


def plan(**changes):
    base={
        "beast_object_type":"sourceplan", "kind":"beast_source_patch_plan", "version":"1.0",
        "plan_id":"plan-1", "status":"draft", "worktree_task_id":"wt-1",
        "files":["app/x.py"], "diff_truncated":False, "requires_operator_translation":False,
        "operations":[{"op_id":"op-1","op":"replace_exact","path":"app/x.py","old_text":"a","new_text":"b","selected":True}],
    }
    base.update(changes); return base


def prepare(o=None,p=None):
    return SourcePlanReuseHandoffEngine().prepare(outcome_receipt=o or outcome(), sourceplan=p or plan(), created_at="2026-07-19T00:00:00Z")


def test_verified_exact_is_review_ready_not_authorized():
    result=prepare(); assert result["disposition"]=="SOURCEPLAN_REVIEW_READY"
    assert result["sourceplan_review_eligible"] and not result["promotion_authorized"] and not result["sourceplan_apply_authorized"]


def test_verified_adapted_is_review_ready():
    assert prepare(outcome("VERIFIED_ADAPTED"))["sourceplan_review_eligible"]


def test_failed_outcome_blocks():
    result=prepare(outcome("VERIFICATION_FAILED")); assert "reuse_outcome_not_verified" in result["blockers"]


def test_tampered_outcome_blocks():
    o=outcome(); o["worktree_id"]="evil"; assert "outcome_receipt_digest_invalid" in prepare(o)["blockers"]


def test_worktree_mismatch_blocks():
    assert "sourceplan_worktree_binding_mismatch" in prepare(p=plan(worktree_task_id="wt-2"))["blockers"]


def test_truncated_or_translation_plan_blocks():
    assert "sourceplan_diff_truncated" in prepare(p=plan(diff_truncated=True))["blockers"]
    assert "sourceplan_requires_operator_translation" in prepare(p=plan(requires_operator_translation=True))["blockers"]


def test_non_exact_operation_blocks():
    p=plan(operations=[{"op_id":"op-1","op":"shell","path":"app/x.py"}])
    assert "non_exact_operation:op-1" in prepare(p=p)["blockers"]


def test_unsafe_path_blocks():
    p=plan(files=["../escape"],operations=[{"op_id":"op-1","op":"replace_exact","path":"../escape"}])
    assert any("unsafe SourcePlan path" in item for item in prepare(p=p)["blockers"])


def test_operation_digest_and_receipt_are_deterministic():
    a=prepare(); b=prepare(); assert a["receipt_digest"]==b["receipt_digest"] and a["operations_digest"]==b["operations_digest"]
