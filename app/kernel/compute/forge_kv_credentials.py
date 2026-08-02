"""Call-scoped credential broker for online Forge publication."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

@dataclass(frozen=True)
class CredentialLease:
    provider: str
    audience: str
    token: str
    expires_at: float

class CredentialBroker:
    def __init__(self, resolver: Callable[[str,str], CredentialLease]): self._resolver=resolver
    @contextmanager
    def lease(self, provider: str, audience: str, *, now: float) -> Iterator[CredentialLease]:
        item=self._resolver(provider,audience)
        if item.provider!=provider or item.audience!=audience or not item.token: raise PermissionError("credential lease binding mismatch")
        if now>=item.expires_at: raise PermissionError("credential lease expired")
        try: yield item
        finally: item=None
