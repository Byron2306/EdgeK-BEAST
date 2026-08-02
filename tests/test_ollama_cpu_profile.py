from pathlib import Path
from app.kernel.compute.ollama_cpu_profile import detect_topology, request_options


def test_cpu_profile_counts_physical_core_pairs(tmp_path: Path, monkeypatch):
    for index, core in enumerate(("0", "0", "1", "1")):
        topology = tmp_path / f"cpu{index}" / "topology"
        topology.mkdir(parents=True)
        (topology / "core_id").write_text(core)
        (topology / "physical_package_id").write_text("0")
    result = detect_topology(tmp_path)
    assert result.logical_cpus == 4
    assert result.physical_cores == 2
    monkeypatch.setenv("BEAST_OLLAMA_NUM_THREAD", "2")
    assert request_options()["num_thread"] == 2
