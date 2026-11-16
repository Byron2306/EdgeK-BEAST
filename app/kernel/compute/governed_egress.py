"""Thin governed shims for every direct model-call site (closure 2026-11-16).

Each former direct call (httpx / requests / urllib, sync, async or streamed) now goes through one of:
``post(client, caller, url, **kw)``, ``apost(client, caller, url, **kw)``, ``astream(client, caller, method, url, **kw)``,
``urlopen(caller, request, timeout=...)`` (``caller`` is positional so a one-token rewrite of each call site suffices).

* Flags off (``BEAST_GOVERNED_INTERCEPTION`` unset): byte-for-byte the original call -- same method, same args, no
  extra headers, no receipts. Behaviour-preserving by construction (tests assert the exact call).
* Flags on: the governed client's Compute Governor admits the call (``Proposal(kind="egress")``), the request carries
  ``X-BEAST-Admit: <receipt hash prefix>`` + ``X-BEAST-Caller``, a redacted ``model_egress`` receipt (caller, host,
  path, status, latency, usage tokens when the body reports them -- never prompts, outputs or credentials) is
  appended to the governor chain, and the shared circuit breaker records transport failures. A refusal raises
  ``EgressRefused`` only when ``BEAST_GOVERNED_EGRESS_ENFORCE=1`` (otherwise it is receipted and the call proceeds).
* ``BEAST_ARDA_EGRESS_ADMIT=1``: each admit is also queued for the operator-run ARDA/X7 admit writer
  (``bpf/beast_x7_model_egress_lsm.bpf.c``), which turns it into a short-lived ``beast_admit_tokens`` entry the
  BPF LSM checks on ``connect()`` from measured consumer cgroups.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional

_ON = {"1", "true", "yes", "on"}
_LOCK = threading.Lock()
_STATE: Dict[str, Any] = {}
ROOT = Path(__file__).resolve().parents[3]
ADMIT_QUEUE = Path(os.environ.get("BEAST_ARDA_ADMIT_QUEUE", str(ROOT / ".beast" / "governed-egress" / "admit-queue.jsonl")))


class EgressRefused(PermissionError):
    pass


def enabled() -> bool:
    return str(os.environ.get("BEAST_GOVERNED_INTERCEPTION", "")).strip().lower() in _ON


def _governor():
    with _LOCK:
        gov = _STATE.get("governor")
        if gov is None:
            from app.kernel.governance.governor_spine import ComputeGovernorSpine, GovernorReceiptLog

            path = os.environ.get("BEAST_GOVERNED_EGRESS_RECEIPTS") or str(ROOT / ".beast" / "governed-egress" / "receipts.jsonl")
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            gov = _STATE["governor"] = ComputeGovernorSpine(receipts=GovernorReceiptLog(Path(path)), enforce=True)
        return gov


def _split(url: Any) -> tuple[str, str]:
    p = urllib.parse.urlsplit(str(url))
    return p.netloc or "", p.path or str(url)


class _Gate:
    __slots__ = ("caller", "host", "path", "headers", "receipt", "started", "admitted")

    def __init__(self, caller: str, url: Any):
        self.caller, (self.host, self.path) = caller, _split(url)
        self.headers: Dict[str, str] = {}
        self.receipt = ""
        self.started = time.perf_counter()
        self.admitted = True


def _admit(caller: str, url: Any) -> _Gate:
    gate = _Gate(caller, url)
    if not enabled():
        return gate
    from app.kernel.governance.governor_spine import Episode, Proposal

    gov = _governor()
    proposal = Proposal(kind="cloud", provider=f"egress:{gate.host}", tool_id=f"egress:{caller}",
                        quality_cascade={"skipped": "egress-shim:caller-verifies"}, estimate={"tokens_total": 0.0},
                        signature_material={"caller": caller, "host": gate.host, "path": gate.path, "t": time.time_ns()})
    decision = gov.admit(Episode(run_id=f"egress:{caller}"), proposal)
    gate.receipt = str(getattr(decision, "receipt_hash", "") or getattr(decision, "receipt_id", "")).split(":", 1)[-1]
    gate.admitted = bool(decision.permits())
    if not gate.admitted:
        gov.receipts._append({"type": "model_egress", "caller": caller, "host": gate.host, "path": gate.path,
                              "status": "refused_governor", "reasons": list(getattr(decision, "reasons", ()))})
        if str(os.environ.get("BEAST_GOVERNED_EGRESS_ENFORCE", "")).lower() in _ON:
            raise EgressRefused(f"governor refused egress for {caller}: {','.join(decision.reasons)}")
    gate.headers = {"X-BEAST-Admit": gate.receipt[:32], "X-BEAST-Caller": caller}
    if str(os.environ.get("BEAST_ARDA_EGRESS_ADMIT", "")).lower() in _ON and gate.admitted:
        ADMIT_QUEUE.parent.mkdir(parents=True, exist_ok=True)
        with ADMIT_QUEUE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "host": gate.host, "receipt_prefix": gate.receipt[:16],
                                 "ttl_ms": 30000, "caller": caller, "at": time.time()}) + "\n")
    return gate


def _usage(body: Any) -> Dict[str, int]:
    if not isinstance(body, dict):
        return {}
    u = body.get("usage") or {}
    out = {k: int(u[k]) for k in ("prompt_tokens", "completion_tokens", "total_tokens") if isinstance(u.get(k), int)}
    for k in ("prompt_eval_count", "eval_count"):  # Ollama
        if isinstance(body.get(k), int):
            out[k] = int(body[k])
    return out


def _record(gate: _Gate, status: Any, *, error: str = "", body: Any = None) -> None:
    if not enabled():
        return
    try:
        _governor().receipts._append({"type": "model_egress", "caller": gate.caller, "host": gate.host, "path": gate.path,
                                      "status": status, "latency_ms": round((time.perf_counter() - gate.started) * 1000, 1),
                                      "admit": gate.receipt[:16], "error": error[:120], "usage": _usage(body)})
    except Exception:  # noqa: BLE001 - receipts must never break the call
        pass


def _merge(kw: Dict[str, Any], gate: _Gate) -> Dict[str, Any]:
    if gate.headers:
        kw = dict(kw)
        kw["headers"] = {**dict(kw.get("headers") or {}), **gate.headers}
    return kw


def _json_or_none(resp: Any) -> Any:
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return None


def post(client: Any, caller: str, url: Any, **kw: Any) -> Any:
    """Sync ``client.post(url, **kw)`` (httpx.Client, requests.Session or the ``httpx``/``requests`` module)."""
    gate = _admit(caller, url)
    try:
        resp = client.post(url, **_merge(kw, gate))
    except Exception as exc:
        _record(gate, "transport_error", error=type(exc).__name__)
        raise
    _record(gate, getattr(resp, "status_code", None), body=_json_or_none(resp) if enabled() else None)
    return resp


async def apost(client: Any, caller: str, url: Any, **kw: Any) -> Any:
    gate = _admit(caller, url)
    try:
        resp = await client.post(url, **_merge(kw, gate))
    except Exception as exc:
        _record(gate, "transport_error", error=type(exc).__name__)
        raise
    _record(gate, getattr(resp, "status_code", None), body=_json_or_none(resp) if enabled() else None)
    return resp


@contextlib.asynccontextmanager
async def astream(client: Any, caller: str, method: str, url: Any, **kw: Any):
    gate = _admit(caller, url)
    try:
        async with client.stream(method, url, **_merge(kw, gate)) as resp:
            yield resp
    except Exception as exc:
        _record(gate, "transport_error", error=type(exc).__name__)
        raise
    else:
        _record(gate, getattr(resp, "status_code", None))


def urlopen(caller: str, request: Any, timeout: Optional[float] = None, **kw: Any) -> Any:
    """``urllib.request.urlopen`` with the admit headers added to a Request object (strings pass through)."""
    import urllib.request

    url = request.full_url if hasattr(request, "full_url") else request
    gate = _admit(caller, url)
    if gate.headers and hasattr(request, "add_header"):
        for k, v in gate.headers.items():
            request.add_header(k, v)
    try:
        resp = urllib.request.urlopen(request, timeout=timeout, **kw) if timeout is not None else urllib.request.urlopen(request, **kw)
    except Exception as exc:
        _record(gate, "transport_error", error=type(exc).__name__)
        raise
    _record(gate, getattr(resp, "status", None))
    return resp


__all__ = ["EgressRefused", "apost", "astream", "enabled", "post", "urlopen"]
