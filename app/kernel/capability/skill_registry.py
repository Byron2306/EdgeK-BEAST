from pathlib import Path
from typing import Optional, Dict, Any, List
import sqlite3
import json
import hashlib
from datetime import datetime, timezone

from app.kernel.capability.models import Skill


def _json_load(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        parsed = json.loads(value or "")
        return parsed
    except Exception:
        return fallback

class SkillRegistry:
    def __init__(self, db_path: Optional[str] = None):
        self._use_container = db_path is None
        if db_path is None:
            db_path = Path(__file__).resolve().parents[2] / "data" / "skills.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_initialized = False

    def _connect(self) -> sqlite3.Connection:
        if self._use_container:
            from app.kernel.compute.container import container
            return container.get("observation_store").get_skills_conn()
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initialize the database schema"""
        if not self._db_initialized:
            conn = self._connect()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    action TEXT DEFAULT '{}',
                    success_rate REAL DEFAULT 1.0,
                    usage_count INTEGER DEFAULT 1,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            for column, kind in {
                "action": "TEXT DEFAULT '{}'",
                "success_rate": "REAL DEFAULT 1.0",
                "usage_count": "INTEGER DEFAULT 1",
                "metadata": "TEXT DEFAULT '{}'",
                "updated_at": "TEXT DEFAULT ''",
            }.items():
                cols = {row[1] for row in cursor.execute("PRAGMA table_info(skills)").fetchall()}
                if column not in cols:
                    cursor.execute(f"ALTER TABLE skills ADD COLUMN {column} {kind}")
            conn.commit()
            conn.close()
            self._db_initialized = True

    def register_skill(
        self,
        name: str,
        category: str,
        pattern: Dict[str, Any] | str,
        action: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Skill:
        self._init_db()
        pattern_json = pattern if isinstance(pattern, str) else json.dumps(pattern or {}, sort_keys=True, default=str)
        action_json = json.dumps(action or {}, sort_keys=True, default=str)
        metadata_json = json.dumps(metadata or {}, sort_keys=True, default=str)
        seed = f"{category}:{name}:{pattern_json}:{action_json}"
        skill_id = "skill_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
        created_at = datetime.now(timezone.utc).isoformat()
        updated_at = created_at
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO skills (
                    id, name, category, pattern, action, success_rate, usage_count,
                    metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (skill_id, name, category, pattern_json, action_json, 1.0, 1, metadata_json, created_at, updated_at),
            )
        return Skill(
            id=skill_id, name=name, category=category, pattern=_json_load(pattern_json, pattern_json),
            action=_json_load(action_json, {}), success_rate=1.0, usage_count=1,
            created_at=created_at, updated_at=updated_at, metadata=_json_load(metadata_json, {}),
        )

    def get_skills(self, category: Optional[str] = None, limit: int = 100) -> List[Skill]:
        self._init_db()
        sql = "SELECT id, name, category, pattern, action, success_rate, usage_count, created_at, updated_at, metadata FROM skills"
        params: List[Any] = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [
            Skill(
                id=row[0], name=row[1], category=row[2], pattern=_json_load(row[3], row[3]),
                action=_json_load(row[4], {}), success_rate=float(row[5] or 0.0), usage_count=int(row[6] or 0),
                created_at=row[7], updated_at=row[8], metadata=_json_load(row[9], {}),
            )
            for row in rows
        ]

    def get_statistics(self) -> Dict[str, Any]:
        self._init_db()
        with self._connect() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0])
            by_category = {
                str(row[0]): int(row[1])
                for row in conn.execute("SELECT category, COUNT(*) FROM skills GROUP BY category").fetchall()
            }
        return {"total": total, "by_category": by_category}
