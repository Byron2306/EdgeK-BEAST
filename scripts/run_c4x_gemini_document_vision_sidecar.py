#!/usr/bin/env python3
"""Generate native Gemini vision sidecars for the C4-X document arena.

Default mode is a safe dry run: it writes planned request rows that the
adjudicator will not accept for truth credit.  Use ``--live`` to call Gemini and
produce provenance-bearing ``gemini_native_vision`` rows.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import shlex
import sys
from typing import Any, Mapping

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402


REQUIRED_FIELDS = ("tables", "merged_headers", "footnotes", "statistical_notation", "chart_values")
DEFAULT_MODEL = "auto"


def run_gemini_document_vision_sidecar(
    *,
    document_arena_json: str | Path,
    output: str | Path | None = None,
    env_file: str | Path | None = REPO_ROOT / ".beast" / "provider_secrets.env",
    model: str = DEFAULT_MODEL,
    live: bool = False,
    approval_receipt: str = "",
    timeout_seconds: float = 90.0,
) -> dict[str, Any]:
    _load_env_file(env_file)
    arena_path = Path(document_arena_json)
    if not arena_path.is_absolute():
        arena_path = REPO_ROOT / arena_path
    arena = json.loads(arena_path.read_text(encoding="utf-8"))
    evidence_root = arena_path.parent
    out_path = Path(output) if output else evidence_root / "audit_packets" / "gemini_native_vision_sidecar.jsonl"
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    api_key_ready = bool(_api_key())
    resolved_model = _resolve_model(model, live=live and api_key_ready, timeout_seconds=timeout_seconds)
    rows = []
    for doc in arena.get("corpus") or []:
        if doc.get("missing"):
            continue
        rows.append(
            _execute_or_plan_doc(
                doc,
                model=resolved_model,
                live=live,
                api_key_ready=api_key_ready,
                approval_receipt=approval_receipt,
                timeout_seconds=timeout_seconds,
            )
        )
    out_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    receipt_core = {
        "beast_object_type": "c4x_gemini_document_vision_sidecar_run",
        "version": "1.0",
        "created_at": utc_now_iso(),
        "document_arena_receipt_digest": arena.get("receipt_digest", ""),
        "document_arena_path": _rel(arena_path),
        "output": _rel(out_path),
        "model": resolved_model,
        "requested_model": model,
        "live": live,
        "api_key_ready": api_key_ready,
        "approval_present": bool(approval_receipt.strip()),
        "row_count": len(rows),
        "eligible_rows": sum(int(row.get("live_execution") is True and row.get("provider_calls_used", 0) >= 1) for row in rows),
        "output_digest": _file_sha256(out_path),
        "claim_boundary": (
            "Gemini document vision sidecar production only. Dry-run rows are "
            "planning artifacts and are not accepted by the adjudicator for truth "
            "credit. Live rows bind request digest, raw response digest, model, "
            "source image digest, and provider call count."
        ),
    }
    receipt = {**receipt_core, "receipt_digest": sha256_digest(receipt_core)}
    summary_path = out_path.with_suffix(".receipt.json")
    summary_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {**receipt, "receipt_path": str(summary_path)}


def _execute_or_plan_doc(
    doc: Mapping[str, Any],
    *,
    model: str,
    live: bool,
    api_key_ready: bool,
    approval_receipt: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    image = doc.get("first_page_image")
    image_path = REPO_ROOT / str(image.get("path") or "") if isinstance(image, Mapping) else None
    image_digest = str(image.get("sha256") or "") if isinstance(image, Mapping) else ""
    prompt = _prompt_for(doc)
    request_core = {
        "document_id": doc.get("document_id"),
        "model": model,
        "source_digest": image_digest,
        "prompt": prompt,
        "required_fields": REQUIRED_FIELDS,
    }
    request_digest = sha256_digest(request_core)
    base = {
        "document_id": doc.get("document_id"),
        "observer_type": "gemini_native_vision" if live else "gemini_native_vision_planned",
        "source_mode": "native_page_image_vision",
        "source_digest": image_digest,
        "raw_text_answer_used": False,
        "beast_text_answer_used": False,
        "model": model,
        "request_digest": request_digest,
        "created_at": utc_now_iso(),
    }
    if not live:
        return {
            **base,
            "live_execution": False,
            "provider_calls_used": 0,
            "final_status": "planned_not_executed",
            "env_ready": api_key_ready,
            "approval_present": bool(approval_receipt.strip()),
            "findings": _empty_findings(),
        }
    if not api_key_ready:
        return {**base, "live_execution": False, "provider_calls_used": 0, "final_status": "missing_gemini_api_key", "findings": _empty_findings()}
    if not approval_receipt.strip():
        return {**base, "live_execution": False, "provider_calls_used": 0, "final_status": "missing_live_approval_receipt", "findings": _empty_findings()}
    if image_path is None or not image_path.is_file() or not image_digest.startswith("sha256:"):
        return {**base, "live_execution": False, "provider_calls_used": 0, "final_status": "missing_rendered_page_image", "findings": _empty_findings()}
    try:
        raw_response = _call_gemini_vision(image_path, prompt=prompt, model=model, timeout_seconds=timeout_seconds)
    except httpx.HTTPStatusError as exc:
        status = f"gemini_http_{exc.response.status_code}"
        return {
            **base,
            "live_execution": False,
            "provider_calls_used": 1,
            "raw_response_digest": sha256_digest(exc.response.text),
            "http_status": exc.response.status_code,
            "final_status": status,
            "findings": _empty_findings(),
        }
    except Exception as exc:
        return {
            **base,
            "live_execution": False,
            "provider_calls_used": 1,
            "raw_response_digest": sha256_digest(type(exc).__name__ + ":" + str(exc)),
            "final_status": type(exc).__name__,
            "findings": _empty_findings(),
        }
    raw_response_text = json.dumps(raw_response, sort_keys=True)
    text = _gemini_text(raw_response)
    findings, parse_status = _parse_findings(text)
    return {
        **base,
        "live_execution": True,
        "provider_calls_used": 1,
        "raw_response_digest": sha256_digest(raw_response_text),
        "response_text_digest": sha256_digest(text),
        "candidate_count": len(raw_response.get("candidates") or []),
        "final_status": parse_status,
        "findings": findings,
    }


def _call_gemini_vision(image_path: Path, *, prompt: str, model: str, timeout_seconds: float) -> dict[str, Any]:
    api_key = _api_key()
    model_path = model if model.startswith("models/") else "models/" + model
    base_url = os.environ.get("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com"
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": image_b64}},
                ],
            }
        ],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            base_url.rstrip("/") + "/v1beta/" + model_path + ":generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
    response.raise_for_status()
    return response.json()


def _resolve_model(model: str, *, live: bool, timeout_seconds: float) -> str:
    requested = (model or DEFAULT_MODEL).strip()
    if requested != "auto" or not live:
        return requested
    try:
        available = _list_generate_content_models(timeout_seconds=timeout_seconds)
    except Exception:
        return "gemini-3.5-flash"
    names = {item["name"].removeprefix("models/"): item for item in available}
    preferred = (
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-002",
        "gemini-1.5-flash-001",
    )
    for name in preferred:
        if name in names:
            return name
    for name in sorted(names):
        lowered = name.lower()
        if "gemini" in lowered and "flash" in lowered:
            return name
    for name in sorted(names):
        if "gemini" in name.lower():
            return name
    return "gemini-3.5-flash"


def _list_generate_content_models(*, timeout_seconds: float) -> list[dict[str, Any]]:
    api_key = _api_key()
    base_url = os.environ.get("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com"
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(
            base_url.rstrip("/") + "/v1beta/models",
            headers={"x-goog-api-key": api_key},
            params={"pageSize": "1000"},
        )
    response.raise_for_status()
    payload = response.json()
    models = []
    for model in payload.get("models") or []:
        methods = model.get("supportedGenerationMethods") or model.get("supportedActions") or ()
        if "generateContent" in methods:
            models.append(model)
    return models


def _prompt_for(doc: Mapping[str, Any]) -> str:
    return (
        "Inspect only the attached rendered PDF page image. Do not use any BEAST text answer. "
        "Return strict JSON with exactly these top-level keys: tables, merged_headers, "
        "footnotes, statistical_notation, chart_values. Use [] when absent or uncertain. "
        f"Document id: {doc.get('document_id')}. Title: {doc.get('title')}."
    )


def _gemini_text(response: Mapping[str, Any]) -> str:
    chunks = []
    for candidate in response.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, Mapping) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks).strip()


def _parse_findings(text: str) -> tuple[dict[str, Any], str]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.removeprefix("```json").removeprefix("```").strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return _empty_findings(), "gemini_response_json_parse_failed"
    if not isinstance(parsed, Mapping):
        return _empty_findings(), "gemini_response_not_object"
    return {field: parsed.get(field, []) for field in REQUIRED_FIELDS}, "gemini_vision_findings_parsed"


def _empty_findings() -> dict[str, Any]:
    return {field: [] for field in REQUIRED_FIELDS}


def _load_env_file(path: str | Path | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.is_absolute():
        env_path = REPO_ROOT / env_path
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        if key and key not in os.environ:
            try:
                parts = shlex.split(value, posix=True)
                os.environ[key] = parts[0] if parts else ""
            except ValueError:
                os.environ[key] = value.strip().strip('"').strip("'")


def _api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def _file_sha256(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Gemini native-vision sidecars for a C4-X document arena run.")
    parser.add_argument("--document-arena-json", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".beast" / "provider_secrets.env"))
    parser.add_argument("--model", default=os.environ.get("GEMINI_VISION_MODEL") or os.environ.get("GEMINI_MODEL") or os.environ.get("GOOGLE_MODEL") or DEFAULT_MODEL)
    parser.add_argument("--live", action="store_true", help="Actually call Gemini. Without this, writes non-credit dry-run rows.")
    parser.add_argument("--approval-receipt", default="")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    args = parser.parse_args()
    receipt = run_gemini_document_vision_sidecar(
        document_arena_json=args.document_arena_json,
        output=args.output,
        env_file=args.env_file,
        model=args.model,
        live=args.live,
        approval_receipt=args.approval_receipt,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps({key: receipt[key] for key in ("output", "output_digest", "receipt_digest", "receipt_path", "live", "eligible_rows")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
