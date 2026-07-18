"""Fail-closed BEAST -> ARDA -> Metatron authorization boundary."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
import os
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from app.kernel.integration.signed_decision import verify_appraisal, verify_decision
from urllib.request import Request, urlopen
import json

from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.integration.request_binding import crystal_request


@dataclass(frozen=True)
class CrossSystemReceipt:
    crystal_id: str
    arda_allowed: bool
    metatron_allowed: bool
    executed: bool
    evidence_node_id: str


class ArdaMetatronBridge:
    def __init__(self, *, arda_authorize: Callable[[Mapping[str, Any]], Any], metatron_authorize: Callable[[Mapping[str, Any]], Any], evidence: ControlEvidenceGraph | None = None, capability_ledger: OneUseCapabilityLedger | None = None, arda_authority: str = "arda", metatron_authority: str = "metatron"):
        self.arda_authorize = arda_authorize
        self.metatron_authorize = metatron_authorize
        self.evidence = evidence or ControlEvidenceGraph()
        self.capability_ledger = capability_ledger
        self.arda_authority, self.metatron_authority = arda_authority, metatron_authority

    def _authorize(self, callback, request, *, authority: str) -> bool:
        result = callback(request)
        if self.capability_ledger is None:
            return result is True or (isinstance(result, Mapping) and result.get("allowed") is True)
        if not isinstance(result, Mapping) or result.get("allowed") is not True:
            return False
        capability = result.get("capability") or result
        try:
            self.capability_ledger.consume(capability, request_digest=str(request["request_digest"]), authority=authority)
            return True
        except (KeyError, TypeError, ValueError, PermissionError):
            return False

    def authorize_and_execute(self, plan: Any, *, execute: Callable[[], Mapping[str, Any]]) -> CrossSystemReceipt:
        request = crystal_request(plan)
        arda = self._authorize(self.arda_authorize, request, authority=self.arda_authority)
        metatron = self._authorize(self.metatron_authorize, request, authority=self.metatron_authority) if arda else False
        did_execute = arda and metatron
        effect = dict(execute()) if did_execute else {"status": "vetoed", "arda_allowed": arda, "metatron_allowed": metatron}
        node = self.evidence.add("cross_system_execution", {"request": request, "arda_allowed": arda, "metatron_allowed": metatron, "executed": did_execute, "effect": effect})
        return CrossSystemReceipt(plan.crystal_id, arda, metatron, did_execute, node.node_id)


class JsonHttpAuthorizer:
    """Small fail-closed transport adapter for ARDA/Metatron decisions."""
    def __init__(self, endpoint: str, *, timeout: float = 3.0, headers: Mapping[str, str] | None = None):
        self.endpoint, self.timeout, self.headers = endpoint, timeout, dict(headers or {})

    def __call__(self, request: Mapping[str, Any]) -> bool:
        try:
            body = json.dumps(dict(request), sort_keys=True).encode()
            wire = Request(self.endpoint, data=body, headers={**self.headers, "Content-Type": "application/json"}, method="POST")
            with urlopen(wire, timeout=self.timeout) as response:
                if response.status != 200:
                    return False
                value = json.loads(response.read())
                return value.get("allowed") is True
        except Exception:
            return False


class SignedJsonHttpAuthorizer(JsonHttpAuthorizer):
    def __init__(self, endpoint: str, public_key_path: str, *, authority: str,
                 expected_audience: str, expected_policy_generation: str,
                 expected_appraisal_ref: str, timeout: float = 3.0,
                 headers: Mapping[str, str] | None = None):
        super().__init__(endpoint, timeout=timeout, headers=headers)
        self.authority = authority
        self.public_key = serialization.load_pem_public_key(Path(public_key_path).read_bytes())
        self.expected_audience = expected_audience
        self.expected_policy_generation = expected_policy_generation
        self.expected_appraisal_ref = expected_appraisal_ref

    def authorize(self, request: Mapping[str, Any]) -> Mapping[str, Any] | bool:
        try:
            body = json.dumps(dict(request), sort_keys=True).encode()
            wire = Request(self.endpoint, data=body, headers={**self.headers, "Content-Type": "application/json"}, method="POST")
            with urlopen(wire, timeout=self.timeout) as response:
                value = json.loads(response.read())
            digest = str(request.get("request_digest", ""))
            decision = verify_decision(value, self.public_key, expected_authority=self.authority, expected_request_digest=digest)
            capability = value.get("capability")
            appraisal = value.get("appraisal")
            if not decision.allowed or not isinstance(capability, Mapping) or not isinstance(appraisal, Mapping):
                return False
            if decision.policy_generation != self.expected_policy_generation:
                return False
            if capability.get("audience") != self.expected_audience:
                return False
            if capability.get("policy_generation") != self.expected_policy_generation:
                return False
            if capability.get("appraisal_ref") != self.expected_appraisal_ref:
                return False
            verify_appraisal(
                appraisal,
                self.public_key,
                expected_authority=self.authority,
                expected_audience=self.expected_audience,
                expected_policy_generation=self.expected_policy_generation,
                expected_appraisal_ref=self.expected_appraisal_ref,
                expected_request_digest=digest,
            )
            return value
        except Exception:
            return False

    __call__ = authorize


def build_live_bridge(*, evidence: ControlEvidenceGraph | None = None) -> ArdaMetatronBridge:
    """Build a protected live bridge; unsigned Boolean decisions are forbidden."""
    names = (
        "BEAST_ARDA_AUTHORIZATION_URL", "BEAST_METATRON_AUTHORIZATION_URL",
        "BEAST_ARDA_PUBLIC_KEY", "BEAST_METATRON_PUBLIC_KEY",
        "BEAST_CAPABILITY_LEDGER_PATH", "BEAST_AUTHORIZATION_AUDIENCE",
        "BEAST_POLICY_GENERATION", "BEAST_ARDA_APPRAISAL_REF",
        "BEAST_METATRON_APPRAISAL_REF",
    )
    config = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in config.items() if not value]
    if missing:
        raise RuntimeError("authorization URLs/keys and protected configuration are incomplete: " + ", ".join(missing))
    arda_key = serialization.load_pem_public_key(Path(config["BEAST_ARDA_PUBLIC_KEY"]).read_bytes())
    metatron_key = serialization.load_pem_public_key(Path(config["BEAST_METATRON_PUBLIC_KEY"]).read_bytes())
    ledger = OneUseCapabilityLedger(
        verifier={"arda": arda_key, "metatron": metatron_key},
        path=config["BEAST_CAPABILITY_LEDGER_PATH"],
        require_verifier=True,
    )
    return ArdaMetatronBridge(
        arda_authorize=SignedJsonHttpAuthorizer(
            config["BEAST_ARDA_AUTHORIZATION_URL"], config["BEAST_ARDA_PUBLIC_KEY"],
            authority="arda", expected_audience=config["BEAST_AUTHORIZATION_AUDIENCE"],
            expected_policy_generation=config["BEAST_POLICY_GENERATION"],
            expected_appraisal_ref=config["BEAST_ARDA_APPRAISAL_REF"],
        ),
        metatron_authorize=SignedJsonHttpAuthorizer(
            config["BEAST_METATRON_AUTHORIZATION_URL"], config["BEAST_METATRON_PUBLIC_KEY"],
            authority="metatron", expected_audience=config["BEAST_AUTHORIZATION_AUDIENCE"],
            expected_policy_generation=config["BEAST_POLICY_GENERATION"],
            expected_appraisal_ref=config["BEAST_METATRON_APPRAISAL_REF"],
        ),
        evidence=evidence,
        capability_ledger=ledger,
    )
