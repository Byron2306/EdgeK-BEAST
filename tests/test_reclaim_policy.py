"""Acceptance tests for the ordered memory reclaim ladder.

These encode the ordering and guardrails the census demanded:

1. below the actuation threshold the policy is advisory only;
2. the KV crystal tier is the first rung and its observed bytes count;
3. a capsule is only touched when a scoped authorization exists, otherwise the
   step is recorded as ``refused`` and nothing is written;
4. freeze/kill never run without an explicit (destructive) authorization;
5. the receipt reports observed bytes, not requested bytes, and stops as soon
   as the target is met.
"""
from __future__ import annotations

import pytest

from app.kernel.compute.reclaim_policy import ReclaimPolicy


class FakeTier:
    def __init__(self, kv_bytes: int, freed_on_high: int, freed_on_critical: int | None = None):
        self._kv_bytes = kv_bytes
        self._freed = {"high": freed_on_high, "critical": freed_on_critical if freed_on_critical is not None else freed_on_high}
        self.calls: list[str] = []

    def stats(self):
        return {"kv_bytes": self._kv_bytes}

    def reclaim(self, level: str):
        self.calls.append(level)
        request = int(self._kv_bytes * {"high": 0.15, "critical": 0.35}.get(level, 0.0))
        freed = min(request, self._freed.get(level, 0))
        if freed <= 0:
            return None
        return {
            "beast_object_type": "kv_eviction_receipt",
            "requested_bytes": request,
            "evicted": ["kv_test"],
            "freed_bytes": freed,
            "retained_pinned": [],
        }


class FakeCapsule:
    def __init__(self, *, reclaimable: int = 0, fail: str = ""):
        self.reclaimable = reclaimable
        self.fail = fail
        self.calls: list[tuple[str, int]] = []

    def reclaim_memory(self, ask, authorization):
        self.calls.append(("reclaim", ask))
        if self.fail == "reclaim":
            raise RuntimeError("memory.reclaim unavailable")
        gained = min(int(ask), int(self.reclaimable))
        return {
            "beast_object_type": "cgroup_capsule_action_receipt",
            "action": "reclaim",
            "confirmed": gained > 0,
            "details": {"requested_bytes": int(ask), "reclaimed_bytes": gained},
        }

    def freeze(self, frozen, authorization):
        self.calls.append(("freeze", 0))
        return {"action": "freeze", "confirmed": True, "details": {}}

    def kill(self, authorization):
        self.calls.append(("kill", 0))
        return {"action": "kill", "confirmed": True, "details": {}}


class Auth:
    def __init__(self, action: str, mission_id: str, *, destructive: bool = False):
        self.action = action
        self.mission_id = mission_id
        self.approved_by = "operator"
        self.approval_receipt_id = "receipt-1"
        self.reason = "test"
        self.destructive = destructive


def consume(policy: ReclaimPolicy, level: str, **kwargs):
    return policy.run(level, **kwargs).as_dict()


def test_below_threshold_is_advisory_only() -> None:
    tier = FakeTier(kv_bytes=10 * 1024 * 1024, freed_on_high=10 * 1024 * 1024)
    receipt = consume(ReclaimPolicy(kv_tier=tier), "rising")
    assert receipt["acted"] is False
    assert receipt["freed_bytes"] == 0
    assert receipt["stopped_because"] == "below_threshold"
    assert tier.calls == [], "advisory pressure must not mutate the KV tier"


def test_kv_tier_is_first_rung_and_satisfies_target() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=100 * 1024 * 1024)
    capsule = FakeCapsule(reclaimable=1024)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule})
    receipt = consume(policy, "high")
    assert receipt["acted"] is True
    assert receipt["satisfied"] is True
    assert receipt["stopped_because"] == "target_met"
    assert receipt["steps"][0]["step"] == "kv_crystal_eviction"
    assert capsule.calls == [], "capsule must not be touched once KV eviction satisfies the target"


def test_capsule_requires_scoped_authorization() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(reclaimable=8 * 1024 * 1024)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule})
    receipt = consume(policy, "high")
    reclaim_steps = [step for step in receipt["steps"] if step["step"] == "cgroup_memory_reclaim"]
    assert reclaim_steps and reclaim_steps[0]["status"] == "refused"
    assert capsule.calls == []


def test_capsule_reclaim_runs_with_authorization_and_reports_observed_bytes() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(reclaimable=4 * 1024 * 1024)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule})

    def auth(mission_id: str, action: str):
        return Auth(action, mission_id) if action == "reclaim" else None

    receipt = consume(policy, "high", authorization_factory=auth)
    reclaim_steps = [step for step in receipt["steps"] if step["step"] == "cgroup_memory_reclaim"]
    assert reclaim_steps[0]["status"] == "performed"
    assert reclaim_steps[0]["freed_bytes"] == 4 * 1024 * 1024
    assert capsule.calls and capsule.calls[0][0] == "reclaim"


def test_capsule_reclaim_failure_is_unavailable_not_performed() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(fail="reclaim")
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule})

    receipt = consume(policy, "high", authorization_factory=lambda m, a: Auth(a, m))
    step = next(item for item in receipt["steps"] if item["step"] == "cgroup_memory_reclaim")
    assert step["status"] == "unavailable"
    assert step["freed_bytes"] == 0


def test_freeze_and_kill_are_off_by_default_even_when_authorized() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(reclaimable=0)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule})
    receipt = consume(policy, "critical", authorization_factory=lambda m, a: Auth(a, m, destructive=True))
    assert not any(step["step"] in {"cgroup_freeze", "cgroup_kill"} for step in receipt["steps"])
    assert not any(call[0] in {"freeze", "kill"} for call in capsule.calls)


def test_freeze_runs_only_for_critical_with_authorization() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(reclaimable=0)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule}, allow_freeze=True)

    no_auth = consume(policy, "critical")
    assert next(s for s in no_auth["steps"] if s["step"] == "cgroup_freeze")["status"] == "refused"
    assert ("freeze", 0) not in capsule.calls

    with_auth = consume(policy, "critical", authorization_factory=lambda m, a: Auth(a, m))
    assert next(s for s in with_auth["steps"] if s["step"] == "cgroup_freeze")["status"] == "performed"
    assert ("freeze", 0) in capsule.calls


def test_kill_requires_destructive_authorization() -> None:
    tier = FakeTier(kv_bytes=1024 * 1024, freed_on_high=0)
    capsule = FakeCapsule(reclaimable=0)
    policy = ReclaimPolicy(kv_tier=tier, capsules={"m1": capsule}, allow_kill=True)

    receipt = consume(policy, "critical", authorization_factory=lambda m, a: Auth(a, m))
    kill_step = next(s for s in receipt["steps"] if s["step"] == "cgroup_kill")
    assert kill_step["status"] == "refused"
    assert ("kill", 0) not in capsule.calls

    destructive = consume(
        policy, "critical", authorization_factory=lambda m, a: Auth(a, m, destructive=True)
    )
    assert next(s for s in destructive["steps"] if s["step"] == "cgroup_kill")["status"] == "performed"
    assert ("kill", 0) in capsule.calls


def test_no_tier_is_recorded_as_unavailable_not_silent() -> None:
    receipt = consume(ReclaimPolicy(kv_tier=None), "high")
    step = receipt["steps"][0]
    assert step["step"] == "kv_crystal_eviction"
    assert step["status"] == "unavailable"
    assert "no crystal KV tier" in step["reason"]


def test_requested_target_is_bounded_by_policy_cap() -> None:
    tier = FakeTier(kv_bytes=64 * 1024 * 1024 * 1024, freed_on_high=0)
    policy = ReclaimPolicy(kv_tier=tier, total_cap_bytes=2 * 1024 * 1024)
    receipt = consume(policy, "high")
    assert receipt["requested_bytes"] == 2 * 1024 * 1024


def test_receipt_includes_digests_and_authority() -> None:
    tier = FakeTier(kv_bytes=100 * 1024 * 1024, freed_on_high=5 * 1024 * 1024)
    receipt = consume(ReclaimPolicy(kv_tier=tier), "high", snapshot_digest="sha256:" + "a" * 64)
    assert receipt["snapshot_digest"] == "sha256:" + "a" * 64
    assert receipt["policy_digest"].startswith("sha256:")
    assert receipt["authority"] == "ordered_pressure_reclaim_v1"
    assert receipt["beast_object_type"] == "reclaim_receipt"


def test_unknown_level_is_rejected() -> None:
    with pytest.raises(ValueError):
        ReclaimPolicy(kv_tier=None).run("panicking")
