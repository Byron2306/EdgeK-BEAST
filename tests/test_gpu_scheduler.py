from dataclasses import dataclass, field

from app.kernel.compute import gpu_scheduler as gs
from app.kernel.compute import placement


@dataclass(frozen=True)
class C:
    provider: str
    model: str = "m"
    placement: str = "gpu_full"
    options: dict = field(default_factory=dict)


def test_enabled_follows_flags():
    assert not gs.enabled({})
    assert gs.enabled({"BEAST_GOVERNED_INTERCEPTION": "1"})
    assert not gs.enabled({"BEAST_GOVERNED_INTERCEPTION": "1", "BEAST_GPU_SCHEDULER": "0"})
    assert gs.enabled({"BEAST_GPU_SCHEDULER": "1"})


def test_tgi_up_puts_tgi_first_and_drops_gpu_ollama():
    cands = [C("ollama", "qwen3:4b"), C("nim"), C("tgi")]
    assert [c.provider for c in gs.local_candidates(cands, tgi_up=True)] == ["tgi", "nim"]
    cpu = gs.local_candidates(cands, tgi_up=True, allow_cpu_ollama=True)
    assert [c.provider for c in cpu] == ["tgi", "ollama", "nim"] and cpu[1].placement == "cpu"
    assert cpu[1].options["options"]["num_gpu"] == 0


def test_tgi_down_keeps_ollama_and_drops_tgi():
    cands = [C("tgi"), C("ollama"), C("fireworks")]
    assert [c.provider for c in gs.local_candidates(cands, tgi_up=False)] == ["ollama", "fireworks"]


def test_ensure_tgi_gpu_unloads_only_gpu_resident_and_throttles(monkeypatch):
    posted = []
    monkeypatch.setattr(gs, "_post", lambda url, payload, timeout=30: posted.append(payload) or {"done": True})
    monkeypatch.setitem(gs._LAST_PREPARE, "at", 0.0)
    loaded = [{"name": "qwen3:4b", "size_vram_mib": 2381}, {"name": "granite3.3:2b", "size_vram_mib": 0}]
    r = gs.ensure_tgi_gpu(loaded=loaded)
    assert r["action"] == "unloaded" and [p["model"] for p in posted] == ["qwen3:4b"]
    assert posted[0]["keep_alive"] == 0 and r["freed_est_mib"] == 2381
    assert gs.ensure_tgi_gpu(loaded=loaded)["action"] == "skip"
    monkeypatch.setitem(gs._LAST_PREPARE, "at", 0.0)
    assert gs.ensure_tgi_gpu(loaded=[])["action"] == "none"


def test_calibrated_shapes_plan_within_free_vram():
    for model in ("qwen3:4b", "granite3.3:2b", "granite3.2:2b", "qwen2.5-coder:7b"):
        s = placement.SHAPES[model]
        assert s.measured_layer_mib > 0 and s.measured_overhead_mib > 0
        d = placement.plan(model, pressure={"vram_free_mib": 1832, "ram_available_mib": 20000, "swap_free_mib": 0})
        assert d["est_vram_mib"] <= 1832 - 384 + 1, (model, d)


def test_operator_commands_never_executed():
    cmds = gs.operator_commands()
    assert cmds["pause_tgi_for_ollama"] == "docker stop beast-tgi" and isinstance(cmds["resume_tgi"], str)
