#!/usr/bin/env python3
"""Relay Delve's loopback-only DAP socket over framed stdio for BEAST."""

import os
import socket
import subprocess
import sys
import threading
import time


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
    deadline = time.monotonic() + 10
    last_error = None
    while time.monotonic() < deadline:
        try:
            client = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            client.settimeout(None)
            return client
        except OSError as error:
            last_error = error
            time.sleep(0.05)
    raise RuntimeError(f"Delve did not open its local DAP socket: {last_error}")


def main():
    if len(sys.argv) != 2:
        raise RuntimeError("Expected the verified Delve executable path.")
    executable = os.path.realpath(sys.argv[1])
    if not os.path.isfile(executable) or not os.access(executable, os.X_OK):
        raise RuntimeError("The verified Delve executable is unavailable.")
    port = reserve_port()
    adapter = subprocess.Popen(
        [executable, "dap", "--listen", f"127.0.0.1:{port}", "--check-go-version=false"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    threading.Thread(target=forward_stderr, args=(adapter.stderr,), daemon=True).start()
    client = None
    try:
        client = connect(port)
        threading.Thread(target=forward_socket, args=(client,), daemon=True).start()
        while True:
            chunk = sys.stdin.buffer.read1(65536)
            if not chunk:
                break
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
        sys.stderr.write(f"Delve DAP relay failed: {exc}\n")
        sys.exit(1)
