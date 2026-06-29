"""Semantic compute pages for proof-local reuse.

PagedAttention manages physical KV pages.  This module gives BEAST a higher
level CPU-safe analogue: independently verifiable semantic pages for summaries,
route cards, verifier plans, and negative capabilities.

The rule is deliberately strict: hashes establish identity, but local checks
establish authority.  Any identity drift, expiry, invalidation, content
mutation, or privacy finding becomes a miss and degrades to recomputation.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.kernel.networking.commons_privacy import CommonsPrivacyScrubber
from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity


PAGE_KINDS = {
    "intermediate_summary",
    "route_card",
    "verifier_plan",
    "negative_capability",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_payload(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def short_hash(value: Any, length: int = 24) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()[:length]


@dataclass(frozen=True)
class SemanticPageIdentity:
    """Full semantic identity binding for an independently reusable page."""

    inference_identity: InferenceArtifactIdentity
    task_family: str
    task_class: str
    page_kind: str
    page_version: str = "1.0"
    verifier_fingerprint: str = "unknown"
    behavior_contract_hash: str = "unknown"
    commons_space_id: str = "local"

    @property
    def identity_hash(self) -> str:
        return sha256_payload(self.to_core_dict())

    def to_core_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "semantic_page_identity",
            "version": "1.0",
            "inference_identity": self.inference_identity.to_dict(),
            "task_family": self.task_family,
            "task_class": self.task_class,
            "page_kind": self.page_kind,
            "page_version": self.page_version,
            "verifier_fingerprint": self.verifier_fingerprint,
            "behavior_contract_hash": self.behavior_contract_hash,
            "commons_space_id": self.commons_space_id,
        }

    def to_dict(self) -> Dict[str, Any]:
        payload = self.to_core_dict()
        payload["identity_hash"] = self.identity_hash
        return payload

    def mutated(self, **updates: Any) -> "SemanticPageIdentity":
        inference_updates = updates.pop("inference_identity", None)
        if isinstance(inference_updates, dict):
            inference = replace(self.inference_identity, **inference_updates)
        elif isinstance(inference_updates, InferenceArtifactIdentity):
            inference = inference_updates
        else:
            inference = self.inference_identity
        return replace(self, inference_identity=inference, **updates)


@dataclass
class SemanticComputePage:
    page_id: str
    page_kind: str
    identity: Dict[str, Any]
    identity_hash: str
    content: Dict[str, Any]
    content_hash: str
    behavior_contract_hash: str
    verifier_refs: List[str]
    created_at: str
    expires_at: str
    state: str = "active"
    invalidation_reason: str = ""
    reuse_count: int = 0
    last_reused_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "semantic_compute_page",
            "version": "1.0",
            **asdict(self),
        }


class SemanticComputePageStore:
    """File-backed local semantic page store.

    The store is intentionally boring: JSON files, content hashes, and fail-closed
    validation.  That makes it usable in CPU-only Docker nodes and easy to
    inspect when a page is accidentally over-trusted.
    """

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or Path("benchmarks/results/semantic_compute_pages"))
        self.pages_dir = self.root / "pages"
        self.receipts_dir = self.root / "receipts"
        self.index_path = self.root / "index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.receipts_dir.mkdir(parents=True, exist_ok=True)

    def put_page(
        self,
        identity: SemanticPageIdentity,
        content: Dict[str, Any],
        *,
        verifier_refs: Optional[Iterable[str]] = None,
        ttl_seconds: int = 86_400,
    ) -> Dict[str, Any]:
        if identity.page_kind not in PAGE_KINDS:
            raise ValueError(f"unsupported semantic page kind: {identity.page_kind}")
        privacy_findings = self._privacy_findings({"identity": identity.to_dict(), "content": content})
        if privacy_findings:
            raise ValueError("semantic page privacy scan failed: " + "; ".join(privacy_findings[:3]))
        behavior_contract_hash = identity.behavior_contract_hash
        if not behavior_contract_hash or behavior_contract_hash == "unknown":
            behavior_contract_hash = sha256_payload({
                "page_kind": identity.page_kind,
                "verifier_refs": sorted(str(item) for item in (verifier_refs or [])),
                "content_shape": sorted(content.keys()),
            })
        content_hash = sha256_payload(content)
        page_id = "scp_" + short_hash({
            "identity_hash": identity.identity_hash,
            "page_kind": identity.page_kind,
            "content_hash": content_hash,
        })
        expires_at = (utc_now() + timedelta(seconds=max(1, int(ttl_seconds)))).isoformat()
        page = SemanticComputePage(
            page_id=page_id,
            page_kind=identity.page_kind,
            identity=identity.to_dict(),
            identity_hash=identity.identity_hash,
            content=content,
            content_hash=content_hash,
            behavior_contract_hash=behavior_contract_hash,
            verifier_refs=[str(item) for item in (verifier_refs or [])],
            created_at=iso_now(),
            expires_at=expires_at,
        )
        validation = self.verify_page(page)
        if not validation["valid"]:
            raise ValueError("semantic page validation failed: " + "; ".join(validation["errors"]))
        self._write_page(page)
        self._refresh_index()
        return {"page": page.to_dict(), "validation": validation}

    def lookup(self, identity: SemanticPageIdentity, *, page_kind: Optional[str] = None, record_reuse: bool = True) -> Dict[str, Any]:
        page_kind = page_kind or identity.page_kind
        candidate = self._find_page(identity.identity_hash, page_kind)
        if candidate is None:
            return self._miss(identity, page_kind, "identity_or_kind_miss")
        validation = self.verify_page(candidate)
        if not validation["valid"]:
            return self._miss(identity, page_kind, "validation_failed", validation=validation)
        if record_reuse:
            candidate.reuse_count += 1
            candidate.last_reused_at = iso_now()
            self._write_page(candidate)
            self._write_reuse_receipt(candidate, validation)
            self._refresh_index()
        return {
            "beast_object_type": "semantic_compute_page_lookup",
            "version": "1.0",
            "hit": True,
            "reason": "identity_exact_verified",
            "page": candidate.to_dict(),
            "validation": validation,
        }

    def invalidate(self, page_id: str, *, reason: str = "manual_invalidation") -> Dict[str, Any]:
        page = self._read_page(page_id)
        if page is None:
            return {"invalidated": False, "reason": "page_not_found", "page_id": page_id}
        page.state = "invalidated"
        page.invalidation_reason = str(reason)[:240]
        self._write_page(page)
        self._refresh_index()
        return {"invalidated": True, "page_id": page_id, "reason": page.invalidation_reason}

    def verify_page(self, page: SemanticComputePage) -> Dict[str, Any]:
        errors: List[str] = []
        privacy_findings = self._privacy_findings(page.to_dict())
        if page.page_kind not in PAGE_KINDS:
            errors.append("unsupported page_kind")
        if page.state != "active":
            errors.append(f"page_state_{page.state}")
        try:
            if parse_time(page.expires_at) <= utc_now():
                errors.append("page_expired")
        except (TypeError, ValueError):
            errors.append("invalid_expires_at")
        if sha256_payload(page.content) != page.content_hash:
            errors.append("content_hash_mismatch")
        identity = page.identity if isinstance(page.identity, dict) else {}
        identity_core = dict(identity)
        identity_hash = str(identity_core.pop("identity_hash", ""))
        if identity_hash != page.identity_hash:
            errors.append("identity_hash_field_mismatch")
        if sha256_payload(identity_core) != page.identity_hash:
            errors.append("identity_hash_recompute_mismatch")
        if str(identity.get("page_kind") or "") != page.page_kind:
            errors.append("identity_page_kind_mismatch")
        if str(identity.get("behavior_contract_hash") or "") not in {"", "unknown", page.behavior_contract_hash}:
            errors.append("behavior_contract_mismatch")
        if privacy_findings:
            errors.append("privacy_scan_failed")
        return {
            "beast_object_type": "semantic_compute_page_validation",
            "version": "1.0",
            "valid": not errors,
            "errors": errors,
            "privacy_findings": privacy_findings,
            "page_id": page.page_id,
            "identity_hash": page.identity_hash,
            "content_hash": page.content_hash,
        }

    def state(self, *, include_pages: bool = False) -> Dict[str, Any]:
        index = self._refresh_index()
        pages = [self._read_page(page_id) for page_id in index.get("page_ids", [])]
        pages = [page for page in pages if page is not None]
        active = [page for page in pages if self.verify_page(page)["valid"]]
        payload: Dict[str, Any] = {
            "beast_object_type": "semantic_compute_page_store",
            "version": "1.0",
            "root": str(self.root),
            "page_count": len(pages),
            "active_verified_pages": len(active),
            "reuse_count": sum(page.reuse_count for page in pages),
            "page_kinds": {kind: sum(1 for page in pages if page.page_kind == kind) for kind in sorted(PAGE_KINDS)},
            "latest_receipt": self._latest_receipt_path(),
            "exit_criteria": {
                "individual_page_reuse": sum(page.reuse_count for page in pages) > 0,
                "identity_mutation_miss": bool(index.get("latest_mutation_gauntlet_passed", False)),
                "local_behavior_verification": len(active) == len(pages) and len(pages) > 0,
            },
        }
        if include_pages:
            payload["pages"] = [page.to_dict() for page in pages]
        return payload

    def mutation_gauntlet(self, identity: SemanticPageIdentity) -> Dict[str, Any]:
        mutations: List[Tuple[str, SemanticPageIdentity]] = [
            ("model_revision", identity.mutated(inference_identity={"model_revision": "mutated-revision"})),
            ("tool_schema", identity.mutated(inference_identity={"tool_schema_fingerprint": "sha256:mutated-tool-schema"})),
            ("skill_tree", identity.mutated(inference_identity={"skill_tree_fingerprint": "sha256:mutated-skill-tree"})),
            ("repository", identity.mutated(inference_identity={"repository_fingerprint": "sha256:mutated-repo"})),
            ("verifier", identity.mutated(verifier_fingerprint="sha256:mutated-verifier")),
            ("privacy_class", identity.mutated(inference_identity={"tenant_privacy_class": "different_privacy_class"})),
        ]
        results = []
        for name, mutated_identity in mutations:
            lookup = self.lookup(mutated_identity, record_reuse=False)
            results.append({"mutation": name, "missed": not lookup["hit"], "reason": lookup["reason"]})
        passed = all(item["missed"] for item in results)
        index = self._load_index()
        index["latest_mutation_gauntlet_passed"] = passed
        index["latest_mutation_gauntlet_at"] = iso_now()
        self._write_json(self.index_path, index)
        return {
            "beast_object_type": "semantic_compute_page_mutation_gauntlet",
            "version": "1.0",
            "passed": passed,
            "results": results,
        }

    def _find_page(self, identity_hash: str, page_kind: str) -> Optional[SemanticComputePage]:
        for path in sorted(self.pages_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("identity_hash") == identity_hash and raw.get("page_kind") == page_kind:
                return self._page_from_raw(raw)
        return None

    def _read_page(self, page_id: str) -> Optional[SemanticComputePage]:
        path = self.pages_dir / f"{page_id}.json"
        if not path.is_file():
            return None
        try:
            return self._page_from_raw(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def _write_page(self, page: SemanticComputePage) -> None:
        self._write_json(self.pages_dir / f"{page.page_id}.json", page.to_dict())

    def _page_from_raw(self, raw: Dict[str, Any]) -> SemanticComputePage:
        keys = set(SemanticComputePage.__dataclass_fields__)
        return SemanticComputePage(**{key: raw.get(key) for key in keys})

    def _write_reuse_receipt(self, page: SemanticComputePage, validation: Dict[str, Any]) -> None:
        receipt = {
            "beast_object_type": "semantic_compute_page_reuse_receipt",
            "version": "1.0",
            "receipt_id": "scp_reuse_" + short_hash({"page_id": page.page_id, "reuse_count": page.reuse_count, "at": page.last_reused_at}),
            "page_id": page.page_id,
            "page_kind": page.page_kind,
            "identity_hash": page.identity_hash,
            "content_hash": page.content_hash,
            "reuse_count": page.reuse_count,
            "verified": validation["valid"],
            "issued_at": page.last_reused_at,
            "authority": "local_verified_reuse_only",
        }
        self._write_json(self.receipts_dir / f"{receipt['receipt_id']}.json", receipt)

    def _miss(self, identity: SemanticPageIdentity, page_kind: str, reason: str, *, validation: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "beast_object_type": "semantic_compute_page_lookup",
            "version": "1.0",
            "hit": False,
            "reason": reason,
            "page": None,
            "identity_hash": identity.identity_hash,
            "page_kind": page_kind,
            "validation": validation or {},
        }

    def _privacy_findings(self, payload: Dict[str, Any]) -> List[str]:
        findings = CommonsPrivacyScrubber().scan_payload(payload)
        rendered = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        extra_patterns = [
            ("absolute_local_path", "/home/"),
            ("private_key_material", "PRIVATE KEY"),
            ("raw_prompt_marker", "raw_prompt"),
            ("rollback_snapshot", "rollback_snapshot"),
            ("private_fixture", "private_fixture"),
        ]
        extra = [name for name, pattern in extra_patterns if pattern in rendered]
        return [str(item) for item in findings] + extra

    def _load_index(self) -> Dict[str, Any]:
        if not self.index_path.is_file():
            return {"beast_object_type": "semantic_compute_page_index", "version": "1.0", "page_ids": []}
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw.setdefault("page_ids", [])
                return raw
        except (OSError, json.JSONDecodeError):
            pass
        return {"beast_object_type": "semantic_compute_page_index", "version": "1.0", "page_ids": []}

    def _refresh_index(self) -> Dict[str, Any]:
        index = self._load_index()
        page_ids = sorted(path.stem for path in self.pages_dir.glob("*.json"))
        index.update({
            "page_ids": page_ids,
            "updated_at": iso_now(),
            "page_count": len(page_ids),
        })
        self._write_json(self.index_path, index)
        return index

    def _latest_receipt_path(self) -> Optional[str]:
        receipts = sorted(self.receipts_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns if item.exists() else 0)
        return str(receipts[-1]) if receipts else None

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> Dict[str, Any]:
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return value
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_phase3_semantic_pages(
    *,
    store: Optional[SemanticComputePageStore] = None,
    output_root: Optional[Path] = None,
    ttl_seconds: int = 86_400,
    reuse_repetitions: int = 3,
) -> Dict[str, Any]:
    """Build and prove Phase 3 pages from local Phase 7 artifacts."""

    started = time.perf_counter()
    store = store or SemanticComputePageStore(output_root)
    artifact_root = Path("benchmarks/results/crystal_to_adapter_distillation")
    phase7 = _read_json(artifact_root / "phase7_crystal_to_adapter_latest.json")
    route_head = _read_json(artifact_root / "crystal_lora_route_head_latest.json")
    micro_lora = _read_json(artifact_root / "micro_lora_verification_latest.json")
    runtime = _read_json(artifact_root / "ollama_crystal_runtime_verification_latest.json")

    task_family = str(route_head.get("predicted_task_family") or "phase7_crystal_lattice")
    verifier_refs = ["schema_validation", "local_behavior_verification", "identity_mutation_miss"]
    model_identity = str((runtime.get("model") or {}).get("adapter_model") or "beast-crystal-qwen25-05b:latest")
    inference_identity = InferenceArtifactIdentity.from_prompts(
        model=model_identity,
        tokenizer="ollama-qwen2.5-local",
        prompt_prefix="BEAST semantic compute page: " + task_family,
        system_prompt="Use BEAST task envelopes, registries, skill trees, forge cards, cascades, and verifier gates.",
        engine="semantic_compute_pages",
        engine_version="phase3",
        model_revision=str((runtime.get("model") or {}).get("base_model") or "local_ollama"),
        tokenizer_revision="local",
        precision="cpu",
        quantization="ollama_or_micro_lora",
        policy_fingerprint=_digest_text("proof-local-phase3-policy-v1"),
        tool_schema_fingerprint=_digest_text("compute_governor+commons_spaces+forge+skill_tree"),
        skill_tree_fingerprint=_digest_text("beast_agent_awareness+meta_tool_commons"),
        repository_fingerprint=_digest_text(str(phase7.get("source_digest") or phase7.get("dataset_hash") or "local_artifacts")),
        tenant_privacy_class="local_metadata_only",
    )

    page_specs = [
        (
            "intermediate_summary",
            {
                "title": "Phase 7 lattice summary",
                "summary": "Local crystals were distilled into adapter/route-head evidence. Reuse this page before rebuilding the same task-family summary.",
                "families": phase7.get("families") or phase7.get("top_task_families") or [],
                "dataset_rows": phase7.get("dataset_rows") or phase7.get("row_count") or 0,
                "public_export_allowed": False,
            },
        ),
        (
            "route_card",
            {
                "title": "Crystal LoRA route card",
                "route": route_head.get("route") or route_head.get("proposal") or {},
                "predicted_task_family": task_family,
                "confidence": route_head.get("confidence") or route_head.get("route_confidence") or 0,
                "authority": "proposal_only_governor_must_verify",
            },
        ),
        (
            "verifier_plan",
            {
                "title": "Local verifier plan",
                "required_verifiers": verifier_refs,
                "micro_lora_verified": bool(micro_lora.get("passed") or micro_lora.get("verified")),
                "runtime_verification": runtime.get("status") or runtime.get("verification") or {},
                "approval_boundary": "adapter and page output never bypass policy/verifier/approval gates",
            },
        ),
        (
            "negative_capability",
            {
                "title": "Do not reuse outside the fingerprint boundary",
                "miss_conditions": [
                    "model revision drift",
                    "tool schema drift",
                    "skill tree drift",
                    "repository fingerprint drift",
                    "verifier fingerprint drift",
                    "privacy class drift",
                ],
                "demotion_action": "miss_and_recompute",
                "credit_policy": "no credit for stale or mutated semantic pages",
            },
        ),
    ]

    pages: List[Dict[str, Any]] = []
    identities: List[SemanticPageIdentity] = []
    for page_kind, content in page_specs:
        identity = SemanticPageIdentity(
            inference_identity=inference_identity,
            task_family=task_family,
            task_class="proof_local_phase3",
            page_kind=page_kind,
            verifier_fingerprint=sha256_payload(verifier_refs),
            behavior_contract_hash=sha256_payload({"page_kind": page_kind, "verifiers": verifier_refs, "contract": "local_behavior_verification"}),
            commons_space_id="local_phase7_crystal_distillation",
        )
        put = store.put_page(identity, content, verifier_refs=verifier_refs, ttl_seconds=ttl_seconds)
        pages.append(put["page"])
        identities.append(identity)

    reuse_hits = 0
    estimated_tokens_avoided = 0
    bytes_reused = 0
    for _ in range(max(1, int(reuse_repetitions))):
        for identity in identities:
            lookup = store.lookup(identity)
            if lookup["hit"]:
                reuse_hits += 1
                page = lookup["page"]
                bytes_reused += len(json.dumps(page.get("content") or {}, sort_keys=True))
                estimated_tokens_avoided += max(16, len(json.dumps(page.get("content") or {})) // 4)

    mutation = store.mutation_gauntlet(identities[0])
    validations = [store.verify_page(store._page_from_raw(page)) for page in pages]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    receipt = {
        "beast_object_type": "phase3_semantic_compute_pages_receipt",
        "version": "1.0",
        "status": "implemented",
        "issued_at": iso_now(),
        "page_count": len(pages),
        "page_ids": [page["page_id"] for page in pages],
        "page_kinds": [page["page_kind"] for page in pages],
        "reuse_repetitions": max(1, int(reuse_repetitions)),
        "reuse_hits": reuse_hits,
        "estimated_tokens_avoided": estimated_tokens_avoided,
        "bytes_reused": bytes_reused,
        "cpu_build_elapsed_ms": elapsed_ms,
        "identity_mutation_gauntlet": mutation,
        "validations": validations,
        "exit_criteria": {
            "repeated_workloads_reuse_individual_pages": reuse_hits >= len(pages),
            "every_identity_mutation_causes_miss": mutation["passed"],
            "reuse_preserves_verifier_success": all(item["valid"] for item in validations),
            "cpu_or_token_improvement": estimated_tokens_avoided > 0 and bytes_reused > 0,
        },
        "state": store.state(include_pages=False),
    }
    latest = store.root / "phase3_semantic_compute_pages_latest.json"
    store._write_json(latest, receipt)
    return receipt
