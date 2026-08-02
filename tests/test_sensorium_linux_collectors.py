from pathlib import Path

from app.kernel.sensorium.linux_collectors import collect_socket_observations
from app.kernel.sensorium.runtime import SensoriumRuntime


def _procfs(root: Path) -> None:
    (root / "sys/kernel/random").mkdir(parents=True)
    (root / "sys/kernel/random/boot_id").write_text("boot-test", encoding="utf-8")
    (root / "net").mkdir()
    (root / "net/tcp").write_text("sl local_address rem_address st tx rx tr tm retr uid timeout inode\n   0: 0100007F:1F90 00000000:0000 0A 0 0 0 0 0 42\n", encoding="utf-8")
    for table in ("tcp6", "udp", "udp6"):
        (root / "net" / table).write_text("sl local_address rem_address st tx rx tr tm retr uid timeout inode\n", encoding="utf-8")
    pid = root / "123"; (pid / "fd").mkdir(parents=True); (pid / "ns").mkdir()
    (pid / "stat").write_text("123 (worker) S 1 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 99", encoding="utf-8")
    (pid / "cgroup").write_text("0::/beast", encoding="utf-8")
    (pid / "exe").symlink_to("/usr/bin/worker")
    (pid / "fd" / "5").symlink_to("socket:[42]")
    (pid / "ns" / "pid").symlink_to("/proc/self/ns/pid")
    (pid / "ns" / "mnt").symlink_to("/proc/self/ns/mnt")


def test_procfs_collector_covers_tcp_udp_ip_families_and_runtime_keeps_projection_payload_free(tmp_path):
    root = tmp_path / "proc"; _procfs(root)
    rows, receipt = collect_socket_observations(workspace_id="workspace-a", proc_root=root)
    assert len(rows) == 1 and rows[0]["family"] == "AF_INET" and rows[0]["protocol"] == "TCP"
    assert receipt["read_only"] is True
    runtime = SensoriumRuntime(export_root=tmp_path / "out", boot_id="boot-test")
    result = runtime.collect_linux_sockets(workspace_id="workspace-a", proc_root=root)
    assert result["admitted"] == 1
    state = runtime.state()
    assert state["collectors"][0]["collector"] == "procfs"
    assert state["socket_topology"][0]["local_port"] == 8080
