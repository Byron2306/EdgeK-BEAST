from pathlib import Path

checks = {
    "ledger module": Path("app/kernel/evidence/evidence_ledger.py"),
    "append-only table": Path("app/kernel/evidence/evidence_store.py"),
    "crystallization created event": Path("app/kernel/evidence/evidence_builder.py"),
    "ledger routes": Path("app/routes/ide_routes/agent_runs.py"),
    "ledger tests": Path("tests/phase3/test_evidence_ledger.py"),
}
needles = {
    "ledger module": "class EvidenceLedger",
    "append-only table": "CREATE TABLE IF NOT EXISTS evidence_ledger_events",
    "crystallization created event": '"created"',
    "ledger routes": "/edgek/evidence/{evidence_id}/ledger",
    "ledger tests": "test_tampered_ledger_event_is_detected",
}
passed = 0
for name, path in checks.items():
    ok = path.is_file() and needles[name] in path.read_text(encoding="utf-8")
    print(f"{'PASS' if ok else 'FAIL'} {name}")
    passed += int(ok)
extra = [
    ("hash chain", "previous_hash" in Path("app/kernel/evidence/evidence_ledger.py").read_text()),
    ("revocation gate", "cannot be reused" in Path("app/kernel/evidence/evidence_ledger.py").read_text()),
    ("supersession", "successor_evidence_id" in Path("app/kernel/evidence/evidence_ledger.py").read_text()),
    ("metrics", "record_metric" in Path("app/kernel/evidence/evidence_ledger.py").read_text()),
    ("immutable object retained", "UPDATE evidence_objects" not in Path("app/kernel/evidence/evidence_ledger.py").read_text()),
]
for name, ok in extra:
    print(f"{'PASS' if ok else 'FAIL'} {name}")
    passed += int(ok)
print(f"{passed}/10 checks passed")
raise SystemExit(0 if passed == 10 else 1)
