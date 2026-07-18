from pathlib import Path

from app.kernel.compute.socket_inventory import tcp_listeners


def test_socket_inventory_parses_kernel_listener_fixture(tmp_path: Path):
    (tmp_path / "net").mkdir()
    (tmp_path / "net/tcp").write_text("sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n 0: 0100007F:1F45 00000000:0000 0A 0 0 0 0 0 12345\n")
    listeners = tcp_listeners(tmp_path)
    assert listeners[0].address == "127.0.0.1"
    assert listeners[0].port == 8005
    assert listeners[0].inode == "12345"
