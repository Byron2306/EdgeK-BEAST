#!/usr/bin/env python3
"""Freeze the Phase-3 multi-domain composition proof without replacement."""
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

RELEASE_ID = "DAI-Diode-Phase-3__Multi-Domain-Capability-Composition__2026-08-04"
EVIDENCE = ROOT / "evidence/dai-diode/phase3-composition-001"
HOSTILE_DIGEST = "sha256:8e271be8c571b6e4015aec33118c790857602a1e463ac2ab62bbb8462411a72a"
EXPRESSION_DIGEST = "sha256:ff73430b34ff8e6b2ca882e3ce8a2881cee6c98ed966349fef429e605736e1bc"

SOURCE_PATHS = (
    "app/kernel/dai",
    "app/kernel/compute/deterministic_intelligence.py",
    "scripts/run_dai_phase3_fossil_registry.py",
    "scripts/run_dai_phase3_lockfile_domain.py",
    "scripts/run_dai_phase3_certificate_domain.py",
    "scripts/run_dai_phase3_composition_graph.py",
    "scripts/run_dai_phase3_relevance_pruning.py",
    "scripts/run_dai_phase3_residual_route.py",
    "scripts/run_dai_phase3_expression.py",
    "scripts/run_dai_phase3_hostile_gauntlet.py",
    "scripts/package_dai_phase3_artifact.py",
)
TEST_PATHS = (
    "tests/test_dai_phase3_fossil.py",
    "tests/test_dai_phase3_lockfile.py",
    "tests/test_dai_phase3_certificate.py",
    "tests/test_dai_phase3_composition.py",
    "tests/test_dai_phase3_expression.py",
    "tests/test_dai_phase3_hostile_gauntlet.py",
)
DEPENDENCY_PATHS = ("pyproject.toml", "pytest.ini", "requirements.txt", "requirements-semantic.txt")
PRIOR_FOSSIL = ROOT / "artifacts/DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04.zip"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    result = package(out_root=args.out_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path) -> dict[str, Any]:
    hostile = _read_json(EVIDENCE / "hostile-gauntlet/phase3_hostile_gauntlet_receipt.json")
    expression = _read_json(EVIDENCE / "composition-graph/phase3_expression_receipt.json")
    _assert_green(hostile, HOSTILE_DIGEST, "hostile gauntlet")
    _assert_green(expression, EXPRESSION_DIGEST, "expression")
    if not PRIOR_FOSSIL.is_file():
        raise RuntimeError(f"missing Phase-2.1 predecessor fossil: {PRIOR_FOSSIL}")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    archive = out_root / f"{RELEASE_ID}.zip"
    if bundle.exists() or archive.exists():
        raise RuntimeError("Phase-3 fossil identity already exists; never replace a frozen artifact")
    bundle.mkdir()
    _copy_tree(EVIDENCE, bundle / "evidence/dai-diode/phase3-composition-001")
    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    (bundle / "prior-fossils").mkdir()
    shutil.copy2(PRIOR_FOSSIL, bundle / "prior-fossils" / PRIOR_FOSSIL.name)
    _write(bundle / "README.md", _readme(hostile, expression))
    _write(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims())
    _write(bundle / "AUTHORITY_MAP.md", _authority())
    _write(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _reproduce())
    _write(bundle / "install_source_overlay.sh", _overlay())
    (bundle / "install_source_overlay.sh").chmod(0o755)
    _write(bundle / "verify_phase3_bundle.py", _verifier())
    (bundle / "verify_phase3_bundle.py").chmod(0o755)
    runtime = _runtime()
    _write_json(bundle / "runtime_environment.json", runtime)
    manifest = _manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", manifest)
    _write(bundle / "SHA256SUMS.txt", "\n".join(f"{row['sha256']}  {row['path']}" for row in manifest["entries"]) + "\n")
    release = {
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 3 — Multi-Domain Capability Composition",
        "date": "2026-08-04",
        "beast_object_type": "dai_phase3_composition_release",
        "hostile_gauntlet_receipt_digest": HOSTILE_DIGEST,
        "expression_receipt_digest": EXPRESSION_DIGEST,
        "prior_phase2_1_fossil_sha256": _sha256_file(PRIOR_FOSSIL),
        "file_manifest_digest": manifest["manifest_digest"],
        "one_command_verify": "python3 verify_phase3_bundle.py",
        "source_overlay_installer": "./install_source_overlay.sh /path/to/EdgeK-BEAST",
        "authority_boundary": {"provider_calls_used": 0, "production_authority_allowed": False, "execution_authority_allowed": False},
    }
    release["release_manifest_digest"] = _digest(release)
    _write_json(bundle / "RELEASE_MANIFEST.json", release)
    verified = subprocess.run([sys.executable, str(bundle / "verify_phase3_bundle.py")], cwd=bundle, text=True, capture_output=True, check=True)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                zip_file.write(path, path.relative_to(out_root).as_posix())
    zip_digest = _sha256_file(archive)
    (out_root / f"{RELEASE_ID}.zip.sha256").write_text(f"{zip_digest}  {archive.name}\n", encoding="utf-8")
    return {"release_id": RELEASE_ID, "bundle_dir": str(bundle), "zip": str(archive), "zip_digest": zip_digest, "verifier_stdout": verified.stdout.strip()}


def _assert_green(receipt: dict[str, Any], digest: str, label: str) -> None:
    body = dict(receipt)
    claimed = body.pop("receipt_digest", "")
    if claimed != digest or _digest(body) != claimed:
        raise RuntimeError(f"{label} receipt digest does not recompute")
    if receipt.get("green") is not True and receipt.get("joined_verification") is not True:
        raise RuntimeError(f"{label} receipt is not green")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _copy_paths(paths: tuple[str, ...], destination_root: Path) -> None:
    for relative in paths:
        source = ROOT / relative
        if not source.exists():
            raise RuntimeError(f"required source path missing: {relative}")
        destination = destination_root / relative
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def _manifest(bundle: Path) -> dict[str, Any]:
    entries = [{"path": path.relative_to(bundle).as_posix(), "sha256": _sha256_file(path), "size_bytes": path.stat().st_size} for path in sorted(bundle.rglob("*")) if path.is_file() and path.name not in {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}]
    return {"release_id": RELEASE_ID, "entry_count": len(entries), "entries": entries, "manifest_digest": _digest(entries)}


def _runtime() -> dict[str, Any]:
    return {"python": sys.version, "git_head": _command(["git", "rev-parse", "HEAD"]), "git_status_short": _command(["git", "status", "--short"]), "pip_freeze": _command([str(ROOT / ".venv/bin/python"), "-m", "pip", "freeze"])}


def _command(command: list[str]) -> str:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False).stdout


def _readme(hostile: dict[str, Any], expression: dict[str, Any]) -> str:
    return f"""# {RELEASE_ID}\n\nFrozen Phase-3 proof of multi-domain capability composition.\n\n- Hostile gauntlet: 10/10 attacks blocked (`{hostile['receipt_digest']}`)\n- Text/visual joined verification: green (`{expression['receipt_digest']}`)\n- Provider calls: 0\n- Production/execution authority: false\n\nVerify: `python3 verify_phase3_bundle.py`\n"""


def _claims() -> str:
    return """# Claims and limits\n\nClaim: BEAST composes frozen and live bounded capabilities into an intent-scoped, zero-provider answer and SVG only after relevance, residual and independent entailment gates pass.\n\nNonclaims: this is not general intelligence, autonomous production execution, a hardware-attested quorum, or evidence that every future domain will compose correctly.\n\nKnown limit: the graph schema presently supports the bounded Phase-3 relation vocabulary; broader causal ontology remains a future phase.\n"""


def _authority() -> str:
    return """# Authority map\n\nFossils and receipts may support composition. Relevance may select facts. Residual routing may refuse expression. Text and SVG may express only authorized facts. No layer grants provider, execution, or production authority.\n"""


def _reproduce() -> str:
    return """# Clean reproduction\n\n1. Create a Python environment with the included dependency specifications.\n2. Install source into a clean EdgeK-BEAST checkout using `./install_source_overlay.sh /path/to/EdgeK-BEAST`.\n3. Copy the bundled evidence tree to that checkout.\n4. Run the eight included Phase-3 runners in this order:\n   `scripts/run_dai_phase3_fossil_registry.py`,\n   `scripts/run_dai_phase3_lockfile_domain.py`,\n   `scripts/run_dai_phase3_certificate_domain.py`,\n   `scripts/run_dai_phase3_composition_graph.py`,\n   `scripts/run_dai_phase3_relevance_pruning.py`,\n   `scripts/run_dai_phase3_residual_route.py`,\n   `scripts/run_dai_phase3_expression.py`,\n   `scripts/run_dai_phase3_hostile_gauntlet.py`.\n5. Verify this frozen bundle with `python3 verify_phase3_bundle.py`.\n\nThe included predecessor Phase-2.1 ZIP is historical input; do not overwrite it.\n"""


def _overlay() -> str:
    return """#!/usr/bin/env bash\nset -euo pipefail\nTARGET=${1:?usage: install_source_overlay.sh /path/to/EdgeK-BEAST}\n[ -f \"$TARGET/pyproject.toml\" ] || { echo 'not an EdgeK-BEAST checkout' >&2; exit 65; }\nSCRIPT_DIR=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\nfor tree in source tests dependencies; do\n  [ -d \"$SCRIPT_DIR/$tree\" ] || continue\n  (cd \"$SCRIPT_DIR/$tree\" && find . -type f -print0) | while IFS= read -r -d '' file; do\n    mkdir -p \"$TARGET/$(dirname \"$file\")\"\n    cp -p \"$SCRIPT_DIR/$tree/$file\" \"$TARGET/$file\"\n  done\ndone\n"""


def _verifier() -> str:
    return f'''#!/usr/bin/env python3
import hashlib, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent
def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return "sha256:"+h.hexdigest()
manifest=json.loads((ROOT/"SHA256_MANIFEST.json").read_text())
actual={{
    str(path.relative_to(ROOT))
    for path in ROOT.rglob("*")
    if path.is_file() and path.name not in {{"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}}
}}
listed={{item["path"] for item in manifest["entries"]}}
assert actual == listed, {{"extra_files": sorted(actual-listed), "missing_files": sorted(listed-actual)}}
for item in manifest["entries"]:
    assert digest(ROOT/item["path"]) == item["sha256"], item["path"]
hostile=json.loads((ROOT/"evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json").read_text())
expression=json.loads((ROOT/"evidence/dai-diode/phase3-composition-001/composition-graph/phase3_expression_receipt.json").read_text())
assert hostile["receipt_digest"] == "{HOSTILE_DIGEST}" and hostile["green"] is True
assert expression["receipt_digest"] == "{EXPRESSION_DIGEST}" and expression["joined_verification"] is True
print(json.dumps({{"verified": True, "entry_count": manifest["entry_count"]}}, sort_keys=True))
'''


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write(path, canonical_json(value) + "\n")


def _digest(value: Any) -> str:
    return sha256_digest(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
