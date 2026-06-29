"""Dependency container for the CPU-first BEAST compute pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.kernel.networking.protocols import AblationRunner, CreditStore, ForgeScheduler, KVTransport


@dataclass(frozen=True)
class BeastContext:
    storage: KVTransport
    scheduler: ForgeScheduler
    ablation_runner: AblationRunner
    credit_store: CreditStore

    def contract_status(self) -> Dict[str, bool]:
        return {
            "storage": isinstance(self.storage, KVTransport),
            "scheduler": isinstance(self.scheduler, ForgeScheduler),
            "ablation_runner": isinstance(self.ablation_runner, AblationRunner),
            "credit_store": isinstance(self.credit_store, CreditStore),
        }

    def validate(self) -> None:
        missing = [name for name, valid in self.contract_status().items() if not valid]
        if missing:
            raise TypeError("BEAST context dependencies violate protocols: " + ", ".join(missing))
