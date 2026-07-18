#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

def digest(value): return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def load(path):
    value=json.loads(Path(path).read_text(encoding="utf-8")); claimed=value.pop("receipt_digest")
    if claimed != digest(value): raise ValueError(f"tampered receipt: {path}")
    value["receipt_digest"]=claimed; return value

def main():
    p=argparse.ArgumentParser(); p.add_argument("linux"); p.add_argument("windows"); a=p.parse_args()
    linux,windows=load(a.linux),load(a.windows)
    if linux["contract_id"] != windows["contract_id"]: raise ValueError("contract mismatch")
    if linux["physical_domain"].startswith("windows") or not windows["physical_domain"].startswith("windows"): raise ValueError("receipts are not independent Linux and Windows domains")
    if windows.get("self_test") is not False: raise ValueError("Windows receipt is a non-Windows self-test, not physical replication")
    if not linux["verified"] or not windows["verified"]: raise ValueError("one physical domain failed")
    if windows["provider_calls"] != 0 or not windows["stale_process_refused"]: raise ValueError("Windows recurrence/displacement proof incomplete")
    print(json.dumps({"cross_domain_verified":True,"contract_id":linux["contract_id"],"linux_digest":linux["receipt_digest"],"windows_digest":windows["receipt_digest"]},sort_keys=True))

if __name__ == "__main__": main()
