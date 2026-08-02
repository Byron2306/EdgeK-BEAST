from __future__ import annotations

import copy

import pytest

from app.kernel.approvals.revocation import RevocationPolicyStore


def _store(tmp_path):
    return RevocationPolicyStore(tmp_path)


def _revoke(store, target_type="CAPABILITY", target_id="cap_1", generation="policy:1"):
    return store.revoke({
        "target_type": target_type,
        "target_id": target_id,
        "reason": "operator emergency stop",
        "operator_id": "operator:byron",
        "policy_generation": generation,
    })


def test_revocation_is_durable_and_restart_safe(tmp_path):
    record = _revoke(_store(tmp_path))
    restored = _store(tmp_path)
    assert restored.is_revoked("CAPABILITY", "cap_1")
    assert restored.verify_revocation(record)


def test_duplicate_revocation_is_idempotent(tmp_path):
    store = _store(tmp_path)
    first = _revoke(store)
    second = _revoke(store)
    assert first["revocation_id"] == second["revocation_id"]
    assert len(store.list_revocations()) == 1


def test_revocation_record_cannot_grant_authority(tmp_path):
    store = _store(tmp_path)
    record = _revoke(store)
    tampered = copy.deepcopy(record)
    tampered["grants_authority"] = True
    assert not store.verify_revocation(tampered)


def test_assert_active_rejects_revoked_capability(tmp_path):
    store = _store(tmp_path)
    _revoke(store)
    with pytest.raises(ValueError, match="capability is revoked"):
        store.assert_active({"capability_id": "cap_1", "policy_generation": "policy:1"})


def test_policy_generation_revocation_invalidates_bound_artifacts(tmp_path):
    store = _store(tmp_path)
    _revoke(store, "POLICY_GENERATION", "policy:old", "policy:new")
    with pytest.raises(ValueError, match="policy_generation is revoked"):
        store.assert_active({"capability_id": "cap_safe", "policy_generation": "policy:old"})


def test_create_and_activate_policy_generation(tmp_path):
    store = _store(tmp_path)
    draft = store.create_policy_generation({
        "generation_id": "policy:1",
        "policy": {"permission_mode": "GUIDED"},
        "operator_id": "operator:byron",
        "reason": "initial governed policy",
    })
    assert draft["status"] == "DRAFT"
    active = store.activate_policy_generation("policy:1", operator_id="operator:byron", reason="reviewed")
    assert active["status"] == "ACTIVE"
    assert store.current_policy_generation()["generation_id"] == "policy:1"


def test_new_policy_supersedes_old_without_retroactive_grant(tmp_path):
    store = _store(tmp_path)
    for generation, parent in (("policy:1", ""), ("policy:2", "policy:1")):
        store.create_policy_generation({
            "generation_id": generation,
            "parent_generation": parent,
            "policy": {"generation": generation},
            "operator_id": "operator:byron",
            "reason": "test generation",
        })
        store.activate_policy_generation(generation, operator_id="operator:byron", reason="reviewed")
    current = store.current_policy_generation()
    assert current["generation_id"] == "policy:2"
    assert current["retroactive_grant_allowed"] is False


def test_active_policy_cannot_be_revoked_before_supersession(tmp_path):
    store = _store(tmp_path)
    store.create_policy_generation({
        "generation_id": "policy:1", "policy": {"mode": "GUIDED"},
        "operator_id": "operator:byron", "reason": "initial",
    })
    store.activate_policy_generation("policy:1", operator_id="operator:byron", reason="reviewed")
    with pytest.raises(ValueError, match="must be superseded"):
        store.revoke_policy_generation("policy:1", operator_id="operator:byron", reason="retire")


def test_revocation_check_receipt_is_deny_only(tmp_path):
    store = _store(tmp_path)
    _revoke(store, "RUN", "run_12")
    receipt = store.check({"run_id": "run_12"})
    assert receipt["active"] is False
    assert receipt["grants_authority"] is False
    assert receipt["authority"] == "revocation_status_only"


def test_unknown_target_type_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        _revoke(_store(tmp_path), "MAGIC_WAND", "wand_1")
