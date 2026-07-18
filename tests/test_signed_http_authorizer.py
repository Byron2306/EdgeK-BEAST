def test_signed_http_authorizer_type_is_available():
    from app.kernel.integration.arda_metatron_bridge import SignedJsonHttpAuthorizer
    assert SignedJsonHttpAuthorizer.__name__ == "SignedJsonHttpAuthorizer"


def test_signed_http_authorizer_requires_decision_capability_and_appraisal(monkeypatch, tmp_path):
    import base64
    import json
    import time
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    import app.kernel.integration.arda_metatron_bridge as bridge_module
    from app.kernel.integration.arda_metatron_bridge import SignedJsonHttpAuthorizer
    from app.kernel.integration.one_use_capability import OneUseCapability
    from app.kernel.integration.signed_decision import SignedDecision, signed_appraisal_body

    private = Ed25519PrivateKey.generate()
    key_path = tmp_path / "arda.pem"
    key_path.write_bytes(private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    digest = "sha256:" + "a" * 64
    decision = SignedDecision("arda", True, digest, "policy-1", "decision-nonce", "", "arda-key")
    capability = OneUseCapability(
        "cap:1", digest, "arda", time.time() + 60, "capability-nonce", "",
        "beast-executor", "policy-1", "appraisal:1", "arda-key",
    )
    appraisal = {
        "appraisal_ref": "appraisal:1", "authority": "arda", "audience": "beast-executor",
        "policy_generation": "policy-1", "state": "verified", "expires_at": time.time() + 60,
        "request_digest": digest, "nonce": "appraisal-nonce", "key_id": "arda-key",
        "evidence_digest": "sha256:" + "b" * 64,
    }
    appraisal["signature"] = base64.b64encode(private.sign(signed_appraisal_body(appraisal))).decode()
    value = {
        "authority": "arda", "allowed": True, "request_digest": digest,
        "policy_generation": "policy-1", "nonce": "decision-nonce",
        "signature": base64.b64encode(private.sign(decision.unsigned())).decode(),
        "verification_material": {"key_id": "arda-key"},
        "capability": {
            **capability.__dict__,
            "signature": base64.b64encode(private.sign(capability.body())).decode(),
        },
        "appraisal": appraisal,
    }

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self): return json.dumps(value).encode()

    monkeypatch.setattr(bridge_module, "urlopen", lambda *_args, **_kwargs: Response())
    authorizer = SignedJsonHttpAuthorizer(
        "https://arda.test/authorize", str(key_path), authority="arda",
        expected_audience="beast-executor", expected_policy_generation="policy-1",
        expected_appraisal_ref="appraisal:1",
    )
    assert authorizer({"request_digest": digest})["allowed"] is True
    value["appraisal"]["expires_at"] += 3600
    assert authorizer({"request_digest": digest}) is False
    value["appraisal"] = {}
    assert authorizer({"request_digest": digest}) is False
