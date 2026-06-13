"""
EdgeK BEAST Gateway - Trace Miner
Extracts patterns from successful execution traces for skill discovery
"""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class TraceEvent:
    """Represents a single event in an execution trace"""
    event_type: str  # e.g., "tool_call", "file_read", "file_write", "reasoning"
    tool_name: Optional[str]  # For tool calls
    input_hash: str  # Hash of input parameters
    output_hash: str  # Hash of output
    duration_ms: float
    timestamp: str
    success: bool
    metadata: Dict[str, Any]


@dataclass
class ExecutionTrace:
    """Represents a complete execution trace"""
    trace_id: str
    session_id: str
    events: List[TraceEvent]
    start_time: str
    end_time: str
    overall_success: bool
    metadata: Dict[str, Any]


class TraceMiner:
    """
    Mines execution traces to discover reusable patterns.
    Extracts successful sequences of operations that can be turned into skills.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "traces.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema for traces"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Traces table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                overall_success INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            )
        """)

        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trace_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                tool_name TEXT,
                input_hash TEXT NOT NULL,
                output_hash TEXT NOT NULL,
                duration_ms REAL DEFAULT 0.0,
                timestamp TEXT NOT NULL,
                success INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (trace_id) REFERENCES traces(trace_id)
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_trace ON trace_events(trace_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_type ON trace_events(event_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_tool ON trace_events(tool_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_traces_success ON traces(overall_success)
        """)

        conn.commit()
        conn.close()

    def record_trace(self, trace: ExecutionTrace) -> str:
        """Record a complete execution trace"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Insert trace
        cursor.execute("""
            INSERT INTO traces (trace_id, session_id, start_time, end_time, overall_success, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            trace.trace_id,
            trace.session_id,
            trace.start_time,
            trace.end_time,
            1 if trace.overall_success else 0,
            json.dumps(trace.metadata),
            datetime.utcnow().isoformat()
        ))

        # Insert events
        for event in trace.events:
            cursor.execute("""
                INSERT INTO trace_events (trace_id, event_type, tool_name, input_hash, output_hash,
                                          duration_ms, timestamp, success, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                event.event_type,
                event.tool_name,
                event.input_hash,
                event.output_hash,
                event.duration_ms,
                event.timestamp,
                1 if event.success else 0,
                json.dumps(event.metadata)
            ))

        conn.commit()
        conn.close()

        logger.info(f"Recorded trace {trace.trace_id} with {len(trace.events)} events")
        return trace.trace_id

    def get_successful_traces(self, limit: int = 100) -> List[ExecutionTrace]:
        """Retrieve successful traces for pattern mining"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("""
            SELECT trace_id, session_id, start_time, end_time, overall_success, metadata
            FROM traces
            WHERE overall_success = 1
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        traces = []
        for row in cursor.fetchall():
            trace_id, session_id, start_time, end_time, success, metadata = row

            # Get events for this trace
            cursor.execute("""
                SELECT event_type, tool_name, input_hash, output_hash, duration_ms, timestamp, success, metadata
                FROM trace_events
                WHERE trace_id = ?
                ORDER BY timestamp ASC
            """, (trace_id,))

            events = []
            for event_row in cursor.fetchall():
                event_type, tool_name, input_hash, output_hash, duration_ms, timestamp, event_success, event_metadata = event_row
                events.append(TraceEvent(
                    event_type=event_type,
                    tool_name=tool_name,
                    input_hash=input_hash,
                    output_hash=output_hash,
                    duration_ms=duration_ms,
                    timestamp=timestamp,
                    success=bool(event_success),
                    metadata=json.loads(event_metadata)
                ))

            traces.append(ExecutionTrace(
                trace_id=trace_id,
                session_id=session_id,
                events=events,
                start_time=start_time,
                end_time=end_time,
                overall_success=bool(success),
                metadata=json.loads(metadata)
            ))

        conn.close()
        return traces

    def extract_tool_sequences(self, traces: List[ExecutionTrace]) -> Dict[str, List[List[str]]]:
        """
        Extract sequences of tool calls from traces.
        Returns: {session_id: [[tool_name1, tool_name2, ...], ...]}
        """
        sequences = defaultdict(list)

        for trace in traces:
            tool_sequence = []
            for event in trace.events:
                if event.event_type == "tool_call" and event.tool_name:
                    tool_sequence.append(event.tool_name)
            if tool_sequence:
                sequences[trace.session_id].append(tool_sequence)

        return dict(sequences)

    def extract_input_output_patterns(self, traces: List[ExecutionTrace]) -> List[Dict[str, Any]]:
        """
        Extract input/output patterns from successful traces.
        Returns patterns that consistently produce successful outcomes.
        """
        patterns = []

        for trace in traces:
            for i, event in enumerate(trace.events):
                if event.success and event.event_type == "tool_call":
                    pattern = {
                        "trace_id": trace.trace_id,
                        "event_index": i,
                        "tool_name": event.tool_name,
                        "input_hash": event.input_hash,
                        "output_hash": event.output_hash,
                        "duration_ms": event.duration_ms,
                        "metadata": event.metadata
                    }
                    patterns.append(pattern)

        return patterns

    def find_frequent_tool_pairs(self, traces: List[ExecutionTrace], min_frequency: int = 3) -> List[Dict[str, Any]]:
        """
        Find pairs of tools that frequently appear together in successful traces.
        """
        pair_counts = defaultdict(int)
        pair_traces = defaultdict(list)

        for trace in traces:
            tools = [e.tool_name for e in trace.events if e.event_type == "tool_call" and e.tool_name]
            seen_pairs = set()

            for i in range(len(tools)):
                for j in range(i + 1, len(tools)):
                    pair = (tools[i], tools[j])
                    if pair not in seen_pairs:
                        pair_counts[pair] += 1
                        pair_traces[pair].append(trace.trace_id)
                        seen_pairs.add(pair)

        # Filter by minimum frequency
        frequent_pairs = []
        for (tool1, tool2), count in pair_counts.items():
            if count >= min_frequency:
                frequent_pairs.append({
                    "tool1": tool1,
                    "tool2": tool2,
                    "frequency": count,
                    "trace_ids": pair_traces[(tool1, tool2)]
                })

        return sorted(frequent_pairs, key=lambda x: x["frequency"], reverse=True)

    def mine_patterns(self, min_frequency: int = 3) -> Dict[str, Any]:
        """
        Main entry point: mine all patterns from successful traces.
        Returns a comprehensive pattern report.
        """
        traces = self.get_successful_traces()

        if not traces:
            return {"status": "no_data", "message": "No successful traces found for mining"}

        tool_sequences = self.extract_tool_sequences(traces)
        io_patterns = self.extract_input_output_patterns(traces)
        frequent_pairs = self.find_frequent_tool_pairs(traces, min_frequency)

        return {
            "status": "success",
            "traces_analyzed": len(traces),
            "tool_sequences": tool_sequences,
            "input_output_patterns": io_patterns,
            "frequent_tool_pairs": frequent_pairs,
            "min_frequency": min_frequency
        }


class TraceCollector:
    """
    Helper class to collect and build traces during execution.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.events: List[TraceEvent] = []
        self.start_time = datetime.utcnow().isoformat()
        self._event_counter = 0

    def add_event(self, event_type: str, tool_name: Optional[str] = None,
                  input_data: Any = None, output_data: Any = None,
                  duration_ms: float = 0.0, success: bool = True,
                  metadata: Optional[Dict[str, Any]] = None) -> TraceEvent:
        """Add an event to the current trace"""

        input_hash = hashlib.sha256(json.dumps(input_data, sort_keys=True, default=str).encode()).hexdigest()[:16]
        output_hash = hashlib.sha256(json.dumps(output_data, sort_keys=True, default=str).encode()).hexdigest()[:16]

        event = TraceEvent(
            event_type=event_type,
            tool_name=tool_name,
            input_hash=input_hash,
            output_hash=output_hash,
            duration_ms=duration_ms,
            timestamp=datetime.utcnow().isoformat(),
            success=success,
            metadata=metadata or {}
        )

        self.events.append(event)
        self._event_counter += 1
        return event

    def build_trace(self, overall_success: bool = True, metadata: Optional[Dict[str, Any]] = None) -> ExecutionTrace:
        """Build the final execution trace"""
        trace_id = f"trace_{self.session_id}_{hashlib.sha256(self.start_time.encode()).hexdigest()[:12]}"
        end_time = datetime.utcnow().isoformat()

        return ExecutionTrace(
            trace_id=trace_id,
            session_id=self.session_id,
            events=self.events,
            start_time=self.start_time,
            end_time=end_time,
            overall_success=overall_success,
            metadata=metadata or {}
        )
