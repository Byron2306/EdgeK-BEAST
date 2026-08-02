"""Fail-closed Crystal IR edit transaction.

This is the narrow bridge from a verified interpretation to one bounded edit.
It deliberately does not grant the model execution authority: the caller must
provide explicit approval, an isolated worktree, and verifier commands.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.kernel.compute.crystal_ir import CrystalIR, compile_crystal_ir


_PLACEHOLDER = re.compile(r"(?i)(?:complete replacement source|replacement code here|insert code|your code|example implementation|\bTODO\b|rest of (?:the )?(?:file|function|code))")
_ALLOWED_VERIFIERS = {"python", "python3", "pytest", "node", "npm", "ruff"}


@dataclass(frozen=True)
class CrystalExecutionRequest:
    crystal_ir: CrystalIR | Mapping[str, Any]
    old: str
    new: str
    approval_id: str
    worktree_task_id: str
    worktree_root: str
    verification_commands: tuple[tuple[str, ...], ...]
    expected_file_sha256: str = ""


@dataclass(frozen=True)
class GroundedCrystalTarget:
    path: str
    symbol: str
    old: str
    file_sha256: str


def ground_crystal_ir(crystal_ir: CrystalIR | Mapping[str, Any], worktree_root: str) -> GroundedCrystalTarget:
    """Resolve one IR target to its exact current source span without editing."""
    ir = crystal_ir if isinstance(crystal_ir, CrystalIR) else compile_crystal_ir(crystal_ir)
    root = Path(worktree_root).resolve()
    path = CrystalExecutionEngine._safe_path(root, ir.target_file)
    source = path.read_text(encoding="utf-8")
    if path.suffix != ".py":
        raise CrystalExecutionError("repository grounding currently requires a Python target")
    tree = ast.parse(source, filename=str(path))
    target = next((node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == ir.target_symbol), None)
    if target is None or target.end_lineno is None:
        raise CrystalExecutionError(f"target symbol not found: {ir.target_symbol}")
    lines = source.splitlines(keepends=True)
    old = "".join(lines[target.lineno - 1:target.end_lineno])
    return GroundedCrystalTarget(ir.target_file, ir.target_symbol, old, CrystalExecutionEngine._digest_bytes(source.encode("utf-8")))


class CrystalExecutionError(ValueError):
    pass


class CrystalExecutionEngine:
    """Apply one exact edit, verify it, and restore the preimage on failure."""

    def execute(self, request: CrystalExecutionRequest) -> dict[str, Any]:
        ir = request.crystal_ir if isinstance(request.crystal_ir, CrystalIR) else compile_crystal_ir(request.crystal_ir)
        self._check_authority(request, ir)
        root = Path(request.worktree_root).resolve()
        path = self._safe_path(root, ir.target_file)
        before = path.read_bytes()
        before_digest = self._digest_bytes(before)
        if request.expected_file_sha256 and request.expected_file_sha256 != before_digest:
            raise CrystalExecutionError("target file fingerprint changed before execution")
        old = request.old
        new = request.new
        if not old or not new or _PLACEHOLDER.search(new):
            raise CrystalExecutionError("edit requires non-empty concrete source without placeholders")
        text = before.decode("utf-8", errors="strict")
        if text.count(old) != 1:
            raise CrystalExecutionError(f"exact edit expected one old snippet, found {text.count(old)}")
        candidate = text.replace(old, new, 1)
        self._syntax_preflight(path, candidate)
        self._symbol_preflight(path, text, ir.target_symbol)
        path.write_text(candidate, encoding="utf-8")
        after_digest = self._digest_bytes(path.read_bytes())
        checks = self._run_verifiers(root, request.verification_commands)
        passed = all(item["ok"] for item in checks)
        rolled_back = False
        if not passed:
            path.write_bytes(before)
            rolled_back = True
        receipt = {
            "beast_object_type": "crystal_execution_receipt",
            "version": "1.0",
            "status": "verified" if passed else "rolled_back",
            "crystal_ir_digest": ir.digest(),
            "approval_id": request.approval_id,
            "worktree_task_id": request.worktree_task_id,
            "path": ir.target_file,
            "before_sha256": before_digest,
            "after_sha256": after_digest,
            "mutation_performed": True,
            "rollback_performed": rolled_back,
            "verification": checks,
            "authority": {"execute": False, "authorize": False, "model_authority": ir.model_authority},
        }
        receipt["receipt_digest"] = self._digest_json(receipt)
        if not passed:
            raise CrystalExecutionError(json.dumps(receipt, sort_keys=True))
        return receipt

    @staticmethod
    def _check_authority(request: CrystalExecutionRequest, ir: CrystalIR) -> None:
        if not request.approval_id:
            raise CrystalExecutionError("explicit approval is required")
        if not request.worktree_task_id or not request.worktree_root:
            raise CrystalExecutionError("isolated worktree binding is required")
        if ir.network_allowed:
            raise CrystalExecutionError("network-enabled Crystal IR is not executable in this lane")
        if ir.tests_mutable:
            raise CrystalExecutionError("tests_mutable Crystal IR is not executable in this lane")
        if not ir.rollback_required:
            raise CrystalExecutionError("rollback is required for Crystal execution")
        if ir.maximum_effects != 1 or len(ir.writable_files) != 1:
            raise CrystalExecutionError("execution lane requires exactly one file and one effect")
        if not request.verification_commands:
            raise CrystalExecutionError("at least one verifier command is required")

    @staticmethod
    def _safe_path(root: Path, relative: str) -> Path:
        path = (root / relative).resolve()
        if path != root and root not in path.parents:
            raise CrystalExecutionError("target path escaped worktree")
        if not path.is_file():
            raise CrystalExecutionError("target file does not exist")
        return path

    @staticmethod
    def _syntax_preflight(path: Path, candidate: str) -> None:
        if path.suffix == ".py":
            try:
                ast.parse(candidate, filename=str(path))
            except SyntaxError as exc:
                raise CrystalExecutionError(f"syntax preflight failed: {exc}") from exc

    @staticmethod
    def _symbol_preflight(path: Path, source: str, symbol: str) -> None:
        if path.suffix != ".py" or not symbol:
            return
        tree = ast.parse(source, filename=str(path))
        names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        if symbol not in names:
            raise CrystalExecutionError(f"target symbol not found: {symbol}")

    @staticmethod
    def _run_verifiers(root: Path, commands: Sequence[Sequence[str]]) -> list[dict[str, Any]]:
        results = []
        project_root = Path(__file__).resolve().parents[3]
        for raw in commands:
            command = tuple(str(item) for item in raw)
            if not command or command[0] not in _ALLOWED_VERIFIERS:
                raise CrystalExecutionError("verifier command is not in the local allowlist")
            argv = list(command)
            if argv[0] in {"python", "python3"}:
                argv[0] = sys.executable
            try:
                verifier_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
                verifier_env["PYTHONPATH"] = str(root) + os.pathsep + str(project_root) + (os.pathsep + verifier_env["PYTHONPATH"] if verifier_env.get("PYTHONPATH") else "")
                completed = subprocess.run(
                    argv,
                    cwd=root,
                    env=verifier_env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                result = {"command": list(command), "ok": completed.returncode == 0, "returncode": completed.returncode, "stdout": completed.stdout[-12000:], "stderr": completed.stderr[-12000:]}
            except subprocess.TimeoutExpired as exc:
                result = {"command": list(command), "ok": False, "returncode": None, "stdout": str(exc.stdout or "")[-12000:], "stderr": "verification timeout"}
            except OSError as exc:
                result = {"command": list(command), "ok": False, "returncode": None, "stdout": "", "stderr": str(exc)}
            results.append(result)
            if not result["ok"]:
                break
        return results

    @staticmethod
    def _digest_bytes(value: bytes) -> str:
        return "sha256:" + hashlib.sha256(value).hexdigest()

    @staticmethod
    def _digest_json(value: Mapping[str, Any]) -> str:
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
