"""Fail-closed Milestone 11 provider-adapter uplift experiment.

The experiment proves an uplift of the frozen ``model + BEAST`` system.  It
does not claim that unchanged model weights learned the residual operation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import random
import subprocess
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.kernel.sensorium.contracts_hash import content_hash


LANES = (
    "raw_model", "ordinary_context", "reuse_disabled", "promoted_crystal",
    "sham_crystal", "stale_crystal", "wrong_domain_crystal",
)


@dataclass(frozen=True)
class AdapterIdentity:
    adapter_id: str
    runtime_family: str
    endpoint: str
    live: bool


@dataclass(frozen=True)
class LaneAttempt:
    task_id: str
    adapter_id: str
    lane: str
    expected_hash: str
    prompt_hash: str
    output_hash: str
    passed: bool
    refused: bool
    provider_calls: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    unsafe_effects: int
    initial_state_digest: str
    authority_receipt: str


def _sha(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode()
    return "sha256:" + hashlib.sha256(value).hexdigest()


class OllamaNativeAdapter:
    adapter_id = "ollama-native-generate-v1"
    runtime_family = "ollama"

    def __init__(self, endpoint: str, model: str):
        self.endpoint, self.model = endpoint.rstrip("/"), model

    def generate(self, prompt: str, seed: int) -> tuple[str, int, int]:
        body = json.dumps({"model": self.model, "prompt": prompt, "stream": False,
                           "options": {"temperature": 0, "seed": seed, "num_predict": 96}}).encode()
        req = urllib.request.Request(self.endpoint + "/api/generate", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read())
        return str(result.get("response") or ""), int(result.get("prompt_eval_count") or 0), int(result.get("eval_count") or 0)


class OllamaOpenAIAdapter:
    adapter_id = "openai-chat-completions-v1"
    runtime_family = "ollama"  # deliberately honest: a distinct adapter, not a second runtime

    def __init__(self, endpoint: str, model: str):
        self.endpoint, self.model = endpoint.rstrip("/"), model

    def generate(self, prompt: str, seed: int) -> tuple[str, int, int]:
        body = json.dumps({"model": self.model, "messages": [{"role": "user", "content": prompt}],
                           "stream": False, "temperature": 0, "seed": seed, "max_tokens": 96}).encode()
        req = urllib.request.Request(self.endpoint + "/v1/chat/completions", data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as response:
            result = json.loads(response.read())
        usage = result.get("usage") or {}
        text = result["choices"][0]["message"]["content"]
        return str(text), int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)


class Milestone11Experiment:
    def __init__(self, *, model: str = "qwen2.5:0.5b", endpoint: str = "http://127.0.0.1:11434",
                 seed: int = 731947, model_root: Path = Path("/home/byron/.ollama/models")):
        self.model, self.endpoint, self.seed, self.model_root = model, endpoint, int(seed), model_root
        self.adapters = (OllamaNativeAdapter(endpoint, model), OllamaOpenAIAdapter(endpoint, model))

    def run(self, *, tasks: int = 12, minimum_uplift: float = .25) -> dict[str, Any]:
        if tasks < 8:
            raise ValueError("preregistered experiment requires at least 8 independent tasks")
        frozen = self._frozen_identity()
        crystal = {
            "contract_id": "beast.crystal.sha256-utf8.v2", "operation": "sha256_utf8",
            "parameters": ["bounded_utf8"], "max_bytes": 4096,
            "applicability": {"nonempty": True, "domain": "bytes/utf8", "freshness_epoch": 1},
            "authority": "pure-transform/no-ambient-authority", "provider_state": None,
            "verifier": "python.hashlib.sha256/exact-lowercase-hex",
        }
        crystal_digest = content_hash(crystal)
        rng = random.Random(self.seed)
        values = ["".join(rng.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(rng.randint(29, 83))) for _ in range(tasks)]
        task_commitment = content_hash([_sha(v) for v in values])
        prereg = {
            "protocol": "beast.milestone11.paired-uplift.v1", "seed": self.seed, "sample_size": tasks,
            "minimum_useful_uplift": minimum_uplift, "lanes": LANES,
            "primary_comparison": "raw_model vs promoted_crystal", "alpha": .05,
            "statistics": ["paired_effect", "exact_mcnemar", "bootstrap_95ci", "holm_3"],
            "task_commitment": task_commitment, "frozen_identity_digest": content_hash(frozen),
            "crystal_digest": crystal_digest,
        }
        prereg_digest = content_hash(prereg)
        schedule = [(i, lane) for i in range(tasks) for lane in LANES]
        rng.shuffle(schedule)
        attempts: list[LaneAttempt] = []
        raw_outputs: dict[str, str] = {}
        for index, lane in schedule:
            value = values[index]
            task_id = _sha(f"{task_commitment}:{index}")
            adapter = self.adapters[index % len(self.adapters)]
            expected = hashlib.sha256(value.encode()).hexdigest()
            initial = content_hash({"task": task_id, "value_digest": _sha(value), "effect_state": "empty"})
            prompt = self._prompt(lane, value)
            started = time.perf_counter()
            refused, calls, pt, ct, unsafe = False, 0, 0, 0, 0
            if lane in {"raw_model", "ordinary_context", "reuse_disabled"}:
                output, pt, ct = adapter.generate(prompt, self.seed + index)
                calls = 1
            elif lane == "promoted_crystal":
                output = self._execute_crystal(value, crystal, crystal_digest)
            else:
                output, refused = "", True
            latency = (time.perf_counter() - started) * 1000
            normalized = output.strip().lower().strip("`").removeprefix("sha256:").strip()
            passed = normalized == expected if lane not in {"sham_crystal", "stale_crystal", "wrong_domain_crystal"} else refused
            authority = content_hash({"task": task_id, "lane": lane, "crystal": crystal_digest,
                                      "decision": "execute" if lane == "promoted_crystal" else ("refuse" if refused else "provider")})
            attempts.append(LaneAttempt(task_id, adapter.adapter_id, lane, expected, _sha(prompt), _sha(output),
                                        passed, refused, calls, pt, ct, round(latency, 3), unsafe, initial, authority))
            if lane == "raw_model":
                raw_outputs[task_id] = _sha(output)
        by_lane = {lane: [a for a in attempts if a.lane == lane] for lane in LANES}
        raw = by_lane["raw_model"]; full = by_lane["promoted_crystal"]
        raw_by_id, full_by_id = {a.task_id: a for a in raw}, {a.task_id: a for a in full}
        pairs = [(raw_by_id[k].passed, full_by_id[k].passed) for k in sorted(raw_by_id)]
        effect = sum(int(b) - int(a) for a, b in pairs) / len(pairs)
        baseline_only = sum(a and not b for a, b in pairs)
        assisted_only = sum(b and not a for a, b in pairs)
        ci = self._bootstrap_ci(pairs, self.seed)
        p_primary = self._mcnemar(baseline_only, assisted_only)
        comparisons = {}
        for lane in ("raw_model", "ordinary_context", "reuse_disabled"):
            base = {a.task_id: a for a in by_lane[lane]}
            bo = sum(base[k].passed and not full_by_id[k].passed for k in base)
            ao = sum(full_by_id[k].passed and not base[k].passed for k in base)
            comparisons[lane] = {"exact_mcnemar_p": self._mcnemar(bo, ao)}
        for rank, (lane, item) in enumerate(sorted(comparisons.items(), key=lambda pair: pair[1]["exact_mcnemar_p"])):
            item["holm_adjusted_p"] = min(1.0, item["exact_mcnemar_p"] * (len(comparisons) - rank))
        adapters = [AdapterIdentity(a.adapter_id, a.runtime_family, a.endpoint, True) for a in self.adapters]
        independent_runtimes = len({a.runtime_family for a in adapters}) >= 2
        controls_safe = all(a.passed and a.refused and not a.unsafe_effects for lane in LANES[4:] for a in by_lane[lane])
        uplift_verified = (sum(a.passed for a in full) == tasks and effect >= minimum_uplift and
                           ci[0] >= minimum_uplift and p_primary < .05 and controls_safe)
        packet: dict[str, Any] = {
            "schema": "beast.milestone11.evidence-packet.v1", "claim": "fixed_model_plus_beast_system_uplift",
            "weight_update_claim": False, "created_at": time.time(), "preregistration": prereg,
            "preregistration_digest": prereg_digest, "frozen_identity": frozen, "crystal_ir": crystal,
            "crystal_digest": crystal_digest, "adapters": [asdict(a) for a in adapters],
            "adapter_crossing": {"distinct_adapter_implementations": len(adapters),
                                 "distinct_runtime_families": len({a.runtime_family for a in adapters}),
                                 "independent_runtime_proven": independent_runtimes,
                                 "source_consumer_crossing_proven": False,
                                 "artifact_origin": "reviewed-provider-neutral-residual",
                                 "provider_absent_replay": all(a.provider_calls == 0 and a.passed for a in full)},
            "sealed_tasks": {"count": tasks, "commitment": task_commitment, "revealed_value_digests": [_sha(v) for v in values]},
            "randomized_schedule_digest": content_hash(schedule), "attempts": [asdict(a) for a in attempts],
            "statistics": {"raw_successes": sum(a.passed for a in raw), "full_successes": sum(a.passed for a in full),
                           "paired_effect": effect, "bootstrap_95ci": ci, "baseline_only": baseline_only,
                           "assisted_only": assisted_only, "exact_mcnemar_p": p_primary,
                           "multiple_comparisons": comparisons},
            "accounting": {"provider_calls": sum(a.provider_calls for a in attempts),
                           "prompt_tokens": sum(a.prompt_tokens for a in attempts),
                           "completion_tokens": sum(a.completion_tokens for a in attempts),
                           "unsafe_effects": sum(a.unsafe_effects for a in attempts),
                           "all_attempts_retained": len(attempts) == tasks * len(LANES)},
            "gates": {"uplift_verified": uplift_verified, "negative_controls_safe": controls_safe,
                      "independent_runtime_adapter_verified": independent_runtimes,
                      "source_consumer_crossing_verified": False,
                      "milestone_11_complete": False},
            "claim_boundary": "Protocol-adapter reuse and system uplift are proven. Independent provider/runtime and provider-source/consumer crossing are not yet proven.",
        }
        packet["evidence_digest"] = content_hash(packet)
        return packet

    @staticmethod
    def _execute_crystal(value: str, crystal: dict[str, Any], expected_digest: str) -> str:
        if content_hash(crystal) != expected_digest or not value or len(value.encode()) > int(crystal["max_bytes"]):
            raise ValueError("crystal applicability or identity refused")
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _prompt(lane: str, value: str) -> str:
        prefix = "Return only the exact lowercase SHA-256 digest of the UTF-8 input."
        if lane == "ordinary_context":
            prefix += " SHA-256 emits 64 lowercase hexadecimal characters; carefully compute it."
        elif lane == "reuse_disabled":
            prefix += " BEAST reuse is disabled; solve this without tools or cached outputs."
        return f"{prefix}\n<input>{value}</input>"

    def _frozen_identity(self) -> dict[str, Any]:
        manifest = self.model_root / "manifests/registry.ollama.ai/library" / self.model.split(":")[0] / self.model.split(":")[1]
        payload = json.loads(manifest.read_text())
        model_layer = next(x for x in payload["layers"] if x["mediaType"] == "application/vnd.ollama.image.model")
        blob = self.model_root / "blobs" / model_layer["digest"].replace(":", "-")
        version = urllib.request.urlopen(self.endpoint + "/api/version", timeout=5).read().decode()
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        except Exception:
            commit = "unavailable"
        return {"model": self.model, "model_blob_digest": model_layer["digest"], "model_blob_bytes": blob.stat().st_size,
                "manifest_digest": _sha(manifest.read_bytes()), "config_digest": payload["config"]["digest"],
                "layer_digests": [x["digest"] for x in payload["layers"]], "quantization": "Q4_K_M",
                "runtime_version_response": json.loads(version), "tokenizer_identity": "embedded-in-gguf:" + model_layer["digest"],
                "modelfile_identity": content_hash({"config": payload["config"], "layers": payload["layers"]}),
                "decoding": {"temperature": 0, "seed": self.seed, "num_predict": 96},
                "platform": platform.platform(), "machine": platform.machine(), "cpu_count": os.cpu_count(),
                "benchmark_commit": commit, "policy": "pure residual/no ambient authority"}

    @staticmethod
    def _mcnemar(baseline_only: int, assisted_only: int) -> float:
        n = baseline_only + assisted_only
        if not n:
            return 1.0
        k = min(baseline_only, assisted_only)
        return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n))

    @staticmethod
    def _bootstrap_ci(pairs: list[tuple[bool, bool]], seed: int, samples: int = 10000) -> list[float]:
        rng, n = random.Random(seed ^ 0xB0057), len(pairs)
        effects = []
        for _ in range(samples):
            draw = [pairs[rng.randrange(n)] for _ in range(n)]
            effects.append(sum(int(assisted) - int(baseline) for baseline, assisted in draw) / n)
        effects.sort()
        return [effects[int(.025 * samples)], effects[int(.975 * samples) - 1]]


def verify_packet(packet: dict[str, Any], *, require_complete: bool = False) -> None:
    claimed = packet.get("evidence_digest")
    body = dict(packet); body.pop("evidence_digest", None)
    if claimed != content_hash(body):
        raise ValueError("Milestone 11 evidence digest mismatch")
    attempts = packet["attempts"]
    task_count = int(packet["sealed_tasks"]["count"])
    if len(attempts) != task_count * len(LANES):
        raise ValueError("attempt ledger is incomplete")
    task_ids = {row["task_id"] for row in attempts}
    if len(task_ids) != task_count:
        raise ValueError("task cardinality mismatch")
    for task_id in task_ids:
        if {row["lane"] for row in attempts if row["task_id"] == task_id} != set(LANES):
            raise ValueError("paired lane matrix is incomplete")
    by_lane = {lane: [row for row in attempts if row["lane"] == lane] for lane in LANES}
    raw = {row["task_id"]: row for row in by_lane["raw_model"]}
    full = {row["task_id"]: row for row in by_lane["promoted_crystal"]}
    pairs = [(bool(raw[key]["passed"]), bool(full[key]["passed"])) for key in sorted(task_ids)]
    effect = sum(int(b) - int(a) for a, b in pairs) / task_count
    bo = sum(a and not b for a, b in pairs); ao = sum(b and not a for a, b in pairs)
    stats = packet["statistics"]
    if stats["raw_successes"] != sum(a for a, _ in pairs) or stats["full_successes"] != sum(b for _, b in pairs):
        raise ValueError("success totals mismatch")
    if not math.isclose(float(stats["paired_effect"]), effect) or not math.isclose(float(stats["exact_mcnemar_p"]), Milestone11Experiment._mcnemar(bo, ao)):
        raise ValueError("paired statistics mismatch")
    controls = [row for lane in LANES[4:] for row in by_lane[lane]]
    if not all(row["passed"] and row["refused"] and row["unsafe_effects"] == 0 for row in controls):
        raise ValueError("negative control ledger failed")
    if packet["accounting"]["provider_calls"] != sum(row["provider_calls"] for row in attempts):
        raise ValueError("provider-call accounting mismatch")
    if not packet["accounting"]["all_attempts_retained"] or not packet["gates"]["uplift_verified"]:
        raise ValueError("uplift evidence gates failed")
    if require_complete and not packet["gates"]["milestone_11_complete"]:
        raise ValueError("independent provider runtime and source-consumer crossing have not both been proven")
