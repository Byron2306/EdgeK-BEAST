from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .residual_contracts import canonical_json, sha256_digest, utc_now_iso
from .residual_economics import EconomicsDelta, ResidualCostObservation, ResidualEconomics


@dataclass(frozen=True, slots=True)
class AmortizationAccount:
    artifact_id: str
    workspace_id: str
    privacy_domain: str
    preparation_debt: float = 0.0
    gross_avoided_value: float = 0.0
    incurred_cost: float = 0.0
    net_value: float = 0.0
    realized_positive_value: float = 0.0
    successful_reuses: int = 0
    failed_reuses: int = 0
    prompt_tokens_avoided: int = 0
    provider_calls_avoided: int = 0
    observations: int = 0
    updated_at: str = ""
    account_digest: str = ""

    @property
    def break_even(self) -> bool:
        return self.net_value >= 0 and self.successful_reuses > 0


class AmortizationLedger:
    def __init__(self, path: str | Path | None = None, economics: ResidualEconomics | None = None) -> None:
        self.path = Path(path) if path else None
        self.economics = economics or ResidualEconomics()
        self._lock = threading.RLock()
        self._accounts: dict[str, AmortizationAccount] = {}
        self._seen: set[str] = set()
        if self.path and self.path.exists():
            self._load()

    def _key(self, artifact_id: str, workspace_id: str, privacy_domain: str) -> str:
        return sha256_digest({"artifact_id": artifact_id, "workspace_id": workspace_id, "privacy_domain": privacy_domain})

    def record(self, obs: ResidualCostObservation) -> tuple[AmortizationAccount, EconomicsDelta]:
        delta = self.economics.evaluate(obs)
        with self._lock:
            if obs.digest in self._seen:
                key = self._key(obs.artifact_id, obs.workspace_id, obs.privacy_domain)
                return self._accounts[key], delta
            key = self._key(obs.artifact_id, obs.workspace_id, obs.privacy_domain)
            old = self._accounts.get(key, AmortizationAccount(obs.artifact_id, obs.workspace_id, obs.privacy_domain))
            raw = {
                "artifact_id": old.artifact_id,
                "workspace_id": old.workspace_id,
                "privacy_domain": old.privacy_domain,
                "preparation_debt": old.preparation_debt + delta.preparation_debt_added,
                "gross_avoided_value": old.gross_avoided_value + delta.gross_avoided_value,
                "incurred_cost": old.incurred_cost + delta.incurred_cost,
                "net_value": old.net_value + delta.net_value,
                "realized_positive_value": max(0.0, old.net_value + delta.net_value),
                "successful_reuses": old.successful_reuses + int(obs.successful_reuse),
                "failed_reuses": old.failed_reuses + int(obs.failed_reuse),
                "prompt_tokens_avoided": old.prompt_tokens_avoided + obs.prompt_tokens_avoided,
                "provider_calls_avoided": old.provider_calls_avoided + obs.provider_calls_avoided,
                "observations": old.observations + 1,
                "updated_at": utc_now_iso(),
            }
            account = AmortizationAccount(**raw, account_digest=sha256_digest(raw))
            self._accounts[key] = account
            self._seen.add(obs.digest)
            self._persist()
            return account, delta

    def get(self, artifact_id: str, workspace_id: str, privacy_domain: str) -> AmortizationAccount | None:
        with self._lock:
            return self._accounts.get(self._key(artifact_id, workspace_id, privacy_domain))

    def should_retain(self, account: AmortizationAccount, *, minimum_expected_reuses: int = 1) -> bool:
        if account.break_even:
            return True
        return account.successful_reuses + minimum_expected_reuses > account.failed_reuses and account.net_value > -max(0.1, account.preparation_debt)

    def _persist(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = {"accounts": [asdict(x) for x in self._accounts.values()], "seen": sorted(self._seen)}
        body["ledger_digest"] = sha256_digest(body)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(canonical_json(body), encoding="utf-8")
        os.replace(tmp, self.path)

    def _load(self) -> None:
        body = json.loads(self.path.read_text(encoding="utf-8"))
        supplied = body.pop("ledger_digest", None)
        if supplied != sha256_digest(body):
            raise ValueError("amortization ledger digest mismatch")
        for raw in body.get("accounts", []):
            account = AmortizationAccount(**raw)
            self._accounts[self._key(account.artifact_id, account.workspace_id, account.privacy_domain)] = account
        self._seen = set(body.get("seen", []))
