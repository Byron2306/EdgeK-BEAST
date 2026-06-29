#!/usr/bin/env python3
"""Use BEAST crystal-lattice matrices as a local route/proposal head.

This is the local Ollama-first companion: before asking Ollama, BEAST can use
the trained crystal lattice matrices to predict the closest task family and
emit a verifier-gated proposal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.kernel.crystal_distillation import validate_agent_awareness_proposal


VERIFIER_BY_FAMILY = {
    "schema_validation": "schema_validation",
    "secret_redaction": "privacy_scan",
    "patch_compilation": "py_compile",
    "syntax_check": "py_compile",
    "route_diagnostics": "provider_fitness_check",
    "provider_alias_normalization": "provider_fitness_check",
}


def stable_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def tokens_for_envelope(envelope: Dict[str, Any]) -> List[str]:
    family = str(envelope.get("task_family") or envelope.get("family") or "unknown")
    provider = str(envelope.get("provider") or "local")
    source_provider = str(envelope.get("source_provider") or "")
    fingerprint = str(envelope.get("fingerprint_hash") or stable_hash(envelope))
    positive = str(bool(envelope.get("positive", True)))
    verifiers = envelope.get("required_verifiers") if isinstance(envelope.get("required_verifiers"), list) else []
    labels = envelope.get("labels") if isinstance(envelope.get("labels"), list) else [family]
    out = [
        "task_id:" + stable_hash(envelope.get("task_id") or family),
        "fingerprint:" + fingerprint,
        "provider:" + provider,
        "source_provider:" + source_provider,
        "occurrence_bucket:" + str(envelope.get("occurrence_bucket") or 3),
        "positive:" + positive,
    ]
    out.extend("verifier:" + str(v) for v in verifiers)
    out.extend("behavior:" + str(v) for v in labels)
    return out


def vectorize(tokens: List[str], dimension: int) -> np.ndarray:
    x = np.zeros((dimension,), dtype=np.float32)
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        x[bucket] += sign
    norm = float(np.linalg.norm(x))
    return x / norm if norm else x


def softmax(logits: np.ndarray) -> np.ndarray:
    logits = logits - logits.max()
    exp = np.exp(logits)
    return exp / exp.sum()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BEAST crystal LoRA lattice route head")
    parser.add_argument("--weights", default="benchmarks/results/crystal_to_adapter_distillation/crystal_lora_lattice_weights_latest.npz")
    parser.add_argument("--task-family", default="schema_validation")
    parser.add_argument("--task-id", default="operator_route")
    parser.add_argument("--provider", default="local")
    parser.add_argument("--fingerprint-hash", default="")
    parser.add_argument("--json", dest="json_payload", default="", help="Optional full task envelope JSON")
    parser.add_argument("--output", default="benchmarks/results/crystal_to_adapter_distillation/crystal_lora_route_head_latest.json")
    args = parser.parse_args()

    envelope: Dict[str, Any] = json.loads(args.json_payload) if args.json_payload else {
        "task_family": args.task_family,
        "task_id": args.task_id,
        "provider": args.provider,
        "fingerprint_hash": args.fingerprint_hash or stable_hash({"task_family": args.task_family, "task_id": args.task_id}),
        "positive": True,
        "labels": [args.task_family],
        "required_verifiers": [VERIFIER_BY_FAMILY.get(args.task_family, "behavior_verifier")],
    }
    data = np.load(args.weights, allow_pickle=True)
    a = data["lora_A"].astype(np.float32)
    b = data["lora_B"].astype(np.float32)
    bias = data["bias"].astype(np.float32)
    families = [str(x) for x in data["families"].tolist()]
    x = vectorize(tokens_for_envelope(envelope), a.shape[0])
    logits = (x @ a) @ b + bias
    probs = softmax(logits)
    order = list(np.argsort(-probs))
    predicted = families[int(order[0])]
    verifier = VERIFIER_BY_FAMILY.get(predicted, "behavior_verifier")
    proposal = {
        "beast_object_type": "adapter_assisted_local_proposal",
        "task_family": predicted,
        "task_envelope": envelope,
        "prec_stage": "reason",
        "action_ir": {"route": "crystal_lora_route_head_then_local_ollama_if_needed"},
        "required_verifiers": sorted(set([verifier] + list(envelope.get("required_verifiers") or []))),
        "beast_systems_used": [
            "task_envelope",
            "prec_lifecycle",
            "compute_governor",
            "commons_spaces",
            "compute_forge",
            "skill_tree",
            "chronicle",
            "crystal_chain",
            "local_verifiers",
        ],
        "agent_awareness": {"linked": True, "authority": "proposal_only", "must_use_beast_systems": True},
        "risk_notes": ["matrix route head is advisory; local verifiers required"],
        "authority": "proposal_only",
    }
    report = {
        "beast_object_type": "crystal_lora_route_head_receipt",
        "version": "1.0",
        "weights": args.weights,
        "input_envelope": envelope,
        "predicted_task_family": predicted,
        "confidence": round(float(probs[int(order[0])]), 6),
        "top3": [
            {"task_family": families[int(i)], "score": round(float(probs[int(i)]), 6)}
            for i in order[:3]
        ],
        "proposal": proposal,
        "proposal_validation": validate_agent_awareness_proposal(proposal),
        "authority": "matrix_advisory_only",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["proposal_validation"].get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
