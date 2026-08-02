from __future__ import annotations

from dataclasses import dataclass

from .amortization_ledger import AmortizationAccount, AmortizationLedger
from .forge_credit_bridge import ForgeCreditBridge, ForgeCreditReceipt
from .residual_contracts import sha256_digest
from .residual_economics import EconomicsDelta, ResidualCostObservation


@dataclass(frozen=True, slots=True)
class EconomicsClosureReceipt:
    account: AmortizationAccount
    delta: EconomicsDelta
    credits: tuple[ForgeCreditReceipt, ...]
    retain_recommended: bool
    receipt_digest: str


class PRISMR6EconomicsPlane:
    def __init__(self, ledger: AmortizationLedger, credit_bridge: ForgeCreditBridge | None = None) -> None:
        self.ledger = ledger
        self.credit_bridge = credit_bridge or ForgeCreditBridge()

    def close_observation(self, obs: ResidualCostObservation) -> EconomicsClosureReceipt:
        account, delta = self.ledger.record(obs)
        credits = self.credit_bridge.issue_for(obs, delta, account)
        retain = self.ledger.should_retain(account)
        digest = sha256_digest({"account": account, "delta": delta, "credits": credits, "retain": retain})
        return EconomicsClosureReceipt(account, delta, credits, retain, digest)
