"""Bridge from BEAST (Python) to the real Effect TS runtime (Node).

Python builds an *effect program* as plain JSON data and ships it to
``desktop-ide/scripts/effect-rpc.mjs``, which executes it with the installed
``effect`` package. Effects that must touch BEAST state are declared as
``call`` leaves; the Node runtime invokes them back over a loopback HTTP
callback hosted by this module.

This is the Phase 1 FFI boundary: Effect's concurrency, scheduling, timeout,
scoping and fiber semantics live in TypeScript; BEAST tool logic stays Python.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNNER = REPO_ROOT / "desktop-ide" / "scripts" / "effect-rpc.mjs"


# =============================================================================
# Errors
# =============================================================================


class EffectError(RuntimeError):
    """An Effect program failed."""

    def __init__(self, message: str, tag: str = "Error") -> None:
        super().__init__(message)
        self.tag = tag


class EffectTimeoutError(EffectError):
    def __init__(self, message: str = "effect run timed out on the Python side") -> None:
        super().__init__(message, tag="BridgeTimeout")


class EffectUnavailable(RuntimeError):
    """The Effect TS runtime could not be started."""


# =============================================================================
# Program builders (plain data, JSON-serialisable)
# =============================================================================


def succeed(value: Any = None) -> Dict[str, Any]:
    return {"type": "succeed", "value": value}


def fail(message: str) -> Dict[str, Any]:
    return {"type": "fail", "message": message}


def sleep(ms: int) -> Dict[str, Any]:
    return {"type": "sleep", "ms": ms}


def as_(effect: Dict[str, Any], value: Any) -> Dict[str, Any]:
    return {"type": "as", "effect": effect, "value": value}


def call(op: str, args: Optional[Dict[str, Any]] = None, timeout_ms: int = 60000) -> Dict[str, Any]:
    """Leaf effect executed by a Python-registered operation."""
    return {"type": "call", "op": op, "args": args or {}, "timeoutMs": timeout_ms}


def zip_(*effects: Dict[str, Any]) -> Dict[str, Any]:  # noqa: A001 - mirrors Effect.zip
    return {"type": "zip", "effects": list(effects)}


def sequence(*effects: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "sequence", "effects": list(effects)}


def race(*effects: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "race", "effects": list(effects)}


def retry(effect: Dict[str, Any], count: int = 3) -> Dict[str, Any]:
    return {"type": "retry", "effect": effect, "schedule": {"type": "recurs", "params": {"count": count}}}


def retry_exponential(effect: Dict[str, Any], count: int = 3, base_ms: int = 20) -> Dict[str, Any]:
    return {
        "type": "retry",
        "effect": effect,
        "schedule": {"type": "exponential", "params": {"count": count, "baseMs": base_ms}},
    }


def timeout(effect: Dict[str, Any], ms: int) -> Dict[str, Any]:
    return {"type": "timeout", "effect": effect, "ms": ms}


def resource(
    acquire: Dict[str, Any], release: Dict[str, Any], use: Dict[str, Any]
) -> Dict[str, Any]:
    """Bracket: acquire, run use, always release (Effect.acquireRelease + scoped)."""
    return {"type": "resource", "acquire": acquire, "release": release, "use": use}


def fork(effect: Dict[str, Any]) -> Dict[str, Any]:
    """Start an effect and return ``{"fiberId": ...}``."""
    return {"type": "fork", "effect": effect}


def join(fiber_id: str) -> Dict[str, Any]:
    return {"type": "join", "fiberId": fiber_id}


def interrupt(fiber_id: str) -> Dict[str, Any]:
    return {"type": "interrupt", "fiberId": fiber_id}


# =============================================================================
# Bridge
# =============================================================================


@dataclass
class _Pending:
    done: threading.Event = field(default_factory=threading.Event)
    response: Optional[Dict[str, Any]] = None


class EffectTSBridge:
    """Owns one Node Effect runtime process plus the Python callback server."""

    def __init__(self, runner: Optional[Path] = None, node_binary: str = "node") -> None:
        self._runner = Path(runner) if runner else DEFAULT_RUNNER
        self._node = shutil.which(node_binary)
        self._ops: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self._pending: Dict[str, _Pending] = {}
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._stderr_lines: List[str] = []
        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None
        self._callback_url: Optional[str] = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def callback_url(self) -> str:
        if self._callback_url is None:
            self._start_callback_server()
        assert self._callback_url is not None
        return self._callback_url

    def _start_callback_server(self) -> None:
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # keep test output quiet
                pass

            def do_POST(self) -> None:  # noqa: N802
                try:
                    length = int(self.headers.get("content-length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    value = bridge._dispatch_op(payload.get("op", ""), payload.get("args") or {})
                    body = json.dumps({"ok": True, "value": value}).encode()
                except Exception as exc:  # noqa: BLE001 - report to Effect runtime
                    body = json.dumps(
                        {"ok": False, "error": {"message": str(exc), "tag": type(exc).__name__}}
                    ).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass  # Effect may have interrupted the call already

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, name="effect-callback", daemon=True)
        thread.start()
        self._server = server
        self._server_thread = thread
        self._callback_url = f"http://127.0.0.1:{server.server_address[1]}/op"

    def _start(self) -> None:
        if self._process is not None:
            return
        if self._node is None:
            raise EffectUnavailable("node binary not found on PATH")
        if not self._runner.exists():
            raise EffectUnavailable(f"effect runtime script missing: {self._runner}")
        self.callback_url  # ensure the callback server is up first
        logger.info("effect_runtime_starting", extra={"runner": str(self._runner)})
        self._process = subprocess.Popen(
            [self._node, str(self._runner)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(self._runner.parent.parent),
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        self._reader = threading.Thread(target=self._read_stdout, name="effect-reader", daemon=True)
        self._reader.start()
        threading.Thread(target=self._read_stderr, name="effect-stderr", daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        for line in self._process.stdout:
            text = line.strip()
            if not text:
                continue
            try:
                response = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("effect_runtime_bad_line: %s", text[:200])
                continue
            with self._lock:
                pending = self._pending.pop(str(response.get("id")), None)
            if pending is not None:
                pending.response = response
                pending.done.set()

    def _read_stderr(self) -> None:
        assert self._process and self._process.stderr
        for line in self._process.stderr:
            self._stderr_lines.append(line.rstrip())
            if len(self._stderr_lines) > 200:
                del self._stderr_lines[:100]

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            try:
                if process.stdin:
                    process.stdin.write(json.dumps({"id": str(uuid.uuid4()), "op": "shutdown"}) + "\n")
                    process.stdin.flush()
            except (BrokenPipeError, ValueError):
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()

    def __enter__(self) -> "EffectTSBridge":
        self._start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- ops ---------------------------------------------------------------

    def register_op(self, name: str, fn: Callable[[Dict[str, Any]], Any]) -> None:
        self._ops[name] = fn

    def op(self, name: str) -> Callable[[Callable[[Dict[str, Any]], Any]], Callable[[Dict[str, Any]], Any]]:
        def decorator(fn: Callable[[Dict[str, Any]], Any]) -> Callable[[Dict[str, Any]], Any]:
            self.register_op(name, fn)
            return fn

        return decorator

    def _dispatch_op(self, name: str, args: Dict[str, Any]) -> Any:
        fn = self._ops.get(name)
        if fn is None:
            raise KeyError(f"unregistered effect op: {name}")
        return fn(args)

    # -- execution ---------------------------------------------------------

    def _inject_callback_url(self, node: Any) -> Any:
        """Attach this bridge's loopback URL to every ``call`` leaf."""
        if isinstance(node, list):
            return [self._inject_callback_url(item) for item in node]
        if not isinstance(node, dict):
            return node
        result = {key: self._inject_callback_url(value) for key, value in node.items()}
        if result.get("type") == "call":
            result.setdefault("url", self.callback_url)
        return result

    def run(self, program: Dict[str, Any], timeout_s: float = 60.0) -> Any:
        """Execute an effect program and return its success value."""
        self._start()
        assert self._process and self._process.stdin
        program = self._inject_callback_url(program)
        request_id = str(uuid.uuid4())
        pending = _Pending()
        with self._lock:
            self._pending[request_id] = pending
        try:
            self._process.stdin.write(json.dumps({"id": request_id, "op": "run", "program": program}) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise EffectUnavailable(f"effect runtime is not accepting input: {exc}") from exc

        if not pending.done.wait(timeout_s):
            with self._lock:
                self._pending.pop(request_id, None)
            raise EffectTimeoutError(f"no response within {timeout_s}s from Effect runtime")

        response = pending.response or {}
        if response.get("ok"):
            return response.get("value")
        error = response.get("error") or {}
        raise EffectError(error.get("message", "effect failed"), tag=error.get("tag", "Error"))

    async def arun(self, program: Dict[str, Any], timeout_s: float = 60.0) -> Any:
        import asyncio

        return await asyncio.to_thread(self.run, program, timeout_s)

    @property
    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_lines[-20:])


_default_bridge: Optional[EffectTSBridge] = None


def get_bridge() -> EffectTSBridge:
    global _default_bridge
    if _default_bridge is None:
        _default_bridge = EffectTSBridge()
        atexit.register(_default_bridge.close)
    return _default_bridge
