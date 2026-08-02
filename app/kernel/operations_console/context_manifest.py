"""Phase 5.5 durable, explicit-selection context manifest backend."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.approvals.digests import semantic_payload, sha256_digest

VERSION = "5.5"
MANIFEST_TYPE = "beast_context_manifest"
ITEM_TYPE = "beast_context_manifest_item"
EVENT_TYPE = "beast_context_manifest_event"
VALID_STATES = {"DISCOVERED","SUGGESTED_UNSELECTED","ACCEPTED","REJECTED","ADMITTED","REDACTED","EXCLUDED","STALE"}
PRIVACY_LEVELS = {"PUBLIC","INTERNAL","SENSITIVE","RESTRICTED"}
VISIBILITY = {"LOCAL_ONLY","REDACTED_ONLY","APPROVED_PROVIDER","ANY_PROVIDER"}


def _hash_content(value: Any) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _clean_reasons(values: Sequence[Any] | None) -> list[str]:
    result=[]
    for value in values or []:
        text=str(value or "").strip()
        if text and text not in result: result.append(text)
    return result


class ContextManifestStore:
    """Durable manifest. Suggested context is never implicitly accepted."""
    def __init__(self, workspace_root: str | Path):
        self.workspace_root=Path(workspace_root).expanduser().resolve()
        self.engine=AgentRunEngine(self.workspace_root)
        self.db_path=self.workspace_root/".beast"/"operations_console"/"context_manifest.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock=threading.RLock()
        with self._connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS context_items(
              item_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, source TEXT NOT NULL,
              path TEXT NOT NULL, start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
              content_hash TEXT NOT NULL, retrieval_reasons_json TEXT NOT NULL,
              selection_origin TEXT NOT NULL, token_estimate INTEGER NOT NULL,
              privacy_level TEXT NOT NULL, provider_visibility TEXT NOT NULL,
              status TEXT NOT NULL, admitted_provider TEXT NOT NULL,
              redaction_digest TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
              item_digest TEXT NOT NULL, UNIQUE(run_id,item_id));
            CREATE INDEX IF NOT EXISTS idx_context_items_run ON context_items(run_id,created_at,item_id);
            CREATE TABLE IF NOT EXISTS context_events(
              event_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, item_id TEXT NOT NULL,
              event_type TEXT NOT NULL, payload_json TEXT NOT NULL,
              previous_event_digest TEXT NOT NULL, event_digest TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_context_events_run ON context_events(run_id,created_at,event_id);
            """)

    def _connect(self):
        db=sqlite3.connect(str(self.db_path), isolation_level=None)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=FULL")
        return db

    def add_item(self, run_id: str, *, source: str, path: str="", start_line: int=0, end_line: int=0,
                 content: Any=None, content_hash: str="", retrieval_reasons: Sequence[Any]|None=None,
                 selection_origin: str="suggested", token_estimate: int=0, privacy_level: str="INTERNAL",
                 provider_visibility: str="LOCAL_ONLY", item_id: str="") -> dict[str,Any]:
        if not self.engine.store.get_run(run_id): raise KeyError(f"unknown agent run: {run_id}")
        src=str(source or "").strip(); p=str(path or "").strip(); origin=str(selection_origin or "suggested").strip().lower()
        privacy=str(privacy_level or "INTERNAL").upper(); visibility=str(provider_visibility or "LOCAL_ONLY").upper()
        if not src: raise ValueError("source is required")
        if privacy not in PRIVACY_LEVELS: raise ValueError("unsupported privacy level")
        if visibility not in VISIBILITY: raise ValueError("unsupported provider visibility")
        if origin not in {"manual","suggested","system"}: raise ValueError("unsupported selection origin")
        digest=str(content_hash or "").strip() or _hash_content(content)
        if not digest.startswith("sha256:"): raise ValueError("content_hash must be sha256-bound")
        status="ACCEPTED" if origin=="manual" else "SUGGESTED_UNSELECTED"
        now=time.time(); iid=item_id or f"ctx_{uuid4().hex}"
        semantic={"version":VERSION,"beast_object_type":ITEM_TYPE,"item_id":iid,"run_id":run_id,"source":src,
          "path":p,"line_range":{"start":max(0,int(start_line)),"end":max(0,int(end_line))},"content_hash":digest,
          "retrieval_reasons":_clean_reasons(retrieval_reasons),"selection_origin":origin,"token_estimate":max(0,int(token_estimate)),
          "privacy_level":privacy,"provider_visibility":visibility,"status":status,"admitted_provider":"","redaction_digest":"",
          "created_at":now,"updated_at":now,"authority":"context_selection_record_only","grants_model_admission":False,"grants_execution_authority":False}
        semantic["item_digest"]=sha256_digest(semantic)
        with self._lock,self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO context_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (iid,run_id,src,p,semantic["line_range"]["start"],semantic["line_range"]["end"],digest,json.dumps(semantic["retrieval_reasons"]),origin,semantic["token_estimate"],privacy,visibility,status,"","",now,now,semantic["item_digest"]))
            self._event(db,run_id,iid,"context.item.added",{"status":status,"item_digest":semantic["item_digest"]},now)
            db.execute("COMMIT")
        return semantic

    def decide(self, run_id: str, item_id: str, *, decision: str, operator_id: str, reason: str,
               provider: str="", redaction_digest: str="") -> dict[str,Any]:
        decision=str(decision or "").upper(); operator=str(operator_id or "").strip(); why=str(reason or "").strip()
        if decision not in {"ACCEPTED","REJECTED","EXCLUDED","ADMITTED","REDACTED"}: raise ValueError("unsupported context decision")
        if not operator or not why: raise ValueError("operator_id and reason are required")
        current=self.get(run_id,item_id)
        if current["status"] in {"REJECTED","EXCLUDED","STALE"} and decision in {"ADMITTED","REDACTED"}: raise ValueError("inactive context cannot be admitted")
        if decision=="ADMITTED" and current["status"] not in {"ACCEPTED","REDACTED","ADMITTED"}: raise ValueError("context must be accepted before admission")
        if decision=="ADMITTED" and current["privacy_level"] in {"SENSITIVE","RESTRICTED"} and not redaction_digest:
            raise ValueError("sensitive context requires redaction before provider admission")
        if decision=="ADMITTED" and current["provider_visibility"]=="LOCAL_ONLY" and provider and provider.lower() not in {"local","ollama","cpu"}:
            raise ValueError("provider visibility forbids external admission")
        now=time.time(); admitted_provider=provider if decision=="ADMITTED" else current["admitted_provider"]
        redaction=redaction_digest or current["redaction_digest"]
        semantic={**current,"status":decision,"admitted_provider":admitted_provider,"redaction_digest":redaction,"updated_at":now}
        semantic.pop("item_digest",None); semantic["item_digest"]=sha256_digest(semantic)
        with self._lock,self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE context_items SET status=?,admitted_provider=?,redaction_digest=?,updated_at=?,item_digest=? WHERE run_id=? AND item_id=?",
              (decision,admitted_provider,redaction,now,semantic["item_digest"],run_id,item_id))
            self._event(db,run_id,item_id,"context.item.decided",{"decision":decision,"operator_id":operator,"reason":why,"item_digest":semantic["item_digest"]},now)
            db.execute("COMMIT")
        self.engine.emit(run_id,"agent.context.updated",{"summary":f"Context item {item_id} {decision.lower()}","item_id":item_id,"status":decision,"item_digest":semantic["item_digest"]})
        return semantic

    def mark_stale(self, run_id:str,item_id:str,*,observed_content:Any=None,observed_hash:str="") -> dict[str,Any]:
        current=self.get(run_id,item_id); observed=observed_hash or _hash_content(observed_content)
        if observed==current["content_hash"]: return current
        return self.decide(run_id,item_id,decision="EXCLUDED",operator_id="system:hash-monitor",reason="content hash changed") | {"status":"STALE","observed_content_hash":observed}

    def get(self,run_id:str,item_id:str)->dict[str,Any]:
        with self._connect() as db: row=db.execute("SELECT * FROM context_items WHERE run_id=? AND item_id=?",(run_id,item_id)).fetchone()
        if not row: raise KeyError(f"unknown context item: {item_id}")
        return self._row(row)

    def manifest(self,run_id:str)->dict[str,Any]:
        if not self.engine.store.get_run(run_id): raise KeyError(f"unknown agent run: {run_id}")
        with self._connect() as db: rows=db.execute("SELECT * FROM context_items WHERE run_id=? ORDER BY created_at,item_id",(run_id,)).fetchall()
        items=[self._row(r) for r in rows]
        semantic={"version":VERSION,"beast_object_type":MANIFEST_TYPE,"run_id":run_id,"status":"available" if items else "not_built",
          "item_count":len(items),"accepted_count":sum(i["status"] in {"ACCEPTED","ADMITTED","REDACTED"} for i in items),
          "admitted_count":sum(i["status"]=="ADMITTED" for i in items),"suggested_unselected_count":sum(i["status"]=="SUGGESTED_UNSELECTED" for i in items),
          "rejected_count":sum(i["status"] in {"REJECTED","EXCLUDED","STALE"} for i in items),"token_estimate":sum(i["token_estimate"] for i in items if i["status"] in {"ACCEPTED","ADMITTED","REDACTED"}),
          "items":items,"authority":"context_manifest_read_only","grants_model_admission":False,"grants_execution_authority":False}
        semantic["manifest_digest"]=sha256_digest(semantic)
        return semantic

    def verify_item(self,item:Mapping[str,Any])->bool:
        value=dict(item); claimed=str(value.get("item_digest") or "")
        return bool(claimed) and sha256_digest(semantic_payload(value, exclude={"item_digest"})) == claimed

    def verify_manifest(self,m:Mapping[str,Any])->bool:
        value=dict(m); claimed=str(value.get("manifest_digest") or "")
        return bool(claimed) and sha256_digest(semantic_payload(value, exclude={"manifest_digest"})) == claimed

    def _event(self,db,run_id,item_id,event_type,payload,created):
        prev=db.execute("SELECT event_digest FROM context_events WHERE run_id=? ORDER BY created_at DESC,event_id DESC LIMIT 1",(run_id,)).fetchone()
        semantic={"version":VERSION,"beast_object_type":EVENT_TYPE,"event_id":f"ctxevt_{uuid4().hex}","run_id":run_id,"item_id":item_id,"event_type":event_type,"payload":payload,"previous_event_digest":str(prev[0]) if prev else "","created_at":created}
        digest=sha256_digest(semantic)
        db.execute("INSERT INTO context_events VALUES(?,?,?,?,?,?,?,?)",(semantic["event_id"],run_id,item_id,event_type,json.dumps(payload,separators=(",",":")),semantic["previous_event_digest"],digest,created))

    def _row(self,row)->dict[str,Any]:
        value={"version":VERSION,"beast_object_type":ITEM_TYPE,"item_id":row["item_id"],"run_id":row["run_id"],"source":row["source"],"path":row["path"],"line_range":{"start":row["start_line"],"end":row["end_line"]},"content_hash":row["content_hash"],"retrieval_reasons":json.loads(row["retrieval_reasons_json"]),"selection_origin":row["selection_origin"],"token_estimate":row["token_estimate"],"privacy_level":row["privacy_level"],"provider_visibility":row["provider_visibility"],"status":row["status"],"admitted_provider":row["admitted_provider"],"redaction_digest":row["redaction_digest"],"created_at":row["created_at"],"updated_at":row["updated_at"],"authority":"context_selection_record_only","grants_model_admission":False,"grants_execution_authority":False,"item_digest":row["item_digest"]}
        return value
