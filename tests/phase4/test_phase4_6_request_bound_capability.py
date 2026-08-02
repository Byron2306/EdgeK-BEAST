from copy import deepcopy
from datetime import datetime, timezone
import pytest

from app.kernel.approvals import ApprovalContractFactory, ApprovalRiskClassifier, ApprovalRiskPolicy, ApprovalScopeEngine, RichApprovalEnvelopeBuilder, RequestBoundCapabilityIssuer


def chain():
    classifier=ApprovalRiskClassifier()
    classification=classifier.classify({"tool_id":"workspace.read_range","tool_version":"1","tool_class":"READ_ONLY","workspace_id":"workspace:repo","execution_target":"local","permission_mode":"REVIEW","read_only":True,"trusted_workspace":True,"worktree_bound":False,"affected_resources":["app/example.py"],"data_egress":[],"network_domains":[]}, policy=ApprovalRiskPolicy(generation="policy:46", trusted_targets=("local",)))
    envelope=RichApprovalEnvelopeBuilder().build({"classification":classification,"request":{"run_id":"run_46","step_id":"step_1","agent_id":"agent:beast","model_id":"model:coder","provider_id":"provider:local","arguments":{"path":"app/example.py","start":1,"end":10},"affected_resources":["app/example.py"],"data_egress":[],"expected_side_effects":[],"reason":"Read exact approved range.","budget_impact":{"tool_calls":1},"evidence_policy":{"level":"summary"},"requested_scope":"ONCE","expiry_seconds":600,"risk_class":classification["risk_class"]}})
    factory=ApprovalContractFactory(); decision=factory.create_decision(envelope["approval_request"],{"operator_id":"operator:byron","decision":"APPROVE","scope":"ONCE","policy_generation":"policy:46"})
    engine=ApprovalScopeEngine(); grant=engine.create_grant({"envelope":envelope,"decision":decision})
    match=engine.evaluate({"grant":grant,"candidate_request":envelope["approval_request"],"candidate_classification":classification})
    return classification,envelope["approval_request"],decision,grant,match


def test_issue_request_bound_capability():
    c,r,d,g,m=chain(); issuer=RequestBoundCapabilityIssuer(); cap=issuer.issue({"classification":c,"request":r,"decision":d,"grant":g,"scope_match":m})
    assert issuer.verify(cap, require_unexpired=True)
    assert cap["run_id"]=="run_46" and cap["step_id"]=="step_1"
    assert cap["execution_authorized"] is False


def test_non_match_cannot_issue():
    c,r,d,g,m=chain(); bad=deepcopy(m); bad["result"]="NO_MATCH"; bad.pop("match_digest")
    from app.kernel.approvals.digests import semantic_payload, sha256_digest
    bad["match_digest"]=sha256_digest(semantic_payload(bad, exclude={"match_digest"}))
    with pytest.raises(ValueError, match="successful scope match"):
        RequestBoundCapabilityIssuer().issue({"classification":c,"request":r,"decision":d,"grant":g,"scope_match":bad})


def test_tampered_grant_denied():
    c,r,d,g,m=chain(); bad=deepcopy(g); bad["tool_id"]="git.push"
    with pytest.raises(ValueError, match="grant"):
        RequestBoundCapabilityIssuer().issue({"classification":c,"request":r,"decision":d,"grant":bad,"scope_match":m})


def test_request_binding_enforced():
    c,r,d,g,m=chain(); bad=deepcopy(r); bad["step_id"]="step_other"
    with pytest.raises(ValueError): RequestBoundCapabilityIssuer().issue({"classification":c,"request":bad,"decision":d,"grant":g,"scope_match":m})


def test_decision_binding_enforced():
    c,r,d,g,m=chain(); bad=deepcopy(d); bad["decision_digest"]="sha256:bad"
    with pytest.raises(ValueError): RequestBoundCapabilityIssuer().issue({"classification":c,"request":r,"decision":bad,"grant":g,"scope_match":m})


def test_classification_binding_enforced():
    c,r,d,g,m=chain(); bad=deepcopy(c); bad["classification_digest"]="sha256:bad"
    with pytest.raises(ValueError, match="classification"):
        RequestBoundCapabilityIssuer().issue({"classification":bad,"request":r,"decision":d,"grant":g,"scope_match":m})


def test_capability_tamper_detection():
    c,r,d,g,m=chain(); issuer=RequestBoundCapabilityIssuer(); cap=issuer.issue({"classification":c,"request":r,"decision":d,"grant":g,"scope_match":m})
    cap["workspace_id"]="workspace:other"
    assert issuer.verify(cap) is False


def test_capability_never_authorizes_execution():
    c,r,d,g,m=chain(); cap=RequestBoundCapabilityIssuer().issue({"classification":c,"request":r,"decision":d,"grant":g,"scope_match":m})
    assert cap["authority"]=="request_bound_capability_descriptor_only"
    assert cap["capability_consumed"] is False
    assert cap["workspace_mutation_authorized"] is False
    assert cap["promotion_authorized"] is False
