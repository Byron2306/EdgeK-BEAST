"""BEAST Action IR: compact provider intent packets."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


ACTION_IR_KIND = "beast.action_intent.v1"


@dataclass(frozen=True)
class FileReference:
    ref: str
    path: str
    sha256: str = ""
    symbols: List[str] = field(default_factory=list)
    anchors: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionTarget:
    file_ref: str = ""
    path: str = ""
    symbol: str = ""
    anchor_ref: str = ""
    sha256: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ActionTarget":
        return cls(
            file_ref=str(payload.get("file_ref") or payload.get("ref") or ""),
            path=str(payload.get("path") or ""),
            symbol=str(payload.get("symbol") or ""),
            anchor_ref=str(payload.get("anchor_ref") or ""),
            sha256=str(payload.get("sha256") or payload.get("file_sha256") or ""),
        )


@dataclass(frozen=True)
class ActionIntent:
    id: str
    type: str
    target: ActionTarget
    intent: str = ""
    constraints: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    old: str = ""
    new: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], index: int) -> "ActionIntent":
        target_payload = payload.get("target") if isinstance(payload.get("target"), dict) else payload
        constraints = payload.get("constraints") or []
        parameters_payload = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else payload.get("args")
        if not isinstance(parameters_payload, dict):
            parameters_payload = payload
        return cls(
            id=str(payload.get("id") or payload.get("op_id") or f"a{index + 1}"),
            type=str(payload.get("type") or payload.get("op") or ""),
            target=ActionTarget.from_dict(target_payload),
            intent=str(payload.get("intent") or payload.get("change_intent") or payload.get("why") or ""),
            constraints=[str(item) for item in constraints if item],
            parameters={
                str(key): value
                for key, value in parameters_payload.items()
                if key not in {"id", "op_id", "type", "op", "target", "intent", "change_intent", "why", "constraints", "old", "new"}
            },
            old=str(payload.get("old") or ""),
            new=str(payload.get("new") or ""),
        )


@dataclass(frozen=True)
class ActionIR:
    kind: str
    objective: str
    actions: List[ActionIntent]
    verify: List[str] = field(default_factory=list)
    fallback: str = ""
    handoff_hash: str = ""
    provider_handoff_hash: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ActionIR":
        actions_payload = payload.get("actions")
        if not isinstance(actions_payload, list):
            actions_payload = payload.get("operations") if isinstance(payload.get("operations"), list) else []
        actions = [
            ActionIntent.from_dict(item, index)
            for index, item in enumerate(actions_payload)
            if isinstance(item, dict)
        ]
        verify = payload.get("verify") or payload.get("tests") or []
        return cls(
            kind=str(payload.get("kind") or ACTION_IR_KIND),
            objective=str(payload.get("objective") or ""),
            actions=actions,
            verify=[str(item) for item in verify if item],
            fallback=str(payload.get("fallback") or ""),
            handoff_hash=str(payload.get("provider_handoff_hash") or payload.get("handoff_hash") or payload.get("input_handoff_hash") or ""),
            provider_handoff_hash=str(payload.get("provider_handoff_hash") or payload.get("handoff_hash") or payload.get("input_handoff_hash") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def action_ir_schema() -> Dict[str, Any]:
    return {
        "kind": ACTION_IR_KIND,
        "objective": "short objective",
        "actions": [
            {
                "id": "a1",
                "type": "replace_anchor | modify_symbol | add_provider_record | set_default_model | add_provider_alias | ask_for_context | run_verifier",
                "target": {
                    "file_ref": "F1",
                    "path": "optional allowed path",
                    "symbol": "optional symbol",
                    "anchor_ref": "optional anchor id",
                },
                "intent": "short intended local change",
                "constraints": ["preserve existing behavior"],
                "parameters": {"key": "value for semantic local transforms"},
                "old": "optional exact old snippet for replace_anchor",
                "new": "optional replacement snippet for replace_anchor",
            }
        ],
        "verify": ["python -m pytest tests -q"],
        "provider_handoff_hash": "copy trace.provider_handoff_hash from the provider handoff",
        "fallback": "ask_for_context if refs cannot be resolved",
    }
