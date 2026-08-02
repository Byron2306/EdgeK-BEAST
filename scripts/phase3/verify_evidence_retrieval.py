from pathlib import Path
root = Path(__file__).resolve().parents[2]
paths = {
    "retrieval": root / "app/kernel/evidence/evidence_retrieval.py",
    "routes": root / "app/routes/ide_routes/agent_runs.py",
    "tests": root / "tests/phase3/test_evidence_retrieval.py",
}
texts = {name: path.read_text(encoding="utf-8") for name, path in paths.items()}
checks = [
    "class EvidenceRetriever" in texts["retrieval"],
    "class RetrievalQuery" in texts["retrieval"],
    "ledger_{status}" in texts["retrieval"],
    "missing_fingerprint" in texts["retrieval"],
    "candidate_only" in texts["retrieval"],
    "reuse_authorized" in texts["retrieval"],
    "receipt_digest" in texts["retrieval"],
    "score_components" in texts["retrieval"],
    "/edgek/evidence/search" in texts["routes"],
    "test_revoked_is_excluded" in texts["tests"],
]
assert all(checks), [index + 1 for index, ok in enumerate(checks) if not ok]
print("Phase 3.4 evidence retrieval architecture: 10/10 PASS")
