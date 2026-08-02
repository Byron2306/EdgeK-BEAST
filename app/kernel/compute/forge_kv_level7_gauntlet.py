"""Offline hostile gauntlet for the Level 7 live boundary."""
from pathlib import Path
import tempfile,os
from app.kernel.compute.forge_kv_level7_config import ForgeKVLiveConfig
from app.kernel.compute.forge_kv_cross_node_evidence import CrossNodeEvidencePacket

def run_level7_gauntlet():
    with tempfile.TemporaryDirectory() as d:
        token=Path(d)/"hf.token"; token.write_text("secret-token",encoding="utf-8"); os.chmod(token,0o600)
        cfg=ForgeKVLiveConfig(enabled=False,dry_run=True,hf_dataset_id="owner/private",hf_token_file=str(token))
        cfg.validate(for_write=False)
        refused=False
        try: cfg.validate(for_write=True)
        except PermissionError: refused=True
        p=CrossNodeEvidencePacket("owner/private","sha256:"+"1"*64,"remote","sha256:"+"2"*64,"node-b","sha256:"+"3"*64,"sha256:"+"4"*64,"sha256:"+"5"*64,"sha256:"+"6"*64).sealed(); p.validate()
        return {"beast_object_type":"forge_kv_level7_gauntlet","dry_run_refused_write":refused,"packet_valid":True,"native_context_exported":False,"promotion_granted":False}
