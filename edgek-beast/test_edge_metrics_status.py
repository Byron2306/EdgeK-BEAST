from benchmarks.edge_metrics_benchmark import os_bypass_status


def test_os_bypass_status_reports_missing_libraries_cleanly():
    status = os_bypass_status({
        "supported_modes": {"af_packet_tpacket_v3_mmap": True},
        "dpdk": {"available": False, "libraries": {"rte_eal": None, "rte_ethdev": None}},
        "af_xdp": {"available": False, "libraries": {"xdp": None, "bpf": "libbpf.so.1"}},
    })

    assert status["status"] == "native_libraries_missing"
    assert status["missing_dpdk_libraries"] == ["rte_eal", "rte_ethdev"]
    assert status["missing_af_xdp_libraries"] == ["xdp"]
