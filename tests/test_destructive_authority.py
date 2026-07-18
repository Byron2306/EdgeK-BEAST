import base64
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.kernel.execution.destructive_authority import DestructiveAuthorityVerifier
from app.kernel.integration.signed_decision import SignedDecision, signed_appraisal_body


def test_destructive_operator_and_arda_signatures_bind_exact_request():
    operator_private = Ed25519PrivateKey.generate()
    arda_private = Ed25519PrivateKey.generate()
    request_digest = "sha256:destructive-request"
    decision = SignedDecision(
        "beast.process.retire", True, request_digest, "policy:1", "nonce:operator", "", "operator:key:1"
    )
    operator = {
        "authority": decision.authority,
        "allowed": decision.allowed,
        "request_digest": decision.request_digest,
        "policy_generation": decision.policy_generation,
        "nonce": decision.nonce,
        "verification_material": {"key_id": decision.key_id},
        "signature": base64.b64encode(operator_private.sign(decision.unsigned())).decode(),
    }
    appraisal = {
        "appraisal_ref": "appraisal:1",
        "authority": "arda",
        "audience": "beast-stale-process-retirement",
        "policy_generation": "policy:1",
        "state": "verified",
        "expires_at": time.time() + 60,
        "request_digest": request_digest,
        "nonce": "nonce:arda",
        "key_id": "arda:key:1",
        "evidence_digest": "sha256:evidence",
    }
    appraisal["signature"] = base64.b64encode(arda_private.sign(signed_appraisal_body(appraisal))).decode()
    verifier = DestructiveAuthorityVerifier(operator_private.public_key(), arda_private.public_key())
    verifier.verify(
        operator_approval=operator,
        arda_appraisal=appraisal,
        action_authority="beast.process.retire",
        request_digest=request_digest,
        audience="beast-stale-process-retirement",
        policy_generation="policy:1",
        appraisal_ref="appraisal:1",
    )
    with pytest.raises(ValueError, match="binding"):
        verifier.verify(
            operator_approval=operator,
            arda_appraisal=appraisal,
            action_authority="beast.process.retire",
            request_digest="sha256:retargeted",
            audience="beast-stale-process-retirement",
            policy_generation="policy:1",
            appraisal_ref="appraisal:1",
        )
