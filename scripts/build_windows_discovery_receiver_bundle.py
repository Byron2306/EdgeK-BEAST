#!/usr/bin/env python3
"""Build a portable Windows clean-room receiver bundle from current sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "requirements.txt",
    "scripts/setup_beast_windows_discovery_receiver.ps1",
    "scripts/Install-BEASTReceiver.ps1",
    "scripts/run_discovery_agnostic_receiver.py",
    "scripts/verify_discovery_agnostic_receipt.py",
    "scripts/windows_receiver_local_verifier.py",
    "scripts/show_scenario_contract_digests.py",
    "scripts/export_discovery_receiver_fixture.py",
    "docs/windows-discovery-agnostic-receiver-runbook.md",
    "examples/windows-discovery-receiver-scenario.template.json",
    "examples/windows-receiver-verifier-plan.template.json",
    "examples/windows-receiver-config.template.json",
    "app/__init__.py",
    "app/kernel/__init__.py",
    "app/kernel/compute/__init__.py",
    "app/kernel/compute/discovery_agnostic_reuse.py",
    "app/kernel/commons/appraisal_verifier.py",
    "app/kernel/commons/job_choir.py",
    "app/kernel/commons/signature_verifier.py",
    "app/kernel/integration/arda_appraisal.py",
    "app/kernel/integration/signed_decision.py",
    "app/kernel/sensorium/__init__.py",
    "app/kernel/sensorium/contracts_hash.py",
    "app/kernel/sensorium/artifact_taxonomy.py",
    "app/kernel/sensorium/architecture_decisions.py",
    "app/kernel/sensorium/contracts.py",
    "app/kernel/sensorium/physical_effects.py",
    "app/kernel/sensorium/privacy.py",
    "app/kernel/sensorium/network_attribution.py",
    "app/kernel/sensorium/read_model.py",
    "app/kernel/sensorium/adapters.py",
    "app/kernel/sensorium/episode_builder.py",
    "app/kernel/sensorium/event_sequencer.py",
    "app/kernel/sensorium/journal.py",
    "app/kernel/sensorium/observatory.py",
    "app/kernel/sensorium/runtime.py",
    "app/kernel/sensorium/socket_reconciler.py",
    "app/kernel/sensorium/exporter.py",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist/beast-windows-discovery-receiver.zip")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve() if not Path(args.output).is_absolute() else Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "beast_object_type": "beast_windows_discovery_receiver_bundle",
        "version": "1.0",
        "claim_boundary": "receiver tooling only; contains no origin private keys, source corpus, cache, or execution authority",
        "files": [],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in FILES:
            source = ROOT / relative
            if not source.is_file():
                raise FileNotFoundError(source)
            payload = source.read_bytes()
            target = "receiver/" + relative
            archive.writestr(target, payload)
            manifest["files"].append({
                "path": target,
                "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            })
        fixture = ROOT / "dist/windows-receiver-fixture"
        if fixture.is_dir():
            for source in sorted(fixture.iterdir()):
                if source.is_file():
                    payload = source.read_bytes(); target = "receiver/examples/windows-receiver-fixture/" + source.name
                    archive.writestr(target, payload)
                    manifest["files"].append({"path": target, "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
        public_key = ROOT / ".beast/remote-commons-lab/trust-commons/lattice-authority.pub.pem"
        if public_key.is_file():
            payload = public_key.read_bytes()
            archive.writestr("receiver/keys/arda-public-key.pem", payload)
            manifest["files"].append({"path": "receiver/keys/arda-public-key.pem", "sha256": "sha256:" + hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
        archive.writestr("receiver/bundle-manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "bundle": str(output), "bytes": output.stat().st_size,
        "file_count": len(FILES), "manifest_sha256": "sha256:" + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest(),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
