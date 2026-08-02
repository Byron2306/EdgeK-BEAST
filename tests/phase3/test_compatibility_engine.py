from copy import deepcopy
from app.kernel.evidence.compatibility_engine import CompatibilityEngine


def _bundle(task="t1", env="e1", policy="default", system="linux", language_path="a.py"):
    return {"version":"3.3","bundle_digest":f"b-{task}-{env}","task":{"digest":task,"components":{"affected_paths":[language_path]}},"environment":{"digest":env,"components":{"policy_profile":policy,"runtime":{"system":system,"machine":"x86_64"},"dependency_digest":"d1","symbols":{"digest":"s1"},"git":{"head":"g1"}}}}


def _engine(tmp_path, monkeypatch, state="active", candidate=None):
    e=CompatibilityEngine(tmp_path)
    monkeypatch.setattr(e.store,"get",lambda x:{"evidence_id":x})
    monkeypatch.setattr(e.fingerprints,"get",lambda x:candidate or _bundle())
    monkeypatch.setattr(e.ledger,"state",lambda x:{"status":state})
    return e


def test_exact_is_classification_only(tmp_path, monkeypatch):
    r=_engine(tmp_path,monkeypatch).evaluate({"evidence_id":"e","current_fingerprint":_bundle()})
    assert r["verdict"]=="EXACT" and not r["reuse_authorized"]
    assert r["requirements"]["fresh_verification_required"]


def test_adaptable_on_same_task_environment_drift(tmp_path, monkeypatch):
    q=_bundle(env="e2"); q["environment"]["components"]["dependency_digest"]="d2"
    r=_engine(tmp_path,monkeypatch).evaluate({"evidence_id":"e","current_fingerprint":q})
    assert r["verdict"]=="ADAPTABLE" and r["requirements"]["adaptation_required"]


def test_reference_on_different_task_with_score(tmp_path, monkeypatch):
    r=_engine(tmp_path,monkeypatch).evaluate({"evidence_id":"e","current_fingerprint":_bundle(task="t2"),"retrieval_score":.7})
    assert r["verdict"]=="REFERENCE" and r["requirements"]["reference_only"]


def test_policy_mismatch_rejected(tmp_path, monkeypatch):
    r=_engine(tmp_path,monkeypatch).evaluate({"evidence_id":"e","current_fingerprint":_bundle(policy="strict"),"retrieval_score":1})
    assert r["verdict"]=="REJECTED" and "policy_profile_mismatch" in r["blockers"]


def test_revoked_terminal(tmp_path, monkeypatch):
    r=_engine(tmp_path,monkeypatch,state="revoked").evaluate({"evidence_id":"e","current_fingerprint":_bundle()})
    assert r["verdict"]=="REVOKED"


def test_receipt_is_deterministic(tmp_path, monkeypatch):
    e=_engine(tmp_path,monkeypatch); p={"evidence_id":"e","current_fingerprint":_bundle()}
    assert e.evaluate(p)["receipt_digest"]==e.evaluate(p)["receipt_digest"]
