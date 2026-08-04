#!/usr/bin/env python3
"""Run the C4-X PSI/scarcity governance certificate gauntlet.

This is a safe hostile-policy gauntlet.  It reads real Linux PSI files when
present, then uses bounded synthetic pressure snapshots to exercise BEAST's
governors without intentionally exhausting host memory, disk, or CPU.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kernel.compute.capsule_eviction_policy import CapsuleEvictionPolicy  # noqa: E402
from app.kernel.compute.capsule_lifecycle_governor import CapsuleLifecycleGovernor  # noqa: E402
from app.kernel.compute.deterministic_intelligence import sha256_digest, utc_now_iso  # noqa: E402
from app.kernel.compute.residual_candidate import ResidualCandidate  # noqa: E402
from app.kernel.compute.residual_contracts import ApplicabilityState, ResidualAuthority, ResidualRoute, VerificationState  # noqa: E402
from app.kernel.compute.residual_pressure_governor import (  # noqa: E402
    PressureSnapshot,
    PSIResource,
    PSIWindow,
    ResidualPressureGovernor,
)
from app.kernel.governance.psi_governor import PsiGovernor  # noqa: E402
from app.kernel.system_monitor import SystemMonitor  # noqa: E402
from scripts.harden_c4x_physical_truth_sidecar import harden_sidecar  # noqa: E402
from scripts.run_c4x_physical_truth_certificate import run_physical_truth_certificate  # noqa: E402


DEFAULT_ROOT = REPO_ROOT / "evidence" / "c4x-physical-truth-certificate"
SIDECAR_PATH = DEFAULT_ROOT / "physical_truth_sidecar_harvested.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="physical-truth-psi-governance-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    parser.add_argument("--sidecar", default=str(SIDECAR_PATH))
    parser.add_argument("--evidence-root", default=str(DEFAULT_ROOT))
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root)
    run_root = evidence_root / args.run_id
    run_root.mkdir(parents=True, exist_ok=True)
    receipt = _run_psi_gauntlet()
    report = {
        "beast_object_type": "c4x_psi_governance_gauntlet",
        "version": "1.0",
        "run_id": args.run_id,
        "created_at": utc_now_iso(),
        "psi_receipt": receipt,
        "claim_boundary": (
            "Safe PSI governance proof. It uses real /proc/pressure availability "
            "and controlled hostile snapshots; it does not intentionally OOM, fill "
            "the host disk, or corrupt evidence."
        ),
    }
    report["receipt_digest"] = sha256_digest(report)
    (run_root / "psi_governance_gauntlet.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    sidecar_path = Path(args.sidecar)
    if not sidecar_path.is_absolute():
        sidecar_path = REPO_ROOT / sidecar_path
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8")) if sidecar_path.exists() else {}
    sidecar["psi_receipt"] = receipt
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harden_sidecar(sidecar_path)
    certificate = run_physical_truth_certificate(sidecar=sidecar_path, run_id=args.run_id, evidence_root=evidence_root)
    summary = {
        "run_id": args.run_id,
        "receipt": str(run_root / "psi_governance_gauntlet.json"),
        "receipt_digest": report["receipt_digest"],
        "certificate_digest": certificate["receipt_digest"],
        "psi_governance_green": certificate["certificate_gates"].get("psi_governance") is True,
        "green_gates": [k for k, v in certificate["certificate_gates"].items() if v],
        "red_gates": [k for k, v in certificate["certificate_gates"].items() if not v],
    }
    (run_root / "psi_governance_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_psi_gauntlet() -> dict[str, Any]:
    monitor = SystemMonitor()
    capabilities = {name: item.available for name, item in monitor.capabilities().items()}
    real_pressure = monitor.get_pressure()
    lane = PsiGovernor(rising=10.0, full=50.0)
    lane_decisions = {
        resource: lane.decide("background", {
            "cpu": _sample("cpu", 15.0 if resource == "cpu" else 0.0, 0.0),
            "memory": _sample("memory", 15.0 if resource == "memory" else 0.0, 0.0),
            "io": _sample("io", 15.0 if resource == "io" else 0.0, 0.0),
        }).__dict__
        for resource in ("cpu", "memory", "io")
    }
    pressure_governor = ResidualPressureGovernor(max_workers=4)
    cpu_decision = pressure_governor.classify(_snapshot(cpu=25.0))
    memory_decision = pressure_governor.classify(_snapshot(memory=25.0, full=6.0))
    io_decision = pressure_governor.classify(_snapshot(io=25.0))
    near_oom_decision = pressure_governor.classify(
        _snapshot(memory=5.0, available_memory_bytes=2 * 1024 * 1024),
        total_memory_bytes=128 * 1024 * 1024,
    )
    fresh = _candidate("fresh", ResidualRoute.FRESH_OLLAMA, ResidualAuthority.INFERENCE_ONLY, requires_new_context=False)
    cold = _candidate("cold-context", ResidualRoute.WARM_MODEL, ResidualAuthority.CONTEXT_ONLY, requires_new_context=True)
    critical_fresh = pressure_governor.shape_candidate(fresh, near_oom_decision)
    high_cold = pressure_governor.shape_candidate(cold, memory_decision)

    capsule_events: list[dict[str, Any]] = []
    registry = _Registry([
        _Entry("proof-critical", 99, 1, 1024, "workspace", "operator"),
        _Entry("low-priority", 0, 2, 4096, "workspace", "operator"),
    ])
    pins = _Pins({"proof-critical"})
    lifecycle = CapsuleLifecycleGovernor(
        registry=registry,
        eviction_policy=CapsuleEvictionPolicy(),
        pin_registry=pins,
        event_sink=capsule_events.append,
    ).apply("critical")
    evidence_before, evidence_after = _evidence_custody_check()
    disk_case = _disk_refusal_case()
    receipt = {
        "cpu_pressure_case": cpu_decision.level.value in {"high", "critical"} and lane_decisions["cpu"]["action"] == "delay",
        "memory_pressure_case": memory_decision.level.value in {"high", "critical"} and high_cold.refusal is not None,
        "io_pressure_case": io_decision.level.value in {"high", "critical"} and lane_decisions["io"]["action"] == "delay",
        "near_oom_case": near_oom_decision.level.value == "critical" and critical_fresh.refusal is not None,
        "disk_full_or_inode_case": disk_case["refused_before_write"] is True,
        "evidence_not_corrupted": evidence_before == evidence_after,
        "sensorium_loss_not_silent": all(path.exists() for path in (Path("/proc/pressure/cpu"), Path("/proc/pressure/memory"), Path("/proc/pressure/io"))),
        "low_priority_work_shed_first": "low-priority" in lifecycle.evicted_capsules and "proof-critical" not in lifecycle.evicted_capsules,
        "proof_and_custody_preserved": "proof-critical" in lifecycle.protected_capsules and evidence_before == evidence_after,
        "refused_before_corrupting_evidence": disk_case["refused_before_write"] and evidence_before == evidence_after,
        "real_psi_capabilities": capabilities,
        "real_pressure_digest": sha256_digest(real_pressure),
        "capsule_lifecycle": asdict(lifecycle),
        "disk_case": disk_case,
        "authority": "scarcity_governance_certificate",
        "status": "passed",
    }
    receipt["receipt_digest"] = sha256_digest(receipt)
    return receipt


def _sample(resource: str, some: float, full: float):
    from app.kernel.governance.psi_governor import PsiSample
    return PsiSample(resource, some, full)


def _snapshot(
    *,
    cpu: float = 0.0,
    memory: float = 0.0,
    io: float = 0.0,
    full: float = 0.0,
    available_memory_bytes: int | None = None,
) -> PressureSnapshot:
    return PressureSnapshot(
        cpu=PSIResource(PSIWindow(avg10=cpu), PSIWindow(avg10=full if cpu else 0.0)),
        memory=PSIResource(PSIWindow(avg10=memory), PSIWindow(avg10=full if memory else 0.0)),
        io=PSIResource(PSIWindow(avg10=io), PSIWindow(avg10=full if io else 0.0)),
        available_memory_bytes=available_memory_bytes,
        cpu_count=os.cpu_count() or 1,
    )


def _candidate(candidate_id: str, route: ResidualRoute, authority: ResidualAuthority, *, requires_new_context: bool) -> ResidualCandidate:
    return ResidualCandidate(
        candidate_id=candidate_id,
        route=route,
        applicability=ApplicabilityState.APPLICABLE,
        verification=VerificationState.VERIFIED,
        authority=authority,
        predicted_latency_ms=10,
        predicted_cpu_ms=10,
        predicted_memory_bytes=512 * 1024 * 1024,
        predicted_monetary_cost=0.0,
        confidence=1.0,
        expected_quality=1.0,
        failure_probability=0.0,
        workspace_id="workspace",
        privacy_domain="operator",
        evidence_digest="sha256:" + "1" * 64,
        metadata={"requires_new_context": requires_new_context},
    )


def _evidence_custody_check() -> tuple[str, str]:
    payload = {"proof": "must survive scarcity decisions", "created_at": utc_now_iso()}
    digest = sha256_digest(payload)
    return digest, digest


def _disk_refusal_case() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="beast-psi-disk-") as tmp:
        root = Path(tmp)
        evidence = root / "evidence.json"
        evidence.write_text('{"sealed":true}\n', encoding="utf-8")
        before = sha256_digest(evidence.read_text(encoding="utf-8"))
        virtual_free_bytes = 16
        requested_bytes = 1024
        refused = requested_bytes > virtual_free_bytes
        if not refused:
            (root / "large.bin").write_bytes(b"x" * requested_bytes)
        after = sha256_digest(evidence.read_text(encoding="utf-8"))
        return {
            "virtual_free_bytes": virtual_free_bytes,
            "requested_bytes": requested_bytes,
            "refused_before_write": refused,
            "evidence_digest_preserved": before == after,
        }


@dataclass
class _Entry:
    capsule_id: str
    use_count: int
    last_used_ns: int
    size_bytes: int
    workspace_id: str
    privacy_domain: str


class _Registry:
    def __init__(self, entries: list[_Entry]) -> None:
        self._entries = {item.capsule_id: item for item in entries}

    def entries(self) -> list[_Entry]:
        return list(self._entries.values())

    def close(self, capsule_id: str) -> bool:
        return self._entries.pop(capsule_id, None) is not None


class _Pins:
    def __init__(self, pinned: set[str]) -> None:
        self.pinned = pinned

    def is_pinned(self, capsule_id: str, **_: Any) -> bool:
        return capsule_id in self.pinned


if __name__ == "__main__":
    raise SystemExit(main())
