import pytest
from app.kernel.compute.quality_equivalence_harness import QualityAttempt, QualityEquivalenceHarness

def attempt(lane, patch, **kw):
    values={"tests_passed":True,"security_scan_passed":True,"no_secret_leak":True,"no_unrelated_changes":True,"provider_calls":0 if lane=="crystallized" else 1,"elapsed_ms":10}
    values.update(kw)
    return QualityAttempt("heldout-1",lane,patch,**values)
def review(): return {"correctness":5,"maintainability":4,"minimality":4,"compatibility":5,"operational_safety":5,"diagnostic_usefulness":4}
def test_blinding_hides_lanes_and_receipt_pairs_reviews():
    h=QualityEquivalenceHarness(seed=7); e,c=attempt("ephemeral","patch-e"),attempt("crystallized","patch-c")
    packet,key=h.blind_packet([e,c]); assert all("lane" not in row for row in packet); assert set(key.values())=={"ephemeral","crystallized"}
    receipt=h.receipt([e,c],{e.patch_digest:review(),c.patch_digest:review()},preregistration={"corpus":"heldout","margin":.25})
    assert receipt["all_hard_gates_passed"] is True and receipt["mean_quality_delta"]==0 and receipt["quality_noninferior"] is True
def test_failed_hard_gate_cannot_claim_equivalence():
    h=QualityEquivalenceHarness(); e=attempt("ephemeral","e"); c=attempt("crystallized","c",tests_passed=False)
    r=h.receipt([e,c],{e.patch_digest:review(),c.patch_digest:review()},preregistration={"corpus":"heldout"})
    assert r["all_hard_gates_passed"] is False and r["paired_quality_deltas"]==[-4.5]
