"""Incremental Fingerprinting for Compute Forge Nodes.

Uses git diff + mtime to only re-hash changed files instead of rebuilding
the entire repository fingerprint on every watch cycle.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.kernel.capability.capability_impact import CapabilityImpactFingerprint


@dataclass
class IncrementalFingerprintState:
    """Persisted state for incremental fingerprinting."""
    last_commit: str = ""
    last_mtimes: Dict[str, float] = field(default_factory=dict)  # path -> mtime
    last_fingerprint_hash: str = ""


class IncrementalFingerprintEngine:
    """CPU-first incremental fingerprint engine using git + mtime."""

    def __init__(self, repo_root: Path, state_file: Optional[Path] = None):
        self.repo_root = repo_root.resolve()
        self.impact = CapabilityImpactFingerprint()
        if state_file is None:
            state_file = self.repo_root / "data" / "fingerprint_state.json"
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> IncrementalFingerprintState:
        if self.state_file.exists():
            try:
                data = json.loads(self.state_file.read_text())
                return IncrementalFingerprintState(**data)
            except Exception:
                pass
        return IncrementalFingerprintState()

    def _save_state(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({
            "last_commit": self.state.last_commit,
            "last_mtimes": self.state.last_mtimes,
            "last_fingerprint_hash": self.state.last_fingerprint_hash,
        }, indent=2, sort_keys=True))

    def _get_current_commit(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout.strip()
        except Exception:
            return ""

    def _get_changed_files(self) -> Set[str]:
        """Return tracked working-tree changes since the recorded commit."""
        if not self.state.last_commit:
            # First run: treat everything as changed
            return set()
        
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", self.state.last_commit, "--"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return {line.strip() for line in result.stdout.splitlines() if line.strip()}
        except Exception:
            return set()

    def _get_mtime_changed_files(self, target_paths: List[str]) -> Set[str]:
        """Return files whose mtime changed since last recorded mtime."""
        changed = set()
        for rel in target_paths:
            path = self.repo_root / rel
            if not path.exists():
                if rel in self.state.last_mtimes:
                    changed.add(rel)
                    self.state.last_mtimes.pop(rel, None)
                continue
            current_mtime = path.stat().st_mtime
            last_mtime = self.state.last_mtimes.get(rel, 0.0)
            if current_mtime > last_mtime:
                changed.add(rel)
                self.state.last_mtimes[rel] = current_mtime
        return changed

    def build_incremental(
        self,
        target_paths: List[str],
        dependency_paths: List[str] = None,
        test_paths: List[str] = None,
        symbols: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Build fingerprint only for changed files (git + mtime)."""
        current_commit = self._get_current_commit()
        
        # Git-level changes
        git_changed = self._get_changed_files()
        
        all_paths = list(dict.fromkeys(target_paths + (dependency_paths or []) + (test_paths or [])))

        # Mtime-level changes include every input that contributes to validity.
        mtime_changed = self._get_mtime_changed_files(all_paths)
        
        all_changed = git_changed | mtime_changed
        
        # If nothing changed and we have a previous fingerprint, return it
        if all_changed or not self.state.last_fingerprint_hash:
            # Need to rebuild (or first run)
            fingerprint = self.impact.build(
                self.repo_root,
                target_paths=target_paths,
                dependency_paths=dependency_paths or [],
                test_paths=test_paths or [],
                symbols=symbols or {},
            )
            self.state.last_commit = current_commit
            self.state.last_fingerprint_hash = fingerprint.get("fingerprint_hash", "")
            for rel in all_paths:
                path = self.repo_root / rel
                if path.exists():
                    self.state.last_mtimes[rel] = path.stat().st_mtime
            self._save_state()
            return fingerprint
        
        # No changes — return cached hash with a note
        return {
            "beast_object_type": "incremental_fingerprint_unchanged",
            "version": "1.0",
            "fingerprint_hash": self.state.last_fingerprint_hash,
            "changed_files": list(all_changed),
            "note": "No changes detected; returning cached fingerprint hash",
            "last_commit": self.state.last_commit,
        }

    def force_rebuild(
        self,
        target_paths: List[str],
        dependency_paths: List[str] = None,
        test_paths: List[str] = None,
        symbols: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """Force a full rebuild and update state."""
        fingerprint = self.impact.build(
            self.repo_root,
            target_paths=target_paths,
            dependency_paths=dependency_paths or [],
            test_paths=test_paths or [],
            symbols=symbols or {},
        )
        self.state.last_commit = self._get_current_commit()
        self.state.last_fingerprint_hash = fingerprint.get("fingerprint_hash", "")
        # Update all mtimes
        for rel in list(dict.fromkeys(target_paths + (dependency_paths or []) + (test_paths or []))):
            path = self.repo_root / rel
            if path.exists():
                self.state.last_mtimes[rel] = path.stat().st_mtime
        self._save_state()
        return fingerprint
