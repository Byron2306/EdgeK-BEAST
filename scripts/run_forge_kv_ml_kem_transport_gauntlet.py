#!/usr/bin/env python3
"""Run a Forge KV network-transfer receipt bound to Commons ML-KEM evidence.

Default mode is deliberately conservative: without ``--engine-native-payload``
the runner uses CI fixture bytes and marks the receipt ``payload_kind`` as
``test_oracle``.  That exercises the route but does not grant production
transport verification.  Supplying a real engine-native payload file promotes
the claim to ``payload_kind=engine_native``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.forge_kv_ml_kem_transport import build_ml_kem_bound_transport_receipt
from app.kernel.compute.kv_cache_transport import CacheEngine, CacheLocation, CrossEngineKVCacheTransport
from app.kernel.compute.residual_contracts import sha256_digest, utc_now_iso


def run_forge_kv_ml_kem_transport_gauntlet(
    *,
    ml_kem_receipt_path: str | Path = REPO_ROOT / "evidence" / "commons-ml-kem" / "latest.json",
    evidence_root: str | Path = REPO_ROOT / "evidence" / "forge-kv-ml-kem-transport",
    state_root: str | Path = REPO_ROOT / ".beast" / "state" / "forge_kv_ml_kem_transport_gauntlet",
    run_id: str | None = None,
    engine_native_payload: str | Path | None = None,
) -> dict[str, Any]:
    run_id = run_id or utc_now_iso().replace(":", "").replace("+", "z")
    evidence_path = Path(evidence_root)
    evidence_path.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_root)
    source = CrossEngineKVCacheTransport(storage_dir=state_path / "source")
    target = CrossEngineKVCacheTransport(storage_dir=state_path / "target")
    payload, payload_kind = _payload(engine_native_payload)
    ml_kem_receipt = json.loads(Path(ml_kem_receipt_path).read_text(encoding="utf-8"))
    endpoint = "memory://forge-kv-ml-kem-target"
    block = source.register_block(
        model="llama",
        tokenizer="tok",
        prompt_prefix="forge kv ml-kem transport",
        system_prompt="beast system",
        engine=CacheEngine.SGLANG,
        location=CacheLocation.CPU,
        precision="bf16",
        num_layers=2,
        num_heads=2,
        head_dim=8,
        seq_len=16,
        size_bytes=len(payload),
        metadata={"target_endpoint": endpoint, "source_node": "forge-kv-mlkem-gauntlet"},
        tensor_payload=payload,
        tensor_format="safetensors" if payload_kind == "engine_native" else "test-oracle",
    )
    source.register_network_sender(endpoint, target.receive_network_transfer)
    transferred = source.move(block.block_id, CacheLocation.NETWORK)
    manifest_path = source.storage_dir / f"{block.block_id}.json"
    kv_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    receipt = build_ml_kem_bound_transport_receipt(
        kv_manifest=kv_manifest,
        ml_kem_receipt=ml_kem_receipt,
        payload_kind=payload_kind,
    )
    plane = ComputePlane(root=state_path / "compute")
    projection = plane.ingest_reduction_evidence("forge_kv_prompt_cache", receipt, interface="forge-kv-ml-kem-gauntlet")
    report = {
        "beast_object_type": "forge_kv_ml_kem_transport_gauntlet",
        "version": "1.0",
        "run_id": run_id,
        "observed_at": utc_now_iso(),
        "transferred": bool(transferred),
        "payload_kind": payload_kind,
        "block_id": block.block_id,
        "source_manifest_digest": sha256_digest(kv_manifest),
        "ml_kem_receipt_digest": str(ml_kem_receipt.get("receipt_digest") or sha256_digest(ml_kem_receipt)),
        "transport_receipt": receipt,
        "normalized_projection": projection,
        "claim_boundary": (
            "Checksum-bound KV network transfer plus Commons ML-KEM receipt binding; "
            "provider-call avoidance and token savings remain zero unless separate execution evidence exists"
        ),
    }
    report["receipt_digest"] = sha256_digest(report)
    json_path = evidence_path / f"{run_id}.json"
    md_path = evidence_path / f"{run_id}.md"
    json_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    (evidence_path / "latest.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (evidence_path / "latest.md").write_text(_markdown(report), encoding="utf-8")
    report["evidence_paths"] = {
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(evidence_path / "latest.json"),
        "latest_markdown": str(evidence_path / "latest.md"),
    }
    return report


def _payload(engine_native_payload: str | Path | None) -> tuple[bytes, str]:
    if engine_native_payload:
        payload = Path(engine_native_payload).read_bytes()
        if not payload:
            raise ValueError("engine-native payload file is empty")
        return payload, "engine_native"
    return b"ci-test-oracle-kv-payload-not-production-engine-native", "test_oracle"


def _markdown(report: Mapping[str, Any]) -> str:
    transport = report.get("transport_receipt") if isinstance(report.get("transport_receipt"), Mapping) else {}
    projection = report.get("normalized_projection") if isinstance(report.get("normalized_projection"), Mapping) else {}
    return "\n".join([
        f"# Forge KV ML-KEM transport gauntlet — {report['run_id']}",
        "",
        f"- Receipt digest: `{report['receipt_digest']}`",
        f"- Payload kind: `{report.get('payload_kind')}`",
        f"- Transport status: `{transport.get('status')}`",
        f"- Transport verified: `{transport.get('transport_verified')}`",
        f"- Claim class: `{projection.get('claim_class')}`",
        f"- Bytes transferred verified: `{projection.get('bytes_transferred_verified', 0)}`",
        f"- Provider calls avoided: `{projection.get('provider_calls_avoided', 0)}`",
        f"- Tokens avoided observed: `{projection.get('tokens_avoided_observed', 0)}`",
        "",
        "## Claim boundary",
        "",
        str(report.get("claim_boundary") or ""),
        "",
    ]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ml-kem-receipt", default=str(REPO_ROOT / "evidence" / "commons-ml-kem" / "latest.json"))
    parser.add_argument("--evidence-root", default=str(REPO_ROOT / "evidence" / "forge-kv-ml-kem-transport"))
    parser.add_argument("--state-root", default=str(REPO_ROOT / ".beast" / "state" / "forge_kv_ml_kem_transport_gauntlet"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--engine-native-payload", default=None)
    args = parser.parse_args(argv)
    report = run_forge_kv_ml_kem_transport_gauntlet(
        ml_kem_receipt_path=args.ml_kem_receipt,
        evidence_root=args.evidence_root,
        state_root=args.state_root,
        run_id=args.run_id,
        engine_native_payload=args.engine_native_payload,
    )
    print(json.dumps({
        "receipt_digest": report["receipt_digest"],
        "payload_kind": report["payload_kind"],
        "transport_status": report["transport_receipt"]["status"],
        "transport_verified": report["transport_receipt"]["transport_verified"],
        "claim_class": report["normalized_projection"]["claim_class"],
        "evidence_paths": report["evidence_paths"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
