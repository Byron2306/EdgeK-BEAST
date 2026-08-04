from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
import json
import os
from typing import Any, Iterable, Mapping

from .operator_language import AnswerFrame, CandidateMeaning, EvidenceBinding, MeaningCrystal, MeaningResolutionState
from .residual_contracts import canonical_json, sha256_digest, utc_now_iso, validate_digest


NORMALIZE_RE = re.compile(r"\s+")
TOKEN_RE = re.compile(r"[a-z0-9]+")

SEMANTIC_STOP_WORDS = frozenset(
    {
        "a", "about", "an", "and", "are", "can", "current", "currently", "do", "does",
        "for", "give", "how", "i", "is", "it", "me", "my", "now", "of", "please",
        "s", "service", "services", "show", "tell", "the", "to", "up", "what",
        "whats", "with", "you",
    }
)

SEMANTIC_ALIASES = {
    "alive": "status",
    "available": "status",
    "doing": "status",
    "health": "status",
    "healthy": "status",
    "readiness": "status",
    "ready": "status",
    "running": "status",
    "state": "status",
    "states": "status",
    "status": "status",
    "bound": "endpoint",
    "listen": "endpoint",
    "listening": "endpoint",
    "port": "endpoint",
    "ports": "endpoint",
    "route": "endpoint",
    "routes": "endpoint",
    "url": "endpoint",
    "urls": "endpoint",
    "where": "endpoint",
    "endpoint": "endpoint",
    "endpoints": "endpoint",
    "commons": "commons",
    "common": "commons",
}


def normalize_utterance(value: str) -> str:
    return NORMALIZE_RE.sub(" ", str(value or "").strip().casefold())


def semantic_intent_fingerprint(value: str) -> tuple[str, ...]:
    """Return a deliberately bounded paraphrase fingerprint for BEAST operator prompts.

    This is not open-ended natural-language understanding.  It only folds a
    small, auditable vocabulary of operator-language aliases while keeping
    unknown content in the fingerprint so unrelated requests do not collide.
    """
    terms: set[str] = set()
    for token in TOKEN_RE.findall(normalize_utterance(value)):
        canonical = SEMANTIC_ALIASES.get(token, token)
        if canonical in SEMANTIC_STOP_WORDS:
            continue
        terms.add(canonical)
    if not terms:
        terms.add("empty-utterance")
    return tuple(sorted(terms))


@dataclass(frozen=True, slots=True)
class SemanticReuseKey:
    semantic_fingerprint_digest: str
    normalized_utterance_digest: str
    schema_digest: str
    discourse_digest: str
    world_digest: str
    capability_digest: str
    evidence_digest: str
    policy_digest: str
    temporal_scope_digest: str

    def __post_init__(self) -> None:
        for name in (
            "semantic_fingerprint_digest", "normalized_utterance_digest", "schema_digest", "discourse_digest",
            "world_digest", "capability_digest", "evidence_digest",
            "policy_digest", "temporal_scope_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)

    @property
    def key_digest(self) -> str:
        return sha256_digest(self)

    @property
    def semantic_match_digest(self) -> str:
        return sha256_digest(
            {
                "semantic_fingerprint_digest": self.semantic_fingerprint_digest,
                "schema_digest": self.schema_digest,
                "discourse_digest": self.discourse_digest,
                "world_digest": self.world_digest,
                "capability_digest": self.capability_digest,
                "evidence_digest": self.evidence_digest,
                "policy_digest": self.policy_digest,
                "temporal_scope_digest": self.temporal_scope_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class SemanticEpisode:
    episode_id: str
    utterance: str
    meaning: CandidateMeaning
    answer_frame: AnswerFrame
    schema_digest: str
    discourse_digest: str
    world_digest: str
    capability_digest: str
    evidence_digest: str
    policy_digest: str
    temporal_scope_digest: str
    verification_evidence_digest: str
    verified: bool
    provider_calls: int = 0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.episode_id.strip() or not self.utterance.strip():
            raise ValueError("semantic episodes require identity and utterance")
        for name in (
            "schema_digest", "discourse_digest", "world_digest", "capability_digest",
            "evidence_digest", "policy_digest", "temporal_scope_digest",
            "verification_evidence_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        if self.provider_calls < 0:
            raise ValueError("provider_calls must be non-negative")
        if self.meaning.resolution_state is not MeaningResolutionState.RESOLVED:
            raise ValueError("semantic promotion episodes require resolved meanings")
        if self.answer_frame.resolution_state is not MeaningResolutionState.RESOLVED:
            raise ValueError("semantic promotion episodes require resolved answer frames")
        if self.answer_frame.meaning_digest != self.meaning.meaning_digest:
            raise ValueError("answer frame is not bound to episode meaning")
        if not self.verified:
            raise ValueError("semantic promotion episodes must be verified")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def normalized_utterance_digest(self) -> str:
        return sha256_digest(normalize_utterance(self.utterance))

    @property
    def semantic_fingerprint_digest(self) -> str:
        return sha256_digest(semantic_intent_fingerprint(self.utterance))

    @property
    def reuse_key(self) -> SemanticReuseKey:
        return SemanticReuseKey(
            semantic_fingerprint_digest=self.semantic_fingerprint_digest,
            normalized_utterance_digest=self.normalized_utterance_digest,
            schema_digest=self.schema_digest,
            discourse_digest=self.discourse_digest,
            world_digest=self.world_digest,
            capability_digest=self.capability_digest,
            evidence_digest=self.evidence_digest,
            policy_digest=self.policy_digest,
            temporal_scope_digest=self.temporal_scope_digest,
        )

    @property
    def episode_digest(self) -> str:
        return sha256_digest(self)


@dataclass(frozen=True, slots=True)
class SemanticPromotionReceipt:
    crystal_id: str
    semantic_key_digest: str
    episode_digests: tuple[str, ...]
    meaning_digest: str
    answer_frame_digest: str
    verification_evidence_digest: str
    provider_calls_observed: int
    promoted: bool
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.crystal_id.strip():
            raise ValueError("semantic promotion receipt requires crystal_id")
        for name in (
            "semantic_key_digest", "meaning_digest", "answer_frame_digest",
            "verification_evidence_digest",
        ):
            validate_digest(getattr(self, name), field_name=name)
        for digest in self.episode_digests:
            validate_digest(digest, field_name="episode_digest")
        if self.provider_calls_observed < 0:
            raise ValueError("provider_calls_observed must be non-negative")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def receipt_digest(self) -> str:
        return sha256_digest(self)


class SemanticCrystalLifecycleState(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class SemanticCrystalRecord:
    crystal: MeaningCrystal
    semantic_reuse_key: SemanticReuseKey
    semantic_key_digest: str
    promotion_receipt_digest: str
    promotion_receipt: SemanticPromotionReceipt
    lifecycle_state: SemanticCrystalLifecycleState = SemanticCrystalLifecycleState.ACTIVE
    appraisal_digest: str = ""
    expires_at: str | None = None
    verifier_version: str = "semantic-generalizer.v1"
    revoked_reason: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle_state, SemanticCrystalLifecycleState):
            object.__setattr__(self, "lifecycle_state", SemanticCrystalLifecycleState(self.lifecycle_state))
        if self.semantic_key_digest != self.semantic_reuse_key.semantic_match_digest:
            raise ValueError("semantic crystal record key digest does not match sealed reuse key")
        validate_digest(self.semantic_key_digest, field_name="semantic_key_digest")
        validate_digest(self.promotion_receipt_digest, field_name="promotion_receipt_digest")
        if self.promotion_receipt.receipt_digest != self.promotion_receipt_digest:
            raise ValueError("semantic crystal record promotion receipt digest mismatch")
        if self.promotion_receipt.semantic_key_digest != self.semantic_key_digest:
            raise ValueError("promotion receipt does not bind the same semantic key")
        if self.promotion_receipt.crystal_id != self.crystal.crystal_id:
            raise ValueError("promotion receipt does not bind the same crystal")
        if self.crystal.schema_digest != self.semantic_reuse_key.schema_digest:
            raise ValueError("crystal schema digest is not bound to semantic reuse key")
        if self.crystal.discourse_digest != self.semantic_reuse_key.discourse_digest:
            raise ValueError("crystal discourse digest is not bound to semantic reuse key")
        if self.crystal.world_digest != self.semantic_reuse_key.world_digest:
            raise ValueError("crystal world digest is not bound to semantic reuse key")
        if self.crystal.capability_digest != self.semantic_reuse_key.capability_digest:
            raise ValueError("crystal capability digest is not bound to semantic reuse key")
        if self.crystal.policy_digest != self.semantic_reuse_key.policy_digest:
            raise ValueError("crystal policy digest is not bound to semantic reuse key")
        if self.crystal.temporal_scope_digest != self.semantic_reuse_key.temporal_scope_digest:
            raise ValueError("crystal temporal scope digest is not bound to semantic reuse key")
        if self.appraisal_digest:
            validate_digest(self.appraisal_digest, field_name="appraisal_digest")
        if not self.verifier_version.strip():
            raise ValueError("semantic crystal record requires verifier_version")
        if self.lifecycle_state is SemanticCrystalLifecycleState.REVOKED and not self.revoked_reason.strip():
            raise ValueError("revoked semantic crystal records require revoked_reason")
        if not self.created_at:
            object.__setattr__(self, "created_at", utc_now_iso())

    @property
    def record_digest(self) -> str:
        return sha256_digest(self)

    def revoke(self, reason: str) -> "SemanticCrystalRecord":
        if not reason.strip():
            raise ValueError("semantic crystal revocation requires a reason")
        return replace(self, lifecycle_state=SemanticCrystalLifecycleState.REVOKED, revoked_reason=reason)


@dataclass(frozen=True, slots=True)
class SemanticReplayOutcome:
    reused: bool
    answer_frame: AnswerFrame | None
    receipt_digest: str
    provider_called: bool
    refusal_reason: str = ""


class SemanticGeneralizer:
    def __init__(self, *, minimum_verified_episodes: int = 2) -> None:
        if minimum_verified_episodes < 2:
            raise ValueError("minimum_verified_episodes must be at least two")
        self.minimum_verified_episodes = int(minimum_verified_episodes)

    def promote(
        self,
        episodes: Iterable[SemanticEpisode],
        *,
        crystal_id: str,
        verifier_id: str,
    ) -> tuple[MeaningCrystal, SemanticPromotionReceipt]:
        record = self.promote_record(episodes, crystal_id=crystal_id, verifier_id=verifier_id)
        return record.crystal, record.promotion_receipt

    def promote_record(
        self,
        episodes: Iterable[SemanticEpisode],
        *,
        crystal_id: str,
        verifier_id: str,
        expires_at: str | None = None,
        verifier_version: str = "semantic-generalizer.v1",
    ) -> SemanticCrystalRecord:
        values = sorted(tuple(episodes), key=lambda item: item.episode_id)
        if len(values) < self.minimum_verified_episodes:
            raise ValueError(f"at least {self.minimum_verified_episodes} verified semantic episodes are required")
        key = values[0].reuse_key
        meaning_digest = self._stable_meaning_digest(values[0].meaning)
        frame_digest = self._stable_answer_frame_digest(values[0].answer_frame, meaning_digest)
        for episode in values[1:]:
            mismatched = self._mismatched_key_fields(key, episode.reuse_key, include_surface=False)
            if mismatched:
                raise ValueError("semantic episodes do not share one reuse key: " + ", ".join(mismatched))
            episode_meaning_digest = self._stable_meaning_digest(episode.meaning)
            if episode_meaning_digest != meaning_digest:
                raise ValueError("semantic episodes do not share one candidate meaning")
            if self._stable_answer_frame_digest(episode.answer_frame, episode_meaning_digest) != frame_digest:
                raise ValueError("semantic episodes do not share one answer frame")
        verification_evidence_digest = sha256_digest(
            {
                "episode_verification": [item.verification_evidence_digest for item in values],
                "semantic_key": key.semantic_match_digest,
            }
        )
        crystal = MeaningCrystal(
            crystal_id=crystal_id,
            meaning=values[0].meaning,
            answer_frame=values[0].answer_frame,
            schema_digest=key.schema_digest,
            discourse_digest=key.discourse_digest,
            world_digest=key.world_digest,
            capability_digest=key.capability_digest,
            policy_digest=key.policy_digest,
            temporal_scope_digest=key.temporal_scope_digest,
            verifier_id=verifier_id,
            verification_evidence_digest=verification_evidence_digest,
        )
        receipt = SemanticPromotionReceipt(
            crystal_id=crystal_id,
            semantic_key_digest=key.semantic_match_digest,
            episode_digests=tuple(item.episode_digest for item in values),
            meaning_digest=meaning_digest,
            answer_frame_digest=frame_digest,
            verification_evidence_digest=verification_evidence_digest,
            provider_calls_observed=sum(item.provider_calls for item in values),
            promoted=True,
        )
        appraisal_digest = sha256_digest({
            "authority": "semantic-generalizer",
            "crystal_id": crystal_id,
            "semantic_key_digest": key.semantic_match_digest,
            "promotion_receipt_digest": receipt.receipt_digest,
            "verifier_version": verifier_version,
            "expires_at": expires_at,
        })
        return SemanticCrystalRecord(
            crystal=crystal,
            semantic_reuse_key=key,
            semantic_key_digest=key.semantic_match_digest,
            promotion_receipt_digest=receipt.receipt_digest,
            promotion_receipt=receipt,
            appraisal_digest=appraisal_digest,
            expires_at=expires_at,
            verifier_version=verifier_version,
        )

    def replay(
        self,
        crystal: MeaningCrystal,
        request_key: SemanticReuseKey,
        *,
        expected_key_digest: str,
        active_negative_conditions: tuple[str, ...] = (),
        provider_enabled: bool = False,
    ) -> SemanticReplayOutcome:
        validate_digest(expected_key_digest, field_name="expected_key_digest")
        if expected_key_digest not in {request_key.key_digest, request_key.semantic_match_digest}:
            return self._refuse("semantic request key digest was not the reviewed key", provider_enabled)
        crystal_key = SemanticReuseKey(
            semantic_fingerprint_digest=request_key.semantic_fingerprint_digest,
            normalized_utterance_digest=request_key.normalized_utterance_digest,
            schema_digest=crystal.schema_digest,
            discourse_digest=crystal.discourse_digest,
            world_digest=crystal.world_digest,
            capability_digest=crystal.capability_digest,
            evidence_digest=request_key.evidence_digest,
            policy_digest=crystal.policy_digest,
            temporal_scope_digest=crystal.temporal_scope_digest,
        )
        mismatched = self._mismatched_key_fields(crystal_key, request_key, include_surface=False)
        if mismatched:
            return self._refuse("semantic reuse key mismatch: " + ", ".join(mismatched), provider_enabled)
        active = set(active_negative_conditions)
        blocked = sorted(set(crystal.meaning.negative_conditions) & active)
        if blocked:
            return self._refuse("negative applicability condition matched: " + ", ".join(blocked), provider_enabled)
        return SemanticReplayOutcome(
            reused=True,
            answer_frame=crystal.answer_frame,
            receipt_digest=sha256_digest(
                {
                    "status": "semantic_reuse_verified",
                    "crystal_digest": crystal.crystal_digest,
                    "request_key": request_key.key_digest,
                    "provider_enabled": provider_enabled,
                    "provider_called": False,
                }
            ),
            provider_called=False,
        )

    def replay_record(
        self,
        record: SemanticCrystalRecord,
        request_key: SemanticReuseKey,
        *,
        active_negative_conditions: tuple[str, ...] = (),
        provider_enabled: bool = False,
        now: str | None = None,
        verifier_version: str = "semantic-generalizer.v1",
    ) -> SemanticReplayOutcome:
        if record.lifecycle_state is SemanticCrystalLifecycleState.REVOKED:
            return self._refuse("semantic crystal revoked: " + record.revoked_reason, provider_enabled)
        if record.expires_at is not None and (now or utc_now_iso()) >= record.expires_at:
            return self._refuse("semantic crystal expired", provider_enabled)
        if record.verifier_version != verifier_version:
            return self._refuse("semantic verifier version drift", provider_enabled)
        mismatched = self._mismatched_key_fields(record.semantic_reuse_key, request_key, include_surface=False)
        if mismatched:
            return self._refuse("semantic reuse key mismatch: " + ", ".join(mismatched), provider_enabled)
        active = set(active_negative_conditions)
        blocked = sorted(set(record.crystal.meaning.negative_conditions) & active)
        if blocked:
            return self._refuse("negative applicability condition matched: " + ", ".join(blocked), provider_enabled)
        return SemanticReplayOutcome(
            reused=True,
            answer_frame=record.crystal.answer_frame,
            receipt_digest=sha256_digest(
                {
                    "status": "semantic_reuse_verified",
                    "record_digest": record.record_digest,
                    "request_key": request_key.key_digest,
                    "semantic_key_digest": record.semantic_key_digest,
                    "promotion_receipt_digest": record.promotion_receipt_digest,
                    "provider_enabled": provider_enabled,
                    "provider_called": False,
                }
            ),
            provider_called=False,
        )

    @staticmethod
    def _mismatched_key_fields(
        left: SemanticReuseKey,
        right: SemanticReuseKey,
        *,
        include_surface: bool = True,
    ) -> tuple[str, ...]:
        names = (
            "semantic_fingerprint_digest", "normalized_utterance_digest", "schema_digest", "discourse_digest",
            "world_digest", "capability_digest", "evidence_digest", "policy_digest", "temporal_scope_digest",
        )
        if not include_surface:
            names = tuple(name for name in names if name != "normalized_utterance_digest")
        return tuple(
            name
            for name in names
            if getattr(left, name) != getattr(right, name)
        )

    @staticmethod
    def _stable_meaning_digest(meaning: CandidateMeaning) -> str:
        return sha256_digest(
            {
                "meaning_id": meaning.meaning_id,
                "domain": meaning.domain,
                "intent": meaning.intent,
                "slots": meaning.slots,
                "evidence": tuple(item.binding_digest for item in meaning.evidence),
                "resolution_state": meaning.resolution_state,
                "confidence": meaning.confidence,
                "negative_conditions": meaning.negative_conditions,
            }
        )

    @staticmethod
    def _stable_answer_frame_digest(frame: AnswerFrame, stable_meaning_digest: str) -> str:
        return sha256_digest(
            {
                "frame_id": frame.frame_id,
                "meaning_digest": stable_meaning_digest,
                "template_id": frame.template_id,
                "slots": frame.slots,
                "evidence_digests": frame.evidence_digests,
                "resolution_state": frame.resolution_state,
                "unresolved_fields": frame.unresolved_fields,
            }
        )

    @staticmethod
    def _refuse(reason: str, provider_enabled: bool) -> SemanticReplayOutcome:
        return SemanticReplayOutcome(
            reused=False,
            answer_frame=None,
            receipt_digest=sha256_digest({"status": "semantic_reuse_refused", "reason": reason}),
            provider_called=False,
            refusal_reason=reason if not provider_enabled else reason + "; provider fallback remains governed separately",
        )


class SemanticCrystalRegistry:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, SemanticCrystalRecord] = {}

    def promote(self, record: SemanticCrystalRecord) -> SemanticCrystalRecord:
        self._records[record.crystal.crystal_id] = record
        self._persist()
        return record

    def get(self, crystal_id: str) -> SemanticCrystalRecord | None:
        return self._records.get(crystal_id)

    def records(self) -> tuple[SemanticCrystalRecord, ...]:
        return tuple(sorted(self._records.values(), key=lambda item: item.crystal.crystal_id))

    def revoke(self, crystal_id: str, *, reason: str) -> SemanticCrystalRecord:
        record = self._records.get(crystal_id)
        if record is None:
            raise KeyError(f"unknown semantic crystal: {crystal_id}")
        revoked = record.revoke(reason)
        self._records[crystal_id] = revoked
        self._persist()
        return revoked

    def load(self) -> None:
        self._records.clear()
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            # Full MeaningCrystal records are dataclass-heavy and intentionally
            # kept in-memory for now.  The durable file is a tamper-evident
            # lifecycle index that prevents silent loss of promotion/revocation
            # receipts while avoiding an unsafe partial deserializer.
            row = json.loads(line)
            if not isinstance(row, Mapping):
                continue
            if not str(row.get("record_digest") or "").startswith("sha256:"):
                continue
            payload = row.get("record_payload")
            if isinstance(payload, Mapping):
                try:
                    record = self._record_from_payload(payload)
                except (TypeError, ValueError, KeyError):
                    continue
                if record.record_digest == row.get("record_digest"):
                    self._records[record.crystal.crystal_id] = record

    def _persist(self) -> None:
        rows = [
            {
                "crystal_id": record.crystal.crystal_id,
                "semantic_key_digest": record.semantic_key_digest,
                "promotion_receipt_digest": record.promotion_receipt_digest,
                "record_digest": record.record_digest,
                "lifecycle_state": record.lifecycle_state.value,
                "appraisal_digest": record.appraisal_digest,
                "expires_at": record.expires_at,
                "verifier_version": record.verifier_version,
                "revoked_reason": record.revoked_reason,
                "record_payload": json.loads(canonical_json(record)),
            }
            for record in sorted(self._records.values(), key=lambda item: item.crystal.crystal_id)
        ]
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text("\n".join(canonical_json(row) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
        os.replace(temporary, self.path)

    @staticmethod
    def _record_from_payload(payload: Mapping[str, Any]) -> SemanticCrystalRecord:
        crystal_payload = dict(payload["crystal"])
        meaning_payload = dict(crystal_payload["meaning"])
        answer_payload = dict(crystal_payload["answer_frame"])
        key_payload = dict(payload["semantic_reuse_key"])
        receipt_payload = dict(payload["promotion_receipt"])
        meaning = CandidateMeaning(
            meaning_id=str(meaning_payload["meaning_id"]),
            domain=meaning_payload["domain"],
            intent=str(meaning_payload["intent"]),
            slots=dict(meaning_payload.get("slots") or {}),
            evidence=tuple(
                EvidenceBinding(
                    evidence_digest=str(item["evidence_digest"]),
                    source=str(item["source"]),
                    world_digest=str(item["world_digest"]),
                    policy_digest=str(item["policy_digest"]),
                    temporal_scope_digest=str(item["temporal_scope_digest"]),
                )
                for item in meaning_payload.get("evidence", ())
            ),
            resolution_state=meaning_payload["resolution_state"],
            confidence=float(meaning_payload["confidence"]),
            negative_conditions=tuple(str(item) for item in meaning_payload.get("negative_conditions", ())),
            created_at=str(meaning_payload.get("created_at") or ""),
        )
        answer_frame = AnswerFrame(
            frame_id=str(answer_payload["frame_id"]),
            meaning_digest=str(answer_payload["meaning_digest"]),
            template_id=str(answer_payload["template_id"]),
            slots=dict(answer_payload.get("slots") or {}),
            evidence_digests=tuple(str(item) for item in answer_payload.get("evidence_digests", ())),
            resolution_state=answer_payload["resolution_state"],
            unresolved_fields=tuple(str(item) for item in answer_payload.get("unresolved_fields", ())),
            created_at=str(answer_payload.get("created_at") or ""),
        )
        crystal = MeaningCrystal(
            crystal_id=str(crystal_payload["crystal_id"]),
            meaning=meaning,
            answer_frame=answer_frame,
            schema_digest=str(crystal_payload["schema_digest"]),
            discourse_digest=str(crystal_payload["discourse_digest"]),
            world_digest=str(crystal_payload["world_digest"]),
            capability_digest=str(crystal_payload["capability_digest"]),
            policy_digest=str(crystal_payload["policy_digest"]),
            temporal_scope_digest=str(crystal_payload["temporal_scope_digest"]),
            verifier_id=str(crystal_payload["verifier_id"]),
            verification_evidence_digest=str(crystal_payload["verification_evidence_digest"]),
            expires_at=crystal_payload.get("expires_at"),
            created_at=str(crystal_payload.get("created_at") or ""),
        )
        reuse_key = SemanticReuseKey(
            semantic_fingerprint_digest=str(key_payload["semantic_fingerprint_digest"]),
            normalized_utterance_digest=str(key_payload["normalized_utterance_digest"]),
            schema_digest=str(key_payload["schema_digest"]),
            discourse_digest=str(key_payload["discourse_digest"]),
            world_digest=str(key_payload["world_digest"]),
            capability_digest=str(key_payload["capability_digest"]),
            evidence_digest=str(key_payload["evidence_digest"]),
            policy_digest=str(key_payload["policy_digest"]),
            temporal_scope_digest=str(key_payload["temporal_scope_digest"]),
        )
        promotion_receipt = SemanticPromotionReceipt(
            crystal_id=str(receipt_payload["crystal_id"]),
            semantic_key_digest=str(receipt_payload["semantic_key_digest"]),
            episode_digests=tuple(str(item) for item in receipt_payload.get("episode_digests", ())),
            meaning_digest=str(receipt_payload["meaning_digest"]),
            answer_frame_digest=str(receipt_payload["answer_frame_digest"]),
            verification_evidence_digest=str(receipt_payload["verification_evidence_digest"]),
            provider_calls_observed=int(receipt_payload["provider_calls_observed"]),
            promoted=bool(receipt_payload["promoted"]),
            created_at=str(receipt_payload.get("created_at") or ""),
        )
        return SemanticCrystalRecord(
            crystal=crystal,
            semantic_reuse_key=reuse_key,
            semantic_key_digest=str(payload["semantic_key_digest"]),
            promotion_receipt_digest=str(payload["promotion_receipt_digest"]),
            promotion_receipt=promotion_receipt,
            lifecycle_state=payload.get("lifecycle_state", SemanticCrystalLifecycleState.ACTIVE.value),
            appraisal_digest=str(payload.get("appraisal_digest") or ""),
            expires_at=payload.get("expires_at"),
            verifier_version=str(payload.get("verifier_version") or "semantic-generalizer.v1"),
            revoked_reason=str(payload.get("revoked_reason") or ""),
            created_at=str(payload.get("created_at") or ""),
        )
