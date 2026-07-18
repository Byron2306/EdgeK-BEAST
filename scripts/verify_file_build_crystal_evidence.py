#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from app.kernel.compute.physical_crystal_lifecycle import PhysicalCrystalRecord
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR,TypedCrystalNode,default_opcode_registry
from app.kernel.sensorium.contracts_hash import content_hash

def require(value,message):
    if not value: raise ValueError(message)

def verify(receipt_path:Path,packet_path:Path):
    receipt=json.loads(receipt_path.read_text());packet=json.loads(packet_path.read_text())
    receipt_body=dict(receipt);claimed_receipt=receipt_body.pop("receipt_digest")
    packet_body=dict(packet);claimed_packet=packet_body.pop("evidence_packet_digest")
    require(claimed_receipt==content_hash(receipt_body),"receipt digest mismatch")
    require(claimed_packet==content_hash(packet_body),"packet digest mismatch")
    require(receipt["evidence_packet_digest"]==claimed_packet,"receipt does not bind packet")
    typed_value=dict(packet["typed_crystal"])
    for key in ("beast_object_type","version","contains_executable_code"):typed_value.pop(key,None)
    typed_value["nodes"]=tuple(TypedCrystalNode(**item) for item in typed_value["nodes"])
    for key in ("task_family","preconditions","postconditions","negative_conditions","evidence"):typed_value[key]=tuple(typed_value[key])
    typed_value["edges"]=tuple(tuple(item) for item in typed_value["edges"])
    typed=ExecutableCrystalIR(**typed_value);typed.validate(default_opcode_registry())
    require(typed.artifact_digest==receipt["typed_artifact_digest"],"typed artifact mismatch")
    replay=packet["heldout_replay"];variants=replay["variant_receipts"]
    require(replay["evidence_root"]==content_hash([item["evidence_digest"] for item in variants]),"replay root mismatch")
    require(len(variants)==6 and all(item["verified"] for item in variants),"held-out variants failed")
    require(sum(item["negative"] for item in variants)==2,"negative case count mismatch")
    rollback=packet["rollback_probe"];nodes=rollback["variant_receipts"][0]["node_receipts"]
    actuator=next(item for item in nodes if item["opcode"]=="build.render_artifact")
    require(actuator["rollback_attempted"] and actuator["rollback_successful"],"post-write rollback failed")
    record=PhysicalCrystalRecord(**packet["promotion_record"]);record.validate()
    require(record.record_digest==receipt["promoted_record_digest"],"promotion record mismatch")
    execution=packet["execution_receipt"];execution_body=dict(execution);execution_digest=execution_body.pop("receipt_digest")
    require(execution_digest==content_hash(execution_body),"execution receipt digest mismatch")
    require(execution["final_status"]=="verified_local_recurrence" and execution["provider_calls_during_execution"]==0,"local recurrence claim failed")
    objective=packet["objective_verification"]
    require(objective["byte_exact"] and objective["final_artifact_digest"]==objective["expected_artifact_digest"],"objective bytes mismatch")
    require(all(objective["build_test"].get(key) is True for key in ("verified","bytes_match","tests_passed")),"build tests failed")
    require(receipt["compute_plane_phases"]==["begin","authorize","execute","verify","complete"],"ComputePlane lifecycle incomplete")
    return {"verified":True,"receipt_digest":claimed_receipt,"evidence_packet_digest":claimed_packet,"typed_artifact_digest":typed.artifact_digest,"heldout_variants":len(variants),"negative_variants":2,"provider_calls":0}

def main():
    p=argparse.ArgumentParser();p.add_argument("receipt",type=Path);p.add_argument("packet",type=Path);a=p.parse_args();print(json.dumps(verify(a.receipt,a.packet),sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
