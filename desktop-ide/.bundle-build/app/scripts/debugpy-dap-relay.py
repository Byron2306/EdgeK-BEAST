#!/usr/bin/env python3
"""Bridge debugpy's loopback DAP socket to stdio for the BEAST protocol host.

debugpy intentionally exposes its adapter as a TCP debug server. Keeping that
detail in this tiny, local-only relay lets Electron use the same framed stdio
session implementation for LSP and DAP, without giving the renderer sockets.
"""

import socket
import subprocess
import sys
import threading
import time
import os


def reserve_port():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    listener.close()
    return port


def forward_stderr(stream):
    for chunk in iter(lambda: stream.read(65536), b""):
        sys.stderr.buffer.write(chunk)
        sys.stderr.buffer.flush()


def forward_socket(source):
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                return
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
    except OSError:
        return


def connect(port):
    deadline = time.monotonic() + 8
    last_error = None
    while time.monotonic() < deadline:
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            client.settimeout(None)
            return client
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError(f"debugpy adapter did not open its local DAP socket: {last_error}")


def main():
    port = reserve_port()
    adapter = subprocess.Popen(
        [sys.executable, "-m", "debugpy.adapter", "--host", "127.0.0.1", "--port", str(port)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    stderr_thread = threading.Thread(target=forward_stderr, args=(adapter.stderr,), daemon=True)
    stderr_thread.start()
    client = None
    try:
        client = connect(port)
        socket_thread = threading.Thread(target=forward_socket, args=(client,), daemon=True)
        socket_thread.start()
        while True:
            chunk = sys.stdin.buffer.read1(65536)
            if not chunk:
                break
            if os.environ.get("BEAST_DEBUG_PROTOCOL") == "1":
                sys.stderr.write(f"debugpy relay forwarded {len(chunk)} bytes to adapter\n")
            client.sendall(chunk)
    finally:
        if client:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        if adapter.poll() is None:
            adapter.terminate()
            try:
                adapter.wait(timeout=2)
            except subprocess.TimeoutExpired:
                adapter.kill()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stderr.write(f"debugpy DAP relay failed: {exc}\n")
        sys.exit(1)
