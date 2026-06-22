"""Repository impact fingerprints for deterministic capability validity."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


class CapabilityImpactFingerprint:
    """Detect whether repository drift invalidates a promoted capability."""

    def build(
        self,
        root: Path,
        *,
        target_paths: Iterable[str],
        dependency_paths: Iterable[str] = (),
        test_paths: Iterable[str] = (),
        symbols: Optional[Mapping[str, Iterable[str]]] = None,
        tool_schema_hashes: Iterable[str] = (),
        policy_version: str = "unknown",
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        root = root.resolve()
        payload = {
            "beast_object_type": "capability_impact_fingerprint",
            "version": "1.0",
            "targets": self._path_group(root, target_paths, symbols or {}),
            "dependencies": self._path_group(root, dependency_paths, symbols or {}),
            "tests": self._path_group(root, test_paths, {}),
            "tool_schema_hashes": sorted({str(item) for item in tool_schema_hashes if str(item)}),
            "policy_version": str(policy_version),
            "confidence": min(1.0, max(0.0, float(confidence))),
            "safety_policy": "any_material_ast_or_contract_change_requires_shadow_revalidation",
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        payload["fingerprint_hash"] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        return payload

    def compare(self, previous: Dict[str, Any], current: Dict[str, Any]) -> Dict[str, Any]:
        reasons = []
        critical = []
        nonsemantic = []
        for group in ("targets", "dependencies", "tests"):
            old_group = previous.get(group) if isinstance(previous.get(group), dict) else {}
            new_group = current.get(group) if isinstance(current.get(group), dict) else {}
            for path in sorted(set(old_group) | set(new_group)):
                old = old_group.get(path)
                new = new_group.get(path)
                if not old or not new or not old.get("exists") or not new.get("exists"):
                    critical.append(f"{group}:{path}:missing_or_added")
                    continue
                if old.get("semantic_hash") != new.get("semantic_hash"):
                    critical.append(f"{group}:{path}:semantic_change")
                elif old.get("file_hash") != new.get("file_hash"):
                    nonsemantic.append(f"{group}:{path}:nonsemantic_change")
                if old.get("symbol_hashes") != new.get("symbol_hashes"):
                    critical.append(f"{group}:{path}:symbol_change")
        if previous.get("tool_schema_hashes") != current.get("tool_schema_hashes"):
            critical.append("tool_schema_change")
        if previous.get("policy_version") != current.get("policy_version"):
            critical.append("policy_version_change")
        critical = sorted(set(critical))
        nonsemantic = sorted(set(nonsemantic))
        previous_confidence = min(1.0, max(0.0, float(previous.get("confidence", 1.0))))
        if critical:
            state = "shadow_revalidation"
            reusable = False
            confidence = min(previous_confidence * 0.5, 0.49)
            reasons.extend(critical)
        elif nonsemantic:
            state = "active"
            reusable = True
            confidence = previous_confidence * 0.98
            reasons.extend(nonsemantic)
        else:
            state = "active"
            reusable = True
            confidence = previous_confidence
            reasons.append("impact_fingerprint_unchanged")
        return {
            "beast_object_type": "capability_validity_decision",
            "version": "1.0",
            "state": state,
            "reusable": reusable,
            "confidence": round(confidence, 6),
            "previous_fingerprint_hash": previous.get("fingerprint_hash"),
            "current_fingerprint_hash": current.get("fingerprint_hash"),
            "critical_changes": critical,
            "nonsemantic_changes": nonsemantic,
            "reasons": reasons,
            "tiebreaker_policy": "shadow_revalidation_on_uncertain_repository_impact",
        }

    def _path_group(self, root: Path, paths: Iterable[str], symbols: Mapping[str, Iterable[str]]) -> Dict[str, Any]:
        result = {}
        for rel in sorted({str(item) for item in paths if str(item).strip()}):
            path = (root / rel).resolve()
            if root not in path.parents and path != root:
                raise ValueError(f"impact path escaped repository root: {rel}")
            if not path.is_file():
                result[rel] = {"exists": False, "file_hash": "", "semantic_hash": "", "symbol_hashes": {}}
                continue
            data = path.read_bytes()
            text = data.decode("utf-8", errors="replace")
            semantic_hash, symbol_hashes = self._semantic_fingerprint(text, symbols.get(rel, ()))
            result[rel] = {
                "exists": True,
                "file_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
                "semantic_hash": semantic_hash,
                "symbol_hashes": symbol_hashes,
            }
        return result

    @staticmethod
    def _semantic_fingerprint(text: str, selected_symbols: Iterable[str]) -> tuple[str, Dict[str, str]]:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            digest = "sha256:" + hashlib.sha256(text.encode()).hexdigest()
            return digest, {}
        semantic = ast.dump(tree, annotate_fields=True, include_attributes=False)
        semantic_hash = "sha256:" + hashlib.sha256(semantic.encode()).hexdigest()
        wanted = {str(item) for item in selected_symbols}
        hashes = {}
        for node in tree.body:
            name = getattr(node, "name", None)
            if not name or (wanted and name not in wanted):
                continue
            dumped = ast.dump(node, annotate_fields=True, include_attributes=False)
            hashes[str(name)] = "sha256:" + hashlib.sha256(dumped.encode()).hexdigest()
        return semantic_hash, hashes
