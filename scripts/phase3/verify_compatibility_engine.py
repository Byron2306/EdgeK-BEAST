from pathlib import Path
root=Path(__file__).resolve().parents[2]
checks={
"engine": root.joinpath("app/kernel/evidence/compatibility_engine.py").is_file(),
"route": "/edgek/evidence/compatibility/evaluate" in root.joinpath("app/routes/ide_routes/agent_runs.py").read_text(),
"exact": '"EXACT"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"adaptable": '"ADAPTABLE"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"reference": '"REFERENCE"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"rejected": '"REJECTED"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"revoked": '"REVOKED"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"no_authority": '"reuse_authorized": False' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"fresh_verification": '"fresh_verification_required"' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
"digest": 'receipt_digest' in root.joinpath("app/kernel/evidence/compatibility_engine.py").read_text(),
}
for name,ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
if not all(checks.values()): raise SystemExit(1)
print(f"{sum(checks.values())}/{len(checks)} checks passed")
