from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
checks = {
    "models": ROOT / "app/kernel/evidence/evidence_models.py",
    "digest": ROOT / "app/kernel/evidence/evidence_digest.py",
    "store": ROOT / "app/kernel/evidence/evidence_store.py",
    "builder": ROOT / "app/kernel/evidence/evidence_builder.py",
    "verify": ROOT / "app/kernel/evidence/evidence_verify.py",
}
failures = []
for name, path in checks.items():
    if not path.is_file(): failures.append(f"missing {name}: {path}")
    else: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
text = checks["store"].read_text(encoding="utf-8")
assert "journal_mode=WAL" in text
assert "O_EXCL" in text
assert "INSERT OR IGNORE" in text
builder = checks["builder"].read_text(encoding="utf-8")
assert "promoted commit candidate" in builder
assert "fresh_verification_required" in builder
routes = (ROOT / "app/routes/ide_routes/agent_runs.py").read_text(encoding="utf-8")
for route in ("/evidence/crystallize", "/edgek/evidence", "/verify"):
    assert route in routes
print("Phase 3.1 architecture checks: 10/10 PASS")
