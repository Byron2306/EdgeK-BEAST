from app.kernel.networking.host_enforcement import HostEnforcementController


def test_host_enforcement_discovery_and_plans_are_operator_gated(tmp_path):
    (tmp_path / "sys/kernel/sched_ext").mkdir(parents=True)
    (tmp_path / "sys/fs/bpf").mkdir(parents=True)
    controller = HostEnforcementController(root=tmp_path)
    state = controller.capabilities()
    assert {item["name"] for item in state["capabilities"]} == {"sched_ext", "resctrl", "damon", "vrf", "af_xdp"}
    plan = controller.plan("sched_ext", {})
    assert plan["dry_run"] is True and plan["opaque_program_loading"] is True
    assert controller.apply("sched_ext", {}, approved=False, allow_host_mutation=False)["status"] == "approval_required"
