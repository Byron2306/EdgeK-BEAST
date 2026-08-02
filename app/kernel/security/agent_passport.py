"""BEAST Agent Passport identity and policy primitives.

The passport layer provides SPIFFE-shaped local workload identity, deterministic
policy decisions, and optional residue-sealed audit records. It is designed to
be backed by mTLS/SPIRE later without changing the calling contract.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.security.residue_seal import ResidueSeal
from app.kernel.policy.policy_gate import from_agent_passport_decision


BEAST_TRUST_DOMAIN = "beast.local"
PASSPORT_VERSION = "2.0"
PASSPORT_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,126}$")


DEFAULT_POLICIES = [
    {
        "id": "memory-hull-scout-read-append",
        "effect": "allow",
        "caller": "spiffe://beast.local/scout/repo-reader",
        "target": "spiffe://beast.local/memory/vault",
        "actions": ["read", "append"],
    },
    {
        "id": "memory-hull-runtime-governor-append",
        "effect": "allow",
        "caller": "spiffe://beast.local/runtime-governor",
        "target": "spiffe://beast.local/memory/vault",
        "actions": ["read", "append", "seal"],
    },
    {
        "id": "proxy-provider-local-first",
        "effect": "allow",
        "caller": "spiffe://beast.local/proxy/gateway",
        "target": "spiffe://beast.local/provider/*",
        "actions": ["call"],
    },
    {
        "id": "proxy-local-compute-cascade",
        "effect": "allow",
        "caller": "spiffe://beast.local/proxy/gateway",
        "target": "spiffe://beast.local/compute/cascade",
        "actions": ["run"],
    },
    {
        "id": "runtime-governor-cloud-escalation",
        "effect": "allow",
        "caller": "spiffe://beast.local/runtime-governor",
        "target": "spiffe://beast.local/provider/cloud",
        "actions": ["approve_escalation", "call"],
        "requires": {"quality_cascade.approved": True},
    },
    {
        "id": "deny-unapproved-cloud-calls",
        "effect": "deny",
        "caller": "*",
        "target": "spiffe://beast.local/provider/cloud",
        "actions": ["call"],
        "unless": {"quality_cascade.approved": True},
    },
]


@dataclass(frozen=True)
class AgentPassport:
    component: str
    spiffe_id: str
    public_key_hash: str = ""
    cert_fingerprint: str = ""
    issuer: str = "beast.local/bootstrap"
    issued_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat())
    audiences: tuple[str, ...] = ("beast",)
    claims: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def local(
        cls,
        component: str,
        *,
        issuer: str = "beast.local/bootstrap",
        ttl_seconds: int = 12 * 60 * 60,
        audiences: Optional[Iterable[str]] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> "AgentPassport":
        normalized = normalize_component(component)
        spiffe_id = f"spiffe://{BEAST_TRUST_DOMAIN}/{normalized}"
        digest = "sha256:" + hashlib.sha256(spiffe_id.encode("utf-8")).hexdigest()
        issued = datetime.now(timezone.utc)
        expires = issued + timedelta(seconds=max(60, int(ttl_seconds)))
        return cls(
            component=normalized,
            spiffe_id=spiffe_id,
            public_key_hash=digest,
            issuer=issuer,
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
            audiences=tuple(audiences or ("beast",)),
            claims=dict(claims or {}),
        )

    @classmethod
    def from_workload_certificate(
        cls,
        component: str,
        cert_pem: str,
        *,
        issuer: str = "beast.local/workload-cert",
        ttl_seconds: int = 12 * 60 * 60,
        audiences: Optional[Iterable[str]] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> "AgentPassport":
        """Bind a local passport to supplied mTLS/SPIRE certificate material."""
        if "BEGIN CERTIFICATE" not in str(cert_pem or ""):
            raise ValueError("workload certificate must be PEM certificate material")
        normalized = normalize_component(component)
        spiffe_id = f"spiffe://{BEAST_TRUST_DOMAIN}/{normalized}"
        cert_fingerprint = "sha256:" + hashlib.sha256(cert_pem.encode("utf-8")).hexdigest()
        issued = datetime.now(timezone.utc)
        expires = issued + timedelta(seconds=max(60, int(ttl_seconds)))
        bound_claims = dict(claims or {})
        bound_claims["workload_identity"] = {
            "binding": "certificate_fingerprint",
            "cert_fingerprint": cert_fingerprint,
            "mtls_or_spire_ready": True,
        }
        return cls(
            component=normalized,
            spiffe_id=spiffe_id,
            public_key_hash=cert_fingerprint,
            cert_fingerprint=cert_fingerprint,
            issuer=issuer,
            issued_at=issued.isoformat(),
            expires_at=expires.isoformat(),
            audiences=tuple(audiences or ("beast",)),
            claims=bound_claims,
        )

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AgentPassport":
        if payload.get("beast_object_type") != "beast_agent_passport":
            raise ValueError("not a BEAST agent passport")
        component = normalize_component(str(payload.get("component") or ""))
        spiffe_id = normalize_spiffe_id(str(payload.get("spiffe_id") or f"spiffe://{BEAST_TRUST_DOMAIN}/{component}"))
        audiences = payload.get("audiences") if isinstance(payload.get("audiences"), list) else ["beast"]
        claims = payload.get("claims") if isinstance(payload.get("claims"), dict) else {}
        return cls(
            component=component,
            spiffe_id=spiffe_id,
            public_key_hash=str(payload.get("public_key_hash") or ""),
            cert_fingerprint=str(payload.get("cert_fingerprint") or ""),
            issuer=str(payload.get("issuer") or "unknown"),
            issued_at=str(payload.get("issued_at") or ""),
            expires_at=str(payload.get("expires_at") or ""),
            audiences=tuple(str(item) for item in audiences),
            claims=claims,
        )

    @property
    def expired(self) -> bool:
        try:
            return datetime.fromisoformat(self.expires_at) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "beast_agent_passport",
            "version": PASSPORT_VERSION,
            "component": self.component,
            "spiffe_id": self.spiffe_id,
            "public_key_hash": self.public_key_hash,
            "cert_fingerprint": self.cert_fingerprint,
            "issuer": self.issuer,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "audiences": list(self.audiences),
            "claims": self.claims,
            "identity_boundary": "local_passport_claim_ready_for_mtls_or_spire_binding",
        }


class AgentPassportPolicy:
    def __init__(
        self,
        policies: Optional[List[Dict[str, Any]]] = None,
        *,
        seal: Optional[ResidueSeal] = None,
        sign_decisions: bool = False,
    ):
        self.policies = [dict(policy) for policy in (policies or DEFAULT_POLICIES)]
        self.seal = seal
        self.sign_decisions = sign_decisions
        self._validate_policies()

    def evaluate(
        self,
        *,
        caller: AgentPassport | Dict[str, Any] | str,
        target: str,
        action: str,
        facts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        passport = self._coerce_passport(caller)
        caller_id = passport.spiffe_id if passport is not None else normalize_spiffe_id(str(caller))
        normalized_target = normalize_spiffe_id(target)
        normalized_action = normalize_action(action)
        facts = facts or {}

        if passport is not None and passport.expired:
            return self._seal_decision(
                self._decision(False, caller_id, normalized_target, normalized_action, "passport_expired", [], facts)
            )

        matched = []
        deny_matches = []
        allow_matches = []
        for policy in self.policies:
            if not self._matches(policy, caller_id, normalized_target, normalized_action):
                continue
            matched.append(policy)
            if policy.get("effect") == "deny":
                deny_matches.append(policy)
            elif policy.get("effect") == "allow":
                allow_matches.append(policy)

        for policy in deny_matches:
            if self._unless_not_met(policy, facts):
                return self._seal_decision(
                    self._decision(False, caller_id, normalized_target, normalized_action, "explicit_deny", matched, facts)
                )
        for policy in allow_matches:
            if self._requirements_met(policy, facts):
                return self._seal_decision(
                    self._decision(True, caller_id, normalized_target, normalized_action, "explicit_allow", matched, facts)
                )
        return self._seal_decision(
            self._decision(False, caller_id, normalized_target, normalized_action, "default_deny", matched, facts)
        )

    def authorize(self, *, caller: AgentPassport | Dict[str, Any] | str, target: str, action: str, facts: Optional[Dict[str, Any]] = None) -> None:
        decision = self.evaluate(caller=caller, target=target, action=action, facts=facts)
        if not decision.get("allowed"):
            raise PermissionError(f"BEAST passport denied {action} from {decision['caller']} to {decision['target']}: {decision['reason']}")

    def lint(self) -> Dict[str, Any]:
        errors = []
        for index, policy in enumerate(self.policies):
            try:
                self._validate_policy(policy)
            except ValueError as exc:
                errors.append({"index": index, "error": str(exc), "policy": policy})
        return {
            "beast_object_type": "beast_agent_passport_policy_lint",
            "version": "1.0",
            "valid": not errors,
            "policy_count": len(self.policies),
            "errors": errors,
            "policy_hash": self._policy_hash(self.policies),
        }

    @staticmethod
    def _coerce_passport(caller: AgentPassport | Dict[str, Any] | str) -> Optional[AgentPassport]:
        if isinstance(caller, AgentPassport):
            return caller
        if isinstance(caller, dict):
            return AgentPassport.from_dict(caller)
        return None

    @staticmethod
    def _matches(policy: Dict[str, Any], caller: str, target: str, action: str) -> bool:
        return (
            fnmatch.fnmatch(caller, str(policy.get("caller") or ""))
            and fnmatch.fnmatch(target, str(policy.get("target") or ""))
            and any(fnmatch.fnmatch(action, normalize_action(str(item), allow_wildcard=True)) for item in (policy.get("actions") or []))
        )

    def _requirements_met(self, policy: Dict[str, Any], facts: Dict[str, Any]) -> bool:
        required = policy.get("requires") if isinstance(policy.get("requires"), dict) else {}
        return all(self._fact(facts, key) == value for key, value in required.items())

    def _unless_not_met(self, policy: Dict[str, Any], facts: Dict[str, Any]) -> bool:
        unless = policy.get("unless") if isinstance(policy.get("unless"), dict) else {}
        if not unless:
            return True
        return not all(self._fact(facts, key) == value for key, value in unless.items())

    @staticmethod
    def _fact(facts: Dict[str, Any], dotted: str) -> Any:
        node: Any = facts
        for part in dotted.split("."):
            if not isinstance(node, dict):
                return None
            node = node.get(part)
        return node

    def _decision(
        self,
        allowed: bool,
        caller: str,
        target: str,
        action: str,
        reason: str,
        matched: List[Dict[str, Any]],
        facts: Dict[str, Any],
    ) -> Dict[str, Any]:
        matched_ids = [str(policy.get("id") or "") for policy in matched]
        decision = {
            "beast_object_type": "beast_agent_passport_policy_decision",
            "version": PASSPORT_VERSION,
            "allowed": allowed,
            "caller": caller,
            "target": target,
            "action": action,
            "reason": reason,
            "matched_policy_count": len(matched),
            "matched_policy_ids": matched_ids,
            "policy_hash": self._policy_hash(matched),
            "policy_set_hash": self._policy_hash(self.policies),
            "facts_hash": "sha256:" + hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        decision["decision_id"] = "passport_decision_" + hashlib.sha256(
            json.dumps(decision, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
        return decision

    def _seal_decision(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        decision = dict(decision)
        decision["policy_gate"] = from_agent_passport_decision(decision)
        if self.sign_decisions and self.seal is not None:
            decision["residue_seal"] = self.seal.sign(decision, purpose="agent_passport_policy_decision")
        return decision

    def _validate_policies(self) -> None:
        lint = self.lint()
        if not lint["valid"]:
            raise ValueError(f"invalid BEAST passport policy set: {lint['errors']}")

    @staticmethod
    def _validate_policy(policy: Dict[str, Any]) -> None:
        if policy.get("effect") not in {"allow", "deny"}:
            raise ValueError("policy effect must be allow or deny")
        if not policy.get("id"):
            raise ValueError("policy id is required")
        normalize_spiffe_id(str(policy.get("caller") or "*"), allow_wildcard=True)
        normalize_spiffe_id(str(policy.get("target") or "*"), allow_wildcard=True)
        actions = policy.get("actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError("policy actions must be a non-empty list")

    @staticmethod
    def _policy_hash(policies: List[Dict[str, Any]]) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(policies, sort_keys=True).encode("utf-8")).hexdigest()


def normalize_component(component: str) -> str:
    normalized = str(component or "").strip().strip("/").lower()
    normalized = re.sub(r"/+", "/", normalized)
    if not PASSPORT_COMPONENT_RE.match(normalized) or ".." in normalized:
        raise ValueError(f"invalid BEAST passport component: {component!r}")
    return normalized


def normalize_spiffe_id(value: str, *, allow_wildcard: bool = False) -> str:
    text = str(value or "").strip()
    if allow_wildcard and text == "*":
        return text
    if allow_wildcard and "*" in text:
        if not text.startswith(f"spiffe://{BEAST_TRUST_DOMAIN}/"):
            raise ValueError(f"wildcard policy must stay inside {BEAST_TRUST_DOMAIN}: {value!r}")
        return text
    prefix = f"spiffe://{BEAST_TRUST_DOMAIN}/"
    if not text.startswith(prefix):
        raise ValueError(f"BEAST SPIFFE id must start with {prefix}: {value!r}")
    return f"{prefix}{normalize_component(text[len(prefix):])}"


def normalize_action(action: str, *, allow_wildcard: bool = False) -> str:
    normalized = str(action or "").strip().lower()
    if allow_wildcard and normalized == "*":
        return normalized
    if not re.match(r"^[a-z][a-z0-9_:-]{0,63}$", normalized):
        raise ValueError(f"invalid BEAST passport action: {action!r}")
    return normalized
