import time
from pathlib import Path
import pytest
from app.kernel.commons.enterprise_plane import CommonsEnterprisePlane
from app.kernel.commons.dataset_river import DatasetRiver
from app.kernel.commons.job_choir import CommonsJobChoir, NodeAdvertisement
from app.kernel.commons.route_damping import RouteFlapDampener
from app.kernel.commons.space_forge import SpaceForge
from app.kernel.networking.service_registry import ServiceRegistry

def test_enterprise_commons_snapshot_and_persistent_registry(tmp_path):
    verifier=lambda _body, signature, authority: signature=="sig" and authority=="beast.local"
    plane=CommonsEnterprisePlane(tmp_path,signature_verifier=verifier,appraisal_verifier=lambda _appraisal,_body: True,node_attestation_verifier=lambda _node: True)
    plane.registry.publish("model",{"revision":"v1"},signature="sig",authority="beast.local")
    plane.vault.put(b"weights"); plane.chunks.put(b"weights")
    snapshot=CommonsEnterprisePlane(tmp_path,signature_verifier=verifier,appraisal_verifier=lambda _appraisal,_body: True,node_attestation_verifier=lambda _node: True).snapshot()
    assert snapshot["artifact_registry"]["count"]==1
    assert snapshot["artifact_vault"]["objects"]==1
    assert snapshot["space_forge"]["appraisal_required"] is True
    assert snapshot["status"]=="ready"

def test_dataset_digest_and_attested_job_selection():
    river=DatasetRiver(); rows=[{"id":1},{"id":2}]; digest=river.digest(rows)
    stream,lineage=river.stream(rows,dataset_digest=digest,verify_digest=True)
    assert list(stream)==rows and lineage.record_count==2
    nodes=[NodeAdvertisement("bad","unverified",("cpu",),1,1),NodeAdvertisement("good","verified",("cpu",),.7,.9,expires_at=time.time()+60)]
    assert CommonsJobChoir().select(nodes,required="cpu",now=time.time()).node_id=="good"

def test_enterprise_job_choir_rejects_self_reported_attestation():
    node=NodeAdvertisement("claimed","verified",("cpu",),1,1,expires_at=time.time()+60)
    with pytest.raises(PermissionError): CommonsJobChoir(require_attestation_verification=True).select([node],required="cpu",now=time.time())

def test_route_damping_survives_restart(tmp_path):
    path=tmp_path/"routes.json"; RouteFlapDampener(path=path).record("node:a","attestation",now=100)
    assert RouteFlapDampener(path=path).suppressed("node:a",now=100)

def test_route_damping_merges_updates_from_multiple_live_instances(tmp_path):
    path=tmp_path/"routes.json"
    first=RouteFlapDampener(path=path); second=RouteFlapDampener(path=path)
    first.record("provider:a","timeout",now=100)
    second.record("provider:a","timeout",now=100)
    assert RouteFlapDampener(path=path).score("provider:a",now=100).penalty==400

def test_space_forge_enterprise_requires_authority_and_appraisal():
    forge=SpaceForge(verifier=lambda _body,_signature,_authority: True,appraisal_verifier=lambda _appraisal,_body: True,require_authority=True,require_appraisal=True,require_verification=True)
    base={"space_id":"beast/lab","image_digest":"sha256:"+"a"*64,"cpu":1,"memory_mb":128,"mounts":["commons://datasets/x"],"outbound_policy":"deny","port":0,"signature":"sig"}
    with pytest.raises((ValueError,PermissionError)): forge.validate(base)
    assert forge.validate({**base,"authority_ref":"beast.local","appraisal_ref":"arda:1"}).appraisal_ref=="arda:1"

def test_enterprise_admission_fails_closed_without_verifiers(tmp_path):
    plane=CommonsEnterprisePlane(tmp_path)
    assert plane.snapshot()["status"]=="configuration_required"
    with pytest.raises(PermissionError):
        plane.registry.publish("model",{"revision":"v1"},signature="not-enough",authority="unknown")

def test_enterprise_plane_refuses_corrupt_persistent_state(tmp_path):
    path=tmp_path/"registry"/"manifests.jsonl"; path.parent.mkdir(parents=True); path.write_text("not-json\n",encoding="utf-8")
    with pytest.raises(ValueError): CommonsEnterprisePlane(tmp_path)

def test_service_registry_loads_and_renders_enterprise_files(tmp_path):
    source=tmp_path/"services.yaml"; source.write_text("services:\n  reverse_proxy: {port: 80}\n  beast: {hostname: beast.test, upstream: '127.0.0.1:8101', port: 8101}\n",encoding="utf-8")
    registry=ServiceRegistry.from_file(source); outputs=registry.render(tmp_path/"generated")
    assert registry.digest().startswith("sha256:") and all(Path(path).exists() for path in outputs.values())
