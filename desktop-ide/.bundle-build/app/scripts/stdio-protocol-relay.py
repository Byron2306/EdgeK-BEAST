#!/usr/bin/env python3
"""Transparent stdio relay for Node 24 language-server stream compatibility."""

from __future__ import annotations

import subprocess
import sys
import threading


def pump(source, target, close_target: bool = False) -> None:
    try:
        read = getattr(source, "read1", source.read)
        while True:
            chunk = read(65536)
            if not chunk:
                break
            target.write(chunk)
            target.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        if close_target:
            try:
                target.close()
            except OSError:
                pass


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: stdio-protocol-relay.py COMMAND [ARGS...]", file=sys.stderr)
        return 2
    process = subprocess.Popen(
        sys.argv[1:],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    threads = [
        threading.Thread(target=pump, args=(sys.stdin.buffer, process.stdin, True), daemon=True),
        threading.Thread(target=pump, args=(process.stdout, sys.stdout.buffer), daemon=True),
        threading.Thread(target=pump, args=(process.stderr, sys.stderr.buffer), daemon=True),
    ]
    for thread in threads:
        thread.start()
    return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
