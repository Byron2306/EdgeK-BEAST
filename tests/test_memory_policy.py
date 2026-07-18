from app.kernel.compute.memory_policy import MemoryPolicy


def test_memory_capability_discovery_is_read_only(tmp_path):
    (tmp_path / "resctrl").mkdir(); (tmp_path / "damon").mkdir(); (tmp_path / "zswap").mkdir()
    caps = MemoryPolicy(resctrl_root=tmp_path / "resctrl", damon_root=tmp_path / "damon", zswap_path=tmp_path / "zswap").capabilities()
    assert caps.resctrl and caps.damon and caps.zswap


def test_memory_classes_have_pressure_aware_advice(tmp_path):
    policy = MemoryPolicy(resctrl_root=tmp_path / "none", damon_root=tmp_path / "none2", zswap_path=tmp_path / "none3")
    assert policy.advise("operator").action == "preserve"
    assert policy.advise("active_model").residency == "hot"
    assert policy.advise("inactive_worktree", pressure=60).action == "reclaimable"

