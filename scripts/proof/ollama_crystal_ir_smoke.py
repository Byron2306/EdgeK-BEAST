#!/usr/bin/env python3
"""Ask a local Ollama model for Crystal IR and validate it without mutation."""
from __future__ import annotations

import json
import hashlib
import os
import resource
import sys
import time
import zipfile
from pathlib import Path
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.kernel.compute.crystal_ir import CRYSTAL_IR_TRANSLATOR_SCHEMA, compile_crystal_ir_from_intent, compile_intent_candidate, translator_prompt


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def write_evidence_pack(receipt_path: Path, *, receipt: dict, payload: dict, prompt: str, body: dict, started: float, cpu_start: resource.struct_rusage) -> Path:
    """Write a replayable, phase-level evidence bundle beside the receipt."""
    pack = receipt_path.with_name(receipt_path.stem + "_pack")
    pack.mkdir(parents=True, exist_ok=True)
    elapsed_ns = int((time.perf_counter() - started) * 1_000_000_000)
    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    cpu_ns = int(((cpu_end.ru_utime - cpu_start.ru_utime) + (cpu_end.ru_stime - cpu_start.ru_stime)) * 1_000_000_000)
    usage = {key: body.get(key) for key in ("total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}
    phase = {
        "wall_elapsed_ns": elapsed_ns,
        "process_cpu_ns": cpu_ns,
        "ollama": usage,
        "derived_ms": {
            "load": round((usage.get("load_duration") or 0) / 1_000_000, 3),
            "prefill": round((usage.get("prompt_eval_duration") or 0) / 1_000_000, 3),
            "decode": round((usage.get("eval_duration") or 0) / 1_000_000, 3),
            "total": round((usage.get("total_duration") or 0) / 1_000_000, 3),
        },
        "cpu": {"logical_cpus": os.cpu_count(), "affinity_cpus": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else []},
    }
    request_manifest = {
        "model": payload["model"],
        "endpoint": os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate",
        "options": payload["options"],
        "stream": False,
        "format_schema_sha256": "sha256:" + hashlib.sha256(json.dumps(payload["format"], sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "prompt_sha256": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
        "prompt_chars": len(prompt),
        "prompt_bytes": len(prompt.encode()),
        "keep_alive": payload["keep_alive"],
    }
    artifacts = {
        "translation_receipt.json": receipt,
        "request_manifest.json": request_manifest,
        "phase_telemetry.json": phase,
        "model_response_metadata.json": {"response_sha256": "sha256:" + hashlib.sha256(str(body.get("response") or "").encode()).hexdigest(), "response_present": bool(body.get("response")), "provider_called": True, "mutation_performed": False},
        "verification_report.json": {"schema_constrained": True, "semantic_candidate_valid": bool(receipt.get("valid")), "canonical_ir_compiled": bool(receipt.get("ir")), "model_authority": {"execute": False, "authorize": False, "declare_success": False}},
    }
    for name, value in artifacts.items():
        (pack / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (pack / "README.md").write_text(
        "# Crystal IR Ollama Smoke Evidence\n\n"
        f"Model: `{payload['model']}`\n\n"
        "This pack proves the live semantic translation boundary only. It does not claim source mutation, execution, or model-weight improvement. "
        "Use `phase_telemetry.json` to distinguish model load, prefill, decode, and process CPU cost.\n",
        encoding="utf-8",
    )
    manifest = {"beast_object_type": "crystal_ir_smoke_integrity_manifest", "version": "1.0", "files": {path.name: _sha256(path) for path in sorted(pack.iterdir()) if path.is_file() and path.name != "integrity_manifest.json"}}
    manifest["manifest_hash"] = "sha256:" + hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    (pack / "integrity_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    archive = pack.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(pack.iterdir()):
            if path.is_file():
                bundle.write(path, path.name)
    return pack


def main() -> int:
    started = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    prompt = translator_prompt(
        "Fix provider names because NVIDIA-NIM and NVIDIA NIM break routing; do not touch tests or unrelated files.",
        target_file="app/provider_parser.py",
        context='Observed inputs: "nvidia-nim" and " NVIDIA NIM "; expected canonical value: "nvidia_nim".',
    )
    options = {"temperature": 0, "num_ctx": 1024, "num_predict": int(os.environ.get("BEAST_OLLAMA_NUM_PREDICT", "64")), "num_thread": int(os.environ.get("BEAST_OLLAMA_NUM_THREAD", "2")), "num_batch": int(os.environ.get("BEAST_OLLAMA_NUM_BATCH", "128"))}
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": CRYSTAL_IR_TRANSLATOR_SCHEMA,
        "options": options,
        "keep_alive": os.environ.get("BEAST_OLLAMA_KEEP_ALIVE", "10m"),
    }
    request = urllib.request.Request(
        os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode())
    raw = body.get("response") or ""
    candidate = json.loads(raw) if isinstance(raw, str) else raw
    receipt_path = Path(os.environ.get("CRYSTAL_IR_EVIDENCE_PATH", "evidence/ollama_crystal_ir_smoke_latest.json"))
    try:
        intent = compile_intent_candidate(candidate)
        ir = compile_crystal_ir_from_intent(intent, objective="canonicalize provider identifier", target_file="app/provider_parser.py", target_symbol="normalize_provider_id")
    except Exception as exc:
        receipt = {"beast_object_type": "crystal_ir_translation_receipt", "valid": False, "model": model, "options": options, "error": str(exc), "candidate": candidate, "provider_called": True, "mutation_performed": False, "usage": {k: body.get(k) for k in ("total_duration", "prompt_eval_count", "eval_count")}}
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt["evidence_pack"] = str(write_evidence_pack(receipt_path, receipt=receipt, payload=payload, prompt=prompt, body=body, started=started, cpu_start=cpu_start))
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 2
    receipt = {"beast_object_type": "crystal_ir_translation_receipt", "valid": True, "model": model, "options": options, "intent": intent.to_dict(), "digest": ir.digest(), "ir": ir.to_dict(), "provider_called": True, "mutation_performed": False, "usage": {k: body.get(k) for k in ("total_duration", "prompt_eval_count", "eval_count")}}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt["evidence_pack"] = str(write_evidence_pack(receipt_path, receipt=receipt, payload=payload, prompt=prompt, body=body, started=started, cpu_start=cpu_start))
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
