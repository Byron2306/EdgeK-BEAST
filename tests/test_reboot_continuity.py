import json
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import app.kernel.execution.reboot_continuity as continuity


def _write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _paths(tmp_path, boot="boot-a"):
    tpm=tmp_path/"tpm.json"; arda=tmp_path/"arda.json"; guardian=tmp_path/"guardian.db"
    caps=tmp_path/"caps.db"; sensorium=tmp_path/"sensorium.db"; promotions=tmp_path/"promotions.json"
    _write(tpm,{"boot_id":boot,"evidence_digest":"sha256:evidence-"+boot,"eligible_for_commons":True,"collected_at":"2026-07-15T00:00:00Z"})
    _write(arda,{"appraisal":{"appraisal_ref":"arda:"+boot,"state":"verified","evidence_digest":"sha256:evidence-"+boot,"expires_at":9e9,"policy_generation":"policy:1","signature":"signed"}})
    db=sqlite3.connect(guardian); db.executescript("CREATE TABLE generations(identity_key TEXT,generation INTEGER);CREATE TABLE leases(lease_id TEXT,lifecycle_state TEXT,health_state TEXT,payload TEXT);INSERT INTO generations VALUES('tcp:8101',3);INSERT INTO leases VALUES('lease:1','healthy','healthy','{}');");db.close()
    db=sqlite3.connect(caps);db.executescript("CREATE TABLE consumed_capabilities(capability_id TEXT,request_digest TEXT,authority TEXT,issuer_key_id TEXT);CREATE TABLE revoked_capabilities(capability_id TEXT,authority TEXT,issuer_key_id TEXT,reason TEXT);INSERT INTO consumed_capabilities VALUES('used:1','req:1','arda','key:1');");db.close()
    db=sqlite3.connect(sensorium);db.executescript("CREATE TABLE sensor_events(offset INTEGER,record_hash TEXT);INSERT INTO sensor_events VALUES(4,'sha256:head');");db.close()
    _write(promotions,{"crystal:1":{"record_digest":"sha256:promotion"}})
    return continuity.ContinuityPaths(tpm,arda,guardian,caps,sensorium,promotions)


def test_real_boot_change_and_fresh_attestation_complete_continuity(tmp_path, monkeypatch):
    paths=_paths(tmp_path); key=Ed25519PrivateKey.generate()
    monkeypatch.setattr(continuity,"current_boot_id",lambda:"boot-a")
    before=continuity.create_preboot_witness(paths,signer=key,now=100)
    monkeypatch.setattr(continuity,"current_boot_id",lambda:"boot-b")
    _write(paths.tpm_evidence,{"boot_id":"boot-b","evidence_digest":"sha256:evidence-boot-b","eligible_for_commons":True,"collected_at":"2026-07-15T01:00:00Z"})
    _write(paths.arda_appraisal,{"appraisal":{"appraisal_ref":"arda:boot-b","state":"verified","evidence_digest":"sha256:evidence-boot-b","expires_at":9e9,"policy_generation":"policy:1","signature":"signed"}})
    recurrence={"verified":True,"boot_id":"boot-b","provider_calls":0,"receipt_digest":"sha256:recurrence"}
    receipt=continuity.verify_postboot(before,paths,verifier=key.public_key(),recurrence_receipt=recurrence,now=200)
    assert receipt["verified"] is True
    assert all(receipt["checks"].values())


def test_process_restart_cannot_masquerade_as_reboot(tmp_path, monkeypatch):
    paths=_paths(tmp_path); monkeypatch.setattr(continuity,"current_boot_id",lambda:"boot-a")
    before=continuity.create_preboot_witness(paths,now=100)
    with pytest.raises(PermissionError,match="boot_id_changed"):
        continuity.verify_postboot(before,paths,recurrence_receipt={"verified":True,"boot_id":"boot-a","provider_calls":0},now=200)


def test_rollback_of_generation_or_consumed_capability_is_rejected(tmp_path, monkeypatch):
    paths=_paths(tmp_path); monkeypatch.setattr(continuity,"current_boot_id",lambda:"boot-a")
    before=continuity.create_preboot_witness(paths,now=100)
    monkeypatch.setattr(continuity,"current_boot_id",lambda:"boot-b")
    _write(paths.tpm_evidence,{"boot_id":"boot-b","evidence_digest":"sha256:evidence-boot-b","eligible_for_commons":True})
    _write(paths.arda_appraisal,{"appraisal":{"state":"verified","evidence_digest":"sha256:evidence-boot-b","expires_at":9e9}})
    db=sqlite3.connect(paths.guardian_ledger);db.execute("UPDATE generations SET generation=2");db.commit();db.close()
    db=sqlite3.connect(paths.capability_ledger);db.execute("DELETE FROM consumed_capabilities");db.commit();db.close()
    with pytest.raises(PermissionError):
        continuity.verify_postboot(before,paths,recurrence_receipt={"verified":True,"boot_id":"boot-b","provider_calls":0},now=200)


def test_applicability_proof_is_bound_to_boot(monkeypatch):
    from app.kernel.compute.physical_crystal_lifecycle import ApplicabilityProof
    proof=ApplicabilityProof("c","d","r",{},(),(),(),"w","g","p","a","boot-a",(),10,20).sealed()
    proof.validate(now_monotonic_ns=11,expected_boot_id="boot-a")
    with pytest.raises(PermissionError,match="boot boundary"):
        proof.validate(now_monotonic_ns=11,expected_boot_id="boot-b")
