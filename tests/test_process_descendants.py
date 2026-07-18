import os
import subprocess
import sys
import time

import pytest

from app.kernel.execution.process_descendants import LinuxProcessDescendantInspector
from app.kernel.execution.process_identity import LinuxProcessIdentityCollector


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Linux fork is required")
def test_descendant_snapshot_is_content_bound_and_proves_absence_after_exit():
    parent = subprocess.Popen([
        sys.executable,
        "-u",
        "-c",
        "import os,time; p=os.fork(); print(p,flush=True) if p else None; time.sleep(30)",
    ], stdout=subprocess.PIPE, text=True)
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline().strip())
    collector = LinuxProcessIdentityCollector()
    inspector = LinuxProcessDescendantInspector(collector)
    try:
        root = collector.collect(parent.pid, owner_scope="beast_service")
        snapshot = inspector.capture(root)
        assert snapshot.scan_complete is True
        assert [item.pid_at_observation for item in snapshot.descendant_leases] == [child_pid]
        assert inspector.absence(snapshot) is False
        os.kill(child_pid, 9)
        parent.kill()
        parent.wait(timeout=5)
        deadline = time.monotonic() + 3
        while not inspector.absence(snapshot) and time.monotonic() < deadline:
            time.sleep(0.02)
        assert inspector.absence(snapshot) is True
    finally:
        if parent.poll() is None:
            parent.kill()
        parent.wait(timeout=5)
        try:
            os.kill(child_pid, 9)
        except ProcessLookupError:
            pass
