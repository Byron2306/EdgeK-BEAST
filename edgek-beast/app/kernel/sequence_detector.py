"""
EdgeK BEAST Gateway - Repeated Sequence Detector
Identifies common operation sequences that can be abstracted into meta-tools
"""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set
from collections import defaultdict, Counter
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SequencePattern:
    """Represents a detected repeated sequence pattern"""
    pattern_id: str
    sequence: List[str]  # List of tool names/operations
    frequency: int  # How many times this sequence appears
    contexts: List[str]  # Session IDs or trace IDs where found
    avg_duration_ms: float
    success_rate: float
    confidence: float  # 0.0 to 1.0, how confident we are this is a real pattern


class RepeatedSequenceDetector:
    """
    Detects repeated sequences of operations in execution traces.
    Uses multiple algorithms: exact matching, approximate matching, and sliding window.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "sequences.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema for sequence patterns"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sequence_patterns (
                pattern_id TEXT PRIMARY KEY,
                sequence TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                contexts TEXT DEFAULT '[]',
                avg_duration_ms REAL DEFAULT 0.0,
                success_rate REAL DEFAULT 1.0,
                confidence REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT DEFAULT 'detected'  -- detected, validated, promoted, rejected
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_patterns_freq ON sequence_patterns(frequency)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_patterns_conf ON sequence_patterns(confidence)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_patterns_status ON sequence_patterns(status)
        """)

        conn.commit()
        conn.close()

    def _hash_sequence(self, sequence: List[str]) -> str:
        """Create a hash for a sequence"""
        return hashlib.sha256(json.dumps(sequence, sort_keys=True).encode()).hexdigest()[:16]

    def find_exact_repeats(self, sequences: List[List[str]], min_length: int = 2,
                           min_frequency: int = 3) -> List[SequencePattern]:
        """
        Find exact repeated sequences using a trie-based approach.
        """
        # Build frequency map of all subsequences
        subsequence_counts = defaultdict(lambda: {"count": 0, "contexts": set()})

        for seq_idx, sequence in enumerate(sequences):
            if len(sequence) < min_length:
                continue

            # Generate all possible subsequences of length >= min_length
            for length in range(min_length, len(sequence) + 1):
                for start in range(len(sequence) - length + 1):
                    sub = tuple(sequence[start:start + length])
                    subsequence_counts[sub]["count"] += 1
                    subsequence_counts[sub]["contexts"].add(seq_idx)

        # Filter by minimum frequency
        patterns = []
        for sub, data in subsequence_counts.items():
            if data["count"] >= min_frequency:
                pattern_id = self._hash_sequence(list(sub))
                patterns.append(SequencePattern(
                    pattern_id=pattern_id,
                    sequence=list(sub),
                    frequency=data["count"],
                    contexts=[str(ctx) for ctx in data["contexts"]],
                    avg_duration_ms=0.0,  # Would need trace data for this
                    success_rate=1.0,  # Assume success for exact repeats
                    confidence=min(1.0, data["count"] / min_frequency * 0.5)
                ))

        # Sort by frequency descending, then by length descending
        patterns.sort(key=lambda p: (p.frequency, len(p.sequence)), reverse=True)
        return patterns

    def find_approximate_repeats(self, sequences: List[List[str]], max_edit_distance: int = 1,
                                  min_length: int = 2, min_frequency: int = 3) -> List[SequencePattern]:
        """
        Find approximate repeated sequences using edit distance.
        Groups similar sequences together.
        """
        from collections import defaultdict

        # Normalize sequences
        normalized = []
        for seq in sequences:
            if len(seq) >= min_length:
                normalized.append(tuple(seq))

        # Group by approximate similarity using a simple approach
        groups = []
        used = set()

        for i, seq1 in enumerate(normalized):
            if i in used:
                continue

            group = [seq1]
            used.add(i)

            for j, seq2 in enumerate(normalized[i+1:], start=i+1):
                if j in used:
                    continue

                if self._edit_distance(seq1, seq2) <= max_edit_distance:
                    group.append(seq2)
                    used.add(j)

            if len(group) >= min_frequency:
                # Use the most common sequence as the representative
                representative = Counter(group).most_common(1)[0][0]
                pattern_id = self._hash_sequence(list(representative))

                groups.append(SequencePattern(
                    pattern_id=pattern_id,
                    sequence=list(representative),
                    frequency=len(group),
                    contexts=[str(idx) for idx in range(len(group))],
                    avg_duration_ms=0.0,
                    success_rate=1.0,
                    confidence=min(1.0, len(group) / min_frequency * 0.5)
                ))

        return groups

    def _edit_distance(self, seq1: Tuple[str, ...], seq2: Tuple[str, ...]) -> int:
        """Calculate Levenshtein distance between two sequences"""
        m, n = len(seq1), len(seq2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]

        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if seq1[i-1] == seq2[j-1]:
                    dp[i][j] = dp[i-1][j-1]
                else:
                    dp[i][j] = 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])

        return dp[m][n]

    def find_sliding_window_patterns(self, sequences: List[List[str]],
                                     window_size: int = 3,
                                     min_frequency: int = 3) -> List[SequencePattern]:
        """
        Find patterns using a sliding window approach.
        Good for detecting patterns in longer sequences.
        """
        window_counts = defaultdict(lambda: {"count": 0, "contexts": set()})

        for seq_idx, sequence in enumerate(sequences):
            if len(sequence) < window_size:
                continue

            for i in range(len(sequence) - window_size + 1):
                window = tuple(sequence[i:i + window_size])
                window_counts[window]["count"] += 1
                window_counts[window]["contexts"].add(seq_idx)

        patterns = []
        for window, data in window_counts.items():
            if data["count"] >= min_frequency:
                pattern_id = self._hash_sequence(list(window))
                patterns.append(SequencePattern(
                    pattern_id=pattern_id,
                    sequence=list(window),
                    frequency=data["count"],
                    contexts=[str(ctx) for ctx in data["contexts"]],
                    avg_duration_ms=0.0,
                    success_rate=1.0,
                    confidence=min(1.0, data["count"] / min_frequency * 0.5)
                ))

        patterns.sort(key=lambda p: p.frequency, reverse=True)
        return patterns

    def detect_patterns(self, sequences: List[List[str]],
                         min_length: int = 2,
                         min_frequency: int = 3,
                         use_approximate: bool = True) -> Dict[str, Any]:
        """
        Main entry point: detect all types of repeated patterns.
        """
        if not sequences:
            return {"status": "no_data", "message": "No sequences provided for detection"}

        exact_patterns = self.find_exact_repeats(sequences, min_length, min_frequency)
        sliding_patterns = self.find_sliding_window_patterns(sequences, min_length, min_frequency)

        approximate_patterns = []
        if use_approximate:
            approximate_patterns = self.find_approximate_repeats(sequences, min_length=min_length, min_frequency=min_frequency)

        # Combine and deduplicate
        all_patterns = exact_patterns + sliding_patterns + approximate_patterns
        seen = set()
        unique_patterns = []

        for pattern in all_patterns:
            seq_tuple = tuple(pattern.sequence)
            if seq_tuple not in seen:
                seen.add(seq_tuple)
                unique_patterns.append(pattern)

        # Sort by confidence and frequency
        unique_patterns.sort(key=lambda p: (p.confidence, p.frequency), reverse=True)

        return {
            "status": "success",
            "sequences_analyzed": len(sequences),
            "exact_patterns": exact_patterns,
            "sliding_window_patterns": sliding_patterns,
            "approximate_patterns": approximate_patterns,
            "combined_unique_patterns": unique_patterns,
            "min_length": min_length,
            "min_frequency": min_frequency
        }

    def store_pattern(self, pattern: SequencePattern) -> str:
        """Store a detected pattern in the database"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        now = __import__('datetime').datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT OR REPLACE INTO sequence_patterns
            (pattern_id, sequence, frequency, contexts, avg_duration_ms, success_rate, confidence, created_at, updated_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pattern.pattern_id,
            json.dumps(pattern.sequence),
            pattern.frequency,
            json.dumps(pattern.contexts),
            pattern.avg_duration_ms,
            pattern.success_rate,
            pattern.confidence,
            now,
            now,
            "detected"
        ))

        conn.commit()
        conn.close()

        logger.info(f"Stored sequence pattern: {pattern.pattern_id}")
        return pattern.pattern_id

    def get_stored_patterns(self, status: Optional[str] = None,
                           min_confidence: float = 0.0) -> List[SequencePattern]:
        """Retrieve stored patterns from the database"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        if status:
            cursor.execute("""
                SELECT pattern_id, sequence, frequency, contexts, avg_duration_ms, success_rate, confidence
                FROM sequence_patterns
                WHERE status = ? AND confidence >= ?
                ORDER BY confidence DESC, frequency DESC
            """, (status, min_confidence))
        else:
            cursor.execute("""
                SELECT pattern_id, sequence, frequency, contexts, avg_duration_ms, success_rate, confidence
                FROM sequence_patterns
                WHERE confidence >= ?
                ORDER BY confidence DESC, frequency DESC
            """, (min_confidence,))

        patterns = []
        for row in cursor.fetchall():
            patterns.append(SequencePattern(
                pattern_id=row[0],
                sequence=json.loads(row[1]),
                frequency=row[2],
                contexts=json.loads(row[3]),
                avg_duration_ms=row[4],
                success_rate=row[5],
                confidence=row[6]
            ))

        conn.close()
        return patterns

    def update_pattern_status(self, pattern_id: str, status: str):
        """Update the status of a pattern (detected, validated, promoted, rejected)"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        now = __import__('datetime').datetime.utcnow().isoformat()

        cursor.execute("""
            UPDATE sequence_patterns
            SET status = ?, updated_at = ?
            WHERE pattern_id = ?
        """, (status, now, pattern_id))

        conn.commit()
        conn.close()

        logger.info(f"Updated pattern {pattern_id} status to {status}")
