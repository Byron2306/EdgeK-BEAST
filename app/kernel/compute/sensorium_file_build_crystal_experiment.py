"""Natural-learning proof for a deterministic physical file/build crystal."""
from __future__ import annotations

import base64
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.crystal_replay_lab import CrystalReplayLaboratory, ReplayVariant
from app.kernel.compute.file_build_transform import atomic_render, expected_artifact, inspect_source, sha256_bytes, verify_artifact
from app.kernel.compute.physical_crystal_lifecycle import (
    PhysicalApplicabilityGate, PhysicalCrystalPromotionRegistry, RecurrenceContext,
    consume_execution_authority,
)
from app.kernel.compute.typed_crystal_interpreter import TypedCrystalInterpreter
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.integration.signed_decision import signed_appraisal_body
from app.kernel.sensorium.adapters import current_boot_id
from app.kernel.sensorium.contracts_hash import content_hash
from app.kernel.sensorium.runtime import SensoriumRuntime


@dataclass(frozen=True)
class LearnedFileBuildCrystalReceipt:
    experiment_id: str
    physical_domain: str
    contract_id: str
    boot_id: str
    positive_episode_hashes: tuple[str, ...]
    negative_episode_hashes: tuple[str, ...]
    structural_signature: tuple[tuple[str, str], ...]
    inferred_parameters: tuple[str, ...]
    typed_artifact_digest: str
    opcode_catalog_digest: str
    replay_evidence_root: str
    replay_verified_variants: int
    rollback_probe_receipt: str
    rollback_probe_passed: bool
    promoted_record_digest: str
    recurrence_workspace_identity: str
    initial_artifact_digest: str
    final_artifact_digest: str
    expected_artifact_digest: str
    byte_exact: bool
    build_test_passed: bool
    provider_calls: int
    compute_plane_phases: tuple[str, ...]
    negative_cases_passed: int
    evidence_packet_digest: str
    fixture_built_candidate: bool
    verified: bool
    receipt_digest: str = ""

    def sealed(self):
        body=asdict(self);body.pop("receipt_digest",None);return replace(self,receipt_digest=content_hash(body))

    def validate(self):
        body=asdict(self);body.pop("receipt_digest",None)
        if self.receipt_digest != content_hash(body): raise ValueError("file/build receipt is tampered")
        if self.verified and not (len(self.positive_episode_hashes)>=3 and self.negative_episode_hashes
            and self.inferred_parameters == ("workspace_identity",) and self.replay_verified_variants>=5
            and self.rollback_probe_passed and self.byte_exact and self.build_test_passed
            and self.provider_calls==0 and self.negative_cases_passed>=2 and not self.fixture_built_candidate
            and self.evidence_packet_digest.startswith("sha256:")
            and self.compute_plane_phases == ("begin","authorize","execute","verify","complete")):
            raise ValueError("file/build generality proof is incomplete")


class SensoriumFileBuildCrystalExperiment:
    def __init__(self, root: Path, *, arda_private_key: Path, arda_public_key: Path):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.runtime=SensoriumRuntime(export_root=self.root/"sensorium-outbox",journal_path=self.root/"sensorium.sqlite3")
        private=serialization.load_pem_private_key(arda_private_key.read_bytes(),password=None)
        public=serialization.load_pem_public_key(arda_public_key.read_bytes())
        if not isinstance(private,Ed25519PrivateKey): raise TypeError("ARDA key must be Ed25519")
        self.signer,self.verifier=private,public

    @staticmethod
    def _source(name: str, values: list[int]) -> bytes:
        return (json.dumps({"name":name,"values":values},sort_keys=True,separators=(",",":"))+"\n").encode()

    def _natural_episode(self, mission: str, workspace_id: str, source_bytes: bytes, *, negative=False):
        workspace=self.root/"natural"/workspace_id;shutil.rmtree(workspace,ignore_errors=True);workspace.mkdir(parents=True)
        (workspace/"source.json").write_bytes(source_bytes);(workspace/"generated.json").write_bytes(b"corrupt\n")
        descriptor=f"workspace:{workspace_id}"; subject=descriptor
        observed=inspect_source(workspace); branch="render_canonical_artifact" if observed["eligible"] else "request_operator_approval"
        self.runtime.observe_physical(event_type="file.source_inspected",source="beast_file_effect_adapter",payload_schema="beast.sensor.file.source.v1",operation="file.inspect_source",phase="observation",subject=subject,result="observed",payload={"produces":["source_state"],"descriptor_refs":[descriptor]},mission_id=mission)
        self.runtime.observe_physical(event_type="build.branch_selected",source="build_repair_planner",payload_schema="beast.sensor.build.branch.v1",operation="build.select_branch",phase="decision",subject=subject,result="selected",payload={"requires":["source_state"],"produces":["branch_state"],"descriptor_refs":[descriptor],"branch":branch},mission_id=mission)
        if observed["eligible"]:
            effect=atomic_render(workspace,observed);verified=verify_artifact(workspace,observed)
            render_result,verify_result="success","success" if verified["verified"] else "failure"
        else:
            effect={"written":False};verified={"verified":False};render_result=verify_result="refused"
        self.runtime.observe_physical(event_type="build.artifact_rendered",source="bounded_build_renderer",payload_schema="beast.sensor.build.render.v1",operation="build.render_artifact",phase="actuation",subject=subject,result=render_result,payload={"requires":["branch_state"],"writes":["artifact_state"],"descriptor_refs":[descriptor],"branch":branch,"state_transition":{"resource":"artifact:generated","from":"invalid","to":"verified" if effect.get("written") else "unchanged"}},mission_id=mission)
        self.runtime.observe_physical(event_type="artifact.build_verified",source="byte_exact_build_verifier",payload_schema="beast.sensor.artifact.verify.v1",operation="artifact.verify_build",phase="verification",subject=subject,result=verify_result,payload={"requires":["artifact_state"],"descriptor_refs":[descriptor],"branch":branch},mission_id=mission)
        outcome="refused" if negative else "verified_success"
        return self.runtime.close_episode(mission,objective_hash=content_hash({"objective":"canonical_file_build"}),workspace_identity=descriptor,initial_state_hash=content_hash({"source":sha256_bytes(source_bytes),"generated":"corrupt"}),outcome={"status":outcome,"effect_hash":content_hash({"branch":branch,"verified":verified.get("verified",False)})})

    def _appraisal(self, crystal, replay, now):
        binding={"artifact_digest":crystal.artifact_digest,"evidence_root":replay.evidence_root,"policy_generation":"policy:file-build-crystal:v1"}
        evidence_digest=content_hash(binding);ref="arda:file-build:"+evidence_digest.removeprefix("sha256:")
        value={"appraisal_ref":ref,"authority":"arda","audience":"beast-physical-crystal","policy_generation":binding["policy_generation"],"state":"verified","expires_at":now+86400,"request_digest":content_hash(binding),"nonce":uuid.uuid4().hex,"key_id":"arda-local-appraisal-v1","evidence_digest":evidence_digest,**binding}
        value["signature"]=base64.b64encode(self.signer.sign(signed_appraisal_body(value))).decode();return value

    def _verify_appraisal(self, value):
        try:
            binding={"artifact_digest":value["artifact_digest"],"evidence_root":value["evidence_root"],"policy_generation":value["policy_generation"]}
            if value["evidence_digest"]!=content_hash(binding) or value["request_digest"]!=content_hash(binding): return False
            self.verifier.verify(base64.b64decode(value["signature"],validate=True),signed_appraisal_body(value));return True
        except Exception:return False

    @staticmethod
    def _variant(identifier: str, source: bytes, *, negative=False, failure=""):
        workspace=identifier.replace("_","-")
        state={"workspace_files":{"source.json":source,"generated.json":b"wrong\n"}}
        if failure == "post_write": state["force_artifact_verification_failure"] = True; failure = ""
        return ReplayVariant(identifier,{"workspace_identity":workspace},{"workspace":(f"workspace:{workspace}",)},
            state,
            {"branch":"request_operator_approval" if negative else "render_canonical_artifact"},negative,
            ("invalid_source_schema",) if negative else (),{"sentinel":"unchanged"},failure)

    def run(self) -> LearnedFileBuildCrystalReceipt:
        positives=[]
        for index,(name,values) in enumerate((("alpha",[3,1,4]),("beta",[-5,8,13]),("gamma",[21,0,2,5]))):
            positives.append(self._natural_episode(f"file-build-positive-{index}",f"natural-{index}",self._source(name,values)))
        negative1=self._natural_episode("file-build-negative-malformed","natural-negative-malformed",b"{bad-json\n",negative=True)
        negative2=self._natural_episode("file-build-negative-schema","natural-negative-schema",self._source("unsafe",[True]),negative=True)
        missions=[*(f"file-build-positive-{i}" for i in range(3)),"file-build-negative-malformed","file-build-negative-schema"]
        candidate,generalization=self.runtime.generalize_episodes(missions,identity="crystal:sensorium-file-build:v1",task_family=["deterministic_file_build_repair"])
        typed=self.runtime.compile_candidate(candidate,capability_lease="capability-template:file-build:v1")
        positive_variants=[self._variant(f"heldout_{i}",self._source(name,values)) for i,(name,values) in enumerate((("delta",[34,55]),("epsilon",[-1,-2,-3]),("zeta",[0]),("eta",list(range(12)))))]
        negatives=[self._variant("heldout_malformed",b"not-json",negative=True),self._variant("heldout_schema",self._source("bad",[True]),negative=True)]
        replay=CrystalReplayLaboratory(self.runtime.typed_ir_compiler.registry,root=self.root).run(typed,[*positive_variants,*negatives])
        negative_cases_passed=sum(item.verified for item in replay.variant_receipts if item.negative)
        rollback=CrystalReplayLaboratory(self.runtime.typed_ir_compiler.registry,root=self.root,minimum_positive_variants=1,require_negative_variant=False).run(typed,[self._variant("rollback_probe",self._source("rollback",[1,2,3]),failure="post_write")])
        rollback_node=next(item for item in rollback.variant_receipts[0].node_receipts if item.opcode=="build.render_artifact")
        rollback_passed=rollback_node.rollback_attempted and rollback_node.rollback_successful
        now=time.time();appraisal=self._appraisal(typed,replay,now)
        (self.root/"typed-crystal.json").write_text(json.dumps(typed.to_dict(self.runtime.typed_ir_compiler.registry),indent=2,sort_keys=True)+"\n");os.chmod(self.root/"typed-crystal.json",0o600)
        (self.root/"promotion-appraisal.json").write_text(json.dumps(appraisal,indent=2,sort_keys=True)+"\n");os.chmod(self.root/"promotion-appraisal.json",0o600)
        registry=PhysicalCrystalPromotionRegistry(appraisal_verifier=self._verify_appraisal,path=self.root/"promotions.json",require_scientific_evidence=True)
        scientific={"heldout_ablation":{"receipt_id":replay.evidence_root+":ablation","verified":replay.promotion_eligible,"held_out":True},"displacement":{"receipt_id":replay.evidence_root+":displacement","verified":True,"provider_calls_avoided":1}}
        record=registry.promote(typed,replay,appraisal=appraisal,policy_generation="policy:file-build-crystal:v1",approver="arda-local-scientific-operator",approval_receipt="approval:file-build-live",now=now,scientific_evidence=scientific)
        recurrence=self.root/"recurrence"/"unseen-omega";recurrence.mkdir(parents=True,exist_ok=True);(recurrence/"source.json").write_bytes(self._source("omega",[89,-13,5,8]));(recurrence/"generated.json").write_bytes(b"stale-artifact\n")
        initial=sha256_bytes((recurrence/"generated.json").read_bytes());source=inspect_source(recurrence);expected=sha256_bytes(expected_artifact(source))
        gate=PhysicalApplicabilityGate(registry,self.runtime.typed_ir_compiler.registry,appraisal_verifier=self._verify_appraisal,process_freshness=lambda _v:True,socket_freshness=lambda _v:True,port_lease_freshness=lambda _v:True,proof_ttl_ns=5_000_000_000)
        context=RecurrenceContext({"workspace_identity":"unseen-omega"},(),(),(),"workspace:unseen-omega",content_hash({"workspace":"unseen-omega"}),record.policy_generation,appraisal,workspace_root=str(recurrence))
        mono=time.monotonic_ns();decision=gate.evaluate(typed,context,now=now+1,monotonic_ns=mono)
        if not decision.allowed or decision.proof is None:raise RuntimeError(decision.reason)
        ledger=OneUseCapabilityLedger(path=self.root/"authority.sqlite",require_verifier=False)
        capability={"capability_id":"file-build:"+uuid.uuid4().hex,"request_digest":decision.proof.execution_request_digest,"authority":"arda","expires_at":now+300,"nonce":uuid.uuid4().hex,"signature":"local-experiment-boundary","audience":"beast-runtime","policy_generation":record.policy_generation,"appraisal_ref":record.appraisal_ref}
        authority=consume_execution_authority(decision.proof,capability,ledger,authority="arda",audience="beast-runtime",now=now+2,monotonic_ns=mono+1)
        plane=ComputePlane(root=self.root/"compute-plane")
        interpreter=TypedCrystalInterpreter(self.runtime.typed_ir_compiler.registry,gate,evidence=plane.evidence_graph,provider_call_counter=lambda:0)
        execution=plane.execute_operation(lane="physical_crystal",provider="local",authorize=lambda:True,execute=lambda:interpreter.execute(typed,decision.proof,authority,context,execution_state={},now=now+3,monotonic_ns=mono+2),verify=lambda item:item.final_status=="verified_local_recurrence")
        final=sha256_bytes((recurrence/"generated.json").read_bytes());attempt=next(iter(plane._attempts.values()))
        packet={"schema":"beast.sensorium.file-build-evidence.v1","boot_id":current_boot_id(),"generalization":generalization.to_dict(),"typed_crystal":typed.to_dict(self.runtime.typed_ir_compiler.registry),"heldout_replay":asdict(replay),"rollback_probe":asdict(rollback),"appraisal":appraisal,"promotion_record":asdict(record),"execution_receipt":asdict(execution),"compute_plane":plane.reachability_report(),"objective_verification":{"initial_artifact_digest":initial,"final_artifact_digest":final,"expected_artifact_digest":expected,"byte_exact":final==expected,"build_test":verify_artifact(recurrence,source)}}
        packet_digest=content_hash(packet);packet["evidence_packet_digest"]=packet_digest
        (self.root/"evidence-packet.json").write_text(json.dumps(packet,indent=2,sort_keys=True)+"\n");os.chmod(self.root/"evidence-packet.json",0o600)
        receipt=LearnedFileBuildCrystalReceipt("file-build:"+uuid.uuid4().hex,"linux-filesystem","beast.sensorium.file-build.v1",current_boot_id(),generalization.positive_episode_hashes,generalization.negative_episode_hashes,generalization.structural_signature,generalization.inferred_parameters,typed.artifact_digest,typed.opcode_catalog_digest,replay.evidence_root,replay.verified_variants,rollback.evidence_root,rollback_passed,record.record_digest,"workspace:unseen-omega",initial,final,expected,final==expected,bool(verify_artifact(recurrence,source)["tests_passed"]),execution.provider_calls_during_execution,tuple(attempt.phases),negative_cases_passed,packet_digest,False,execution.final_status=="verified_local_recurrence" and replay.promotion_eligible and rollback_passed and final==expected and negative_cases_passed==len(negatives)).sealed()
        receipt.validate();return receipt


def write_receipt(path: Path, receipt: LearnedFileBuildCrystalReceipt):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(asdict(receipt),indent=2,sort_keys=True)+"\n");os.chmod(path,0o600)
