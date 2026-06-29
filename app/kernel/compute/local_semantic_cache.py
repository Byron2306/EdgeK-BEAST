import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()

def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[A-Za-z0-9_:-]{3,}", text or "")}

def _jaccard(a: str, b: str) -> float:
    aa, bb = _tokens(a), _tokens(b)
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)

@dataclass
class LocalSemanticHit:
    credit_id: str
    answer: str
    confidence: float
    reason: str
    metadata: Dict[str, Any]

class LocalSemanticCache:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _init(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS semantic_cache (
                    credit_id TEXT PRIMARY KEY,
                    prompt_hash TEXT NOT NULL,
                    prompt_preview TEXT NOT NULL,
                    task_class TEXT NOT NULL,
                    repo_fingerprint TEXT DEFAULT '',
                    policy_version TEXT DEFAULT '',
                    answer TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    verified INTEGER NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_semantic_scope ON semantic_cache(task_class, repo_fingerprint)")

    def put(
        self,
        *,
        credit_id: str,
        prompt: str,
        task_class: str,
        repo_fingerprint: str,
        answer: str,
        confidence: float,
        verified: bool,
        policy_version: str,
        metadata: Dict[str, Any],
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO semantic_cache
                (credit_id, prompt_hash, prompt_preview, task_class, repo_fingerprint,
                 policy_version, answer, confidence, verified, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                credit_id,
                _hash(prompt),
                prompt[:1200],
                task_class,
                repo_fingerprint or "",
                policy_version or "",
                answer,
                max(0.0, min(1.0, float(confidence))),
                1 if verified else 0,
                json.dumps(metadata or {}, sort_keys=True, default=str),
            ))

    def match(
        self,
        *,
        prompt: str,
        task_class: str,
        repo_fingerprint: str,
        threshold: float = 0.86,
        require_verified: bool = True,
    ) -> Optional[LocalSemanticHit]:
        prompt_hash = _hash(prompt)

        with sqlite3.connect(self.db_path) as conn:
            exact = conn.execute("""
                SELECT credit_id, answer, confidence, metadata
                FROM semantic_cache
                WHERE prompt_hash = ?
                  AND task_class = ?
                  AND repo_fingerprint = ?
                  AND (? = 0 OR verified = 1)
                LIMIT 1
            """, (prompt_hash, task_class, repo_fingerprint or "", 1 if require_verified else 0)).fetchone()

            if exact:
                return LocalSemanticHit(
                    credit_id=exact[0],
                    answer=exact[1],
                    confidence=float(exact[2]),
                    reason="exact_prompt_hash",
                    metadata=_loads_metadata(exact[3]),
                )

            rows = conn.execute("""
                SELECT credit_id, prompt_preview, answer, confidence, metadata
                FROM semantic_cache
                WHERE task_class = ?
                  AND repo_fingerprint = ?
                  AND (? = 0 OR verified = 1)
                ORDER BY created_at DESC
                LIMIT 200
            """, (task_class, repo_fingerprint or "", 1 if require_verified else 0)).fetchall()

        best = None
        best_score = 0.0
        for credit_id, preview, answer, base_conf, metadata in rows:
            score = _jaccard(prompt, preview) * float(base_conf)
            if score > best_score:
                best_score = score
                best = (credit_id, answer, metadata)

        if best and best_score >= threshold:
            return LocalSemanticHit(
                credit_id=best[0],
                answer=best[1],
                confidence=round(best_score, 4),
                reason="local_token_overlap_semantic_match",
                metadata=_loads_metadata(best[2]),
            )

        return None

    def quarantine(
        self,
        *,
        task_class: str,
        repo_fingerprint: str,
        credit_ids: Optional[list[str]] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        credit_ids = [str(item) for item in (credit_ids or []) if item]
        with sqlite3.connect(self.db_path) as conn:
            if credit_ids:
                placeholders = ",".join("?" for _ in credit_ids)
                params = [task_class, repo_fingerprint or "", *credit_ids]
                rows = conn.execute(
                    f"""
                    SELECT credit_id FROM semantic_cache
                    WHERE task_class = ? AND repo_fingerprint = ? AND credit_id IN ({placeholders})
                    """,
                    params,
                ).fetchall()
                conn.execute(
                    f"""
                    DELETE FROM semantic_cache
                    WHERE task_class = ? AND repo_fingerprint = ? AND credit_id IN ({placeholders})
                    """,
                    params,
                )
            else:
                rows = conn.execute(
                    "SELECT credit_id FROM semantic_cache WHERE task_class = ? AND repo_fingerprint = ?",
                    (task_class, repo_fingerprint or ""),
                ).fetchall()
                conn.execute(
                    "DELETE FROM semantic_cache WHERE task_class = ? AND repo_fingerprint = ?",
                    (task_class, repo_fingerprint or ""),
                )
        return {
            "beast_object_type": "local_semantic_cache_quarantine",
            "version": "1.0",
            "reason": reason,
            "task_class": task_class,
            "repo_fingerprint": repo_fingerprint or "",
            "removed_count": len(rows),
            "credit_ids": [row[0] for row in rows],
        }


def _loads_metadata(raw: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {"value": data}
    except (TypeError, json.JSONDecodeError):
        return {"parse_error": True}
