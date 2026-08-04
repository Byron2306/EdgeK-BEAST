#!/usr/bin/env python3
"""Run the BEAST proof-bound image-provider gate gauntlet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.generation_provider_adapters import (  # noqa: E402
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.proof_graph import CanonicalProofGraph, ProofClaimStatus, ProofGraphClaim, VisualProofPrimitive, VisualProofView  # noqa: E402
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.scene_synthesis import CanvasContract  # noqa: E402
from app.kernel.compute.visual_proof_provider_gate import (  # noqa: E402
    attest_visual_provider_output_against_proof,
    build_visual_proof_provider_prompt,
)
from app.kernel.compute.visual_residuals import RegionMask  # noqa: E402


CASES = (
    {"case_id": "proof_bound_green_supported", "status": ProofClaimStatus.SUPPORTED, "color": (38, 220, 72), "tamper_prompt": False},
    {"case_id": "reject_text_or_arbitrary_prompt", "status": ProofClaimStatus.SUPPORTED, "color": (38, 220, 72), "tamper_prompt": True},
    {"case_id": "reject_wrong_pixels", "status": ProofClaimStatus.SUPPORTED, "color": (220, 38, 32), "tamper_prompt": False},
    {"case_id": "block_stale_claim_promotion", "status": ProofClaimStatus.STALE, "color": (235, 204, 52), "tamper_prompt": False},
)


def run_visual_proof_provider_gate_gauntlet(
    *,
    evidence_root: str | Path = REPO_ROOT / "evidence" / "visual-proof-provider-gate",
    run_id: str | None = None,
) -> dict[str, Any]:
    evidence_path = Path(evidence_root)
    evidence_path.mkdir(parents=True, exist_ok=True)
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    mask = _mask()
    receipts = []
    for case in CASES:
        graph, visual_view = _proof_artifacts(case["status"])
        prompt_spec = build_visual_proof_provider_prompt(graph, visual_view, primitive_id="primitive:risk-edge")
        prompt_digest = (
            sha256_digest({"prompt": "text answer says restart risk is safe"})
            if case["tamper_prompt"]
            else prompt_spec.prompt_digest
        )
        output = _status_light_region_bytes(case["color"])
        registry = GenerationProviderAdapterRegistry(image_factory=lambda _request, data=output: data)
        request = GenerationProviderRequest(
            request_id="visual-proof-provider-gate:" + str(case["case_id"]),
            modality=GenerationModality.IMAGE,
            provider_id="gauntlet_stub",
            mode=ProviderMode.STUB,
            prompt_digest=prompt_digest,
            metadata={"prompt": prompt_spec.prompt, "boundary": "visual_proof_provider_gate"},
        )
        result = registry.execute(request)
        gate = attest_visual_provider_output_against_proof(
            graph,
            visual_view,
            primitive_id="primitive:risk-edge",
            provider_request=request,
            provider_receipt=result.receipt,
            output=result.output,
            mask=mask,
        )
        receipts.append({
            "case_id": case["case_id"],
            "claim_status": case["status"].value,
            "provider_receipt_digest": result.receipt.receipt_digest,
            "provider_calls_used": result.receipt.provider_calls_used,
            "live_execution": result.receipt.live_execution,
            "prompt_spec": prompt_spec.to_dict(),
            "gate": gate.to_dict(),
        })
    scorecard = {
        "case_count": len(receipts),
        "trusted_for_promotion": sum(1 for item in receipts if item["gate"]["trusted_for_promotion"]),
        "quarantined": sum(1 for item in receipts if not item["gate"]["trusted_for_promotion"]),
        "prompt_tamper_rejected": sum(1 for item in receipts if item["gate"]["failure_class"] == "prompt_proof_mismatch"),
        "wrong_pixels_rejected": sum(1 for item in receipts if item["gate"]["failure_class"] == "visual_intent_failure"),
        "stale_claim_blocked": sum(1 for item in receipts if item["gate"]["failure_class"] == "non_current_claim"),
        "raw_text_answer_used": sum(1 for item in receipts if item["prompt_spec"]["raw_text_answer_used"]),
        "provider_calls_used": sum(int(item["provider_calls_used"]) for item in receipts),
        "live_provider_calls_used": sum(int(item["provider_calls_used"]) for item in receipts if item["live_execution"]),
        "failure_classes": tuple(sorted({item["gate"]["failure_class"] for item in receipts if item["gate"]["failure_class"]})),
    }
    receipt = {
        "beast_object_type": "visual_proof_provider_gate_gauntlet_receipt",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "claim_boundary": (
            "Proof-bound image-provider gate. The provider prompt is built from the canonical proof graph "
            "and visual proof primitive, not from the text answer. Provider pixels remain quarantined unless "
            "the request prompt digest, provider receipt, output digest, region boundary, visual intent, "
            "perceptual checks, and current supported proof claim all verify."
        ),
        "scorecard": scorecard,
        "cases": tuple(receipts),
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    json_path = evidence_path / f"{run_id}.json"
    md_path = evidence_path / f"{run_id}.md"
    json_path.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(receipt), encoding="utf-8")
    (evidence_path / "latest.json").write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence_path / "latest.md").write_text(_markdown(receipt), encoding="utf-8")
    receipt["evidence_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(evidence_path / "latest.json"),
        "latest_markdown": str(evidence_path / "latest.md"),
    }
    return receipt


def _proof_artifacts(status: ProofClaimStatus) -> tuple[CanonicalProofGraph, VisualProofView]:
    fact_digest = sha256_digest({"fact": "service-health", "service": "beast"})
    rule_digest = sha256_digest({"rule": "restart-risk-visual-proof"})
    policy_digest = sha256_digest({"policy": "visual-provider-proof-bound.v1"})
    claim = ProofGraphClaim(
        claim_id="claim:restart-risk:beast-to-commons",
        claim_type="conditional_causal",
        subject="beast",
        predicate="restart_may_destabilize",
        object="commons",
        status=status,
        confidence_class="bounded_verified",
        fact_refs=(fact_digest,),
        rule_ref=rule_digest,
        policy_ref=policy_digest,
    )
    graph = CanonicalProofGraph(
        graph_id="proof-graph:visual-provider-gate:" + status.value,
        claims=(claim,),
        world_snapshot_digest=sha256_digest({"snapshot": "visual-provider-gate", "status": status.value}),
        policy_digest=policy_digest,
        capability_fact_digests=(fact_digest,),
        causal_rule_digests=(rule_digest,),
    )
    visual_view = VisualProofView(
        view_id="visual-view:visual-provider-gate",
        scene_capsule_digest=sha256_digest({"scene": "restart-risk-provider-gate"}),
        rendered_visual_digest=sha256_digest({"render": "proof-bound-provider-candidate"}),
        asset_manifest_digest=sha256_digest({"manifest": "beast-provider-gate"}),
        layout_engine_digest=sha256_digest({"layout": "proof-bound-provider-gate"}),
        primitives=(
            VisualProofPrimitive(
                primitive_id="primitive:risk-edge",
                primitive="risk_edge",
                claim_ref=claim.claim_id,
                evidence_state=status,
                metadata={
                    "object_hint": "status_light",
                    "expected_color": "green" if status is ProofClaimStatus.SUPPORTED else "yellow",
                    "visual_treatment": "solid_edge_with_rule_badge" if status is ProofClaimStatus.SUPPORTED else "clock_badge_and_faded_status",
                },
            ),
        ),
    )
    return graph, visual_view


def _mask() -> RegionMask:
    return RegionMask(
        mask_id="mask:proof-bound-risk-edge",
        x=0,
        y=0,
        width=8,
        height=8,
        canvas=CanvasContract(8, 8, "#000000"),
        provenance_digest=sha256_digest({"provenance": "visual-proof-provider-gate"}),
    )


def _status_light_region_bytes(color: tuple[int, int, int]) -> bytes:
    region = bytearray()
    for y in range(8):
        for x in range(8):
            distance = (((x - 3.5) ** 2 + (y - 3.5) ** 2) ** 0.5) / 4
            gain = 0.38 + max(0.0, 1.0 - distance) * 0.72
            region.extend([
                min(255, int(color[0] * gain) + (x + y) % 3),
                min(255, int(color[1] * gain) + (x % 2)),
                min(255, int(color[2] * gain)),
                255,
            ])
    return bytes(region)


def _markdown(receipt: dict[str, Any]) -> str:
    scorecard = receipt["scorecard"]
    return "\n".join([
        f"# BEAST visual proof-provider gate gauntlet — {receipt['run_id']}",
        "",
        f"- Receipt digest: `{receipt['receipt_digest']}`",
        f"- Cases: `{scorecard['case_count']}`",
        f"- Trusted for promotion: `{scorecard['trusted_for_promotion']}`",
        f"- Quarantined: `{scorecard['quarantined']}`",
        f"- Prompt tamper rejected: `{scorecard['prompt_tamper_rejected']}`",
        f"- Wrong pixels rejected: `{scorecard['wrong_pixels_rejected']}`",
        f"- Stale claim blocked: `{scorecard['stale_claim_blocked']}`",
        f"- Raw text answer used in prompts: `{scorecard['raw_text_answer_used']}`",
        f"- Provider calls used: `{scorecard['provider_calls_used']}`",
        f"- Live provider calls used: `{scorecard['live_provider_calls_used']}`",
        f"- Failure classes: `{scorecard['failure_classes']}`",
        "",
        "## Claim boundary",
        "",
        receipt["claim_boundary"],
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "visual-proof-provider-gate"))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)
    receipt = run_visual_proof_provider_gate_gauntlet(evidence_root=args.evidence_root, run_id=args.run_id)
    print(json.dumps({
        "receipt_digest": receipt["receipt_digest"],
        "scorecard": receipt["scorecard"],
        "evidence_paths": receipt["evidence_paths"],
    }, sort_keys=True, indent=2))
    return 0 if receipt["scorecard"]["trusted_for_promotion"] == 1 and receipt["scorecard"]["quarantined"] == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
