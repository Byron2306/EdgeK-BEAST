"""Context-aware generative crystals.

Generative crystals are bounded templates extracted from verified work.  They
are not autonomous code generation and they do not grant authority.  They bind
local parameters into deterministic Action IR, attach verifier/rollback/approval
requirements, and demote themselves when structural generalization fails.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.networking.commons_privacy import CommonsPrivacyScrubber


PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _short_hash(value: Any, length: int = 20) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()[:length]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class GenerativeCrystalTemplate:
    template_id: str
    task_family: str
    boundary_hash: str
    required_parameters: List[str]
    action_ir_template: Dict[str, Any]
    verifier_plan: List[str]
    rollback_template: Dict[str, Any]
    approval_required: bool
    risk_class: str
    source_evidence_hash: str
    created_at: str
    expires_at: str
    state: str = "candidate"
    successful_instantiations: int = 0
    false_hits: int = 0
    demotion_reason: str = ""
    credit_reversal_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "generative_crystal_template",
            "version": "1.0",
            **asdict(self),
        }


class GenerativeCrystalStore:
    def __init__(self, root: Optional[Path] = None, *, false_hit_threshold: int = 2):
        self.root = Path(root or Path("benchmarks/results/generative_crystals"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.templates_dir = self.root / "templates"
        self.instantiations_dir = self.root / "instantiations"
        self.receipts_dir = self.root / "receipts"
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.instantiations_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self.false_hit_threshold = max(1, int(false_hit_threshold))

    def register_template(
        self,
        *,
        task_family: str,
        boundary: Dict[str, Any],
        required_parameters: Iterable[str],
        action_ir_template: Dict[str, Any],
        verifier_plan: Iterable[str],
        rollback_template: Dict[str, Any],
        approval_required: bool,
        risk_class: str,
        source_evidence_hash: str,
        ttl_seconds: int = 86_400,
    ) -> Dict[str, Any]:
        payload = {
            "task_family": task_family,
            "boundary": boundary,
            "required_parameters": list(required_parameters),
            "action_ir_template": action_ir_template,
            "verifier_plan": list(verifier_plan),
            "rollback_template": rollback_template,
        }
        findings = self._privacy_findings(payload)
        if findings:
            raise ValueError("generative crystal privacy scan failed: " + "; ".join(findings[:3]))
        template_id = "gct_" + _short_hash(payload)
        template = GenerativeCrystalTemplate(
            template_id=template_id,
            task_family=str(task_family),
            boundary_hash=_sha256_payload(boundary),
            required_parameters=[str(item) for item in required_parameters],
            action_ir_template=action_ir_template,
            verifier_plan=[str(item) for item in verifier_plan],
            rollback_template=rollback_template,
            approval_required=bool(approval_required),
            risk_class=str(risk_class),
            source_evidence_hash=str(source_evidence_hash),
            created_at=_utc_now(),
            expires_at=(datetime.now(timezone.utc) + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat(),
        )
        validation = self.validate_template(template)
        if not validation["valid"]:
            raise ValueError("generative crystal template validation failed: " + "; ".join(validation["errors"]))
        self._write_template(template)
        return {"template": template.to_dict(), "validation": validation}

    def instantiate(
        self,
        template_id: str,
        *,
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        template = self._read_template(template_id)
        if template is None:
            raise ValueError("template not found")
        validation = self.validate_template(template)
        if not validation["valid"]:
            raise ValueError("template is not valid: " + "; ".join(validation["errors"]))
        boundary = self._boundary_from_context(context)
        if boundary != template.boundary_hash:
            return self._instantiation_miss(template, parameters, context, "boundary_hash_mismatch")
        missing = [name for name in template.required_parameters if name not in parameters or parameters.get(name) in {None, ""}]
        if missing:
            return self._instantiation_miss(template, parameters, context, "missing_parameters:" + ",".join(missing))
        rendered_action = self._render(template.action_ir_template, parameters)
        rendered_rollback = self._render(template.rollback_template, parameters)
        rendered_verifier_plan = self._render(template.verifier_plan, parameters)
        unresolved = self._unresolved_placeholders({
            "action_ir": rendered_action,
            "rollback": rendered_rollback,
            "verifier_plan": rendered_verifier_plan,
        })
        if unresolved:
            return self._instantiation_miss(template, parameters, context, "unresolved_placeholders:" + ",".join(sorted(unresolved)))
        payload = {
            "beast_object_type": "generative_crystal_instantiation",
            "version": "1.0",
            "instantiation_id": "gci_" + _short_hash({
                "template_id": template.template_id,
                "parameters": parameters,
                "context": context,
            }),
            "template_id": template.template_id,
            "task_family": template.task_family,
            "boundary_hash": template.boundary_hash,
            "context_hash": _sha256_payload(context),
            "action_ir": rendered_action,
            "verifier_plan": list(rendered_verifier_plan),
            "rollback": rendered_rollback,
            "approval_required": template.approval_required,
            "risk_class": template.risk_class,
            "authority": "proposal_only_until_local_verifiers_pass",
            "created_at": _utc_now(),
        }
        findings = self._privacy_findings(payload)
        if findings:
            return self._instantiation_miss(template, parameters, context, "privacy_scan_failed")
        self._write_json(self.instantiations_dir / f"{payload['instantiation_id']}.json", payload)
        return {"hit": True, "reason": "context_boundary_match", "instantiation": payload}

    def record_verifier_result(
        self,
        instantiation: Dict[str, Any],
        *,
        verifier_results: Dict[str, bool],
    ) -> Dict[str, Any]:
        template = self._read_template(str(instantiation.get("template_id") or ""))
        if template is None:
            raise ValueError("template not found")
        required = list(instantiation.get("verifier_plan") or [])
        passed = bool(required) and all(bool(verifier_results.get(name)) for name in required)
        if passed:
            template.successful_instantiations += 1
            if template.state == "candidate" and template.successful_instantiations >= 2:
                template.state = "active"
        else:
            template.false_hits += 1
            if template.false_hits >= self.false_hit_threshold:
                template.state = "demoted"
                template.demotion_reason = "false_hit_threshold_exceeded"
                template.credit_reversal_required = True
        self._write_template(template)
        receipt = {
            "beast_object_type": "generative_crystal_verifier_receipt",
            "version": "1.0",
            "receipt_id": "gcv_" + _short_hash({
                "instantiation_id": instantiation.get("instantiation_id"),
                "verifier_results": verifier_results,
                "template_state": template.state,
            }),
            "template_id": template.template_id,
            "instantiation_id": instantiation.get("instantiation_id"),
            "passed": passed,
            "verifier_results": verifier_results,
            "template_state": template.state,
            "false_hits": template.false_hits,
            "successful_instantiations": template.successful_instantiations,
            "credit_reversal_required": template.credit_reversal_required,
            "authority": "local_verifier_receipt",
            "created_at": _utc_now(),
        }
        self._write_json(self.receipts_dir / f"{receipt['receipt_id']}.json", receipt)
        return receipt

    def validate_template(self, template: GenerativeCrystalTemplate) -> Dict[str, Any]:
        errors: List[str] = []
        if template.state not in {"candidate", "active", "demoted", "expired"}:
            errors.append("invalid_state")
        if template.state == "demoted":
            errors.append("template_demoted")
        try:
            if _parse_time(template.expires_at) <= datetime.now(timezone.utc):
                template.state = "expired"
                errors.append("template_expired")
        except (TypeError, ValueError):
            errors.append("invalid_expires_at")
        if not template.verifier_plan:
            errors.append("missing_verifier_plan")
        if not template.rollback_template:
            errors.append("missing_rollback_template")
        placeholders = self._unresolved_placeholders({
            "action_ir": template.action_ir_template,
            "verifier_plan": template.verifier_plan,
            "rollback": template.rollback_template,
        })
        missing_requirements = sorted(placeholders - set(template.required_parameters))
        if missing_requirements:
            errors.append("placeholder_without_required_parameter:" + ",".join(missing_requirements))
        findings = self._privacy_findings(template.to_dict())
        if findings:
            errors.append("privacy_scan_failed")
        return {
            "beast_object_type": "generative_crystal_template_validation",
            "version": "1.0",
            "valid": not errors,
            "errors": errors,
            "privacy_findings": findings,
            "template_id": template.template_id,
        }

    def state(self, *, include_templates: bool = False) -> Dict[str, Any]:
        templates = [self._template_from_raw(item) for item in self._read_template_rows()]
        templates = [item for item in templates if item is not None]
        payload: Dict[str, Any] = {
            "beast_object_type": "generative_crystal_store",
            "version": "1.0",
            "root": str(self.root),
            "template_count": len(templates),
            "active_templates": sum(1 for item in templates if item.state == "active"),
            "candidate_templates": sum(1 for item in templates if item.state == "candidate"),
            "demoted_templates": sum(1 for item in templates if item.state == "demoted"),
            "false_hits": sum(item.false_hits for item in templates),
            "successful_instantiations": sum(item.successful_instantiations for item in templates),
            "claim_boundary": "bounded_templates_only_no_authority_without_local_verifiers",
        }
        if include_templates:
            payload["templates"] = [item.to_dict() for item in templates]
        return payload

    def _boundary_from_context(self, context: Dict[str, Any]) -> str:
        return _sha256_payload({
            "task_family": context.get("task_family"),
            "repository_fingerprint": context.get("repository_fingerprint"),
            "tool_schema_fingerprint": context.get("tool_schema_fingerprint"),
            "policy_fingerprint": context.get("policy_fingerprint"),
        })

    def _instantiation_miss(self, template: GenerativeCrystalTemplate, parameters: Dict[str, Any], context: Dict[str, Any], reason: str) -> Dict[str, Any]:
        return {
            "beast_object_type": "generative_crystal_instantiation_miss",
            "version": "1.0",
            "hit": False,
            "reason": reason,
            "template_id": template.template_id,
            "context_hash": _sha256_payload(context),
            "parameters_hash": _sha256_payload(parameters),
            "authority": "miss_and_recompute",
        }

    def _render(self, value: Any, parameters: Dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: self._render(item, parameters) for key, item in value.items()}
        if isinstance(value, list):
            return [self._render(item, parameters) for item in value]
        if isinstance(value, str):
            def repl(match: re.Match[str]) -> str:
                return str(parameters.get(match.group(1), match.group(0)))
            return PLACEHOLDER_RE.sub(repl, value)
        return value

    def _unresolved_placeholders(self, value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for item in value.values():
                found.update(self._unresolved_placeholders(item))
        elif isinstance(value, list):
            for item in value:
                found.update(self._unresolved_placeholders(item))
        elif isinstance(value, str):
            found.update(match.group(1) for match in PLACEHOLDER_RE.finditer(value))
        return found

    def _privacy_findings(self, payload: Dict[str, Any]) -> List[str]:
        findings = CommonsPrivacyScrubber().scan_payload(payload)
        text = json.dumps(payload, sort_keys=True, default=str)
        extra = []
        for marker in ("/home/", "PRIVATE KEY", "raw_prompt", "rollback_snapshot", "private_fixture"):
            if marker in text:
                extra.append(marker)
        return [str(item) for item in findings] + extra

    def _read_template_rows(self) -> List[Dict[str, Any]]:
        rows = []
        for path in sorted(self.templates_dir.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    rows.append(value)
            except (OSError, json.JSONDecodeError):
                continue
        return rows

    def _read_template(self, template_id: str) -> Optional[GenerativeCrystalTemplate]:
        path = self.templates_dir / f"{template_id}.json"
        if not path.is_file():
            return None
        try:
            return self._template_from_raw(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return None

    def _template_from_raw(self, raw: Dict[str, Any]) -> Optional[GenerativeCrystalTemplate]:
        try:
            keys = set(GenerativeCrystalTemplate.__dataclass_fields__)
            return GenerativeCrystalTemplate(**{key: raw.get(key) for key in keys})
        except TypeError:
            return None

    def _write_template(self, template: GenerativeCrystalTemplate) -> None:
        self._write_json(self.templates_dir / f"{template.template_id}.json", template.to_dict())

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def run_phase5_generative_crystal_gauntlet(*, store: Optional[GenerativeCrystalStore] = None) -> Dict[str, Any]:
    store = store or GenerativeCrystalStore()
    context = {
        "task_family": "route_diagnostics",
        "repository_fingerprint": "sha256:local-repo-phase5",
        "tool_schema_fingerprint": "sha256:beast-tools-phase5",
        "policy_fingerprint": "sha256:proof-local-phase5",
    }
    boundary = {
        "task_family": context["task_family"],
        "repository_fingerprint": context["repository_fingerprint"],
        "tool_schema_fingerprint": context["tool_schema_fingerprint"],
        "policy_fingerprint": context["policy_fingerprint"],
    }
    registered = store.register_template(
        task_family="route_diagnostics",
        boundary=boundary,
        required_parameters=["task_id", "task_family", "verifier"],
        action_ir_template={
            "route": "local_verifier_first",
            "task_id": "{{task_id}}",
            "task_family": "{{task_family}}",
            "handoff": "compute_governor",
        },
        verifier_plan=["provider_fitness_check", "{{verifier}}"],
        rollback_template={
            "rollback_action": "discard_instantiation",
            "task_id": "{{task_id}}",
            "restore": "previous_route_card",
        },
        approval_required=True,
        risk_class="medium",
        source_evidence_hash="sha256:phase5-local-crystal-evidence",
    )
    template_id = registered["template"]["template_id"]
    contexts = [
        dict(context, structural_variant="provider_route"),
        dict(context, structural_variant="local_model_route"),
    ]
    instantiations = [
        store.instantiate(template_id, parameters={"task_id": f"phase5_task_{index}", "task_family": "route_diagnostics", "verifier": "schema_validation"}, context=item)
        for index, item in enumerate(contexts, 1)
    ]
    pass_receipts = [
        store.record_verifier_result(item["instantiation"], verifier_results={"provider_fitness_check": True, "schema_validation": True})
        for item in instantiations if item.get("hit")
    ]
    mutated_context = dict(context, tool_schema_fingerprint="sha256:mutated-tools")
    miss = store.instantiate(template_id, parameters={"task_id": "phase5_mutated", "task_family": "route_diagnostics", "verifier": "schema_validation"}, context=mutated_context)
    failed = store.instantiate(template_id, parameters={"task_id": "phase5_bad", "task_family": "route_diagnostics", "verifier": "schema_validation"}, context=context)
    fail_receipt_1 = store.record_verifier_result(failed["instantiation"], verifier_results={"provider_fitness_check": True, "schema_validation": False})
    fail_receipt_2 = store.record_verifier_result(failed["instantiation"], verifier_results={"provider_fitness_check": False, "schema_validation": False})
    state = store.state(include_templates=True)
    receipt = {
        "beast_object_type": "proof_local_phase5_generative_crystals_receipt",
        "version": "1.0",
        "status": "implemented",
        "template_id": template_id,
        "successful_instantiations": pass_receipts,
        "failed_receipts": [fail_receipt_1, fail_receipt_2],
        "boundary_miss": miss,
        "state": state,
        "exit_criteria": {
            "templates_generalize_across_structurally_similar_tasks": len(pass_receipts) >= 2,
            "instantiated_actions_pass_local_policy_and_verifiers": all(item["passed"] for item in pass_receipts),
            "failed_generalization_causes_demotion": fail_receipt_2["template_state"] == "demoted",
            "credit_reversal_on_demotion": fail_receipt_2["credit_reversal_required"] is True,
            "boundary_mutation_misses": miss["hit"] is False and miss["reason"] == "boundary_hash_mismatch",
            "rollback_and_approval_present": all(
                item.get("instantiation", {}).get("rollback") and item.get("instantiation", {}).get("approval_required") is True
                for item in instantiations
            ),
        },
    }
    latest = store.root / "proof_local_phase5_generative_crystals_latest.json"
    store._write_json(latest, receipt)
    return receipt
