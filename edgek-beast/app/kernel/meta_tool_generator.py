"""
Meta-Tool Candidate Generator for Phase 7 Skill Tree & Meta-Tools system.
Analyzes frequent sequences from the Sequence Detector to generate new skill candidates.
"""

import json
import sqlite3
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class MetaToolCandidate:
    """Represents a candidate meta-tool generated from frequent sequences."""
    candidate_id: str
    name: str
    description: str
    source_sequence: List[str]
    frequency: int
    confidence_score: float
    suggested_parameters: Dict[str, Any]
    usage_examples: List[str]
    tags: List[str]
    created_at: str
    approval_status: str = "candidate"

class MetaToolGenerator:
    """Generates meta-tool candidates from frequent tool usage sequences."""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            self.db_path = str(Path(__file__).resolve().parents[2] / "data" / "skills.db")
        else:
            self.db_path = db_path
        
        self._ensure_tables()
    
    def _ensure_tables(self):
        """Ensure the meta-tool candidate tables exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meta_tool_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    source_sequence TEXT,  -- JSON array of tool names
                    frequency INTEGER,
                    confidence_score REAL,
                    suggested_parameters TEXT,  -- JSON object
                    usage_examples TEXT,  -- JSON array
                    tags TEXT,  -- JSON array
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approval_status TEXT DEFAULT 'candidate'
                )
            """)
            self._ensure_column(conn, "meta_tool_candidates", "approval_status", "TEXT DEFAULT 'candidate'")
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_meta_tool_frequency 
                ON meta_tool_candidates(frequency DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_meta_tool_confidence 
                ON meta_tool_candidates(confidence_score DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_meta_tool_approval_status
                ON meta_tool_candidates(approval_status)
            """)

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, definition: str):
        columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    
    def generate_candidates_from_sequences(self, min_frequency: int = 3, 
                                         min_confidence: float = 0.6) -> List[MetaToolCandidate]:
        """
        Generate meta-tool candidates from frequent sequences in the trace database.
        
        Args:
            min_frequency: Minimum frequency threshold for considering a sequence
            min_confidence: Minimum confidence score for candidate generation
            
        Returns:
            List of MetaToolCandidate objects
        """
        # Get frequent sequences from trace data
        frequent_sequences = self._mine_frequent_sequences(min_frequency)
        
        candidates = []
        for sequence, frequency in frequent_sequences.items():
            if frequency >= min_frequency:
                candidate = self._generate_candidate_from_sequence(sequence, frequency)
                if candidate and candidate.confidence_score >= min_confidence:
                    candidates.append(candidate)
                    self._store_candidate(candidate)
        
        # Sort by confidence score and frequency
        candidates.sort(key=lambda c: (c.confidence_score, c.frequency), reverse=True)
        return candidates

    def generate_candidates_from_patterns(
        self,
        patterns: List[Any],
        min_frequency: int = 3,
        min_confidence: float = 0.6
    ) -> List[MetaToolCandidate]:
        """Generate candidates from SequencePattern-like objects or dictionaries."""
        candidates = []
        for pattern in patterns:
            sequence = getattr(pattern, "sequence", None) or pattern.get("sequence", [])
            frequency = int(getattr(pattern, "frequency", None) or pattern.get("frequency", 0))
            if frequency < min_frequency:
                continue
            candidate = self._generate_candidate_from_sequence(tuple(sequence), frequency)
            if candidate and candidate.confidence_score >= min_confidence:
                candidates.append(candidate)
                self._store_candidate(candidate)
        candidates.sort(key=lambda c: (c.confidence_score, c.frequency), reverse=True)
        return candidates
    
    def _mine_frequent_sequences(self, min_frequency: int) -> Dict[Tuple[str, ...], int]:
        """Mine frequent sequences from execution traces."""
        sequences_counter = Counter()
        
        with sqlite3.connect(self.db_path) as conn:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            if "sequence_patterns" in tables:
                cursor = conn.execute("""
                    SELECT sequence, frequency FROM sequence_patterns
                    WHERE frequency >= ?
                    ORDER BY frequency DESC
                """, (min_frequency,))
                for row in cursor:
                    try:
                        sequence = tuple(json.loads(row[0]))
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if len(sequence) >= 2:
                        sequences_counter[sequence] += int(row[1] or 0)

            if "execution_traces" not in tables:
                return {seq: freq for seq, freq in sequences_counter.items() if freq >= min_frequency}

            cursor = conn.execute("""
                SELECT tool_sequence FROM execution_traces
                WHERE tool_sequence IS NOT NULL AND tool_sequence != '[]'
                ORDER BY timestamp
            """)
            
            for row in cursor:
                try:
                    tool_sequence = json.loads(row[0])
                    if isinstance(tool_sequence, list) and len(tool_sequence) >= 2:
                        # Extract all subsequences of length 2-5
                        for i in range(len(tool_sequence) - 1):
                            for j in range(i + 2, min(i + 6, len(tool_sequence) + 1)):
                                subsequence = tuple(tool_sequence[i:j])
                                sequences_counter[subsequence] += 1
                except (json.JSONDecodeError, TypeError):
                    continue
        
        # Filter by minimum frequency
        return {seq: freq for seq, freq in sequences_counter.items() if freq >= min_frequency}
    
    def _generate_candidate_from_sequence(self, sequence: Tuple[str, ...], 
                                        frequency: int) -> Optional[MetaToolCandidate]:
        """Generate a meta-tool candidate from a frequent sequence."""
        if not sequence or len(sequence) < 2:
            return None
        
        # Generate candidate ID
        sequence_str = json.dumps(list(sequence), sort_keys=True)
        candidate_id = f"meta_{hashlib.sha256(sequence_str.encode()).hexdigest()[:12]}"
        
        # Generate name and description
        name = self._generate_tool_name(sequence)
        description = self._generate_tool_description(sequence, frequency)
        
        # Suggest parameters based on sequence analysis
        suggested_parameters = self._suggest_parameters(sequence)
        
        # Generate usage examples
        usage_examples = self._generate_usage_examples(sequence)
        
        # Generate tags
        tags = self._generate_tags(sequence)
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence_score(sequence, frequency)
        
        return MetaToolCandidate(
            candidate_id=candidate_id,
            name=name,
            description=description,
            source_sequence=list(sequence),
            frequency=frequency,
            confidence_score=confidence_score,
            suggested_parameters=suggested_parameters,
            usage_examples=usage_examples,
            tags=tags,
            created_at=self._get_current_timestamp()
        )
    
    def _generate_tool_name(self, sequence: Tuple[str, ...]) -> str:
        """Generate a descriptive name for the meta-tool."""
        # Take meaningful parts of tool names
        meaningful_parts = []
        for tool in sequence:
            # Remove common suffixes/prefixes
            clean_name = tool.lower()
            for suffix in ['_agent', '_tool', '_service', '_manager', '_controller']:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[:-len(suffix)]
            meaningful_parts.append(clean_name)
        
        # Create compound name
        if len(meaningful_parts) == 2:
            return f"{meaningful_parts[0]}_{meaningful_parts[1]}_orchestrator"
        elif len(meaningful_parts) == 3:
            return f"{meaningful_parts[0]}_{meaningful_parts[1]}_{meaningful_parts[2]}_workflow"
        else:
            return f"multi_step_{'_'.join(meaningful_parts[:3])}_process"
    
    def _generate_tool_description(self, sequence: Tuple[str, ...], frequency: int) -> str:
        """Generate a description for the meta-tool candidate."""
        seq_str = " → ".join(sequence)
        return f"Automated workflow that executes the sequence: {seq_str}. " \
               f"This pattern has been observed {frequency} times in execution traces, " \
               f"suggesting it represents a common operational workflow."
    
    def _suggest_parameters(self, sequence: Tuple[str, ...]) -> Dict[str, Any]:
        """Suggest parameters for the meta-tool based on the sequence."""
        parameters = {
            "execution_mode": "sequential",  # or parallel, conditional
            "timeout_per_step": 30,
            "retry_failed_steps": True,
            "max_retries": 2,
            "continue_on_error": False
        }
        
        # Add sequence-specific parameters
        if any("agent" in tool.lower() for tool in sequence):
            parameters["require_consensus"] = False
            parameters["agent_timeout"] = 60
        
        if any("data" in tool.lower() for tool in sequence):
            parameters["data_validation"] = True
            parameters["output_format"] = "json"
        
        return parameters
    
    def _generate_usage_examples(self, sequence: Tuple[str, ...]) -> List[str]:
        """Generate usage examples for the meta-tool."""
        examples = []
        
        # Basic usage example
        example = f"# Execute the {sequence[0]} → {sequence[-1]} workflow\n"
        example += f"workflow = MetaToolRunner('{sequence[0]}_to_{sequence[-1]}')\n"
        example += f"result = workflow.execute(input_data={{\"param\": \"value\"}})"
        examples.append(example)
        
        # Advanced usage with parameters
        if len(sequence) > 2:
            example = f"# Customized workflow execution\n"
            example += f"workflow = MetaToolRunner('{sequence[0]}_to_{sequence[-1]}', \n"
            example += f"                        timeout_per_step=45, \n"
            example += f"                        retry_failed_steps=True)\n"
            example += 'result = workflow.execute(context={"user_id": "12345"})'
            examples.append(example)
        
        return examples
    
    def _generate_tags(self, sequence: Tuple[str, ...]) -> List[str]:
        """Generate tags for categorizing the meta-tool."""
        tags = ["meta-tool", "generated", "workflow"]
        
        # Add domain-specific tags based on tool names
        tool_names_lower = [tool.lower() for tool in sequence]
        
        if any("data" in name for name in tool_names_lower):
            tags.append("data-processing")
        if any("agent" in name for name in tool_names_lower):
            tags.append("agent-coordination")
        if any("network" in name for name in tool_names_lower):
            tags.append("network-operations")
        if any("security" in name for name in tool_names_lower):
            tags.append("security")
        if any("ui" in name or "interface" in name for name in tool_names_lower):
            tags.append("user-interface")
        if any("exec" in name or "run" in name for name in tool_names_lower):
            tags.append("execution")
        
        return list(set(tags))  # Remove duplicates
    
    def _calculate_confidence_score(self, sequence: Tuple[str, ...], frequency: int) -> float:
        """Calculate confidence score for the meta-tool candidate."""
        # Base score from frequency (logarithmic scale)
        import math
        frequency_score = min(1.0, math.log(frequency) / math.log(100))  # Normalize to 0-1
        
        # Length penalty/bonus - optimal length is 3-4 steps
        length = len(sequence)
        if 3 <= length <= 4:
            length_score = 1.0
        elif length == 2 or length == 5:
            length_score = 0.8
        else:
            length_score = 0.6
        
        # Diversity bonus - different types of tools
        unique_tools = len(set(sequence))
        diversity_score = min(1.0, unique_tools / length) if length > 0 else 0.0
        
        # Combine scores
        confidence = (frequency_score * 0.4) + (length_score * 0.3) + (diversity_score * 0.3)
        return min(1.0, max(0.0, confidence))
    
    def _store_candidate(self, candidate: MetaToolCandidate):
        """Store a meta-tool candidate in the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO meta_tool_candidates 
                (candidate_id, name, description, source_sequence, frequency,
                 confidence_score, suggested_parameters, usage_examples, tags, created_at, approval_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candidate.candidate_id,
                candidate.name,
                candidate.description,
                json.dumps(candidate.source_sequence),
                candidate.frequency,
                candidate.confidence_score,
                json.dumps(candidate.suggested_parameters),
                json.dumps(candidate.usage_examples),
                json.dumps(candidate.tags),
                candidate.created_at,
                candidate.approval_status
            ))
    
    def get_top_candidates(self, limit: int = 10) -> List[MetaToolCandidate]:
        """Get the top meta-tool candidates by confidence score."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM meta_tool_candidates 
                ORDER BY confidence_score DESC, frequency DESC 
                LIMIT ?
            """, (limit,))
            
            candidates = []
            for row in cursor:
                candidate = MetaToolCandidate(
                    candidate_id=row['candidate_id'],
                    name=row['name'],
                    description=row['description'],
                    source_sequence=json.loads(row['source_sequence']),
                    frequency=row['frequency'],
                    confidence_score=row['confidence_score'],
                    suggested_parameters=json.loads(row['suggested_parameters']),
                    usage_examples=json.loads(row['usage_examples']),
                    tags=json.loads(row['tags']),
                    created_at=row['created_at'],
                    approval_status=row['approval_status'] or "candidate"
                )
                candidates.append(candidate)
            
            return candidates
    
    def get_candidate_by_id(self, candidate_id: str) -> Optional[MetaToolCandidate]:
        """Get a specific meta-tool candidate by ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM meta_tool_candidates WHERE candidate_id = ?
            """, (candidate_id,))
            
            row = cursor.fetchone()
            if row:
                return MetaToolCandidate(
                    candidate_id=row['candidate_id'],
                    name=row['name'],
                    description=row['description'],
                    source_sequence=json.loads(row['source_sequence']),
                    frequency=row['frequency'],
                    confidence_score=row['confidence_score'],
                    suggested_parameters=json.loads(row['suggested_parameters']),
                    usage_examples=json.loads(row['usage_examples']),
                    tags=json.loads(row['tags']),
                    created_at=row['created_at'],
                    approval_status=row['approval_status'] or "candidate"
                )
            return None
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def approve_candidate(self, candidate_id: str, approved_by: str = "system") -> bool:
        """Mark a candidate as approved for promotion to a full skill."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE meta_tool_candidates
                SET approval_status = 'approved'
                WHERE candidate_id = ?
            """, (candidate_id,))
            if cursor.rowcount == 0:
                return False
        logger.info(f"Meta-tool candidate {candidate_id} approved by {approved_by}")
        return True
    
    def reject_candidate(self, candidate_id: str, reason: str = "") -> bool:
        """Mark a candidate as rejected."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE meta_tool_candidates
                SET approval_status = 'rejected'
                WHERE candidate_id = ?
            """, (candidate_id,))
            if cursor.rowcount == 0:
                return False
        logger.info(f"Meta-tool candidate {candidate_id} rejected: {reason}")
        return True

# Example usage and testing
if __name__ == "__main__":
    # Initialize the meta-tool generator
    generator = MetaToolGenerator()
    
    # Generate candidates from existing trace data
    print("Generating meta-tool candidates from trace data...")
    candidates = generator.generate_candidates_from_sequences(min_frequency=2, min_confidence=0.5)
    
    print(f"Generated {len(candidates)} meta-tool candidates:")
    for i, candidate in enumerate(candidates[:5], 1):  # Show top 5
        print(f"\n{i}. {candidate.name}")
        print(f"   ID: {candidate.candidate_id}")
        print(f"   Sequence: {' → '.join(candidate.source_sequence)}")
        print(f"   Frequency: {candidate.frequency}")
        print(f"   Confidence: {candidate.confidence_score:.2f}")
        print(f"   Description: {candidate.description}")
        print(f"   Tags: {', '.join(candidate.tags)}")
