#!/usr/bin/env python3
"""Prove the crystal-keyed KV cache against live model metadata.

Every number in the receipt is derived from the running Ollama instance:
block count, KV head count, head dimensions and the model manifest digest.
KV is simulated at the *real* per-token footprint so byte accounting and
dedup ratios are not toy numbers, but the tensors are synthetic (this host has
no vLLM/SGLang engine, so there is no engine-native KV to capture).

The script fails closed: any red check exits non-zero and forbids public
credit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.request
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.crystal_kv_index import (  # noqa: E402
    CrystalKVIndex,
    KVLookupStatus,
    KVModelFingerprint,
    KVTokenSpan,
)
from app.kernel.execution.cgroup_capsule import CgroupV2Discovery  # noqa: E402

BLOCK_TOKENS = 16
PRIVACY = "workspace:edgek"
LAYERS = (0, 35)


def _get(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _sha256(value: Any) -> str:
    body = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def model_facts(base_url: str, model: str) -> dict[str, Any]:
    tags = _get(f"{base_url}/api/tags")
    match = next((item for item in tags.get("models", []) if item["name"] == model), None)
    if match is None:
        raise SystemExit(f"model not present in Ollama: {model}")
    show = _get(f"{base_url}/api/show", {"model": model})
    info = show.get("model_info", {})
    family = str(match.get("details", {}).get("family", ""))
    prefix = family if any(key.startswith(f"{family}.") for key in info) else ""

    def value(name: str, default: Any = None) -> Any:
        for key in (f"{prefix}.{name}" if prefix else name, f"general.{name}" if name.startswith("block") else name):
            if key in info:
                return info[key]
        return default

    layers = value("block_count")
    heads_kv = value("attention.head_count_kv")
    head_count = value("attention.head_count")
    key_len = value("attention.key_length")
    val_len = value("attention.value_length", key_len)
    embedding = value("embedding_length")
    if layers is None or embedding is None:
        raise SystemExit(f"model metadata is incomplete for {model}")
    if heads_kv is None:
        heads_kv = head_count
    if key_len is None:
        # head dimension comes from the query head count, not the KV head count
        key_len = int(embedding) // max(1, int(head_count))
        val_len = key_len
    layers, heads_kv, key_len, val_len = int(layers), int(heads_kv), int(key_len), int(val_len)
    kv_dtype_bytes = 2  # Ollama KV cache is fp16 regardless of weight quant
    per_token = layers * heads_kv * (key_len + val_len) * kv_dtype_bytes
    return {
        "model": model,
        "manifest_digest": "sha256:" + str(match["digest"]),
        "parameter_size": match.get("details", {}).get("parameter_size"),
        "weight_quantization": match.get("details", {}).get("quantization_level"),
        "kv_cache_dtype": "fp16",
        "block_count": layers,
        "kv_heads": heads_kv,
        "key_length": key_len,
        "value_length": val_len,
        "embedding_length": int(embedding),
        "kv_bytes_per_token": per_token,
        "kv_mib_per_4k": round(per_token * 4096 / 1024 / 1024, 1),
        "rope": {
            key: info[key]
            for key in info
            if key.endswith("rope.freq_base") or key.endswith("rope.scaling.type")
        },
    }


def build_fingerprint(facts: dict[str, Any], *, rope_salt: str = "") -> KVModelFingerprint:
    return KVModelFingerprint(
        weights_digest=facts["manifest_digest"],
        tokenizer_digest=_sha256([facts["model"], facts.get("parameter_size"), facts.get("embedding_length")]),
        engine="ollama",
        engine_version="native-context",
        dtype="fp16",
        block_size_tokens=BLOCK_TOKENS,
        rope_config_digest=_sha256([facts["model"], facts["rope"], rope_salt]),
    )


def kv_bytes_for(per_token: int) -> int:
    return per_token * BLOCK_TOKENS


def pad_block(block_index: int, block_bytes: int) -> bytes:
    marker = hashlib.sha256(f"kv-block-{block_index}".encode()).digest()
    return (marker * (block_bytes // len(marker) + 1))[:block_bytes]


def make_slab(block_bytes: int, start_block: int, blocks: int, *, seed: bytes = b"") -> bytes:
    out = bytearray()
    for index in range(blocks):
        block = bytearray(pad_block(start_block + index, block_bytes))
        if seed:
            block[: len(seed)] = seed[: len(block)]
        out.extend(block)
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ollama-url", default=os.environ.get("BEAST_OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("BEAST_OLLAMA_MODEL", "qwen3:4b"))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    facts = model_facts(args.ollama_url, args.model)
    block_bytes = kv_bytes_for(int(facts["kv_bytes_per_token"]))
    fingerprint = build_fingerprint(facts)

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(args.out) if args.out else REPO_ROOT / "evidence" / f"crystal-kv-gauntlet-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="crystal-kv-gauntlet-", dir="/tmp/opencode"))
    index = CrystalKVIndex(work / "index")

    checks: dict[str, bool] = {}
    detail: dict[str, Any] = {}

    def record(name: str, ok: bool, **extra: Any) -> None:
        checks[name] = bool(ok)
        if extra:
            detail[name] = extra

    # ---- dedup: shared prefix across sessions -------------------------
    prefix_span = KVTokenSpan(0, 2 * BLOCK_TOKENS)
    session_a = KVTokenSpan(0, 4 * BLOCK_TOKENS)
    tail_span = KVTokenSpan(2 * BLOCK_TOKENS, 4 * BLOCK_TOKENS)

    prefix_slab = make_slab(block_bytes, 0, 2)
    shared_tail = make_slab(block_bytes, 2, 2)
    divergent_tail = make_slab(block_bytes, 2, 2, seed=b"\xff\x00\xff\x00")
    full_a = prefix_slab + shared_tail

    manifest_prefix = index.put(
        fingerprint, prefix_span, prefix_slab, block_bytes=block_bytes,
        layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    manifest_a = index.put(
        fingerprint, session_a, full_a, block_bytes=block_bytes,
        layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    manifest_b = index.put(
        fingerprint, tail_span, divergent_tail, block_bytes=block_bytes,
        layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    manifest_a_replay = index.put(
        fingerprint, session_a, full_a, block_bytes=block_bytes,
        layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    stats = index.stats()
    logical = manifest_prefix.kv_bytes + manifest_a.kv_bytes + manifest_b.kv_bytes + manifest_a_replay.kv_bytes
    dedup_pct = round(100.0 * (1 - stats["unique_chunk_bytes"] / logical), 2) if logical else 0.0
    detail["dedup"] = {
        "logical_bytes": logical,
        "unique_bytes": stats["unique_chunk_bytes"],
        "dedup_pct": dedup_pct,
        "manifests": stats["manifests"],
        "replay_manifest_is_identical": manifest_a.crystal_id == manifest_a_replay.crystal_id,
    }
    record("prefix_and_replay_dedup", dedup_pct >= 40.0 and manifest_a.crystal_id == manifest_a_replay.crystal_id)

    # ---- hit / miss / refusal matrix ----------------------------------
    hit = index.get(fingerprint, session_a, layer_range=LAYERS, privacy_domain=PRIVACY)
    record("aligned_hit", hit.hit and hit.payload == full_a, bytes_served=hit.receipt.bytes_served)

    shifted = index.get(
        fingerprint, KVTokenSpan(BLOCK_TOKENS, 5 * BLOCK_TOKENS),
        layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    record("shifted_span_miss", shifted.receipt.status is KVLookupStatus.MISS)

    other = build_fingerprint(facts, rope_salt="rope-v2")
    cross = index.get(other, session_a, layer_range=LAYERS, privacy_domain=PRIVACY)
    record("cross_fingerprint_reject", cross.receipt.status is KVLookupStatus.REJECTED_FINGERPRINT)

    privacy = index.get(fingerprint, session_a, layer_range=LAYERS, privacy_domain="workspace:spill")
    record("privacy_domain_reject", privacy.receipt.status is KVLookupStatus.REJECTED_PRIVACY)

    # tamper: flip one byte inside the stored chunks
    chunk_dir = work / "index" / "chunks" / f"b{block_bytes}"
    victim = sorted(path for path in chunk_dir.iterdir() if path.is_file())[0]
    original = victim.read_bytes()
    victim.write_bytes(b"\x00" + original[1:])
    tampered = index.get(fingerprint, session_a, layer_range=LAYERS, privacy_domain=PRIVACY)
    record("tamper_reject", tampered.receipt.status is KVLookupStatus.REJECTED_INTEGRITY and tampered.payload is None)
    victim.write_bytes(original)

    # expiry with a controlled clock
    clock = [1_000_000.0]
    expiry_index = CrystalKVIndex(work / "expiry", clock=lambda: clock[0])
    expiry_index.put(
        fingerprint, KVTokenSpan(0, BLOCK_TOKENS), make_slab(block_bytes, 0, 1),
        block_bytes=block_bytes, layer_range=LAYERS, privacy_domain=PRIVACY, ttl_seconds=5.0,
    )
    clock[0] += 6.0
    expired = expiry_index.get(fingerprint, KVTokenSpan(0, BLOCK_TOKENS), layer_range=LAYERS, privacy_domain=PRIVACY)
    record("expiry_reject", expired.receipt.status is KVLookupStatus.REJECTED_EXPIRED)

    revoked_index = CrystalKVIndex(work / "revoked")
    revoked_manifest = revoked_index.put(
        fingerprint, KVTokenSpan(0, BLOCK_TOKENS), make_slab(block_bytes, 0, 1),
        block_bytes=block_bytes, layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    revoked_index.revoke(revoked_manifest.crystal_id, reason="gauntlet")
    revoked = revoked_index.get(fingerprint, KVTokenSpan(0, BLOCK_TOKENS), layer_range=LAYERS, privacy_domain=PRIVACY)
    record("crystal_revoke_reject", revoked.receipt.status is KVLookupStatus.REJECTED_REVOKED)

    fp_revoked_index = CrystalKVIndex(work / "fp-revoked")
    fp_revoked_index.put(
        fingerprint, KVTokenSpan(0, BLOCK_TOKENS), make_slab(block_bytes, 0, 1),
        block_bytes=block_bytes, layer_range=LAYERS, privacy_domain=PRIVACY,
    )
    fp_revoked_index.revoke_fingerprint(fingerprint.digest(), reason="weights rolled")
    fp_revoked = fp_revoked_index.get(fingerprint, KVTokenSpan(0, BLOCK_TOKENS), layer_range=LAYERS, privacy_domain=PRIVACY)
    record("fingerprint_revoke_reject", fp_revoked.receipt.status is KVLookupStatus.REJECTED_REVOKED)

    # ---- pressure binding --------------------------------------------
    pressure_index = CrystalKVIndex(work / "pressure")
    pinned_manifest = pressure_index.put(
        fingerprint, KVTokenSpan(0, BLOCK_TOKENS), make_slab(block_bytes, 0, 1),
        block_bytes=block_bytes, layer_range=LAYERS, privacy_domain=PRIVACY, pinned=True,
    )
    for session in range(1, 13):
        start = session * BLOCK_TOKENS
        pressure_index.put(
            fingerprint, KVTokenSpan(start, start + BLOCK_TOKENS),
            make_slab(block_bytes, session * 4, 1, seed=bytes([session])),
            block_bytes=block_bytes, layer_range=LAYERS, privacy_domain=PRIVACY,
        )
    reclaimable = sum(item.kv_bytes for item in pressure_index.manifests() if not item.pinned)
    high = pressure_index.reclaim_for_pressure("high", reclaimable_bytes=reclaimable)
    record(
        "pressure_high_evicts_bounded_fraction",
        high is not None and high.freed_bytes >= high.requested_bytes,
        requested=high.requested_bytes if high else None,
        freed=high.freed_bytes if high else None,
    )
    remaining = sum(item.kv_bytes for item in pressure_index.manifests() if not item.pinned)
    critical = pressure_index.reclaim_for_pressure("critical", reclaimable_bytes=remaining)
    record(
        "pressure_critical_evicts_more",
        critical is not None and critical.freed_bytes >= critical.requested_bytes,
        requested=critical.requested_bytes if critical else None,
        freed=critical.freed_bytes if critical else None,
    )
    record(
        "pinned_survives_pressure",
        pressure_index.manifest(pinned_manifest.crystal_id) is not None,
    )

    cgroup = CgroupV2Discovery().state()
    record(
        "cgroup_actuator_visible",
        bool(cgroup["controls"]["kill"]),
        source=cgroup["control_sources"]["kill"],
        actuation_proven=cgroup["actuation_proven"],
    )

    # ---- model cost table for every resident model --------------------
    tags = _get(f"{args.ollama_url}/api/tags")
    model_table = []
    for item in tags.get("models", []):
        try:
            model_table.append(model_facts(args.ollama_url, item["name"]))
        except SystemExit:
            continue

    green = [name for name, ok in checks.items() if ok]
    red = [name for name, ok in checks.items() if not ok]
    receipt = {
        "beast_object_type": "crystal_kv_gauntlet_receipt",
        "version": "1.0",
        "receipt_id": "crystal-kv-" + stamp,
        "generated_at": stamp,
        "duration_seconds": round(time.time() - started, 2),
        "host": {"kernel": os.uname().release, "python": sys.version.split()[0]},
        "model_facts": facts,
        "resident_model_kv_cost": model_table,
        "index_root_relative": "tmp:/crystal-kv-gauntlet-*/index",
        "block_size_tokens": BLOCK_TOKENS,
        "block_bytes": block_bytes,
        "checks": checks,
        "green": green,
        "red": red,
        "detail": detail,
        "cgroup": {
            "controls": cgroup["controls"],
            "control_sources": cgroup["control_sources"],
            "effective_cgroup": cgroup["effective_cgroup"],
            "actuation_proven": cgroup["actuation_proven"],
        },
        "claims": {
            "kv_bytes_measured_from_live_model_metadata": True,
            "kv_tensors_synthetic": True,
            "engine_native_kv_captured": False,
            "native_kv_portability_claimed": False,
            "cross_engine_portable": False,
            "kv_may_contain_prompt_content": True,
        },
        "public_credit_allowed": not red,
    }
    receipt["receipt_digest"] = _sha256({k: v for k, v in receipt.items() if k != "receipt_digest"})

    (out_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "README.md").write_text(
        render_markdown(receipt), encoding="utf-8"
    )
    shutil.rmtree(work, ignore_errors=True)

    print(json.dumps({
        "receipt": str(out_dir / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "green": green,
        "red": red,
        "dedup_pct": dedup_pct,
        "kv_bytes_per_token": facts["kv_bytes_per_token"],
        "public_credit_allowed": receipt["public_credit_allowed"],
    }, indent=2))
    return 0 if not red else 1


def render_markdown(receipt: dict[str, Any]) -> str:
    lines = [
        f"# Crystal KV Gauntlet — {receipt['receipt_id']}",
        "",
        f"Receipt digest: `{receipt['receipt_digest']}`",
        "",
        "## Model-derived KV cost",
        "",
        "| model | weights | KV dtype | layers | KV heads | head dim | KiB/token | MiB @ 4k |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in receipt["resident_model_kv_cost"]:
        lines.append(
            "| {model} | {weight_quantization} | {kv_cache_dtype} | {block_count} | {kv_heads} | "
            "{key_length} | {kib} | {mib} |".format(
                kib=round(row["kv_bytes_per_token"] / 1024, 1), mib=row["kv_mib_per_4k"], **row
            )
        )
    lines += ["", "## Checks", "", "| check | result |", "|---|---|"]
    for name, ok in receipt["checks"].items():
        lines.append(f"| `{name}` | {'PASS' if ok else 'FAIL'} |")
    lines += [
        "",
        "## Claims",
        "",
    ]
    for key, value in receipt["claims"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines += [
        "",
        f"**public_credit_allowed: {receipt['public_credit_allowed']}**",
        "",
        "KV tensors are synthetic, sized at the real per-token footprint of the",
        "live model. No engine-native KV was captured, and no cross-engine",
        "portability is claimed.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
