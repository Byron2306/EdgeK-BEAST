"""Crystal IR v1: zero-authority task interpretation for small local models.

Crystal IR is deliberately declarative.  It describes what the operator means
and what must be true afterward; it is not an executable patch and cannot grant
mutation, approval, network, or success authority to a model.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping


VERSION = "crystal.ir.v1"
_SAFE_RELATIVE = re.compile(r"^[^/\\][^:]*$")
_ALLOWED_TRANSFORMS = {
    "strip_whitespace",
    "lowercase",
    "replace_separator",
    "remove_alias",
    "add_import",
    "replace_exact",
    "replace_expression",
    "replace_function",
}

# Ollama receives this small, non-authoritative wire contract.  BEAST owns the
# executable Crystal IR fields and fills them after the candidate is accepted.
_INTENT_PROPERTIES: dict[str, Any] = {
        "s": {"type": "string", "enum": ["ok", "needs_clarification", "refuse"]},
        "f": {"type": "string", "enum": ["provider_normalization", "missing_import", "arithmetic_repair", "configuration_validation", "secret_redaction", "rollback", "unknown"]},
        "sym": {"type": "string", "maxLength": 160},
        "fc": {"type": "string", "enum": ["identifier_alias_mismatch", "missing_import", "arithmetic_invariant_failure", "configuration_contract_failure", "secret_exposure", "rollback_request", "unknown"]},
        "fx": {"type": "string", "enum": ["canonicalize", "add_import", "correct_arithmetic", "validate_configuration", "redact_secret", "rollback", "unknown"]},
        "c": {"type": "array", "items": {"type": "string", "enum": ["tests_immutable", "network_forbidden", "single_effect", "minimal_scope"]}, "uniqueItems": True},
        "ex": {"type": "array", "items": {"type": "array", "prefixItems": [{"type": "string"}, {"type": "string"}], "minItems": 2, "maxItems": 2}, "maxItems": 4},
        "u": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
        "r": {"type": "string", "enum": ["missing_postcondition", "unsafe_scope", "contradictory_constraints", "unknown_intent"]},
        "q": {"type": "string", "maxLength": 300},
        "e": {"type": "array", "items": {"type": "string"}, "maxItems": 4},
}

CRYSTAL_IR_TRANSLATOR_SCHEMA: dict[str, Any] = {
    "oneOf": [
        {"type": "object", "additionalProperties": False, "required": ["s", "f", "sym", "fc", "fx"], "properties": {**_INTENT_PROPERTIES, "s": {"const": "ok"}}},
        {"type": "object", "additionalProperties": False, "required": ["s", "r", "q"], "properties": {**_INTENT_PROPERTIES, "s": {"const": "needs_clarification"}}},
        {"type": "object", "additionalProperties": False, "required": ["s", "r"], "properties": {**_INTENT_PROPERTIES, "s": {"const": "refuse"}},},
    ],
}


class CrystalIRValidationError(ValueError):
    """Raised when an untrusted model packet is not a valid Crystal IR."""


@dataclass(frozen=True)
class IntentCandidate:
    """Small-model semantic output; it has no target or execution authority."""

    status: str
    intent_family: str = "unknown"
    target_symbol_hint: str = ""
    failure_class: str = "unknown"
    requested_effect: str = "unknown"
    constraints: tuple[str, ...] = ()
    examples: tuple[tuple[str, str], ...] = ()
    uncertainties: tuple[str, ...] = ()
    reason_code: str = ""
    question: str = ""
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "intent_family": self.intent_family, "target_symbol_hint": self.target_symbol_hint, "failure_class": self.failure_class, "requested_effect": self.requested_effect, "constraints": list(self.constraints), "examples": [list(item) for item in self.examples], "uncertainties": list(self.uncertainties), "reason_code": self.reason_code, "question": self.question, "evidence": list(self.evidence)}


def deterministic_intent(objective: str, context: str, *, target_symbol: str = "") -> IntentCandidate | None:
    """Resolve familiar BEAST vocabulary without spending a model call."""
    text = f"{objective} {context}".lower()
    rules = (
        (("provider", "identifier", "normal"), "provider_normalization", "identifier_alias_mismatch", "canonicalize"),
        (("missing", "import"), "missing_import", "missing_import", "add_import"),
        (("arithmetic", "correct"), "arithmetic_repair", "arithmetic_invariant_failure", "correct_arithmetic"),
        (("configuration", "valid"), "configuration_validation", "configuration_contract_failure", "validate_configuration"),
        (("secret", "redact"), "secret_redaction", "secret_exposure", "redact_secret"),
        (("rollback",), "rollback", "rollback_request", "rollback"),
    )
    for keywords, family, failure, effect in rules:
        if all(keyword in text for keyword in keywords):
            return IntentCandidate("interpreted", family, target_symbol, failure, effect, ("tests_immutable", "network_forbidden", "single_effect", "minimal_scope"))
    if any(phrase in text for phrase in ("don't touch tests", "do not touch tests", "keep it local", "only this function")):
        return None
    return None


def normalize_intent_text(value: str) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())


def deterministic_paraphrase_intent(objective: str, context: str, *, target_symbol: str = "") -> IntentCandidate | None:
    """Tier-2 activation matcher for verified recipe language surfaces."""
    text = normalize_intent_text(f"{objective} {context}")
    surfaces = (
        ((("provider", "identifier"), ("provider", "alias"), ("canonical",)), "provider_normalization", "identifier_alias_mismatch", "canonicalize"),
        ((("missing", "import"), ("unavailable", "dependency"), ("undefined", "decimal"), ("decimal", "not defined"), ("cannot", "resolve", "decimal")), "missing_import", "missing_import", "add_import"),
        ((("arithmetic", "correction"), ("numeric", "parser"), ("sum",), ("subtract",)), "arithmetic_repair", "arithmetic_invariant_failure", "correct_arithmetic"),
        ((("configuration", "validation"), ("config", "schema"), ("configuration", "contract")), "configuration_validation", "configuration_contract_failure", "validate_configuration"),
        ((("secret", "redaction"), ("mask", "secret"), ("hide", "credential"), ("replace", "token", "stars")), "secret_redaction", "secret_exposure", "redact_secret"),
        ((("rollback",), ("undo", "change"), ("restore", "previous", "state"), ("revert", "edit"), ("put", "back")), "rollback", "rollback_request", "rollback"),
    )
    for signals, family, failure, effect in surfaces:
        if any(all(term in text for term in signal) for signal in signals):
            return IntentCandidate("interpreted", family, target_symbol, failure, effect, ("tests_immutable", "network_forbidden", "single_effect", "minimal_scope"))
    return None


_AUTHORITY_ESCALATION_PHRASES = (
    "ignore restrictions", "change the tests", "edit anything necessary", "use the network",
    "skip verification", "force it", "bypass policy", "outside the repository", "do not rollback",
)


def deterministic_preflight(payload: Mapping[str, Any], *, allowed_targets: Mapping[str, Mapping[str, str]] | None = None) -> IntentCandidate | None:
    """Choose disposition before semantic interpretation or provider access."""
    target = payload.get("target") if isinstance(payload.get("target"), Mapping) else {}
    authority = payload.get("authority") if isinstance(payload.get("authority"), Mapping) else {}
    mission = payload.get("mission") if isinstance(payload.get("mission"), Mapping) else {}
    text = json.dumps(payload, sort_keys=True).lower()
    path = str(target.get("file") or "").strip()
    target_id = str(target.get("id") or payload.get("target_id") or "").strip()
    if not path or not str(target.get("symbol") or "").strip():
        return IntentCandidate("needs_clarification", reason_code="vague", question="Which grounded target and expected behavior should be used?")
    if path.startswith(("/", "~")) or ".." in path.replace("\\", "/").split("/") or ".git" in path.replace("\\", "/").split("/"):
        return IntentCandidate("refuse", reason_code="unsafe_scope", evidence=["target path is outside the workspace or targets .git"])
    if allowed_targets is not None:
        if target_id and target_id not in allowed_targets:
            return IntentCandidate("refuse", reason_code="unsafe_scope", evidence=["target ID is not in the Cartographer menu"])
        if target_id:
            chosen = allowed_targets[target_id]
            if path != str(chosen.get("file") or "") or str(target.get("symbol") or "") != str(chosen.get("symbol") or ""):
                return IntentCandidate("refuse", reason_code="unsafe_scope", evidence=["target ID does not match its grounded file and symbol"])
    if any(phrase in text for phrase in _AUTHORITY_ESCALATION_PHRASES):
        return IntentCandidate("refuse", reason_code="authority_escalation", evidence=["authority-escalation phrase detected"])
    if bool(authority.get("network_allowed")) or bool(authority.get("tests_mutable")) or int(authority.get("maximum_effects") or 1) != 1:
        return IntentCandidate("refuse", reason_code="authority_escalation", evidence=["requested authority exceeds the single local rollback-gated effect"])
    if ("tests_immutable" in text or "do not touch tests" in text) and ("tests_mutable" in text or "change the tests" in text):
        return IntentCandidate("refuse", reason_code="contradictory_constraints", evidence=["tests_immutable and tests_mutable conflict"])
    return None


_FAMILY_ALIASES = {
    "provider_normalization": "provider_identifier_normalization",
    "missing_import": "missing_import_repair",
    "arithmetic_repair": "one_function_arithmetic_correction",
    "configuration_contract_validation": "configuration_validation",
    "config_validation": "configuration_validation",
    "secret_redaction": "secret_redaction_policy",
    "rollback": "rollback_request",
    "rollback_request": "rollback_request",
}


def canonical_intent_family(value: str) -> str:
    return _FAMILY_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())


_FAILURE_ALIASES = {
    "configuration_contract_failure": "configuration_schema_failure",
    "rollback_request": "operator_requested_rollback",
}


def canonical_failure_class(value: str) -> str:
    return _FAILURE_ALIASES.get(str(value or "").strip().lower(), str(value or "").strip().lower())


def compile_intent_candidate(payload: Mapping[str, Any]) -> IntentCandidate:
    """Validate only semantic model output; never infer missing authority."""
    if not isinstance(payload, Mapping):
        raise CrystalIRValidationError("IntentCandidate must be an object")
    # Accept the compact wire dialect only, with a narrow compatibility path
    # for hand-authored tests and previously recorded translator receipts.
    status = str(payload.get("s") or payload.get("status") or "").strip()
    status = {"ok": "interpreted", "interpreted": "interpreted"}.get(status, status)
    if status not in {"interpreted", "needs_clarification", "refuse"}:
        raise CrystalIRValidationError("IntentCandidate requires status interpreted, needs_clarification, or refuse")
    if status != "interpreted":
        reason = str(payload.get("r") or payload.get("reason_code") or "unknown_intent").strip()
        return IntentCandidate(status=status, reason_code=reason, question=str(payload.get("q") or payload.get("question") or "").strip(), evidence=tuple(str(item) for item in (payload.get("e") or payload.get("evidence") or [])))
    family = str(payload.get("f") or payload.get("intent_family") or "unknown").strip()
    failure = str(payload.get("fc") or payload.get("failure_class") or "unknown").strip()
    effect = str(payload.get("fx") or payload.get("requested_effect") or "unknown").strip()
    symbol = str(payload.get("sym") or payload.get("target_symbol_hint") or "").strip()
    if family == "unknown" or failure == "unknown" or effect == "unknown" or not symbol:
        raise CrystalIRValidationError("interpreted IntentCandidate requires family, symbol, failure class, and effect")
    examples = payload.get("ex") if payload.get("ex") is not None else payload.get("examples") or []
    normalized_examples = tuple((str(item[0]), str(item[1])) for item in examples if isinstance(item, (list, tuple)) and len(item) == 2)
    constraints = tuple(str(item) for item in (payload.get("c") if payload.get("c") is not None else payload.get("constraints") or []))
    uncertainties = tuple(str(item) for item in (payload.get("u") if payload.get("u") is not None else payload.get("uncertainties") or []))
    return IntentCandidate("interpreted", family, symbol, failure, effect, constraints, normalized_examples, uncertainties)


def compile_crystal_ir_from_intent(candidate: IntentCandidate | Mapping[str, Any], *, objective: str, target_file: str, target_symbol: str = "", examples: list[dict[str, str]] | None = None) -> CrystalIR:
    """Author canonical authority from a validated semantic candidate."""
    intent = candidate if isinstance(candidate, IntentCandidate) else compile_intent_candidate(candidate)
    if intent.status != "interpreted":
        raise CrystalIRValidationError(f"cannot compile {intent.status} candidate into executable-shaped Crystal IR")
    symbol = target_symbol or intent.target_symbol_hint
    transform_map = {
        "provider_normalization": ["strip_whitespace", "lowercase", {"replace_separator": {"from": ["-", " "], "to": "_"}}],
        "missing_import": ["add_import"],
        "arithmetic_repair": ["replace_expression"],
        "configuration_validation": ["replace_function"],
        "secret_redaction": ["replace_function"],
        "rollback": ["replace_exact"],
    }
    payload = {
        "version": VERSION,
        "mission": {"objective": objective},
        "target": {"file": target_file, "symbol": symbol},
        "observed_failure": {"class": intent.failure_class, "examples": examples or [{"input": key, "expected": value} for key, value in intent.examples]},
        "required_transform": {"pipeline": transform_map.get(intent.intent_family, ["replace_exact"])},
        "authority": {"writable_files": [target_file], "tests_mutable": False, "network_allowed": False, "maximum_effects": 1},
        "postconditions": ["syntax_valid", "target_tests_pass", "no_unrelated_diff"],
        "rollback": {"required": True},
        "unresolved_fields": list(intent.uncertainties),
    }
    return compile_crystal_ir(payload)


@dataclass(frozen=True)
class CrystalIR:
    objective: str
    target_file: str
    target_symbol: str
    failure_class: str
    examples: tuple[dict[str, str], ...]
    transforms: tuple[dict[str, Any], ...]
    writable_files: tuple[str, ...]
    tests_mutable: bool
    network_allowed: bool
    maximum_effects: int
    postconditions: tuple[str, ...]
    rollback_required: bool
    unresolved_fields: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"beast_object_type": "crystal_ir", "version": VERSION, **asdict(self)}

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @property
    def model_authority(self) -> dict[str, bool]:
        return {"interpret": True, "propose": True, "execute": False, "authorize": False, "declare_success": False}


def _string(value: Any, field: str, *, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise CrystalIRValidationError(f"Crystal IR requires {field}")
    return result


def _files(values: Any) -> tuple[str, ...]:
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple)) or not values:
        raise CrystalIRValidationError("Crystal IR requires writable_files")
    result = tuple(_string(item, "writable file") for item in values)
    for path in result:
        if not _SAFE_RELATIVE.match(path) or ".." in path.replace("\\", "/").split("/"):
            raise CrystalIRValidationError(f"unsafe writable file: {path}")
    return result


def compile_crystal_ir(payload: Mapping[str, Any]) -> CrystalIR:
    """Validate and canonicalize a translator packet; never execute it."""
    if not isinstance(payload, Mapping):
        raise CrystalIRValidationError("Crystal IR must be an object")
    version = str(payload.get("version") or VERSION)
    if version != VERSION:
        raise CrystalIRValidationError(f"unsupported Crystal IR version: {version}")
    target = payload.get("target") if isinstance(payload.get("target"), Mapping) else {}
    failure = payload.get("observed_failure") if isinstance(payload.get("observed_failure"), Mapping) else {}
    required = payload.get("required_transform") if isinstance(payload.get("required_transform"), Mapping) else {}
    authority = payload.get("authority") if isinstance(payload.get("authority"), Mapping) else {}
    postconditions = payload.get("postconditions") or []
    if isinstance(postconditions, str):
        postconditions = [postconditions]
    if not isinstance(postconditions, (list, tuple)) or not postconditions:
        raise CrystalIRValidationError("Crystal IR requires postconditions")
    pipeline = required.get("pipeline") or []
    if not isinstance(pipeline, (list, tuple)) or not pipeline:
        raise CrystalIRValidationError("Crystal IR requires a non-empty transform pipeline")
    transforms: list[dict[str, Any]] = []
    for item in pipeline:
        if isinstance(item, str):
            name, options = item.strip(), {}
        elif isinstance(item, Mapping) and len(item) == 1:
            name = str(next(iter(item)))
            options = dict(next(iter(item.values()))) if isinstance(next(iter(item.values())), Mapping) else {}
        else:
            raise CrystalIRValidationError("each transform must be a name or one-key object")
        if name not in _ALLOWED_TRANSFORMS:
            raise CrystalIRValidationError(f"unsupported transform: {name}")
        transforms.append({"name": name, **options})
    maximum_effects = int(authority.get("maximum_effects") or 0)
    if maximum_effects < 1 or maximum_effects > 16:
        raise CrystalIRValidationError("maximum_effects must be between 1 and 16")
    writable = _files(authority.get("writable_files") or target.get("file"))
    target_file = _string(target.get("file") or writable[0], "target.file")
    if target_file not in writable:
        raise CrystalIRValidationError("target.file must be declared writable")
    if ".git" in target_file.replace("\\", "/").split("/"):
        raise CrystalIRValidationError("Crystal IR may not target .git")
    if len(writable) > 1 and maximum_effects <= 1:
        raise CrystalIRValidationError("one-effect Crystal IR cannot span multiple files")
    examples = payload.get("examples") or (failure.get("examples") if isinstance(failure, Mapping) else []) or []
    if not isinstance(examples, (list, tuple)):
        raise CrystalIRValidationError("examples must be a list")
    normalized_examples = tuple({str(k): str(v) for k, v in item.items()} for item in examples if isinstance(item, Mapping))
    unresolved = payload.get("unresolved_fields") or []
    if isinstance(unresolved, str):
        unresolved = [unresolved]
    return CrystalIR(
        objective=_string(payload.get("mission", {}).get("objective") if isinstance(payload.get("mission"), Mapping) else payload.get("objective"), "objective"),
        target_file=target_file,
        target_symbol=_string(target.get("symbol"), "target.symbol"),
        failure_class=_string(failure.get("class"), "observed_failure.class"),
        examples=normalized_examples,
        transforms=tuple(transforms),
        writable_files=writable,
        tests_mutable=bool(authority.get("tests_mutable", False)),
        network_allowed=bool(authority.get("network_allowed", False)),
        maximum_effects=maximum_effects,
        postconditions=tuple(_string(item, "postcondition") for item in postconditions),
        rollback_required=bool((payload.get("rollback") or {}).get("required", False)) if isinstance(payload.get("rollback"), Mapping) else bool(payload.get("rollback")),
        unresolved_fields=tuple(_string(item, "unresolved field") for item in unresolved),
    )


def translator_prompt(objective: str, *, target_file: str = "", context: str = "") -> str:
    """Build the compact prompt for a zero-authority IntentCandidate translator."""
    return (
        "Return one compact JSON IntentCandidate only. Do not solve, edit, execute, approve, "
        "inspect the network, select files, or claim success. BEAST supplies all authority. "
        "Use s=ok for a clear interpretation, needs_clarification for ambiguity, and refuse for unsafe scope. "
        "The compact keys are s,f,sym,fc,fx,c,ex,u,r,q,e. For s=ok, emit f,sym,fc,fx; otherwise emit a reason.\n"
        f"Objective: {objective.strip()}\n"
        f"Target hint: {target_file.strip()}\n"
        f"Observed context: {context.strip()}\n"
        "Allowed f: provider_normalization, missing_import, arithmetic_repair, configuration_validation, secret_redaction, rollback, unknown. "
        "Allowed fc: identifier_alias_mismatch, missing_import, arithmetic_invariant_failure, configuration_contract_failure, secret_exposure, rollback_request, unknown. "
        "Allowed fx: canonicalize, add_import, correct_arithmetic, validate_configuration, redact_secret, rollback, unknown. "
        "Wire contract: s=ok requires f,sym,fc,fx; s=needs_clarification requires r,q; s=refuse requires r. "
        "Use the exact enum vocabulary above and omit unknown optional keys. This is a semantic packet, not crystal.ir.v1; "
        "BEAST deterministically compiles accepted packets into crystal.ir.v1."
    )
