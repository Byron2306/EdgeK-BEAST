from __future__ import annotations
from dataclasses import dataclass
import hashlib,json,os,time
from app.kernel.crystals.capsule_codec import CapsuleCodec
from app.kernel.crystals.capsule_contracts import CapsuleStatus
@dataclass(frozen=True)
class CapsuleExecutionReceipt:
    crystal_id:str; capsule_digest:str; process_lease_id:str; capability_digest:str; authority_consumed:bool; effects_started:bool; postconditions_verified:bool; rollback_available:bool; rollback_performed:bool; final_status:str; execution_digest:str
class CapsuleExecutionAdapter:
    def __init__(self,*,capsule_verifier,capability_ledger,decoder=None): self.verifier=capsule_verifier; self.ledger=capability_ledger; self.decoder=decoder or (lambda ir:ir)
    def execute(self,received,*,expected_workspace,expected_privacy_domain,expected_audience,active_policy_digest,active_source_state_digest,promotion_is_valid,actuator,postcondition_verifier,rollback=None):
        vr=self.verifier.verify(received.fd,expected_workspace=expected_workspace,expected_privacy_domain=expected_privacy_domain,expected_audience=expected_audience,active_policy_digest=active_policy_digest,active_source_state_digest=active_source_state_digest,promotion_is_valid=promotion_is_valid)
        if vr.status!=CapsuleStatus.VERIFIED_ARTIFACT: raise PermissionError(f"capsule refused: {vr.status.value}:{vr.reason}")
        if time.time() >= received.offer.expires_at: raise PermissionError("capsule offer expired")
        if vr.capsule_digest!=received.offer.capsule_digest or vr.crystal_id!=received.offer.crystal_id: raise PermissionError("control message does not bind received capsule")
        env=CapsuleCodec.decode(os.pread(received.fd,os.fstat(received.fd).st_size,0)); m=env["manifest"]
        if env["manifest"]["promotion_digest"] != received.offer.promotion_digest: raise PermissionError("promotion digest mismatch")
        lease=self.ledger.consume(received.offer.capability_lease_digest,crystal_id=vr.crystal_id,capsule_digest=vr.capsule_digest,audience=received.offer.audience,capability=m["required_capability"])
        plan=self.decoder(env["canonical_ir"]); effect=None; verified=False; rolled=False
        try:
            started=time.monotonic_ns(); effect=actuator(plan,m["execution_bounds"]); elapsed_ms=(time.monotonic_ns()-started)/1_000_000
            effect_bytes=len(json.dumps(effect,sort_keys=True,separators=(",",":"),default=str).encode())
            within_bounds=elapsed_ms <= float(m["execution_bounds"]["max_runtime_ms"]) and effect_bytes <= int(m["execution_bounds"]["max_output_bytes"])
            verified=within_bounds and bool(postcondition_verifier(plan,effect,env["verifier_manifest"]))
            if not verified and rollback: rollback(plan,effect); rolled=True
        except Exception:
            if effect is not None and rollback:
                try: rollback(plan,effect); rolled=True
                except Exception: pass
            raise
        status="verified_success" if verified else ("rolled_back_after_verification_failure" if rolled else "verification_failed")
        body={"crystal_id":vr.crystal_id,"capsule_digest":vr.capsule_digest,"process_lease_id":received.peer_receipt.process_lease_id,"capability_digest":lease.digest,"authority_consumed":True,"effects_started":True,"postconditions_verified":verified,"rollback_available":rollback is not None,"rollback_performed":rolled,"final_status":status}
        ed="sha256:"+hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        return CapsuleExecutionReceipt(**body,execution_digest=ed)
