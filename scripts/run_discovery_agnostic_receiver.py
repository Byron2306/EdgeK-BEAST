#!/usr/bin/env python3
"""Run a sealed discovery-agnostic corpus on an attested receiving host.

The scenario deliberately carries only digests/contracts/candidate metadata.
The receiver's local verifier command is responsible for reproducing the task
against its own checked-out state.  Exit status zero means verified; any other
status is a safe miss/provider fallback.  This runner never grants execution
authority from an advertised candidate alone.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.commons.appraisal_verifier import SignedNodeAttestationVerifier
from app.kernel.compute.discovery_agnostic_reuse import (
    CapabilityCandidate,
    DiscoveryAgnosticCorpusRunner,
    DiscoveryAgnosticReuseHarness,
    DiscoveryCorpusCase,
    DiscoveryTask,
    PairedEconomics,
    ReceiverContext,
    SemanticCapabilityContract,
    commons_node_attestation_verifier,
)


def _contract(value: Mapping[str, Any]) -> SemanticCapabilityContract:
    return SemanticCapabilityContract(
        operation=str(value["operation"]), input_schema=dict(value["input_schema"]),
        output_schema=dict(value["output_schema"]),
        invariants=tuple(str(item) for item in value["invariants"]),
        tool_schema_digest=str(value["tool_schema_digest"]), risk_tier=str(value["risk_tier"]),
    )


def _task(value: Mapping[str, Any]) -> DiscoveryTask:
    if "contract" in value:
        return DiscoveryTask.from_contract(
            task_id=str(value["task_id"]), contract=_contract(dict(value["contract"])),
            policy_digest=str(value["policy_digest"]), verifier_digest=str(value["verifier_digest"]),
            state_digest=str(value["state_digest"]), runtime_digest=str(value["runtime_digest"]),
            negative=bool(value.get("negative", False)),
        )
    return DiscoveryTask(**dict(value))


def _candidate(value: Mapping[str, Any]) -> CapabilityCandidate:
    payload = dict(value)
    payload["runtime_compatible_digests"] = tuple(payload.get("runtime_compatible_digests") or ())
    payload["negative_contract_digests"] = tuple(payload.get("negative_contract_digests") or ())
    return CapabilityCandidate(**payload)


def _receiver(value: Mapping[str, Any]) -> ReceiverContext:
    # Attestation truth is derived by SignedNodeAttestationVerifier below; the
    # boolean is not trusted without that verifier.
    payload = dict(value)
    payload["attestation_verified"] = True
    payload["attestation_evidence"] = dict(payload.get("attestation_evidence") or {})
    return ReceiverContext(**payload)


def _economics(value: Mapping[str, Any] | None) -> PairedEconomics | None:
    return PairedEconomics(**dict(value)) if value else None


def _local_verifier(command: str):
    argv = shlex.split(command)
    if not argv:
        raise ValueError("local verifier command is required")

    def verify(task: DiscoveryTask, candidate: CapabilityCandidate) -> bool:
        with tempfile.TemporaryDirectory(prefix="beast-discovery-verify-") as root:
            root_path = Path(root)
            task_path, candidate_path = root_path / "task.json", root_path / "candidate.json"
            task_path.write_text(json.dumps(task.__dict__, sort_keys=True), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate.__dict__, sort_keys=True), encoding="utf-8")
            completed = subprocess.run(
                [*argv, str(task_path), str(candidate_path)], cwd=root_path,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=120, check=False,
            )
            return completed.returncode == 0
    return verify


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", help="sealed scenario JSON")
    parser.add_argument("--arda-public-key", required=True, help="Ed25519 public key for node appraisal verification")
    parser.add_argument("--local-verifier-command", required=True, help="command receiving task.json and candidate.json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    scenario = json.loads(Path(args.scenario).read_text(encoding="utf-8"))
    receiver = _receiver(dict(scenario["receiver"]))
    verifier = SignedNodeAttestationVerifier(args.arda_public_key)
    cases = tuple(DiscoveryCorpusCase(
        case_id=str(item["case_id"]), task=_task(dict(item["task"])),
        candidates=tuple(_candidate(candidate) for candidate in item.get("candidates") or ()),
        expected_admission=bool(item["expected_admission"]), economics=_economics(item.get("economics")),
    ) for item in scenario["cases"])
    result = DiscoveryAgnosticCorpusRunner(DiscoveryAgnosticReuseHarness()).run(
        preregistration=dict(scenario["preregistration"]), origin_host_id=str(scenario["origin_host_id"]),
        receiver=receiver, cases=cases, verifier=_local_verifier(args.local_verifier_command),
        attestation_verifier=commons_node_attestation_verifier(verifier),
    )
    result.validate()
    Path(args.output).write_text(json.dumps(result.__dict__, default=lambda value: value.__dict__, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "verified": True, "receipt_digest": result.receipt_digest,
        "cases": len(result.case_receipts), "unsafe_admissions": result.unsafe_admissions,
        "provider_calls_avoided": result.provider_calls_avoided,
        "measured_economic_cases": result.measured_economic_cases,
        "net_latency_saved_ms": result.net_latency_saved_ms,
        "claim_boundary": "receiver corpus result; publish only after independent review of corpus, verifier, and raw receipts",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
