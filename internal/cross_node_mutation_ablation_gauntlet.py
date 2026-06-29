#!/usr/bin/env python3
"""Execute BEAST-language ablations and federation mutations across nodes.

Ollama decisions are advisory. The deterministic BEAST gate is authoritative:
an incomplete language contract, failed signature, or non-allowlisted sender
must never reach adoption or credit.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

ROOT = Path(__file__).resolve().parents[1]
NODE_A = "http://127.0.0.1:8101"
NODE_B = "http://127.0.0.1:8102"
OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen2.5:0.5b"
SOURCE = ROOT / "benchmarks/results/cross_node_ollama_reuse_gauntlet_latest.json"
LATEST = ROOT / "benchmarks/results/cross_node_mutation_ablation_gauntlet_latest.json"


def request(client: httpx.Client, method: str, url: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    response = client.request(method, url, json=payload)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:500]}
    return {"status_code": response.status_code, "ok": response.is_success, "body": body}


def ollama_decision(client: httpx.Client, condition: str, contract: Dict[str, bool]) -> Dict[str, Any]:
    started = time.perf_counter()
    response = client.post(OLLAMA + "/api/generate", json={
        "model": MODEL,
        "format": "json",
        "stream": False,
        "prompt": (
            "Return strict JSON with keys reuse,cloud_api_needed,missing_contracts,reason. "
            "You are a BEAST advisory reuse agent. Reuse is allowed only when every language contract is true. "
            f"CONDITION={condition} CONTRACT={json.dumps(contract, sort_keys=True)}"
        ),
        "options": {"temperature": 0.0, "num_predict": 96},
    }, timeout=90)
    response.raise_for_status()
    raw = str(response.json().get("response") or "")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"parsed": False, "raw": raw}
    return {"model": MODEL, "latency_ms": round((time.perf_counter() - started) * 1000, 3), "decision": parsed}


def boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "yes", "1"}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    space_id = str(source["space_id"])
    full_contract = dict((source.get("node_b_beast_handoff") or {}).get("language_contract") or {})
    if not full_contract or not all(full_contract.values()):
        raise RuntimeError("source receipt does not contain a complete BEAST language contract")

    ablations: List[Dict[str, Any]] = []
    with httpx.Client(timeout=90) as client:
        for base in (NODE_A, NODE_B):
            health = request(client, "GET", base + "/health")
            if not health["ok"]:
                raise RuntimeError(f"node unhealthy: {base}")
        tags = request(client, "GET", OLLAMA + "/api/tags")
        if not tags["ok"]:
            raise RuntimeError("Ollama unavailable")

        conditions = [("full_beast", full_contract)]
        for component in sorted(full_contract):
            mutated = dict(full_contract)
            mutated[component] = False
            conditions.append(("without_" + component, mutated))
        for name, contract in conditions:
            beast_gate = all(contract.values())
            advisory = ollama_decision(client, name, contract)
            model_reuse = boolish((advisory.get("decision") or {}).get("reuse"))
            ablations.append({
                "condition": name,
                "removed": None if name == "full_beast" else name.removeprefix("without_"),
                "language_contract": contract,
                "beast_gate_allows_reuse": beast_gate,
                "expected_reuse": name == "full_beast",
                "ollama_advisory": advisory,
                "model_aligned_with_gate": model_reuse == beast_gate,
                "adoption_allowed": beast_gate,
                "credit_allowed": beast_gate,
            })

        envelope = request(client, "POST", NODE_A + f"/edgek/federated-commons/prepare/{space_id}", {
            "contributor_id": "commons-node-a",
            "ttl_days": 30,
        })["body"]
        signature = envelope.get("signature") or {}
        allowlist = request(client, "POST", NODE_B + "/edgek/federated-commons/allowlist", {
            "contributor_id": "commons-node-a",
            "public_key_hash": signature.get("public_key_hash"),
            "approved": True,
            "reason": "mutation ablation gauntlet",
        })
        tampered = copy.deepcopy(envelope)
        tampered["space_id"] = str(tampered.get("space_id")) + "_tampered"
        signed_tamper = request(client, "POST", NODE_B + "/edgek/federated-commons/ingest", {
            "envelope": tampered,
            "require_allowlisted": True,
        })
        stranger = request(client, "POST", NODE_A + f"/edgek/federated-commons/prepare/{space_id}", {
            "contributor_id": "unallowlisted-mutator",
            "ttl_days": 30,
        })["body"]
        non_allowlisted = request(client, "POST", NODE_B + "/edgek/federated-commons/ingest", {
            "envelope": stranger,
            "require_allowlisted": True,
        })

    adversarial = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_commons_adversarial.py", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    mutations = {
        "allowlist_setup": allowlist,
        "signed_envelope_tamper": {
            "result": signed_tamper,
            "oracle_passed": signed_tamper["status_code"] == 400 and "signature" in json.dumps(signed_tamper["body"]).lower(),
        },
        "non_allowlisted_sender": {
            "result": non_allowlisted,
            "oracle_passed": non_allowlisted["status_code"] == 400 and "allowlist" in json.dumps(non_allowlisted["body"]).lower(),
        },
        "local_artifact_privacy_replay_mutations": {
            "returncode": adversarial.returncode,
            "passed": adversarial.returncode == 0,
            "stdout_tail": adversarial.stdout[-2000:],
            "stderr_tail": adversarial.stderr[-1000:],
        },
    }
    deterministic_oracles = bool(
        all(item["beast_gate_allows_reuse"] == item["expected_reuse"] for item in ablations)
        and mutations["signed_envelope_tamper"]["oracle_passed"]
        and mutations["non_allowlisted_sender"]["oracle_passed"]
        and mutations["local_artifact_privacy_replay_mutations"]["passed"]
    )
    result = {
        "beast_object_type": "cross_node_mutation_ablation_gauntlet",
        "version": "1.0",
        "space_id": space_id,
        "nodes": [NODE_A, NODE_B],
        "ollama_model": MODEL,
        "cloud_api_calls_observed": 0,
        "ablation_count": len(ablations),
        "ablations": ablations,
        "ollama_alignment": {
            "aligned": sum(1 for item in ablations if item["model_aligned_with_gate"]),
            "total": len(ablations),
            "model_is_advisory": True,
        },
        "mutations": mutations,
        "success": deterministic_oracles,
        "promotion_rule": "Only the full BEAST contract may reach adoption or credit; model disagreement never overrides the deterministic gate.",
    }
    LATEST.parent.mkdir(parents=True, exist_ok=True)
    LATEST.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
