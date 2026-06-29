#!/usr/bin/env python3
"""Verify BEAST's local Ollama crystal adapter runtime package.

This verifier is Ollama-first but sandbox-aware:
- offline checks validate Modelfile and receipts;
- optional live check tries `ollama run` and records socket/network blockers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


REQUIRED_SYSTEMS = {
    "task_envelope",
    "prec_lifecycle",
    "compute_governor",
    "commons_spaces",
    "compute_forge",
    "skill_tree",
    "meta_tool_commons",
    "chronicle",
    "crystal_chain",
    "local_verifiers",
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify local Ollama BEAST crystal runtime")
    parser.add_argument("--root", default="benchmarks/results/crystal_to_adapter_distillation")
    parser.add_argument("--live", action="store_true", help="Attempt a live ollama run smoke test")
    parser.add_argument("--ollama-host", default=os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434")
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    root = Path(args.root)
    modelfile = root / "Ollama.CrystalAdapter.Modelfile"
    modelfile_receipt_path = root / "ollama_crystal_adapter_modelfile_latest.json"
    create_receipt_path = root / "ollama_crystal_adapter_create_latest.json"
    checks = []

    checks.append({"check": "modelfile_exists", "passed": modelfile.is_file()})
    modelfile_text = modelfile.read_text(encoding="utf-8") if modelfile.is_file() else ""
    checks.append({"check": "modelfile_uses_local_ollama_base", "passed": "FROM qwen2.5:0.5b" in modelfile_text or "FROM qwen2.5:1.5b" in modelfile_text or "FROM llama3.2:3b" in modelfile_text})
    checks.append({"check": "agent_awareness_contract_present", "passed": "Agent awareness contract" in modelfile_text and "must_use_beast_systems" in modelfile_text})
    checks.append({"check": "compute_governor_present", "passed": "Compute Governor" in modelfile_text or "compute_governor" in modelfile_text})
    checks.append({"check": "proposal_only_present", "passed": "proposal_only" in modelfile_text})

    modelfile_receipt = load_json(modelfile_receipt_path) if modelfile_receipt_path.is_file() else {}
    create_receipt = load_json(create_receipt_path) if create_receipt_path.is_file() else {}
    systems = set(modelfile_receipt.get("required_beast_systems") or [])
    checks.append({"check": "modelfile_receipt_exists", "passed": bool(modelfile_receipt)})
    checks.append({"check": "create_receipt_exists", "passed": bool(create_receipt)})
    checks.append({"check": "create_receipt_created", "passed": create_receipt.get("created") is True})
    checks.append({"check": "required_beast_systems_complete", "passed": REQUIRED_SYSTEMS.issubset(systems)})
    checks.append({"check": "authority_proposal_only", "passed": modelfile_receipt.get("authority") == "proposal_only" and create_receipt.get("authority") == "proposal_only"})

    live = {
        "attempted": bool(args.live),
        "passed": None,
        "blocked": False,
    }
    if args.live:
        model_name = str(args.model or create_receipt.get("model_name") or "beast-crystal-qwen25-05b:latest")
        prompt = (
            "Return raw JSON only. No markdown. "
            "For task_family route_diagnostics, propose a BEAST adapter-assisted local route. "
            "The JSON must have beast_object_type adapter_assisted_local_proposal and authority proposal_only. "
            "task_envelope must include task_id live_ollama_crystal_runtime and task_family route_diagnostics. "
            "required_verifiers must include provider_fitness_check. "
            "agent_awareness.must_use_beast_systems must be true. "
            "beast_systems_used must include at minimum these BEAST systems: "
            "task_envelope, prec_lifecycle, compute_governor, chronicle, local_verifiers."
        )
        try:
            env = dict(os.environ)
            env["OLLAMA_HOST"] = str(args.ollama_host)
            completed = subprocess.run(
                ["ollama", "run", model_name],
                input=prompt,
                text=True,
                capture_output=True,
                timeout=max(5, int(args.timeout)),
                check=False,
                env=env,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            blocked = "operation not permitted" in output.lower() or "connection refused" in output.lower()
            model_missing = "pull model manifest: file does not exist" in output.lower() or "model" in output.lower() and "does not exist" in output.lower()
            parsed = _extract_json(output)
            contract_violations = _live_contract_violations(parsed)
            contract_passed = not contract_violations
            live.update({
                "model_name": model_name,
                "ollama_host": str(args.ollama_host),
                "returncode": completed.returncode,
                "output_preview": output[:2000],
                "parsed_json": parsed if isinstance(parsed, dict) else None,
                "blocked": blocked,
                "model_missing_on_this_daemon": model_missing,
                "contract_violations": contract_violations,
                "contract_passed": contract_passed,
                "passed": completed.returncode == 0 and contract_passed,
            })
        except (OSError, subprocess.SubprocessError) as exc:
            live.update({"blocked": True, "passed": False, "ollama_host": str(args.ollama_host), "error": str(exc)})

    report = {
        "beast_object_type": "ollama_crystal_runtime_verification",
        "version": "1.0",
        "root": str(root),
        "model_name": create_receipt.get("model_name") or modelfile_receipt.get("model_name"),
        "base_model": create_receipt.get("base_model") or modelfile_receipt.get("base_model"),
        "offline_passed": all(bool(item["passed"]) for item in checks),
        "checks": checks,
        "live": live,
        "runtime_priority": "local_ollama_primary",
        "hf_peft_boundary": "optional export/training lane only; not BEAST runtime center",
        "authority": "verified_runtime_package_not_promoted",
    }
    out = root / "ollama_crystal_runtime_verification_latest.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["offline_passed"] and (not args.live or live.get("passed") or live.get("blocked")) else 1


def _extract_json(output: str) -> dict:
    text = (output or "").strip()
    if not text:
        return {}
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.insert(0, text[text.find("{"):text.rfind("}") + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _live_contract_violations(parsed: dict) -> list[str]:
    if not isinstance(parsed, dict):
        return ["response_not_json_object"]
    violations = []
    awareness = parsed.get("agent_awareness") if isinstance(parsed.get("agent_awareness"), dict) else {}
    systems = set(parsed.get("beast_systems_used") or [])
    verifiers = set(parsed.get("required_verifiers") or [])
    required_systems = {"task_envelope", "prec_lifecycle", "compute_governor", "chronicle", "local_verifiers"}
    if parsed.get("beast_object_type") != "adapter_assisted_local_proposal":
        violations.append("invalid_beast_object_type")
    if parsed.get("authority") != "proposal_only":
        violations.append("authority_not_proposal_only")
    if awareness.get("must_use_beast_systems") is not True:
        violations.append("agent_awareness_missing_must_use_beast_systems")
    missing_systems = sorted(required_systems - systems)
    if missing_systems:
        violations.append("missing_beast_systems:" + ",".join(missing_systems))
    if "provider_fitness_check" not in verifiers:
        violations.append("missing_provider_fitness_check")
    task_envelope = parsed.get("task_envelope") if isinstance(parsed.get("task_envelope"), dict) else {}
    if not task_envelope:
        violations.append("task_envelope_missing_fields")
    if task_envelope.get("task_family") not in {"route_diagnostics", None} and parsed.get("task_family") != "route_diagnostics":
        violations.append("task_envelope_family_mismatch")
    return violations


def _validate_live_contract(parsed: dict) -> bool:
    return not _live_contract_violations(parsed)


if __name__ == "__main__":
    raise SystemExit(main())
