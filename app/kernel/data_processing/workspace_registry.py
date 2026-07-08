"""Multi-repo workspace registry and advisory contract discovery.

The registry is deliberately JSON-backed for the first Workstream 9 slice. It
keeps the active edit repo explicit while allowing read-only context from other
registered repos.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.data_processing.code_indexers import SOURCE_SUFFIXES, extract_routes, language_for_path


OPENAPI_NAMES = {
    "openapi.json",
    "openapi.yaml",
    "openapi.yml",
    "swagger.json",
    "swagger.yaml",
    "swagger.yml",
}

ENV_PATTERNS = [
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    re.compile(r"os\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]+)['\"]\s*\]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]+)"),
    re.compile(r"\$\{([A-Z][A-Z0-9_]+)\}"),
]

TOPIC_PATTERN = re.compile(
    r"(?:topic|queue|subject|channel)\s*[:=]\s*['\"]([A-Za-z0-9_.:/-]{3,})['\"]",
    re.IGNORECASE,
)
CLI_PATTERN = re.compile(r"(?:argparse|click\.command|typer\.Typer|console_scripts)")


def repo_id_for_root(root: str | Path) -> str:
    return f"repo:{Path(root).expanduser().resolve()}"


def stable_registry_hash(payload: Any) -> str:
    data = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8", errors="replace")).hexdigest()


class WorkspaceRegistry:
    """JSON-backed registry for editable and read-only workspace roots."""

    def __init__(self, registry_path: str | Path):
        self.registry_path = Path(registry_path).expanduser().resolve()
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def for_anchor_root(cls, anchor_root: str | Path) -> "WorkspaceRegistry":
        return cls(Path(anchor_root).expanduser().resolve() / ".beast" / "workspaces.json")

    def load(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {
                "beast_object_type": "workspace_registry",
                "version": "1.0",
                "workspaces": {},
                "relationships": [],
                "updated_at": 0,
            }
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("beast_object_type", "workspace_registry")
        payload.setdefault("version", "1.0")
        payload.setdefault("workspaces", {})
        payload.setdefault("relationships", [])
        return payload

    def save(self, registry: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(registry)
        payload["updated_at"] = int(time.time())
        payload["registry_hash"] = stable_registry_hash({
            key: value for key, value in payload.items() if key != "registry_hash"
        })
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        return payload

    def register(
        self,
        root_path: str | Path,
        *,
        trust_level: str = "local",
        allowed_edit_scope: str = "read_write",
        role: str = "primary",
        graph_stats: Optional[Dict[str, Any]] = None,
        contract_scan: bool = True,
    ) -> Dict[str, Any]:
        root = Path(root_path).expanduser().resolve()
        repo_id = repo_id_for_root(root)
        registry = self.load()
        workspace = {
            "repo_id": repo_id,
            "root_path": str(root),
            "name": root.name,
            "role": role,
            "trust_level": trust_level,
            "allowed_edit_scope": allowed_edit_scope,
            "active_branch": self._git_value(root, ["rev-parse", "--abbrev-ref", "HEAD"]),
            "active_commit": self._git_value(root, ["rev-parse", "HEAD"]),
            "graph_stats": graph_stats or {},
            "contract_artifacts": self.detect_contracts(root) if contract_scan else {},
            "updated_at": int(time.time()),
        }
        registry.setdefault("workspaces", {})[repo_id] = workspace
        saved = self.save(registry)
        return {
            "beast_object_type": "workspace_registry_register_result",
            "registry_path": str(self.registry_path),
            "workspace": workspace,
            "registry": saved,
        }

    def list(self) -> Dict[str, Any]:
        registry = self.load()
        workspaces = list((registry.get("workspaces") or {}).values())
        return {
            "beast_object_type": "workspace_registry_list",
            "registry_path": str(self.registry_path),
            "workspaces": sorted(workspaces, key=lambda item: (str(item.get("role") or ""), str(item.get("root_path") or ""))),
            "relationships": registry.get("relationships") or [],
            "registry_hash": registry.get("registry_hash") or "",
        }

    def add_relationship(self, provider_repo_id: str, consumer_repo_id: str, relationship: str = "provides_context") -> Dict[str, Any]:
        registry = self.load()
        item = {
            "provider_repo_id": provider_repo_id,
            "consumer_repo_id": consumer_repo_id,
            "relationship": relationship,
            "created_at": int(time.time()),
        }
        relationships = registry.setdefault("relationships", [])
        if not any(
            existing.get("provider_repo_id") == provider_repo_id
            and existing.get("consumer_repo_id") == consumer_repo_id
            and existing.get("relationship") == relationship
            for existing in relationships
            if isinstance(existing, dict)
        ):
            relationships.append(item)
        saved = self.save(registry)
        return {"beast_object_type": "workspace_registry_relationship", "relationship": item, "registry": saved}

    def build_context_pack(
        self,
        *,
        edit_repo_id: str,
        reference_repo_ids: Optional[Iterable[str]] = None,
        files_by_repo: Optional[Dict[str, List[str]]] = None,
        max_chars_each: int = 4000,
    ) -> Dict[str, Any]:
        registry = self.load()
        workspaces = registry.get("workspaces") if isinstance(registry.get("workspaces"), dict) else {}
        if edit_repo_id not in workspaces:
            return {"beast_object_type": "multi_repo_context_pack", "ok": False, "error": f"unknown edit repo: {edit_repo_id}"}
        refs = list(reference_repo_ids or [])
        repo_ids = [edit_repo_id, *[repo_id for repo_id in refs if repo_id != edit_repo_id]]
        records: List[Dict[str, Any]] = []
        for repo_id in repo_ids:
            workspace = workspaces.get(repo_id)
            if not isinstance(workspace, dict):
                continue
            root = Path(str(workspace.get("root_path") or "")).expanduser().resolve()
            read_only = repo_id != edit_repo_id or str(workspace.get("allowed_edit_scope") or "") == "read_only"
            for rel in (files_by_repo or {}).get(repo_id, []):
                records.append(self._read_context_file(root, rel, repo_id=repo_id, read_only=read_only, max_chars=max_chars_each))
        return {
            "beast_object_type": "multi_repo_context_pack",
            "ok": True,
            "edit_repo_id": edit_repo_id,
            "reference_repo_ids": refs,
            "records": records,
            "read_only_count": sum(1 for item in records if item.get("read_only")),
            "editable_count": sum(1 for item in records if not item.get("read_only")),
            "write_policy": {
                "allowed_edit_repo_id": edit_repo_id,
                "cross_repo_edits_require_explicit_multi_repo_approval": True,
                "reference_repos_read_only": True,
            },
        }

    def detect_contracts(self, root_path: str | Path, *, max_files: int = 1000) -> Dict[str, Any]:
        root = Path(root_path).expanduser().resolve()
        contracts: Dict[str, Any] = {
            "beast_object_type": "workspace_contract_artifacts",
            "repo_id": repo_id_for_root(root),
            "routes": [],
            "openapi_files": [],
            "env_vars": [],
            "message_topics": [],
            "cli_commands": [],
        }
        env_vars = set()
        topics = set()
        scanned = 0
        for path in root.rglob("*"):
            if scanned >= max_files:
                break
            if not path.is_file() or any(part in {".git", ".beast", "__pycache__", "node_modules", ".venv", "venv"} for part in path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            lower_name = path.name.lower()
            if lower_name in OPENAPI_NAMES:
                contracts["openapi_files"].append({"path": rel, "kind": lower_name})
            if path.suffix.lower() not in SOURCE_SUFFIXES and lower_name not in OPENAPI_NAMES and path.suffix.lower() not in {".env", ".yaml", ".yml", ".toml", ".json"}:
                continue
            scanned += 1
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            language = language_for_path(path)
            for route in extract_routes(content, language, rel):
                contracts["routes"].append(route)
            for pattern in ENV_PATTERNS:
                env_vars.update(pattern.findall(content))
            topics.update(TOPIC_PATTERN.findall(content))
            if CLI_PATTERN.search(content) or path.name in {"cli.py", "manage.py"}:
                contracts["cli_commands"].append({"path": rel, "kind": "cli_surface"})
        contracts["env_vars"] = sorted(env_vars)
        contracts["message_topics"] = sorted(topics)
        contracts["counts"] = {
            "routes": len(contracts["routes"]),
            "openapi_files": len(contracts["openapi_files"]),
            "env_vars": len(contracts["env_vars"]),
            "message_topics": len(contracts["message_topics"]),
            "cli_commands": len(contracts["cli_commands"]),
        }
        contracts["contract_hash"] = stable_registry_hash(contracts)
        return contracts

    def contract_mismatch_receipt(self, provider_repo_id: str, consumer_repo_id: str) -> Dict[str, Any]:
        registry = self.load()
        workspaces = registry.get("workspaces") if isinstance(registry.get("workspaces"), dict) else {}
        provider = workspaces.get(provider_repo_id) if isinstance(workspaces.get(provider_repo_id), dict) else {}
        consumer = workspaces.get(consumer_repo_id) if isinstance(workspaces.get(consumer_repo_id), dict) else {}
        provider_contracts = provider.get("contract_artifacts") if isinstance(provider.get("contract_artifacts"), dict) else {}
        consumer_contracts = consumer.get("contract_artifacts") if isinstance(consumer.get("contract_artifacts"), dict) else {}
        provider_env = set(provider_contracts.get("env_vars") or [])
        consumer_env = set(consumer_contracts.get("env_vars") or [])
        provider_routes = {str(item.get("path") or "") for item in provider_contracts.get("routes") or [] if isinstance(item, dict)}
        consumer_routes = {str(item.get("path") or "") for item in consumer_contracts.get("routes") or [] if isinstance(item, dict)}
        receipt = {
            "beast_object_type": "workspace_contract_mismatch_receipt",
            "provider_repo_id": provider_repo_id,
            "consumer_repo_id": consumer_repo_id,
            "advisory": True,
            "missing_env_in_consumer": sorted(provider_env - consumer_env),
            "consumer_references_unknown_env": sorted(consumer_env - provider_env),
            "shared_routes": sorted(provider_routes & consumer_routes),
            "provider_only_routes": sorted(provider_routes - consumer_routes),
            "consumer_only_routes": sorted(consumer_routes - provider_routes),
            "created_at": int(time.time()),
        }
        receipt["receipt_hash"] = stable_registry_hash(receipt)
        return receipt

    def validate_sourceplan_scope(
        self,
        plan: Dict[str, Any],
        *,
        edit_repo_id: str,
        approved_multi_repo: bool = False,
    ) -> Dict[str, Any]:
        """Validate selected SourcePlan operations against registered repo scopes."""
        registry = self.load()
        workspaces = registry.get("workspaces") if isinstance(registry.get("workspaces"), dict) else {}
        if edit_repo_id not in workspaces:
            return {
                "beast_object_type": "workspace_sourceplan_scope_validation",
                "ok": False,
                "errors": [f"unknown edit repo: {edit_repo_id}"],
                "approved_multi_repo": approved_multi_repo,
            }
        errors: List[str] = []
        warnings: List[str] = []
        writable_repo_ids = set()
        operations = plan.get("operations") if isinstance(plan.get("operations"), list) else []
        for index, op in enumerate(operations, start=1):
            if not isinstance(op, dict) or op.get("selected", True) is False:
                continue
            op_id = str(op.get("op_id") or f"op_{index:03d}")
            repo_id = str(op.get("repo_id") or edit_repo_id)
            source_edit = bool(op.get("source_edit", not str(op.get("path") or "").startswith(".beast/")))
            workspace = workspaces.get(repo_id) if isinstance(workspaces.get(repo_id), dict) else None
            if workspace is None:
                errors.append(f"{op_id}: unknown repo_id {repo_id}")
                continue
            scope = str(workspace.get("allowed_edit_scope") or "read_write")
            if source_edit:
                writable_repo_ids.add(repo_id)
                if scope == "read_only":
                    errors.append(f"{op_id}: repo {repo_id} is read_only")
                if repo_id != edit_repo_id and not approved_multi_repo:
                    errors.append(f"{op_id}: cross-repo edit requires explicit multi-repo approval")
            elif repo_id != edit_repo_id:
                warnings.append(f"{op_id}: read-only reference operation from {repo_id}")
        if len(writable_repo_ids) > 1 and not approved_multi_repo:
            errors.append("multiple writable repos require explicit multi-repo approval")
        return {
            "beast_object_type": "workspace_sourceplan_scope_validation",
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "edit_repo_id": edit_repo_id,
            "approved_multi_repo": approved_multi_repo,
            "writable_repo_ids": sorted(writable_repo_ids),
            "registered_repo_count": len(workspaces),
        }

    def _read_context_file(self, root: Path, rel: str, *, repo_id: str, read_only: bool, max_chars: int) -> Dict[str, Any]:
        try:
            target = (root / rel).resolve()
            if root != target and root not in target.parents:
                raise ValueError("path escaped workspace")
            content = target.read_text(encoding="utf-8", errors="replace")
            return {
                "repo_id": repo_id,
                "root_path": str(root),
                "path": rel,
                "ok": True,
                "read_only": read_only,
                "content": content[: max(1, int(max_chars))],
                "truncated": len(content) > max(1, int(max_chars)),
                "sha256": hashlib.sha256(content.encode("utf-8", errors="replace")).hexdigest(),
            }
        except Exception as exc:
            return {"repo_id": repo_id, "root_path": str(root), "path": rel, "ok": False, "read_only": read_only, "error": str(exc)}

    @staticmethod
    def _git_value(root: Path, args: List[str]) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), *args],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=0.7,
                check=False,
            )
            if proc.returncode == 0:
                return proc.stdout.strip()
        except Exception:
            pass
        return ""
