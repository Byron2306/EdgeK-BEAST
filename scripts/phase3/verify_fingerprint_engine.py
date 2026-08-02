from pathlib import Path

root = Path(__file__).resolve().parents[2]
checks = {
    "fingerprint_engine": root / "app/kernel/evidence/fingerprint_engine.py",
    "fingerprint_store": root / "app/kernel/evidence/fingerprint_store.py",
    "builder": root / "app/kernel/evidence/evidence_builder.py",
    "routes": root / "app/routes/ide_routes/agent_runs.py",
    "tests": root / "tests/phase3/test_fingerprint_engine.py",
}
texts = {name: path.read_text(encoding="utf-8") for name, path in checks.items()}
assert "build_task_fingerprint" in texts["fingerprint_engine"]
assert "build_environment_fingerprint" in texts["fingerprint_engine"]
assert "compare_fingerprints" in texts["fingerprint_engine"]
assert "evidence_fingerprints" in texts["fingerprint_store"]
assert "fingerprint is immutable" in texts["fingerprint_store"]
assert "build_fingerprint_bundle" in texts["builder"]
assert "/fingerprint/verify" in texts["routes"]
assert "/fingerprints/compare" in texts["routes"]
assert "dependency_digest" in texts["fingerprint_engine"]
assert "symbol_digest" in texts["fingerprint_engine"]
print("Phase 3.3 fingerprint architecture: 10/10 PASS")
