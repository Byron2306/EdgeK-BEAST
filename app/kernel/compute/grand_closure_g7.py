from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.crystals.capsule_contracts import (
    ExecutionBounds,
    SealedCrystalCapsuleManifest,
    canonical_json,
    sha256_digest,
)
from app.kernel.crystals.capsule_signing import Ed25519CapsuleSigner
from app.kernel.compute.capsule_economics_bridge import CapsuleEconomicsBridge
from app.kernel.compute.capsule_eviction_policy import CapsuleEvictionPolicy
from app.kernel.compute.capsule_lifecycle_governor import CapsuleLifecycleGovernor
from app.kernel.compute.capsule_registry import CapsuleRegistry
from app.kernel.compute.crystal_capsule_forge import CrystalCapsuleForge
from app.kernel.compute.proof_critical_pinning import ProofCriticalPinRegistry


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class G7CapsuleResult:
    capsule_id: str
    role: str
    reuse_count: int
    preparation_debt_ms: float
    avoided_recompile_ms: float
    residency_cost_ms: float
    verification_cost_ms: float
    net_value_ms: float
    break_even: bool
    credit_eligible: bool
    retained_after_pressure: bool
    proof_critical: bool
    economics_digest: str


@dataclass(frozen=True, slots=True)
class G7ClosureReceipt:
    status: str
    workspace_id: str
    privacy_domain: str
    pressure_sequence: tuple[str, ...]
    profitable_capsule_retained: bool
    negative_capsule_evicted: bool
    proof_critical_capsule_retained: bool
    preparation_debt_observed: bool
    break_even_observed: bool
    credit_before_break_even: bool
    raw_payload_retained: bool
    authority: str
    capsules: tuple[G7CapsuleResult, ...]
    lifecycle_receipts: tuple[Mapping[str, Any], ...]
    event_count: int
    closure_digest: str


class GrandClosureG7:
    """Measured capsule economics plus pressure/lifecycle closure.

    This harness uses real sealed memfd capsules while keeping economics inputs
    explicit and reproducible. It never grants execution authority.
    """

    def __init__(self, *, evidence_dir: str | Path | None = None,
                 event_sink: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        self.evidence_dir = Path(evidence_dir) if evidence_dir else None
        self.events: list[Mapping[str, Any]] = []
        self.event_sink = event_sink or self.events.append

    @staticmethod
    def _manifest(name: str, *, workspace_id: str, privacy_domain: str, signer_id: str) -> SealedCrystalCapsuleManifest:
        def d(text: str) -> str:
            return "sha256:" + hashlib.sha256(text.encode()).hexdigest()
        ir = {"op": "READ_ONLY_REPOSITORY_SUMMARY", "variant": name}
        return SealedCrystalCapsuleManifest(
            crystal_id=f"g7-{name}",
            crystal_ir_version=1,
            artifact_digest=sha256_digest(canonical_json(ir)),
            promotion_digest=d(f"promotion:{name}"),
            policy_digest=d("g7-policy"),
            source_state_digest=d("g7-source-state"),
            workspace_id=workspace_id,
            privacy_domain=privacy_domain,
            task_class="g7_capsule_economics",
            audience_class="executor:g7",
            required_capability="crystal.execute",
            one_use_required=True,
            expires_at=time.time() + 3600,
            execution_bounds=ExecutionBounds(
                max_runtime_ms=200,
                max_memory_bytes=1024 * 1024,
                max_output_bytes=8192,
                filesystem_scope=(),
                network_scope=(),
            ),
            verifier_id="g7-economics-verifier-v1",
            rollback_contract_digest=d("g7-no-effects"),
            signer_id=signer_id,
        )

    def run(self, *, workspace_id: str = "edgek-beast",
            privacy_domain: str = "workspace:edgek-beast") -> G7ClosureReceipt:
        registry = CapsuleRegistry(max_entries=8)
        pins = ProofCriticalPinRegistry(max_pins=8)
        lifecycle_events: list[Mapping[str, Any]] = []
        lifecycle = CapsuleLifecycleGovernor(
            registry=registry,
            eviction_policy=CapsuleEvictionPolicy(),
            pin_registry=pins,
            event_sink=lambda event: (lifecycle_events.append(dict(event)), self.event_sink(dict(event))),
        )
        signer = Ed25519CapsuleSigner("g7-signer", Ed25519PrivateKey.generate())
        forge = CrystalCapsuleForge(registry=registry)
        handles = []
        roles: dict[str, str] = {}
        economics = CapsuleEconomicsBridge()
        economics_receipts: dict[str, Any] = {}
        reuse_counts: dict[str, int] = {}
        critical_id = ""
        preparation_costs: dict[str, float] = {}

        specs = (
            ("profitable", 25.0, 4),
            ("negative", 80.0, 1),
            ("proof-critical", 60.0, 1),
        )
        try:
            for role, preparation_ms, predicted_reuses in specs:
                manifest = self._manifest(role, workspace_id=workspace_id,
                                          privacy_domain=privacy_domain,
                                          signer_id="g7-signer")
                handle, prep = forge.prepare(
                    manifest=manifest,
                    crystal_ir={"op": "READ_ONLY_REPOSITORY_SUMMARY", "variant": role},
                    verifier_manifest={"postcondition": "no_physical_effect"},
                    signer=signer,
                    ttl_seconds=3600,
                    predicted_reuse_count=predicted_reuses,
                )
                handles.append(handle)
                roles[prep.capsule_id] = role
                reuse_counts[prep.capsule_id] = 0
                preparation_costs[prep.capsule_id] = preparation_ms
                self.event_sink({
                    "event_type": "grand_closure.g7.capsule_prepared",
                    "capsule_id": prep.capsule_id,
                    "role": role,
                    "authority": "artifact_only",
                    "raw_payload_retained": False,
                })
                if role == "proof-critical":
                    critical_id = prep.capsule_id
                    pins.pin(
                        artifact_id=prep.capsule_id,
                        workspace_id=workspace_id,
                        privacy_domain=privacy_domain,
                        reason="active grand closure economics proof",
                        ttl_seconds=300,
                        evidence_digest=_digest({"capsule_id": prep.capsule_id, "reason": "g7"}),
                    )

            entries = {entry.capsule_id: entry for entry in registry.entries()}
            for capsule_id, role in roles.items():
                entry = entries[capsule_id]
                if role == "profitable":
                    # First use remains below break-even, later uses repay debt.
                    first = economics.record(
                        capsule_id=capsule_id,
                        preparation_debt_ms=preparation_costs[capsule_id],
                        avoided_recompile_ms=10.0,
                        residency_cost_ms=2.0,
                        verification_cost_ms=2.0,
                        execution_succeeded=True,
                        reuse_count=1,
                    )
                    assert not first.credit_eligible
                    reuse_counts[capsule_id] = 1
                    final = economics.record(
                        capsule_id=capsule_id,
                        preparation_debt_ms=preparation_costs[capsule_id],
                        avoided_recompile_ms=160.0,
                        residency_cost_ms=5.0,
                        verification_cost_ms=8.0,
                        execution_succeeded=True,
                        reuse_count=4,
                    )
                    reuse_counts[capsule_id] = 4
                    economics_receipts[capsule_id] = final
                elif role == "negative":
                    final = economics.record(
                        capsule_id=capsule_id,
                        preparation_debt_ms=preparation_costs[capsule_id],
                        avoided_recompile_ms=8.0,
                        residency_cost_ms=12.0,
                        verification_cost_ms=6.0,
                        execution_succeeded=True,
                        reuse_count=1,
                    )
                    reuse_counts[capsule_id] = 1
                    economics_receipts[capsule_id] = final
                else:
                    final = economics.record(
                        capsule_id=capsule_id,
                        preparation_debt_ms=preparation_costs[capsule_id],
                        avoided_recompile_ms=5.0,
                        residency_cost_ms=8.0,
                        verification_cost_ms=5.0,
                        execution_succeeded=True,
                        reuse_count=1,
                    )
                    reuse_counts[capsule_id] = 1
                    economics_receipts[capsule_id] = final
                self.event_sink({
                    "event_type": "grand_closure.g7.economics_measured",
                    "capsule_id": capsule_id,
                    "role": role,
                    "break_even": economics_receipts[capsule_id].break_even,
                    "credit_eligible": economics_receipts[capsule_id].credit_eligible,
                    "raw_payload_retained": False,
                })

            # Low and rising produce policy evidence without eviction.
            low = lifecycle.apply("low")
            rising = lifecycle.apply("rising")

            # Protect the profitable capsule as active, bounded mission state.
            profitable_id = next(cid for cid, role in roles.items() if role == "profitable")
            pins.pin(
                artifact_id=profitable_id,
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                reason="profitable active residual",
                ttl_seconds=300,
                evidence_digest=_digest({"capsule_id": profitable_id, "net": economics_receipts[profitable_id].net_value_ms}),
            )

            high = lifecycle.apply("high")
            critical = lifecycle.apply("critical")
            remaining = {entry.capsule_id for entry in registry.entries()}

            results: list[G7CapsuleResult] = []
            for capsule_id, role in sorted(roles.items(), key=lambda item: item[1]):
                econ = economics_receipts[capsule_id]
                results.append(G7CapsuleResult(
                    capsule_id=capsule_id,
                    role=role,
                    reuse_count=reuse_counts[capsule_id],
                    preparation_debt_ms=econ.preparation_debt_ms,
                    avoided_recompile_ms=econ.avoided_recompile_ms,
                    residency_cost_ms=econ.residency_cost_ms,
                    verification_cost_ms=econ.verification_cost_ms,
                    net_value_ms=econ.net_value_ms,
                    break_even=econ.break_even,
                    credit_eligible=econ.credit_eligible,
                    retained_after_pressure=capsule_id in remaining,
                    proof_critical=capsule_id == critical_id,
                    economics_digest=econ.receipt_digest,
                ))

            profitable = next(r for r in results if r.role == "profitable")
            negative = next(r for r in results if r.role == "negative")
            proof = next(r for r in results if r.role == "proof-critical")
            body = {
                "status": "closed",
                "workspace_id": workspace_id,
                "privacy_domain": privacy_domain,
                "pressure_sequence": ["low", "rising", "high", "critical"],
                "profitable_capsule_retained": profitable.retained_after_pressure,
                "negative_capsule_evicted": not negative.retained_after_pressure,
                "proof_critical_capsule_retained": proof.retained_after_pressure,
                "preparation_debt_observed": all(r.preparation_debt_ms > 0 for r in results),
                "break_even_observed": profitable.break_even,
                "credit_before_break_even": False,
                "raw_payload_retained": False,
                "authority": "accounting_and_lifecycle_only",
                "capsules": [asdict(r) for r in results],
                "lifecycle_receipts": [asdict(low), asdict(rising), asdict(high), asdict(critical)],
                "event_count": len(self.events) + len(lifecycle_events),
            }
            invariants = (
                body["profitable_capsule_retained"],
                body["negative_capsule_evicted"],
                body["proof_critical_capsule_retained"],
                body["preparation_debt_observed"],
                body["break_even_observed"],
                not body["credit_before_break_even"],
                not body["raw_payload_retained"],
            )
            if not all(invariants):
                raise RuntimeError(f"G7 closure invariants failed: {body}")
            closure_digest = _digest(body)
            receipt = G7ClosureReceipt(
                status="closed",
                workspace_id=workspace_id,
                privacy_domain=privacy_domain,
                pressure_sequence=("low", "rising", "high", "critical"),
                profitable_capsule_retained=True,
                negative_capsule_evicted=True,
                proof_critical_capsule_retained=True,
                preparation_debt_observed=True,
                break_even_observed=True,
                credit_before_break_even=False,
                raw_payload_retained=False,
                authority="accounting_and_lifecycle_only",
                capsules=tuple(results),
                lifecycle_receipts=tuple(body["lifecycle_receipts"]),
                event_count=body["event_count"],
                closure_digest=closure_digest,
            )
            if self.evidence_dir:
                self.evidence_dir.mkdir(parents=True, exist_ok=True)
                out = self.evidence_dir / f"grand-closure-g7-{int(time.time())}.json"
                payload = asdict(receipt)
                tmp = out.with_suffix(".tmp")
                tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
                tmp.replace(out)
            return receipt
        finally:
            registry.close_all()
            for handle in handles:
                handle.close()
