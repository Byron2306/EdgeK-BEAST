from pathlib import Path

from app.kernel.sensorium.ollama_runtime_sensor import OllamaRuntimeSensor
from app.kernel.sensorium.workspace_invalidation import WorkspaceInvalidationBus


def _fake_proc(root: Path) -> None:
    process = root / "123"
    process.mkdir(parents=True)
    (process / "comm").write_text("ollama\n")
    (process / "cmdline").write_text("ollama\x00serve\x00")
    # Linux proc stat fields: pid, comm, state, ..., utime(14), stime(15),
    # starttime(22), rss(24).  split indexes are 13, 14, 21, 23.
    fields = ["123", "(ollama)", "S"] + ["0"] * 21
    fields[13] = "7"
    fields[14] = "3"
    fields[21] = "99"
    fields[23] = "4"
    (process / "stat").write_text(" ".join(fields))
    (process / "io").write_text("read_bytes: 10\nwrite_bytes: 20\n")
    (process / "status").write_text("voluntary_ctxt_switches: 2\nnonvoluntary_ctxt_switches: 1\n")
    (process / "fd").mkdir()


def test_runtime_sensor_is_read_only_and_reports_delta(tmp_path: Path):
    _fake_proc(tmp_path)
    sensor = OllamaRuntimeSensor(tmp_path)
    before = sensor.sample()
    assert before["collector"] == "procfs_runtime"
    assert before["processes"][0]["pid"] == 123
    assert before["processes"][0]["rss_bytes"] >= 0

    (tmp_path / "123" / "io").write_text("read_bytes: 30\nwrite_bytes: 25\n")
    after = sensor.sample()
    delta = sensor.delta(before, after)
    assert delta["processes"][0]["read_bytes"] == 20
    assert delta["processes"][0]["write_bytes"] == 5


def test_workspace_bus_emits_only_real_changes(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text("value = 1\n")
    bus = WorkspaceInvalidationBus()
    assert bus.poll(tmp_path) == []
    source.write_text("value = 2\n")
    changes = bus.poll(tmp_path)
    assert len(changes) == 1
    assert changes[0].kind == "modified"
    assert changes[0].path == str(source)

