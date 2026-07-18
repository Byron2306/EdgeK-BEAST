"""Governed BEAST extension marketplace manifest validation and installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


RISK_CLASSES = {"low", "medium", "high", "critical"}
ENTRYPOINT_KINDS = {"mcp_stdio", "python", "http"}


class PluginManifestError(ValueError):
    """Raised when a BEAST plugin manifest violates its governed contract."""


class PluginMarketplace:
    """Prepare, validate, and install local BEAST plugin manifests."""

    def __init__(self, registry_dir: Optional[str] = None):
        if registry_dir:
            self.registry_dir = Path(registry_dir).expanduser()
        else:
            state_root = Path(
                os.environ.get("BEAST_STATE_ROOT")
                or (Path(os.environ.get("XDG_STATE_HOME") or "~/.local/state").expanduser() / "beast")
            ).expanduser()
            self.registry_dir = state_root / "plugins"

    def prepare(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        prepared = deepcopy(manifest)
        prepared.setdefault("beast_plugin_manifest_version", "1.0")
        for tool in prepared.get("tools") or []:
            if isinstance(tool, dict):
                tool["tool_schema_hash"] = self.tool_schema_hash(tool)
        return prepared

    def validate(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []
        required = [
            "beast_plugin_manifest_version", "id", "name", "version", "publisher",
            "risk_class", "entrypoint", "tools", "permissions", "budget", "approval_policy",
        ]
        for key in required:
            if key not in manifest:
                errors.append(f"missing required field: {key}")
        plugin_id = str(manifest.get("id") or "")
        if plugin_id and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,79}", plugin_id):
            errors.append("id must be 3-80 lowercase characters using letters, numbers, dot, underscore, or hyphen")
        risk = str(manifest.get("risk_class") or "")
        if risk not in RISK_CLASSES:
            errors.append(f"risk_class must be one of {sorted(RISK_CLASSES)}")
        entrypoint = manifest.get("entrypoint") if isinstance(manifest.get("entrypoint"), dict) else {}
        if entrypoint.get("kind") not in ENTRYPOINT_KINDS:
            errors.append(f"entrypoint.kind must be one of {sorted(ENTRYPOINT_KINDS)}")
        permissions = manifest.get("permissions") if isinstance(manifest.get("permissions"), dict) else {}
        budget = manifest.get("budget") if isinstance(manifest.get("budget"), dict) else {}
        approvals = manifest.get("approval_policy") if isinstance(manifest.get("approval_policy"), dict) else {}
        errors.extend(self._validate_permissions(permissions, risk))
        errors.extend(self._validate_entrypoint(entrypoint, permissions, risk))
        errors.extend(self._validate_budget(budget))
        errors.extend(self._validate_approval_policy(approvals, permissions, risk))

        tool_results = []
        names = set()
        for index, tool in enumerate(manifest.get("tools") or []):
            if not isinstance(tool, dict):
                errors.append(f"tools[{index}] must be an object")
                continue
            name = str(tool.get("name") or "")
            if not name:
                errors.append(f"tools[{index}].name is required")
            elif name in names:
                errors.append(f"duplicate tool name: {name}")
            names.add(name)
            expected = self.tool_schema_hash(tool)
            declared = str(tool.get("tool_schema_hash") or "")
            matched = declared == expected
            if not declared:
                errors.append(f"tools[{index}].tool_schema_hash is required")
            elif not matched:
                errors.append(f"tools[{index}] schema hash mismatch")
            tool_results.append({"name": name, "declared_hash": declared, "computed_hash": expected, "matched": matched})
        if not tool_results:
            warnings.append("plugin exposes no tools")
        requires_install_approval = True
        return {
            "beast_object_type": "plugin_manifest_validation",
            "version": "1.0",
            "plugin_id": plugin_id,
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "risk_class": risk,
            "requires_install_approval": requires_install_approval,
            "tool_schema_pins": tool_results,
            "permission_summary": self._permission_summary(permissions),
            "budget": budget,
        }

    def install(
        self,
        manifest: Dict[str, Any],
        *,
        approved: bool = False,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        validation = self.validate(manifest)
        result = {
            "beast_object_type": "plugin_install_result",
            "version": "1.0",
            "plugin_id": manifest.get("id"),
            "approved": bool(approved),
            "dry_run": bool(dry_run),
            "validation": validation,
        }
        if not validation["valid"]:
            return {**result, "installed": False, "reason": "manifest validation failed"}
        if dry_run or not approved:
            return {
                **result,
                "installed": False,
                "reason": "Dry-run install; live installation requires approved=true and dry_run=false.",
            }
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        path = self.registry_dir / f"{manifest['id']}.beast-plugin.json"
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {**result, "installed": True, "reason": "manifest installed", "path": str(path)}

    def list_installed(self) -> Dict[str, Any]:
        records = []
        if self.registry_dir.exists():
            for path in sorted(self.registry_dir.glob("*.beast-plugin.json")):
                try:
                    manifest = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                records.append({
                    "id": manifest.get("id"), "name": manifest.get("name"),
                    "version": manifest.get("version"), "risk_class": manifest.get("risk_class"),
                    "publisher": manifest.get("publisher"),
                    "tools": [tool.get("name") for tool in manifest.get("tools") or [] if isinstance(tool, dict)],
                    "operational": bool(manifest.get("publisher") == "BEAST Core" and str((manifest.get("entrypoint") or {}).get("module") or "").startswith("app.kernel.beast_builtin_plugins")),
                    "path": str(path),
                })
        return {"beast_object_type": "plugin_marketplace_inventory", "version": "1.0", "count": len(records), "plugins": records}

    def install_builtins(self) -> Dict[str, Any]:
        from app.kernel.registry.beast_builtin_plugins import manifests
        rows=[]
        for manifest in manifests(self):
            rows.append(self.install(manifest, approved=True, dry_run=False))
        return {"installed":sum(1 for row in rows if row.get("installed")),"results":rows}

    @staticmethod
    def tool_schema_hash(tool: Dict[str, Any]) -> str:
        pinned = {
            "name": tool.get("name"),
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema") or {},
        }
        encoded = json.dumps(pinned, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _validate_permissions(self, permissions: Dict[str, Any], risk: str) -> List[str]:
        errors = []
        for key in ("filesystem_read", "filesystem_write", "network_domains", "environment"):
            value = permissions.get(key, [])
            if not isinstance(value, list):
                errors.append(f"permissions.{key} must be a list")
                continue
            for item in value:
                text = str(item)
                if ".." in Path(text).parts:
                    errors.append(f"permissions.{key} may not contain parent traversal: {text}")
                if key in {"filesystem_read", "filesystem_write"} and Path(text).is_absolute():
                    errors.append(f"permissions.{key} must be workspace-relative: {text}")
                if key == "environment" and not re.fullmatch(r"[A-Z][A-Z0-9_]{1,79}", text):
                    errors.append(f"permissions.environment contains invalid variable name: {text}")
                if key == "network_domains" and not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]{1,5})?", text):
                    errors.append(f"permissions.network_domains must contain hostnames only: {text}")
        if permissions.get("network_domains") and risk == "low":
            errors.append("plugins with network access cannot use low risk_class")
        if permissions.get("subprocess") and risk not in {"high", "critical"}:
            errors.append("plugins with subprocess permission require high or critical risk_class")
        return errors

    @staticmethod
    def _validate_entrypoint(entrypoint: Dict[str, Any], permissions: Dict[str, Any], risk: str) -> List[str]:
        errors = []
        kind = entrypoint.get("kind")
        if kind == "mcp_stdio":
            if not str(entrypoint.get("command") or "").strip():
                errors.append("mcp_stdio entrypoint requires command")
            if permissions.get("subprocess") is not True:
                errors.append("mcp_stdio entrypoint requires permissions.subprocess=true")
            if risk not in {"high", "critical"}:
                errors.append("mcp_stdio entrypoint requires high or critical risk_class")
        elif kind == "python" and not str(entrypoint.get("module") or "").strip():
            errors.append("python entrypoint requires module")
        elif kind == "http":
            url = str(entrypoint.get("url") or "")
            if not re.match(r"^https?://", url):
                errors.append("http entrypoint requires an absolute http(s) url")
            if not permissions.get("network_domains"):
                errors.append("http entrypoint requires permissions.network_domains")
        return errors

    @staticmethod
    def _validate_budget(budget: Dict[str, Any]) -> List[str]:
        errors = []
        for key in ("max_tokens_per_call", "max_cost_usd_per_call", "max_latency_ms", "calls_per_hour"):
            if key not in budget:
                errors.append(f"budget.{key} is required")
                continue
            try:
                if float(budget[key]) < 0:
                    errors.append(f"budget.{key} must be non-negative")
            except (TypeError, ValueError):
                errors.append(f"budget.{key} must be numeric")
        return errors

    def _validate_approval_policy(self, policy: Dict[str, Any], permissions: Dict[str, Any], risk: str) -> List[str]:
        errors = []
        for key in ("install", "first_run", "network", "external_write", "filesystem_write"):
            if key not in policy or not isinstance(policy.get(key), bool):
                errors.append(f"approval_policy.{key} must be boolean")
        if policy.get("install") is not True:
            errors.append("BEAST host policy requires approval_policy.install=true")
        if risk in {"high", "critical"} and policy.get("install") is not True:
            errors.append("high and critical risk plugins require install approval")
        if risk in {"high", "critical"} and policy.get("first_run") is not True:
            errors.append("high and critical risk plugins require first-run approval")
        if permissions.get("network_domains") and policy.get("network") is not True:
            errors.append("network permission requires approval_policy.network=true")
        if self._has_write_permission(permissions) and policy.get("filesystem_write") is not True:
            errors.append("filesystem write permission requires approval_policy.filesystem_write=true")
        return errors

    @staticmethod
    def _has_write_permission(permissions: Dict[str, Any]) -> bool:
        return bool(permissions.get("filesystem_write"))

    @staticmethod
    def _permission_summary(permissions: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "filesystem_read_paths": len(permissions.get("filesystem_read") or []),
            "filesystem_write_paths": len(permissions.get("filesystem_write") or []),
            "network_domains": len(permissions.get("network_domains") or []),
            "environment_variables": len(permissions.get("environment") or []),
            "subprocess": bool(permissions.get("subprocess")),
        }
