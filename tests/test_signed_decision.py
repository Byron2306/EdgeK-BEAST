import base64
import hashlib
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app.kernel.integration.signed_decision import SignedDecision, verify_decision


def test_signed_decision_verifies_and_binds_request():
    private = Ed25519PrivateKey.generate(); public = private.public_key()
    request = "sha256:" + "a" * 64
    value = SignedDecision("arda", True, request, "policy-1", "nonce-1", "", "arda-key")
    signature = base64.b64encode(private.sign(value.unsigned())).decode()
    payload = {"authority": "arda", "allowed": True, "request_digest": request, "policy_generation": "policy-1", "nonce": "nonce-1", "signature": signature, "verification_material": {"key_id": "arda-key"}}
    assert verify_decision(payload, public, expected_authority="arda", expected_request_digest=request).allowed


def test_unsigned_decision_fails_closed():
    private = Ed25519PrivateKey.generate(); request = "sha256:" + "b" * 64
    payload = {"authority": "metatron", "allowed": True, "request_digest": request}
    import pytest
    with pytest.raises(ValueError, match="incomplete"):
        verify_decision(payload, private.public_key(), expected_authority="metatron", expected_request_digest=request)

