#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.kernel.execution.isolated_disk_cleanup import IsolatedDiskCleanupReceipt
from app.kernel.sensorium.contracts_hash import content_hash
def main():
 p=argparse.ArgumentParser();p.add_argument("packet",type=Path);a=p.parse_args();v=json.loads(a.packet.read_text())
 body=dict(v);supplied=body.pop("evidence_digest",None)
 if supplied!=content_hash(body):raise ValueError("isolated disk packet digest mismatch")
 receipt=IsolatedDiskCleanupReceipt(**v["receipt"]);receipt.validate()
 if not v["full_destructive_isolation_proven"] or not receipt.verified:raise ValueError("full destructive isolation was not proven")
 if not v["delegation"]["full_controller_delegation"] or not {"cpu","memory","pids","io"}<=set(v["delegation"]["enabled_controllers"]):raise ValueError("controller delegation incomplete")
 if not v["populated_zero"] or not v["no_orphans"] or v["capsule_cleanup"].get("confirmed") is not True:raise ValueError("destructive capsule cleanup failed")
 if not {"cpu","memory","io"}<=set(v["pressure"]):raise ValueError("pressure evidence incomplete")
 print(json.dumps({"verified":True,"evidence_digest":supplied,"receipt_digest":receipt.receipt_digest,"worker_digest":receipt.worker_digest},sort_keys=True))
if __name__=="__main__":main()
