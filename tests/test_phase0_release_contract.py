from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from app.kernel.build_identity import load_build_identity

ROOT = Path(__file__).resolve().parents[1]


def test_generated_build_identity_is_consistent_across_surfaces() -> None:
    root_identity = json.loads((ROOT / "build" / "BUILD_IDENTITY.json").read_text(encoding="utf-8"))
    desktop_identity = json.loads((ROOT / "desktop-ide" / "BUILD_IDENTITY.json").read_text(encoding="utf-8"))
    declared = json.loads((ROOT / "release" / "RELEASE_VERSION.json").read_text(encoding="utf-8"))

    assert root_identity == desktop_identity
    assert root_identity["schema"] == "beast.build-identity.v1"
    assert root_identity["product_version"] == declared["product_version"]
    assert root_identity["release_id"] == declared["release_id"]
    assert root_identity["desktop_runtime_version"] == declared["desktop_runtime_version"]
    assert load_build_identity()["identity_digest"] == root_identity["identity_digest"]


def test_parity_contract_has_unique_capabilities_and_known_references() -> None:
    contract = yaml.safe_load((ROOT / "contracts" / "beast-parity-contract.v1.yaml").read_text(encoding="utf-8"))
    capabilities = contract["capabilities"]
    identifiers = [row["id"] for row in capabilities]
    known_tiers = set(contract["tiers"])
    known_verification = set(contract["verification_classes"])

    assert identifiers
    assert len(identifiers) == len(set(identifiers))
    assert all(row["tier"] in known_tiers for row in capabilities)
    assert all(set(row["verification"]).issubset(known_verification) for row in capabilities)
    assert all(row["targets"] for row in capabilities)


def test_desktop_package_matches_declared_runtime_version() -> None:
    package = json.loads((ROOT / "desktop-ide" / "package.json").read_text(encoding="utf-8"))
    declared = json.loads((ROOT / "release" / "RELEASE_VERSION.json").read_text(encoding="utf-8"))
    assert package["version"] == declared["desktop_runtime_version"]


def test_phase0_master_plan_exit_gate_command_validates() -> None:
    result = subprocess.run(
        [str(ROOT / "bin" / "beast"), "--agent", "verify", "release-contract", "--all"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "verify release-contract"
    assert payload["mode"] == "all"
    assert payload["ok"] is True
    assert payload["bundle"]["status"] == "PASS"
    assert payload["bundle"]["failed_checks"] == []
