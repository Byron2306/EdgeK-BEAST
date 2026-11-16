"""Full-stack ``beast heal``: discover BEAST servers, stop them, restart gateway + MCP.

Default heal finds BEAST-owned servers for this uid (uvicorn ``app.main:app`` on :8101,
socket-guardian / ``bin/beast gateway --socket-mode guardian`` on :8131, ``bin/beast mcp-http``
on :8765, and stale ``*.pid`` files), then SIGTERM → grace → SIGKILL via ``ProcessLifecycle``
(pidfd) unless a systemd --user unit is installed, in which case ``systemctl --user restart``
is preferred.  Gateway is relaunched with ``deploy/closure-2026-11-16/beast-gateway.env`` and
logs under ``.beast/``.  Health requires ``/proxy/health`` to list ``fireworks`` and MCP
``tools/list`` to return 69 tools.

Hooks are injectable so tests can exercise selection and planning without signalling a process.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from app.kernel.execution import heal_guard as guard

GATEWAY_ENV_REL = Path("deploy") / "closure-2026-11-16" / "beast-gateway.env"
GATEWAY_UNIT = "beast-gateway.service"
LAB_UNITS = (
    "beast-socket-guardian-beast.socket",
    "beast-socket-guardian.service",
    "beast-beast-guardian-consumer.service",
)
MCP_UNITS = ("beast-mcp-http.service",)
MANAGED_PORTS = {"gateway": 8101, "mcp_http": 8765, "lab_8131": 8131}
EXPECTED_MCP_TOOLS = 69
GRACE_SECONDS = 8.0
REQUIRED_GATEWAY_FLAGS = (
    "BEAST_GOVERNED_INTERCEPTION",
    "BEAST_CAPABILITY_ROUTER",
    "BEAST_PROCESS_LIFECYCLE",
    "BEAST_GPU_SCHEDULER",
)
SECRET_KEY_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTHORIZATION")


# -- classification --------------------------------------------------------------------------------

def is_beast_owned_server(facts: Mapping[str, Any], *, listening_ports: Optional[Iterable[int]] = None) -> tuple[bool, str]:
    """Return (True, role) when this uid's process is a BEAST server heal may restart."""
    protected, _reason = guard.pid_protection(int(facts.get("pid") or 0) or 2, facts=dict(facts), mode="full")
    if protected:
        return False, ""
    cmd = " ".join(str(facts.get(k) or "") for k in ("comm", "cmdline")).lower()
    cg = str(facts.get("cgroup") or "").lower()
    if "litellm" in cmd or "electron" in cmd or "desktop-ide" in cmd:
        return False, ""
    if "uvicorn" in cmd and "app.main:app" in cmd:
        return True, "gateway"
    if "mcp-http" in cmd:
        return True, "mcp_http"
    if "socket-mode" in cmd and "guardian" in cmd and "gateway" in cmd:
        return True, "gateway_guardian"
    if "socket_guardian_daemon" in cmd or "socket-guardian" in cmd and "daemon" in cmd:
        return True, "socket_guardian"
    if "bin/beast" in cmd and "gateway" in cmd:
        return True, "gateway"
    if "beast-beast-guardian-consumer" in cg:
        return True, "gateway_guardian"
    if "beast-socket-guardian" in cg:
        return True, "socket_guardian"
    ports = set(int(p) for p in (listening_ports or []))
    # Unknown listener on a managed port is not auto-selected (fail closed on identity).
    _ = ports
    return False, ""


def iter_process_facts() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                out.append(guard.process_facts(int(entry)))
    except OSError:
        pass
    return out


def default_listeners(port: int) -> List[int]:
    pids: set[int] = set()
    commands = [
        ["ss", "-ltnp", f"sport = :{int(port)}"],
        ["lsof", f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-P", "-n", "-t"],
    ]
    for command in commands:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=4, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (completed.stdout or "") + "\n" + (completed.stderr or "")
        if command[0] == "lsof":
            for line in text.splitlines():
                try:
                    pids.add(int(line.strip()))
                except ValueError:
                    pass
            continue
        import re
        for pattern in (r"pid=(\d+)", r",pid=(\d+),"):
            for match in re.findall(pattern, text):
                try:
                    pids.add(int(match))
                except ValueError:
                    pass
    return sorted(pid for pid in pids if pid > 1 and pid != os.getpid())


def discover_pidfiles(root: Path) -> List[Path]:
    found: List[Path] = []
    run_dir = root / "deploy" / "run"
    if run_dir.is_dir():
        found.extend(sorted(run_dir.glob("*.pid")))
    beast_dir = root / ".beast"
    if beast_dir.is_dir():
        for path in beast_dir.rglob("*.pid"):
            parts = set(path.parts)
            if "worktrees" in parts or "node_modules" in parts or ".beast-python-tools" in parts:
                continue
            found.append(path)
    return found


def read_pidfile(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def parse_env_file(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        if key:
            out[key] = value
    return out


def redacted_env_keys(env: Mapping[str, str]) -> List[str]:
    """Names only; never return values (the env file may later gain secrets)."""
    return [k for k in env if not any(m in k.upper() for m in SECRET_KEY_MARKERS)]


def user_unit_installed(unit: str, *, home: Optional[Path] = None,
                        probe: Optional[Callable[[str], bool]] = None) -> bool:
    if probe is not None:
        return bool(probe(unit))
    path = (home or Path.home()) / ".config" / "systemd" / "user" / unit
    if path.is_file():
        return True
    try:
        result = subprocess.run(
            ["systemctl", "--user", "list-unit-files", unit, "--no-legend", "--no-pager"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return unit in (result.stdout or "")


def user_unit_main_pid(unit: str, *, probe: Optional[Callable[[str], Optional[int]]] = None) -> Optional[int]:
    if probe is not None:
        return probe(unit)
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        pid = int((result.stdout or "").strip() or "0")
    except ValueError:
        return None
    return pid if pid > 1 else None


# -- discovery -------------------------------------------------------------------------------------

def discover_targets(
    *,
    root: Path,
    host: str = "127.0.0.1",
    gateway_port: int = 8101,
    mcp_port: int = 8765,
    lab_port: int = 8131,
    processes: Optional[Sequence[Mapping[str, Any]]] = None,
    listeners: Optional[Callable[[int], Sequence[int]]] = None,
    facts_for: Optional[Callable[[int], Dict[str, Any]]] = None,
    pidfiles: Optional[Sequence[Path]] = None,
    unit_installed: Optional[Callable[[str], bool]] = None,
    unit_main_pid: Optional[Callable[[str], Optional[int]]] = None,
) -> Dict[str, Any]:
    """Build the kill / restart / report plan from injectable process, port, pidfile and unit sources."""
    facts_for = facts_for or guard.process_facts
    listeners = listeners or default_listeners
    processes = list(processes) if processes is not None else iter_process_facts()
    by_pid: Dict[int, Dict[str, Any]] = {}
    for item in processes:
        try:
            by_pid[int(item["pid"])] = dict(item)
        except (KeyError, TypeError, ValueError):
            continue

    def facts(pid: int) -> Dict[str, Any]:
        if pid in by_pid:
            return by_pid[pid]
        got = facts_for(pid)
        by_pid[pid] = got
        return got

    port_map = {
        "gateway": int(gateway_port),
        "mcp_http": int(mcp_port),
        "lab_8131": int(lab_port),
        "litellm": guard.LITELLM_PORT,
    }
    listeners_by_port: Dict[int, List[int]] = {p: list(listeners(p)) for p in set(port_map.values())}

    selected: Dict[int, Dict[str, Any]] = {}
    reported: List[Dict[str, Any]] = []
    reported_keys: set[tuple] = set()
    unknown: List[Dict[str, Any]] = []

    def _relevant(f: Mapping[str, Any]) -> bool:
        text = " ".join(str(f.get(k) or "") for k in ("comm", "cmdline", "cgroup")).lower()
        markers = ("arda", "seraph", "ollama", "litellm", "beast", "uvicorn", "mcp-http",
                   "tgi", "guardian", "app.main:app")
        return any(m in text for m in markers)

    def consider(pid: int, *, port: Optional[int] = None, source: str) -> None:
        if pid <= 1 or pid == os.getpid() or pid in selected:
            return
        f = facts(pid)
        listening = [p for p, pids in listeners_by_port.items() if pid in pids]
        if port is not None and port not in listening:
            listening.append(int(port))
        protected, reason = guard.pid_protection(pid, port=port, facts=f, mode="full")
        if protected:
            key = (pid, reason)
            if key not in reported_keys:
                reported_keys.add(key)
                reported.append({"pid": pid, "reason": reason, "source": source, "cmdline": f.get("cmdline", ""),
                                 "comm": f.get("comm", ""), "ports": listening})
            return
        ok, role = is_beast_owned_server(f, listening_ports=listening)
        if ok:
            selected[pid] = {"pid": pid, "role": role, "source": source, "cmdline": f.get("cmdline", ""),
                             "comm": f.get("comm", ""), "cgroup": f.get("cgroup", ""), "ports": listening,
                             "uid": f.get("uid")}
            return
        if port in {int(gateway_port), int(mcp_port), int(lab_port)}:
            unknown.append({"pid": pid, "reason": "unknown_listener", "source": source,
                            "cmdline": f.get("cmdline", ""), "ports": listening})

    listener_pids = {pid for pids in listeners_by_port.values() for pid in pids}
    for item in processes:
        try:
            pid = int(item["pid"])
        except (KeyError, TypeError, ValueError):
            continue
        if pid not in listener_pids and not _relevant(item):
            continue
        consider(pid, source="proc")
    for role, port in port_map.items():
        for pid in listeners_by_port.get(port, []):
            consider(pid, port=port, source=f"port:{port}")

    stale_pidfiles: List[Dict[str, Any]] = []
    kept_pidfiles: List[Dict[str, Any]] = []
    for path in list(pidfiles) if pidfiles is not None else discover_pidfiles(root):
        pid = read_pidfile(path)
        record = {"path": str(path), "pid": pid}
        if pid is None:
            stale_pidfiles.append({**record, "reason": "unreadable"})
            continue
        f = facts(pid)
        alive = bool(f.get("cmdline") or f.get("comm") or f.get("uid") is not None)
        # process_facts on a dead pid still returns uid=None and empty strings
        if not alive and not Path(f"/proc/{pid}").exists() and pid not in by_pid:
            stale_pidfiles.append({**record, "reason": "dead"})
            continue
        # When tests inject facts, treat empty+missing uid as dead.
        if f.get("uid") is None and not f.get("cmdline") and not f.get("comm") and pid not in selected:
            # Could be a live process the injector didn't describe; check /proc if present.
            if not Path(f"/proc/{pid}").exists():
                stale_pidfiles.append({**record, "reason": "dead"})
                continue
        protected, reason = guard.pid_protection(pid, facts=f, mode="full")
        if protected:
            kept_pidfiles.append({**record, "reason": reason})
            reported.append({"pid": pid, "reason": reason, "source": f"pidfile:{path}", "cmdline": f.get("cmdline", ""),
                             "comm": f.get("comm", ""), "ports": []})
            continue
        ok, role = is_beast_owned_server(f)
        if ok:
            consider(pid, source=f"pidfile:{path}")
            kept_pidfiles.append({**record, "reason": f"live:{role}"})
        elif Path(f"/proc/{pid}").exists() and (f.get("cmdline") or f.get("comm")):
            # Live but not a BEAST server — leave the process, drop a stale label if the name no longer matches.
            stale_pidfiles.append({**record, "reason": "mismatched_process", "cmdline": f.get("cmdline", "")})
        elif pid in by_pid and (f.get("cmdline") or f.get("comm") or f.get("uid") is not None):
            ok2, role2 = is_beast_owned_server(f)
            if ok2:
                consider(pid, source=f"pidfile:{path}")
                kept_pidfiles.append({**record, "reason": f"live:{role2}"})
            else:
                stale_pidfiles.append({**record, "reason": "mismatched_process", "cmdline": f.get("cmdline", "")})
        else:
            stale_pidfiles.append({**record, "reason": "dead"})

    installed = unit_installed or (lambda u: user_unit_installed(u))
    main_pid = unit_main_pid or (lambda u: user_unit_main_pid(u))
    units = {
        "gateway": GATEWAY_UNIT if installed(GATEWAY_UNIT) else None,
        "mcp_http": next((u for u in MCP_UNITS if installed(u)), None),
        "lab_8131": list(LAB_UNITS) if all(installed(u) for u in LAB_UNITS) or any(installed(u) for u in LAB_UNITS) else [],
    }
    # If any lab unit is installed, prefer systemd for the whole 8131 group (installed members only).
    units["lab_8131"] = [u for u in LAB_UNITS if installed(u)]
    for unit in units["lab_8131"]:
        pid = main_pid(unit)
        if pid:
            consider(pid, port=lab_port, source=f"unit:{unit}")
            if pid in selected:
                selected[pid]["unit"] = unit

    for rec in selected.values():
        role = rec["role"]
        if role in {"socket_guardian", "gateway_guardian"} and units["lab_8131"]:
            rec["restart_via"] = "systemd"
            rec["units"] = list(units["lab_8131"])
        elif role == "gateway" and units["gateway"]:
            rec["restart_via"] = "systemd"
            rec["units"] = [units["gateway"]]
        elif role == "mcp_http" and units["mcp_http"]:
            rec["restart_via"] = "systemd"
            rec["units"] = [units["mcp_http"]]
        else:
            rec["restart_via"] = "nohup"
            rec["units"] = []

    return {
        "selected": sorted(selected.values(), key=lambda r: (r["role"], r["pid"])),
        "reported": reported,
        "unknown": unknown,
        "stale_pidfiles": stale_pidfiles,
        "kept_pidfiles": kept_pidfiles,
        "units": units,
        "listeners_by_port": listeners_by_port,
        "host": host,
        "ports": {"gateway": int(gateway_port), "mcp_http": int(mcp_port), "lab_8131": int(lab_port)},
    }


# -- health ----------------------------------------------------------------------------------------

def _http_json(url: str, *, payload: Optional[Dict[str, Any]] = None, timeout: float = 3.0) -> Dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - loopback health
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def proxy_health(host: str, port: int, *, getter: Optional[Callable[[str], Dict[str, Any]]] = None) -> Dict[str, Any]:
    url = f"http://{host}:{int(port)}/proxy/health"
    try:
        body = getter(url) if getter is not None else _http_json(url)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "url": url, "fireworks": False, "providers": [], "error": str(exc)}
    providers = body.get("providers") if isinstance(body, dict) else []
    names = [str(p).lower() for p in (providers or [])]
    has = "fireworks" in names
    return {"ok": bool(has and (not isinstance(body, dict) or body.get("status") in {None, "healthy", "ok", "up"} or has)),
            "url": url, "fireworks": has, "providers": list(providers or []),
            "base_url": body.get("base_url") if isinstance(body, dict) else None,
            "status": body.get("status") if isinstance(body, dict) else None}


def mcp_tools_health(host: str, port: int, *, expected: int = EXPECTED_MCP_TOOLS,
                     poster: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None) -> Dict[str, Any]:
    url = f"http://{host}:{int(port)}/mcp"
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    try:
        body = poster(url, payload) if poster is not None else _http_json(url, payload=payload, timeout=5.0)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "url": url, "count": 0, "expected": expected, "error": str(exc)}
    tools = None
    if isinstance(body, dict):
        result = body.get("result")
        if isinstance(result, dict):
            tools = result.get("tools")
        elif "tools" in body:
            tools = body["tools"]
    count = len(tools) if isinstance(tools, list) else 0
    return {"ok": count == expected, "url": url, "count": count, "expected": expected}


# -- execution -------------------------------------------------------------------------------------

def _terminate_via_lifecycle(pid: int, *, label: str, grace_s: float, lifecycle: Any,
                             measure_vram: bool = False) -> Dict[str, Any]:
    handle = lifecycle.adopt(pid, label=label)
    return lifecycle.terminate(handle, reason="operator_request", grace_s=grace_s, measure_vram=measure_vram)


def _ports_free(ports: Iterable[int], listeners: Callable[[int], Sequence[int]], timeout: float = 8.0,
                sleeper: Callable[[float], None] = time.sleep) -> Dict[int, List[int]]:
    deadline = time.monotonic() + timeout
    remaining = {int(p): list(listeners(int(p))) for p in ports}
    while time.monotonic() < deadline and any(remaining.values()):
        sleeper(0.2)
        remaining = {int(p): list(listeners(int(p))) for p in ports}
    return remaining


def load_gateway_env(root: Path, base: Optional[Mapping[str, str]] = None) -> Dict[str, str]:
    env = dict(base if base is not None else os.environ)
    parsed = parse_env_file(root / GATEWAY_ENV_REL)
    env.update(parsed)
    return env


def format_summary_table(payload: Mapping[str, Any]) -> str:
    mode = payload.get("mode", "full_restart")
    status = payload.get("status", "")
    dry = payload.get("status") == "dry_run" or payload.get("dry_run")
    verb_kill = "would kill" if dry else "killed"
    verb_restart = "would restart" if dry else "restarted"
    verb_clear = "would clear" if dry else "cleared"
    lines = [
        f"BEAST heal  mode={mode}  status={status}",
        "",
        f"{verb_kill.capitalize()} PIDs",
        f"{'PID':<10} {'ROLE':<20} {'VIA':<10} COMMAND",
    ]
    kills = payload.get("killed") or payload.get("would_kill") or []
    if not kills:
        lines.append("(none)")
    for rec in kills:
        cmd = str(rec.get("cmdline") or "")
        if len(cmd) > 80:
            cmd = cmd[:77] + "..."
        lines.append(f"{rec.get('pid', ''):<10} {rec.get('role', ''):<20} {rec.get('restart_via', ''):<10} {cmd}")
    lines += ["", f"{verb_restart.capitalize()} services", f"{'SERVICE':<20} {'METHOD':<10} DETAIL"]
    restarts = payload.get("restarts") or []
    if not restarts:
        lines.append("(none)")
    for rec in restarts:
        detail = rec.get("detail") or rec.get("command") or " ".join(rec.get("units") or [])
        lines.append(f"{rec.get('service', ''):<20} {rec.get('method', ''):<10} {detail}")
    lines += ["", f"{verb_clear.capitalize()} stale pidfiles"]
    stale = payload.get("stale_pidfiles") or []
    if not stale:
        lines.append("(none)")
    for rec in stale:
        lines.append(f"  {rec.get('path')}  pid={rec.get('pid')}  ({rec.get('reason')})")
    lines += ["", "Reported (not touched)"]
    reported = payload.get("reported") or []
    unknown = payload.get("unknown") or []
    seen = set()
    unique = []
    for rec in reported:
        key = (rec.get("pid"), rec.get("reason"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(rec)
    reported = unique
    if not reported and not unknown:
        lines.append("(none)")
    for rec in reported:
        cmd = str(rec.get("cmdline") or rec.get("comm") or "")
        if len(cmd) > 70:
            cmd = cmd[:67] + "..."
        lines.append(f"  pid={rec.get('pid')}  {rec.get('reason')}  {cmd}")
    for rec in unknown:
        lines.append(f"  pid={rec.get('pid')}  unknown listener  {rec.get('cmdline', '')[:70]}")
    health = payload.get("health") or {}
    before = health.get("before") or {}
    after = health.get("after") or {}
    lines += ["", "Health"]
    for label, block in (("before", before), ("after", after)):
        if not block:
            continue
        proxy = block.get("proxy") or {}
        mcp = block.get("mcp") or {}
        fw = "yes" if proxy.get("fireworks") else "no"
        lines.append(
            f"  {label}: /proxy/health fireworks={fw}  "
            f"MCP tools/list {mcp.get('count', '?')}/{mcp.get('expected', EXPECTED_MCP_TOOLS)}  "
            f"ok={bool(proxy.get('ok') and mcp.get('ok'))}"
        )
    ops = payload.get("operator_commands") or []
    if ops:
        lines += ["", "Operator commands"]
        for cmd in ops:
            lines.append(f"  {cmd}")
    return "\n".join(lines) + "\n"


def _restart_specs(discovery: Mapping[str, Any], *, root: Path, python: str, beast_bin: Path) -> List[Dict[str, Any]]:
    host = discovery["host"]
    ports = discovery["ports"]
    units = discovery["units"]
    env_file = root / GATEWAY_ENV_REL
    specs = [
        {
            "service": "gateway",
            "method": "systemd" if units.get("gateway") else "nohup",
            "units": [units["gateway"]] if units.get("gateway") else [],
            "command": [python, "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(ports["gateway"])],
            "log_file": str(root / ".beast" / f"gateway-{ports['gateway']}.log"),
            "pid_file": str(root / "deploy" / "run" / "gateway.pid"),
            "env_file": str(env_file),
            "port": ports["gateway"],
            "detail": (
                f"systemctl --user restart {units['gateway']}"
                if units.get("gateway")
                else f"{python} -m uvicorn app.main:app --host {host} --port {ports['gateway']}  (env: {GATEWAY_ENV_REL}, log: .beast/gateway-{ports['gateway']}.log)"
            ),
        },
        {
            "service": "mcp_http",
            "method": "systemd" if units.get("mcp_http") else "nohup",
            "units": [units["mcp_http"]] if units.get("mcp_http") else [],
            "command": [python, str(beast_bin), "mcp-http", "--host", host, "--port", str(ports["mcp_http"])],
            "log_file": str(root / ".beast" / f"mcp-http-{ports['mcp_http']}.log"),
            "pid_file": str(root / "deploy" / "run" / "mcp-http.pid"),
            "env_file": None,
            "port": ports["mcp_http"],
            "detail": (
                f"systemctl --user restart {units['mcp_http']}"
                if units.get("mcp_http")
                else f"{python} {beast_bin} mcp-http --host {host} --port {ports['mcp_http']}  (log: .beast/mcp-http-{ports['mcp_http']}.log)"
            ),
        },
    ]
    lab_units = units.get("lab_8131") or []
    if lab_units:
        specs.append({
            "service": "lab_8131",
            "method": "systemd",
            "units": list(lab_units),
            "command": [],
            "log_file": None,
            "pid_file": None,
            "env_file": None,
            "port": ports["lab_8131"],
            "detail": "systemctl --user restart " + " ".join(lab_units),
        })
    elif any(r["role"] in {"socket_guardian", "gateway_guardian"} for r in discovery.get("selected") or []):
        specs.append({
            "service": "lab_8131",
            "method": "report",
            "units": [],
            "command": [],
            "log_file": None,
            "pid_file": None,
            "env_file": None,
            "port": ports["lab_8131"],
            "detail": "8131 lab processes selected but no systemd --user units installed; stop via pidfd, start not automated",
        })
    return specs


def run_full_heal(
    *,
    root: Path,
    host: str = "127.0.0.1",
    gateway_port: int = 8101,
    mcp_port: int = 8765,
    lab_port: int = 8131,
    dry_run: bool = False,
    python: Optional[str] = None,
    beast_bin: Optional[Path] = None,
    processes: Optional[Sequence[Mapping[str, Any]]] = None,
    listeners: Optional[Callable[[int], Sequence[int]]] = None,
    facts_for: Optional[Callable[[int], Dict[str, Any]]] = None,
    pidfiles: Optional[Sequence[Path]] = None,
    unit_installed: Optional[Callable[[str], bool]] = None,
    unit_main_pid: Optional[Callable[[str], Optional[int]]] = None,
    lifecycle_factory: Optional[Callable[[], Any]] = None,
    systemctl_restart: Optional[Callable[[Sequence[str]], Dict[str, Any]]] = None,
    spawn: Optional[Callable[..., Dict[str, Any]]] = None,
    unlink: Optional[Callable[[Path], None]] = None,
    proxy_getter: Optional[Callable[[str], Dict[str, Any]]] = None,
    mcp_poster: Optional[Callable[[str, Dict[str, Any]], Dict[str, Any]]] = None,
    stack_before: Optional[Dict[str, Any]] = None,
    stack_after_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    sleeper: Callable[[float], None] = time.sleep,
    grace_s: float = GRACE_SECONDS,
    wait_ports_s: float = 8.0,
    wait_health_s: float = 35.0,
) -> Dict[str, Any]:
    """Plan (and optionally execute) a full BEAST restart. Tests must pass dry_run or fakes; never signal real pids in tests."""
    if (not dry_run) and os.environ.get("PYTEST_CURRENT_TEST") and lifecycle_factory is None and spawn is None and systemctl_restart is None:
        raise RuntimeError("refusing to run a real heal from pytest without fakes (would signal live processes)")
    python = python or str((root / ".venv" / "bin" / "python") if (root / ".venv" / "bin" / "python").exists()
                           else (root / "venv" / "bin" / "python"))
    beast_bin = Path(beast_bin) if beast_bin is not None else root / "bin" / "beast"
    discovery = discover_targets(
        root=root, host=host, gateway_port=gateway_port, mcp_port=mcp_port, lab_port=lab_port,
        processes=processes, listeners=listeners, facts_for=facts_for, pidfiles=pidfiles,
        unit_installed=unit_installed, unit_main_pid=unit_main_pid,
    )
    health_before = {
        "proxy": proxy_health(host, gateway_port, getter=proxy_getter),
        "mcp": mcp_tools_health(host, mcp_port, poster=mcp_poster),
    }
    restarts = _restart_specs(discovery, root=root, python=python, beast_bin=beast_bin)
    actions: List[Dict[str, Any]] = []
    kill_records = [dict(r) for r in discovery["selected"]]
    operator: List[str] = []

    def _sys_restart(units: Sequence[str]) -> Dict[str, Any]:
        if systemctl_restart is not None:
            return systemctl_restart(units)
        try:
            result = subprocess.run(
                ["systemctl", "--user", "restart", *units],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "units": list(units), "error": str(exc)}
        return {"ok": result.returncode == 0, "units": list(units), "returncode": result.returncode,
                "stderr": (result.stderr or "")[:400]}

    def _spawn(*, command: Sequence[str], log_file: str, pid_file: str, env_file: Optional[str], cwd: Path) -> Dict[str, Any]:
        if spawn is not None:
            return spawn(command=list(command), log_file=log_file, pid_file=pid_file, env_file=env_file, cwd=str(cwd))
        env = load_gateway_env(root) if env_file else dict(os.environ)
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab")
        proc = subprocess.Popen(
            list(command), cwd=str(cwd), stdout=handle, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True, env=env,
        )
        Path(pid_file).parent.mkdir(parents=True, exist_ok=True)
        Path(pid_file).write_text(str(proc.pid), encoding="utf-8")
        return {"ok": True, "pid": proc.pid, "command": list(command), "log_file": log_file, "pid_file": pid_file}

    listen_fn = listeners or default_listeners

    if dry_run:
        health_after = health_before
        payload = _payload(
            dry_run=True, discovery=discovery, kills=kill_records, restarts=restarts, actions=actions,
            health_before=health_before, health_after=health_after, stack_before=stack_before,
            stack_after=stack_before, operator=operator, grace_s=grace_s, root=root,
        )
        payload["summary_table"] = format_summary_table(payload)
        return payload

    # --- mutate (never used by tests unless every hook is faked) ---------------------------------
    systemd_pids = set()
    for rec in kill_records:
        if rec.get("restart_via") == "systemd":
            systemd_pids.add(rec["pid"])

    # Stop systemd-managed targets first via systemctl (avoids Restart=on-failure races).
    seen_units: List[str] = []
    for spec in restarts:
        if spec["method"] == "systemd" and spec["units"]:
            for u in spec["units"]:
                if u not in seen_units:
                    seen_units.append(u)
            actions.append({"service": spec["service"], "status": "systemctl_restart", "units": list(spec["units"]),
                            **_sys_restart(spec["units"])})

    # pidfd-terminate remaining BEAST pids.
    life = None
    for rec in kill_records:
        if rec["pid"] in systemd_pids:
            continue
        if life is None:
            if lifecycle_factory is not None:
                life = lifecycle_factory()
            else:
                from app.kernel.execution.process_lifecycle import ProcessLifecycle
                life = ProcessLifecycle(protected_ports=())
        try:
            result = _terminate_via_lifecycle(rec["pid"], label=rec["role"], grace_s=grace_s, lifecycle=life)
            actions.append({"service": rec["role"], "status": "stopped", "pid": rec["pid"], "kill": result})
        except Exception as exc:  # noqa: BLE001 - recorded, never raw-killed around a refusal
            actions.append({"service": rec["role"], "status": "stop_failed", "pid": rec["pid"], "error": str(exc)})

    ports_to_free = [discovery["ports"]["gateway"], discovery["ports"]["mcp_http"]]
    still = _ports_free(ports_to_free, listen_fn, timeout=wait_ports_s, sleeper=sleeper)
    busy = {p: pids for p, pids in still.items() if pids}
    if busy:
        actions.append({"service": "ports", "status": "still_busy", "listeners": busy})

    clearer = unlink or (lambda path: path.unlink(missing_ok=True))
    for rec in discovery["stale_pidfiles"]:
        try:
            clearer(Path(rec["path"]))
            actions.append({"service": "pidfile", "status": "cleared", **rec})
        except OSError as exc:
            actions.append({"service": "pidfile", "status": "clear_failed", "error": str(exc), **rec})

    # Start nohup services that were not covered by systemctl restart above.
    already_systemd = {spec["service"] for spec in restarts if spec["method"] == "systemd"}
    for spec in restarts:
        if spec["method"] != "nohup":
            continue
        if spec["service"] in already_systemd:
            continue
        if spec["port"] in busy:
            actions.append({"service": spec["service"], "status": "skipped_port_busy", "port": spec["port"]})
            continue
        started = _spawn(command=spec["command"], log_file=spec["log_file"], pid_file=spec["pid_file"],
                         env_file=spec["env_file"], cwd=root)
        started.update({"service": spec["service"], "status": "started" if started.get("ok", True) else "start_failed"})
        actions.append(started)

    # Wait for health.
    deadline = time.monotonic() + wait_health_s
    health_after = {
        "proxy": proxy_health(host, gateway_port, getter=proxy_getter),
        "mcp": mcp_tools_health(host, mcp_port, poster=mcp_poster),
    }
    while time.monotonic() < deadline and not (health_after["proxy"].get("fireworks") and health_after["mcp"].get("ok")):
        sleeper(0.4)
        health_after = {
            "proxy": proxy_health(host, gateway_port, getter=proxy_getter),
            "mcp": mcp_tools_health(host, mcp_port, poster=mcp_poster),
        }

    stack_after = stack_after_fn() if stack_after_fn is not None else stack_before
    payload = _payload(
        dry_run=False, discovery=discovery, kills=kill_records, restarts=restarts, actions=actions,
        health_before=health_before, health_after=health_after, stack_before=stack_before,
        stack_after=stack_after, operator=operator, grace_s=grace_s, root=root,
    )
    payload["ports_busy_after_stop"] = busy
    payload["summary_table"] = format_summary_table(payload)
    return payload


def _payload(*, dry_run: bool, discovery: Mapping[str, Any], kills, restarts, actions, health_before,
             health_after, stack_before, stack_after, operator, grace_s, root) -> Dict[str, Any]:
    proxy_ok = bool((health_after or {}).get("proxy", {}).get("fireworks"))
    mcp_ok = bool((health_after or {}).get("mcp", {}).get("ok"))
    ready = proxy_ok and mcp_ok
    if dry_run:
        status = "dry_run"
    elif ready:
        status = "healed"
    else:
        status = "attention"
    ollama = guard.ollama_is_system_service()
    if ollama.get("system"):
        ollama_ok = True
        if stack_before and isinstance(stack_before.get("ollama"), dict):
            ollama_ok = bool(stack_before["ollama"].get("ok", True))
        if not ollama_ok:
            operator.append(ollama["operator_command"])
    env_path = root / GATEWAY_ENV_REL
    flags = redacted_env_keys(parse_env_file(env_path)) if env_path.exists() else list(REQUIRED_GATEWAY_FLAGS)
    return {
        "command": "heal",
        "mode": "full_restart",
        "status": status,
        "dry_run": dry_run,
        "grace_seconds": grace_s,
        "gateway_env_file": str(GATEWAY_ENV_REL),
        "gateway_flags_present": [f for f in REQUIRED_GATEWAY_FLAGS if f in flags or f in parse_env_file(env_path)],
        "would_kill" if dry_run else "killed": kills,
        "restarts": restarts,
        "reported": discovery.get("reported") or [],
        "unknown": discovery.get("unknown") or [],
        "stale_pidfiles": discovery.get("stale_pidfiles") or [],
        "kept_pidfiles": discovery.get("kept_pidfiles") or [],
        "actions": actions,
        "health": {"before": health_before, "after": health_after},
        "before": stack_before or {},
        "after": stack_after or {},
        "operator_commands": operator,
        "changed": (not dry_run) and bool(actions),
        "timestamp": time.time(),
        "protected_ports_selective_only": sorted(guard.protected_ports()),
    }


__all__ = [
    "EXPECTED_MCP_TOOLS", "GATEWAY_ENV_REL", "GATEWAY_UNIT", "GRACE_SECONDS", "LAB_UNITS",
    "discover_targets", "format_summary_table", "is_beast_owned_server", "mcp_tools_health",
    "parse_env_file", "proxy_health", "run_full_heal",
]
