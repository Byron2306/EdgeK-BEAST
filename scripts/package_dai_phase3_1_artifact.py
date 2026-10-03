#!/usr/bin/env python3
"""Freeze Phase 3.1 closed-world entailment and signed provenance."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import canonical_json, sha256_bytes, sha256_digest


RELEASE_ID = "DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04"
EVIDENCE = ROOT / "evidence/dai-diode/phase3-composition-001"
PRIOR_FOSSIL = ROOT / "artifacts/DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04.zip"

HOSTILE_DIGEST = "sha256:8e271be8c571b6e4015aec33118c790857602a1e463ac2ab62bbb8462411a72a"
EXPRESSION_DIGEST = "sha256:ff73430b34ff8e6b2ca882e3ce8a2881cee6c98ed966349fef429e605736e1bc"
GRAPH_RECEIPT_DIGEST = "sha256:4f0b0d214e2b0cafbe439329006ce4458558df43a73f3270b8dae332ca6d7418"
FOSSIL_RECEIPT_DIGEST = "sha256:7f0d90bda84f1130198738a0ec29d009bb53edbb21588579b50799f751b692cc"
LOCKFILE_SUMMARY_DIGEST = "sha256:4d7b80007dba10b71069bc383cf27996a2a62349645889845455f54d34e3542e"
CERTIFICATE_SUMMARY_DIGEST = "sha256:f5d743f5699a5377bdbde30bca0c10216410a3b5415d3636e4bc22e42a9a0635"

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
    "scripts/package_dai_phase3_1_artifact.py",
)
TEST_PATHS = (
    "tests/__init__.py",
    "tests/test_dai_phase3_fossil.py",
    "tests/test_dai_phase3_lockfile.py",
    "tests/test_dai_phase3_certificate.py",
    "tests/test_dai_phase3_composition.py",
    "tests/test_dai_phase3_expression.py",
    "tests/test_dai_phase3_hostile_gauntlet.py",
)
DEPENDENCY_PATHS = ("pyproject.toml", "pytest.ini", "requirements.txt", "requirements-semantic.txt")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(json.dumps(package(out_root=args.out_root), indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path) -> dict[str, Any]:
    hostile = _read_json(EVIDENCE / "hostile-gauntlet/phase3_hostile_gauntlet_receipt.json")
    expression = _read_json(EVIDENCE / "composition-graph/phase3_expression_receipt.json")
    graph = _read_json(EVIDENCE / "composition-graph/phase3_composition_graph_receipt.json")
    _assert_receipt(hostile, HOSTILE_DIGEST, "hostile gauntlet")
    _assert_receipt(expression, EXPRESSION_DIGEST, "expression")
    _assert_receipt(graph, GRAPH_RECEIPT_DIGEST, "composition graph")
    if not PRIOR_FOSSIL.is_file():
        raise RuntimeError(f"missing Phase-2.1 predecessor fossil: {PRIOR_FOSSIL}")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    archive = out_root / f"{RELEASE_ID}.zip"
    if bundle.exists() or archive.exists():
        raise RuntimeError("Phase-3.1 fossil identity already exists; never replace a frozen artifact")

    bundle.mkdir()
    _copy_tree(EVIDENCE, bundle / "evidence/dai-diode/phase3-composition-001")
    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    (bundle / "prior-fossils").mkdir()
    shutil.copy2(PRIOR_FOSSIL, bundle / "prior-fossils" / PRIOR_FOSSIL.name)
    predecessor = _predecessor_fossil_record(
        PRIOR_FOSSIL,
        expected_release_id="DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04",
        verifier_name="verify_phase2_exact_bundle.py",
    )
    _write_json(bundle / "PREDECESSOR_PROVENANCE.json", predecessor)

    _write(bundle / "README.md", _readme(hostile, expression))
    _write(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims())
    _write(bundle / "AUTHORITY_MAP.md", _authority())
    _write(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _reproduce())
    _write(bundle / "install_source_overlay.sh", _overlay())
    (bundle / "install_source_overlay.sh").chmod(0o755)
    _write(bundle / "reproduce_clean_environment.sh", _clean_reproduction_script())
    (bundle / "reproduce_clean_environment.sh").chmod(0o755)
    _write(bundle / "verify_phase3_1_bundle.py", _verifier())
    (bundle / "verify_phase3_1_bundle.py").chmod(0o755)
    _write_json(bundle / "runtime_environment.json", _runtime())

    signing_key = Ed25519PrivateKey.generate()
    signed_manifest = _capability_evidence_manifest(bundle, hostile, expression, graph)
    _write_json(bundle / "CAPABILITY_EVIDENCE_MANIFEST.json", signed_manifest)
    _write_json(bundle / "CAPABILITY_EVIDENCE_MANIFEST.sig.json", _signature_packet(signed_manifest, signing_key, "CAPABILITY_EVIDENCE_MANIFEST.json"))

    file_manifest = _manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", file_manifest)
    _write(bundle / "SHA256SUMS.txt", _sha256sums(file_manifest))

    release = {
        "beast_object_type": "dai_phase3_1_closed_world_release",
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 3.1 - Closed-World Entailment and Signed Provenance",
        "date": "2026-08-04",
        "hostile_gauntlet_receipt_digest": HOSTILE_DIGEST,
        "expression_receipt_digest": EXPRESSION_DIGEST,
        "composition_graph_receipt_digest": GRAPH_RECEIPT_DIGEST,
        "capability_evidence_manifest_digest": sha256_digest(signed_manifest),
        "file_manifest_digest": file_manifest["manifest_digest"],
        "prior_phase2_1_fossil_sha256": _sha256_file(PRIOR_FOSSIL),
        "prior_phase2_1_release_manifest_digest": predecessor["release_manifest_digest"],
        "predecessor_provenance_digest": sha256_digest(predecessor),
        "one_command_verify": "python3 verify_phase3_1_bundle.py",
        "one_command_clean_reproduce": "./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST",
        "authority_boundary": {
            "provider_calls_used": 0,
            "production_authority_allowed": False,
            "execution_authority_allowed": False,
        },
    }
    release["release_manifest_digest"] = sha256_digest(release)
    _write_json(bundle / "RELEASE_MANIFEST.json", release)
    _write_json(bundle / "RELEASE_MANIFEST.sig.json", _signature_packet(release, signing_key, "RELEASE_MANIFEST.json"))

    verified = subprocess.run([sys.executable, str(bundle / "verify_phase3_1_bundle.py")], cwd=bundle, text=True, capture_output=True, check=True)
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
        "verifier_stdout": verified.stdout.strip(),
    }


def _capability_evidence_manifest(bundle: Path, hostile: dict[str, Any], expression: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    critical_paths = (
        "evidence/dai-diode/phase3-composition-001/phase3_phase2_fossil_receipt.json",
        "evidence/dai-diode/phase3-composition-001/lockfile-domain/phase3_lockfile_domain_summary.json",
        "evidence/dai-diode/phase3-composition-001/lockfile-domain/phase3_lockfile_cleanup_receipt.json",
        "evidence/dai-diode/phase3-composition-001/lockfile-domain/phase3_lockfile_stale_world_replay_receipt.json",
        "evidence/dai-diode/phase3-composition-001/lockfile-domain/phase3_lockfile_world_lease.json",
        "evidence/dai-diode/phase3-composition-001/certificate-domain/phase3_certificate_domain_summary.json",
        "evidence/dai-diode/phase3-composition-001/certificate-domain/phase3_certificate_handshake_receipt.json",
        "evidence/dai-diode/phase3-composition-001/certificate-domain/phase3_certificate_world_lease.json",
        "evidence/dai-diode/phase3-composition-001/composition-graph/phase3_composition_graph_receipt.json",
        "evidence/dai-diode/phase3-composition-001/composition-graph/phase3_expression_receipt.json",
        "evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json",
    )
    return {
        "beast_object_type": "dai_phase3_1_capability_evidence_manifest",
        "release_id": RELEASE_ID,
        "version": "2026-08-04.phase3.1.signed-provenance.v1",
        "capability_claim": "closed_world_multidomain_composition_reference_only",
        "critical_files": tuple(
            {"path": path, "sha256": _sha256_file(bundle / path), "size_bytes": (bundle / path).stat().st_size}
            for path in critical_paths
        ),
        "expected_receipts": {
            "fossil_receipt_digest": FOSSIL_RECEIPT_DIGEST,
            "lockfile_summary_digest": LOCKFILE_SUMMARY_DIGEST,
            "certificate_summary_digest": CERTIFICATE_SUMMARY_DIGEST,
            "composition_graph_receipt_digest": graph["receipt_digest"],
            "expression_receipt_digest": expression["receipt_digest"],
            "hostile_gauntlet_receipt_digest": hostile["receipt_digest"],
        },
        "hostile_gauntlet": {"case_count": hostile["case_count"], "blocked_count": hostile["blocked_count"], "green": hostile["green"]},
        "authority_boundary": {"provider_calls_used": 0, "production_authority_allowed": False, "execution_authority_allowed": False},
        "signature_nonclaim": "This Ed25519 signature binds this capsule manifest, not public identity or third-party time.",
    }


def _signature_packet(payload: dict[str, Any], key: Ed25519PrivateKey, signed_path: str) -> dict[str, Any]:
    public = key.public_key().public_bytes_raw()
    signature = key.sign(canonical_json(payload).encode("utf-8"))
    packet = {
        "beast_object_type": "dai_phase3_1_ed25519_signature",
        "signed_path": signed_path,
        "signed_payload_digest": sha256_digest(payload),
        "signature_algorithm": "Ed25519",
        "public_key_b64": base64.b64encode(public).decode("ascii"),
        "key_fingerprint": sha256_bytes(public),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    packet["signature_packet_digest"] = sha256_digest(packet)
    return packet


def _assert_receipt(receipt: dict[str, Any], expected_digest: str, label: str) -> None:
    body = dict(receipt)
    claimed = body.pop("receipt_digest", "")
    if claimed != expected_digest or sha256_digest(body) != claimed:
        raise RuntimeError(f"{label} receipt digest does not recompute")
    if receipt.get("green") is not True and receipt.get("joined_verification") is not True and label != "composition graph":
        raise RuntimeError(f"{label} receipt is not green")


def _predecessor_fossil_record(path: Path, *, expected_release_id: str, verifier_name: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"missing predecessor fossil: {path}")
    with tempfile.TemporaryDirectory(prefix="dai-predecessor-") as temp:
        temp_root = Path(temp)
        with zipfile.ZipFile(path) as archive:
            _validate_predecessor_zip(archive, expected_release_id=expected_release_id)
            archive.extractall(temp_root)
        root = temp_root / expected_release_id
        verifier = root / verifier_name
        if not verifier.is_file():
            raise RuntimeError(f"predecessor verifier missing: {verifier_name}")
        verified = subprocess.run([sys.executable, str(verifier)], cwd=root, text=True, capture_output=True, check=True)
        release = _read_json(root / "RELEASE_MANIFEST.json")
        if release.get("release_id") != expected_release_id:
            raise RuntimeError("predecessor release id mismatch")
        claimed = release.get("release_manifest_digest")
        body = dict(release)
        body.pop("release_manifest_digest", None)
        if not claimed or sha256_digest(body) != claimed:
            raise RuntimeError("predecessor release manifest digest does not recompute")
        file_manifest = _read_json(root / "SHA256_MANIFEST.json")
        if release.get("file_manifest_digest") and release["file_manifest_digest"] != file_manifest.get("manifest_digest"):
            raise RuntimeError("predecessor file manifest digest mismatch")
        return {
            "beast_object_type": "dai_predecessor_fossil_provenance",
            "predecessor_zip_name": path.name,
            "predecessor_zip_sha256": _sha256_file(path),
            "release_id": expected_release_id,
            "release_manifest_digest": claimed,
            "file_manifest_digest": file_manifest.get("manifest_digest"),
            "verifier_name": verifier_name,
            "verifier_stdout": verified.stdout.strip(),
            "verified": True,
        }


def _validate_predecessor_zip(archive: zipfile.ZipFile, *, expected_release_id: str) -> None:
    names = set()
    required = {
        f"{expected_release_id}/RELEASE_MANIFEST.json",
        f"{expected_release_id}/SHA256_MANIFEST.json",
        f"{expected_release_id}/SHA256SUMS.txt",
    }
    for info in archive.infolist():
        name = info.filename
        parts = PurePosixPath(name).parts
        if not parts or parts[0] != expected_release_id or any(part in {"", ".", ".."} for part in parts) or PurePosixPath(name).is_absolute():
            raise RuntimeError(f"unsafe predecessor ZIP path: {name}")
        if name in names:
            raise RuntimeError(f"duplicate predecessor ZIP path: {name}")
        names.add(name)
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"predecessor ZIP missing required files: {missing}")


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


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
    excluded = {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json", "RELEASE_MANIFEST.sig.json"}
    entries = []
    seen: set[str] = set()
    seen_folded: set[str] = set()
    seen_nfc: set[str] = set()
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle).as_posix()
        _validate_bundle_path(path, bundle=bundle, relative=relative, control_paths=excluded)
        if relative in excluded:
            continue
        if not path.is_file():
            continue
        folded = relative.casefold()
        normalized = unicodedata.normalize("NFC", relative)
        if relative in seen or folded in seen_folded or normalized in seen_nfc:
            raise RuntimeError(f"duplicate/colliding bundle path: {relative}")
        seen.add(relative)
        seen_folded.add(folded)
        seen_nfc.add(normalized)
        entries.append({"path": relative, "sha256": _sha256_file(path), "size_bytes": path.stat().st_size})
    return {"release_id": RELEASE_ID, "entry_count": len(entries), "entries": entries, "manifest_digest": sha256_digest(entries)}


def _validate_bundle_path(path: Path, *, bundle: Path, relative: str, control_paths: set[str]) -> None:
    if path.is_symlink():
        raise RuntimeError(f"bundle cannot contain symlink: {relative}")
    if Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in Path(relative).parts):
        raise RuntimeError(f"unsafe bundle path: {relative}")
    if path.name in control_paths and relative not in control_paths:
        raise RuntimeError(f"unexpected nested control file: {relative}")
    try:
        path.resolve().relative_to(bundle.resolve())
    except Exception as exc:
        raise RuntimeError(f"bundle path escapes root: {relative}") from exc
    try:
        stat = path.stat()
    except FileNotFoundError:
        return
    if path.is_file() and getattr(stat, "st_nlink", 1) > 1:
        raise RuntimeError(f"bundle cannot contain hard-linked file: {relative}")


def _sha256sums(file_manifest: dict[str, Any]) -> str:
    return "".join(f"{row['sha256'].removeprefix('sha256:')}  {row['path']}\n" for row in file_manifest["entries"])


def _runtime() -> dict[str, Any]:
    return {
        "python": sys.version,
        "git_head": _command(["git", "rev-parse", "HEAD"]),
        "git_status_short": _command(["git", "status", "--short"]),
        "pip_freeze": _command([str(ROOT / ".venv/bin/python"), "-m", "pip", "freeze"]),
    }


def _command(command: list[str]) -> str:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False).stdout


def _readme(hostile: dict[str, Any], expression: dict[str, Any]) -> str:
    return f"""# {RELEASE_ID}

Frozen Phase-3.1 correction release for closed-world entailment and signed provenance.

- Hostile gauntlet: {hostile['blocked_count']}/{hostile['case_count']} attacks blocked (`{hostile['receipt_digest']}`)
- Text/visual joined verification: green (`{expression['receipt_digest']}`)
- Capability/evidence manifest: Ed25519-signed
- Bundle verifier: closed-world file set
- Provider calls: 0
- Production/execution authority: false

Verify: `python3 verify_phase3_1_bundle.py`
"""


def _claims() -> str:
    return """# Claims and limits

Claim: BEAST Phase 3.1 rejects unauthorized extra text/SVG claims, semantic digest marker tampering and summary-only provenance substitution for the bounded Phase-3 multi-domain composition domain.

Nonclaims: this is not public identity proof, independent timestamping, production execution authority, a hardware quorum, or evidence that arbitrary future semantics are solved.

Known limit: the included Ed25519 key is generated for this capsule. It binds the manifest inside the artifact; external identity pinning remains a publication step.
"""


def _authority() -> str:
    return """# Authority map

The signed capability/evidence manifest grants no execution authority. It binds only the closed-world evidence and capability receipts used by the Phase-3.1 verifier. Text and SVG may express only verifier-authorized facts. Production and execution remain false at every gate.
"""


def _reproduce() -> str:
    return """# Clean reproduction

One-command path:

```bash
./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST
```

Environment policy:

- Python 3.11+ with an existing checkout virtual environment at
  `/path/to/clean/EdgeK-BEAST/.venv/bin/python`, or set `PYTHON=/path/to/python`.
- Dependency specifications are provided under `dependencies/` and installed by
  the caller; the reproduction script does not perform network installs.
- The source overlay is non-destructive and refuses to overwrite differing
  source or test files.

Expected commands and outputs:

1. `python3 verify_phase3_1_bundle.py` -> JSON with `"verified": true`.
2. `./install_source_overlay.sh /path/to/clean/EdgeK-BEAST`.
3. Copy bundled `evidence/dai-diode/phase3-composition-001` into the checkout
   without overwriting differing files.
4. Run the eight Phase-3 runners in order.
5. Run the focused Phase-3 test suite; expected output includes `36 passed`.

The predecessor Phase-2.1 ZIP is included as historical input and must not be overwritten.
"""


def _overlay() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: install_source_overlay.sh /path/to/EdgeK-BEAST}
[ -f "$TARGET/pyproject.toml" ] || { echo 'not an EdgeK-BEAST checkout' >&2; exit 65; }
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
copy_tree() {
  local src_root=$1
  local dst_root=$2
  [ -d "$src_root" ] || return 0
  (cd "$src_root" && find . -type f -print0) | while IFS= read -r -d '' file; do
    case "$file" in *"/../"*|"../"*|*"/./"*|"./."*) echo "unsafe overlay path: $file" >&2; exit 66;; esac
    src="$src_root/$file"
    dst="$dst_root/$file"
    if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then
      echo "refusing to overwrite differing file: $dst" >&2
      exit 67
    fi
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  done
}
copy_tree "$SCRIPT_DIR/source" "$TARGET"
copy_tree "$SCRIPT_DIR/tests" "$TARGET"
copy_tree "$SCRIPT_DIR/dependencies" "$TARGET/reproduction-dependencies"
"""


def _clean_reproduction_script() -> str:
    return """#!/usr/bin/env bash
set -euo pipefail
TARGET=${1:?usage: reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN=${PYTHON:-"$TARGET/.venv/bin/python"}
[ -x "$PYTHON_BIN" ] || { echo "missing executable Python: $PYTHON_BIN" >&2; exit 68; }
[ -f "$TARGET/pyproject.toml" ] || { echo "not an EdgeK-BEAST checkout: $TARGET" >&2; exit 65; }

copy_tree() {
  local src_root=$1
  local dst_root=$2
  [ -d "$src_root" ] || return 0
  (cd "$src_root" && find . -type f -print0) | while IFS= read -r -d '' file; do
    case "$file" in *"/../"*|"../"*|*"/./"*|"./."*) echo "unsafe reproduction path: $file" >&2; exit 66;; esac
    local src="$src_root/$file"
    local dst="$dst_root/$file"
    if [ -e "$dst" ] && ! cmp -s "$src" "$dst"; then
      echo "refusing to overwrite differing reproduction file: $dst" >&2
      exit 67
    fi
    mkdir -p "$(dirname "$dst")"
    cp -p "$src" "$dst"
  done
}

python3 "$SCRIPT_DIR/verify_phase3_1_bundle.py"
bash "$SCRIPT_DIR/install_source_overlay.sh" "$TARGET"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase3-composition-001" "$TARGET/evidence/dai-diode/phase3-composition-001"

cd "$TARGET"
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_fossil_registry.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_lockfile_domain.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_certificate_domain.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_composition_graph.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_relevance_pruning.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_residual_route.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_expression.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase3_hostile_gauntlet.py

test_output=$(PYTHONNOUSERSITE=1 "$PYTHON_BIN" -m pytest --noconftest \
  tests/test_dai_phase3_fossil.py \
  tests/test_dai_phase3_lockfile.py \
  tests/test_dai_phase3_certificate.py \
  tests/test_dai_phase3_composition.py \
  tests/test_dai_phase3_expression.py \
  tests/test_dai_phase3_hostile_gauntlet.py \
  -q)
printf '%s\n' "$test_output"
grep -q "36 passed" <<< "$test_output" || { echo "expected 36 passed" >&2; exit 69; }
printf '{"verified":true,"phase":"3.1","expected_tests":"36 passed","provider_calls_used":0,"production_authority_allowed":false,"execution_authority_allowed":false}\\n'
"""


def _verifier() -> str:
    return f'''#!/usr/bin/env python3
import base64, hashlib, json, subprocess, tempfile, unicodedata, zipfile
from pathlib import Path, PurePosixPath
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

class VerificationError(RuntimeError): pass
ROOT = Path(__file__).resolve().parent
HOSTILE_DIGEST = "{HOSTILE_DIGEST}"
EXPRESSION_DIGEST = "{EXPRESSION_DIGEST}"
GRAPH_RECEIPT_DIGEST = "{GRAPH_RECEIPT_DIGEST}"
PREDECESSOR_FILE = "{PRIOR_FOSSIL.name}"
PREDECESSOR_RELEASE_ID = "DAI-Diode-Phase-2.1__Authority-Grade-Stale-Listener-Exact-X2__2026-08-04"
PREDECESSOR_VERIFIER = "verify_phase2_exact_bundle.py"
CONTROL = {{"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json", "RELEASE_MANIFEST.sig.json"}}

if not __debug__:
    raise RuntimeError("Verifier must not run with Python optimization enabled")

def check(condition, message):
    if not condition:
        raise VerificationError(str(message))

def canonical(value):
    if isinstance(value, dict):
        return {{str(k): canonical(value[k]) for k in sorted(value, key=lambda item: str(item))}}
    if isinstance(value, list):
        return [canonical(item) for item in value]
    if isinstance(value, tuple):
        return [canonical(item) for item in value]
    return value

def canonical_json(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def obj_digest(value):
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()

def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1048576), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()

def verify_predecessor_fossil():
    zip_path = ROOT / "prior-fossils" / PREDECESSOR_FILE
    check(zip_path.is_file(), {{"predecessor_zip_missing": PREDECESSOR_FILE}})
    with tempfile.TemporaryDirectory(prefix="dai-predecessor-") as temp:
        temp_root = Path(temp)
        with zipfile.ZipFile(zip_path) as archive:
            names = set()
            required = {{
                PREDECESSOR_RELEASE_ID + "/RELEASE_MANIFEST.json",
                PREDECESSOR_RELEASE_ID + "/SHA256_MANIFEST.json",
                PREDECESSOR_RELEASE_ID + "/SHA256SUMS.txt",
            }}
            for info in archive.infolist():
                name = info.filename
                parts = PurePosixPath(name).parts
                check(parts and parts[0] == PREDECESSOR_RELEASE_ID and not PurePosixPath(name).is_absolute(), {{"unsafe_predecessor_zip_path": name}})
                check(all(part not in ("", ".", "..") for part in parts), {{"unsafe_predecessor_zip_path": name}})
                check(name not in names, {{"duplicate_predecessor_zip_path": name}})
                names.add(name)
            check(not (required - names), {{"predecessor_missing_required_files": sorted(required - names)}})
            archive.extractall(temp_root)
        predecessor_root = temp_root / PREDECESSOR_RELEASE_ID
        verifier = predecessor_root / PREDECESSOR_VERIFIER
        check(verifier.is_file(), {{"predecessor_verifier_missing": PREDECESSOR_VERIFIER}})
        verified = subprocess.run([__import__("sys").executable, str(verifier)], cwd=predecessor_root, text=True, capture_output=True, check=True)
        release = json.loads((predecessor_root / "RELEASE_MANIFEST.json").read_text())
        check(release.get("release_id") == PREDECESSOR_RELEASE_ID, "predecessor release id mismatch")
        claimed = release.get("release_manifest_digest")
        body = dict(release); body.pop("release_manifest_digest", None)
        check(claimed and obj_digest(body) == claimed, "predecessor release manifest digest mismatch")
        file_manifest = json.loads((predecessor_root / "SHA256_MANIFEST.json").read_text())
        if release.get("file_manifest_digest"):
            check(release["file_manifest_digest"] == file_manifest.get("manifest_digest"), "predecessor file manifest digest mismatch")
        return {{
            "beast_object_type": "dai_predecessor_fossil_provenance",
            "predecessor_zip_name": PREDECESSOR_FILE,
            "predecessor_zip_sha256": file_digest(zip_path),
            "release_id": PREDECESSOR_RELEASE_ID,
            "release_manifest_digest": claimed,
            "file_manifest_digest": file_manifest.get("manifest_digest"),
            "verifier_name": PREDECESSOR_VERIFIER,
            "verifier_stdout": verified.stdout.strip(),
            "verified": True,
        }}

def verify_signature(payload_path, signature_path):
    payload = json.loads((ROOT / payload_path).read_text())
    sig = json.loads((ROOT / signature_path).read_text())
    check(sig.get("signed_path") == payload_path, {{"signature_path_mismatch": payload_path}})
    check(sig.get("signed_payload_digest") == obj_digest(payload), {{"signature_payload_digest_mismatch": payload_path}})
    public = base64.b64decode(sig["public_key_b64"], validate=True)
    check("sha256:" + hashlib.sha256(public).hexdigest() == sig.get("key_fingerprint"), {{"key_fingerprint_mismatch": payload_path}})
    Ed25519PublicKey.from_public_bytes(public).verify(base64.b64decode(sig["signature_b64"], validate=True), canonical_json(payload).encode("utf-8"))
    return payload, sig

def safe_rel(path):
    rel = path.relative_to(ROOT).as_posix()
    check(not path.is_symlink(), {{"symlink_rejected": rel}})
    check(not Path(rel).is_absolute() and all(part not in ("", ".", "..") for part in Path(rel).parts), {{"unsafe_path": rel}})
    check(path.name not in CONTROL or rel in CONTROL, {{"nested_control_file": rel}})
    check(path.resolve().is_relative_to(ROOT.resolve()), {{"path_escape": rel}})
    try:
        st = path.stat()
        check(not (path.is_file() and getattr(st, "st_nlink", 1) > 1), {{"hardlink_rejected": rel}})
    except FileNotFoundError:
        pass
    return rel

manifest = json.loads((ROOT / "SHA256_MANIFEST.json").read_text())
check(manifest.get("entry_count") == len(manifest.get("entries", [])), "manifest entry_count mismatch")
check(obj_digest(manifest["entries"]) == manifest.get("manifest_digest"), "manifest digest mismatch")
actual = set()
folded = set()
nfc = set()
for path in ROOT.rglob("*"):
    rel = safe_rel(path)
    if rel in CONTROL:
        continue
    if path.is_file():
        check(rel not in actual, {{"duplicate_path": rel}})
        check(rel.casefold() not in folded, {{"casefold_collision": rel}})
        check(unicodedata.normalize("NFC", rel) not in nfc, {{"unicode_nfc_collision": rel}})
        actual.add(rel); folded.add(rel.casefold()); nfc.add(unicodedata.normalize("NFC", rel))
listed = {{item["path"] for item in manifest["entries"]}}
check(actual == listed, {{"extra_files": sorted(actual - listed), "missing_files": sorted(listed - actual)}})
expected_sums = "".join(item["sha256"].removeprefix("sha256:") + "  " + item["path"] + "\\n" for item in manifest["entries"])
check((ROOT / "SHA256SUMS.txt").read_text() == expected_sums, "SHA256SUMS.txt mismatch")
for item in manifest["entries"]:
    check(file_digest(ROOT / item["path"]) == item["sha256"], {{"file_digest_mismatch": item["path"]}})

capability, capability_sig = verify_signature("CAPABILITY_EVIDENCE_MANIFEST.json", "CAPABILITY_EVIDENCE_MANIFEST.sig.json")
release, release_sig = verify_signature("RELEASE_MANIFEST.json", "RELEASE_MANIFEST.sig.json")
check(capability_sig["key_fingerprint"] == release_sig["key_fingerprint"], "manifest signing keys mismatch")
check(release["capability_evidence_manifest_digest"] == obj_digest(capability), "capability evidence manifest digest mismatch")
check(release["file_manifest_digest"] == manifest["manifest_digest"], "release file manifest digest mismatch")
predecessor = json.loads((ROOT / "PREDECESSOR_PROVENANCE.json").read_text())
check(release["predecessor_provenance_digest"] == obj_digest(predecessor), "predecessor provenance digest mismatch")
actual_predecessor = verify_predecessor_fossil()
check(actual_predecessor == predecessor, {{"predecessor_provenance_mismatch": actual_predecessor}})
check(release["prior_phase2_1_release_manifest_digest"] == predecessor["release_manifest_digest"], "predecessor release digest not bound")

for item in capability["critical_files"]:
    check(file_digest(ROOT / item["path"]) == item["sha256"], {{"critical_file_digest_mismatch": item["path"]}})
hostile = json.loads((ROOT / "evidence/dai-diode/phase3-composition-001/hostile-gauntlet/phase3_hostile_gauntlet_receipt.json").read_text())
expression = json.loads((ROOT / "evidence/dai-diode/phase3-composition-001/composition-graph/phase3_expression_receipt.json").read_text())
graph = json.loads((ROOT / "evidence/dai-diode/phase3-composition-001/composition-graph/phase3_composition_graph_receipt.json").read_text())
check(hostile["receipt_digest"] == HOSTILE_DIGEST and hostile["green"] is True and hostile["case_count"] == 10, "hostile receipt mismatch")
check(expression["receipt_digest"] == EXPRESSION_DIGEST and expression["joined_verification"] is True, "expression receipt mismatch")
check(graph["receipt_digest"] == GRAPH_RECEIPT_DIGEST, "graph receipt mismatch")
print(json.dumps({{"verified": True, "entry_count": manifest["entry_count"], "capability_manifest_digest": obj_digest(capability), "signing_key_fingerprint": capability_sig["key_fingerprint"]}}, sort_keys=True))
'''


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write(path, canonical_json(value) + "\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
