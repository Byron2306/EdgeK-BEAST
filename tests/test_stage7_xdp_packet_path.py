import hashlib
import socket
import threading

import pytest


@pytest.fixture
def lab():
    from scripts.proof import run_stage7_xdp_packet_path
    return run_stage7_xdp_packet_path


@pytest.mark.parametrize("corrupt", [False, True])
def test_udp_probe_checks_every_byte(lab, corrupt):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        seen = []

        def echo():
            for _ in range(3):
                packet, peer = server.recvfrom(2048)
                seen.append(packet)
                server.sendto(packet[:-1] + bytes([packet[-1] ^ 1]) if corrupt else packet, peer)

        thread = threading.Thread(target=echo)
        thread.start()
        result = lab.probe(server.getsockname(), 3, 64, 0.001, 0.02)
        thread.join()
    assert [int.from_bytes(packet[:4], "big") for packet in seen] == [0, 1, 2]
    assert all(len(packet) == 64 for packet in seen)
    assert result["sent_sha256"] == hashlib.sha256(b"".join(seen)).hexdigest()
    assert result["valid"] == (0 if corrupt else 3)
    assert result["unexpected"] == (3 if corrupt else 0)


def test_xdp_verification_requires_observed_mode_and_counters(lab):
    data = {"sent": 4, "valid": 4, "unexpected": 0, "sent_sha256": "x", "echo_sha256": "x"}
    counters = {"xdp_packets_seen": 4, "xdp_socket_misses": 0, "packets_rx": 4, "packets_tx": 4}
    assert lab.verified("copy", "copy", data, counters)
    assert not lab.verified("copy", "unknown", data, counters)
    assert not lab.verified("zero_copy", "copy", data, counters)
    assert not lab.verified("copy", "copy", data, counters | {"packets_rx": 0})
    assert not lab.verified("copy", "copy", data | {"unexpected": 1}, counters)
