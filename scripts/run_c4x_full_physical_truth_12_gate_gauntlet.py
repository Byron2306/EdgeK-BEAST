#!/usr/bin/env python3
"""Run the full C4-X physical-truth 12-gate gauntlet in one command.

This is the operator-friendly orchestration layer.  It runs the proven
component gauntlets, rebuilds the final physical-truth certificate, writes an
umbrella receipt, and exits non-zero unless all 12 certificate gates are green.

By default it reuses the current privileged sidecar evidence for memfd,
Guardian, and BPF substrate authority.  Add ``--include-sudo-harvest`` when
running from a real terminal if you want to refresh privileged evidence too.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
DEFAULT_SIDECAR = DEFAULT_ROOT / "physical_truth_sidecar_harvested.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="physical-truth-full-12-gate-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--sidecar", default=str(DEFAULT_SIDECAR))
    parser.add_argument("--evidence-root", default=str(DEFAULT_ROOT))
    parser.add_argument("--oqs-helper-container", default="edgek-beast-commons-node-a-1")
    parser.add_argument("--pq-node", default="http://127.0.0.1:8111")
    parser.add_argument("--skip-commons-up", action="store_true")
    parser.add_argument("--include-sudo-harvest", action="store_true")
    parser.add_argument("--skip-sudo", action="store_true", help="Pass --skip-sudo to the sudo harvester after you manually run sudo -v.")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    run_root = Path(args.evidence_root) / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    sidecar = _resolve(args.sidecar)
    python = str(REPO_ROOT / ".venv" / "bin" / "python")
    if not Path(python).exists():
        python = sys.executable

    steps: list[tuple[str, list[str]]] = []
    if not args.skip_commons_up:
        steps.append((
            "commons_lab_up",
            ["docker", "compose", "-f", "docker-compose.commons-lab.yml", "up", "-d", "commons-node-a", "commons-node-b", "commons-node-c"],
        ))
    if args.include_sudo_harvest:
        command = [python, "scripts/run_c4x_sudo_physical_harvest.py", "--run-id", args.run_id + "-sudo-harvest"]
        if args.skip_sudo:
            command.append("--skip-sudo")
        steps.append(("sudo_physical_harvest", command))

    steps.extend([
        (
            "sensorium_bpf_zero_provider",
            [
                python,
                "scripts/run_c4x_sensorium_bpf_zero_provider_episode.py",
                "--run-id",
                args.run_id + "-sensorium-bpf",
                "--sidecar",
                str(sidecar),
            ],
        ),
        (
            "protocol_reuse_route",
            [
                python,
                "scripts/run_c4x_protocol_reuse_route_gauntlet.py",
                "--run-id",
                args.run_id + "-protocol-reuse-route",
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
            ],
        ),
        (
            "commons_ml_kem",
            [
                python,
                "scripts/run_commons_ml_kem_gauntlet.py",
                "--run-id",
                args.run_id + "-commons-ml-kem",
                "--oqs-helper-container",
                args.oqs_helper_container,
            ],
        ),
        (
            "commons_replication",
            [
                python,
                "scripts/run_c4x_commons_replication_gauntlet.py",
                "--run-id",
                args.run_id + "-commons-replication",
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
            ],
        ),
        (
            "psi_governance",
            [
                python,
                "scripts/run_c4x_psi_governance_gauntlet.py",
                "--run-id",
                args.run_id + "-psi-governance",
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
            ],
        ),
        (
            "xdp_scope",
            [
                python,
                "scripts/run_c4x_xdp_scope_gauntlet.py",
                "--run-id",
                args.run_id + "-xdp-scope",
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
            ],
        ),
        (
            "pq_transport",
            [
                python,
                "scripts/run_c4x_pq_transport_gauntlet.py",
                "--run-id",
                args.run_id + "-pq-transport",
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
                "--node",
                args.pq_node,
                "--oqs-helper-container",
                args.oqs_helper_container,
            ],
        ),
        (
            "harden_sidecar_provenance",
            [
                python,
                "scripts/harden_c4x_physical_truth_sidecar.py",
                "--sidecar",
                str(sidecar),
            ],
        ),
        (
            "final_certificate",
            [
                python,
                "scripts/run_c4x_physical_truth_certificate.py",
                "--run-id",
                args.run_id,
                "--sidecar",
                str(sidecar),
                "--evidence-root",
                args.evidence_root,
            ],
        ),
    ])
    if not args.skip_tests:
        steps.append(("certificate_tests", [python, "-m", "pytest", "tests/test_c4x_physical_truth_certificate.py", "-q"]))

    step_receipts = []
    for name, command in steps:
        print(f"\n=== {name} ===", flush=True)
        print(_format_command(command), flush=True)
        started = time.time()
        completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True)
        duration = round(time.time() - started, 3)
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n", flush=True)
        if completed.stderr:
            print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n", file=sys.stderr, flush=True)
        step_receipt = {
            "name": name,
            "command": command,
            "returncode": completed.returncode,
            "duration_seconds": duration,
            "stdout_digest": _sha256_text(completed.stdout),
            "stderr_digest": _sha256_text(completed.stderr),
            "stdout_tail": completed.stdout[-4000:],
            "stderr_tail": completed.stderr[-4000:],
        }
        step_receipts.append(step_receipt)
        _write_umbrella(run_root, args.run_id, sidecar, step_receipts, final_certificate=None)
        if completed.returncode != 0:
            final = _final_payload(run_root, args.run_id, sidecar, step_receipts, final_certificate=None, status="failed")
            print(json.dumps(_summary(final), indent=2, sort_keys=True))
            return completed.returncode or 1

    final_certificate = _load_latest_certificate(Path(args.evidence_root))
    green = [key for key, value in final_certificate.get("certificate_gates", {}).items() if value]
    red = [key for key, value in final_certificate.get("certificate_gates", {}).items() if not value]
    status = "passed" if len(green) == 12 and not red and final_certificate.get("public_credit_allowed") is True else "failed"
    final = _final_payload(run_root, args.run_id, sidecar, step_receipts, final_certificate=final_certificate, status=status)
    receipt_path = _write_umbrella(run_root, args.run_id, sidecar, step_receipts, final_certificate=final_certificate, status=status)
    final["umbrella_receipt"] = str(receipt_path)
    print(json.dumps(_summary(final), indent=2, sort_keys=True))
    return 0 if status == "passed" else 1


def _resolve(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else REPO_ROOT / value


def _load_latest_certificate(evidence_root: Path) -> dict[str, Any]:
    latest = evidence_root / "latest.json"
    if not latest.is_absolute():
        latest = REPO_ROOT / latest
    return json.loads(latest.read_text(encoding="utf-8"))


def _write_umbrella(
    run_root: Path,
    run_id: str,
    sidecar: Path,
    step_receipts: list[dict[str, Any]],
    final_certificate: dict[str, Any] | None,
    status: str = "running",
) -> Path:
    payload = _final_payload(run_root, run_id, sidecar, step_receipts, final_certificate=final_certificate, status=status)
    path = run_root / "full_12_gate_umbrella_receipt.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _final_payload(
    run_root: Path,
    run_id: str,
    sidecar: Path,
    step_receipts: list[dict[str, Any]],
    final_certificate: dict[str, Any] | None,
    status: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "beast_object_type": "c4x_full_physical_truth_12_gate_umbrella",
        "version": "1.0",
        "run_id": run_id,
        "status": status,
        "sidecar": str(sidecar),
        "evidence_root": str(run_root),
        "step_count": len(step_receipts),
        "steps": step_receipts,
        "claim_boundary": (
            "One-shot orchestration receipt. Authority still comes from each "
            "component gate receipt and the final physical-truth certificate; "
            "this wrapper does not average or override failed gates."
        ),
    }
    if final_certificate is not None:
        gates = final_certificate.get("certificate_gates", {})
        payload["final_certificate_digest"] = final_certificate.get("receipt_digest", "")
        payload["public_credit_allowed"] = final_certificate.get("public_credit_allowed") is True
        payload["green_gates"] = [key for key, value in gates.items() if value]
        payload["red_gates"] = [key for key, value in gates.items() if not value]
    payload["receipt_digest"] = _sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return payload


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload["status"],
        "run_id": payload["run_id"],
        "umbrella_receipt": payload.get("umbrella_receipt", str(Path(payload["evidence_root"]) / "full_12_gate_umbrella_receipt.json")),
        "receipt_digest": payload["receipt_digest"],
        "final_certificate_digest": payload.get("final_certificate_digest", ""),
        "public_credit_allowed": payload.get("public_credit_allowed", False),
        "green_count": len(payload.get("green_gates", [])),
        "red_gates": payload.get("red_gates", []),
    }


def _sha256_text(value: str) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _format_command(command: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(item) for item in command)


if __name__ == "__main__":
    raise SystemExit(main())
