"""Experimental Task 4: zero-copy KV handoff between local processes (IEI v0.9 §7.12 Table 14, Phase 9)."""
from __future__ import annotations

import fcntl
import os

import pytest

from app.kernel.compute.kv_memfd_handoff import KV_ENV, ZeroCopyKVTransport
from app.kernel.governance.governor_spine import ComputeGovernorSpine

ON = {KV_ENV: "1"}
IDENTITY = {"model": "qwen3:4b", "tokenizer": "sha256:" + "7" * 64, "engine": "llama.cpp", "engine_version": "b4000",
            "precision": "fp16"}
PAYLOAD = os.urandom(1 << 20)


def transport(env=ON, governor=None):
    return ZeroCopyKVTransport(governor=governor or ComputeGovernorSpine(enforce=True), env=env)


def manifest(t):
    return t.manifest(IDENTITY, system_prompt="SECRET-SYSTEM-PROMPT", prompt_prefix="prefix tokens", payload=PAYLOAD)


def test_flag_default_off():
    with pytest.raises(PermissionError, match=KV_ENV):
        transport(env={}).manifest(IDENTITY, system_prompt="s", prompt_prefix="p", payload=b"x")


def test_manifest_is_host_local_unpublishable_and_not_reusable_yet():
    m = manifest(transport())
    assert m["privacy"] == "host_local" and m["publishable"] is False and m["reuse_allowed"] is False
    assert m["engine_identity"]["engine"] == "llama.cpp" and m["payload_sha256"].startswith("sha256:")
    assert "SECRET-SYSTEM-PROMPT" not in str(m) and "prefix tokens" not in str(m)  # hashes only


def test_sealed_memfd_handoff_is_zero_copy_read_only_and_custodied():
    t = transport()
    sender, receiver = t.pair()
    m = manifest(t)
    sent = t.send(sender, m, PAYLOAD)
    assert sent["governor"]["outcome"] == "admit"
    handoff = t.receive(receiver, expected_identity=IDENTITY)
    try:
        assert handoff.view.readonly and bytes(handoff.view) == PAYLOAD
        with pytest.raises(TypeError):
            handoff.view[0] = 1
        seals = fcntl.fcntl(handoff.fd, fcntl.F_GET_SEALS)
        assert seals & fcntl.F_SEAL_WRITE and seals & fcntl.F_SEAL_SEAL
        assert handoff.manifest["manifest_digest"] == m["manifest_digest"]
        assert handoff.custody_receipt["direction"] == "received"
        assert t.verify_custody() is True
    finally:
        handoff.close()


def test_engine_identity_mismatch_refused():
    t = transport()
    sender, receiver = t.pair()
    t.send(sender, manifest(t), PAYLOAD)
    with pytest.raises(PermissionError, match="engine identity"):
        t.receive(receiver, expected_identity={**IDENTITY, "engine": "vllm"})


def test_reuse_allowed_only_after_restore_verification():
    t = transport()
    sender, receiver = t.pair()
    t.send(sender, manifest(t), PAYLOAD)
    handoff = t.receive(receiver, expected_identity=IDENTITY)
    try:
        assert t.verify_restore(handoff, lambda view: False)["reuse_allowed"] is False
        verified = t.verify_restore(handoff, lambda view: bytes(view[:16]) == PAYLOAD[:16])
        assert verified["reuse_allowed"] is True and verified["restore_check"]["passed"] is True
        assert verified["publishable"] is False
    finally:
        handoff.close()


def test_publication_is_always_refused():
    t = transport()
    with pytest.raises(PermissionError, match="never published"):
        t.publish(manifest(t))
    m = dict(manifest(t), privacy="commons")
    with pytest.raises(PermissionError):
        t.send(t.pair()[0], m, PAYLOAD)


def test_payload_tamper_and_lease_replay_refused():
    t = transport()
    sender, receiver = t.pair()
    with pytest.raises(ValueError, match="payload"):
        t.send(sender, manifest(t), PAYLOAD[:-1] + b"\0")
    m = manifest(t)
    offer = t.send(sender, m, PAYLOAD)["offer"]
    t.receive(receiver, expected_identity=IDENTITY).close()
    fd = t._seal(m, PAYLOAD)
    sender.send_capsule(offer, fd)  # replay the same one-use lease
    with pytest.raises(PermissionError, match="replay|sequence"):
        t.receive(receiver, expected_identity=IDENTITY)
    os.close(fd)


def test_governor_refusal_blocks_send():
    class Refuse(ComputeGovernorSpine):
        def admit(self, episode, proposal):
            from dataclasses import replace
            return replace(super().admit(episode, proposal), outcome="refuse", reasons=("operator_refused",))

    t = transport(governor=Refuse(enforce=True))
    with pytest.raises(PermissionError, match="refuse"):
        t.send(t.pair()[0], manifest(t), PAYLOAD)
