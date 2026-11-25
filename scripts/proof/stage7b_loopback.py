"""Reserve an exclusive loopback listener which can be restarted after TCP close."""

import errno
import socket


def reserve_lab_listener(port: int) -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Allows reuse of closed connections in TIME_WAIT, not live listeners.
        # Do not enable SO_REUSEPORT, which can share a live listener.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", port))
        listener.listen()
        return listener
    except OSError as exc:
        listener.close()
        if exc.errno == errno.EADDRINUSE:
            raise OSError(errno.EADDRINUSE, f"Commons loopback 127.0.0.1:{port} is busy; "
                          "choose another three-port range with --base-port") from exc
        raise
