"""
EdgeK BEAST Gateway - Skill Registry
Stores learned patterns and governance decisions for future reference
"""

import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import asdict, dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """Represents a learned skill/pattern"""
    id: str
    name: str
    category: str  # e.g., "governance", "routing", "optimization"
    pattern: Dict[str, Any]  # What triggered this skill
    action: Dict[str, Any]  # What action was taken
    success_rate: float  # 0.0 to 1.0
    usage_count: int
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]


class SkillRegistry:
    """
    Registry for storing and retrieving learned skills.
    Skills are patterns that have been successfully used to handle requests.
    """
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "skills.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                pattern TEXT NOT NULL,
                action TEXT NOT NULL,
                success_rate REAL DEFAULT 1.0,
                usage_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_skills_name ON skills(name)
        """)
        conn.commit()
        conn.close()
    
    def register_skill(
        self,
        name: str,
        category: str,
        pattern: Dict[str, Any],
        action: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Skill:
        """Register a new skill or update existing one"""
        pattern_fingerprint = hashlib.sha256(
            json.dumps(pattern, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:12]
        skill_id = f"{category}_{name}_{pattern_fingerprint}"
        now = datetime.utcnow().isoformat()
        
        skill = Skill(
            id=skill_id,
            name=name,
            category=category,
            pattern=pattern,
            action=action,
            success_rate=1.0,
            usage_count=1,
            created_at=now,
            updated_at=now,
            metadata=metadata or {}
        )
        
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        # Check if skill already exists
        cursor.execute("SELECT id, usage_count, success_rate FROM skills WHERE id = ?", (skill_id,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing skill
            cursor.execute("""
                UPDATE skills 
                SET usage_count = usage_count + 1,
                    updated_at = ?
                WHERE id = ?
            """, (now, skill_id))
        else:
            # Insert new skill
            cursor.execute("""
                INSERT INTO skills 
                (id, name, category, pattern, action, success_rate, usage_count, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                skill.id,
                skill.name,
                skill.category,
                json.dumps(skill.pattern),
                json.dumps(skill.action),
                skill.success_rate,
                skill.usage_count,
                skill.created_at,
                skill.updated_at,
                json.dumps(skill.metadata)
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Registered skill: {skill_id}")
        return skill
    
    def get_skills(self, category: Optional[str] = None, limit: int = 100) -> List[Skill]:
        """Retrieve skills, optionally filtered by category"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        if category:
            cursor.execute("""
                SELECT * FROM skills 
                WHERE category = ?
                ORDER BY success_rate DESC, usage_count DESC
                LIMIT ?
            """, (category, limit))
        else:
            cursor.execute("""
                SELECT * FROM skills 
                ORDER BY success_rate DESC, usage_count DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        skills = []
        for row in rows:
            skills.append(Skill(
                id=row[0],
                name=row[1],
                category=row[2],
                pattern=json.loads(row[3]),
                action=json.loads(row[4]),
                success_rate=row[5],
                usage_count=row[6],
                created_at=row[7],
                updated_at=row[8],
                metadata=json.loads(row[9])
            ))
        
        return skills
    
    def update_success_rate(self, skill_id: str, success: bool):
        """Update the success rate of a skill based on outcome"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT usage_count, success_rate FROM skills WHERE id = ?", (skill_id,))
        row = cursor.fetchone()
        
        if row:
            usage_count, current_rate = row
            # Exponential moving average
            new_rate = (current_rate * (usage_count - 1) + (1.0 if success else 0.0)) / usage_count
            
            cursor.execute("""
                UPDATE skills SET success_rate = ? WHERE id = ?
            """, (new_rate, skill_id))
            
            logger.info(f"Updated skill {skill_id} success rate to {new_rate:.2f}")
        
        conn.commit()
        conn.close()
    
    def find_matching_skill(self, pattern: Dict[str, Any], category: str) -> Optional[Skill]:
        """Find a skill that matches the given pattern"""
        skills = self.get_skills(category=category, limit=50)
        
        for skill in skills:
            if self._pattern_matches(pattern, skill.pattern):
                return skill
        
        return None
    
    def _pattern_matches(self, request: Dict[str, Any], skill_pattern: Dict[str, Any]) -> bool:
        """Check if a request matches a skill pattern"""
        for key, value in skill_pattern.items():
            if key not in request:
                return False
            if isinstance(value, dict):
                if not self._pattern_matches(request[key], value):
                    return False
            elif request[key] != value:
                return False
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), AVG(success_rate), SUM(usage_count) FROM skills")
        row = cursor.fetchone()
        
        cursor.execute("SELECT category, COUNT(*) FROM skills GROUP BY category")
        categories = cursor.fetchall()
        
        conn.close()
        
        return {
            "total_skills": row[0] or 0,
            "average_success_rate": row[1] or 0.0,
            "total_usage": row[2] or 0,
            "categories": {cat: count for cat, count in categories}
        }


# Global skill registry instance
skill_registry = SkillRegistry()
