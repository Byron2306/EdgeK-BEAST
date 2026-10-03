"""Minimal DAI capability ledger for deterministic arena composition.

The ledger is deliberately small and immutable-by-value.  It records promoted
capability families as digest-bound crystals, then later arenas can prove they
are composing stored capabilities rather than rediscovering them from an answer
cache or provider call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json
from typing import Any, Mapping

from app.kernel.compute.deterministic_intelligence import canonical_json, require_digest, sha256_digest


LEDGER_VERSION = "2026-08-04.phase6.2.capability-ledger.v1"


@dataclass(frozen=True, slots=True)
class CapabilityCrystal:
    crystal_id: str
    family: str
    source_phase: str
    capability_digest: str
    receipt_digest: str
    predicate_ids: tuple[str, ...]
    authority: str = "test_only_composition"
    provider_calls_after_promotion: int = 0
    production_authority_allowed: bool = False
    execution_authority_allowed: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.crystal_id.strip() or not self.family.strip() or not self.source_phase.strip():
            raise ValueError("capability crystal requires id, family and source phase")
        require_digest(self.capability_digest, field_name="capability_digest")
        require_digest(self.receipt_digest, field_name="receipt_digest")
        if not self.predicate_ids:
            raise ValueError("capability crystal requires at least one predicate id")
        if self.provider_calls_after_promotion != 0:
            raise ValueError("DAI deterministic crystals must be zero-provider after promotion")
        if self.production_authority_allowed or self.execution_authority_allowed:
            raise ValueError("DAI deterministic crystals cannot grant production or execution authority")
        canonical_json(self.metadata)

    @property
    def crystal_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class CapabilityLedger:
    beast_object_type: str
    version: str
    ledger_id: str
    crystals: tuple[CapabilityCrystal, ...]
    provider_calls_used: int = 0
    production_authority_allowed: bool = False
    execution_authority_allowed: bool = False

    def __post_init__(self) -> None:
        if self.beast_object_type != "dai_capability_ledger":
            raise ValueError("unexpected capability ledger object type")
        if self.version != LEDGER_VERSION:
            raise ValueError("unexpected capability ledger version")
        ids = [crystal.crystal_id for crystal in self.crystals]
        if len(ids) != len(set(ids)):
            raise ValueError("capability crystal ids must be unique")
        if self.provider_calls_used != 0 or self.production_authority_allowed or self.execution_authority_allowed:
            raise ValueError("capability ledger cannot grant provider, production or execution authority")

    @property
    def ledger_digest(self) -> str:
        return sha256_digest(self)

    def has_family(self, family: str) -> bool:
        return any(crystal.family == family for crystal in self.crystals)

    def require_families(self, families: tuple[str, ...]) -> bool:
        return all(self.has_family(family) for family in families)

    def crystal_digest_for_family(self, family: str) -> str:
        for crystal in self.crystals:
            if crystal.family == family:
                return crystal.crystal_digest
        return ""


def build_phase6_capability_ledger(
    *,
    restart_arena_receipt: Mapping[str, Any],
    sophia_transfer_receipt: Mapping[str, Any],
    ledger_id: str = "phase6.2:capability-ledger:restart-risk+sophia-source-support",
) -> CapabilityLedger:
    restart_receipt_digest = str(restart_arena_receipt.get("receipt_digest") or "")
    sophia_receipt_digest = str(sophia_transfer_receipt.get("receipt_digest") or "")
    require_digest(restart_receipt_digest, field_name="restart_arena_receipt.receipt_digest")
    require_digest(sophia_receipt_digest, field_name="sophia_transfer_receipt.receipt_digest")
    if restart_arena_receipt.get("green") is not True:
        raise ValueError("restart arena receipt is not green")
    if sophia_transfer_receipt.get("green") is not True:
        raise ValueError("Sophia transfer receipt is not green")
    if _int_field(restart_arena_receipt, "provider_calls_after_promotion") != 0:
        raise ValueError("restart arena did not prove zero-provider reuse")
    if _int_field(sophia_transfer_receipt, "provider_calls_after_promotion") != 0:
        raise ValueError("Sophia transfer arena did not prove zero-provider reuse")

    restart_digest = str(restart_arena_receipt.get("case_receipts", [{}])[0].get("capability_family_digest") or "")
    if not restart_digest:
        restart_digest = sha256_digest({
            "phase": "6",
            "receipt_digest": restart_receipt_digest,
            "family": "restart_risk_composition",
        })
    sophia_digest = str(sophia_transfer_receipt.get("capability_family_digest") or "")
    require_digest(restart_digest, field_name="restart_capability_digest")
    require_digest(sophia_digest, field_name="sophia_capability_digest")

    return CapabilityLedger(
        beast_object_type="dai_capability_ledger",
        version=LEDGER_VERSION,
        ledger_id=ledger_id,
        crystals=(
            CapabilityCrystal(
                crystal_id="crystal:phase6:restart-risk-composition",
                family="restart_risk_composition",
                source_phase="phase6.0",
                capability_digest=restart_digest,
                receipt_digest=restart_receipt_digest,
                predicate_ids=(
                    "healthy",
                    "depends_path_to",
                    "restart_policy_ordered",
                    "current_evidence_bound",
                    "restart_could_destabilize_target",
                ),
                metadata={"arena_case_count": restart_arena_receipt.get("case_count")},
            ),
            CapabilityCrystal(
                crystal_id="crystal:phase6.1:sophia-source-support",
                family="sophia_source_support",
                source_phase="phase6.1",
                capability_digest=sophia_digest,
                receipt_digest=sophia_receipt_digest,
                predicate_ids=("visible_source_span_bound", "source_supports_claim", "source_contradicts_claim", "citation_needed"),
                metadata={"sophia_export_digest": sophia_transfer_receipt.get("sophia_export_digest")},
            ),
        ),
    )


def write_capability_ledger(path: str | Path, ledger: CapabilityLedger) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(canonical_json(ledger))
    payload["ledger_digest"] = ledger.ledger_digest
    target.write_text(canonical_json(payload) + "\n", encoding="utf-8")


def _int_field(payload: Mapping[str, Any], field_name: str) -> int:
    if field_name not in payload:
        return -1
    try:
        return int(payload[field_name])
    except (TypeError, ValueError):
        return -1
