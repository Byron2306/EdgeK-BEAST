from __future__ import annotations
import importlib.util
import json
import os
import socket
import struct
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).parents[1]

def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

sm = load("sm", "app/kernel/system_monitor.py")
aw = load("aw", "app/kernel/app_watcher.py")
br = load("br", "app/kernel/observability/bpf_ring_buffer.py")
fp = load("fp", "app/kernel/storage/file_server_proxy.py")
eq = load("eq", "app/kernel/evidence/equivalence_engine.py")


def test_psi_parser_and_score(tmp_path):
    for name in ("cpu", "io", "memory"):
        (tmp_path / name).write_text("some avg10=10.00 avg60=2.00 avg300=1.00 total=10\nfull avg10=1.00 avg60=0.00 avg300=0.00 total=1\n")
    snap = sm.SystemMonitor(psi_root=tmp_path).get_pressure()
    assert snap.cpu.some.avg10 == 10.0
    assert snap.normalized_score == pytest.approx(0.1)


def test_kernel_mutations_are_deny_by_default(tmp_path):
    monitor = sm.SystemMonitor(zswap_root=tmp_path)
    with pytest.raises(sm.MutationDenied):
        monitor.set_zswap(True)


def test_resctrl_writes_are_validated(tmp_path):
    root = tmp_path / "resctrl"; root.mkdir()
    group = root / "Local_Model"; group.mkdir()
    (group / "schemata").write_text(""); (group / "tasks").write_text("")
    monitor = sm.SystemMonitor(resctrl_root=root, allow_mutation=True)
    receipt = monitor.create_resctrl_group("Local_Model", schemata="L3:0=ff", task_ids=[123])
    assert receipt.applied and (group / "schemata").read_text() == "L3:0=ff\n"


def test_memfd_roundtrip_when_available():
    if not hasattr(os, "memfd_create"):
        pytest.skip("memfd unavailable")
    fd = sm.ExecutionPrimitives.memfd_create("beast-test", seal=True)
    try:
        os.write(fd, b"beast")
        os.lseek(fd, 0, os.SEEK_SET)
        assert os.read(fd, 5) == b"beast"
    finally:
        os.close(fd)


def test_bpf_ring_buffer_bounded_decode():
    ring = br.BpfRingBuffer(max_event_bytes=32)
    body = b"{}"
    event = ring.decode(ring.HEADER.pack(7, len(body), 9) + body)
    assert event.event_type == 7 and event.payload == body
    with pytest.raises(br.RingBufferDecodeError):
        ring.decode(ring.HEADER.pack(7, 99, 9) + body)


def test_forwarded_host_only_from_trusted_proxy():
    policy = fp.HostForwardingPolicy(trusted_proxies=["127.0.0.0/8"], allowed_hosts=["beast.local"])
    trusted = policy.resolve({"Host":"internal", "X-Forwarded-Host":"beast.local", "X-Forwarded-Proto":"https"}, remote_ip="127.0.0.1")
    assert trusted.host == "beast.local" and trusted.proto == "https"
    with pytest.raises(fp.ForwardingError):
        policy.resolve({"Host":"internal", "X-Forwarded-Host":"beast.local"}, remote_ip="10.0.0.1")


def test_egraph_bounded_canonicalization():
    engine = eq.EGraphRewriteEngine((eq.RewriteRule("true-and", ["and", True, "x"], "x"),))
    receipt = engine.saturate(["and", True, "x"])
    assert receipt["canonical_expression"] == "x"
    assert receipt["promotion_authorized"] is False
