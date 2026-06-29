import pytest

from app.kernel.networking.os_bypass import PacketCaptureConfig, PacketRingConfig, build_udp_probe_payload, capabilities, parse_packet_frame


def test_os_bypass_capabilities_reports_modes():
    caps = capabilities()

    assert "supported_modes" in caps
    assert "af_packet_tpacket_v3_mmap" in caps["supported_modes"]
    assert "dpdk" in caps["supported_modes"]
    assert "af_xdp" in caps["supported_modes"]
    assert "dpdk" in caps
    assert "af_xdp" in caps


def test_packet_ring_config_validation():
    config = PacketRingConfig(interface="lo", block_size=4096, block_count=2, frame_size=1024)

    assert config.frame_count == 8
    assert config.mmap_bytes == 8192

    with pytest.raises(ValueError):
        PacketRingConfig(interface="", block_size=4096, block_count=1, frame_size=1024).validate()

    with pytest.raises(ValueError):
        PacketRingConfig(interface="lo", block_size=4097, block_count=1, frame_size=1024).validate()


def test_packet_capture_config_validation():
    PacketCaptureConfig(interface="lo", marker="BEAST_TEST", port=45555, timeout_ms=250).validate()

    with pytest.raises(ValueError):
        PacketCaptureConfig(interface="", marker="BEAST_TEST").validate()

    with pytest.raises(ValueError):
        PacketCaptureConfig(interface="lo", marker="", port=45555).validate()

    with pytest.raises(ValueError):
        PacketCaptureConfig(interface="lo", marker="BEAST_TEST", port=70000).validate()


def test_build_udp_probe_payload_contains_marker():
    payload = build_udp_probe_payload("BEAST_TEST_MARKER")

    assert b"BEAST_TEST_MARKER:" in payload


def test_parse_packet_frame_extracts_ipv4_udp_marker():
    marker = b"BEAST_OS_BYPASS_PROBE"
    udp_length = 8 + len(marker)
    total_length = 20 + udp_length
    ethernet = b"\xaa" * 6 + b"\xbb" * 6 + b"\x08\x00"
    ipv4 = bytes([
        0x45, 0x00,
        (total_length >> 8) & 0xFF, total_length & 0xFF,
        0x00, 0x01,
        0x00, 0x00,
        64,
        17,
        0x00, 0x00,
        127, 0, 0, 1,
        127, 0, 0, 1,
    ])
    udp = bytes([
        0xB1, 0xF3,
        0xB1, 0xF4,
        (udp_length >> 8) & 0xFF, udp_length & 0xFF,
        0x00, 0x00,
    ])
    sample = parse_packet_frame(ethernet + ipv4 + udp + marker, marker=marker)

    assert sample["marker_found"] is True
    assert sample["ethertype"] == "0x0800"
    assert sample["ip_protocol_name"] == "udp"
    assert sample["src_ip"] == "127.0.0.1"
    assert sample["dst_ip"] == "127.0.0.1"
    assert sample["src_port"] == 45555
    assert sample["dst_port"] == 45556
