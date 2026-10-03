#!/usr/bin/env python3
"""Freeze Phase 6.2 mixed-capability Truth Arena without replacement."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_digest


RELEASE_ID = "DAI-Diode-Phase-6.2__Mixed-Capability-Truth-Arena__2026-08-04"
PHASE6_RECEIPT = ROOT / "evidence/dai-diode/phase6-deterministic-arena/dai_phase6_deterministic_arena_receipt.json"
PHASE6_1_RECEIPT = ROOT / "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json"
PHASE6_2_RECEIPT = ROOT / "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json"
PHASE6_2_LEDGER = ROOT / "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json"
SOPHIA_EXPORT = Path("/home/byron/Integritas-Mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json")

EXPECTED = {
    "phase6_receipt_digest": "sha256:e072ff6606f8654ee132b4c1740bacd9538e1d87fb849f8116d8f2e4b1602073",
    "phase6_1_receipt_digest": "sha256:b820ca6f62a10c0477740325500f08365a6b7c98ac3ee819c902456b004b87ae",
    "phase6_2_receipt_digest": "sha256:6b311269f33e381edf3b7536cddb4132506740624d7ca1fbe49c5c4df5221f8a",
    "phase6_2_ledger_digest": "sha256:a1df0125911697249d754a7052573bbc197432e5cd02f4178f3d9e6a78f0e5de",
    "sophia_export_digest": "sha256:5fa74d666de74bbd1de9b41d5652cd6f16ee39d8985ab4de3ca6ef758fa6d3a2",
}

SOURCE_PATHS = (
    "app/kernel/compute/deterministic_intelligence.py",
    "app/kernel/dai/contracts.py",
    "app/kernel/dai/sophia_bridge.py",
    "app/kernel/dai/phase3_composition.py",
    "app/kernel/dai/phase3_expression.py",
    "app/kernel/dai/phase6_deterministic_arena.py",
    "app/kernel/dai/phase6_sophia_transfer_arena.py",
    "app/kernel/dai/capability_ledger.py",
    "app/kernel/dai/phase6_truth_arena.py",
    "scripts/run_dai_phase6_deterministic_arena.py",
    "scripts/run_dai_phase6_sophia_transfer_arena.py",
    "scripts/run_dai_phase6_truth_arena.py",
    "scripts/package_dai_phase6_2_artifact.py",
)
TEST_PATHS = (
    "tests/test_dai_sophia_bridge.py",
    "tests/test_dai_phase3_expression.py",
    "tests/test_dai_phase6_deterministic_arena.py",
    "tests/test_dai_phase6_sophia_transfer_arena.py",
    "tests/test_dai_phase6_truth_arena.py",
)
EVIDENCE_PATHS = (
    "evidence/dai-diode/phase6-deterministic-arena/dai_phase6_deterministic_arena_receipt.json",
    "evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json",
    "evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json",
    "evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json",
)
DEPENDENCY_PATHS = ("pyproject.toml", "pytest.ini", "requirements.txt", "requirements-semantic.txt")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(json.dumps(package(out_root=args.out_root), indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path) -> dict[str, Any]:
    phase6 = _read_json(PHASE6_RECEIPT)
    phase6_1 = _read_json(PHASE6_1_RECEIPT)
    phase6_2 = _read_json(PHASE6_2_RECEIPT)
    ledger = _read_json(PHASE6_2_LEDGER)
    _assert_receipt(phase6, "receipt_digest", EXPECTED["phase6_receipt_digest"], green_field="green")
    _assert_receipt(phase6_1, "receipt_digest", EXPECTED["phase6_1_receipt_digest"], green_field="green")
    _assert_receipt(phase6_2, "receipt_digest", EXPECTED["phase6_2_receipt_digest"], green_field="green")
    _assert_receipt(ledger, "ledger_digest", EXPECTED["phase6_2_ledger_digest"])
    if _sha256_file(SOPHIA_EXPORT) != EXPECTED["sophia_export_digest"]:
        raise RuntimeError("Sophia export digest mismatch")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    archive = out_root / f"{RELEASE_ID}.zip"
    if bundle.exists() or archive.exists():
        raise RuntimeError("Phase-6.2 fossil identity already exists; never replace a frozen artifact")
    bundle.mkdir()

    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    _copy_paths(EVIDENCE_PATHS, bundle / "evidence")
    external = bundle / "external-evidence/integritas-mechanicus/evidence"
    external.mkdir(parents=True)
    shutil.copy2(SOPHIA_EXPORT, external / SOPHIA_EXPORT.name)
    docs = bundle / "docs"
    docs.mkdir()
    shutil.copy2(ROOT / "docs/SOPHIA_BEAST_SYNTHESIS_PLAN_2026-08-04.md", docs / "SOPHIA_BEAST_SYNTHESIS_PLAN_2026-08-04.md")

    _write(bundle / "README.md", _readme())
    _write(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims())
    _write(bundle / "AUTHORITY_MAP.md", _authority())
    _write(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _clean_repro())
    _write(bundle / "install_source_overlay.sh", _overlay())
    (bundle / "install_source_overlay.sh").chmod(0o755)
    _write(bundle / "reproduce_clean_environment.sh", _reproduce_script())
    (bundle / "reproduce_clean_environment.sh").chmod(0o755)
    _write(bundle / "verify_phase6_2_bundle.py", _verifier())
    (bundle / "verify_phase6_2_bundle.py").chmod(0o755)
    _write_json(bundle / "runtime_environment.json", _runtime())
    _write_json(bundle / "EXPECTED_DIGESTS.json", EXPECTED)

    manifest = _manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", manifest)
    _write(bundle / "SHA256SUMS.txt", "\n".join(f"{row['sha256']}  {row['path']}" for row in manifest["entries"]) + "\n")
    release = {
        "beast_object_type": "dai_phase6_2_mixed_truth_arena_release",
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 6.2 - Mixed-Capability Truth Arena",
        "date": "2026-08-04",
        "expected_digests": EXPECTED,
        "file_manifest_digest": manifest["manifest_digest"],
        "one_command_verify": "python3 verify_phase6_2_bundle.py",
        "one_command_clean_reproduce": "./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST",
        "authority_boundary": {"provider_calls_after_ledger": 0, "production_authority_allowed": False, "execution_authority_allowed": False},
        "core_claim": "A ledger containing restart-risk and Sophia source-support crystals solves mixed held-out source-policy-operational cases deterministically with proposition-covered text/SVG and zero post-ledger provider calls.",
    }
    release["release_manifest_digest"] = sha256_digest(release)
    _write_json(bundle / "RELEASE_MANIFEST.json", release)

    verified = subprocess.run([sys.executable, str(bundle / "verify_phase6_2_bundle.py")], cwd=bundle, text=True, capture_output=True, check=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(out_root).as_posix())
    zip_digest = _sha256_file(archive)
    (out_root / f"{RELEASE_ID}.zip.sha256").write_text(f"{zip_digest}  {archive.name}\n", encoding="utf-8")
    return {
        "release_id": RELEASE_ID,
        "bundle_dir": str(bundle),
        "zip": str(archive),
        "zip_digest": zip_digest,
        "release_manifest_digest": release["release_manifest_digest"],
        "file_manifest_digest": manifest["manifest_digest"],
        "verifier_stdout": verified.stdout.strip(),
    }


def _assert_receipt(payload: dict[str, Any], digest_field: str, expected: str, *, green_field: str | None = None) -> None:
    body = dict(payload)
    claimed = body.pop(digest_field, "")
    if claimed != expected or sha256_digest(body) != claimed:
        raise RuntimeError(f"{digest_field} does not recompute")
    if green_field and payload.get(green_field) is not True:
        raise RuntimeError(f"{digest_field} is not green")


def _copy_paths(paths: tuple[str, ...], destination_root: Path) -> None:
    for relative in paths:
        source = ROOT / relative
        if not source.exists():
            raise RuntimeError(f"required path missing: {relative}")
        destination = destination_root / relative
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def _manifest(bundle: Path) -> dict[str, Any]:
    excluded = {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}
    entries = [
        {"path": path.relative_to(bundle).as_posix(), "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
        for path in sorted(bundle.rglob("*"))
        if path.is_file() and path.name not in excluded
    ]
    return {"release_id": RELEASE_ID, "entry_count": len(entries), "entries": entries, "manifest_digest": sha256_digest(entries)}


def _runtime() -> dict[str, Any]:
    return {
        "python": sys.version,
        "git_head": _command(["git", "rev-parse", "HEAD"]),
        "git_status_short": _command(["git", "status", "--short"]),
        "pip_freeze": _command([str(ROOT / ".venv/bin/python"), "-m", "pip", "freeze"]),
    }


def _readme() -> str:
    return f"""# {RELEASE_ID}

Frozen Phase-6.2 mixed-capability Truth Arena.

Core result:

- capability ledger digest: `{EXPECTED["phase6_2_ledger_digest"]}`
- arena receipt digest: `{EXPECTED["phase6_2_receipt_digest"]}`
- 9/9 mixed-capability held-out cases semantic-correct
- 9/9 text + visual joined verification green
- 9/9 visual proposition coverage
- 6 ordinary answers, 3 refusal artifacts
- 0 provider calls after ledger lookup

Verify the bundle:

```bash
python3 verify_phase6_2_bundle.py
```
"""


def _claims() -> str:
    return """# Claims, nonclaims and limitations

## Claim

BEAST can compose two previously promoted deterministic crystals — restart-risk composition and Sophia source-support — to answer new mixed source-policy-operational questions from a capability ledger without post-ledger provider calls.

## Nonclaims

- This is not AGI.
- This is not a claim of universal academic truth.
- This is not production execution authority.
- This is not a live external RDS/RAG victory in the frozen receipt; the RDS adapter hook is present but disabled for this fossil.
- This is not independent third-party replication.

## Known limitations

- The arena is still a bounded synthetic held-out generator.
- The visual verifier checks proposition coverage in the SVG text layer, not arbitrary graphic semantics.
- Live RAG/KG/model baselines remain the next Truth Arena extension.
"""


def _authority() -> str:
    return """# Authority map

Sophia export -> observation-only source artifact.

BEAST bridge -> quarantined candidate.

Phase 6.1 -> bounded test-only source-support crystal.

Phase 6.0 -> bounded test-only restart-risk crystal.

Phase 6.2 ledger -> test-only non-executable capability ledger.

Truth Arena -> deterministic text/SVG expression only when the route is answerable.

Residual / unsupported / missing evidence -> refusal artifact only.

No layer grants provider, production or execution authority.
"""


def _clean_repro() -> str:
    return """# Clean-environment reproduction

1. Prepare a clean EdgeK-BEAST checkout with Python dependencies installed.
2. From this bundle, run:

```bash
./install_source_overlay.sh /path/to/clean/EdgeK-BEAST
./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST
```

The reproduction script copies the bundled evidence overlay, runs Phase 6.0,
Phase 6.1 with the bundled Sophia export, Phase 6.2, and then runs the bundled
Phase 6/Phase 3 expression tests.
"""


def _overlay() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: install_source_overlay.sh /path/to/EdgeK-BEAST}
[ -f "$TARGET/pyproject.toml" ] || { echo "not an EdgeK-BEAST checkout: $TARGET" >&2; exit 65; }
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
for tree in source tests dependencies; do
  [ -d "$SCRIPT_DIR/$tree" ] || continue
  (cd "$SCRIPT_DIR/$tree" && find . -type f -print0) | while IFS= read -r -d '' file; do
    mkdir -p "$TARGET/$(dirname "$file")"
    cp -p "$SCRIPT_DIR/$tree/$file" "$TARGET/$file"
  done
done
"""


def _reproduce_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: reproduce_clean_environment.sh /path/to/EdgeK-BEAST}
[ -f "$TARGET/pyproject.toml" ] || { echo "not an EdgeK-BEAST checkout: $TARGET" >&2; exit 65; }
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$TARGET/evidence"
if [ -d "$SCRIPT_DIR/evidence/evidence" ]; then
  (cd "$SCRIPT_DIR/evidence" && find evidence -type f -print0) | while IFS= read -r -d '' file; do
    mkdir -p "$TARGET/$(dirname "$file")"
    cp -p "$SCRIPT_DIR/evidence/$file" "$TARGET/$file"
  done
fi
PY="$TARGET/.venv/bin/python"
[ -x "$PY" ] || PY=python3
cd "$TARGET"
PYTHONNOUSERSITE=1 "$PY" scripts/run_dai_phase6_deterministic_arena.py
PYTHONNOUSERSITE=1 "$PY" scripts/run_dai_phase6_sophia_transfer_arena.py --export-path "$SCRIPT_DIR/external-evidence/integritas-mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json"
PYTHONNOUSERSITE=1 "$PY" scripts/run_dai_phase6_truth_arena.py
PYTHONNOUSERSITE=1 "$PY" -m pytest tests/test_dai_phase6_truth_arena.py tests/test_dai_phase6_sophia_transfer_arena.py tests/test_dai_phase6_deterministic_arena.py tests/test_dai_phase3_expression.py -q
"""


def _verifier() -> str:
    return f'''#!/usr/bin/env python3
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
EXPECTED = {json.dumps(EXPECTED, sort_keys=True)}
def canonical(value):
    if isinstance(value, dict):
        return {{str(k): canonical(value[k]) for k in sorted(value, key=lambda item: str(item))}}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value
def digest_value(value):
    return "sha256:" + hashlib.sha256(json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def digest_file(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return "sha256:"+h.hexdigest()
def read_json(rel):
    return json.loads((ROOT/rel).read_text())
manifest=read_json("SHA256_MANIFEST.json")
actual={{str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file() and path.name not in {{"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}}}}
listed={{item["path"] for item in manifest["entries"]}}
assert actual == listed, {{"extra": sorted(actual-listed), "missing": sorted(listed-actual)}}
for item in manifest["entries"]:
    assert digest_file(ROOT/item["path"]) == item["sha256"], item["path"]
def assert_self(rel, field, expected, green=None):
    payload=read_json(rel)
    body=dict(payload)
    claimed=body.pop(field)
    assert claimed == expected, rel
    assert digest_value(body) == claimed, rel
    if green:
        assert payload[green] is True, rel
    return payload
assert_self("evidence/evidence/dai-diode/phase6-deterministic-arena/dai_phase6_deterministic_arena_receipt.json", "receipt_digest", EXPECTED["phase6_receipt_digest"], "green")
assert_self("evidence/evidence/dai-diode/phase6-sophia-transfer-arena/dai_phase6_sophia_transfer_arena_receipt.json", "receipt_digest", EXPECTED["phase6_1_receipt_digest"], "green")
truth=assert_self("evidence/evidence/dai-diode/phase6-truth-arena/dai_phase6_truth_arena_receipt.json", "receipt_digest", EXPECTED["phase6_2_receipt_digest"], "green")
ledger=assert_self("evidence/evidence/dai-diode/phase6-truth-arena/dai_capability_ledger.json", "ledger_digest", EXPECTED["phase6_2_ledger_digest"])
assert digest_file(ROOT/"external-evidence/integritas-mechanicus/evidence/sophia_writing_desk_phase3_export_semantic_latest.json") == EXPECTED["sophia_export_digest"]
assert truth["ledger_digest"] == ledger["ledger_digest"]
assert truth["semantic_correct_count"] == truth["case_count"] == 9
assert truth["text_visual_joined_green_count"] == 9
assert truth["visual_proposition_coverage_count"] == 9
assert truth["provider_calls_after_ledger"] == 0
print(json.dumps({{"verified": True, "entry_count": manifest["entry_count"], "truth_receipt_digest": truth["receipt_digest"]}}, sort_keys=True))
'''


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write(path, canonical_json(value) + "\n")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def _command(command: list[str]) -> str:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False).stdout


if __name__ == "__main__":
    raise SystemExit(main())
