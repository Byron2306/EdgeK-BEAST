from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime, timezone

@dataclass
class Skill:
    id: str
    name: str
    category: str
    pattern: Any
    created_at: str
    action: Any = field(default_factory=dict)
    success_rate: float = 1.0
    usage_count: int = 1
    updated_at: str = ""
    metadata: Any = field(default_factory=dict)

@dataclass
class CapabilityRecord:
    """Unified representation of a governed compute asset."""
    asset_id: str
    asset_name: str
    asset_type: str  # "meta_tool", "crystal"
    description: str
    status: str  # "candidate", "promoted", "demoted", "retired"
    
    # Fingerprint and verification metrics
    confidence: float = 0.0
    impact_fingerprint: Optional[Dict[str, Any]] = field(default_factory=dict)
    
    # Operational metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type,
            "status": self.status,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
