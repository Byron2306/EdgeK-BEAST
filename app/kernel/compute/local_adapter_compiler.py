"""Experimental Task 2: Local Adapter Compiler (IEI v0.9 §7.12 Table 14), default-off behind BEAST_ADAPTER_COMPILER.

Compiles one *promoted* coding crystal (structured held-out receipt with an evidence root) plus its *verified*
Episode Envelopes into a local specialist package for the Ollama swarm runners:

    manifest.json        provenance, excluded-episode counts, runtime contract, Governor receipt
    Modelfile            ``FROM <installed base>`` + SYSTEM specialist prompt (crystal program + verified exemplars)
    dataset.jsonl        verified episodes only (tool sequences / digests; never raw tool output)
    training_plan.json   LoRA/PEFT plan (mode=plan); nothing is trained here

Claim boundary: plan mode only. No weights are trained or written; the adapter/specialist may only *propose*;
BEAST verifiers decide. ``ollama create`` is an operator command, never run from here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

COMPILER_ENV = "BEAST_ADAPTER_COMPILER"
SCHEMA = "beast.local_adapter_package.v1"
REJECTED_BASE = re.compile(r"(random|rand-init|randinit|untrained|diagnostic|dummy|tiny-random)", re.I)
FAILED_STATES = {"failed", "error", "cancelled", "canceled", "aborted", "rejected", "timeout"}
RUNTIME_CONTRACT = {
    "adapter_can_execute": False,
    "adapter_may_only_propose": True,
    "crystal_may_only_propose": True,
    "beast_verifiers_decide": True,
    "no_compute_saving_counts_unless_verification_quality_is_preserved": True,
}


def compiler_enabled(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(COMPILER_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


def _sha(value: Any) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def ollama_installed_models(host: str = "http://127.0.0.1:11434", timeout: float = 3.0) -> list[str]:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as response:  # noqa: S310 (loopback only)
            return [str(m.get("name") or "") for m in json.load(response).get("models") or []]
    except (OSError, ValueError):
        return []


class LocalAdapterCompiler:
    def __init__(self, *, registry: Any, envelopes: Any, out_dir: str | Path, governor: Any = None,
                 env: Mapping[str, str] | None = None,
                 installed_models: Callable[[], Iterable[str]] = ollama_installed_models):
        from app.kernel.governance.governor_spine import ComputeGovernorSpine

        self.registry = registry
        self.envelopes = envelopes
        self.out_dir = Path(out_dir)
        self.governor = governor if governor is not None else ComputeGovernorSpine()
        self.env = dict(os.environ if env is None else env)
        self.installed_models = installed_models

    # -- gates -----------------------------------------------------------------------------------------
    def _promoted(self, crystal_id: str) -> dict[str, Any]:
        record = self.registry.get(crystal_id)  # verifies the record digest; raises on tamper
        if record.get("status") != "promoted":
            raise PermissionError(f"crystal {crystal_id} is {record.get('status')!r}; only promoted crystals compile")
        receipt = record.get("receipt") or {}
        if not receipt.get("promoted") or not receipt.get("structured") or not receipt.get("evidence_root"):
            raise PermissionError("compilation requires a structured held-out replay receipt with an evidence root")
        return record

    def _base(self, base_model: str) -> str:
        if REJECTED_BASE.search(base_model):
            raise ValueError(f"base model {base_model!r} looks random-init/diagnostic; refusing")
        installed = {str(name) for name in self.installed_models()}
        if base_model not in installed and f"{base_model}:latest" not in installed:
            raise ValueError(f"base model {base_model!r} is not installed locally (installed: {sorted(installed)})")
        return base_model

    def _verified(self, task_family: str) -> tuple[list[Any], dict[str, int]]:
        from app.kernel.sensorium.episode_envelope import EpisodeEnvelope

        excluded = {"unverified": 0, "failed_state": 0, "tampered": 0}
        with sqlite3.connect(Path(self.envelopes.path)) as connection:  # per-row validation: one bad row != no data
            rows = connection.execute("SELECT payload FROM episode_envelopes WHERE task_family=? ORDER BY created_at",
                                      (task_family,)).fetchall()
        verified = []
        for (payload,) in rows:
            try:
                item = EpisodeEnvelope.from_dict(json.loads(payload))
            except (ValueError, TypeError, KeyError):
                excluded["tampered"] += 1
                continue
            if str(item.state).lower() in FAILED_STATES:
                excluded["failed_state"] += 1
            elif not (item.verification.get("present") and item.verification.get("passed")):
                excluded["unverified"] += 1
            else:
                verified.append(item)
        return verified, excluded

    # -- compile -------------------------------------------------------------------------------------
    def compile(self, crystal_id: str, *, base_model: str = "qwen3:4b", max_exemplars: int = 8) -> dict[str, Any]:
        from app.kernel.governance.governor_spine import Episode, Proposal

        if not compiler_enabled(self.env):
            raise PermissionError(f"local adapter compiler is disabled (set {COMPILER_ENV}=1)")
        record = self._promoted(crystal_id)
        candidate = record["candidate_object"]
        base = self._base(base_model)
        verified, excluded = self._verified(candidate.task_family)
        if not verified:
            raise PermissionError(f"no verified episodes for task family {candidate.task_family!r}; refusing to compile")
        rows = [{"run_id": e.run_id, "envelope_digest": e.envelope_digest, "task_family": e.task_family,
                 "implementation_target": e.implementation_target,
                 "tool_sequence": [s["tool_id"] for s in e.steps],
                 "verification": {"passed": True, "verify_steps": e.verification.get("verify_steps"),
                                  "failures_before_pass": e.verification.get("failures_before_pass")}}
                for e in verified]
        dataset = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
        dataset_digest = _sha(dataset.encode())
        proposal = Proposal(kind="deterministic_tool", crystal_id=crystal_id, tool_id="local_adapter_compiler",
                            signature_material={"dataset": dataset_digest, "base": base},
                            estimate={"tool_calls": 1.0})
        decision = self.governor.admit(Episode(run_id=f"adapter-compile:{crystal_id}"), proposal)
        return self.governor.run_admitted(decision, proposal,
                                          lambda: self._write(record, candidate, base, rows, dataset, dataset_digest,
                                                              excluded, decision, max_exemplars))

    def _write(self, record, candidate, base, rows, dataset, dataset_digest, excluded, decision, max_exemplars):
        name = "beast-" + re.sub(r"[^a-z0-9]+", "-", candidate.task_family.lower()).strip("-") + "-" + \
            candidate.digest.split(":", 1)[1][:12]
        package = self.out_dir / name
        package.mkdir(parents=True, exist_ok=True)
        program = "\n".join(f"  {i + 1}. {s['opcode']}" + (f" (tool {s['tool_id']})" if s["tool_id"] else "") +
                            (f" expect={s['expect']}" if s["expect"] else "") for i, s in enumerate(candidate.steps))
        exemplars = "\n".join(f"  - {r['run_id']}: " + " -> ".join(r["tool_sequence"]) for r in rows[:max_exemplars])
        system = (f"You are a BEAST local specialist for task family '{candidate.task_family}'.\n"
                  "You may only PROPOSE the next tool call; you cannot execute anything. BEAST verifiers decide.\n"
                  f"Promoted crystal {candidate.crystal_id} program:\n{program}\n"
                  f"Verified exemplar tool sequences ({len(rows)} verified episodes):\n{exemplars}\n"
                  "Return a single JSON tool proposal.")
        modelfile = f"FROM {base}\nPARAMETER temperature 0\nSYSTEM \"\"\"\n{system}\n\"\"\"\n"
        peft = importlib.util.find_spec("peft") is not None
        plan = {"schema": "beast.adapter_training_plan.v1", "mode": "plan", "method": "lora",
                "fallback_method": "ollama_specialist_prompt", "base_model": base, "peft_available": peft,
                "dataset_digest": dataset_digest, "examples": len(rows),
                "lora": {"r": 8, "alpha": 16, "dropout": 0.05, "target_modules": ["q_proj", "v_proj"]},
                "preconditions": ["peft + base safetensors available locally (not an Ollama GGUF blob)",
                                  "operator approves training run", "held-out replay re-run on the trained adapter"],
                "training_performed": False}
        manifest = {"schema": SCHEMA, "name": name, "crystal_id": candidate.crystal_id,
                    "crystal_digest": candidate.digest, "task_family": candidate.task_family,
                    "promotion_receipt_digest": _sha(record.get("receipt") or {}),
                    "evidence_root": (record.get("receipt") or {}).get("evidence_root"),
                    "base_model": base, "mode": "plan", "training_performed": False,
                    "dataset_digest": dataset_digest, "examples": len(rows),
                    "source_envelope_digests": [r["envelope_digest"] for r in rows], "excluded": excluded,
                    "runtime_contract": dict(RUNTIME_CONTRACT), "modelfile_digest": _sha(modelfile.encode()),
                    "governor": {"outcome": decision.outcome, "receipt_id": decision.receipt_id,
                                 "receipt_hash": decision.receipt_hash},
                    "compiled_at": time.time()}
        (package / "dataset.jsonl").write_text(dataset, encoding="utf-8")
        (package / "Modelfile").write_text(modelfile, encoding="utf-8")
        (package / "training_plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        command = ["ollama", "create", name, "-f", str(package / "Modelfile")]
        return {"package_dir": str(package), "manifest": manifest, "ollama_create_command": command}


__all__ = ["COMPILER_ENV", "RUNTIME_CONTRACT", "LocalAdapterCompiler", "compiler_enabled", "ollama_installed_models"]
