import base64, time
import pytest
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.kernel.integration.one_use_capability import OneUseCapabilityLedger
from app.kernel.integration.arda_appraisal import ArdaAppraisal

def test_one_use_capability_consumption_survives_restart(tmp_path):
    path=tmp_path/"consumed.txt"; payload={"capability_id":"cap:1","request_digest":"sha256:x","authority":"arda","expires_at":time.time()+60,"nonce":"n","signature":base64.b64encode(b"sig").decode()}
    OneUseCapabilityLedger(path=path, require_verifier=False).consume(payload,request_digest="sha256:x",authority="arda")
    with pytest.raises(PermissionError): OneUseCapabilityLedger(path=path, require_verifier=False).consume(payload,request_digest="sha256:x",authority="arda")

def test_arda_appraisal_binds_policy_and_audience():
    appraisal=ArdaAppraisal.from_mapping({"appraisal_ref":"app:1","policy_generation":"p1","authority":"arda","state":"verified","expires_at":time.time()+60,"audience":"beast-crystal-executor"})
    appraisal.bind(appraisal_ref="app:1",policy_generation="p1",audience="beast-crystal-executor")
    with pytest.raises(PermissionError): appraisal.bind(appraisal_ref="app:2",policy_generation="p1",audience="beast-crystal-executor")

def test_protected_capability_ledger_requires_verifier(tmp_path):
    with pytest.raises(RuntimeError, match="verifier"):
        OneUseCapabilityLedger(path=tmp_path / "caps.sqlite3", require_verifier=True)

def test_capability_consumption_is_atomic_across_ledger_instances(tmp_path):
    private = Ed25519PrivateKey.generate()
    path = tmp_path / "caps.sqlite3"
    unsigned = {
        "capability_id":"cap:atomic", "request_digest":"sha256:x", "authority":"arda",
        "expires_at":time.time()+60, "nonce":"n", "audience":"executor",
        "policy_generation":"p1", "appraisal_ref":"app:1", "key_id":"key:1",
    }
    from app.kernel.integration.one_use_capability import OneUseCapability
    item = OneUseCapability(**unsigned, signature="")
    payload = {**unsigned, "signature": base64.b64encode(private.sign(item.body())).decode()}
    ledgers = [OneUseCapabilityLedger(private.public_key(), path, require_verifier=True) for _ in range(2)]
    def consume(ledger):
        try:
            ledger.consume(payload, request_digest="sha256:x", authority="arda")
            return True
        except PermissionError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(consume, ledgers))
    assert sorted(results) == [False, True]
