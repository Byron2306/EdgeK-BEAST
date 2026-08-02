from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ResidualRoute(str, Enum):
    SEMANTIC_RESULT = "semantic_result"
    PROMOTED_CRYSTAL = "promoted_crystal"
    NATIVE_CONTEXT = "native_context"
    PREFIX_REPLAY = "prefix_replay"
    WARM_MODEL = "warm_model"
    FRESH_OLLAMA = "fresh_ollama"
    FRESH_LLAMA_CPP = "fresh_llama_cpp"
    PROVIDER = "provider"


class ResidualAuthority(str, Enum):
    READ_VERIFIED = "read_verified"
    CONTEXT_ONLY = "context_only"
    INFERENCE_ONLY = "inference_only"
    PROVIDER_CALL = "provider_call"
    ONE_USE_EXECUTE = "one_use_execute"


class ApplicabilityState(str, Enum):
    APPLICABLE = "applicable"
    INAPPLICABLE = "inapplicable"
    UNKNOWN = "unknown"


class VerificationState(str, Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    STALE = "stale"
    REVOKED = "revoked"


class DecisionPolicy(str, Enum):
    LOWEST_VERIFIED_EXPECTED_COST = "lowest_verified_expected_cost"
    STRICT_ROUTE_ORDER = "strict_route_order"
    OPERATOR_SELECTED = "operator_selected"
    GOVERNED_REFUSAL = "governed_refusal"


ROUTE_AUTHORITIES: dict[ResidualRoute, frozenset[ResidualAuthority]] = {
    ResidualRoute.SEMANTIC_RESULT: frozenset({ResidualAuthority.READ_VERIFIED}),
    ResidualRoute.PROMOTED_CRYSTAL: frozenset({ResidualAuthority.ONE_USE_EXECUTE}),
    ResidualRoute.NATIVE_CONTEXT: frozenset({ResidualAuthority.CONTEXT_ONLY}),
    ResidualRoute.PREFIX_REPLAY: frozenset({ResidualAuthority.CONTEXT_ONLY}),
    ResidualRoute.WARM_MODEL: frozenset({ResidualAuthority.CONTEXT_ONLY}),
    ResidualRoute.FRESH_OLLAMA: frozenset({ResidualAuthority.INFERENCE_ONLY}),
    ResidualRoute.FRESH_LLAMA_CPP: frozenset({ResidualAuthority.INFERENCE_ONLY}),
    ResidualRoute.PROVIDER: frozenset({ResidualAuthority.PROVIDER_CALL}),
}


ROUTE_ORDER: tuple[ResidualRoute, ...] = (
    ResidualRoute.SEMANTIC_RESULT,
    ResidualRoute.PROMOTED_CRYSTAL,
    ResidualRoute.NATIVE_CONTEXT,
    ResidualRoute.PREFIX_REPLAY,
    ResidualRoute.WARM_MODEL,
    ResidualRoute.FRESH_OLLAMA,
    ResidualRoute.FRESH_LLAMA_CPP,
    ResidualRoute.PROVIDER,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _canonicalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_canonicalize(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonicalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_digest(value: str, *, field_name: str = "digest") -> None:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{field_name} must be a sha256:<64 hex> digest")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise ValueError(f"{field_name} must contain hexadecimal characters") from exc


def validate_non_negative_number(value: float, *, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")


def validate_probability(value: float, *, field_name: str) -> None:
    validate_non_negative_number(value, field_name=field_name)
    if float(value) > 1:
        raise ValueError(f"{field_name} must be between 0 and 1")


def ensure_route_authority(route: ResidualRoute, authority: ResidualAuthority) -> None:
    allowed = ROUTE_AUTHORITIES[route]
    if authority not in allowed:
        names = ", ".join(sorted(item.value for item in allowed))
        raise PermissionError(f"route {route.value} cannot carry authority {authority.value}; allowed: {names}")
