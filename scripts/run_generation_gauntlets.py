#!/usr/bin/env python3
"""Run BEAST text and image generation gauntlets with durable learning receipts.

The default gauntlet is local-only.  Image "provider" calls go through
ComputePlane's explicit provider-fallback boundary, but use deterministic stub
bytes so the runner can be repeated without cloud spend or secret material.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.generation_provider_adapters import (
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso
from app.kernel.compute.scene_synthesis import (
    CanvasContract,
    SceneCrystal,
    SceneOpcode,
    SceneOpcodeKind,
    default_beast_asset_manifest,
)


TEXT_CASES: tuple[Mapping[str, Any], ...] = (
    {
        "case_id": "text:service-health:beast",
        "train": ("what is beast status?", "is beast healthy?"),
        "replay": "how is beast doing?",
        "crystal_id": "meaning-crystal:gauntlet:beast-health",
    },
    {
        "case_id": "text:service-health:commons",
        "train": ("what is commons health?", "is commons healthy?"),
        "replay": "how is commons doing?",
        "crystal_id": "meaning-crystal:gauntlet:commons-health",
    },
    {
        "case_id": "text:service-endpoint:beast",
        "train": ("where is beast listening", "beast endpoint please"),
        "replay": "what is beast port?",
        "crystal_id": "meaning-crystal:gauntlet:beast-endpoint",
    },
)


IMAGE_CASES: tuple[Mapping[str, Any], ...] = (
    {
        "case_id": "image:status-light:green",
        "prompt": "bright green circular LED status light icon filling the frame, centered, simple isolated indicator, no text",
        "color": (38, 220, 72),
        "seed": 101,
        "mask_id": "mask:gauntlet-green-status-light",
    },
    {
        "case_id": "image:status-light:blue",
        "prompt": "bright blue circular LED status light icon filling the frame, centered, simple isolated indicator, no text",
        "color": (52, 110, 235),
        "seed": 102,
        "mask_id": "mask:gauntlet-blue-status-light",
    },
)


def run_generation_gauntlets(
    *,
    state_root: str | Path = REPO_ROOT / ".beast" / "state" / "generation_gauntlets",
    evidence_root: str | Path = REPO_ROOT / "evidence" / "generation-gauntlet",
    run_id: str | None = None,
    include_text: bool = True,
    include_image: bool = True,
    provider_mode: str = "stub",
    provider_id: str = "gauntlet_stub",
    chat_provider_id: str = "",
    chat_model: str = "",
    approval_receipt: str = "",
) -> dict[str, Any]:
    state_path = Path(state_root)
    evidence_path = Path(evidence_root)
    state_path.mkdir(parents=True, exist_ok=True)
    evidence_path.mkdir(parents=True, exist_ok=True)
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    provider_outputs: dict[str, tuple[bytes, ...]] = {}
    provider_receipts: list[dict[str, Any]] = []
    provider_call_counts: Counter[str] = Counter()
    provider_call_log: list[dict[str, Any]] = []
    adapter_registry = GenerationProviderAdapterRegistry(
        image_factory=lambda request: _next_provider_image(request, provider_outputs, provider_call_counts)
    )

    def provider(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        prompt_digest = str(payload.get("prompt_digest") or "")
        mask = dict(payload.get("mask") or {})
        request = GenerationProviderRequest(
            request_id=str(payload.get("request_digest") or "gauntlet-provider:" + prompt_digest.removeprefix("sha256:")[:16]),
            modality=GenerationModality.IMAGE,
            provider_id=provider_id,
            mode=ProviderMode(provider_mode),
            prompt_digest=prompt_digest,
            approval_receipt=approval_receipt or str(payload.get("approval_receipt_digest") or ""),
            metadata={
                "boundary": "visual_provider_fallback",
                "source_request_digest": str(payload.get("request_digest") or ""),
                "prompt": str(payload.get("prompt") or ""),
                "seed": int(payload.get("seed") or 0),
                "output_format": "rgba_region",
                "normalize_intent_color": True,
                "region_width": int(mask.get("width") or 8),
                "region_height": int(mask.get("height") or 8),
                "negative_prompt": "words, letters, label, people, scenery, dark background, multiple lights",
                "num_inference_steps": 8,
            },
        )
        result = adapter_registry.execute(request)
        output = result.output
        if ProviderMode(provider_mode) is ProviderMode.LIVE:
            provider_call_counts[prompt_digest] += int(result.receipt.provider_calls_used)
        provider_receipts.append(result.to_dict()["receipt"])
        provider_call_log.append({
            "prompt_digest": prompt_digest,
            "request_digest": str(payload.get("request_digest") or ""),
            "output_digest": result.receipt.output_digest,
            "provider_receipt_digest": result.receipt.receipt_digest,
            "provider_mode": result.receipt.mode,
        })
        return {
            "verified": True,
            "output_base64": base64.b64encode(output).decode("ascii"),
            "output_digest": result.receipt.output_digest,
        }

    plane = ComputePlane(root=state_path, provider_fallback=provider)
    scorecard_before = plane.provider_reduction_scorecard()
    text = (
        _run_text_gauntlet(
            plane,
            adapter_registry=adapter_registry,
            provider_receipts=provider_receipts,
            provider_mode=provider_mode,
            chat_provider_id=chat_provider_id,
            chat_model=chat_model,
            approval_receipt=approval_receipt,
        )
        if include_text
        else _skipped("text")
    )
    image = _run_image_gauntlet(plane, provider_outputs, provider_call_counts) if include_image else _skipped("image")
    scorecard_after = plane.provider_reduction_scorecard()
    visual_registry = plane.visual_asset_registry_report()
    semantic_records = plane.semantic_crystal_registry.records()
    receipt: dict[str, Any] = {
        "beast_object_type": "generation_gauntlet_receipt",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "state_root": str(state_path),
        "claim_boundary": (
            "Local-only gauntlet. Text cases exercise bounded operator-language crystals. "
            "Image provider calls use deterministic stub bytes through the governed provider-fallback boundary, "
            "not live cloud image generation."
            if ProviderMode(provider_mode) is ProviderMode.STUB
            else "Live-provider boundary requested. Execution remains governed by adapter readiness, approval, and downstream gates."
        ),
        "provider_boundary": {
            "provider_mode": ProviderMode(provider_mode).value,
            "provider_id": provider_id,
            "chat_provider_id": chat_provider_id,
            "approval_present": bool(str(approval_receipt or "").strip()),
            "adapter_inventory_digest": adapter_registry.inventory(approval_receipt=approval_receipt)["inventory_digest"],
            "provider_receipt_digests": tuple(item["receipt_digest"] for item in provider_receipts),
        },
        "generation_synthesis_plane": _synthesis_plane_summary(provider_receipts),
        "evidence_bounded_semantic_resolution": _ebsr_summary(text),
        "learning_model": {
            "semantic_crystals": "promote repeated verified operator-language episodes, then replay from stored registry",
            "visual_assets": "promote repeated/equivalent verified region outputs into render-only assets, then reuse before provider fallback",
        },
        "scorecard_before": scorecard_before,
        "text": text,
        "image": image,
        "scorecard_after": scorecard_after,
        "stored_capabilities": {
            "semantic_crystal_count": len(semantic_records),
            "semantic_crystal_ids": tuple(record.crystal.crystal_id for record in semantic_records),
            "semantic_registry_path": str(plane.semantic_crystal_registry.path),
            "visual_asset_count": visual_registry["count"],
            "visual_asset_ids": tuple(item["asset"]["asset_id"] for item in visual_registry["assets"]),
            "visual_registry_digest": visual_registry["registry_digest"],
        },
        "provider_call_log_digest": sha256_digest(tuple(provider_call_log)),
    }
    gauntlet_status = "passed" if text["status"] in {"passed", "skipped"} and image["status"] in {"passed", "skipped"} else "failed"
    gauntlet_event_digest = sha256_digest({
        "run_id": run_id,
        "text_gauntlet_digest": text.get("gauntlet_digest", ""),
        "image_gauntlet_digest": image.get("gauntlet_digest", ""),
        "provider_call_log_digest": receipt["provider_call_log_digest"],
        "status": gauntlet_status,
    })
    plane.capability_learning_ledger.record(
        event_type="gauntlet_completed",
        capability_type="generation_gauntlet",
        capability_id="generation-gauntlet:" + run_id,
        lifecycle_state=gauntlet_status,
        authority="measurement_only",
        evidence_digest=gauntlet_event_digest,
        receipt_digest=gauntlet_event_digest,
        provider_calls_used=int(image.get("provider_calls_used") or 0) + int(text.get("provider_calls_used") or 0),
        provider_calls_avoided=int(scorecard_after.get("provider_calls_avoided") or 0) - int(scorecard_before.get("provider_calls_avoided") or 0),
        fresh_work_units=int(text.get("semantic_promotions_new") or 0),
        reuse_hits=int(text.get("semantic_replay_hits") or 0) + int(image.get("promoted_asset_reuse_hits") or 0),
        metadata={
            "text_status": text["status"],
            "image_status": image["status"],
            "visual_asset_count": visual_registry["count"],
            "semantic_crystal_count": len(semantic_records),
            "provider_mode": ProviderMode(provider_mode).value,
            "provider_id": provider_id,
            "chat_provider_id": chat_provider_id,
        },
    )
    receipt["capability_learning"] = plane.capability_learning_report(limit=100)
    receipt["receipt_digest"] = sha256_digest(receipt)
    json_path = evidence_path / f"{run_id}.json"
    md_path = evidence_path / f"{run_id}.md"
    json_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_summary_markdown(receipt), encoding="utf-8")
    (evidence_path / "latest.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence_path / "latest.md").write_text(_summary_markdown(receipt), encoding="utf-8")
    receipt["evidence_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(evidence_path / "latest.json"),
        "latest_markdown": str(evidence_path / "latest.md"),
    }
    return receipt


def _run_text_gauntlet(
    plane: ComputePlane,
    *,
    adapter_registry: GenerationProviderAdapterRegistry,
    provider_receipts: list[dict[str, Any]],
    provider_mode: str,
    chat_provider_id: str,
    chat_model: str,
    approval_receipt: str,
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    promotions = 0
    stored_reuse_hits = 0
    replay_hits = 0
    failures = 0
    provider_calls_used = 0
    for case in TEXT_CASES:
        replay = str(case["replay"])
        crystal_id = str(case["crystal_id"])
        before_response = plane.answer_operator_prompt(replay, interface="generation-gauntlet")
        reused_before = _is_semantic_replay(before_response)
        promoted_now = False
        chat_provider_called = False
        chat_provider_receipt_digest = ""
        failure = ""
        if reused_before:
            stored_reuse_hits += 1
        else:
            try:
                if str(chat_provider_id or "").strip():
                    provider_request = GenerationProviderRequest(
                        request_id="chat-provider:" + str(case["case_id"]).replace(":", "-"),
                        modality=GenerationModality.TEXT,
                        provider_id=chat_provider_id,
                        mode=ProviderMode(provider_mode),
                        prompt_digest=sha256_digest({"prompt": replay}),
                        model=chat_model,
                        approval_receipt=approval_receipt,
                        metadata={"prompt": replay, "boundary": "operator_language_chat_teach"},
                    )
                    provider_result = adapter_registry.execute(provider_request)
                    provider_receipt = provider_result.to_dict()["receipt"]
                    provider_receipts.append(provider_receipt)
                    chat_provider_called = True
                    provider_calls_used += int(provider_result.receipt.provider_calls_used)
                    chat_provider_receipt_digest = provider_result.receipt.receipt_digest
                plane.promote_operator_language_semantic_crystal(
                    tuple(str(item) for item in case["train"]),
                    crystal_id=crystal_id,
                    verifier_id="generation-gauntlet.operator-language.semantic",
                )
                promotions += 1
                promoted_now = True
            except Exception as exc:  # gauntlet receipts should preserve failures.
                failure = f"{type(exc).__name__}: {exc}"
        response = plane.answer_operator_prompt(replay, interface="generation-gauntlet")
        replayed = _is_semantic_replay(response)
        replay_hits += int(replayed)
        if failure or response.receipt.provider_called or response.receipt.action_taken or not replayed:
            failures += 1
        cases.append({
            "case_id": str(case["case_id"]),
            "execution_mode_before": "exact" if reused_before else ("escalate" if str(chat_provider_id or "").strip() else "template"),
            "execution_mode_after": "exact" if replayed else "unresolved",
            "semantic_space_class_before": _semantic_space_class(str(before_response.receipt.state.value), exact_replay=reused_before),
            "semantic_space_class_after": _semantic_space_class(str(response.receipt.state.value), exact_replay=replayed),
            "meaning_resolution_state_before": str(before_response.receipt.state.value),
            "meaning_resolution_state_after": str(response.receipt.state.value),
            "candidate_meaning_count_after": len(response.candidates),
            "evidence_binding_count_after": len(response.receipt.evidence_digests),
            "train_utterance_digests": tuple(sha256_digest(item) for item in case["train"]),
            "replay_utterance_digest": sha256_digest(replay),
            "crystal_id": crystal_id,
            "stored_reuse_before_teach": reused_before,
            "promoted_now": promoted_now,
            "replayed_after": replayed,
            "chat_provider_called": chat_provider_called,
            "chat_provider_receipt_digest": chat_provider_receipt_digest,
            "provider_called": bool(response.receipt.provider_called),
            "action_taken": bool(response.receipt.action_taken),
            "receipt_digest": response.receipt.receipt_digest,
            "failure": failure,
        })
    return {
        "status": "passed" if failures == 0 else "failed",
        "case_count": len(cases),
        "failed_count": failures,
        "semantic_promotions_new": promotions,
        "stored_reuse_hits": stored_reuse_hits,
        "semantic_replay_hits": replay_hits,
        "provider_calls_used": provider_calls_used + sum(1 for item in cases if item["provider_called"]),
        "actions_taken": sum(1 for item in cases if item["action_taken"]),
        "cases": cases,
        "gauntlet_digest": sha256_digest(cases),
    }


def _run_image_gauntlet(
    plane: ComputePlane,
    provider_outputs: dict[str, tuple[bytes, ...]],
    provider_call_counts: Counter[str],
) -> dict[str, Any]:
    manifest = default_beast_asset_manifest()
    scene = _runtime_scene(manifest)
    cases: list[dict[str, Any]] = []
    stored_asset_reuse_hits = 0
    failures = 0
    for case in IMAGE_CASES:
        prompt = str(case["prompt"])
        prompt_digest = sha256_digest({"prompt": prompt})
        provider_outputs[prompt_digest] = (
            _status_light_region_bytes(tuple(case["color"]), delta=0),
            _status_light_region_bytes(tuple(case["color"]), delta=1),
        )
        calls_before = provider_call_counts[prompt_digest]
        mask = {"mask_id": str(case["mask_id"]), "x": 240, "y": 44, "width": 8, "height": 8}
        capsule_id = "scene-capsule:generation-gauntlet:" + str(case["case_id"]).replace(":", "-")
        provider_teach_attempted = False
        provider_teach_skipped = False
        failure = ""
        try:
            provider_teach_attempted = True
            plane.run_visual_provider_fallback(
                scene,
                manifest=manifest,
                mask=mask,
                prompt=prompt,
                seed=int(case["seed"]),
                capsule_id=capsule_id,
                allow_provider_fallback=True,
                operator_approval="approval:generation-gauntlet:" + str(case["case_id"]),
                interface="generation-gauntlet",
            )
            plane.run_visual_provider_fallback(
                scene,
                manifest=manifest,
                mask=mask,
                prompt=prompt,
                seed=int(case["seed"]),
                capsule_id=capsule_id,
                allow_provider_fallback=True,
                operator_approval="approval:generation-gauntlet:" + str(case["case_id"]) + ":repeat",
                interface="generation-gauntlet",
            )
        except PermissionError as exc:
            if "promoted visual asset already exists" not in str(exc):
                failure = f"{type(exc).__name__}: {exc}"
            else:
                provider_teach_skipped = True
                stored_asset_reuse_hits += 1
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
        reuse = None
        if not failure:
            try:
                reuse = plane.run_visual_residual(
                    scene,
                    manifest=manifest,
                    mask=mask,
                    prompt=prompt,
                    seed=int(case["seed"]),
                    capsule_id=capsule_id,
                    interface="generation-gauntlet",
                )
            except Exception as exc:
                failure = f"{type(exc).__name__}: {exc}"
        provider_calls_used = provider_call_counts[prompt_digest] - calls_before
        reused = bool(reuse is not None and reuse.receipt.details and reuse.receipt.details.get("worker") == "promoted_visual_asset_reuse")
        if failure or not reused:
            failures += 1
        cases.append({
            "case_id": str(case["case_id"]),
            "execution_mode_before": "exact" if provider_teach_skipped else ("escalate" if provider_calls_used else "local_reason"),
            "execution_mode_after": "exact" if reused else "unresolved",
            "prompt_digest": prompt_digest,
            "provider_teach_attempted": provider_teach_attempted,
            "provider_teach_skipped_existing_asset": provider_teach_skipped,
            "provider_calls_used": int(provider_calls_used),
            "promoted_asset_reused": reused,
            "reuse_receipt_digest": reuse.receipt.receipt_digest if reuse is not None else "",
            "failure": failure,
        })
    return {
        "status": "passed" if failures == 0 else "failed",
        "case_count": len(cases),
        "failed_count": failures,
        "provider_calls_used": sum(int(item["provider_calls_used"]) for item in cases),
        "stored_asset_reuse_hits": stored_asset_reuse_hits,
        "promoted_asset_reuse_hits": sum(1 for item in cases if item["promoted_asset_reused"]),
        "cases": cases,
        "gauntlet_digest": sha256_digest(cases),
    }


def _runtime_scene(manifest: Any) -> SceneCrystal:
    return SceneCrystal(
        scene_id="scene:generation-gauntlet-status-card",
        manifest_digest=manifest.manifest_digest,
        canvas=CanvasContract(320, 160, "#07110d"),
        opcodes=(
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.mascot.idle", "x": 12, "y": 24, "width": 72, "height": 72}),
            SceneOpcode(SceneOpcodeKind.DRAW_TEXT, {"x": 96, "y": 64, "text": "BEAST gauntlet", "font_size": 18}),
            SceneOpcode(SceneOpcodeKind.PLACE_ASSET, {"asset_id": "beast.status.card", "x": 96, "y": 82, "width": 190, "height": 56}),
        ),
        policy_digest=sha256_digest({"policy": "generation-gauntlet.scene.v1"}),
        verifier_id="generation-gauntlet.scene",
    )


def _status_light_region_bytes(color: tuple[int, int, int], *, delta: int) -> bytes:
    region = bytearray()
    for y in range(8):
        for x in range(8):
            distance = (((x - 3.5) ** 2 + (y - 3.5) ** 2) ** 0.5) / 4
            gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
            region.extend([
                min(255, int((color[0] + delta) * gain) + (x + y + delta) % 3),
                min(255, int((color[1] - delta) * gain) + ((x + delta) % 2)),
                min(255, int((color[2] + delta) * gain)),
                255,
            ])
    return bytes(region)


def _next_provider_image(
    request: GenerationProviderRequest,
    provider_outputs: dict[str, tuple[bytes, ...]],
    provider_call_counts: Counter[str],
) -> bytes:
    outputs = provider_outputs.get(request.prompt_digest)
    if not outputs:
        raise RuntimeError("gauntlet provider received an unknown prompt digest")
    index = provider_call_counts[request.prompt_digest]
    provider_call_counts[request.prompt_digest] += 1
    return outputs[min(index, len(outputs) - 1)]


def _is_semantic_replay(response: Any) -> bool:
    return str(response.receipt.reason or "").startswith("semantic crystal replay:")


def _skipped(name: str) -> dict[str, Any]:
    return {"status": "skipped", "case_count": 0, "reason": f"{name} gauntlet disabled"}


def _synthesis_plane_summary(provider_receipts: list[dict[str, Any]]) -> dict[str, Any]:
    capsules = []
    mode_counts: Counter[str] = Counter()
    memfd_verified = 0
    sealed_memfd = 0
    guardian_handoff_attempted = 0
    guardian_handoff_verified = 0
    commons_digests = set()
    guardian_digests = set()
    for receipt in provider_receipts:
        metadata = dict(receipt.get("metadata") or {})
        capsule = metadata.get("generation_synthesis_capsule")
        if not isinstance(capsule, Mapping):
            continue
        sealed = dict(capsule.get("sealed_capsule") or {})
        mode = str(capsule.get("execution_mode") or "unknown")
        mode_counts[mode] += 1
        sealed_memfd += int(sealed.get("sealed_memfd") is True)
        memfd_verified += int(sealed.get("capsule_verified") is True)
        guardian = dict(sealed.get("socket_guardian_handoff") or {})
        guardian_handoff_attempted += int(guardian.get("attempted") is True)
        guardian_handoff_verified += int(guardian.get("verified") is True)
        commons_digests.add(str(capsule.get("commons_capability_digest") or ""))
        guardian_digests.add(str(capsule.get("socket_guardian_binding_digest") or ""))
        capsules.append({
            "provider_receipt_digest": str(receipt.get("receipt_digest") or ""),
            "execution_mode": mode,
            "crystal_digest": str(capsule.get("crystal_digest") or ""),
            "payload_digest": str(capsule.get("payload_digest") or ""),
            "sealed_memfd": sealed.get("sealed_memfd") is True,
            "capsule_verified": sealed.get("capsule_verified") is True,
            "capsule_offer_digest": str(sealed.get("capsule_offer_digest") or ""),
            "socket_guardian_handoff_verified": guardian.get("verified") is True,
            "socket_guardian_handoff_receipt_digest": str(guardian.get("receipt_digest") or ""),
            "commons_capability_digest": str(capsule.get("commons_capability_digest") or ""),
            "socket_guardian_binding_digest": str(capsule.get("socket_guardian_binding_digest") or ""),
            "raw_prompt_stored": capsule.get("raw_prompt_stored") is True,
        })
    return {
        "beast_object_type": "generation_synthesis_plane_gauntlet_summary",
        "version": "1.0",
        "capsule_count": len(capsules),
        "sealed_memfd_count": sealed_memfd,
        "capsule_verified_count": memfd_verified,
        "socket_guardian_handoff_attempted_count": guardian_handoff_attempted,
        "socket_guardian_handoff_verified_count": guardian_handoff_verified,
        "execution_mode_counts": dict(sorted(mode_counts.items())),
        "commons_capability_digests": tuple(sorted(item for item in commons_digests if item)),
        "socket_guardian_binding_digests": tuple(sorted(item for item in guardian_digests if item)),
        "raw_prompt_stored_count": sum(1 for item in capsules if item["raw_prompt_stored"]),
        "capsules": capsules,
        "summary_digest": sha256_digest(capsules),
    }


def _semantic_space_class(state: str, *, exact_replay: bool) -> str:
    if exact_replay:
        return "provable"
    if state in {"entailed", "refuted", "resolved", "contradicted", "ambiguous", "unsupported"}:
        return "resolvable"
    return "open"


def _ebsr_summary(text: Mapping[str, Any]) -> dict[str, Any]:
    cases = tuple(dict(item) for item in text.get("cases", ()) if isinstance(item, Mapping))
    state_counts: Counter[str] = Counter()
    class_counts: Counter[str] = Counter()
    matrix_free = 0
    exact_replay = 0
    bounded_non_replay = 0
    for case in cases:
        after_state = str(case.get("meaning_resolution_state_after") or "unknown")
        after_class = str(case.get("semantic_space_class_after") or "unknown")
        state_counts[after_state] += 1
        class_counts[after_class] += 1
        exact = case.get("execution_mode_after") == "exact"
        exact_replay += int(exact)
        bounded_non_replay += int(after_class == "resolvable" and not exact)
        matrix_free += int(
            after_class in {"provable", "resolvable"}
            and case.get("chat_provider_called") is not True
            and case.get("provider_called") is not True
            and case.get("action_taken") is not True
        )
    return {
        "beast_object_type": "evidence_bounded_semantic_resolution_summary",
        "version": "1.0",
        "case_count": len(cases),
        "semantic_space_class_counts": dict(sorted(class_counts.items())),
        "meaning_resolution_state_counts": dict(sorted(state_counts.items())),
        "matrix_free_case_count": matrix_free,
        "exact_replay_case_count": exact_replay,
        "bounded_non_replay_case_count": bounded_non_replay,
        "provider_taught_case_count": sum(1 for item in cases if item.get("chat_provider_called") is True),
        "summary_digest": sha256_digest(cases),
    }


def _summary_markdown(receipt: Mapping[str, Any]) -> str:
    text = receipt.get("text", {})
    image = receipt.get("image", {})
    stored = receipt.get("stored_capabilities", {})
    synthesis = receipt.get("generation_synthesis_plane", {})
    ebsr = receipt.get("evidence_bounded_semantic_resolution", {})
    return "\n".join([
        f"# BEAST generation gauntlet — {receipt['run_id']}",
        "",
        f"- Receipt digest: `{receipt['receipt_digest']}`",
        f"- Text status: `{text.get('status')}`; cases: {text.get('case_count', 0)}; "
        f"new semantic promotions: {text.get('semantic_promotions_new', 0)}; "
        f"stored reuse hits: {text.get('stored_reuse_hits', 0)}; replay hits: {text.get('semantic_replay_hits', 0)}",
        f"- Image status: `{image.get('status')}`; cases: {image.get('case_count', 0)}; "
        f"provider calls used: {image.get('provider_calls_used', 0)}; "
        f"stored asset reuse hits: {image.get('stored_asset_reuse_hits', 0)}; "
        f"promoted asset reuse hits: {image.get('promoted_asset_reuse_hits', 0)}",
        f"- Stored semantic crystals: {stored.get('semantic_crystal_count', 0)}",
        f"- Stored visual assets: {stored.get('visual_asset_count', 0)}",
        f"- Generation synthesis capsules: {synthesis.get('capsule_count', 0)}; "
        f"memfd sealed: {synthesis.get('sealed_memfd_count', 0)}; "
        f"verified: {synthesis.get('capsule_verified_count', 0)}",
        f"- EBSR matrix-free text cases: {ebsr.get('matrix_free_case_count', 0)} / {ebsr.get('case_count', 0)}; "
        f"semantic classes: `{ebsr.get('semantic_space_class_counts', {})}`",
        "",
        "## Claim boundary",
        "",
        str(receipt.get("claim_boundary") or ""),
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", default=str(REPO_ROOT / ".beast" / "state" / "generation_gauntlets"))
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "generation-gauntlet"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--text-only", action="store_true")
    parser.add_argument("--image-only", action="store_true")
    parser.add_argument("--provider-mode", choices=("stub", "live"), default="stub")
    parser.add_argument("--provider", default="gauntlet_stub")
    parser.add_argument("--chat-provider", default="")
    parser.add_argument("--chat-model", default="")
    parser.add_argument("--approval", default="")
    args = parser.parse_args(argv)
    receipt = run_generation_gauntlets(
        state_root=args.state_root,
        evidence_root=args.evidence_root,
        run_id=args.run_id,
        include_text=not args.image_only,
        include_image=not args.text_only,
        provider_mode=args.provider_mode,
        provider_id=args.provider,
        chat_provider_id=args.chat_provider,
        chat_model=args.chat_model,
        approval_receipt=args.approval,
    )
    print(json.dumps({
        "receipt_digest": receipt["receipt_digest"],
        "text_status": receipt["text"]["status"],
        "image_status": receipt["image"]["status"],
        "evidence_paths": receipt["evidence_paths"],
    }, sort_keys=True, indent=2))
    return 0 if receipt["text"]["status"] in {"passed", "skipped"} and receipt["image"]["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
