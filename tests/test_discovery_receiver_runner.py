from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.signature_verifier import canonical_bytes
from app.kernel.compute.discovery_agnostic_reuse import SemanticCapabilityContract
from app.kernel.compute.discovery_agnostic_reuse import read_corpus_receipt
from app.kernel.integration.signed_decision import SignedDecision


def _digest(letter: str) -> str:
    return "sha256:" + letter * 64


def test_receiver_runner_requires_signed_attestation_and_local_verifier(tmp_path):
    private_key = Ed25519PrivateKey.generate()
    public_path = tmp_path / "arda-public.pem"
    public_path.write_bytes(private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    expires_at = time.time() + 60
    node_body = {
        "node_id": "receiver-host", "attestation": "verified", "capabilities": ["cpu", "tpm"],
        "pressure_budget": 0.8, "reliability": 0.9, "route_penalty": 0.0,
        "expires_at": expires_at, "appraisal_ref": "arda:node:receiver",
    }
    request_digest = "sha256:" + hashlib.sha256(canonical_bytes(node_body)).hexdigest()
    decision = SignedDecision("arda", True, request_digest, "policy-1", "nonce-1", "", "arda-key")
    evidence = {
        "appraisal_ref": "arda:node:receiver", "policy_generation": "policy-1",
        "authority": "arda", "state": "verified", "expires_at": expires_at,
        "audience": "commons-job-choir",
        "decision": {
            "authority": "arda", "allowed": True, "request_digest": request_digest,
            "policy_generation": "policy-1", "nonce": "nonce-1",
            "signature": base64.b64encode(private_key.sign(decision.unsigned())).decode("ascii"),
            "verification_material": {"key_id": "arda-key"},
        },
    }
    contract = SemanticCapabilityContract(
        operation="normalize_provider_identifier", input_schema={"provider": "string"},
        output_schema={"provider": "canonical"}, invariants=("case_fold",),
        tool_schema_digest=_digest("c"), risk_tier="low",
    )
    scenario = {
        "preregistration": {"corpus": "integration-v1", "seed": 11}, "origin_host_id": "origin-host",
        "receiver": {
            "host_id": "receiver-host", "physical_host": True, "attestation_expires_at": expires_at,
            "policy_digest": _digest("a"), "verifier_digest": _digest("b"), "state_digest": _digest("d"),
            "runtime_digest": _digest("e"),
            "attestation_evidence": {"node_advertisement": {**node_body, "attestation_evidence": evidence}},
        },
        "cases": [{
            "case_id": "positive", "expected_admission": True,
            "task": {"task_id": "distant-words", "contract": {
                "operation": contract.operation, "input_schema": contract.input_schema,
                "output_schema": contract.output_schema, "invariants": list(contract.invariants),
                "tool_schema_digest": contract.tool_schema_digest, "risk_tier": contract.risk_tier,
            }, "policy_digest": _digest("a"), "verifier_digest": _digest("b"), "state_digest": _digest("d"), "runtime_digest": _digest("e")},
            "candidates": [{
                "candidate_id": "origin-candidate", "semantic_contract_digest": contract.digest,
                "policy_digest": _digest("a"), "verifier_digest": _digest("b"), "state_digest": _digest("d"),
                "runtime_compatible_digests": [_digest("e")], "expires_at": expires_at, "source": "peer_exchange",
            }],
            "economics": {"baseline_provider_ms": 100.0, "discovery_ms": 1.0, "transfer_ms": 1.0,
                          "reproduction_ms": 2.0, "execution_ms": 1.0, "verifier_ms": 1.0},
        }],
    }
    scenario_path, output_path = tmp_path / "scenario.json", tmp_path / "result.json"
    scenario_path.write_text(json.dumps(scenario), encoding="utf-8")
    command = [
        sys.executable, "scripts/run_discovery_agnostic_receiver.py", str(scenario_path),
        "--arda-public-key", str(public_path),
        "--local-verifier-command", f"{sys.executable} -c 'import sys; raise SystemExit(0)'",
        "--output", str(output_path),
    ]
    completed = subprocess.run(command, cwd=Path(__file__).resolve().parents[1], text=True, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output_path.read_text(encoding="utf-8"))
    assert result["unsafe_admissions"] == 0
    assert result["provider_calls_avoided"] == 1
    assert result["measured_economic_cases"] == 1
    verified = read_corpus_receipt(output_path)
    assert verified.provider_calls_avoided == 1
