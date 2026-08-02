from pathlib import Path
import pytest
from app.kernel.agents.run_engine import AgentRunEngine
from app.kernel.operations_console.context_manifest import ContextManifestStore
from app.kernel.operations_console.view_model import AgentOperationsConsoleViewModel

def run(tmp_path:Path): AgentRunEngine(tmp_path).create_run(session_id="s",objective="Inspect parser",mode="agent",run_id="run-55")

def test_suggestion_remains_unselected(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="semantic_search",path="app/a.py",content="x",retrieval_reasons=["parser symbol"])
 assert i["status"]=="SUGGESTED_UNSELECTED" and s.manifest("run-55")["accepted_count"]==0

def test_manual_item_is_explicitly_accepted(tmp_path):
 run(tmp_path); i=ContextManifestStore(tmp_path).add_item("run-55",source="operator",path="app/a.py",content="x",selection_origin="manual")
 assert i["status"]=="ACCEPTED"

def test_accept_then_admit(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="search",content="x")
 a=s.decide("run-55",i["item_id"],decision="ACCEPTED",operator_id="op",reason="needed")
 d=s.decide("run-55",i["item_id"],decision="ADMITTED",operator_id="op",reason="send local",provider="ollama")
 assert a["status"]=="ACCEPTED" and d["status"]=="ADMITTED"

def test_cannot_admit_unaccepted_suggestion(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="search",content="x")
 with pytest.raises(ValueError,match="accepted"): s.decide("run-55",i["item_id"],decision="ADMITTED",operator_id="op",reason="x")

def test_sensitive_context_requires_redaction(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="file",path=".env",content="SECRET",selection_origin="manual",privacy_level="SENSITIVE",provider_visibility="REDACTED_ONLY")
 with pytest.raises(ValueError,match="redaction"): s.decide("run-55",i["item_id"],decision="ADMITTED",operator_id="op",reason="x",provider="cloud")

def test_local_only_blocks_external_provider(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="file",content="x",selection_origin="manual",provider_visibility="LOCAL_ONLY")
 with pytest.raises(ValueError,match="forbids"): s.decide("run-55",i["item_id"],decision="ADMITTED",operator_id="op",reason="x",provider="openai")

def test_restart_restores_same_manifest(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); s.add_item("run-55",source="file",content="x")
 a=s.manifest("run-55"); b=ContextManifestStore(tmp_path).manifest("run-55")
 assert a["manifest_digest"]==b["manifest_digest"]

def test_content_hash_is_bound_and_item_verifies(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); i=s.add_item("run-55",source="file",content="hello")
 assert i["content_hash"].startswith("sha256:") and s.verify_item(i)
 i["path"]="tampered"; assert not s.verify_item(i)

def test_manifest_counts_and_tokens(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); s.add_item("run-55",source="file",content="a",selection_origin="manual",token_estimate=7); s.add_item("run-55",source="search",content="b",token_estimate=9)
 m=s.manifest("run-55"); assert m["accepted_count"]==1 and m["suggested_unselected_count"]==1 and m["token_estimate"]==7

def test_console_prefers_durable_manifest(tmp_path):
 run(tmp_path); s=ContextManifestStore(tmp_path); s.add_item("run-55",source="file",path="app/a.py",content="x",selection_origin="manual")
 snap=AgentOperationsConsoleViewModel(tmp_path).build("run-55")
 assert snap["context_manifest"]["item_count"]==1 and snap["context_manifest"]["items"][0]["path"]=="app/a.py"
