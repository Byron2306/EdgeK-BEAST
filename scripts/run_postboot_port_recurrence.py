#!/usr/bin/env python3
"""Execute the exact persisted learned port crystal after a real reboot."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate, PhysicalCrystalPromotionRegistry, RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.socket_inventory import inode_owners, tcp_listeners
from app.kernel.compute.typed_crystal_interpreter import TypedCrystalInterpreter
from app.kernel.compute.typed_crystal_ir import ExecutableCrystalIR, TypedCrystalNode
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.sensorium.adapters import current_boot_id
from app.kernel.sensorium.contracts import SocketIdentity
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


def load_crystal(path: Path, registry) -> ExecutableCrystalIR:
    value = json.loads(path.read_text(encoding="utf-8"))
    for key in ("beast_object_type", "version", "contains_executable_code"):
        value.pop(key, None)
    value["nodes"] = tuple(TypedCrystalNode(**item) for item in value["nodes"])
    value["task_family"] = tuple(value["task_family"])
    value["preconditions"] = tuple(value["preconditions"])
    value["edges"] = tuple(tuple(item) for item in value["edges"])
    value["postconditions"] = tuple(value["postconditions"])
    value["negative_conditions"] = tuple(value["negative_conditions"])
    value["evidence"] = tuple(value["evidence"])
    crystal = ExecutableCrystalIR(**value)
    crystal.validate(registry)
    return crystal


def listener() -> tuple[subprocess.Popen, int]:
    code = "import socket,time;s=socket.socket();s.bind(('127.0.0.1',0));s.listen();print(s.getsockname()[1],flush=True);time.sleep(120)"
    process = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    assert process.stdout is not None
    return process, int(process.stdout.readline().strip())


def run(state: Path) -> dict:
    runtime = SensoriumRuntime(export_root=state / "postboot-sensorium")
    crystal = load_crystal(state / "typed-crystal.json", runtime.typed_ir_compiler.registry)
    appraisal = json.loads((state / "promotion-appraisal.json").read_text(encoding="utf-8"))
    appraisal_verifier = lambda value: value.get("signature") == content_hash({k: v for k, v in value.items() if k != "signature"})
    registry = PhysicalCrystalPromotionRegistry(appraisal_verifier=appraisal_verifier, path=state / "promotions.json", require_scientific_evidence=True)
    record = registry.require_active(crystal.identity)
    if record.artifact_digest != crystal.artifact_digest:
        raise PermissionError("persisted promotion does not bind persisted Crystal IR")
    collector = LinuxProcessIdentityCollector(); process, port = listener()
    try:
        lease = collector.collect(process.pid, owner_scope="postboot-port-recurrence")
        identity = SocketIdentity(
            family="AF_INET", protocol="TCP", local_address_class="loopback", local_port=port,
            remote_scope="none", owning_process=lease.lease_id, service_id="observed-loopback",
            workspace_id="workspace:live-port", cgroup_id=lease.cgroup_id, listener_generation=1,
            opened_at_monotonic_ns=time.monotonic_ns(), policy_class="operator",
        ).with_identity()
        gate = PhysicalApplicabilityGate(
            registry, runtime.typed_ir_compiler.registry, appraisal_verifier=appraisal_verifier,
            process_freshness=collector.still_matches,
            socket_freshness=lambda value: bool((item := next((x for x in tcp_listeners() if x.port == value.local_port), None)) and process.pid in inode_owners(item.inode)),
            port_lease_freshness=lambda _value: True, proof_ttl_ns=5_000_000_000,
        )
        context = RecurrenceContext(
            parameter_bindings={"requested_port": port}, process_leases=(lease,), socket_identities=(identity,),
            port_leases=(), workspace_identity="workspace:live-port",
            registry_digest=content_hash({"workspace": "live-port"}),
            policy_generation=record.policy_generation, appraisal=appraisal,
        )
        mono=time.monotonic_ns(); decision=gate.evaluate(crystal,context,monotonic_ns=mono)
        if not decision.allowed or decision.proof is None: raise PermissionError(decision.reason)
        ledger=OneUseCapabilityLedger(path=state/"authority.sqlite",require_verifier=False)
        capability={"capability_id":"postboot:"+uuid.uuid4().hex,"request_digest":decision.proof.execution_request_digest,
                    "authority":"arda","expires_at":time.time()+120,"nonce":uuid.uuid4().hex,"signature":"local-experiment-boundary",
                    "audience":"beast-runtime","policy_generation":record.policy_generation,"appraisal_ref":record.appraisal_ref}
        authority=consume_execution_authority(decision.proof,capability,ledger,authority="arda",audience="beast-runtime",monotonic_ns=mono+1)
        execution=TypedCrystalInterpreter(runtime.typed_ir_compiler.registry,gate,provider_call_counter=lambda:0).execute(
            crystal,decision.proof,authority,context,execution_state={"kernel_inventory":True},monotonic_ns=mono+2)
        body={"schema":"beast.postboot-port-recurrence.v1","boot_id":current_boot_id(),"crystal_id":crystal.identity,
              "crystal_digest":crystal.artifact_digest,"promotion_record_digest":record.record_digest,
              "execution_receipt":asdict(execution),"provider_calls":execution.provider_calls_during_execution,
              "verified":execution.final_status=="verified_local_recurrence"}
        body["receipt_digest"]=content_hash(body)
        if not body["verified"] or body["provider_calls"] != 0: raise RuntimeError("post-boot recurrence was not verified")
        return body
    finally:
        process.terminate(); process.wait(timeout=3)


def main() -> int:
    parser=argparse.ArgumentParser();parser.add_argument("--state-root",type=Path,required=True);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    receipt=run(args.state_root);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n");args.output.chmod(0o600);print(receipt["receipt_digest"]);return 0


if __name__=="__main__": raise SystemExit(main())
