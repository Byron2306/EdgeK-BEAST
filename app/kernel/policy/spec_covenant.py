"""Spec Covenant compiler for scoped project instructions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.kernel.policy.policy_gate import from_spec_covenant


RULE_SOURCE_PATTERNS = [
    "AGENTS.md",
    "BEAST_PROJECT.md",
    ".beast/rules/*.md",
    ".beast/rules/*.yaml",
    ".beast/rules/*.yml",
]

UNSAFE_RULE_MARKERS = [
    "curl | bash",
    "curl -fs",
    "wget",
    "sudo",
    "chmod -r",
    "chown -r",
    "rm -rf",
    "postinstall",
    "preinstall",
    "disable safety",
    "ignore tests",
    "ignore approval",
]

IMPOSSIBLE_PAIRS = [
    ("never run tests", "always run tests"),
    ("do not edit", "must edit"),
    ("readonly", "write files"),
    ("no network", "curl"),
]


@dataclass(frozen=True)
class RuleRecord:
    source: str
    line: int
    text: str
    tags: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "line": self.line,
            "text": self.text,
            "tags": list(self.tags),
        }


def _safe_join(root: Path, rel: str) -> Path:
    candidate = (root / rel).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError(f"path escaped workspace: {rel}")
    return candidate


def _tokens(*values: str) -> set[str]:
    text = " ".join(str(value or "").lower() for value in values)
    return {token for token in re.findall(r"[a-zA-Z0-9_./-]{3,}", text) if token}


def _digest(payload: Dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


class SpecCovenantCompiler:
    """Load, lint, prune, and digest task-scoped project rules."""

    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).expanduser().resolve()

    def compile(
        self,
        *,
        objective: str,
        files: Optional[List[str]] = None,
        mode: str = "",
        operator_notes: str = "",
        max_rules: int = 18,
    ) -> Dict[str, Any]:
        files = [str(item) for item in (files or []) if str(item or "").strip()]
        all_rules = self.load_rules(operator_notes=operator_notes)
        lint = self.lint(all_rules, files=files, mode=mode)
        selected, pruned = self._scope_rules(all_rules, objective=objective, files=files, max_rules=max_rules)
        digest_payload = {
            "objective": objective,
            "files": files,
            "mode": mode,
            "rules": [rule.to_dict() for rule in selected],
            "lint": lint,
        }
        covenant_hash = _digest(digest_payload)
        covenant = {
            "beast_object_type": "beast_spec_covenant",
            "version": "1.0",
            "workspace_root": str(self.workspace_root),
            "objective": objective,
            "files": files,
            "mode": mode,
            "covenant_hash": covenant_hash,
            "included_count": len(selected),
            "pruned_count": len(pruned),
            "rules_included": [rule.to_dict() for rule in selected],
            "rules_pruned": [rule.to_dict() for rule in pruned[:50]],
            "lint": lint,
            "receipt": {
                "beast_object_type": "beast_spec_covenant_receipt",
                "version": "1.0",
                "covenant_hash": covenant_hash,
                "source_count": len({rule.source for rule in all_rules}),
                "rule_count": len(all_rules),
                "included_count": len(selected),
                "timestamp": time.time(),
            },
        }
        covenant["policy_gate"] = from_spec_covenant(covenant)
        self._persist_and_register(covenant)
        return covenant

    def load_rules(self, *, operator_notes: str = "") -> List[RuleRecord]:
        rules: List[RuleRecord] = []
        for pattern in RULE_SOURCE_PATTERNS:
            for path in sorted(self.workspace_root.glob(pattern)):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.workspace_root).as_posix()
                    rules.extend(self._parse_file(path, rel))
                except Exception:
                    continue
        if operator_notes.strip():
            for line_no, text in enumerate(operator_notes.splitlines(), 1):
                normalized = self._normalize_rule(text)
                if normalized:
                    rules.append(RuleRecord("operator_notes", line_no, normalized, ["operator"]))
        return rules

    def lint(self, rules: List[RuleRecord], *, files: List[str], mode: str = "") -> Dict[str, Any]:
        seen: Dict[str, RuleRecord] = {}
        duplicate_rules: List[Dict[str, Any]] = []
        unsafe_rules: List[Dict[str, Any]] = []
        stale_references: List[Dict[str, Any]] = []
        mode_conflicts: List[Dict[str, Any]] = []
        conflict_pairs: List[Dict[str, Any]] = []
        all_text = "\n".join(rule.text.lower() for rule in rules)
        for rule in rules:
            key = re.sub(r"\s+", " ", rule.text.strip().lower())
            if key in seen:
                duplicate_rules.append({"first": seen[key].to_dict(), "duplicate": rule.to_dict()})
            else:
                seen[key] = rule
            lowered = rule.text.lower()
            if any(marker in lowered for marker in UNSAFE_RULE_MARKERS):
                unsafe_rules.append(rule.to_dict())
            if mode in {"scout", "architect", "reviewer"} and any(term in lowered for term in ("write file", "apply patch", "run install", "execute setup")):
                mode_conflicts.append(rule.to_dict())
            for ref in re.findall(r"`([^`]+\.(?:py|js|ts|tsx|json|md|toml|yaml|yml|sh))`", rule.text):
                try:
                    if not _safe_join(self.workspace_root, ref).exists():
                        stale_references.append({"source": rule.source, "line": rule.line, "path": ref})
                except Exception:
                    stale_references.append({"source": rule.source, "line": rule.line, "path": ref})
        for left, right in IMPOSSIBLE_PAIRS:
            if left in all_text and right in all_text:
                conflict_pairs.append({"left": left, "right": right})
        severity = "ok"
        if unsafe_rules or mode_conflicts or conflict_pairs:
            severity = "warn"
        return {
            "severity": severity,
            "duplicate_rules": duplicate_rules[:20],
            "unsafe_rules": unsafe_rules[:20],
            "stale_references": stale_references[:20],
            "mode_conflicts": mode_conflicts[:20],
            "conflict_pairs": conflict_pairs,
            "related_files": files,
        }

    def spec_to_sourceplan_batches(self, covenant: Dict[str, Any], *, batch_size: int = 5) -> Dict[str, Any]:
        files = [str(item) for item in covenant.get("files") or []]
        batches: List[Dict[str, Any]] = []
        for index in range(0, len(files), max(1, batch_size)):
            chunk = files[index : index + max(1, batch_size)]
            batches.append({
                "batch_id": f"batch_{len(batches) + 1:03d}",
                "files": chunk,
                "covenant_hash": covenant.get("covenant_hash"),
                "status": "planned",
            })
        return {
            "beast_object_type": "beast_spec_sourceplan_batches",
            "version": "1.0",
            "covenant_hash": covenant.get("covenant_hash"),
            "batch_count": len(batches),
            "batches": batches,
        }

    def _parse_file(self, path: Path, rel: str) -> List[RuleRecord]:
        text = path.read_text(encoding="utf-8", errors="replace")
        records: List[RuleRecord] = []
        for line_no, raw in enumerate(text.splitlines(), 1):
            normalized = self._normalize_rule(raw)
            if not normalized:
                continue
            tags = self._tags_for(normalized, rel)
            records.append(RuleRecord(rel, line_no, normalized, tags))
        return records

    def _normalize_rule(self, text: str) -> str:
        stripped = str(text or "").strip()
        stripped = re.sub(r"^[-*]\s+", "", stripped)
        stripped = re.sub(r"^#+\s*", "", stripped)
        if len(stripped) < 8:
            return ""
        if set(stripped) <= {"-", "=", "_"}:
            return ""
        return stripped[:600]

    def _tags_for(self, text: str, source: str) -> List[str]:
        lowered = f"{source} {text}".lower()
        tags: List[str] = []
        for tag, terms in {
            "testing": ["test", "pytest", "verification"],
            "style": ["style", "format", "lint"],
            "security": ["secret", "token", "credential", "safety", "sudo", "curl"],
            "sourceplan": ["sourceplan", "patch", "diff", "apply"],
            "docs": ["docs", "markdown", "readme"],
        }.items():
            if any(term in lowered for term in terms):
                tags.append(tag)
        return tags or ["general"]

    def _scope_rules(self, rules: List[RuleRecord], *, objective: str, files: List[str], max_rules: int) -> tuple[List[RuleRecord], List[RuleRecord]]:
        wanted = _tokens(objective, *files)
        scored: List[tuple[int, int, RuleRecord]] = []
        for idx, rule in enumerate(rules):
            rule_tokens = _tokens(rule.text, rule.source)
            score = len(wanted & rule_tokens)
            if "general" in rule.tags:
                score += 1
            if any(tag in rule.tags for tag in ("security", "testing", "sourceplan")):
                score += 2
            scored.append((score, -idx, rule))
        scored.sort(reverse=True, key=lambda item: (item[0], item[1]))
        selected = [rule for score, _idx, rule in scored if score > 0][:max_rules]
        if not selected and rules:
            selected = [rule for _score, _idx, rule in scored[: min(max_rules, 5)]]
        selected_ids = {(rule.source, rule.line, rule.text) for rule in selected}
        pruned = [rule for _score, _idx, rule in scored if (rule.source, rule.line, rule.text) not in selected_ids]
        return selected, pruned

    def _persist_and_register(self, covenant: Dict[str, Any]) -> None:
        try:
            suffix = str(covenant.get("covenant_hash") or "unknown").split(":", 1)[-1][:24] or "unknown"
            store_dir = self.workspace_root / ".beast" / "evidence" / "spec_covenant"
            path = store_dir / f"{suffix}.json"
            store_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(covenant, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
            from app.kernel.evidence.evidence_bus import EvidenceBus

            covenant["evidence_bus"] = EvidenceBus(self.workspace_root).register_spec_covenant(covenant, covenant_path=path)
            path.write_text(json.dumps(covenant, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        except Exception:
            pass
