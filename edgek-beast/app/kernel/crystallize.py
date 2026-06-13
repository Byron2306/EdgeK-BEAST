"""
EdgeK BEAST Gateway - Crystallize Phase of PREC Cycle
Responsible for archiving traces, updating skills, emitting telemetry, and learning from interactions
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import asdict, is_dataclass
from enum import Enum
import logging
from datetime import datetime

from .perceive import EdgeKIR
from .reason import GovernanceResult
from .skill_registry import SkillRegistry
from .workspace_graph import WorkspaceGraph

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Convert dataclasses and enums into JSON-serializable structures."""
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class Crystallizer:
    """Completes the PREC cycle by crystallizing the interaction"""
    
    def __init__(
        self,
        data_dir: Optional[str] = None,
        skill_registry: Optional[SkillRegistry] = None,
        workspace_graph: Optional[WorkspaceGraph] = None
    ):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parents[2] / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.data_dir / "traces.jsonl"
        self.index_path = self.data_dir / "trace_index.db"
        self.skill_registry = skill_registry or SkillRegistry(str(self.data_dir / "skills.db"))
        self.workspace_graph = workspace_graph or WorkspaceGraph(str(self.data_dir / "workspace_graph.db"))

        self.trace_storage = []
        self.skill_updates = []
        self.telemetry_data = []
        self.workspace_graph_updates = []
        self._init_index()

    def _init_index(self):
        with sqlite3.connect(str(self.index_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS traces (
                    trace_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    model TEXT NOT NULL,
                    governance_decision TEXT NOT NULL,
                    estimated_total_tokens INTEGER DEFAULT 0,
                    estimated_cost_usd REAL DEFAULT 0.0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_traces_session_time ON traces(session_id, timestamp)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workspace_interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    provider_type TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    tool_count INTEGER NOT NULL
                )
            """)
        
    async def crystallize(
        self, 
        original_request: Dict[Any, Any],
        ir: EdgeKIR,
        governance_result: GovernanceResult,
        provider_response: Dict[Any, Any],
        session_id: str = "default",
        provider_type: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Complete the PREC cycle by archiving and learning from the interaction
        
        Args:
            original_request: The raw request as received from the client
            ir: The EdgeK Internal Representation (after perception)
            governance_result: Result from the reasoning phase
            provider_response: The response from the provider
            session_id: Identifier for the session
            provider_type: The type of provider used
            
        Returns:
            Dict[str, Any]: Crystallization results including trace ID
        """
        trace_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Create trace record
        trace_record = {
            "trace_id": trace_id,
            "timestamp": timestamp,
            "session_id": session_id,
            "provider_type": provider_type,
            "original_request": original_request,
            "edgek_ir": _json_safe(ir),
            "governance_result": _json_safe(governance_result),
            "provider_response": provider_response,
            "prec_phase": "crystallize"
        }
        
        # Archive trace (L4 forensic archive)
        await self._archive_trace(trace_record)
        
        # Update skills (L3 skill tree)
        await self._update_skills(trace_record)
        
        # Emit telemetry (observability)
        await self._emit_telemetry(trace_record)
        
        # Update workspace graph (L2)
        await self._update_workspace_graph(trace_record)
        
        logger.info(f"Crystallized interaction {trace_id} for session {session_id}")
        
        return {
            "trace_id": trace_id,
            "timestamp": timestamp,
            "crystallization_complete": True,
            "trace_archived": True,
            "skills_updated": len(self.skill_updates) > 0,
            "telemetry_emitted": len(self.telemetry_data) > 0,
            "workspace_graph_updated": len(self.workspace_graph_updates) > 0
        }
    
    async def _archive_trace(self, trace_record: Dict[Any, Any]):
        """Archive trace to L4 forensic storage (JSONL + index)"""
        self.trace_storage.append(trace_record)
        with self.trace_path.open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(trace_record, sort_keys=True) + "\n")

        governance = trace_record["governance_result"]
        budget = governance.get("budget_impact", {})
        ir = trace_record["edgek_ir"]
        with sqlite3.connect(str(self.index_path)) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO traces
                (trace_id, timestamp, session_id, provider_type, model, governance_decision,
                 estimated_total_tokens, estimated_cost_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_record["trace_id"],
                trace_record["timestamp"],
                trace_record["session_id"],
                trace_record["provider_type"],
                ir.get("model", "unknown"),
                governance.get("decision", "unknown"),
                int(budget.get("estimated_total_tokens", 0)),
                float(budget.get("estimated_cost_usd", 0.0))
            ))
        logger.debug(f"Archived trace {trace_record['trace_id']} to L4 storage")
    
    async def _update_skills(self, trace_record: Dict[Any, Any]):
        """Update L3 skill tree based on interaction"""
        ir = trace_record["edgek_ir"]
        governance = trace_record["governance_result"]
        context_economy = ir.get("metadata", {}).get("context_economy", {})
        pattern = {
            "provider": trace_record["provider_type"],
            "model_family": self._model_family(ir.get("model", "")),
            "has_tools": bool(ir.get("tools")),
            "decision": governance.get("decision"),
            "context_economized": bool(context_economy.get("changed", False))
        }
        action = {
            "route_provider": trace_record["provider_type"],
            "max_tokens": ir.get("max_tokens"),
            "policies_applied": governance.get("policies_applied", [])
        }
        skill = self.skill_registry.register_skill(
            name=f"{pattern['model_family']}_{pattern['decision']}",
            category="request_routing",
            pattern=pattern,
            action=action,
            metadata={"last_trace_id": trace_record["trace_id"]}
        )
        skill_update = {
            "trace_id": trace_record["trace_id"],
            "timestamp": trace_record["timestamp"],
            "update_type": "skill_registered",
            "skills_affected": [skill.id],
            "proficiency_change": 0.01
        }
        self.skill_updates.append(skill_update)
        logger.debug(f"Updated skills for trace {trace_record['trace_id']}")
    
    async def _emit_telemetry(self, trace_record: Dict[Any, Any]):
        """Emit telemetry data for observability"""
        # In production, this would send metrics to monitoring system
        telemetry_entry = {
            "trace_id": trace_record["trace_id"],
            "timestamp": trace_record["timestamp"],
            "session_id": trace_record["session_id"],
            "provider_type": trace_record["provider_type"],
            "governance_decision": trace_record["governance_result"]["decision"],
            "context_economized": trace_record["edgek_ir"].get("metadata", {}).get("context_economy", {}).get("changed", False),
            "context_original_tokens": trace_record["edgek_ir"].get("metadata", {}).get("context_economy", {}).get("original_tokens", 0),
            "context_final_tokens": trace_record["edgek_ir"].get("metadata", {}).get("context_economy", {}).get("final_tokens", 0),
            "input_tokens_estimated": trace_record["governance_result"].get("budget_impact", {}).get("estimated_input_tokens", 0),
            "output_tokens_estimated": trace_record["governance_result"].get("budget_impact", {}).get("estimated_output_tokens", 0),
            "total_tokens_estimated": trace_record["governance_result"].get("budget_impact", {}).get("estimated_total_tokens", 0),
            "estimated_cost_usd": trace_record["governance_result"].get("budget_impact", {}).get("estimated_cost_usd", 0.0),
            "policies_applied_count": len(trace_record["governance_result"]["policies_applied"]),
            "prec_completed": True
        }
        self.telemetry_data.append(telemetry_entry)
        logger.debug(f"Emitted telemetry for trace {trace_record['trace_id']}")
    
    async def _update_workspace_graph(self, trace_record: Dict[Any, Any]):
        """Update L2 workspace graph with interaction metadata"""
        ir = trace_record["edgek_ir"]
        message_count = len(ir.get("messages") or [])
        tool_count = len(ir.get("tools") or [])
        with sqlite3.connect(str(self.index_path)) as conn:
            conn.execute("""
                INSERT INTO workspace_interactions
                (trace_id, timestamp, session_id, model, provider_type, message_count, tool_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_record["trace_id"],
                trace_record["timestamp"],
                trace_record["session_id"],
                ir.get("model", "unknown"),
                trace_record["provider_type"],
                message_count,
                tool_count
            ))

        graph_update = {
            "trace_id": trace_record["trace_id"],
            "timestamp": trace_record["timestamp"],
            **self.workspace_graph.observe_trace(trace_record),
            "properties_updated": {
                "last_interaction": trace_record["timestamp"],
                "interaction_count": 1,
                "message_count": message_count,
                "tool_count": tool_count
            }
        }
        self.workspace_graph_updates.append(graph_update)
        logger.debug(f"Updated workspace graph for trace {trace_record['trace_id']}")

    def _model_family(self, model: str) -> str:
        if model.startswith("gpt"):
            return "gpt"
        if model.startswith("claude"):
            return "claude"
        return model.split("-", 1)[0] if model else "unknown"


# Global crystallizer instance
crystallizer = Crystallizer()
