"""
EdgeK BEAST Canon Registry.

Local schema and validation registry for V2 artifacts. Canon keeps object shapes,
identity fields, hashes, and cross-object references explicit before workflow
cards are allowed anywhere near a future executor.
"""

import re
from typing import Any, Dict, List, Optional


class CanonRegistry:
    """Validate BEAST V2 objects against lightweight local schemas."""

    HASH_RE = re.compile(r"^sha256:[a-fA-F0-9]{64}$")
    ID_PREFIXES = {
        "task_envelope": {"task_id": "tsk_"},
        "route_card": {"route_id": "route_"},
        "quality_cascade_report": {},
        "context_packet": {"packet_id": "pkt_", "task_id": "tsk_"},
        "forge_scorecard": {"scorecard_id": "forge_", "task_id": "tsk_"},
        "conductor_workflow_card": {"workflow_id": "wf_", "task_id": "tsk_"},
        "provider_diagnostic": {"task_id": "tsk_"},
        "provider_diagnostic_summary": {"task_id": "tsk_"},
        "promotion_candidate": {"candidate_id": "promo_"},
        "sensor_event": {"event_id": "event:sha256:"},
        "process_lease": {"lease_id": "process:sha256:"},
        "socket_identity": {"identity": "socket:sha256:"},
        "runtime_episode": {},
        "compute_crystal_ir": {"identity": "crystal:"},
        "crystal_artifact_descriptor": {},
        "pidfd_signal_receipt": {"lease_id": "process:sha256:"},
        "cgroup_capsule_action_receipt": {},
        "cgroup_graceful_cleanup_receipt": {},
        "cgroup_capsule_orphan_state": {},
        "beast_process_plane_capabilities": {},
    }

    def __init__(self):
        self.schemas = self._schemas()

    def schema_catalog(self) -> Dict[str, Any]:
        """Return the canonical V2 schema catalog."""
        return {
            "beast_object_type": "canon_schema_catalog",
            "version": "1.0",
            "schemas": self.schemas,
            "count": len(self.schemas),
        }

    def metrics(self) -> Dict[str, Any]:
        """Return registry coverage metrics."""
        schema_names = sorted(self.schemas.keys())
        return {
            "beast_object_type": "canon_metrics",
            "version": "1.0",
            "schema_count": len(schema_names),
            "schemas": schema_names,
            "hash_validated_types": [
                name for name, schema in self.schemas.items()
                if schema.get("hash_fields")
            ],
            "cross_reference_rules": [
                "context_packet.task_id must match task_envelope.task_id when both are supplied",
                "forge_scorecard.context_packet_id must match context_packet.packet_id when both are supplied",
                "conductor_workflow_card.forge_scorecard_id must match forge_scorecard.scorecard_id when both are supplied",
                "conductor_workflow_card.context_packet_id must match context_packet.packet_id when both are supplied",
                "route ids must match across route_card, context_packet, forge_scorecard, and workflow when present",
            ],
        }

    def validate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validate one object or an artifact bundle."""
        if not isinstance(payload, dict):
            return self._result("unknown", False, [{"path": "$", "message": "payload must be an object"}], [])
        if "artifacts" in payload:
            return self.validate_bundle(payload.get("artifacts") or {})
        obj = payload.get("object") or payload
        return self.validate_object(obj)

    def validate_object(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        object_type = obj.get("beast_object_type") or obj.get("chronicle_type")
        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        if not object_type:
            errors.append({"path": "beast_object_type", "message": "required field is missing"})
            return self._result("unknown", False, errors, warnings)
        schema = self.schemas.get(object_type)
        if not schema:
            errors.append({"path": "beast_object_type", "message": f"unknown BEAST object type: {object_type}"})
            return self._result(object_type, False, errors, warnings)

        for field in schema.get("required", []):
            if not self._present(obj.get(field)):
                errors.append({"path": field, "message": "required field is missing"})
        supported_versions = schema.get("supported_versions") or []
        if supported_versions and obj.get("version") not in supported_versions:
            errors.append({
                "path": "version",
                "message": f"unsupported version; expected one of {supported_versions}",
            })
        for field, expected in schema.get("types", {}).items():
            value = obj.get(field)
            if self._present(value) and not self._is_type(value, expected):
                errors.append({"path": field, "message": f"expected {expected}"})
        for field in schema.get("hash_fields", []):
            value = obj.get(field)
            if self._present(value) and not self.HASH_RE.match(str(value)):
                errors.append({"path": field, "message": "expected sha256:<64 hex chars>"})
        for field, prefix in self.ID_PREFIXES.get(object_type, {}).items():
            value = obj.get(field)
            if self._present(value) and not str(value).startswith(prefix):
                errors.append({"path": field, "message": f"expected id prefix {prefix}"})
        for field in schema.get("recommended", []):
            if not self._present(obj.get(field)):
                warnings.append({"path": field, "message": "recommended field is missing"})

        return self._result(object_type, not errors, errors, warnings)

    def validate_bundle(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a set of related artifacts and their references."""
        errors: List[Dict[str, str]] = []
        warnings: List[Dict[str, str]] = []
        object_results = {}
        for name, obj in artifacts.items():
            if isinstance(obj, dict):
                result = self.validate_object(obj)
                object_results[name] = result
                for error in result["errors"]:
                    errors.append({"path": f"{name}.{error['path']}", "message": error["message"]})
                for warning in result["warnings"]:
                    warnings.append({"path": f"{name}.{warning['path']}", "message": warning["message"]})
            elif obj is not None:
                errors.append({"path": name, "message": "artifact must be an object"})

        self._check_equal(artifacts, errors, "task_envelope", "task_id", "context_packet", "task_id")
        self._check_equal(artifacts, errors, "task_envelope", "task_id", "forge_scorecard", "task_id")
        self._check_equal(artifacts, errors, "task_envelope", "task_id", "workflow", "task_id")
        self._check_equal(artifacts, errors, "context_packet", "packet_id", "forge_scorecard", "context_packet_id")
        self._check_equal(artifacts, errors, "context_packet", "packet_id", "workflow", "context_packet_id")
        self._check_equal(artifacts, errors, "forge_scorecard", "scorecard_id", "workflow", "forge_scorecard_id")
        self._check_route_alignment(artifacts, errors)

        return {
            "beast_object_type": "canon_validation_report",
            "version": "1.0",
            "object_type": "artifact_bundle",
            "valid": not errors,
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "warnings": warnings,
            "object_results": object_results,
            "summary": {
                "artifact_count": len([value for value in artifacts.values() if isinstance(value, dict)]),
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        }

    def _schemas(self) -> Dict[str, Dict[str, Any]]:
        return {
            "task_envelope": {
                "required": ["beast_object_type", "version", "task_id", "intent", "task_class", "risk_level", "privacy_class", "inputs", "context_budget", "success_criteria"],
                "recommended": ["allowed_actions", "approval_required_for"],
                "types": {"inputs": "dict", "context_budget": "dict", "success_criteria": "list"},
                "hash_fields": [],
            },
            "route_card": {
                "required": ["beast_object_type", "version", "route_id", "name", "task_class", "preferred_order", "avoid", "safety", "promotion_status"],
                "recommended": ["route_quality_score", "cache_policy"],
                "types": {"preferred_order": "list", "avoid": "list", "safety": "dict"},
                "hash_fields": [],
            },
            "quality_cascade_report": {
                "required": ["beast_object_type", "version", "task_id", "task_class", "route_id", "status", "checks", "summary"],
                "recommended": ["local_only"],
                "types": {"checks": "list", "summary": "dict"},
                "hash_fields": [],
            },
            "context_packet": {
                "required": ["beast_object_type", "version", "packet_id", "task_id", "task_class", "context_budget", "included_evidence", "excluded_evidence", "packet_stats", "handoff_hash"],
                "recommended": ["workspace_context", "quality_summary"],
                "types": {"context_budget": "dict", "included_evidence": "list", "excluded_evidence": "list", "packet_stats": "dict"},
                "hash_fields": ["handoff_hash"],
            },
            "forge_scorecard": {
                "required": ["beast_object_type", "version", "scorecard_id", "task_id", "scores", "required_gates", "decision", "scorecard_hash"],
                "recommended": ["context_packet_id", "evidence_summary"],
                "types": {"scores": "dict", "required_gates": "dict", "recommendations": "list"},
                "hash_fields": ["scorecard_hash"],
            },
            "conductor_workflow_card": {
                "required": ["beast_object_type", "version", "workflow_id", "task_id", "execution_mode", "executor_binding", "decision", "required_gates", "steps", "verification_plan", "workflow_hash"],
                "recommended": ["context_packet_id", "forge_scorecard_id", "swarm", "chronicle_plan"],
                "types": {"executor_binding": "dict", "required_gates": "list", "steps": "list", "verification_plan": "dict"},
                "hash_fields": ["workflow_hash"],
            },
            "provider_diagnostic": {
                "required": ["beast_object_type", "version", "task_id", "provider", "failure_category", "confidence", "envelope", "checks", "recommendations"],
                "recommended": ["route_card", "quality_report", "chronicle"],
                "types": {"envelope": "dict", "checks": "list", "recommendations": "list"},
                "hash_fields": [],
            },
            "provider_diagnostic_summary": {
                "required": ["chronicle_type", "version", "task_id", "task_class", "provider", "category", "summary", "root_cause", "verification", "recommendations"],
                "recommended": ["route_card", "envelope", "artifacts"],
                "types": {"verification": "dict", "recommendations": "list"},
                "hash_fields": [],
            },
            "promotion_candidate": {
                "required": ["beast_object_type", "version", "candidate_id", "candidate_type", "scenario", "eligible", "approval_status", "confidence", "evidence", "canon", "tool_laziness", "promotion_action", "candidate_hash"],
                "recommended": ["recommendations"],
                "types": {"evidence": "dict", "canon": "dict", "tool_laziness": "dict", "promotion_action": "dict", "recommendations": "list"},
                "hash_fields": ["candidate_hash"],
            },
            "sensor_event": {
                "required": ["beast_object_type", "version", "event_id", "event_type", "source", "source_instance", "ordering", "attribution", "confidence", "privacy", "payload_schema", "payload", "payload_sha256"],
                "recommended": [],
                "types": {"ordering": "dict", "attribution": "dict", "confidence": "dict", "privacy": "dict", "payload": "dict"},
                "hash_fields": ["payload_sha256"],
                "supported_versions": ["1.0"],
            },
            "process_lease": {
                "required": ["beast_object_type", "version", "lease_id", "boot_id", "pid_at_observation", "start_time_ticks", "executable_digest", "cgroup_id", "pid_namespace_inode", "mount_namespace_inode", "parent_identity_hash", "owner_scope", "acquired_at"],
                "recommended": ["exited_at"],
                "types": {"pid_at_observation": "number", "start_time_ticks": "number"},
                "hash_fields": ["executable_digest", "parent_identity_hash"],
                "supported_versions": ["1.0"],
            },
            "socket_identity": {
                "required": ["beast_object_type", "version", "identity", "family", "protocol", "local_address_class", "local_port", "remote_scope", "owning_process", "service_id", "workspace_id", "cgroup_id", "listener_generation", "opened_at_monotonic_ns", "policy_class"],
                "recommended": [],
                "types": {"local_port": "number", "listener_generation": "number", "opened_at_monotonic_ns": "number"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
            "runtime_episode": {
                "required": ["beast_object_type", "version", "mission_id", "objective_hash", "workspace_identity", "initial_state_hash", "event_ids", "event_range", "source_loss", "causal_graph", "resources", "outcome", "episode_hash", "authority"],
                "recommended": [],
                "types": {"event_ids": "list", "event_range": "dict", "source_loss": "dict", "causal_graph": "dict", "resources": "dict", "outcome": "dict"},
                "hash_fields": ["objective_hash", "initial_state_hash", "episode_hash"],
                "supported_versions": ["1.0"],
            },
            "compute_crystal_ir": {
                "required": ["beast_object_type", "version", "identity", "artifact_digest", "signer", "artifact_class", "task_family", "authority", "applicability", "parameters", "preconditions", "execution_graph", "postconditions", "topology", "evidence_requirements", "economics", "decay"],
                "recommended": [],
                "types": {"task_family": "list", "authority": "dict", "applicability": "dict", "parameters": "dict", "preconditions": "list", "execution_graph": "dict", "postconditions": "list", "topology": "dict", "evidence_requirements": "list", "economics": "dict", "decay": "dict"},
                "hash_fields": ["artifact_digest"],
                "supported_versions": ["1.0"],
            },
            "crystal_artifact_descriptor": {
                "required": ["beast_object_type", "version", "artifact_class", "authority", "verification_state", "applicability_hash", "policy_generation", "expires_at"],
                "recommended": [],
                "types": {},
                "hash_fields": ["applicability_hash"],
                "supported_versions": ["1.0"],
            },
            "pidfd_signal_receipt": {
                "required": ["beast_object_type", "version", "lease_id", "signal_number", "approved_by", "approval_receipt_id", "reason", "targeted_via", "integer_pid_signal_used", "created_at"],
                "recommended": [],
                "types": {"signal_number": "number"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
            "cgroup_capsule_action_receipt": {
                "required": ["beast_object_type", "version", "mission_id", "action", "confirmed", "authorization", "details", "created_at"],
                "recommended": [],
                "types": {"authorization": "dict", "details": "dict"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
            "cgroup_graceful_cleanup_receipt": {
                "required": ["beast_object_type", "version", "mission_id", "signal_receipts", "empty_after_graceful_wait", "escalated_to_cgroup_kill", "escalation_required", "timeout_seconds"],
                "recommended": ["kill_receipt"],
                "types": {"signal_receipts": "list", "timeout_seconds": "number"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
            "cgroup_capsule_orphan_state": {
                "required": ["beast_object_type", "version", "mission_id", "members", "expected", "unexpected_members", "missing_expected_members", "orphaned", "populated", "read_only"],
                "recommended": [],
                "types": {"members": "list", "expected": "list", "unexpected_members": "list", "missing_expected_members": "list"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
            "beast_process_plane_capabilities": {
                "required": ["beast_object_type", "version", "authority", "actuator_available", "platform", "cgroup_v2", "claim_boundary"],
                "recommended": [],
                "types": {"platform": "dict", "cgroup_v2": "dict", "claim_boundary": "dict"},
                "hash_fields": [],
                "supported_versions": ["1.0"],
            },
        }

    def _check_equal(
        self,
        artifacts: Dict[str, Any],
        errors: List[Dict[str, str]],
        left_name: str,
        left_field: str,
        right_name: str,
        right_field: str,
    ) -> None:
        left = artifacts.get(left_name) or {}
        right = artifacts.get(right_name) or {}
        if not isinstance(left, dict) or not isinstance(right, dict):
            return
        left_value = left.get(left_field)
        right_value = right.get(right_field)
        if self._present(left_value) and self._present(right_value) and left_value != right_value:
            errors.append({
                "path": f"{left_name}.{left_field}->{right_name}.{right_field}",
                "message": f"reference mismatch: {left_value} != {right_value}",
            })

    def _check_route_alignment(self, artifacts: Dict[str, Any], errors: List[Dict[str, str]]) -> None:
        route_values = []
        for name, field in (
            ("route_card", "route_id"),
            ("context_packet", "route_id"),
            ("forge_scorecard", "route_id"),
            ("workflow", "route_id"),
        ):
            obj = artifacts.get(name) or {}
            if isinstance(obj, dict) and self._present(obj.get(field)):
                route_values.append((name, obj[field]))
        if not route_values:
            return
        first_name, first_value = route_values[0]
        for name, value in route_values[1:]:
            if value != first_value:
                errors.append({
                    "path": f"{first_name}.route_id->{name}.route_id",
                    "message": f"route mismatch: {first_value} != {value}",
                })

    def _result(
        self,
        object_type: str,
        valid: bool,
        errors: List[Dict[str, str]],
        warnings: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        return {
            "beast_object_type": "canon_validation_report",
            "version": "1.0",
            "object_type": object_type,
            "valid": valid,
            "status": "passed" if valid else "failed",
            "errors": errors,
            "warnings": warnings,
            "summary": {
                "error_count": len(errors),
                "warning_count": len(warnings),
            },
        }

    def _present(self, value: Any) -> bool:
        return value is not None and value != ""

    def _is_type(self, value: Any, expected: str) -> bool:
        if expected == "dict":
            return isinstance(value, dict)
        if expected == "list":
            return isinstance(value, list)
        if expected == "str":
            return isinstance(value, str)
        if expected == "number":
            return isinstance(value, (int, float))
        return True
