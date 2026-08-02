from __future__ import annotations
import os
from app.kernel.compute.residual_contracts import ResidualRoute, ResidualAuthority
from app.kernel.compute.residual_compute_plane import RouteExecutionResult
class PrismCrystalCapsuleExecutor:
    route=ResidualRoute.PROMOTED_CRYSTAL; authority=ResidualAuthority.ONE_USE_EXECUTE
    def __init__(self,*,registry,bus_sender,execution_adapter,capability_issuer): self.registry=registry;self.bus_sender=bus_sender;self.execution_adapter=execution_adapter;self.capability_issuer=capability_issuer
    def __call__(self,request,decision_digest):
        meta=getattr(request,'metadata',{}) or {}; capsule_id=meta['capsule_id']; e=self.registry.get(capsule_id,workspace_id=request.workspace_id,privacy_domain=request.privacy_domain)
        if e is None: raise RuntimeError('selected capsule unavailable or out of scope')
        lease=self.capability_issuer(e,request,decision_digest)
        received=self.bus_sender(e,lease,request)
        try:
            receipt=self.execution_adapter.execute(received,expected_workspace=request.workspace_id,expected_privacy_domain=request.privacy_domain,expected_audience=meta['audience'],active_policy_digest=meta['policy_digest'],active_source_state_digest=meta['source_state_digest'],promotion_is_valid=meta['promotion_is_valid'],actuator=meta['actuator'],postcondition_verifier=meta['postcondition_verifier'],rollback=meta.get('rollback'))
        finally:
            try: os.close(received.fd)
            except OSError: pass
        return RouteExecutionResult(route=self.route,authority_used=self.authority,output=receipt,verified=receipt.postconditions_verified,execution_digest=receipt.execution_digest,actual_latency_ms=0.0,physical_effects=1)
