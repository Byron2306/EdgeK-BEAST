from pathlib import Path

from app.kernel.evidence.evidence_digest import sha256_digest
from app.kernel.evidence.evidence_ledger import EvidenceLedger
from app.kernel.evidence.evidence_retrieval import EvidenceRetriever
from app.kernel.evidence.evidence_store import EvidenceStore
from app.kernel.evidence.fingerprint_store import FingerprintStore


def seed(root: Path, evidence_id: str, objective: str, path: str, *, policy: str = "default", language_dep: str = "pyproject.toml"):
    evidence = {
        "evidence_id": evidence_id, "run_id": f"run-{evidence_id}", "kind": "beast_evidence_crystal",
        "version": "3.1", "created_at": 1.0,
    }
    evidence["evidence_digest"] = sha256_digest(evidence)
    EvidenceStore(root).put(evidence)
    task_components = {"objective": objective, "mode": "agent", "operation_manifest": [{"kind": "replace", "path": path}], "affected_paths": [path], "error_terms": ["typeerror"]}
    env_components = {
        "git": {"head": "abc", "tree": "tree", "branch": "beast/x"},
        "runtime": {"python": "3.13"},
        "dependencies": [{"path": language_dep, "digest": "sha256:x", "bytes": 1}],
        "dependency_digest": "sha256:d", "symbols": {"files": [{"path": path, "present": True, "symbols": [{"name": "resolve_user", "kind": "function"}]}], "digest": "sha256:s"},
        "policy_profile": policy,
    }
    task = {"algorithm": "beast.task.v1", "components": task_components, "digest": sha256_digest(task_components)}
    env = {"algorithm": "beast.environment.v1", "components": env_components, "digest": sha256_digest(env_components)}
    core = {"version": "3.3", "task": task, "environment": env}
    FingerprintStore(root).put(evidence_id, {**core, "bundle_digest": sha256_digest(core)})
    EvidenceLedger(root).append(evidence_id, "created", {}, actor="test")


def test_ranked_explainable_retrieval(tmp_path: Path):
    seed(tmp_path, "crystal-a", "fix user typeerror", "app/auth.py")
    seed(tmp_path, "crystal-b", "update documentation", "README.md")
    result = EvidenceRetriever(tmp_path).search({
        "objective": "fix user TypeError in authentication", "languages": ["python"],
        "symbols": ["resolve_user"], "affected_paths": ["app/auth.py"], "error_terms": ["typeerror"],
    })
    assert result["candidates"][0]["evidence_id"] == "crystal-a"
    assert result["candidates"][0]["authority"] == "candidate_only"
    assert result["reuse_authorized"] is False
    assert result["receipt_digest"].startswith("sha256:")


def test_revoked_is_excluded(tmp_path: Path):
    seed(tmp_path, "crystal-a", "fix typeerror", "app/auth.py")
    EvidenceLedger(tmp_path).revoke("crystal-a", reason="unsafe", actor="operator")
    result = EvidenceRetriever(tmp_path).search({"objective": "fix typeerror"})
    assert result["candidates"] == []
    assert result["rejected"]["ledger_revoked"] == 1


def test_hard_language_and_policy_filters(tmp_path: Path):
    seed(tmp_path, "crystal-a", "fix typeerror", "app/auth.py", policy="strict")
    result = EvidenceRetriever(tmp_path).search({"objective": "fix typeerror", "languages": ["typescript"]})
    assert result["candidates"] == []
    result = EvidenceRetriever(tmp_path).search({"objective": "fix typeerror", "policy_profile": "default"})
    assert result["candidates"] == []


def test_deterministic_receipt(tmp_path: Path):
    seed(tmp_path, "crystal-a", "fix typeerror", "app/auth.py")
    payload = {"objective": "fix typeerror", "symbols": ["resolve_user"]}
    one = EvidenceRetriever(tmp_path).search(payload)
    two = EvidenceRetriever(tmp_path).search(payload)
    assert one["receipt_digest"] == two["receipt_digest"]
    assert one["candidates"] == two["candidates"]
