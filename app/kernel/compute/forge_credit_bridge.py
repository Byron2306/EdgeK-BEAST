from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .amortization_ledger import AmortizationAccount
from .residual_contracts import ResidualRoute, sha256_digest, utc_now_iso
from .residual_economics import EconomicsDelta, ResidualCostObservation


class ForgeCreditClass(str, Enum):
    PREPARED_COMPUTE = "prepared_compute_credit"
    REALIZED_REUSE = "realized_reuse_credit"
    VERIFIED_DISPLACEMENT = "verified_displacement_credit"
    PROVIDER_AVOIDANCE = "provider_avoidance_credit"
    COMMONS_CONTRIBUTION = "commons_contribution_credit"


class CreditSink(Protocol):
    def issue(self, receipt: "ForgeCreditReceipt") -> None: ...


@dataclass(frozen=True, slots=True)
class ForgeCreditReceipt:
    artifact_id: str
    credit_class: ForgeCreditClass
    amount: float
    route: ResidualRoute
    workspace_id: str
    privacy_domain: str
    account_digest: str
    observation_digest: str
    authority: str
    issued_at: str
    receipt_digest: str


class ForgeCreditBridge:
    def __init__(self, sink: CreditSink | None = None) -> None:
        self.sink = sink

    def issue_for(self, obs: ResidualCostObservation, delta: EconomicsDelta,
                  account: AmortizationAccount) -> tuple[ForgeCreditReceipt, ...]:
        # Preparation is accounted, never credited merely for existing.
        if not account.break_even or delta.net_value <= 0 or not obs.successful_reuse:
            return ()
        grants: list[tuple[ForgeCreditClass, float]] = [
            (ForgeCreditClass.REALIZED_REUSE, delta.net_value),
        ]
        if obs.avoided_fresh_compute_ms > 0:
            grants.append((ForgeCreditClass.VERIFIED_DISPLACEMENT, delta.components["avoided_compute"]))
        if obs.avoided_provider_cost > 0 or obs.provider_calls_avoided > 0:
            grants.append((ForgeCreditClass.PROVIDER_AVOIDANCE, max(obs.avoided_provider_cost, 1e-9)))
        receipts = []
        for credit_class, amount in grants:
            core = {
                "artifact_id": obs.artifact_id, "credit_class": credit_class, "amount": amount,
                "route": obs.route, "workspace_id": obs.workspace_id, "privacy_domain": obs.privacy_domain,
                "account_digest": account.account_digest, "observation_digest": obs.digest,
                "authority": "accounting_only", "issued_at": utc_now_iso(),
            }
            receipt = ForgeCreditReceipt(receipt_digest=sha256_digest(core), **core)  # type: ignore[arg-type]
            receipts.append(receipt)
            if self.sink is not None:
                self.sink.issue(receipt)
        return tuple(receipts)
