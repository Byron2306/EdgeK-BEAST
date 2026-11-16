"""Sealed memfd crystal capsule: seals, digests, separate-process zero-network replay, negative controls."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.kernel.compute import crystal_memfd_capsule as cap
from app.kernel.compute.coding_crystals import (
    CRYSTAL_PARAMETERS,
    RECIPE_FIX_FAILING_ASSERTION,
    CodingCrystalCandidate,
    coding_catalog_digest,
)

ON = {cap.CAPSULE_ENV: "1"}
CONFIG = "SERVICE_NAME = 'billing'\nINVOICE_RETRY_LIMIT = 3\nGRACE_DAYS = 14\n"
TESTS = ("import unittest\nfrom billing.config import INVOICE_RETRY_LIMIT, GRACE_DAYS\n\n"
         "class T(unittest.TestCase):\n"
         "    def test_retry(self):\n        self.assertEqual(INVOICE_RETRY_LIMIT, 5)\n"
         "    def test_grace(self):\n        self.assertEqual(GRACE_DAYS, 14)\n")
VERIFY = ["/usr/bin/python3", "-m", "unittest", "test_billing_config"]


@pytest.fixture(autouse=True)
def _flag(monkeypatch):
    monkeypatch.setenv(cap.CAPSULE_ENV, "1")


def _repo(root: Path) -> Path:
    (root / "billing").mkdir(parents=True)
    (root / "billing" / "__init__.py").write_text("")
    (root / "billing" / "config.py").write_text(CONFIG)
    (root / "test_billing_config.py").write_text(TESTS)
    return root


def _crystal() -> CodingCrystalCandidate:
    return CodingCrystalCandidate(crystal_id="", task_family="fix-failing-config-constant",
                                  steps=RECIPE_FIX_FAILING_ASSERTION, parameters=CRYSTAL_PARAMETERS,
                                  opcode_catalog_digest=coding_catalog_digest(), source_run_id="cold",
                                  source_envelope_digest="sha256:" + "a" * 64,
                                  learned_budget={"model_turns": 1.0}).sealed()


def _capsule(tmp_path, *, sha_after=None, tests_run=2):
    root = _repo(tmp_path / "repo")
    fixed = CONFIG.replace("INVOICE_RETRY_LIMIT = 3", "INVOICE_RETRY_LIMIT = 5").encode()
    c = _crystal()
    payload = cap.build_payload(c, registry_record_digest="sha256:" + "b" * 64, promotion={"approved_by": "test"},
                                parameters={"implementation_target": "billing/config.py", "verify_command": VERIFY},
                                postcondition={"verify_command": VERIFY, "implementation_target": "billing/config.py",
                                               "expect_returncode": 0, "tests_run": tests_run,
                                               "target_sha256_after": sha_after or cap.sha256_bytes(fixed)},
                                binding={"root": str(root), "worktree": str(tmp_path / "wt")})
    return c, payload, cap.build_manifest(payload, crystal_id=c.crystal_id, crystal_digest=c.digest), tmp_path / "wt"


def test_flag_default_off(tmp_path):
    _c, payload, manifest, _wt = _capsule(tmp_path)
    with pytest.raises(PermissionError):
        cap.seal_capsule(manifest, payload, env={})


def test_seals_read_back_and_writes_refused(tmp_path):
    _c, payload, manifest, _wt = _capsule(tmp_path)
    fd, stats = cap.seal_capsule(manifest, payload, env=ON)
    try:
        assert stats["seal_names"] == ["F_SEAL_SEAL", "F_SEAL_SHRINK", "F_SEAL_GROW", "F_SEAL_WRITE"]
        assert stats["write_calls"] >= 2 and stats["bytes_written"] == stats["capsule_bytes"]
        assert cap.write_attempt_refused(fd)["refused"] is True
        m, view, keep, opened = cap.open_capsule(fd, expected_manifest_digest=manifest["manifest_digest"])
        assert cap.sha256_bytes(view) == manifest["payload_sha256"] and opened["mmap_access"] == "ACCESS_READ"
        view.release()
        keep[0].release()
        keep[1].close()
    finally:
        os.close(fd)


def test_child_replays_with_zero_network_and_postcondition_passes(tmp_path):
    c, payload, manifest, wt = _capsule(tmp_path)
    fd, _ = cap.seal_capsule(manifest, payload, env=ON)
    try:
        out = cap.handoff_to_replay_child(fd, manifest, admit_token="sha256:test")
    finally:
        os.close(fd)
    assert out["ok"] is True, out.get("refused")
    assert out["admit_token_echo"] == "sha256:test" and out["fds_received"] == 1
    assert out["capsule"]["payload_sha256_child"] == manifest["payload_sha256"]
    assert out["replay"]["model_calls"] == 0 and out["replay"]["edit"]["new_text"] == "INVOICE_RETRY_LIMIT = 5"
    assert all(out["network"][k] == 0 for k in ("inet_sockets", "connects", "dns_lookups", "http_sends"))
    assert out["postcondition"]["passed"] and cap.check_postcondition(wt, {
        "verify_command": VERIFY, "implementation_target": "billing/config.py", "tests_run": 2})["passed"]
    assert out["parent_observed"]["fd_pass_bytes_sent"] < 512 < len(payload)


def test_tampered_unsealed_and_wrong_postcondition_are_refused(tmp_path):
    c, payload, manifest, wt = _capsule(tmp_path / "a")
    tampered = payload.replace(b"\"expect_returncode\":0", b"\"expect_returncode\":1", 1)
    assert tampered != payload
    fd, _ = cap.seal_capsule(manifest, tampered, env=ON)  # manifest digest no longer matches the bytes
    try:
        out = cap.handoff_to_replay_child(fd, manifest, admit_token="t")
    finally:
        os.close(fd)
    assert out["ok"] is False and "tampered" in out["refused"] and "replay" not in out
    fd, _ = cap.seal_capsule(manifest, payload, seal=False, env=ON)
    try:
        out = cap.handoff_to_replay_child(fd, manifest, admit_token="t")
    finally:
        os.close(fd)
    assert out["ok"] is False and "not sealed" in out["refused"]
    _c, payload2, manifest2, _wt = _capsule(tmp_path / "b", sha_after="sha256:" + "0" * 64)
    fd, _ = cap.seal_capsule(manifest2, payload2, env=ON)
    try:
        out = cap.handoff_to_replay_child(fd, manifest2, admit_token="t")
    finally:
        os.close(fd)
    assert out["ok"] is False and out["replay"]["ok"] is True
    assert out["postcondition"]["checks"]["target_sha256_after"] is False


def test_pipe_baseline_copies_twice(tmp_path):
    _c, payload, manifest, _wt = _capsule(tmp_path)
    base = cap.pipe_copy_baseline(payload)
    assert base["transport_copies_bytes"] == 2 * len(payload) and base["sha256_child"] == cap.sha256_bytes(payload)
