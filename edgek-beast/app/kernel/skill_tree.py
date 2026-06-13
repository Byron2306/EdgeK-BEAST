"""
EdgeK BEAST Gateway - Skill Tree Orchestrator
Coordinates trace mining, sequence detection, meta-tool generation, validation,
and user-approved promotion into the skill registry.
"""

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .meta_tool_generator import MetaToolCandidate, MetaToolGenerator
from .sandbox_validator import SandboxValidator, ValidationResult
from .sequence_detector import RepeatedSequenceDetector, SequencePattern
from .skill_registry import SkillRegistry, Skill
from .trace_miner import TraceMiner


def _asdict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _asdict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [_asdict(item) for item in value]
    if isinstance(value, dict):
        return {key: _asdict(item) for key, item in value.items()}
    return value


class SkillTree:
    """Phase 7 facade for learned skills and deterministic meta-tool candidates."""

    def __init__(
        self,
        data_dir: Optional[str] = None,
        trace_miner: Optional[TraceMiner] = None,
        sequence_detector: Optional[RepeatedSequenceDetector] = None,
        meta_tool_generator: Optional[MetaToolGenerator] = None,
        sandbox_validator: Optional[SandboxValidator] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        skill_db = str(self.data_dir / "skills.db")
        self.trace_miner = trace_miner or TraceMiner(str(self.data_dir / "traces.db"))
        self.sequence_detector = sequence_detector or RepeatedSequenceDetector(skill_db)
        self.meta_tool_generator = meta_tool_generator or MetaToolGenerator(skill_db)
        self.sandbox_validator = sandbox_validator or SandboxValidator(skill_db)
        self.skill_registry = skill_registry or SkillRegistry(skill_db)

    def state(self) -> Dict[str, Any]:
        return {
            "skills": self.skill_registry.get_statistics(),
            "patterns": {
                "detected": len(self.sequence_detector.get_stored_patterns()),
                "validated": len(self.sequence_detector.get_stored_patterns(status="validated")),
                "promoted": len(self.sequence_detector.get_stored_patterns(status="promoted")),
            },
            "candidates": [self._candidate_to_dict(item) for item in self.meta_tool_generator.get_top_candidates(limit=10)],
            "storage": {
                "trace_db": str(self.trace_miner.db_path),
                "skill_db": str(self.skill_registry.db_path),
                "sequence_db": str(self.sequence_detector.db_path),
            },
        }

    def mine(
        self,
        sequences: Optional[List[List[str]]] = None,
        min_length: int = 2,
        min_frequency: int = 3,
        use_approximate: bool = True,
        store: bool = True,
    ) -> Dict[str, Any]:
        traces = self.trace_miner.get_successful_traces()
        mined = self.trace_miner.mine_patterns(min_frequency=min_frequency)

        if sequences is None:
            sequences_by_session = mined.get("tool_sequences", {}) if mined.get("status") == "success" else {}
            sequences = [
                sequence
                for session_sequences in sequences_by_session.values()
                for sequence in session_sequences
            ]

        detection = self.sequence_detector.detect_patterns(
            sequences=sequences,
            min_length=min_length,
            min_frequency=min_frequency,
            use_approximate=use_approximate,
        )

        patterns = detection.get("combined_unique_patterns", [])
        stored_pattern_ids = []
        if store:
            for pattern in patterns:
                stored_pattern_ids.append(self.sequence_detector.store_pattern(pattern))

        return {
            "status": detection.get("status"),
            "traces_analyzed": len(traces),
            "sequences_analyzed": detection.get("sequences_analyzed", 0),
            "patterns_detected": len(patterns),
            "stored_pattern_ids": stored_pattern_ids,
            "patterns": [_asdict(pattern) for pattern in patterns],
            "min_length": min_length,
            "min_frequency": min_frequency,
        }

    def generate_candidates(
        self,
        min_frequency: int = 3,
        min_confidence: float = 0.6,
        status: Optional[str] = None,
    ) -> Dict[str, Any]:
        patterns = self.sequence_detector.get_stored_patterns(
            status=status,
            min_confidence=0.0,
        )
        candidates = self.meta_tool_generator.generate_candidates_from_patterns(
            patterns,
            min_frequency=min_frequency,
            min_confidence=min_confidence,
        )
        return {
            "generated": len(candidates),
            "candidates": [self._candidate_to_dict(candidate) for candidate in candidates],
            "min_frequency": min_frequency,
            "min_confidence": min_confidence,
        }

    def list_patterns(self, status: Optional[str] = None, min_confidence: float = 0.0) -> List[Dict[str, Any]]:
        return [
            _asdict(pattern)
            for pattern in self.sequence_detector.get_stored_patterns(
                status=status,
                min_confidence=min_confidence,
            )
        ]

    def list_candidates(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [
            self._candidate_to_dict(candidate)
            for candidate in self.meta_tool_generator.get_top_candidates(limit=limit)
        ]

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        candidate = self.meta_tool_generator.get_candidate_by_id(candidate_id)
        return self._candidate_to_dict(candidate) if candidate else None

    def validate_candidate(
        self,
        candidate_id: str,
        test_scenarios: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        result = self.sandbox_validator.validate_candidate(
            candidate_id,
            test_scenarios=test_scenarios,
        )
        return self._validation_to_dict(result)

    def validation_history(self, candidate_id: str) -> List[Dict[str, Any]]:
        return [
            self._validation_to_dict(result)
            for result in self.sandbox_validator.get_validation_history(candidate_id)
        ]

    def promote_candidate(
        self,
        candidate_id: str,
        approved_by: str = "user",
        require_validation: bool = True,
    ) -> Dict[str, Any]:
        candidate = self.meta_tool_generator.get_candidate_by_id(candidate_id)
        if not candidate:
            raise ValueError(f"Meta-tool candidate not found: {candidate_id}")

        latest_validation = self.sandbox_validator.get_latest_validation(candidate_id)
        if require_validation and (
            not latest_validation or latest_validation.status not in ("passed", "passed_with_warnings")
        ):
            raise ValueError("Candidate must pass sandbox validation before promotion")

        if not self.meta_tool_generator.approve_candidate(candidate_id, approved_by=approved_by):
            raise ValueError(f"Meta-tool candidate not found: {candidate_id}")

        skill = self.skill_registry.register_skill(
            name=candidate.name,
            category="meta_tool",
            pattern={
                "source_sequence": candidate.source_sequence,
                "candidate_id": candidate.candidate_id,
            },
            action={
                "type": "meta_tool_workflow",
                "sequence": candidate.source_sequence,
                "parameters": candidate.suggested_parameters,
            },
            metadata={
                "description": candidate.description,
                "approved_by": approved_by,
                "confidence_score": candidate.confidence_score,
                "frequency": candidate.frequency,
                "tags": candidate.tags,
                "validation": self._validation_to_dict(latest_validation) if latest_validation else None,
            },
        )

        for pattern in self.sequence_detector.get_stored_patterns():
            if pattern.sequence == candidate.source_sequence:
                self.sequence_detector.update_pattern_status(pattern.pattern_id, "promoted")

        return {
            "promoted": True,
            "candidate": self._candidate_to_dict(candidate),
            "skill": self._skill_to_dict(skill),
        }

    def list_skills(self, category: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        return [
            self._skill_to_dict(skill)
            for skill in self.skill_registry.get_skills(category=category, limit=limit)
        ]

    def _candidate_to_dict(self, candidate: Optional[MetaToolCandidate]) -> Dict[str, Any]:
        return _asdict(candidate) if candidate else {}

    def _validation_to_dict(self, result: Optional[ValidationResult]) -> Optional[Dict[str, Any]]:
        return _asdict(result) if result else None

    def _skill_to_dict(self, skill: Skill) -> Dict[str, Any]:
        return _asdict(skill)


skill_tree = SkillTree()
