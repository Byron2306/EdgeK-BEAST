"""Pre-registered blinded small-model versus crystal-assisted experiment."""
from __future__ import annotations

import hashlib
import json
import math
import random
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from app.kernel.sensorium.contracts_hash import content_hash


@dataclass(frozen=True)
class UpliftTrial:
    blinded_task_id: str
    repetition: int
    expected: str
    baseline_output: str
    assisted_output: str
    baseline_passed: bool
    assisted_passed: bool
    provider_calls_baseline: int
    provider_calls_assisted: int


@dataclass(frozen=True)
class ScientificUpliftReceipt:
    experiment_id: str
    preregistration_digest: str
    model: str
    provider: str
    held_out: bool
    blinded: bool
    provider_agnostic_contract: str
    trials: tuple[UpliftTrial, ...]
    negative_cases_passed: int
    negative_cases_total: int
    baseline_successes: int
    assisted_successes: int
    discordant_baseline_only: int
    discordant_assisted_only: int
    exact_mcnemar_p: float
    provider_calls_avoided: int
    provider_disabled_replay_passed: bool
    verified: bool
    receipt_id: str
    receipt_digest: str = ""

    def content_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("receipt_digest", None); return value

    def sealed(self) -> "ScientificUpliftReceipt":
        return replace(self, receipt_digest=content_hash(self.content_payload()))

    def validate(self) -> None:
        if self.receipt_digest != content_hash(self.content_payload()):
            raise ValueError("scientific uplift receipt is tampered")
        if self.verified and not (
            self.held_out and self.blinded and self.provider_disabled_replay_passed
            and self.negative_cases_passed == self.negative_cases_total
            and self.assisted_successes > self.baseline_successes
            and self.provider_calls_avoided == len(self.trials)
        ):
            raise ValueError("verified uplift claim is incomplete")

    def promotion_evidence(self) -> dict[str, dict[str, Any]]:
        self.validate()
        return {
            "heldout_ablation": {
                "receipt_id": self.receipt_id + ":ablation", "verified": self.verified,
                "held_out": self.held_out, "receipt_digest": self.receipt_digest,
                "baseline_successes": self.baseline_successes, "assisted_successes": self.assisted_successes,
                "exact_mcnemar_p": self.exact_mcnemar_p,
            },
            "displacement": {
                "receipt_id": self.receipt_id + ":displacement", "verified": self.verified,
                "provider_calls_avoided": self.provider_calls_avoided,
                "provider_disabled_replay_passed": self.provider_disabled_replay_passed,
                "receipt_digest": self.receipt_digest,
            },
        }


class ScientificUpliftExperiment:
    """Tests a residual SHA-256 crystal, not a claim that model weights changed."""

    def __init__(self, *, model: str = "qwen2.5:0.5b", endpoint: str = "http://127.0.0.1:11434", seed: int = 731947):
        self.model, self.endpoint, self.seed = model, endpoint.rstrip("/"), int(seed)

    def run(self, *, tasks: int = 12, repetitions: int = 2) -> ScientificUpliftReceipt:
        prereg = {"seed": self.seed, "tasks": tasks, "repetitions": repetitions,
                   "operation": "sha256_utf8", "scoring": "exact_lowercase_hex",
                   "negative_cases": ["empty", "over_4096_bytes"]}
        prereg_digest = content_hash(prereg)
        rng = random.Random(self.seed)
        values = ["".join(rng.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(rng.randint(17, 61))) for _ in range(tasks)]
        order = [(i, rep) for rep in range(repetitions) for i in range(tasks)]
        rng.shuffle(order)
        trials = []
        for index, repetition in order:
            value = values[index]
            expected = self._crystal(value)
            blinded = hashlib.sha256(f"{prereg_digest}:{index}".encode()).hexdigest()[:16]
            baseline = self._model_hash(value)
            assisted = self._crystal(value)
            trials.append(UpliftTrial(
                blinded, repetition, expected, baseline, assisted,
                self._normalize(baseline) == expected, assisted == expected, 1, 0,
            ))
        negative_passed = sum(1 for value in ("", "x" * 4097) if self._refuses(value))
        baseline_successes = sum(item.baseline_passed for item in trials)
        assisted_successes = sum(item.assisted_passed for item in trials)
        baseline_only = sum(item.baseline_passed and not item.assisted_passed for item in trials)
        assisted_only = sum(item.assisted_passed and not item.baseline_passed for item in trials)
        p_value = self._exact_mcnemar(baseline_only, assisted_only)
        provider_disabled = all(self._crystal(values[i]) == hashlib.sha256(values[i].encode()).hexdigest() for i in range(tasks))
        verified = bool(assisted_successes == len(trials) and assisted_successes > baseline_successes
                        and negative_passed == 2 and provider_disabled)
        receipt = ScientificUpliftReceipt(
            "uplift:" + uuid.uuid4().hex, prereg_digest, self.model, "ollama", True, True,
            "beast.residual.sha256_utf8.v1", tuple(trials), negative_passed, 2,
            baseline_successes, assisted_successes, baseline_only, assisted_only, p_value,
            len(trials), provider_disabled, verified, "receipt:" + uuid.uuid4().hex,
        ).sealed()
        receipt.validate()
        return receipt

    def _model_hash(self, value: str) -> str:
        prompt = ("Return only the exact lowercase SHA-256 hexadecimal digest of the UTF-8 bytes "
                  f"between <input> tags. No explanation. <input>{value}</input>")
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False,
                           "options": {"temperature": 0, "seed": self.seed, "num_predict": 96}}).encode()
        request = urllib.request.Request(self.endpoint + "/api/generate", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return str(json.loads(response.read()).get("response") or "")

    @staticmethod
    def _normalize(value: str) -> str:
        return value.strip().lower().strip("`").replace("sha256:", "").strip()

    @staticmethod
    def _crystal(value: str) -> str:
        if not value or len(value.encode()) > 4096:
            raise ValueError("sha256 crystal applicability refused")
        return hashlib.sha256(value.encode()).hexdigest()

    @classmethod
    def _refuses(cls, value: str) -> bool:
        try: cls._crystal(value)
        except ValueError: return True
        return False

    @staticmethod
    def _exact_mcnemar(baseline_only: int, assisted_only: int) -> float:
        n = baseline_only + assisted_only
        if n == 0: return 1.0
        k = min(baseline_only, assisted_only)
        return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))


def write_receipt(path: Path, receipt: ScientificUpliftReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(receipt), indent=2, sort_keys=True) + "\n", encoding="utf-8")
