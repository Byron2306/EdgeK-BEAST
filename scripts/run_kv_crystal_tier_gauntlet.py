#!/usr/bin/env python
"""End-to-end gauntlet: transport STORAGE tier -> restart -> dedup -> revocation.

Proves the crystal KV storage tier as it is actually used by
``CrossEngineKVCacheTransport``, not just the index underneath it:

1. ``move(STORAGE)`` writes no raw payload file;
2. identical bytes under different prefixes are stored once;
3. a fresh process restores the exact bytes from the CAS;
4. a revoked crystal stays unreadable after restart;
5. a forced cleanup releases the chunk files (measured on the filesystem);
6. the tier footprint admits into ``PhysicalLedger`` and an over-large
   request is denied with a shortfall;
7. every receipt validates against the canon registry.

Synthetic tensors at a real per-token footprint.  No engine-native KV is
captured and no cross-engine portability is claimed.

Run:  python scripts/run_kv_crystal_tier_gauntlet.py
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.kv_crystal_tier import CrystalKVTier  # noqa: E402
from app.kernel.compute.kv_transport import (  # noqa: E402
    CacheEngine,
    CacheLocation,
    CrossEngineKVCacheTransport,
)
from app.kernel.compute.physical_ledger import PhysicalLedger  # noqa: E402
from app.kernel.registry.canon_registry import CanonRegistry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / f"kv-crystal-tier-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
PAYLOAD_BYTES = 32 * 1024
SEQ_LEN = 16


def body(seed: int) -> bytes:
    return bytes([(seed * 29 + offset * 3) % 251 for offset in range(PAYLOAD_BYTES)])


def tier(root: Path) -> CrystalKVTier:
    return CrystalKVTier(root / "crystal", privacy_domain="gauntlet", ttl_seconds=3600)


def transport(root: Path, kv_tier: CrystalKVTier) -> CrossEngineKVCacheTransport:
    return CrossEngineKVCacheTransport(storage_dir=root / "kv", crystal_tier=kv_tier)


def register(tp: CrossEngineKVCacheTransport, prefix: str, payload: bytes, *, model: str = "qwen2.5-coder:7b"):
    return tp.register_block(
        model=model,
        tokenizer=model,
        prompt_prefix=prefix,
        system_prompt="beast-agent-coder",
        engine=CacheEngine.OLLAMA,
        location=CacheLocation.CPU,
        precision="fp16",
        num_layers=28,
        num_heads=28,
        head_dim=128,
        seq_len=SEQ_LEN,
        size_bytes=len(payload),
        tensor_payload=payload,
    )


def du(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str, **extra) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail, **extra})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    root = Path(tempfile.mkdtemp(prefix="beast-tier-"))
    try:
        kv_tier = tier(root)
        tp = transport(root, kv_tier)

        # 1. storage move writes no raw payload
        block_a = register(tp, "def alpha(x):\n    return x\n", body(0))
        assert tp.move(block_a.block_id, CacheLocation.STORAGE) is True
        raw = root / "kv" / f"{block_a.block_id}.bin"
        record(
            "no_raw_payload_file",
            not raw.exists(),
            f"raw_bin_exists={raw.exists()} manifest_exists={(root / 'kv' / f'{block_a.block_id}.json').exists()}",
        )

        # 2. dedup: identical bytes, different prefix
        block_b = register(tp, "def beta(y):\n    return y\n", body(0))
        assert block_b.block_id != block_a.block_id
        assert tp.move(block_b.block_id, CacheLocation.STORAGE) is True
        stats = kv_tier.stats()
        receipt_b = block_b.metadata["crystal_storage"]
        record(
            "dedup_identical_bytes",
            stats["unique_chunk_bytes"] == PAYLOAD_BYTES and receipt_b["dedup_bytes_saved"] == PAYLOAD_BYTES,
            f"unique_chunk_bytes={stats['unique_chunk_bytes']} dedup_saved={receipt_b['dedup_bytes_saved']}",
        )

        # 3. restart: fresh objects over the same roots
        reboot_tier = tier(root)
        reboot = transport(root, reboot_tier)
        again = register(reboot, "def alpha(x):\n    return x\n", body(0))
        assert again.block_id == block_a.block_id
        assert reboot.move(again.block_id, CacheLocation.CPU) is True
        restored = reboot.export_tensor_payload(again.block_id)
        record(
            "restart_restores_exact_bytes",
            restored == body(0),
            f"bytes={len(restored or b'')} match={restored == body(0)}",
        )

        # 4. revocation survives restart
        revoke_tier = tier(root)
        revoke_tp = transport(root, revoke_tier)
        target = register(revoke_tp, "def gamma(z):\n    return z\n", body(7))
        assert revoke_tp.move(target.block_id, CacheLocation.STORAGE) is True
        revoke_receipt = revoke_tier.revoke(target, reason="gauntlet privacy deletion")
        fresh_tier = tier(root)
        fresh_tp = transport(root, fresh_tier)
        fresh_block = register(fresh_tp, "def gamma(z):\n    return z\n", body(7))
        fresh_block = fresh_tp.blocks[fresh_block.block_id]
        restored_revoked, lookup = fresh_tier.restore(fresh_block)
        record(
            "revocation_survives_restart",
            revoke_receipt.ok and restored_revoked is None and "revok" in (lookup.reason or "").lower(),
            f"revoke_ok={revoke_receipt.ok} restore={restored_revoked is not None} reason={lookup.reason}",
        )

        # 5. forced cleanup frees chunk files (filesystem measurement)
        before_bytes = du(root / "crystal" / "chunks")
        evicted = revoke_tp.cleanup(force=True)
        after_bytes = du(root / "crystal" / "chunks")
        record(
            "forced_cleanup_frees_chunks",
            after_bytes < before_bytes and evicted,
            f"before={before_bytes} after={after_bytes} evicted={len(evicted)}",
        )

        # 6. ledger admission over the tier footprint
        footprint = max(0, du(root / "crystal"))
        book = PhysicalLedger({"nvme_kv": max(footprint * 2, 1 << 20)})
        admitted = book.admit("kv_crystal_tier", "nvme_kv", footprint, privacy_domain="gauntlet")
        denied = book.admit("oversized", "nvme_kv", book.available_bytes("nvme_kv") + 1, privacy_domain="gauntlet")
        record(
            "ledger_admits_and_denies",
            admitted.ok and not denied.ok and denied.shortfall_bytes == 1,
            f"footprint={footprint} admitted={admitted.ok} denied={denied.denied_reason}",
        )
        book.release(admitted.lease_id, reason="gauntlet end")

        # 7. canon validation
        canon = CanonRegistry()
        objects = [
            receipt_b,
            revoke_receipt.as_dict(),
            admitted.as_dict(),
            denied.as_dict(),
            book.state(),
            kv_tier.stats(),
        ]
        invalid = [obj.get("beast_object_type") for obj in objects if not canon.validate_object(obj)["valid"]]
        record("canon_receipts_valid", not invalid, f"invalid={invalid}")

        ok = all(check["ok"] for check in checks)
        receipt = {
            "beast_object_type": "kv_crystal_tier_gauntlet",
            "version": "1.0",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ok": ok,
            "checks": checks,
            "payload_bytes": PAYLOAD_BYTES,
            "synthetic_tensors": True,
            "engine_native_kv_captured": False,
            "cross_engine_portable": False,
            "native_kv_portability_claimed": False,
            "backend": kv_tier.stats()["authority"],
        }
        text = json.dumps(receipt, indent=2, sort_keys=True)
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "receipt.json").write_text(text, encoding="utf-8")
        digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        (EVIDENCE / "receipt.sha256").write_text(digest + "\n", encoding="utf-8")

        print()
        print(f"checks: {sum(1 for c in checks if c['ok'])}/{len(checks)}")
        print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
        print(f"digest: {digest}")
        return 0 if ok else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
