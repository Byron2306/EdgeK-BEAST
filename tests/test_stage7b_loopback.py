import errno
import socket
import unittest

from scripts.proof.stage7b_loopback import reserve_lab_listener


class LabListenerTests(unittest.TestCase):
    def test_restart_after_server_active_close(self):
        with reserve_lab_listener(0) as first:
            port = first.getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                connected, _ = first.accept()
                with connected:
                    connected.settimeout(2)
                    connected.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(connected.recv(1), b"")
        # Server did the active close, so the port can still have TIME_WAIT sockets.
        with reserve_lab_listener(port) as second:
            self.assertEqual(second.getsockname(), ("127.0.0.1", port))

    def test_reservation_cannot_take_over_a_live_listener(self):
        with reserve_lab_listener(0) as first:
            port = first.getsockname()[1]
            with self.assertRaisesRegex(OSError, f"127.0.0.1:{port}") as caught:
                reserve_lab_listener(port)
            self.assertEqual(caught.exception.errno, errno.EADDRINUSE)
