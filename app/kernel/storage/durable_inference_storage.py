"""Phase 7: Durable Inference Storage — store verified reusable artifacts as Semantic Compute Credit.

This module implements the storage layer for:
1. Store the answer (normal caching)
2. Store the semantic result (BEAST-like: task envelope + repo state + tests + evidence + patch + chronicle + fingerprint)
3. Store the prefill / KV cache (engine-level preparation)
4. Store KV caches across engines (transportable compute assets)

The key abstraction is "Semantic Compute Credit" — a verified reusable artifact that reduces future uncertainty.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import re
import math
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.kernel.data_processing.inference_artifact_identity import InferenceArtifactIdentity


@dataclass(frozen=True)
class SemanticComputeCredit:
    """A verified reusable artifact representing stored inference value.
    
    This is the core Phase 7 abstraction: not "one token" but a verified artifact
    that reduces future uncertainty and can prevent a provider call.
    """
    credit_id: str
    artifact_type: str  # "verified_capability" | "deterministic_transform" | "route_card" | "test_impact_map" | "kv_cache" | "prefill"
    task_class: str
    repo_fingerprint: str
    policy_version: str
    verified_tests: List[str] = field(default_factory=list)  # ["visible", "hidden"]
    avoided_tokens_estimate: int = 0
    confidence: float = 0.0
    reuse_state: str = "active"  # "active" | "stale" | "retired"
    impact_fingerprint_hash: Optional[str] = None
    chronicle_lesson_id: Optional[str] = None
    evidence_packet_id: Optional[str] = None
    created_at: str = ""
    last_reused_at: Optional[str] = None
    reuse_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "semantic_compute_credit",
            "version": "1.0",
            "credit_id": self.credit_id,
            "artifact_type": self.artifact_type,
            "task_class": self.task_class,
            "repo_fingerprint": self.repo_fingerprint,
            "policy_version": self.policy_version,
            "verified_tests": self.verified_tests,
            "avoided_tokens_estimate": self.avoided_tokens_estimate,
            "confidence": self.confidence,
            "reuse_state": self.reuse_state,
            "impact_fingerprint_hash": self.impact_fingerprint_hash,
            "chronicle_lesson_id": self.chronicle_lesson_id,
            "evidence_packet_id": self.evidence_packet_id,
            "created_at": self.created_at,
            "last_reused_at": self.last_reused_at,
            "reuse_count": self.reuse_count,
            "metadata": self.metadata,
        }

    def is_reusable(self) -> bool:
        """Check if this credit can be safely reused."""
        if self.reuse_state != "active":
            return False
        if self.artifact_type == "cached_answer":
            return self.confidence >= 0.50
        if self.confidence < 0.60:
            return False
        if self.artifact_type in {"verified_capability", "deterministic_transform"}:
            checks = {str(item).lower() for item in self.verified_tests}
            return {"visible", "hidden"}.issubset(checks) and bool(self.impact_fingerprint_hash)
        return True

    def record_reuse(self) -> "SemanticComputeCredit":
        """Return a new credit with updated reuse statistics (immutable update)."""
        return SemanticComputeCredit(
            credit_id=self.credit_id,
            artifact_type=self.artifact_type,
            task_class=self.task_class,
            repo_fingerprint=self.repo_fingerprint,
            policy_version=self.policy_version,
            verified_tests=self.verified_tests,
            avoided_tokens_estimate=self.avoided_tokens_estimate,
            confidence=self.confidence,
            reuse_state=self.reuse_state,
            impact_fingerprint_hash=self.impact_fingerprint_hash,
            chronicle_lesson_id=self.chronicle_lesson_id,
            evidence_packet_id=self.evidence_packet_id,
            created_at=self.created_at,
            last_reused_at=datetime.now(timezone.utc).isoformat(),
            reuse_count=self.reuse_count + 1,
            metadata=self.metadata,
        )


@dataclass(frozen=True)
class StoredInferenceValue:
    """Three-tier currency model for BEAST compute economics."""
    live_compute: Dict[str, Any] = field(default_factory=dict)  # GPU/CPU seconds, tokens, latency, USD
    stored_compute: Dict[str, Any] = field(default_factory=dict)  # KV cache, prefix cache, embeddings, summaries, route cards
    crystallized_compute: Dict[str, Any] = field(default_factory=dict)  # Promoted capabilities, fingerprints, evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "stored_inference_value",
            "version": "1.0",
            "live_compute": self.live_compute,
            "stored_compute": self.stored_compute,
            "crystallized_compute": self.crystallized_compute,
            "description": "Three currencies: Live (runtime), Stored (preparation), Crystallized (verified capability)",
        }


@dataclass(frozen=True)
class RuntimeReplayResult:
    """Runtime-safe replay result for a stored inference artifact."""
    replay_type: str  # "cached_answer" | "semantic_credit" | "kv_prefill"
    credit_id: str
    reusable: bool
    payload: Dict[str, Any] = field(default_factory=dict)
    avoided_tokens_estimate: int = 0
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "beast_object_type": "runtime_replay_result",
            "version": "1.0",
            "replay_type": self.replay_type,
            "credit_id": self.credit_id,
            "reusable": self.reusable,
            "payload": self.payload,
            "avoided_tokens_estimate": self.avoided_tokens_estimate,
            "confidence": self.confidence,
            "reason": self.reason,
        }


class DurableInferenceStorage:
    """Phase 7 storage layer for Semantic Compute Credits and stored inference artifacts."""
    SEMANTIC_INDEX_VERSION = "beast_hashed_embedding_v1"
    SEMANTIC_DIMENSIONS = 256

    def __init__(self, storage_path: Optional[Path] = None):
        if storage_path is None:
            storage_path = Path(__file__).resolve().parents[2] / "data" / "durable_inference"
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.blob_path = self.storage_path / "blobs" / "sha256"
        self.blob_path.mkdir(parents=True, exist_ok=True)
        self.credits: Dict[str, SemanticComputeCredit] = {}
        self.credit_blobs: Dict[str, str] = {}
        self.load_errors: List[Dict[str, str]] = []
        self._load_from_disk()

    def _credit_path(self, credit_id: str) -> Path:
        return self.storage_path / f"{credit_id}.json"

    def _answer_path(self, credit_id: str) -> Path:
        return self.storage_path / f"{credit_id}.answer.json"

    def _blob_file(self, digest: str) -> Path:
        return self.blob_path / f"{digest.removeprefix('sha256:')}.json"

    @staticmethod
    def _canonical_bytes(payload: Any) -> bytes:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    @staticmethod
    def _atomic_bytes(path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            dir_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    @classmethod
    def _atomic_json(cls, path: Path, payload: Dict[str, Any]) -> None:
        cls._atomic_bytes(path, json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n")

    @staticmethod
    def _immutable_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        mutable = {"measured_reuse_tokens_saved", "last_measured_reuse_tokens_saved"}
        return {key: value for key, value in metadata.items() if key not in mutable}

    def _immutable_credit_payload(self, credit: SemanticComputeCredit) -> Dict[str, Any]:
        return {
            "beast_object_type": "semantic_compute_artifact",
            "version": "1.0",
            "artifact_type": credit.artifact_type,
            "task_class": credit.task_class,
            "repo_fingerprint": credit.repo_fingerprint,
            "policy_version": credit.policy_version,
            "verified_tests": list(credit.verified_tests),
            "avoided_tokens_estimate": credit.avoided_tokens_estimate,
            "confidence": credit.confidence,
            "impact_fingerprint_hash": credit.impact_fingerprint_hash,
            "chronicle_lesson_id": credit.chronicle_lesson_id,
            "evidence_packet_id": credit.evidence_packet_id,
            "metadata": self._immutable_metadata(credit.metadata),
        }

    def _store_blob(self, payload: Dict[str, Any]) -> Dict[str, str]:
        canonical = self._canonical_bytes(payload)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        path = self._blob_file(digest)
        if not path.exists():
            self._atomic_json(path, {
                "beast_object_type": "content_addressed_blob",
                "version": "1.0",
                "digest": digest,
                "payload": payload,
            })
        return {"digest": digest, "ref": str(path.relative_to(self.storage_path))}

    def _verify_blob(self, blob: Dict[str, Any]) -> bool:
        digest = str(blob.get("digest") or "")
        ref = str(blob.get("ref") or "")
        if not digest or not ref:
            return False
        try:
            envelope = json.loads((self.storage_path / ref).read_text(encoding="utf-8"))
            payload = envelope.get("payload")
            actual = "sha256:" + hashlib.sha256(self._canonical_bytes(payload)).hexdigest()
            return actual == digest == envelope.get("digest")
        except (OSError, json.JSONDecodeError, TypeError):
            return False

    def _load_from_disk(self) -> None:
        """Load existing credits from disk."""
        for json_file in self.storage_path.glob("*.json"):
            if json_file.name.endswith(".answer.json"):
                continue
            try:
                data = json.loads(json_file.read_text())
                allowed = {item.name for item in fields(SemanticComputeCredit)}
                credit = SemanticComputeCredit(**{key: value for key, value in data.items() if key in allowed})
                self.credits[credit.credit_id] = credit
                blob = data.get("artifact_blob") if isinstance(data.get("artifact_blob"), dict) else {}
                if blob:
                    if self._verify_blob(blob):
                        self.credit_blobs[credit.credit_id] = str(blob.get("digest"))
                    else:
                        self.load_errors.append({"path": str(json_file), "error": "ArtifactBlobIntegrityError"})
                else:
                    # Legacy indexes are upgraded in place without changing the public credit id.
                    self._persist_credit(credit)
            except (json.JSONDecodeError, TypeError, KeyError) as exc:
                self.load_errors.append({"path": str(json_file), "error": type(exc).__name__})

    def _persist_credit(self, credit: SemanticComputeCredit) -> None:
        """Persist the mutable credit index and reference an immutable artifact blob."""
        blob = self._store_blob(self._immutable_credit_payload(credit))
        payload = credit.to_dict()
        payload["index_version"] = "2.0"
        payload["artifact_blob"] = blob
        self.credit_blobs[credit.credit_id] = blob["digest"]
        self._atomic_json(self._credit_path(credit.credit_id), payload)

    @classmethod
    def _redact_metadata(cls, value: Any) -> Any:
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                secret_markers = ("api_key", "secret", "password", "access_token", "auth_token", "bearer_token")
                if any(marker in normalized for marker in secret_markers):
                    result[str(key)] = "[REDACTED]"
                else:
                    result[str(key)] = cls._redact_metadata(item)
            return result
        if isinstance(value, list):
            return [cls._redact_metadata(item) for item in value]
        return value

    def store_semantic_result(
        self,
        task_class: str,
        repo_fingerprint: str,
        policy_version: str,
        verified_tests: List[str],
        avoided_tokens_estimate: int,
        confidence: float,
        impact_fingerprint_hash: Optional[str] = None,
        chronicle_lesson_id: Optional[str] = None,
        evidence_packet_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SemanticComputeCredit:
        """Store a BEAST-like semantic result (task envelope + repo state + tests + evidence + patch + chronicle + fingerprint).
        
        This is the highest-value form: a verified capability that can safely displace future inference.
        """
        credit_id = f"scc_{hashlib.sha256(f'{task_class}:{repo_fingerprint}:{policy_version}'.encode()).hexdigest()[:16]}"
        
        credit = SemanticComputeCredit(
            credit_id=credit_id,
            artifact_type="verified_capability",
            task_class=task_class,
            repo_fingerprint=repo_fingerprint,
            policy_version=policy_version,
            verified_tests=verified_tests,
            avoided_tokens_estimate=avoided_tokens_estimate,
            confidence=confidence,
            reuse_state="active",
            impact_fingerprint_hash=impact_fingerprint_hash,
            chronicle_lesson_id=chronicle_lesson_id,
            evidence_packet_id=evidence_packet_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=self._redact_metadata(metadata or {}),
        )
        
        self.credits[credit_id] = credit
        self._persist_credit(credit)
        return credit

    def store_answer(
        self,
        prompt_hash: str,
        model: str,
        parameters: Dict[str, Any],
        response: str,
        cost_usd: Optional[float] = None,
    ) -> SemanticComputeCredit:
        """Store a normal cached answer (same prompt + model + parameters → cached response).
        
        This is the simplest form: useful but brittle.
        """
        parameter_hash = self._parameter_hash(parameters)
        credit_id = self._answer_credit_id(prompt_hash, model, parameter_hash)
        response_sha = hashlib.sha256(response.encode()).hexdigest()
        response_blob = self._persist_answer(credit_id, response)
        
        credit = SemanticComputeCredit(
            credit_id=credit_id,
            artifact_type="cached_answer",
            task_class="chat_completion",
            repo_fingerprint="n/a",
            policy_version="cache_v1",
            verified_tests=[],
            avoided_tokens_estimate=0,
            confidence=0.50,  # Lower confidence for simple caching (brittle)
            reuse_state="active",
            metadata={
                "prompt_hash": prompt_hash,
                "model": model,
                "parameter_hash": parameter_hash,
                "parameters": self._redact_metadata(parameters),
                "response_preview": response[:500],
                "response_ref": self._answer_path(credit_id).name,
                "response_blob_ref": response_blob["ref"],
                "response_blob_digest": response_blob["digest"],
                "response_sha256": "sha256:" + response_sha,
                "response_chars": len(response),
                "cost_usd": cost_usd,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        
        self.credits[credit_id] = credit
        self._persist_credit(credit)
        return credit

    def store_prefill(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        kv_cache_metadata: Dict[str, Any],
        compatibility: Optional[Dict[str, Any]] = None,
    ) -> SemanticComputeCredit:
        """Store engine-level prefill / KV cache preparation.
        
        This is the engine-level version: same model + tokenizer + prompt prefix + system prompt → reuse prefill computation.
        """
        compatibility = dict(compatibility or {})
        identity = InferenceArtifactIdentity.from_prompts(
            model=model, tokenizer=tokenizer, prompt_prefix=prompt_prefix,
            system_prompt=system_prompt, **compatibility,
        )
        prompt_prefix_hash = identity.prompt_prefix_hash.removeprefix("sha256:")
        system_prompt_hash = identity.system_prompt_hash.removeprefix("sha256:")
        prefix_hash = identity.identity_hash.removeprefix("sha256:")[:16]
        credit_id = f"prefill_{prefix_hash}"
        
        credit = SemanticComputeCredit(
            credit_id=credit_id,
            artifact_type="kv_prefill",
            task_class="prefill_preparation",
            repo_fingerprint="n/a",
            policy_version="engine_v1",
            verified_tests=[],
            avoided_tokens_estimate=kv_cache_metadata.get("estimated_tokens_saved", 0),
            confidence=0.70,
            reuse_state="active",
            metadata={
                "model": model,
                "tokenizer": tokenizer,
                "prompt_prefix_hash": prompt_prefix_hash,
                "system_prompt_hash": system_prompt_hash,
                "kv_cache_metadata": self._redact_metadata(kv_cache_metadata),
                "inference_artifact_identity": identity.to_dict(),
                "inference_artifact_identity_hash": identity.identity_hash,
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        
        self.credits[credit_id] = credit
        self._persist_credit(credit)
        return credit

    def lookup_answer(
        self,
        prompt_hash: str,
        model: str,
        parameters: Dict[str, Any],
        *,
        record_reuse: bool = True,
    ) -> Optional[RuntimeReplayResult]:
        """Retrieve a complete cached answer for an exact prompt/model/parameter identity."""
        parameter_hash = self._parameter_hash(parameters)
        credit_id = self._answer_credit_id(prompt_hash, model, parameter_hash)
        credit = self.credits.get(credit_id)
        if not credit or not credit.is_reusable():
            return None
        response = self._load_answer(credit)
        if response is None:
            return None
        if record_reuse:
            credit = self.record_credit_reuse(credit.credit_id) or credit
        return RuntimeReplayResult(
            replay_type="cached_answer",
            credit_id=credit.credit_id,
            reusable=True,
            payload={
                "response": response,
                "prompt_hash": prompt_hash,
                "model": model,
                "parameter_hash": parameter_hash,
            },
            avoided_tokens_estimate=credit.avoided_tokens_estimate,
            confidence=credit.confidence,
            reason="exact_cached_answer_retrieved",
        )

    def lookup_prefill(
        self,
        model: str,
        tokenizer: str,
        prompt_prefix: str,
        system_prompt: str,
        *,
        record_reuse: bool = True,
        compatibility: Optional[Dict[str, Any]] = None,
    ) -> Optional[RuntimeReplayResult]:
        """Retrieve a reusable prefill identity for the exact model/tokenizer/prompt prefix."""
        compatibility = dict(compatibility or {})
        identity = InferenceArtifactIdentity.from_prompts(
            model=model, tokenizer=tokenizer, prompt_prefix=prompt_prefix,
            system_prompt=system_prompt, **compatibility,
        )
        prompt_prefix_hash = identity.prompt_prefix_hash.removeprefix("sha256:")
        system_prompt_hash = identity.system_prompt_hash.removeprefix("sha256:")
        candidates = [
            credit for credit in self.credits.values()
            if credit.artifact_type == "kv_prefill"
            and credit.is_reusable()
            and credit.metadata.get("model") == model
            and credit.metadata.get("tokenizer") == tokenizer
            and credit.metadata.get("prompt_prefix_hash") == prompt_prefix_hash
            and credit.metadata.get("system_prompt_hash") == system_prompt_hash
            and (not compatibility or credit.metadata.get("inference_artifact_identity_hash") == identity.identity_hash)
        ]
        if not candidates:
            return None
        credit = max(candidates, key=lambda item: (item.confidence, item.reuse_count))
        if record_reuse:
            credit = self.record_credit_reuse(credit.credit_id) or credit
        return RuntimeReplayResult(
            replay_type="kv_prefill",
            credit_id=credit.credit_id,
            reusable=True,
            payload={
                "model": model,
                "tokenizer": tokenizer,
                "prompt_prefix_hash": prompt_prefix_hash,
                "system_prompt_hash": system_prompt_hash,
                "kv_cache_metadata": credit.metadata.get("kv_cache_metadata", {}),
            },
            avoided_tokens_estimate=credit.avoided_tokens_estimate,
            confidence=credit.confidence,
            reason="exact_prefill_identity_retrieved",
        )

    def runtime_lookup_replay(
        self,
        *,
        task_class: Optional[str] = None,
        repo_fingerprint: Optional[str] = None,
        prompt_hash: Optional[str] = None,
        model: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        tokenizer: Optional[str] = None,
        prompt_prefix: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Optional[RuntimeReplayResult]:
        """Shared runtime lookup order: semantic credit, exact answer, then prefill."""
        if task_class:
            credit = self.lookup_reusable_credit(task_class, repo_fingerprint=repo_fingerprint)
            if credit:
                return self.replay_credit(credit.credit_id)
        if prompt_hash and model and parameters is not None:
            answer = self.lookup_answer(prompt_hash, model, parameters)
            if answer:
                return answer
        if model and tokenizer and prompt_prefix is not None and system_prompt is not None:
            return self.lookup_prefill(model, tokenizer, prompt_prefix, system_prompt)
        return None

    @staticmethod
    def _semantic_terms(value: str) -> set[str]:
        return {item for item in re.findall(r"[a-z0-9_]{3,}", value.lower()) if len(item) <= 80}

    def semantic_index(self, prompt: str) -> Dict[str, Any]:
        """Create a local, salted feature vector without persisting prompt text."""
        terms = sorted(self._semantic_terms(prompt))[:256]
        salt = hashlib.sha256(str(self.storage_path.resolve()).encode("utf-8")).hexdigest()
        vector = [0.0] * self.SEMANTIC_DIMENSIONS
        token_hashes: list[str] = []
        for term in terms:
            token_hashes.append(hashlib.sha256(f"{salt}:term:{term}".encode()).hexdigest()[:24])
            features = [term] + [f"g:{term[index:index + 3]}" for index in range(max(0, len(term) - 2))]
            for feature in features:
                digest = hashlib.sha256(f"{salt}:feature:{feature}".encode()).digest()
                index = int.from_bytes(digest[:4], "big") % self.SEMANTIC_DIMENSIONS
                vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(item * item for item in vector))
        normalized = [round(item / norm, 8) for item in vector] if norm else vector
        return {
            "version": self.SEMANTIC_INDEX_VERSION,
            "dimensions": self.SEMANTIC_DIMENSIONS,
            "token_hashes": sorted(token_hashes),
            "vector": normalized,
        }

    @staticmethod
    def _cosine(left: Any, right: Any) -> float:
        if not isinstance(left, list) or not isinstance(right, list) or len(left) != len(right) or not left:
            return 0.0
        try:
            return max(0.0, min(1.0, sum(float(a) * float(b) for a, b in zip(left, right))))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _jaccard(left: Any, right: Any) -> float:
        if not isinstance(left, list) or not isinstance(right, list):
            return 0.0
        lhs, rhs = set(map(str, left)), set(map(str, right))
        return len(lhs & rhs) / len(lhs | rhs) if lhs and rhs else 0.0

    def _semantic_candidates(
        self, *, task_class: str, repo_fingerprint: Optional[str], model: Optional[str],
        require_repo_fingerprint: bool, require_verified: bool,
    ) -> list[SemanticComputeCredit]:
        if require_repo_fingerprint and not repo_fingerprint:
            return []
        result = []
        for credit in self.credits.values():
            if credit.task_class != task_class or (require_verified and not credit.is_reusable()):
                continue
            if repo_fingerprint and credit.repo_fingerprint != repo_fingerprint:
                continue
            if require_repo_fingerprint and credit.repo_fingerprint in {"", "n/a"}:
                continue
            if model and str(credit.metadata.get("model") or "") != model:
                continue
            index = credit.metadata.get("semantic_index")
            if not isinstance(index, dict) or index.get("version") != self.SEMANTIC_INDEX_VERSION:
                continue
            result.append(credit)
        return result

    def _replay_with_similarity(self, credit: SemanticComputeCredit, similarity: float, reason: str) -> Optional[RuntimeReplayResult]:
        replay = self.replay_credit(credit.credit_id)
        if replay is None:
            return None
        return RuntimeReplayResult(
            replay_type=replay.replay_type, credit_id=replay.credit_id, reusable=replay.reusable,
            payload={**replay.payload, "semantic_similarity": round(similarity, 6), "semantic_index_version": self.SEMANTIC_INDEX_VERSION},
            avoided_tokens_estimate=replay.avoided_tokens_estimate,
            confidence=min(float(replay.confidence), float(similarity)), reason=reason,
        )

    def semantic_search(
        self, *, task_class: str, prompt: str, threshold: float = 0.86,
        repo_fingerprint: Optional[str] = None, model: Optional[str] = None,
        require_repo_fingerprint: bool = True, require_verified: bool = True,
    ) -> Optional[RuntimeReplayResult]:
        """Match only explicit, bounded semantic terms stored with verified credits."""
        query = self.semantic_index(prompt)
        if not query["token_hashes"]:
            return None
        candidates = []
        for credit in self._semantic_candidates(
            task_class=task_class, repo_fingerprint=repo_fingerprint, model=model,
            require_repo_fingerprint=require_repo_fingerprint, require_verified=require_verified,
        ):
            index = credit.metadata["semantic_index"]
            cosine = self._cosine(query["vector"], index.get("vector"))
            overlap = self._jaccard(query["token_hashes"], index.get("token_hashes"))
            similarity = (0.75 * cosine) + (0.25 * overlap)
            if similarity >= float(threshold):
                candidates.append((similarity, credit))
        if not candidates:
            return None
        _score, credit = max(candidates, key=lambda item: (item[0], item[1].confidence, item[1].reuse_count))
        return self._replay_with_similarity(credit, _score, "gptcache_compatible_verified_semantic_replay")

    def embedding_search(
        self, *, task_class: str, prompt: str, threshold: float = 0.90,
        repo_fingerprint: Optional[str] = None, model: Optional[str] = None,
        require_repo_fingerprint: bool = True, require_verified: bool = True,
    ) -> Optional[RuntimeReplayResult]:
        """Strict cosine search over versioned local hashed embeddings."""
        query = self.semantic_index(prompt)
        if not query["token_hashes"]:
            return None
        candidates = []
        for credit in self._semantic_candidates(
            task_class=task_class, repo_fingerprint=repo_fingerprint, model=model,
            require_repo_fingerprint=require_repo_fingerprint, require_verified=require_verified,
        ):
            similarity = self._cosine(query["vector"], credit.metadata["semantic_index"].get("vector"))
            if similarity >= float(threshold):
                candidates.append((similarity, credit))
        if not candidates:
            return None
        score, credit = max(candidates, key=lambda item: (item[0], item[1].confidence, item[1].reuse_count))
        return self._replay_with_similarity(credit, score, "local_hashed_embedding_verified_replay")

    def replay_credit(self, credit_id: str, *, measured_tokens_saved: Optional[int] = None) -> Optional[RuntimeReplayResult]:
        """Replay a stored artifact by credit id and update reuse counters."""
        credit = self.credits.get(credit_id)
        if not credit or not credit.is_reusable():
            return None
        credit = self.record_credit_reuse(credit_id, measured_tokens_saved=measured_tokens_saved) or credit
        if credit.artifact_type == "cached_answer":
            response = self._load_answer(credit)
            if response is None:
                return None
            return RuntimeReplayResult(
                replay_type="cached_answer",
                credit_id=credit.credit_id,
                reusable=True,
                payload={"response": response, "model": credit.metadata.get("model")},
                avoided_tokens_estimate=credit.avoided_tokens_estimate,
                confidence=credit.confidence,
                reason="cached_answer_replayed",
            )
        if credit.artifact_type == "kv_prefill":
            return RuntimeReplayResult(
                replay_type="kv_prefill",
                credit_id=credit.credit_id,
                reusable=True,
                payload={
                    "model": credit.metadata.get("model"),
                    "tokenizer": credit.metadata.get("tokenizer"),
                    "prompt_prefix_hash": credit.metadata.get("prompt_prefix_hash"),
                    "system_prompt_hash": credit.metadata.get("system_prompt_hash"),
                    "kv_cache_metadata": credit.metadata.get("kv_cache_metadata", {}),
                },
                avoided_tokens_estimate=credit.avoided_tokens_estimate,
                confidence=credit.confidence,
                reason="kv_prefill_replayed",
            )
        payload = {
            "artifact_type": credit.artifact_type,
            "task_class": credit.task_class,
            "repo_fingerprint": credit.repo_fingerprint,
            "policy_version": credit.policy_version,
            "verified_tests": credit.verified_tests,
            "impact_fingerprint_hash": credit.impact_fingerprint_hash,
            "chronicle_lesson_id": credit.chronicle_lesson_id,
            "evidence_packet_id": credit.evidence_packet_id,
            "metadata": credit.metadata,
        }
        answer_credit_id = str(credit.metadata.get("answer_credit_id") or "")
        answer_credit = self.credits.get(answer_credit_id) if answer_credit_id else None
        if answer_credit and answer_credit.is_reusable():
            response = self._load_answer(answer_credit)
            if response is not None:
                payload["answer"] = response
                payload["response"] = response
                payload["answer_credit_id"] = answer_credit.credit_id
        return RuntimeReplayResult(
            replay_type="semantic_credit",
            credit_id=credit.credit_id,
            reusable=True,
            payload=payload,
            avoided_tokens_estimate=credit.avoided_tokens_estimate,
            confidence=credit.confidence,
            reason="semantic_credit_replayed",
        )

    def lookup_reusable_credit(
        self,
        task_class: str,
        repo_fingerprint: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> Optional[SemanticComputeCredit]:
        """Look up a reusable credit matching the task and (optionally) repo fingerprint."""
        candidates = [
            c for c in self.credits.values()
            if c.task_class == task_class and c.is_reusable()
        ]

        # Repository-bound capabilities never match without an exact current
        # repository fingerprint. Engine-level prefills are matched separately.
        if repo_fingerprint is None:
            candidates = [
                c for c in candidates
                if c.artifact_type not in {"verified_capability", "deterministic_transform"}
            ]
        
        if artifact_type:
            candidates = [c for c in candidates if c.artifact_type == artifact_type]
        
        if repo_fingerprint:
            candidates = [c for c in candidates if c.repo_fingerprint == repo_fingerprint]
        
        # Return highest-confidence match
        if candidates:
            return max(candidates, key=lambda c: c.confidence)
        
        return None

    def record_credit_reuse(
        self,
        credit_id: str,
        *,
        measured_tokens_saved: Optional[int] = None,
    ) -> Optional[SemanticComputeCredit]:
        """Record that a credit was reused, updating its statistics."""
        credit = self.credits.get(credit_id)
        if not credit or not credit.is_reusable():
            return None
        
        updated = credit.record_reuse()
        if measured_tokens_saved is not None:
            measured = max(0, int(measured_tokens_saved))
            previous = int(updated.metadata.get("measured_reuse_tokens_saved", 0) or 0)
            metadata = {
                **updated.metadata,
                "measured_reuse_tokens_saved": previous + measured,
                "last_measured_reuse_tokens_saved": measured,
            }
            updated = SemanticComputeCredit(
                credit_id=updated.credit_id,
                artifact_type=updated.artifact_type,
                task_class=updated.task_class,
                repo_fingerprint=updated.repo_fingerprint,
                policy_version=updated.policy_version,
                verified_tests=updated.verified_tests,
                avoided_tokens_estimate=updated.avoided_tokens_estimate,
                confidence=updated.confidence,
                reuse_state=updated.reuse_state,
                impact_fingerprint_hash=updated.impact_fingerprint_hash,
                chronicle_lesson_id=updated.chronicle_lesson_id,
                evidence_packet_id=updated.evidence_packet_id,
                created_at=updated.created_at,
                last_reused_at=updated.last_reused_at,
                reuse_count=updated.reuse_count,
                metadata=metadata,
            )
        self.credits[credit_id] = updated
        self._persist_credit(updated)
        return updated

    def mark_stale(
        self,
        credit_id: str,
        *,
        reason: str = "",
        evidence: Optional[Dict[str, Any]] = None,
    ) -> Optional[SemanticComputeCredit]:
        """Mark a credit as stale (e.g., after repo change or policy update)."""
        credit = self.credits.get(credit_id)
        if not credit:
            return None
        metadata = dict(credit.metadata)
        if reason or evidence:
            metadata["quarantine"] = {
                "reason": reason or "marked_stale",
                "evidence": evidence or {},
                "quarantined_at": datetime.now(timezone.utc).isoformat(),
            }
        
        updated = SemanticComputeCredit(
            credit_id=credit.credit_id,
            artifact_type=credit.artifact_type,
            task_class=credit.task_class,
            repo_fingerprint=credit.repo_fingerprint,
            policy_version=credit.policy_version,
            verified_tests=credit.verified_tests,
            avoided_tokens_estimate=credit.avoided_tokens_estimate,
            confidence=credit.confidence,
            reuse_state="stale",
            impact_fingerprint_hash=credit.impact_fingerprint_hash,
            chronicle_lesson_id=credit.chronicle_lesson_id,
            evidence_packet_id=credit.evidence_packet_id,
            created_at=credit.created_at,
            last_reused_at=credit.last_reused_at,
            reuse_count=credit.reuse_count,
            metadata=metadata,
        )
        self.credits[credit_id] = updated
        self._persist_credit(updated)
        return updated

    def retire_credit(self, credit_id: str) -> Optional[SemanticComputeCredit]:
        """Retire a credit that is no longer relevant."""
        credit = self.credits.get(credit_id)
        if not credit:
            return None
        
        updated = SemanticComputeCredit(
            credit_id=credit.credit_id,
            artifact_type=credit.artifact_type,
            task_class=credit.task_class,
            repo_fingerprint=credit.repo_fingerprint,
            policy_version=credit.policy_version,
            verified_tests=credit.verified_tests,
            avoided_tokens_estimate=credit.avoided_tokens_estimate,
            confidence=credit.confidence,
            reuse_state="retired",
            impact_fingerprint_hash=credit.impact_fingerprint_hash,
            chronicle_lesson_id=credit.chronicle_lesson_id,
            evidence_packet_id=credit.evidence_packet_id,
            created_at=credit.created_at,
            last_reused_at=credit.last_reused_at,
            reuse_count=credit.reuse_count,
            metadata=credit.metadata,
        )
        self.credits[credit_id] = updated
        self._persist_credit(updated)
        return updated

    def compute_stored_inference_value(self) -> StoredInferenceValue:
        """Aggregate all stored credits into the three-tier currency model."""
        live = {"total_credits": 0, "total_avoided_tokens": 0}
        stored = {"kv_prefill": 0, "cached_answer": 0, "route_card": 0, "test_impact_map": 0}
        crystallized = {"verified_capability": 0, "deterministic_transform": 0}
        
        for credit in self.credits.values():
            if credit.is_reusable():
                live["total_credits"] += 1
                live["total_avoided_tokens"] += credit.avoided_tokens_estimate
                
                if credit.artifact_type in stored:
                    stored[credit.artifact_type] += 1
                elif credit.artifact_type in crystallized:
                    crystallized[credit.artifact_type] += 1
        
        return StoredInferenceValue(
            live_compute=live,
            stored_compute=stored,
            crystallized_compute=crystallized,
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Return storage metrics for reporting."""
        total = len(self.credits)
        active = sum(1 for c in self.credits.values() if c.reuse_state == "active")
        stale = sum(1 for c in self.credits.values() if c.reuse_state == "stale")
        retired = sum(1 for c in self.credits.values() if c.reuse_state == "retired")
        
        total_avoided = sum(c.avoided_tokens_estimate for c in self.credits.values() if c.is_reusable())
        total_reuses = sum(c.reuse_count for c in self.credits.values())
        measured_reuse_savings = sum(
            int(c.metadata.get("measured_reuse_tokens_saved", 0) or 0)
            for c in self.credits.values()
        )
        stored_value = self.compute_stored_inference_value()
        stored_by_type = stored_value.stored_compute
        crystallized_by_type = stored_value.crystallized_compute
        
        return {
            "beast_object_type": "durable_inference_storage_metrics",
            "version": "1.0",
            "total_credits": total,
            "active_credits": active,
            "stale_credits": stale,
            "retired_credits": retired,
            "total_avoided_tokens": total_avoided,
            "total_reuse_count": total_reuses,
            "measured_reuse_tokens_saved": measured_reuse_savings,
            "stored_by_type": stored_by_type,
            "crystallized_by_type": crystallized_by_type,
            "kv_prefill_credits": int(stored_by_type.get("kv_prefill") or 0),
            "load_error_count": len(self.load_errors),
            "load_errors": list(self.load_errors),
            "artifact_blob_count": len(list(self.blob_path.glob("*.json"))),
            "indexed_blob_count": len(set(self.credit_blobs.values())),
            "storage_path": str(self.storage_path),
        }

    def garbage_collect(self, *, remove_retired_indexes: bool = False, min_age_seconds: float = 0.0) -> Dict[str, Any]:
        """Delete unreferenced immutable blobs and optionally retired mutable indexes."""
        removed_indexes: List[str] = []
        if remove_retired_indexes:
            for credit_id, credit in list(self.credits.items()):
                if credit.reuse_state != "retired":
                    continue
                try:
                    self._credit_path(credit_id).unlink()
                except FileNotFoundError:
                    pass
                try:
                    self._answer_path(credit_id).unlink()
                except FileNotFoundError:
                    pass
                self.credits.pop(credit_id, None)
                self.credit_blobs.pop(credit_id, None)
                removed_indexes.append(credit_id)

        referenced: set[str] = set()
        for index_file in self.storage_path.glob("*.json"):
            if index_file.name.endswith(".answer.json"):
                continue
            try:
                payload = json.loads(index_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            blob = payload.get("artifact_blob") if isinstance(payload.get("artifact_blob"), dict) else {}
            if blob.get("digest"):
                referenced.add(str(blob["digest"]))
            metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
            if metadata.get("response_blob_digest"):
                referenced.add(str(metadata["response_blob_digest"]))

        removed_blobs: List[str] = []
        now = time.time()
        for blob_file in self.blob_path.glob("*.json"):
            digest = "sha256:" + blob_file.stem
            if digest in referenced or now - blob_file.stat().st_mtime < max(0.0, min_age_seconds):
                continue
            blob_file.unlink()
            removed_blobs.append(digest)
        return {
            "beast_object_type": "durable_inference_gc_report",
            "version": "1.0",
            "referenced_blobs": len(referenced),
            "removed_blobs": removed_blobs,
            "removed_indexes": removed_indexes,
            "remaining_blobs": len(list(self.blob_path.glob("*.json"))),
        }

    @staticmethod
    def _parameter_hash(parameters: Dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(parameters, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _answer_credit_id(prompt_hash: str, model: str, parameter_hash: str) -> str:
        return f"cache_{hashlib.sha256(f'{prompt_hash}:{model}:{parameter_hash}'.encode()).hexdigest()[:16]}"

    def _persist_answer(self, credit_id: str, response: str) -> Dict[str, str]:
        blob = self._store_blob({
            "beast_object_type": "cached_answer_payload",
            "version": "1.0",
            "response": response,
            "response_sha256": "sha256:" + hashlib.sha256(response.encode()).hexdigest(),
        })
        path = self._answer_path(credit_id)
        self._atomic_json(path, {
            "beast_object_type": "cached_answer_payload",
            "version": "1.0",
            "credit_id": credit_id,
            "response": response,
            "response_sha256": "sha256:" + hashlib.sha256(response.encode()).hexdigest(),
            "content_blob": blob,
        })
        return blob

    def _load_answer(self, credit: SemanticComputeCredit) -> Optional[str]:
        blob_ref = credit.metadata.get("response_blob_ref")
        blob_digest = credit.metadata.get("response_blob_digest")
        if blob_ref and blob_digest:
            try:
                envelope = json.loads((self.storage_path / str(blob_ref)).read_text(encoding="utf-8"))
                payload = envelope.get("payload") if isinstance(envelope.get("payload"), dict) else {}
                actual = "sha256:" + hashlib.sha256(self._canonical_bytes(payload)).hexdigest()
                response = payload.get("response")
                if actual == blob_digest == envelope.get("digest") and isinstance(response, str):
                    return response
                return None
            except (OSError, json.JSONDecodeError, TypeError):
                return None
        ref = credit.metadata.get("response_ref")
        if ref:
            path = self.storage_path / str(ref)
            try:
                payload = json.loads(path.read_text())
                response = payload.get("response")
                expected = credit.metadata.get("response_sha256")
                if isinstance(response, str):
                    actual = "sha256:" + hashlib.sha256(response.encode()).hexdigest()
                    if expected and actual != expected:
                        return None
                    return response
            except (OSError, json.JSONDecodeError):
                return None
        legacy = credit.metadata.get("response")
        return legacy if isinstance(legacy, str) else None
