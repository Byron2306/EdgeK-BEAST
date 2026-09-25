#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

FROZEN_ORGANS: dict[str, str] = {
    "app/kernel/compute/semantic_speech_act.py":
        "c41d85c9d7e0565c875643a10449a081870d6c6445bce7b5f25a8405737f9136",
    "app/kernel/compute/semantic_realization.py":
        "e65ed83f67afb92c55eb930f50a6b129a49150ab976da0ffdd8ab6160fad6524",
    "app/kernel/agents/residual_solver.py":
        "86ac8cc9fb807b0bc84ec7a8d35934ae24d4c822ea49150f8d6fe48e475c0753",
    "app/kernel/compute/lexical_surface.py":
        "116e02b7893a017b2b426ba02ea36999a63e6635e9278608edc4165048260263",
    "app/kernel/compute/lexical_equivalence.py":
        "ba52a84c76f916e4227814a858cba3240f04fd69c8dd3b952a3ce052503c2c41",
    "app/kernel/agents/lexical_surface_realization_provider.py":
        "88ae6abd2f978119511d454d1ba0c779110f2671018007ec5e7c38a4ec83ef76",
    "app/kernel/compute/semantic_surface_recognizer.py":
        "4e505bfa3bd2afa2ff15bbba3544ee367c368ad5a65519a44966b2049bf8cd70",
}

PROSPECTIVE_BINDINGS = (
    "app/kernel/compute/semantic_expression.py",
    "app/kernel/agents/linguistic_realization_provider.py",
    "app/kernel/agents/speech_act_realization_provider.py",
)

REQUIRED_SYMBOLS = {
    "app.kernel.compute.semantic_expression": (
        "SemanticExpressionEngine",
        "compile_semantic_residual_packet",
        "ResidualRouter",
    ),
    "app.kernel.compute.semantic_speech_act": (
        "SemanticSpeechAct",
        "compile_semantic_speech_act",
        "build_speech_act_lexicalization_payload",
    ),
    "app.kernel.compute.semantic_realization": (
        "SemanticRealizationVerifier",
    ),
    "app.kernel.compute.lexical_surface": (
        "compile_lexical_surface",
        "build_lexical_neural_payload",
    ),
    "app.kernel.compute.semantic_surface_recognizer": (
        "recognize_surface",
    ),
    "app.kernel.agents.linguistic_realization_provider": (
        "OllamaLinguisticRealizationProvider",
    ),
    "app.kernel.agents.speech_act_realization_provider": (
        "OllamaSpeechActRealizationProvider",
    ),
    "app.kernel.agents.lexical_surface_realization_provider": (
        "OllamaGovernedLexicalRealizationProvider",
    ),
    "app.kernel.agents.residual_solver": (
        "ResidualSolverBoundary",
    ),
}

ARCHITECTURE_ARMS = {
    "A_FULL_CONTEXT_NEURAL": {
        "relevance_scope": False,
        "pre_neural_speech_act": False,
        "human_lexical_surface": False,
        "post_neural_inverse_recognition": False,
        "provider": "OllamaLinguisticRealizationProvider",
        "purpose": "Neural baseline over the full experimental case surface.",
    },
    "B_RELEVANCE_ROUTED_NEURAL": {
        "relevance_scope": True,
        "pre_neural_speech_act": False,
        "human_lexical_surface": False,
        "post_neural_inverse_recognition": False,
        "provider": "OllamaLinguisticRealizationProvider",
        "purpose": "SC2 relevance routing before otherwise neural realization.",
    },
    "C_PRE_GOVERNED_DIO": {
        "relevance_scope": True,
        "pre_neural_speech_act": True,
        "human_lexical_surface": False,
        "post_neural_inverse_recognition": False,
        "provider": "OllamaSpeechActRealizationProvider",
        "purpose": "SC2 relevance plus SC3.4D speech-act authority before wording.",
    },
    "D_FULL_DIO": {
        "relevance_scope": True,
        "pre_neural_speech_act": True,
        "human_lexical_surface": True,
        "post_neural_inverse_recognition": True,
        "provider": "OllamaGovernedLexicalRealizationProvider",
        "purpose": "Full governed lexical surface plus SC3.4F inverse recognition.",
    },
}

@dataclass(frozen=True)
class OrganReceipt:
    path: str
    sha256: str
    expected_sha256: str | None
    custody: str
    matches_expected: bool | None

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def inspect_frozen_organs() -> list[OrganReceipt]:
    rows: list[OrganReceipt] = []
    for rel, expected in FROZEN_ORGANS.items():
        path = ROOT / rel
        if not path.is_file():
            rows.append(OrganReceipt(rel, "MISSING", expected, "inherited_frozen_sc3_4", False))
            continue
        actual = sha256_file(path)
        rows.append(OrganReceipt(rel, actual, expected, "inherited_frozen_sc3_4", actual == expected))
    return rows

def inspect_prospective_bindings() -> list[OrganReceipt]:
    rows: list[OrganReceipt] = []
    for rel in PROSPECTIVE_BINDINGS:
        path = ROOT / rel
        rows.append(
            OrganReceipt(
                path=rel,
                sha256=sha256_file(path) if path.is_file() else "MISSING",
                expected_sha256=None,
                custody="prospective_sc4_binding",
                matches_expected=None,
            )
        )
    return rows

def inspect_symbols() -> dict[str, dict[str, Any]]:
    report: dict[str, dict[str, Any]] = {}
    for module_name, names in REQUIRED_SYMBOLS.items():
        module = importlib.import_module(module_name)
        module_row: dict[str, Any] = {}
        for name in names:
            value = getattr(module, name, None)
            module_row[name] = {
                "present": value is not None,
                "kind": (
                    "class" if inspect.isclass(value)
                    else "function" if inspect.isfunction(value)
                    else type(value).__name__ if value is not None
                    else None
                ),
            }
        report[module_name] = module_row
    return report

def attachment_status(frozen, symbols):
    failures: list[str] = []
    for row in frozen:
        if row.matches_expected is not True:
            failures.append(f"frozen_organ_drift:{row.path}")
    for module, entries in symbols.items():
        for name, result in entries.items():
            if not result["present"]:
                failures.append(f"missing_symbol:{module}:{name}")
    return ("SC4_PHASE1_ATTACHMENT_READY" if not failures else "SC4_PHASE1_REFUSE", failures)

def build_receipt() -> dict[str, Any]:
    frozen = inspect_frozen_organs()
    prospective = inspect_prospective_bindings()
    symbols = inspect_symbols()
    status, failures = attachment_status(frozen, symbols)
    return {
        "schema": "dio.sc4.phase1.live_attachment_receipt.v1",
        "status": status,
        "failures": failures,
        "confirmatory_provider_calls": 0,
        "confirmatory_observations": 0,
        "execution_authorized": False,
        "frozen_sc3_4_organs": [asdict(x) for x in frozen],
        "prospective_sc4_bindings": [asdict(x) for x in prospective],
        "required_symbols": symbols,
        "architecture_arms": ARCHITECTURE_ARMS,
        "laws": [
            "SC4 reuses frozen SC3.4 organs; it does not rewrite them.",
            "No confirmatory provider call is permitted in Phase 1.",
            "Current SC2/provider digests become prospective SC4 bindings only after review.",
            "A model registry and blocked randomization schedule must be sealed before execution.",
        ],
    }

def main() -> None:
    receipt = build_receipt()
    out = ROOT / "docs/experiments/SC4_PHASE1_LIVE_ATTACHMENT_RECEIPT_V1.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print("receipt", out)
    print("receipt_sha256", sha256_file(out))
    if receipt["status"] != "SC4_PHASE1_ATTACHMENT_READY":
        raise SystemExit(2)

if __name__ == "__main__":
    main()
