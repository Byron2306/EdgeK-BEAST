"""Safety Governor for command and bootstrap risk receipts."""

from __future__ import annotations

import json
import hashlib
import re
import shlex
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.kernel.policy.policy_gate import from_safety_receipt


HIGH_RISK_PATTERNS = [
    ("network_shell_pipe", re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|zsh|python|perl)\b", re.I), "block"),
    ("destructive_remove", re.compile(r"\brm\s+(-[^\s]*r[^\s]*f|-rf|-fr)\b", re.I), "block"),
    ("raw_disk_write", re.compile(r"\bdd\b.*\bof=/dev/", re.I), "block"),
    ("privilege_escalation", re.compile(r"\b(sudo|su)\b", re.I), "require_approval"),
    ("recursive_permission_change", re.compile(r"\b(chmod|chown)\s+-R\b", re.I), "require_approval"),
    ("decode_execute", re.compile(r"\bbase64\b.*\|\s*(bash|sh|python|perl)\b", re.I), "block"),
    ("repo_binary_execution", re.compile(r"(^|\s)(\./|scripts/|bin/)[^\s]+", re.I), "warn"),
    ("network_download", re.compile(r"\b(curl|wget|Invoke-WebRequest)\b", re.I), "require_approval"),
    ("package_install", re.compile(r"\b(npm|pnpm|yarn|pip|uv|poetry|cargo|go)\b\s+(install|add|get|update)\b", re.I), "require_approval"),
]

BOOTSTRAP_FILES = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}

SCRIPT_SUFFIXES = {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}

LIFECYCLE_KEYS = {
    "preinstall",
    "install",
    "postinstall",
    "prepare",
    "prepack",
    "postpack",
}

DECISION_ORDER = ["allow", "warn", "require_approval", "sandbox/worktree_only", "block"]


def _max_decision(values: List[str]) -> str:
    if not values:
        return "allow"
    return max(values, key=lambda item: DECISION_ORDER.index(item) if item in DECISION_ORDER else 0)


class SafetyGovernor:
    """Classify commands and workspace bootstrap files before execution."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.store_dir = self.workspace_root / ".beast" / "evidence" / "safety"

    def classify_command(self, command: str, *, mode: str = "", task_id: str = "", operator_override: str = "", record: bool = True) -> Dict[str, Any]:
        command = str(command or "").strip()
        reasons: List[Dict[str, Any]] = []
        decisions: List[str] = []
        for name, pattern, decision in HIGH_RISK_PATTERNS:
            if pattern.search(command):
                reasons.append({"kind": name, "decision": decision, "detail": self._detail_for(name)})
                decisions.append(decision)
        if self._unknown_repo_binary(command):
            reasons.append({"kind": "unknown_repo_binary", "decision": "require_approval", "detail": "command executes a local repo binary or script"})
            decisions.append("require_approval")
        if mode in {"scout", "architect", "reviewer"} and self._looks_mutating(command):
            reasons.append({"kind": "mode_mutation_conflict", "decision": "sandbox/worktree_only", "detail": f"{mode} mode should not execute mutating commands"})
            decisions.append("sandbox/worktree_only")
        decision = _max_decision(decisions)
        if operator_override and decision in {"warn", "require_approval", "sandbox/worktree_only"}:
            reasons.append({"kind": "operator_override", "decision": "allow", "detail": operator_override[:300]})
        receipt = {
            "beast_object_type": "beast_safety_command_receipt",
            "version": "1.0",
            "command": command,
            "mode": mode,
            "task_id": task_id,
            "decision": decision,
            "risk_level": self._risk_level(decision),
            "reasons": reasons,
            "operator_override": operator_override,
            "timestamp": time.time(),
        }
        receipt["policy_gate"] = from_safety_receipt(receipt)
        if record:
            self._persist_and_register(receipt)
        return receipt

    def scan_workspace(self, *, files: Optional[List[str]] = None, max_files: int = 250) -> Dict[str, Any]:
        target_files = self._target_files(files, max_files=max_files)
        findings: List[Dict[str, Any]] = []
        for path in target_files:
            findings.extend(self._scan_file(path))
        decision = _max_decision([finding.get("decision", "allow") for finding in findings])
        receipt = {
            "beast_object_type": "beast_safety_workspace_receipt",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "decision": decision,
            "risk_level": self._risk_level(decision),
            "finding_count": len(findings),
            "findings": findings[:100],
            "scanned_files": [path.relative_to(self.workspace_root).as_posix() for path in target_files if path.exists()][:max_files],
            "timestamp": time.time(),
        }
        receipt["policy_gate"] = from_safety_receipt(receipt)
        self._persist_and_register(receipt)
        return receipt

    def _target_files(self, files: Optional[List[str]], *, max_files: int) -> List[Path]:
        if files:
            out: List[Path] = []
            for rel in files[:max_files]:
                try:
                    path = (self.workspace_root / str(rel)).resolve()
                    if path == self.workspace_root or self.workspace_root not in path.parents:
                        continue
                    if path.is_file():
                        out.append(path)
                except Exception:
                    continue
            return out
        candidates: List[Path] = []
        for path in self.workspace_root.rglob("*"):
            try:
                rel_parts = path.relative_to(self.workspace_root).parts
                if any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in rel_parts):
                    continue
                if not path.is_file():
                    continue
                if path.name in BOOTSTRAP_FILES or path.suffix in SCRIPT_SUFFIXES or ".github/workflows" in path.as_posix():
                    candidates.append(path)
                if len(candidates) >= max_files:
                    break
            except Exception:
                continue
        return candidates

    def _scan_file(self, path: Path) -> List[Dict[str, Any]]:
        try:
            rel = path.relative_to(self.workspace_root).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []
        findings: List[Dict[str, Any]] = []
        if path.name == "package.json":
            findings.extend(self._scan_package_json(rel, text))
        for name, pattern, decision in HIGH_RISK_PATTERNS:
            if pattern.search(text):
                findings.append({"file": rel, "kind": name, "decision": decision, "detail": self._detail_for(name)})
        if path.suffix in SCRIPT_SUFFIXES and any(term in text.lower() for term in ("curl", "wget", "sudo", "rm -rf", "chmod -r")):
            findings.append({"file": rel, "kind": "risky_shell_script", "decision": "require_approval", "detail": "script contains setup or destructive command markers"})
        return findings

    def _scan_package_json(self, rel: str, text: str) -> List[Dict[str, Any]]:
        findings: List[Dict[str, Any]] = []
        try:
            payload = json.loads(text)
        except Exception:
            return findings
        scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
        for key, value in scripts.items():
            command = str(value or "")
            if key in LIFECYCLE_KEYS:
                findings.append({"file": rel, "kind": "package_lifecycle_hook", "script": key, "decision": "require_approval", "detail": command[:300]})
            classified = self.classify_command(command, record=False)
            if classified.get("decision") != "allow":
                findings.append({"file": rel, "kind": "risky_package_script", "script": key, "decision": classified.get("decision"), "detail": command[:300], "reasons": classified.get("reasons")})
        return findings

    def _unknown_repo_binary(self, command: str) -> bool:
        try:
            parts = shlex.split(command)
        except Exception:
            parts = command.split()
        if not parts:
            return False
        first = parts[0]
        if first.startswith("./") or first.startswith("scripts/") or first.startswith("bin/"):
            candidate = (self.workspace_root / first).resolve()
            return candidate.exists() and candidate.is_file()
        return False

    def _looks_mutating(self, command: str) -> bool:
        lowered = command.lower()
        return any(term in lowered for term in (" install", " add ", " apply", " write", " rm ", " mv ", " cp ", "chmod", "chown", "docker run"))

    def _risk_level(self, decision: str) -> str:
        if decision == "block":
            return "critical"
        if decision in {"require_approval", "sandbox/worktree_only"}:
            return "high"
        if decision == "warn":
            return "medium"
        return "low"

    def _detail_for(self, kind: str) -> str:
        return {
            "network_shell_pipe": "downloaded content is piped directly to an interpreter",
            "destructive_remove": "recursive forced removal can destroy workspace or system files",
            "raw_disk_write": "raw disk writes can damage host state",
            "privilege_escalation": "command requests elevated privileges",
            "recursive_permission_change": "recursive ownership or permission changes can damage workspace security",
            "decode_execute": "decoded content is executed without inspection",
            "repo_binary_execution": "local repo executable should be inspected before execution",
            "network_download": "command downloads remote content",
            "package_install": "package installation may run hooks or modify dependency state",
        }.get(kind, "risk marker detected")

    def _persist_and_register(self, receipt: Dict[str, Any]) -> None:
        try:
            body = json.dumps(receipt, sort_keys=True, default=str)
            receipt_id = "safe_" + hashlib.sha256(body.encode("utf-8", errors="replace")).hexdigest()[:18]
            receipt["receipt_id"] = receipt_id
            path = self.store_dir / f"{receipt_id}.json"
            self.store_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            from app.kernel.evidence.evidence_bus import EvidenceBus

            receipt["evidence_bus"] = EvidenceBus(self.workspace_root).register_safety_receipt(receipt, receipt_path=path)
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        except Exception:
            pass
