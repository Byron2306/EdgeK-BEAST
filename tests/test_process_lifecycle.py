"""Owned-process lifecycle: pidfd teardown, escalation, cgroup.kill, ownership refusal, receipts."""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time

import pytest

from app.kernel.execution.process_lifecycle import OwnershipError, ProcessLifecycle, proc_start_time
from app.kernel.governance.governor_spine import GovernorReceiptLog

PY = sys.executable


def _life(**kw):
    return ProcessLifecycle(receipts=GovernorReceiptLog(None), use_scope=kw.pop("use_scope", False), **kw)


def test_sigterm_teardown_with_receipt_and_reclaim():
    life = _life()
    h = life.spawn([PY, "-c", "import time; time.sleep(60)"], label="disposable")
    r_fd, w_fd = os.pipe()
    life.attach_fd(h, r_fd)
    released = []
    life.on_release(h, "socket_guardian_lease", lambda: released.append("lease"))
    life.on_release(h, "memory_hull_entry", lambda: released.append("hull"))
    out = life.terminate(h, reason="stream_stall", grace_s=3, measure_vram=False)
    os.close(w_fd)
    assert out["signal_path"] == ["pidfd:SIGTERM"] and h.popen.returncode is not None
    assert out["reclaimed"]["fds_closed"] == 1 and released == ["lease", "hull"]
    rec = life.receipts.records()[-1]
    assert rec["type"] == "process_teardown" and rec["trigger"] == "stream_stall" and rec["pid"] == h.pid
    assert rec["start_time"] == h.start_time and life.receipts.verify()["valid"]


def test_escalates_to_sigkill_when_sigterm_ignored():
    life = _life()
    code = "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ready', flush=True); time.sleep(60)"
    h = life.spawn([PY, "-c", code], label="stubborn", stdout=subprocess.PIPE)
    assert h.popen.stdout.readline().strip() == b"ready"
    out = life.terminate(h, reason="runaway_output", grace_s=0.5, measure_vram=False)
    assert out["signal_path"] == ["pidfd:SIGTERM", "pidfd:SIGKILL"] and h.popen.returncode == -9


@pytest.mark.skipif(not shutil.which("systemd-run"), reason="needs systemd --user")
def test_scope_spawn_uses_cgroup_kill_and_reaps_descendants():
    life = _life(use_scope=True)
    code = ("import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']);"
            "print(p.pid, flush=True); time.sleep(60)")
    h = life.spawn([PY, "-c", code], label="tree", stdout=subprocess.PIPE)
    if not h.beast_scope:
        pytest.skip("user scope not available in this session")
    grandchild = int(h.popen.stdout.readline())
    out = life.terminate(h, reason="placement_change", grace_s=1, measure_vram=False)
    assert "cgroup.kill" in out["signal_path"]
    time.sleep(0.5)
    assert proc_start_time(grandchild) is None  # descendant gone too


def test_refuses_foreign_and_protected_processes():
    life = _life()
    with pytest.raises(OwnershipError):
        life.adopt(1, label="init")
    with pytest.raises(OwnershipError):
        life.adopt(os.getpid(), label="self")
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); port = srv.getsockname()[1]; srv.close()
    child = subprocess.Popen([PY, "-c", f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{port})); s.listen(); time.sleep(60)"])
    try:
        time.sleep(0.6)
        guarded = _life(protected_ports=(port,))
        with pytest.raises(OwnershipError, match="protected_port"):
            guarded.adopt(child.pid, label="looks like 8101")
    finally:
        child.kill(); child.wait()


def test_adopt_requires_matching_start_time_and_kill_refuses_after_identity_change():
    life = _life()
    child = subprocess.Popen([PY, "-c", "import time; time.sleep(60)"])
    try:
        with pytest.raises(OwnershipError, match="start_time"):
            life.adopt(child.pid, label="x", expected_start_time=1)
        h = life.adopt(child.pid, label="worker", expected_start_time=proc_start_time(child.pid))
        h.start_time += 1  # simulate PID reuse: recorded identity no longer matches
        with pytest.raises(OwnershipError, match="start_time_changed"):
            life.terminate(h, reason="circuit_open", measure_vram=False)
        assert child.poll() is None  # nothing was signalled
        assert life.receipts.records()[-1]["ok"] is False
    finally:
        child.kill(); child.wait()


def test_unknown_trigger_rejected():
    life = _life()
    h = life.spawn([PY, "-c", "import time; time.sleep(5)"], label="t")
    with pytest.raises(ValueError):
        life.terminate(h, reason="because")
    life.terminate(h, reason="test", measure_vram=False)
