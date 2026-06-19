import pytest

from app.kernel.os_bypass import PacketRingConfig, capabilities


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
