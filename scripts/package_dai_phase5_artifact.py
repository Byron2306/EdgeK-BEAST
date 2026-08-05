#!/usr/bin/env python3
"""Freeze Phase 5 DIO Commons heterogeneous autonomous quorum proof."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest


RELEASE_ID = "DAI-Diode-Phase-5__Heterogeneous-Autonomous-Commons-Quorum__2026-08-04"
PRIOR_FOSSIL = ROOT / "artifacts/DAI-Diode-Phase-4__DIO-Commons-Online-Space-Protocol__2026-08-04.zip"

EVIDENCE_ROOTS = (
    "evidence/dai-diode/phase5-remote-witness-packet",
    "evidence/dai-diode/phase5-hf-witness",
    "evidence/dai-diode/phase5-github-witness",
    "evidence/dai-diode/phase5-mixed-witness-readiness",
    "evidence/dai-diode/phase5-shared-quorum",
)

SOURCE_PATHS = (
    "app/dio_hf_witness_main.py",
    "app/kernel/compute/deterministic_intelligence.py",
    "app/kernel/dai/dio_cloud_attestation.py",
    "app/kernel/dai/dio_cloud_autonomous_packet.py",
    "app/kernel/dai/dio_commons_coordinator.py",
    "app/kernel/dai/dio_distributed_quorum.py",
    "app/kernel/dai/dio_remote_witness_packet.py",
    "scripts/deploy_dio_hf_witness_space.py",
    "scripts/harvest_dio_azure_tee_attestation.py",
    "scripts/harvest_dio_gcp_tee_attestation.py",
    "scripts/mint_dai_phase5_shared_proposal.py",
    "scripts/run_dai_phase5_mixed_witness_readiness.py",
    "scripts/run_dai_phase5_remote_witness_packet_gauntlet.py",
    "scripts/run_dai_phase5_shared_quorum_replay.py",
    "scripts/run_dio_github_actions_witness.py",
    "scripts/verify_dio_azure_maa_token.py",
    "scripts/verify_dio_gcp_attestation_packet.py",
    "scripts/verify_dio_github_actions_witness.py",
    "scripts/verify_dio_hf_witness.py",
    ".github/workflows/dio-remote-witness.yml",
    "deploy/dio-cloud-witness",
    "deploy/dio-hf-witness",
)

TEST_PATHS = (
    "tests/test_dio_cloud_attestation.py",
    "tests/test_dio_cloud_autonomous_packet.py",
    "tests/test_dio_commons_coordinator.py",
    "tests/test_dio_commons_coordinator_runner.py",
    "tests/test_dio_distributed_quorum.py",
    "tests/test_dio_gcp_attestation_packet_verifier.py",
    "tests/test_dio_github_actions_witness.py",
    "tests/test_dio_remote_witness_packet.py",
)

DEPENDENCY_PATHS = ("pyproject.toml", "pytest.ini", "requirements.txt", "requirements-semantic.txt")

EXPECTED = {
    "shared_proposal_packet_digest": "sha256:974d47dcb8f3d46b78f72de97b86a1f7960176423dcea46c37574810650bea86",
    "shared_proposal_digest": "sha256:5df338a298b4f95abcc6edfcdc98772b787848c3cc0694a144110ac3553fcaff",
    "remote_packet_gauntlet_receipt_digest": "sha256:d73ee9ce91657c4492d31561303f15c59d17664a138c2ac3620115ea65c03ce4",
    "hf_shared_receipt_digest": "sha256:a1737d69a90592873087c7a3bdf40d7e118923db53bf6fd96120c99fa9c8da0d",
    "hf_shared_packet_digest": "sha256:334699f9c5d21687874c7ec8a54b1ecd04196b2c877518b1ffc9423d290365f9",
    "github_live_envelope_digest": "sha256:3440cb4385a732ff7160df7061149cb8772e87e8fb2c89caa0912e2e83cf2996",
    "github_live_verification_digest": "sha256:4ce16441ae173eafcaad2b4a12f01220e8cbdb7ee81805bdf75f3002121b4f4f",
    "gcp_physical_envelope_digest": "sha256:de095c739633f7c06a48207b9bdd58085335b0dccf0bdda81e3811cfdb0b2462",
    "gcp_governance_envelope_digest": "sha256:e443ec62d6406f1ea2af14e630bd1d69f2285a2df20536ed97ca01213f02b019",
    "gcp_provider_signature_verification_digest": "sha256:966bf9fb70c48cd9b0cec71132ba6fc4ba90cc3e64e3a27da8ce3d85901c2edf",
    "azure_harvest_digest": "sha256:6b156024ccf83f7106b175b75e65f56b0e2bd4b119004d49125fff1bf96e2bcd",
    "azure_admission_report_digest": "sha256:df5675269c407631b902d706759686b2662d45ac8888ff63ffe75843560b136a",
    "azure_live_verification_digest": "sha256:13cd905ca91ef07b86752d8874d4e6d21e300214e111e883099a943899fd7316",
    "azure_offline_verification_digest": "sha256:e164ff3d76bb6fa6f7eb53dd7f99e1e860f5d2cf0f630a1e5053a2722c168b94",
    "azure_jwks_digest": "sha256:46b7ff1df1b903f9e9b1c1c43363199eea990025ea2852af44add3d14ed677a9",
    "shared_quorum_replay_digest": "sha256:40a463606d84606260aaaaedde538ff691dd37e7f6cf939c4673a56c809e5a16",
    "shared_quorum_report_digest": "sha256:a031335809e7e98609691d56ea297829204eeb6500bfc48a135f3767d558be4d",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-root", type=Path, default=ROOT / "artifacts")
    args = parser.parse_args()
    print(json.dumps(package(out_root=args.out_root), indent=2, sort_keys=True))
    return 0


def package(*, out_root: Path) -> dict[str, Any]:
    evidence = _load_evidence(ROOT)
    _assert_evidence(evidence)
    if not PRIOR_FOSSIL.is_file():
        raise RuntimeError(f"missing Phase-4 predecessor fossil: {PRIOR_FOSSIL}")

    out_root.mkdir(parents=True, exist_ok=True)
    bundle = out_root / RELEASE_ID
    archive = out_root / f"{RELEASE_ID}.zip"
    if bundle.exists() or archive.exists():
        raise RuntimeError("Phase-5 fossil identity already exists; never replace a frozen artifact")

    bundle.mkdir()
    for relative in EVIDENCE_ROOTS:
        _copy_tree(ROOT / relative, bundle / relative)
    _copy_paths(SOURCE_PATHS, bundle / "source")
    _copy_paths(TEST_PATHS, bundle / "tests")
    _copy_paths(DEPENDENCY_PATHS, bundle / "dependencies")
    (bundle / "prior-fossils").mkdir()
    shutil.copy2(PRIOR_FOSSIL, bundle / "prior-fossils" / PRIOR_FOSSIL.name)

    _write(bundle / "README.md", _readme())
    _write(bundle / "CLAIMS_NONCLAIMS_LIMITATIONS.md", _claims())
    _write(bundle / "AUTHORITY_MAP.md", _authority())
    _write(bundle / "CLEAN_ENVIRONMENT_REPRODUCTION.md", _reproduce())
    _write(bundle / "install_source_overlay.sh", _overlay())
    (bundle / "install_source_overlay.sh").chmod(0o755)
    _write(bundle / "reproduce_clean_environment.sh", _clean_reproduction_script())
    (bundle / "reproduce_clean_environment.sh").chmod(0o755)
    _write(bundle / "verify_phase5_bundle.py", _verifier())
    (bundle / "verify_phase5_bundle.py").chmod(0o755)
    _write_json(bundle / "runtime_environment.json", _runtime())

    evidence_manifest = _evidence_manifest(bundle, evidence)
    _write_json(bundle / "PHASE5_EVIDENCE_MANIFEST.json", evidence_manifest)
    file_manifest = _manifest(bundle)
    _write_json(bundle / "SHA256_MANIFEST.json", file_manifest)
    _write(bundle / "SHA256SUMS.txt", _sha256sums(file_manifest))

    release = {
        "beast_object_type": "dai_phase5_heterogeneous_autonomous_commons_quorum_release",
        "release_id": RELEASE_ID,
        "title": "DAI Diode Phase 5 - Heterogeneous Autonomous Commons Quorum",
        "date": "2026-08-04",
        "expected_receipts": EXPECTED,
        "phase5_evidence_manifest_digest": sha256_digest(evidence_manifest),
        "file_manifest_digest": file_manifest["manifest_digest"],
        "prior_phase4_fossil_sha256": _sha256_file(PRIOR_FOSSIL),
        "one_command_verify": "python3 verify_phase5_bundle.py",
        "one_command_clean_reproduce": "./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST",
        "authority_boundary": _authority_boundary(),
        "strongest_claim": (
            "One shared proposal was approved by four independently signed autonomous witness packets "
            "spanning HF, GitHub/Sigstore and GCP remote runtime evidence, with separate Google and Azure "
            "provider attestation verification receipts preserved."
        ),
    }
    release["release_manifest_digest"] = sha256_digest(release)
    _write_json(bundle / "RELEASE_MANIFEST.json", release)

    verified = subprocess.run([sys.executable, str(bundle / "verify_phase5_bundle.py")], cwd=bundle, text=True, capture_output=True, check=True)
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
        "phase5_evidence_manifest_digest": release["phase5_evidence_manifest_digest"],
    }


def _load_evidence(root: Path) -> dict[str, Any]:
    return {
        "proposal": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json"),
        "quorum_replay": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json"),
        "hf": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json"),
        "github": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_verification.json"),
        "gcp_physical": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json"),
        "gcp_governance": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json"),
        "gcp_provider": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/gcp/google-confidential-space-provider-signature-reverification.json"),
        "azure_harvest": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/azure-live-maa-001/dio_azure_tee_attestation_harvest.json"),
        "azure_live": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.json"),
        "azure_offline": _read_json(root / "evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.offline.json"),
        "remote_gauntlet": _read_json(root / "evidence/dai-diode/phase5-remote-witness-packet/phase5_remote_witness_packet_gauntlet_receipt.json"),
    }


def _assert_evidence(evidence: dict[str, Any]) -> None:
    _assert_self_digest(evidence["proposal"], "packet_digest", EXPECTED["shared_proposal_packet_digest"], "shared proposal")
    if evidence["proposal"].get("proposal_digest") != EXPECTED["shared_proposal_digest"]:
        raise RuntimeError("shared proposal digest mismatch")
    _assert_self_digest(evidence["remote_gauntlet"], "receipt_digest", EXPECTED["remote_packet_gauntlet_receipt_digest"], "remote packet gauntlet")
    _assert_self_digest(evidence["hf"], "receipt_digest", EXPECTED["hf_shared_receipt_digest"], "HF shared receipt")
    _assert_self_digest(evidence["github"], "verification_digest", EXPECTED["github_live_verification_digest"], "GitHub verification")
    _assert_self_digest(evidence["gcp_provider"], "verification_digest", EXPECTED["gcp_provider_signature_verification_digest"], "GCP provider verification")
    _assert_self_digest(evidence["azure_harvest"], "harvest_digest", EXPECTED["azure_harvest_digest"], "Azure harvest")
    _assert_self_digest(evidence["azure_live"], "verification_digest", EXPECTED["azure_live_verification_digest"], "Azure live verification")
    _assert_self_digest(evidence["azure_offline"], "verification_digest", EXPECTED["azure_offline_verification_digest"], "Azure offline verification")
    _assert_self_digest(evidence["quorum_replay"], "replay_digest", EXPECTED["shared_quorum_replay_digest"], "shared quorum replay")

    if evidence["hf"].get("verified") is not True or evidence["hf"].get("red_gates") != []:
        raise RuntimeError("HF shared receipt not green")
    if (evidence["hf"].get("autonomous_packet") or {}).get("packet", {}).get("packet_digest") != EXPECTED["hf_shared_packet_digest"]:
        raise RuntimeError("HF autonomous packet digest mismatch")
    if evidence["github"].get("verified") is not True or evidence["github"].get("red_gates") != []:
        raise RuntimeError("GitHub verification not green")
    if evidence["github"].get("envelope_digest") != EXPECTED["github_live_envelope_digest"]:
        raise RuntimeError("GitHub envelope digest mismatch")
    for label, key, expected in (
        ("GCP physical", "gcp_physical", EXPECTED["gcp_physical_envelope_digest"]),
        ("GCP governance", "gcp_governance", EXPECTED["gcp_governance_envelope_digest"]),
    ):
        if evidence[key].get("envelope_digest") != expected:
            raise RuntimeError(f"{label} envelope digest mismatch")
        if evidence[key].get("remote_runtime_observed") is not True:
            raise RuntimeError(f"{label} remote runtime flag missing")
    if evidence["gcp_provider"].get("passed") is not True or evidence["gcp_provider"].get("red_gates") != []:
        raise RuntimeError("GCP provider-signature verification not green")
    if evidence["azure_harvest"].get("green") is not True:
        raise RuntimeError("Azure harvest not green")
    if evidence["azure_harvest"].get("admission_report_digest") != EXPECTED["azure_admission_report_digest"]:
        raise RuntimeError("Azure admission report digest mismatch")
    for key in ("azure_live", "azure_offline"):
        if evidence[key].get("passed") is not True or evidence[key].get("red_gates") != []:
            raise RuntimeError(f"{key} MAA verification not green")
        if evidence[key].get("jwks_digest") != EXPECTED["azure_jwks_digest"]:
            raise RuntimeError(f"{key} JWKS digest mismatch")
    quorum = evidence["quorum_replay"].get("quorum") or {}
    if evidence["quorum_replay"].get("green") is not True or evidence["quorum_replay"].get("red_gates") != []:
        raise RuntimeError("shared quorum replay not green")
    if evidence["quorum_replay"].get("provider_calls_used") != 0:
        raise RuntimeError("shared quorum replay used providers")
    if quorum.get("report_digest") != EXPECTED["shared_quorum_report_digest"]:
        raise RuntimeError("shared quorum report digest mismatch")
    if quorum.get("decision") != "approve" or quorum.get("quorum_class") != "heterogeneous_distributed_quorum":
        raise RuntimeError("shared quorum did not approve as heterogeneous distributed quorum")
    if quorum.get("valid_vote_count") != 4 or quorum.get("admitted_node_count") != 4:
        raise RuntimeError("shared quorum vote/admission count mismatch")
    if quorum.get("hardware_rooted_node_count") != 2:
        raise RuntimeError("shared quorum hardware-rooted node count mismatch")
    required_roles = {"semantic_witness", "adversarial_witness", "physical_execution_witness", "governance_witness"}
    if set(quorum.get("roles_present") or []) != required_roles:
        raise RuntimeError("shared quorum role coverage mismatch")
    for payload in evidence.values():
        if payload.get("production_authority_allowed") not in (None, False):
            raise RuntimeError(f"production authority boundary violated in {payload.get('beast_object_type')}")
        if payload.get("execution_authority_allowed") not in (None, False):
            raise RuntimeError(f"execution authority boundary violated in {payload.get('beast_object_type')}")


def _assert_self_digest(payload: dict[str, Any], field: str, expected: str, label: str) -> None:
    body = dict(payload)
    claimed = body.pop(field, "")
    if claimed != expected:
        raise RuntimeError(f"{label} expected {field} mismatch")
    if sha256_digest(body) != claimed:
        raise RuntimeError(f"{label} {field} does not recompute")


def _evidence_manifest(bundle: Path, evidence: dict[str, Any]) -> dict[str, Any]:
    critical_paths = (
        "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json",
        "evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json",
        "evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json",
        "evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_verification.json",
        "evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json",
        "evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json",
        "evidence/dai-diode/phase5-shared-quorum/gcp/google-confidential-space-provider-signature-reverification.json",
        "evidence/dai-diode/phase5-shared-quorum/azure-live-maa-001/dio_azure_tee_attestation_harvest.json",
        "evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.json",
        "evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.offline.json",
        "evidence/dai-diode/phase5-remote-witness-packet/phase5_remote_witness_packet_gauntlet_receipt.json",
    )
    quorum = evidence["quorum_replay"]["quorum"]
    return {
        "beast_object_type": "dai_phase5_evidence_manifest",
        "release_id": RELEASE_ID,
        "version": "2026-08-04.phase5.heterogeneous-autonomous-quorum.v1",
        "critical_files": [
            {"path": path, "sha256": _sha256_file(bundle / path), "size_bytes": (bundle / path).stat().st_size}
            for path in critical_paths
        ],
        "expected_receipts": EXPECTED,
        "quorum": {
            "proposal_packet_digest": quorum["proposal_packet_digest"],
            "report_digest": quorum["report_digest"],
            "decision": quorum["decision"],
            "quorum_class": quorum["quorum_class"],
            "valid_vote_count": quorum["valid_vote_count"],
            "admitted_node_count": quorum["admitted_node_count"],
            "hardware_rooted_node_count": quorum["hardware_rooted_node_count"],
            "roles_present": quorum["roles_present"],
        },
        "cloud_provider_verification": {
            "google_provider_signature_verified": evidence["gcp_provider"]["passed"],
            "azure_maa_signature_verified": evidence["azure_offline"]["signature"]["signature_verified"],
            "azure_jwks_digest": evidence["azure_offline"]["jwks_digest"],
        },
        "authority_boundary": _authority_boundary(),
    }


def _authority_boundary() -> dict[str, Any]:
    return {
        "provider_calls_used_during_replay": 0,
        "production_authority_allowed": False,
        "execution_authority_allowed": False,
        "quorum_authority": "bounded governance approval of one shared proposal only",
        "hf_boundary": "remote signed software semantic witness",
        "github_boundary": "remote OIDC/Sigstore adversarial software witness",
        "gcp_boundary": "remote runtime packets plus separate provider-signature verification; not full raw AMD VCEK reconstruction",
        "azure_boundary": "Azure MAA provider-service JWT/JWKS/x5c verification; not independent raw SNP VCEK reconstruction",
    }


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.exists():
        raise RuntimeError(f"required tree missing: {source}")
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
    excluded = {"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    folded_seen: set[str] = set()
    nfc_seen: set[str] = set()
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle).as_posix()
        _validate_bundle_path(path, bundle=bundle, relative=relative, control_paths=excluded)
        if relative in excluded or not path.is_file():
            continue
        folded = relative.casefold()
        normalized = unicodedata.normalize("NFC", relative)
        if relative in seen or folded in folded_seen or normalized in nfc_seen:
            raise RuntimeError(f"duplicate/colliding bundle path: {relative}")
        seen.add(relative)
        folded_seen.add(folded)
        nfc_seen.add(normalized)
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
    if path.is_file() and getattr(path.stat(), "st_nlink", 1) > 1:
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

Frozen Phase-5 fossil for the DIO Commons heterogeneous autonomous quorum.

This capsule binds one shared proposal to live/remotely signed witness evidence:

- HF semantic witness receipt: `{EXPECTED['hf_shared_receipt_digest']}`
- GitHub Actions/Sigstore witness verification: `{EXPECTED['github_live_verification_digest']}`
- GCP physical and governance remote envelopes:
  `{EXPECTED['gcp_physical_envelope_digest']}`,
  `{EXPECTED['gcp_governance_envelope_digest']}`
- Google provider-signature verification: `{EXPECTED['gcp_provider_signature_verification_digest']}`
- Azure MAA/JWKS verification: `{EXPECTED['azure_offline_verification_digest']}`
- Shared quorum replay: `{EXPECTED['shared_quorum_replay_digest']}`
- Quorum report: `{EXPECTED['shared_quorum_report_digest']}`

Verify:

```bash
python3 verify_phase5_bundle.py
```
"""


def _claims() -> str:
    return """# Claims, nonclaims and limitations

Claim: Phase 5 demonstrates a bounded heterogeneous autonomous Commons quorum.
Four independently signed autonomous witness packets approved one shared
proposal with role coverage across semantic, adversarial, physical execution
and governance witnesses. The replay used zero providers and granted no
production or execution authority.

Additional claim: Google Confidential Space and Azure Confidential VM evidence
now have provider-service signature verification receipts preserved in the
capsule. Azure verification is replayable offline from the frozen JWKS.

Nonclaim: this is not production authorization. It is not a general-purpose
execution grant. It is not independent AMD VCEK reconstruction of raw SNP
reports. GCP remote shared-quorum packets are remote-runtime signed but the
shared-quorum GCP harvest still records no raw provider token for that specific
packet path; the separate preserved Google Confidential Space token verifies
the provider-signature lane.

Known limitations: independent third-party operation of all Commons nodes is
still the next publication layer. Phase 5 proves the packet law, shared-proposal
quorum law and provider-service attestation closure; public scientific authority
still requires external reproducibility and independent operators.
"""


def _authority() -> str:
    return """# Authority map

The quorum may approve only the exact shared proposal digest packaged here.
HF contributes remote signed semantic-witness authority. GitHub contributes
remote OIDC/Sigstore software witness authority. GCP contributes remote runtime
autonomous witness packets and a separate provider-signature verification lane.
Azure contributes a live Confidential VM MAA/JWKS/x5c attestation verification
lane. None of these grant production execution, provider mutation, secret
access or general BEAST authority.
"""


def _reproduce() -> str:
    return """# Clean reproduction

One-command path:

```bash
./reproduce_clean_environment.sh /path/to/clean/EdgeK-BEAST
```

The script verifies this fossil, installs a non-destructive source overlay into
a clean checkout, copies the bundled evidence, and reruns the offline Azure MAA
verifier plus shared quorum replay verifier paths. It does not perform network
installs and it does not mutate cloud resources.
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

python3 "$SCRIPT_DIR/verify_phase5_bundle.py"
bash "$SCRIPT_DIR/install_source_overlay.sh" "$TARGET"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase5-shared-quorum" "$TARGET/evidence/dai-diode/phase5-shared-quorum"
copy_tree "$SCRIPT_DIR/evidence/dai-diode/phase5-remote-witness-packet" "$TARGET/evidence/dai-diode/phase5-remote-witness-packet"

cd "$TARGET"
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/verify_dio_azure_maa_token.py \
  evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token.jwt \
  --vm-description-file evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_tee_governance_01_vm_description.json \
  --verify-signature \
  --jwks-file evidence/dai-diode/phase5-shared-quorum/azure/azure-maa-jwks.json >/tmp/dio_phase5_azure_offline_verify.json
PYTHONNOUSERSITE=1 "$PYTHON_BIN" scripts/run_dai_phase5_shared_quorum_replay.py >/tmp/dio_phase5_shared_quorum_replay.json
printf '{"verified":true,"phase":"5","provider_calls_used":0,"production_authority_allowed":false,"execution_authority_allowed":false}\\n'
"""


def _verifier() -> str:
    return f'''#!/usr/bin/env python3
import hashlib, json, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent
EXPECTED = {json.dumps(EXPECTED, sort_keys=True)}
CONTROL = {{"SHA256_MANIFEST.json", "SHA256SUMS.txt", "RELEASE_MANIFEST.json"}}
def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def od(value): return "sha256:"+hashlib.sha256(canonical(value).encode()).hexdigest()
def fd(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""): h.update(block)
    return "sha256:"+h.hexdigest()
def check(cond, msg):
    if not cond: raise RuntimeError(str(msg))
def read(path): return json.loads((ROOT/path).read_text())
def self_digest(payload, field, expected, label):
    body=dict(payload); claimed=body.pop(field, "")
    check(claimed == expected, {{label+"_expected_mismatch": claimed}})
    check(od(body) == claimed, {{label+"_digest_recompute_failed": claimed}})
def validate_manifest():
    manifest = read(Path("SHA256_MANIFEST.json"))
    entries = manifest["entries"]
    seen=set(); folded=set(); nfc=set()
    for row in entries:
        rel=row["path"]; path=ROOT/rel
        check(path.is_file(), {{"missing_manifest_path": rel}})
        check(not path.is_symlink(), {{"symlink_manifest_path": rel}})
        check(not Path(rel).is_absolute() and all(part not in ("", ".", "..") for part in Path(rel).parts), {{"unsafe_manifest_path": rel}})
        check(path.name not in CONTROL or rel in CONTROL, {{"nested_control_file": rel}})
        check(rel not in seen and rel.casefold() not in folded and unicodedata.normalize("NFC", rel) not in nfc, {{"colliding_manifest_path": rel}})
        seen.add(rel); folded.add(rel.casefold()); nfc.add(unicodedata.normalize("NFC", rel))
        check(fd(path)==row["sha256"], {{"manifest_digest_mismatch": rel}})
        check(path.stat().st_size==row["size_bytes"], {{"manifest_size_mismatch": rel}})
    check(od(entries)==manifest["manifest_digest"], "manifest digest does not recompute")
    release = read(Path("RELEASE_MANIFEST.json"))
    body=dict(release); claimed=body.pop("release_manifest_digest", "")
    check(claimed and od(body)==claimed, "release manifest digest does not recompute")
    check(release["file_manifest_digest"]==manifest["manifest_digest"], "release/file manifest digest mismatch")
def validate_evidence():
    proposal = read(Path("evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_proposal.json"))
    quorum = read(Path("evidence/dai-diode/phase5-shared-quorum/dio_phase5_shared_quorum_replay.json"))
    hf = read(Path("evidence/dai-diode/phase5-shared-quorum/hf/dio_hf_shared_proposal_witness_receipt.json"))
    github = read(Path("evidence/dai-diode/phase5-shared-quorum/github/run-30960436614/dio_github_actions_autonomous_witness_verification.json"))
    gcp_phys = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp-physical-remote/dio_gcp_autonomous_witness_envelope.json"))
    gcp_gov = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp-governance-remote/dio_gcp_autonomous_witness_envelope.json"))
    gcp_provider = read(Path("evidence/dai-diode/phase5-shared-quorum/gcp/google-confidential-space-provider-signature-reverification.json"))
    azure_harvest = read(Path("evidence/dai-diode/phase5-shared-quorum/azure-live-maa-001/dio_azure_tee_attestation_harvest.json"))
    azure_live = read(Path("evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.json"))
    azure_offline = read(Path("evidence/dai-diode/phase5-shared-quorum/azure/dio_azure_maa_token_verification.offline.json"))
    gauntlet = read(Path("evidence/dai-diode/phase5-remote-witness-packet/phase5_remote_witness_packet_gauntlet_receipt.json"))
    self_digest(proposal, "packet_digest", EXPECTED["shared_proposal_packet_digest"], "proposal")
    check(proposal["proposal_digest"]==EXPECTED["shared_proposal_digest"], "proposal digest mismatch")
    self_digest(quorum, "replay_digest", EXPECTED["shared_quorum_replay_digest"], "quorum")
    self_digest(hf, "receipt_digest", EXPECTED["hf_shared_receipt_digest"], "hf")
    self_digest(github, "verification_digest", EXPECTED["github_live_verification_digest"], "github")
    self_digest(gcp_provider, "verification_digest", EXPECTED["gcp_provider_signature_verification_digest"], "gcp_provider")
    self_digest(azure_harvest, "harvest_digest", EXPECTED["azure_harvest_digest"], "azure_harvest")
    self_digest(azure_live, "verification_digest", EXPECTED["azure_live_verification_digest"], "azure_live")
    self_digest(azure_offline, "verification_digest", EXPECTED["azure_offline_verification_digest"], "azure_offline")
    self_digest(gauntlet, "receipt_digest", EXPECTED["remote_packet_gauntlet_receipt_digest"], "gauntlet")
    check(hf.get("verified") is True and hf.get("red_gates")==[], "HF not green")
    check((hf.get("autonomous_packet") or dict()).get("packet", dict()).get("packet_digest")==EXPECTED["hf_shared_packet_digest"], "HF packet digest mismatch")
    check(github.get("verified") is True and github.get("red_gates")==[], "GitHub not green")
    check(github.get("envelope_digest")==EXPECTED["github_live_envelope_digest"], "GitHub envelope mismatch")
    check(gcp_phys.get("envelope_digest")==EXPECTED["gcp_physical_envelope_digest"] and gcp_phys.get("remote_runtime_observed") is True, "GCP physical mismatch")
    check(gcp_gov.get("envelope_digest")==EXPECTED["gcp_governance_envelope_digest"] and gcp_gov.get("remote_runtime_observed") is True, "GCP governance mismatch")
    check(gcp_provider.get("passed") is True and gcp_provider.get("red_gates")==[], "GCP provider verification not green")
    check(azure_harvest.get("green") is True and azure_harvest.get("admission_report_digest")==EXPECTED["azure_admission_report_digest"], "Azure harvest not green")
    check(azure_live.get("passed") is True and azure_live.get("red_gates")==[] and azure_live.get("jwks_digest")==EXPECTED["azure_jwks_digest"], "Azure live verifier not green")
    check(azure_offline.get("passed") is True and azure_offline.get("red_gates")==[] and azure_offline.get("jwks_digest")==EXPECTED["azure_jwks_digest"], "Azure offline verifier not green")
    report = quorum["quorum"]
    check(quorum.get("green") is True and quorum.get("red_gates")==[] and quorum.get("provider_calls_used")==0, "quorum replay not green/zero-provider")
    check(report.get("report_digest")==EXPECTED["shared_quorum_report_digest"], "quorum report digest mismatch")
    check(report.get("decision")=="approve" and report.get("quorum_class")=="heterogeneous_distributed_quorum", "quorum decision/class mismatch")
    check(report.get("valid_vote_count")==4 and report.get("admitted_node_count")==4 and report.get("hardware_rooted_node_count")==2, "quorum count mismatch")
    check(set(report.get("roles_present") or [])=={{"semantic_witness","adversarial_witness","physical_execution_witness","governance_witness"}}, "quorum role mismatch")
    for payload in (quorum, azure_harvest, azure_live, azure_offline):
        check(payload.get("production_authority_allowed") in (None, False), "production authority boundary violated")
        check(payload.get("execution_authority_allowed") in (None, False), "execution authority boundary violated")
validate_manifest()
validate_evidence()
print(json.dumps({{"verified": True, "release_id": "{RELEASE_ID}", "entry_count": read(Path("SHA256_MANIFEST.json"))["entry_count"], "shared_quorum_report_digest": EXPECTED["shared_quorum_report_digest"], "provider_calls_used": 0, "production_authority_allowed": False, "execution_authority_allowed": False}}, sort_keys=True))
'''


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    _write(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
