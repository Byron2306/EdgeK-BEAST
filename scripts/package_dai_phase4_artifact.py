#!/usr/bin/env python3
"""Freeze Phase 4 DIO Commons online/offline witness protocol."""
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


RELEASE_ID = "DAI-Diode-Phase-4__DIO-Commons-Online-Space-Protocol__2026-08-04"
PHASE3_1_FOSSIL = ROOT / "artifacts/DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04.zip"

EVIDENCE_ROOTS = (
    "evidence/dai-diode/phase4-hf-witness",
    "evidence/dai-diode/phase4-commons-adapters",
    "evidence/dai-diode/phase4-commons-coordinator",
    "evidence/dai-diode/phase4-commons-gauntlet",
)
SOURCE_PATHS = (
    "app/dio_hf_witness_main.py",
    "app/kernel/compute/deterministic_intelligence.py",
    "app/kernel/dai/dio_commons_online.py",
    "app/kernel/dai/dio_commons_adapters.py",
    "app/kernel/dai/dio_commons_coordinator.py",
    "app/kernel/dai/dio_distributed_quorum.py",
    "scripts/deploy_dio_hf_witness_space.py",
    "scripts/verify_dio_hf_witness.py",
    "scripts/run_dai_phase4_commons_adapters.py",
    "scripts/run_dai_phase4_commons_coordinator.py",
    "scripts/run_dai_phase4_commons_gauntlet.py",
    "scripts/package_dai_phase4_artifact.py",
    "deploy/dio-hf-witness",
)
TEST_PATHS = (
    "tests/test_dio_commons_online.py",
    "tests/test_dio_commons_adapters.py",
    "tests/test_dio_commons_coordinator.py",
    "tests/test_dio_commons_coordinator_runner.py",
    "tests/test_dio_commons_gauntlet.py",
    "tests/test_dio_distributed_quorum.py",
)
DEPENDENCY_PATHS = ("pyproject.toml", "pytest.ini", "requirements.txt", "requirements-semantic.txt")

EXPECTED = {
    "hf_deployment_digest": "sha256:a8f77fa84cf9b8b278214243ed5cb684fc8913a4e3789b84d1beaaeaf0171119",
    "hf_live_receipt_digest": "sha256:b78c726bbb17e23efa0f7a2ed99e00ed8948e50e6411aa38589c252f3113d5d7",
    "adapter_summary_digest": "sha256:e0ae8ece835d1feb8de3c44805a247e9903914e49d355c662a4c150e9507e603",
    "coordinator_run_digest": "sha256:9eccd5014a56f30f3e25663c969ed1a388ac95de1f8a492a0d56e66a9aac49ab",
    "gauntlet_receipt_digest": "sha256:694f610a863c5e07cb5b5faba1639ed8bd1e3ae1e8957d9724df96c7f86d9ef7",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(json.dumps(package(out_root=args.out_root), indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path) -> dict[str, Any]:
    evidence = _load_phase4_evidence()
    _assert_phase4_evidence(evidence)
    if not PHASE3_1_FOSSIL.is_file():
        raise RuntimeError(f"missing Phase-3.1 predecessor fossil: {PHASE3_1_FOSSIL}")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    archive = out_root / f"{RELEASE_ID}.zip"
    if bundle.exists() or archive.exists():
        raise RuntimeError("Phase-4 fossil identity already exists; never replace a frozen artifact")

    bundle.mkdir()
    for relative in EVIDENCE_ROOTS:
        _copy_tree(ROOT / relative, bundle / relative)
    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    (bundle / "prior-fossils").mkdir()
    shutil.copy2(PHASE3_1_FOSSIL, bundle / "prior-fossils" / PHASE3_1_FOSSIL.name)
    predecessor = _predecessor_fossil_record(
        PHASE3_1_FOSSIL,
        expected_release_id="DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04",
        verifier_name="verify_phase3_1_bundle.py",
    )
    _write_json(bundle / "PREDECESSOR_PROVENANCE.json", predecessor)

    _write(bundle / "README.md", _readme())
    _write(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims())
    _write(bundle / "AUTHORITY_MAP.md", _authority())
    _write(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _reproduce())
    _write(bundle / "install_source_overlay.sh", _overlay())
    (bundle / "install_source_overlay.sh").chmod(0o755)
    _write(bundle / "reproduce_clean_environment.sh", _clean_reproduction_script())
    (bundle / "reproduce_clean_environment.sh").chmod(0o755)
    _write(bundle / "verify_phase4_bundle.py", _verifier())
    (bundle / "verify_phase4_bundle.py").chmod(0o755)
    _write_json(bundle / "runtime_environment.json", _runtime())

    signing_key = Ed25519PrivateKey.generate()
    evidence_manifest = _evidence_manifest(bundle, evidence)
    _write_json(bundle / "PHASE4_EVIDENCE_MANIFEST.json", evidence_manifest)
    _write_json(bundle / "PHASE4_EVIDENCE_MANIFEST.sig.json", _signature_packet(evidence_manifest, signing_key, "PHASE4_EVIDENCE_MANIFEST.json"))

    file_manifest = _manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", file_manifest)
    _write(bundle / "SHA256SUMS.txt", _sha256sums(file_manifest))

    release = {
        "beast_object_type": "dai_phase4_commons_online_release",
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 4 - DIO Commons Online Space Protocol",
        "date": "2026-08-04",
        "expected_receipts": EXPECTED,
        "phase4_evidence_manifest_digest": sha256_digest(evidence_manifest),
        "file_manifest_digest": file_manifest["manifest_digest"],
        "prior_phase3_1_fossil_sha256": _sha256_file(PHASE3_1_FOSSIL),
        "prior_phase3_1_release_manifest_digest": predecessor["release_manifest_digest"],
        "predecessor_provenance_digest": sha256_digest(predecessor),
        "one_command_verify": "python3 verify_phase4_bundle.py",
        "one_command_clean_reproduce": "./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST",
        "authority_boundary": _authority_boundary(),
        "time_boundary": "stored HF vote replay is historical; scripts/verify_dio_hf_witness.py is the fresh live path",
    }
    release["release_manifest_digest"] = sha256_digest(release)
    _write_json(bundle / "RELEASE_MANIFEST.json", release)
    _write_json(bundle / "RELEASE_MANIFEST.sig.json", _signature_packet(release, signing_key, "RELEASE_MANIFEST.json"))

    verified = subprocess.run([sys.executable, str(bundle / "verify_phase4_bundle.py")], cwd=bundle, text=True, capture_output=True, check=True)
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
        "phase4_evidence_manifest_digest": release["phase4_evidence_manifest_digest"],
    }


def _load_phase4_evidence() -> dict[str, dict[str, Any]]:
    return {
        "hf_deployment": _read_json(ROOT / "evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_space_deployment.json"),
        "hf_live": _read_json(ROOT / "evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_live_witness_receipt.json"),
        "adapters": _read_json(ROOT / "evidence/dai-diode/phase4-commons-adapters/dio_phase4_commons_adapter_summary.json"),
        "coordinator": _read_json(ROOT / "evidence/dai-diode/phase4-commons-coordinator/dio_phase4_commons_coordinator_run.json"),
        "gauntlet": _read_json(ROOT / "evidence/dai-diode/phase4-commons-gauntlet/dio_phase4_commons_gauntlet_receipt.json"),
    }


def _assert_phase4_evidence(evidence: dict[str, dict[str, Any]]) -> None:
    if evidence["hf_deployment"]["deployment_digest"] != EXPECTED["hf_deployment_digest"]:
        raise RuntimeError("HF deployment digest mismatch")
    if evidence["hf_live"]["receipt_digest"] != EXPECTED["hf_live_receipt_digest"] or evidence["hf_live"].get("verified") is not True:
        raise RuntimeError("HF live receipt mismatch")
    _assert_self_digest(evidence["adapters"], "summary_digest", EXPECTED["adapter_summary_digest"], "adapter summary")
    _assert_self_digest(evidence["coordinator"], "run_digest", EXPECTED["coordinator_run_digest"], "coordinator run")
    _assert_self_digest(evidence["gauntlet"], "receipt_digest", EXPECTED["gauntlet_receipt_digest"], "Commons gauntlet")
    if evidence["coordinator"].get("green") is not True or evidence["gauntlet"].get("green") is not True:
        raise RuntimeError("Phase-4 coordinator/gauntlet must both be green")
    for value in (evidence["hf_live"], evidence["adapters"], evidence["coordinator"], evidence["gauntlet"]):
        for field in ("provider_calls_used", "production_authority_allowed", "execution_authority_allowed"):
            if field in value and value.get(field) not in (0, False):
                raise RuntimeError(f"authority boundary violated in {value.get('beast_object_type')}: {field}")


def _assert_self_digest(payload: dict[str, Any], field: str, expected: str, label: str) -> None:
    body = dict(payload)
    claimed = body.pop(field, "")
    if claimed != expected or sha256_digest(body) != claimed:
        raise RuntimeError(f"{label} digest does not recompute")


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


def _evidence_manifest(bundle: Path, evidence: dict[str, dict[str, Any]]) -> dict[str, Any]:
    critical_paths = (
        "evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_space_deployment.json",
        "evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_live_witness_receipt.json",
        "evidence/dai-diode/phase4-commons-adapters/dio_phase4_commons_adapter_summary.json",
        "evidence/dai-diode/phase4-commons-coordinator/dio_phase4_commons_coordinator_run.json",
        "evidence/dai-diode/phase4-commons-gauntlet/dio_phase4_commons_gauntlet_receipt.json",
    )
    return {
        "beast_object_type": "dai_phase4_commons_evidence_manifest",
        "release_id": RELEASE_ID,
        "version": "2026-08-04.phase4.commons-release.v1",
        "critical_files": tuple(
            {"path": path, "sha256": _sha256_file(bundle / path), "size_bytes": (bundle / path).stat().st_size}
            for path in critical_paths
        ),
        "expected_receipts": EXPECTED,
        "coordinator": {
            "quorum_class": evidence["coordinator"]["quorum_report"]["quorum_class"],
            "decision": evidence["coordinator"]["quorum_report"]["decision"],
            "admitted_node_count": evidence["coordinator"]["quorum_report"]["admitted_node_count"],
            "valid_vote_count": evidence["coordinator"]["quorum_report"]["valid_vote_count"],
        },
        "gauntlet": {
            "case_count": evidence["gauntlet"]["case_count"],
            "blocked_count": evidence["gauntlet"]["blocked_count"],
            "green": evidence["gauntlet"]["green"],
        },
        "authority_boundary": _authority_boundary(),
        "signature_nonclaim": "This Ed25519 signature binds this capsule manifest, not public identity or third-party time.",
    }


def _signature_packet(payload: dict[str, Any], key: Ed25519PrivateKey, signed_path: str) -> dict[str, Any]:
    public = key.public_key().public_bytes_raw()
    signature = key.sign(canonical_json(payload).encode("utf-8"))
    packet = {
        "beast_object_type": "dai_phase4_ed25519_signature",
        "signed_path": signed_path,
        "signed_payload_digest": sha256_digest(payload),
        "signature_algorithm": "Ed25519",
        "public_key_b64": base64.b64encode(public).decode("ascii"),
        "key_fingerprint": sha256_bytes(public),
        "signature_b64": base64.b64encode(signature).decode("ascii"),
    }
    packet["signature_packet_digest"] = sha256_digest(packet)
    return packet


def _authority_boundary() -> dict[str, Any]:
    return {
        "provider_calls_used": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "online_hf_authority": "remote_signed_software_witness_only",
        "adapter_boundary": "offline/one-shot adapter votes are simulated from local keys and cannot claim persistent online status",
    }


def _copy_tree(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))


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
        resolved = path.resolve()
        root = bundle.resolve()
        resolved.relative_to(root)
    except Exception as exc:
        raise RuntimeError(f"bundle path escapes root: {relative}") from exc
    try:
        stat = path.stat()
    except FileNotFoundError:
        return
    if getattr(stat, "st_nlink", 1) > 1 and path.is_file():
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


def _readme() -> str:
    return f"""# {RELEASE_ID}

Frozen Phase-4 fossil for the DIO Commons Online Space Protocol.

- Live HF signed software Space receipt: `{EXPECTED['hf_live_receipt_digest']}`
- Mixed Commons coordinator: `{EXPECTED['coordinator_run_digest']}`
- Hostile online/offline gauntlet: 11/11 blocked (`{EXPECTED['gauntlet_receipt_digest']}`)
- Provider calls: 0
- Production/execution authority: false

Verify:

```bash
python3 verify_phase4_bundle.py
```
"""


def _claims() -> str:
    return """# Claims, nonclaims and limitations

Claim: Phase 4 demonstrates a bounded Commons protocol where a live HF signed
software witness, GCP/AWS/GitHub/Arda evidence adapters, a shared
proposal/evidence/world/epoch session, role-bound votes and hostile rejection
controls are packaged into one reproducible fossil.

Nonclaims: this is not a full independently attested multi-cloud production
quorum. GCP, AWS, GitHub and Arda records are evidence-bearing adapters, not
persistent online voting Spaces in this release. The stored HF vote is a
historical live receipt; fresh current voting requires running the HF verifier.

Known limitation: adapter votes are simulated from local signing keys because
the adapted witnesses are offline/one-shot evidence sources. Phase 5 should
turn more witness classes into persistent online Spaces or independently
attested autonomous runners.
"""


def _authority() -> str:
    return """# Authority map

HF Space identity can provide remote signed software witness authority only.
Provider hardware adapter receipts can support governance vote simulation only.
Arda local adapter receipts can support physical/execution witness simulation
only. GitHub ephemeral provenance can support semantic/adversarial vote
simulation only. Coordinator quorum may approve the bounded proposition, but it
does not grant provider, production or general execution authority.
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

1. `python3 verify_phase4_bundle.py` -> JSON with `"verified": true`.
2. `./install_source_overlay.sh /path/to/clean/EdgeK-BEAST`.
3. Copy bundled `evidence/dai-diode/phase4-*` trees into the checkout without
   overwriting differing files.
4. Run the coordinator and gauntlet reproduction scripts.
5. Run the focused Commons protocol test suite; expected output includes
   `24 passed`.

For a fresh current HF vote, run `scripts/verify_dio_hf_witness.py` against the
live Space and produce a new receipt rather than mutating this fossil.
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

python3 "$SCRIPT_DIR/verify_phase4_bundle.py"
bash "$SCRIPT_DIR/install_source_overlay.sh" "$TARGET"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase4-hf-witness" "$TARGET/evidence/dai-diode/phase4-hf-witness"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase4-commons-adapters" "$TARGET/evidence/dai-diode/phase4-commons-adapters"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase4-commons-coordinator" "$TARGET/evidence/dai-diode/phase4-commons-coordinator"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase4-commons-gauntlet" "$TARGET/evidence/dai-diode/phase4-commons-gauntlet"

cd "$TARGET"
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase4_commons_coordinator.py
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase4_commons_gauntlet.py

test_output=$(PYTHONNOUSERSITE=1 "$PYTHON_BIN" -m pytest --noconftest \
  tests/test_dio_commons_gauntlet.py \
  tests/test_dio_commons_coordinator.py \
  tests/test_dio_commons_coordinator_runner.py \
  tests/test_dio_commons_adapters.py \
  tests/test_dio_commons_online.py \
  tests/test_dio_distributed_quorum.py \
  -q)
printf '%s\n' "$test_output"
grep -q "24 passed" <<< "$test_output" || { echo "expected 24 passed" >&2; exit 69; }
printf '{"verified":true,"phase":"4","expected_tests":"24 passed","provider_calls_used":0,"production_authority_allowed":false,"execution_authority_allowed":false}\\n'
"""


def _verifier() -> str:
    return f'''#!/usr/bin/env python3
import base64, hashlib, json, subprocess, tempfile, unicodedata, zipfile
from pathlib import Path, PurePosixPath
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
class VerificationError(RuntimeError): pass
ROOT = Path(__file__).resolve().parent
EXPECTED = {json.dumps(EXPECTED, sort_keys=True)}
PREDECESSOR_FILE = "{PHASE3_1_FOSSIL.name}"
PREDECESSOR_RELEASE_ID = "DAI-Diode-Phase-3.1__Closed-World-Entailment-and-Signed-Provenance__2026-08-04"
PREDECESSOR_VERIFIER = "verify_phase3_1_bundle.py"
CONTROL = {{"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json", "RELEASE_MANIFEST.sig.json"}}
if not __debug__:
    raise RuntimeError("Verifier must not run with Python optimization enabled")
def check(condition, message):
    if not condition:
        raise VerificationError(str(message))
def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def file_digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return "sha256:"+h.hexdigest()
def object_digest(value): return "sha256:"+hashlib.sha256(canonical(value).encode()).hexdigest()
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
        check(claimed and object_digest(body) == claimed, "predecessor release manifest digest mismatch")
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
def verify_sig(path, sig_path):
    payload=json.loads((ROOT/path).read_text())
    packet=json.loads((ROOT/sig_path).read_text())
    check(packet.get("signed_path") == path, {{"signature_path_mismatch": path}})
    check(packet.get("signed_payload_digest") == object_digest(payload), {{"signature_payload_digest_mismatch": path}})
    pub=base64.b64decode(packet["public_key_b64"], validate=True)
    check("sha256:"+hashlib.sha256(pub).hexdigest() == packet.get("key_fingerprint"), {{"key_fingerprint_mismatch": path}})
    Ed25519PublicKey.from_public_bytes(pub).verify(base64.b64decode(packet["signature_b64"], validate=True), canonical(payload).encode())
def safe_rel(path):
    rel=path.relative_to(ROOT).as_posix()
    check(not path.is_symlink(), {{"symlink_rejected": rel}})
    check(not Path(rel).is_absolute() and all(part not in ("", ".", "..") for part in Path(rel).parts), {{"unsafe_path": rel}})
    check(path.name not in CONTROL or rel in CONTROL, {{"nested_control_file": rel}})
    check(path.resolve().is_relative_to(ROOT.resolve()), {{"path_escape": rel}})
    try:
        st=path.stat()
        check(not (path.is_file() and getattr(st, "st_nlink", 1) > 1), {{"hardlink_rejected": rel}})
    except FileNotFoundError:
        pass
    return rel
manifest=json.loads((ROOT/"SHA256_MANIFEST.json").read_text())
check(manifest.get("entry_count") == len(manifest.get("entries", [])), "manifest entry_count mismatch")
check(object_digest(manifest["entries"]) == manifest.get("manifest_digest"), "manifest digest mismatch")
actual=set()
folded=set()
nfc=set()
for path in ROOT.rglob("*"):
    rel=safe_rel(path)
    if rel in CONTROL:
        continue
    if path.is_file():
        check(rel not in actual, {{"duplicate_path": rel}})
        check(rel.casefold() not in folded, {{"casefold_collision": rel}})
        check(unicodedata.normalize("NFC", rel) not in nfc, {{"unicode_nfc_collision": rel}})
        actual.add(rel); folded.add(rel.casefold()); nfc.add(unicodedata.normalize("NFC", rel))
listed={{item["path"] for item in manifest["entries"]}}
check(actual == listed, {{"extra_files": sorted(actual-listed), "missing_files": sorted(listed-actual)}})
expected_sums = "".join(item["sha256"].removeprefix("sha256:")+"  "+item["path"]+"\\n" for item in manifest["entries"])
check((ROOT/"SHA256SUMS.txt").read_text() == expected_sums, "SHA256SUMS.txt mismatch")
for item in manifest["entries"]:
    check(file_digest(ROOT/item["path"]) == item["sha256"], {{"file_digest_mismatch": item["path"]}})
verify_sig("PHASE4_EVIDENCE_MANIFEST.json", "PHASE4_EVIDENCE_MANIFEST.sig.json")
verify_sig("RELEASE_MANIFEST.json", "RELEASE_MANIFEST.sig.json")
release=json.loads((ROOT/"RELEASE_MANIFEST.json").read_text())
predecessor=json.loads((ROOT/"PREDECESSOR_PROVENANCE.json").read_text())
check(release["predecessor_provenance_digest"] == object_digest(predecessor), "predecessor provenance digest mismatch")
actual_predecessor=verify_predecessor_fossil()
check(actual_predecessor == predecessor, {{"predecessor_provenance_mismatch": actual_predecessor}})
check(release["prior_phase3_1_release_manifest_digest"] == predecessor["release_manifest_digest"], "predecessor release digest not bound")
hf=json.loads((ROOT/"evidence/dai-diode/phase4-hf-witness/dio_hf_phase4_live_witness_receipt.json").read_text())
adapters=json.loads((ROOT/"evidence/dai-diode/phase4-commons-adapters/dio_phase4_commons_adapter_summary.json").read_text())
coordinator=json.loads((ROOT/"evidence/dai-diode/phase4-commons-coordinator/dio_phase4_commons_coordinator_run.json").read_text())
gauntlet=json.loads((ROOT/"evidence/dai-diode/phase4-commons-gauntlet/dio_phase4_commons_gauntlet_receipt.json").read_text())
check(hf["receipt_digest"] == EXPECTED["hf_live_receipt_digest"] and hf["verified"] is True, "HF receipt mismatch")
for payload, field, key in ((adapters,"summary_digest","adapter_summary_digest"), (coordinator,"run_digest","coordinator_run_digest"), (gauntlet,"receipt_digest","gauntlet_receipt_digest")):
    body=dict(payload); claimed=body.pop(field)
    check(claimed == EXPECTED[key] and object_digest(body) == claimed, {{"object_digest_mismatch": key}})
check(coordinator["green"] is True and gauntlet["green"] is True, "coordinator/gauntlet not green")
check(gauntlet["blocked_count"] == gauntlet["case_count"] == 11, "gauntlet case count mismatch")
print(json.dumps({{"verified": True, "entry_count": manifest["entry_count"], "gauntlet_cases": 11}}, sort_keys=True))
'''


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    _write(path, canonical_json(value) + "\n")


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return "sha256:" + hasher.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
