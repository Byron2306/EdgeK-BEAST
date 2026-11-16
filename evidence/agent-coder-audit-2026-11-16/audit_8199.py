#!/usr/bin/env python3
"""One real Agent Coder run on 127.0.0.1:8199 plus inventory probes.

Uses TGI only (local, $0). Auto-approves the investigation card so the
run can reach PREC / economizer / provider stream. Does not touch :8101.
Never prints secrets.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8199"
WS = "/tmp/beast-audit-ws-20261116"
TGI_MODEL = "Qwen/Qwen2.5-Coder-3B-Instruct-AWQ"
OUT = Path("/home/byron/GitHub/EdgeK-BEAST/evidence/agent-coder-audit-2026-11-16")
CAP_USD = 0.03
spend = 0.0

OUT.mkdir(parents=True, exist_ok=True)


def call(method, path, body=None, query=None, timeout=30, base=BASE):
    url = base + path
    if query:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode() or "null") if raw else None
            return resp.status, payload, time.time() - t0, None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode() or "null")
        except Exception:
            payload = {"raw": raw.decode(errors="replace")[:400]}
        return exc.code, payload, time.time() - t0, str(exc)
    except Exception as exc:
        return None, None, time.time() - t0, f"{type(exc).__name__}: {exc}"


def shrink(o, depth=0):
    if depth > 5:
        return type(o).__name__
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            lk = k.lower()
            if any(s in lk for s in ("api_key", "apikey", "secret", "password", "authorization", "pem")) or (
                lk.endswith("token") and "max" not in lk and "prompt" not in lk and "completion" not in lk
            ):
                out[k] = "<redacted>"
            else:
                out[k] = shrink(v, depth + 1)
        return out
    if isinstance(o, list):
        return [shrink(x, depth + 1) for x in o[:30]] + ([f"...{len(o)}"] if len(o) > 30 else [])
    if isinstance(o, str) and len(o) > 400:
        return o[:400] + "..."
    return o


probes = {}

# --- inventory / backend probes (no paid inference) ---
for name, method, path, body, query in [
    ("health", "GET", "/health", None, None),
    ("proxy_health", "GET", "/proxy/health", None, None),
    ("mcp_health", "GET", "/mcp/health", None, None),
    ("mcp_tools", "GET", "/mcp/tools/list", None, None),
    ("model_inventory", "GET", "/edgek/ide/model-inventory", None, None),
    ("model_route_auto_rename", "POST", "/edgek/ide/model-route",
     {"id": "auto", "provider": "beast", "model": "auto", "family": "rename"}, None),
    ("crystal_reuse", "GET", "/edgek/crystal-reuse", None, None),
    ("crystal_lattice", "GET", "/edgek/crystal-lattice", None, None),
    ("crystal_chain", "GET", "/edgek/crystal-chain", None, {"include_blocks": "true", "limit": "8"}),
    ("commons_economy", "GET", "/edgek/commons-economy", None, None),
    ("memory_security", "GET", "/edgek/memory-security", None, {"verify": "true"}),
    ("ide_snapshot", "GET", "/edgek/ide/snapshot", None, {"root_path": WS}),
    ("system_snapshot", "GET", "/edgek/ide/system-snapshot", None, {"root_path": WS}),
    ("tooling_snapshot", "GET", "/edgek/ide/tooling-snapshot", None, {"root_path": WS}),
    ("chronicle", "GET", "/edgek/chronicle", None, {"limit": "10"}),
]:
    status, payload, elapsed, err = call(method, path, body=body, query=query, timeout=25)
    compact = shrink(payload) if isinstance(payload, dict) else payload
    # keep small
    if name == "mcp_tools" and isinstance(payload, dict):
        tools = [(t.get("name") if isinstance(t, dict) else str(t)) for t in (payload.get("tools") or [])]
        compact = {"count": len(tools), "has_symbol_surgeon": "beast_symbol_surgeon_plan" in tools}
    if name == "model_inventory" and isinstance(payload, dict):
        present = payload.get("providers_present") or []
        blocked = payload.get("blocked_providers") or []
        compact = {
            "count": payload.get("count"),
            "providers_present": present,
            "blocked_providers": blocked,
            "live": {k: {"up": (v or {}).get("up") if isinstance(v, dict) else None} for k, v in (payload.get("live") or {}).items()},
        }
    if name == "proxy_health" and isinstance(payload, dict):
        providers = payload.get("providers") or []
        names = []
        for p in providers:
            if isinstance(p, dict):
                names.append(str(p.get("name") or p.get("id") or p.get("provider") or ""))
            else:
                names.append(str(p))
        compact = {"status": payload.get("status"), "providers": names}
    probes[name] = {"status": status, "elapsed": round(elapsed, 3), "error": err, "payload": compact}
    print(f"PROBE {name}: status={status} err={err}", flush=True)

# socket guardian 8131 (live sidecar — probe only)
st, payload, elapsed, err = call("GET", "/health", timeout=3, base="http://127.0.0.1:8131")
if st is None:
    # try other common paths
    for path in ("/", "/status", "/v1/health"):
        st, payload, elapsed, err = call("GET", path, timeout=2, base="http://127.0.0.1:8131")
        if st is not None:
            break
probes["socket_guardian_8131"] = {"status": st, "elapsed": round(elapsed, 3), "error": err, "payload": shrink(payload) if isinstance(payload, dict) else (str(payload)[:200] if payload else None)}
print(f"PROBE socket_guardian_8131: status={st} err={err}", flush=True)

# live MCP 8765
rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
st, payload, elapsed, err = call("POST", "", body=rpc, timeout=15, base="http://127.0.0.1:8765/mcp")
n = 0
if isinstance(payload, dict):
    result = payload.get("result") or payload
    n = len(result.get("tools") or [])
probes["mcp_live_8765"] = {"status": st, "error": err, "count": n}
print(f"PROBE mcp_live_8765: status={st} count={n}", flush=True)

# --- Agent Coder run (TGI, $0) ---
prompt = (
    "Add a decrement(value, step=1) function to src/counters.py that subtracts step from value and returns it. "
    "Do not change increment or total. Use a minimal line-anchored edit, not a whole-file rewrite."
)
status, payload, elapsed, err = call(
    "POST",
    "/edgek/ide/agent-sessions/create",
    body={
        "root_path": WS,
        "objective": prompt,
        "mode": "implementer",
        "files": ["src/counters.py"],
        "provider": "tgi",
        "model": TGI_MODEL,
        "execution_target": "local",
        "budget": {"tokens": 4000, "seconds": 180, "cost_usd": 0},
    },
    timeout=30,
)
session = ((payload or {}).get("session") or payload or {}) if isinstance(payload, dict) else {}
session_id = str(session.get("session_id") or "")
print(f"SESSION {session_id or 'NONE'} status={status} err={err}", flush=True)

run_id = ""
events_log = []
if session_id:
    status, payload, elapsed, err = call(
        "POST",
        "/edgek/agent-runs",
        body={
            "root_path": WS,
            "session_id": session_id,
            "mode": "implementer",
            "provider": "tgi",
            "model": TGI_MODEL,
            "launch": True,
            "budget": {"tokens": 4000, "seconds": 180, "cost_usd": 0},
            "request": {
                "prompt": prompt,
                "workspace_root": WS,
                "execution_target": "local",
                "context_files": ["src/counters.py"],
                "provider": "tgi",
                "model": TGI_MODEL,
                "max_tokens": 16384,
                "max_turns": 2,
                "launch_strategy": "typed_planner",
                "transport": "durable_agent_run_v2",
            },
        },
        timeout=45,
    )
    run = (payload or {}).get("run") or {}
    run_id = str(run.get("run_id") or "")
    print(f"RUN {run_id or 'NONE'} status={status} state={run.get('state')} err={err}", flush=True)


def list_approvals(rid):
    st, body, _, e = call("GET", f"/edgek/agent-runs/{rid}/approvals", query={"root_path": WS}, timeout=15)
    items = []
    if isinstance(body, dict):
        items = body.get("approvals") or body.get("items") or body.get("pending") or []
        if not items and isinstance(body.get("approval"), dict):
            items = [body["approval"]]
    elif isinstance(body, list):
        items = body
    return st, items, e


def approve(rid, approval_id):
    return call(
        "POST",
        f"/edgek/agent-runs/{rid}/approvals/{approval_id}",
        body={"approved": True, "root_path": WS, "scope": "once"},
        timeout=20,
    )


# Consume SSE while polling the run and approving as needed
def consume_and_drive(rid, timeout=150):
    url = f"{BASE}/edgek/agent-runs/{urllib.parse.quote(rid)}/events?root_path={urllib.parse.quote(WS)}"
    req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    deadline = time.time() + timeout
    approved = set()
    got = []
    last_poll = 0
    try:
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            buf = ""
            event_type = "message"
            while time.time() < deadline and len(got) < 200:
                # periodic approval + state poll
                if time.time() - last_poll > 2:
                    last_poll = time.time()
                    st, items, e = list_approvals(rid)
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        aid = str(item.get("approval_id") or item.get("id") or "")
                        status_a = str(item.get("status") or "")
                        if aid and aid not in approved and status_a.lower() in {"", "pending", "requested", "open", "waiting"}:
                            ast, apayload, _, aerr = approve(rid, aid)
                            approved.add(aid)
                            print(f"APPROVE {aid} -> {ast} {aerr}", flush=True)
                            got.append({"event": "audit.approval", "data": {"approval_id": aid, "http": ast}})
                    st, body, _, _ = call("GET", f"/edgek/agent-runs/{rid}", query={"root_path": WS, "auto_recover": "true"}, timeout=15)
                    state = ""
                    if isinstance(body, dict):
                        state = str(((body.get("run") or body).get("state") if isinstance(body.get("run") or body, dict) else "") or "")
                    if state in {"completed", "failed", "cancelled"}:
                        # read remaining briefly
                        pass
                # non-blocking-ish read
                try:
                    chunk = resp.read(256)
                except Exception:
                    break
                if not chunk:
                    if state in {"completed", "failed", "cancelled"}:
                        break
                    time.sleep(0.2)
                    continue
                buf += chunk.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.rstrip("\r")
                    if line.startswith("event:"):
                        event_type = line[6:].strip() or "message"
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        parsed = data
                        try:
                            parsed = json.loads(data)
                        except Exception:
                            pass
                        got.append({"event": event_type, "data": parsed})
                        event_type = "message"
                    elif line == "":
                        event_type = "message"
    except Exception as exc:
        got.append({"event": "audit.sse_error", "data": f"{type(exc).__name__}: {exc}"})
    return got, sorted(approved)


state = ""
if run_id:
    events_log, approved_ids = consume_and_drive(run_id, timeout=150)
    st, body, _, err = call("GET", f"/edgek/agent-runs/{run_id}", query={"root_path": WS, "auto_recover": "true"}, timeout=20)
    run = (body or {}).get("run") or body or {}
    state = str(run.get("state") or "")
    print(f"TERMINAL state={state} events={len(events_log)} approved={approved_ids}", flush=True)
else:
    approved_ids = []

# flatten event texts for the table
texts = []
for ev in events_log:
    d = ev.get("data")
    if isinstance(d, dict):
        texts.append(str(d.get("text") or d.get("error") or d.get("type") or ev.get("event") or ""))
        # include nested useful keys
        for k in ("phase", "tool", "message", "reason", "action"):
            if d.get(k):
                texts.append(str(d.get(k)))
    else:
        texts.append(str(d)[:240])
blob = "\n".join(texts)

# 8101 still up?
st, payload, _, err = call("GET", "/health", timeout=5, base="http://127.0.0.1:8101")
probes["live_8101"] = {"status": st, "payload": shrink(payload) if isinstance(payload, dict) else None, "error": err}

summary = {
    "gateway": BASE,
    "workspace": WS,
    "tgi_model": TGI_MODEL,
    "spend_usd": spend,
    "cap_usd": CAP_USD,
    "session_id": session_id,
    "run_id": run_id,
    "state": state,
    "approved_ids": approved_ids,
    "event_count": len(events_log),
    "event_texts": texts[:120],
    "probes": probes,
}
OUT.joinpath("mission-8199.json").write_text(json.dumps(summary, indent=2, default=str))
OUT.joinpath("events-8199.json").write_text(json.dumps(events_log, indent=2, default=str)[:400000])
print(f"WROTE {OUT/'mission-8199.json'} state={state} events={len(events_log)} spend={spend}", flush=True)
for t in texts:
    if t.strip():
        print("EVT", t[:200], flush=True)
