import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.job_choir import NodeAdvertisement
from app.kernel.commons.signature_verifier import CommonsTrustStore, canonical_bytes
from app.kernel.evidence.control_graph import ControlEvidenceGraph
from app.kernel.sensorium.runtime import SensoriumRuntime


def test_commons_artifact_admission_cross_checks_storage_and_emits_durable_evidence(tmp_path):
    private=Ed25519PrivateKey.generate()
    trust=CommonsTrustStore({"beast.release":private.public_key()})
    sensorium=SensoriumRuntime(
        capacity=32, journal_path=tmp_path/"sensorium.sqlite3",
        export_root=tmp_path/"outbox", boot_id="boot-commons",
    )
    graph=ControlEvidenceGraph(tmp_path/"evidence.jsonl")
    plane=CommonsEnterprisePlane(
        tmp_path/"commons",signature_verifier=trust.verify,
        appraisal_verifier=lambda _a,_b:True,node_attestation_verifier=lambda _n:True,
        sensorium=sensorium,evidence=graph,
    )
    payload=b"verified model weights"
    metadata={"revision":"v1","payload_digest":"sha256:"+hashlib.sha256(payload).hexdigest()}
    body={"kind":"model","metadata":metadata}
    signature=base64.b64encode(private.sign(canonical_bytes(body))).decode()
    result=plane.ingest_artifact(
        "model",metadata,payload,signature=signature,authority="beast.release",
        workspace_id="workspace-1",policy_generation="policy-1",
    )
    assert plane.vault.get(metadata["payload_digest"])==payload
    assert plane.chunks.get(result["chunk_manifest"])==payload
    assert graph.query("commons_artifact_admitted")[0].node_id==result["evidence_node_id"]
    assert sensorium.state()["recent_event_types"]["commons.artifact_admitted"]==1
    assert sensorium.sequencer.metrics()["journal"]["durable_events"]==1

    restored=CommonsEnterprisePlane(
        tmp_path/"commons",signature_verifier=trust.verify,
        appraisal_verifier=lambda _a,_b:True,node_attestation_verifier=lambda _n:True,
    )
    assert restored.registry.get(result["manifest"].artifact_id).digest==result["manifest"].digest


def test_commons_registry_replay_rejects_content_tampering(tmp_path):
    verifier=lambda _body,signature,authority: signature=="sig" and authority=="authority"
    plane=CommonsEnterprisePlane(
        tmp_path,signature_verifier=verifier,
        appraisal_verifier=lambda _a,_b:True,node_attestation_verifier=lambda _n:True,
    )
    plane.registry.publish("model",{"revision":"v1"},signature="sig",authority="authority")
    path=tmp_path/"registry"/"manifests.jsonl"
    path.write_text(path.read_text().replace('"v1"','"tampered"'),encoding="utf-8")
    with pytest.raises(ValueError,match="corrupt Commons registry"):
        CommonsEnterprisePlane(
            tmp_path,signature_verifier=verifier,
            appraisal_verifier=lambda _a,_b:True,node_attestation_verifier=lambda _n:True,
        )


def test_commons_scheduling_and_witnesses_enter_sensorium_and_control_graph(tmp_path):
    signer=Ed25519PrivateKey.generate()
    sensorium=SensoriumRuntime(capacity=32,export_root=tmp_path/"outbox",boot_id="boot-commons")
    graph=ControlEvidenceGraph()
    plane=CommonsEnterprisePlane(
        tmp_path/"commons",signature_verifier=lambda *_:True,
        appraisal_verifier=lambda *_:True,node_attestation_verifier=lambda _node:True,
        witness_signer=signer,witness_authority="beast.witness",sensorium=sensorium,evidence=graph,
    )
    node=NodeAdvertisement(
        "node-1","verified",("cpu",),.8,.9,expires_at=9999999999,
        appraisal_ref="arda:node:1",attestation_evidence={"policy_generation":"policy-1"},
    )
    selected,schedule_node=plane.select_node([node],required="cpu",workspace_id="workspace-1",policy_generation="policy-1",now=100)
    artifact=plane.jobs.publish("model",{"revision":"v1"},"sig")
    receipt,witness_node=plane.witness_job(
        "job-1",selected,artifact,b"output",workspace_id="workspace-1",policy_generation="policy-1",
    )
    assert receipt.signature and receipt.receipt_digest.startswith("sha256:")
    assert receipt.appraisal_ref=="arda:node:1" and receipt.policy_generation=="policy-1"
    assert schedule_node.node_id.startswith("sha256:") and witness_node.node_id.startswith("sha256:")
    types=sensorium.state()["recent_event_types"]
    assert types["commons.job_scheduled"]==1 and types["commons.job_witnessed"]==1
