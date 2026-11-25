#!/usr/bin/env python
"""Live gauntlet: PSI snapshot -> governor -> crystal KV eviction -> receipt.

This exercises the real objects, not fakes:

* :class:`LinuxPSIReader` reads the host's actual ``/proc/pressure/*``;
* :class:`ResidualPressureGovernor` classifies it;
* :class:`CrystalKVTier` + :class:`CrystalKVIndex` store and then evict real
  bytes on a real filesystem;
* :class:`ReclaimPolicy` applies the ordered ladder and emits a
  ``reclaim_receipt``;
* :class:`CgroupV2Discovery` reports whether the cgroup rungs are even
  reachable on this host, and that fact is recorded rather than assumed;
* the receipt is validated against the canon registry.

Honesty
-------
The host is not under memory pressure while this runs, so the observed level
is reported as-is.  The eviction path is additionally driven at a *forced*
``high`` and ``critical`` level so the ladder is proven; each receipt is
labelled ``level_forced`` and ``observed_level`` is kept alongside.

Run:  python scripts/run_reclaim_policy_gauntlet.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.kernel.compute.crystal_kv_index import (  # noqa: E402
    KVModelFingerprint,
    KVTokenSpan,
)
from app.kernel.compute.kv_crystal_tier import CrystalKVTier  # noqa: E402
from app.kernel.compute.reclaim_policy import ReclaimPolicy  # noqa: E402
from app.kernel.compute.residual_pressure_governor import (  # noqa: E402
    LinuxPSIReader,
    ResidualPressureGovernor,
)
from app.kernel.execution.cgroup_capsule import CgroupV2Discovery  # noqa: E402
from app.kernel.registry.canon_registry import CanonRegistry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / f"reclaim-policy-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
BLOCK_TOKENS = 16
BLOCK_BYTES = 64 * 1024


def fingerprint(seed: int) -> KVModelFingerprint:
    return KVModelFingerprint(
        weights_digest="sha256:" + hashlib.sha256(f"weights-{seed}".encode()).hexdigest(),
        tokenizer_digest="sha256:" + hashlib.sha256("tokenizer".encode()).hexdigest(),
        engine="ollama",
        engine_version="0.6.2",
        dtype="fp16",
        block_size_tokens=BLOCK_TOKENS,
        rope_config_digest="sha256:" + hashlib.sha256("rope".encode()).hexdigest(),
    )


def payload(seed: int, blocks: int = 4) -> bytes:
    out = bytearray()
    for block in range(blocks):
        base = bytes([(seed * 13 + block * 7 + i) % 251 for i in range(BLOCK_BYTES)])
        out.extend(base)
    return bytes(out)


def main() -> int:
    checks: list[dict] = []

    def record(name: str, ok: bool, detail: str, **extra) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail, **extra})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # 1. real PSI
    snapshot = LinuxPSIReader().read()
    governor = ResidualPressureGovernor()
    decision = governor.classify(snapshot)
    observed = decision.level.value
    record(
        "psi_snapshot_read",
        snapshot.available_memory_bytes is not None,
        f"observed={observed} mem_available={snapshot.available_memory_bytes} "
        f"mem_some_avg10={snapshot.memory.some.avg10}",
    )

    # 2. cgroup reachability (recorded, not assumed)
    cgroup_state = CgroupV2Discovery().state()
    record(
        "cgroup_discovery",
        bool(cgroup_state.get("available")),
        f"actuation_proven={cgroup_state.get('actuation_proven')} "
        f"delegated_writable={cgroup_state.get('delegated_writable')}",
        state={
            "actuation_proven": cgroup_state.get("actuation_proven"),
            "delegated_writable": cgroup_state.get("delegated_writable"),
            "controls": cgroup_state.get("controls"),
        },
    )

    tmp = Path(tempfile.mkdtemp(prefix="beast-reclaim-"))
    tier = CrystalKVTier(tmp / "crystal", privacy_domain="gauntlet", ttl_seconds=3600)

    # 3. store real KV bytes
    manifests = []
    for seed in range(2):
        fp = fingerprint(seed)
        span = KVTokenSpan(0, BLOCK_TOKENS * 4)
        manifests.append(
            tier.index.put(
                fp,
                span,
                payload(seed),
                block_bytes=BLOCK_BYTES,
                layer_range=(0, 27),
                privacy_domain="gauntlet",
                ttl_seconds=3600,
            )
        )
    before = tier.stats()
    record(
        "kv_bytes_stored",
        before["manifests"] == 2 and before["unique_chunk_bytes"] == 8 * BLOCK_BYTES,
        f"manifests={before['manifests']} unique_chunk_bytes={before['unique_chunk_bytes']}",
    )

    # 4. advisory pressure must not mutate
    advisory = ReclaimPolicy(kv_tier=tier)
    advisory_receipt = advisory.run("rising").as_dict()
    after_advisory = tier.stats()
    record(
        "advisory_no_mutation",
        advisory_receipt["acted"] is False and after_advisory["manifests"] == before["manifests"],
        f"stopped_because={advisory_receipt['stopped_because']} manifests={after_advisory['manifests']}",
    )

    # 5. forced high: real eviction of real bytes
    high_policy = ReclaimPolicy(kv_tier=tier, total_cap_bytes=BLOCK_BYTES * 4)
    high_receipt = high_policy.run("high", snapshot_digest=snapshot.digest).as_dict()
    after_high = tier.stats()
    record(
        "high_evicts_real_bytes",
        high_receipt["freed_bytes"] > 0 and after_high["unique_chunk_bytes"] < before["unique_chunk_bytes"],
        f"freed={high_receipt['freed_bytes']}kv_bytes={after_high['kv_bytes']}",
    )

    # 6. critical: evicts the remainder
    critical_policy = ReclaimPolicy(kv_tier=tier, total_cap_bytes=BLOCK_BYTES * 8)
    critical_receipt = critical_policy.run("critical", snapshot_digest=snapshot.digest).as_dict()
    after_critical = tier.stats()
    record(
        "critical_reclaims_rest",
        after_critical["manifests"] == 0 and after_critical["unique_chunk_bytes"] == 0,
        f"manifests={after_critical['manifests']} unique_chunk_bytes={after_critical['unique_chunk_bytes']}",
    )

    # 7. canon validation
    registry = CanonRegistry()
    validation_high = registry.validate_object(high_receipt)
    validation_critical = registry.validate_object(critical_receipt)
    record(
        "canon_reclaim_receipt_valid",
        validation_high["valid"] and validation_critical["valid"],
        f"high_errors={validation_high['errors']} critical_errors={validation_critical['errors']}",
    )

    # 8. no authorization -> capsule rung refused, never performed
    class NoopCapsule:
        def __init__(self):
            self.calls = 0

        def reclaim_memory(self, *_args, **_kwargs):
            self.calls += 1
            raise AssertionError("must not be called without authorization")

    capsule = NoopCapsule()
    gate = ReclaimPolicy(kv_tier=None, capsules={"m1": capsule})
    gate_receipt = gate.run("high").as_dict()
    step = next(s for s in gate_receipt["steps"] if s["step"] == "cgroup_memory_reclaim")
    record(
        "authorization_gate_holds",
        step["status"] == "refused" and capsule.calls == 0,
        f"status={step['status']} reason={step['reason']}",
    )

    ok = all(check["ok"] for check in checks)
    receipt = {
        "beast_object_type": "reclaim_policy_gauntlet",
        "version": "1.0",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ok": ok,
        "checks": checks,
        "observed_pressure_level": observed,
        "observed_snapshot_digest": snapshot.digest,
        "level_forced": True,
        "cgroup": {
            "actuation_proven": cgroup_state.get("actuation_proven"),
            "delegated_writable": cgroup_state.get("delegated_writable"),
        },
        "before": before,
        "after_high": after_high,
        "after_critical": after_critical,
        "high_receipt": high_receipt,
        "critical_receipt": critical_receipt,
        "advisory_receipt": advisory_receipt,
        "authorization_gate_receipt": gate_receipt,
        "native_kv_portability_claimed": False,
        "cross_engine_portable": False,
    }
    body = json.dumps(receipt, indent=2, sort_keys=True, default=str)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "receipt.json").write_text(body, encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(body.encode()).hexdigest()
    (EVIDENCE / "receipt.sha256").write_text(digest + "\n", encoding="utf-8")

    print()
    print(f"checks: {sum(1 for c in checks if c['ok'])}/{len(checks)}")
    print(f"evidence: {EVIDENCE.relative_to(ROOT)}")
    print(f"digest: {digest}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
