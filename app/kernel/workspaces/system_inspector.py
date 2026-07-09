"""System inspector: VS Code-like ports / process / environment / package tooling.

Pure, request-agnostic helpers for the BEAST IDE "System" plane. Governance
(SafetyGovernor classification, operator approval, EvidenceBus receipts) is applied
by the route layer in ``app/routes/ide.py`` -- this module only reads system state and
performs the actual signal delivery after the route has authorized it.

Everything degrades gracefully: ``psutil`` is preferred but optional, and each CLI
probe is guarded by ``shutil.which``. No function raises for a missing tool; it
returns a structured ``{"ok": False, ...}`` record instead.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # psutil is the fast, portable path; fall back to CLI tools when absent.
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil normally present
    psutil = None  # type: ignore

try:  # tomllib is stdlib on 3.11+; pyproject parsing is best-effort without it.
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore


# Signals we expose to the IDE. SIGTERM is the polite default; SIGKILL is last resort.
SIGNAL_MAP: Dict[str, int] = {
    "TERM": int(getattr(signal, "SIGTERM", 15)),
    "KILL": int(getattr(signal, "SIGKILL", 9)),
    "INT": int(getattr(signal, "SIGINT", 2)),
    "HUP": int(getattr(signal, "SIGHUP", 1)),
}

_SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE|SESSION|COOKIE|AUTH)", re.IGNORECASE)
_SAFE_ENV_ALLOWLIST = (
    "PATH", "HOME", "PWD", "SHELL", "LANG", "LC_ALL", "TERM", "USER", "LOGNAME",
    "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "PYTHONPATH", "PYTHONHOME",
    "NODE_ENV", "NODE_OPTIONS", "NVM_DIR", "npm_config_prefix",
    "BEAST_ACTIVE_WORKSPACE", "BEAST_WORKSPACE", "BEAST_DESKTOP_GATEWAY", "BEAST_PYTHON",
)


def _truncate(text: str, limit: int = 400) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def _cmdline(parts: Any, limit: int = 400) -> str:
    if isinstance(parts, (list, tuple)):
        return _truncate(" ".join(str(item) for item in parts), limit)
    return _truncate(parts, limit)


def command_version(command: str, args: Optional[List[str]] = None, *, cwd: Optional[str] = None, timeout: float = 5.0) -> Dict[str, Any]:
    """Probe a CLI tool's version without ever raising."""
    args = args or ["--version"]
    resolved = shutil.which(command)
    if not resolved:
        return {"ok": False, "command": command, "installed": False, "error": "not found on PATH"}
    try:
        completed = subprocess.run(
            [command, *args], cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False,
        )
        output = (completed.stdout or completed.stderr or "").strip().splitlines()
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "installed": True,
            "path": resolved,
            "version": output[0].strip() if output else "available",
            "returncode": int(completed.returncode),
        }
    except Exception as exc:  # timeouts, decode errors, etc.
        return {"ok": False, "command": command, "installed": True, "path": resolved, "error": str(exc)}


# --------------------------------------------------------------------------------------
# Ports
# --------------------------------------------------------------------------------------

def _ports_via_psutil(limit: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen = set()
    try:
        connections = psutil.net_connections(kind="inet")
    except Exception:
        return rows
    for conn in connections:
        # Listening TCP sockets, plus bound UDP sockets (which report status NONE).
        is_tcp = getattr(conn, "type", None) == getattr(__import__("socket"), "SOCK_STREAM", 1)
        proto = "tcp" if is_tcp else "udp"
        status = str(getattr(conn, "status", "") or "")
        if is_tcp and status != "LISTEN":
            continue
        if not conn.laddr:
            continue
        ip = getattr(conn.laddr, "ip", "")
        port = int(getattr(conn.laddr, "port", 0) or 0)
        pid = conn.pid
        key = (proto, ip, port, pid)
        if key in seen:
            continue
        seen.add(key)
        name = ""
        cmdline = ""
        username = ""
        if pid:
            try:
                proc = psutil.Process(pid)
                name = proc.name()
                cmdline = _cmdline(proc.cmdline())
                username = proc.username()
            except Exception:
                pass
        rows.append({
            "proto": proto,
            "address": ip,
            "port": port,
            "status": status or "BOUND",
            "pid": pid,
            "process": name,
            "cmdline": cmdline,
            "user": username,
        })
        if len(rows) >= limit:
            break
    return rows


def _ports_via_ss(limit: int) -> List[Dict[str, Any]]:
    if not shutil.which("ss"):
        return []
    try:
        completed = subprocess.run(["ss", "-tulnpH"], capture_output=True, text=True, timeout=6, check=False)
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for line in (completed.stdout or "").splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        proto = fields[0].lower()
        local = fields[4]
        port = 0
        addr = local
        if ":" in local:
            addr, _, port_s = local.rpartition(":")
            try:
                port = int(port_s)
            except ValueError:
                port = 0
        pid = None
        process = ""
        match = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
        if match:
            process = match.group(1)
            pid = int(match.group(2))
        rows.append({
            "proto": "tcp" if proto.startswith("tcp") else "udp",
            "address": addr, "port": port, "status": "LISTEN",
            "pid": pid, "process": process, "cmdline": "", "user": "",
        })
        if len(rows) >= limit:
            break
    return rows


def list_listening_ports(limit: int = 300) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 1000))
    rows = _ports_via_psutil(limit) if psutil is not None else []
    source = "psutil"
    if not rows:
        rows = _ports_via_ss(limit)
        source = "ss"
    rows.sort(key=lambda item: (item.get("proto") or "", int(item.get("port") or 0)))
    return {
        "ok": True,
        "beast_object_type": "beast_ide_ports",
        "version": "1.0",
        "source": source,
        "count": len(rows),
        "ports": rows,
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Processes
# --------------------------------------------------------------------------------------

def list_processes(query: str = "", limit: int = 120, sort: str = "memory") -> Dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    needle = str(query or "").strip().lower()
    rows: List[Dict[str, Any]] = []
    source = "psutil"
    if psutil is not None:
        for proc in psutil.process_iter(["pid", "name", "username", "cmdline", "memory_info", "cpu_percent", "status", "create_time", "ppid"]):
            try:
                info = proc.info
                pid = int(info.get("pid") or 0)
                name = str(info.get("name") or "")
                cmdline = _cmdline(info.get("cmdline"))
                mem = info.get("memory_info")
                rss = int(getattr(mem, "rss", 0) or 0) if mem else 0
                haystack = f"{pid} {name} {cmdline}".lower()
                if needle and needle not in haystack:
                    continue
                rows.append({
                    "pid": pid,
                    "ppid": int(info.get("ppid") or 0),
                    "name": name,
                    "user": str(info.get("username") or ""),
                    "status": str(info.get("status") or ""),
                    "cpu_percent": float(info.get("cpu_percent") or 0.0),
                    "rss_bytes": rss,
                    "rss_mb": round(rss / (1024 * 1024), 1),
                    "cmdline": cmdline,
                })
            except Exception:
                continue
    else:
        source = "ps"
        rows = _processes_via_ps(needle)
    if sort == "cpu":
        rows.sort(key=lambda item: float(item.get("cpu_percent") or 0.0), reverse=True)
    else:
        rows.sort(key=lambda item: int(item.get("rss_bytes") or 0), reverse=True)
    total = len(rows)
    return {
        "ok": True,
        "beast_object_type": "beast_ide_processes",
        "version": "1.0",
        "source": source,
        "query": query,
        "total": total,
        "count": min(total, limit),
        "processes": rows[:limit],
        "read_only": True,
    }


def _processes_via_ps(needle: str) -> List[Dict[str, Any]]:
    if not shutil.which("ps"):
        return []
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,user=,rss=,stat=,comm=,args="],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    for line in (completed.stdout or "").splitlines():
        parts = line.split(None, 6)
        if len(parts) < 7:
            continue
        try:
            pid = int(parts[0]); ppid = int(parts[1]); rss_kb = int(parts[3])
        except ValueError:
            continue
        name = parts[5]; args = parts[6]
        haystack = f"{pid} {name} {args}".lower()
        if needle and needle not in haystack:
            continue
        rows.append({
            "pid": pid, "ppid": ppid, "name": name, "user": parts[2], "status": parts[4],
            "cpu_percent": 0.0, "rss_bytes": rss_kb * 1024, "rss_mb": round(rss_kb / 1024, 1),
            "cmdline": _truncate(args),
        })
    return rows


def process_detail(pid: int) -> Dict[str, Any]:
    pid = int(pid)
    if psutil is None:
        return {"ok": False, "pid": pid, "error": "psutil not available"}
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            mem = proc.memory_info()
            return {
                "ok": True,
                "pid": pid,
                "ppid": proc.ppid(),
                "name": proc.name(),
                "user": proc.username(),
                "status": proc.status(),
                "exe": _safe(lambda: proc.exe()),
                "cwd": _safe(lambda: proc.cwd()),
                "cmdline": _cmdline(proc.cmdline(), 800),
                "create_time": proc.create_time(),
                "rss_mb": round(int(getattr(mem, "rss", 0) or 0) / (1024 * 1024), 1),
                "num_threads": _safe(lambda: proc.num_threads()),
            }
    except Exception as exc:
        return {"ok": False, "pid": pid, "error": str(exc)}


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


# --------------------------------------------------------------------------------------
# Kill (guardrails here; governance/evidence in the route layer)
# --------------------------------------------------------------------------------------

def _protection(pid: int) -> Dict[str, Any]:
    """Classify whether a pid is safe to signal. Never allow suicide or init."""
    if pid <= 0:
        return {"protected": True, "reason": "invalid_pid"}
    if pid == 1:
        return {"protected": True, "reason": "init_process"}
    if pid == os.getpid():
        return {"protected": True, "reason": "beast_gateway_self"}
    if pid == os.getppid():
        return {"protected": True, "reason": "beast_gateway_parent"}
    return {"protected": False, "reason": ""}


def describe_kill_target(pid: int, sig: str = "TERM") -> Dict[str, Any]:
    """Preview a kill: resolve the process, the signal, and any protection.

    The ``command`` field is a synthetic ``kill -N <pid>`` string the route hands to the
    SafetyGovernor so process termination is classified and audited like any command.
    """
    pid = int(pid)
    sig = str(sig or "TERM").upper().lstrip("SIG")
    signum = SIGNAL_MAP.get(sig, SIGNAL_MAP["TERM"])
    detail = process_detail(pid)
    protection = _protection(pid)
    exists = bool(detail.get("ok"))
    return {
        "pid": pid,
        "signal": sig,
        "signum": signum,
        "exists": exists,
        "process": detail if exists else {"ok": False, "pid": pid, "error": detail.get("error")},
        "protected": bool(protection["protected"]),
        "protected_reason": protection["reason"],
        "command": f"kill -{signum} {pid}",
        "killable": exists and not protection["protected"],
    }


def kill_process(pid: int, sig: str = "TERM") -> Dict[str, Any]:
    """Deliver a signal to ``pid`` after guardrail checks. Assumes the route already
    obtained SafetyGovernor approval; this still refuses protected pids defensively."""
    preview = describe_kill_target(pid, sig)
    if preview["protected"]:
        return {"ok": False, "status": "refused", "reason": preview["protected_reason"], **preview}
    if not preview["exists"]:
        return {"ok": False, "status": "not_found", "reason": "no_such_process", **preview}
    signum = preview["signum"]
    try:
        if psutil is not None:
            psutil.Process(pid).send_signal(signum)
        else:
            os.kill(pid, signum)
    except PermissionError:
        return {"ok": False, "status": "permission_denied", "reason": "insufficient_privileges", **preview}
    except ProcessLookupError:
        return {"ok": False, "status": "not_found", "reason": "vanished", **preview}
    except Exception as exc:
        return {"ok": False, "status": "error", "reason": str(exc), **preview}
    still = process_detail(pid).get("ok")
    return {
        "ok": True,
        "status": "signalled" if still else "terminated",
        "still_running": bool(still),
        "reason": "",
        **preview,
    }


def _port_pids_via_cli(port: int) -> List[int]:
    """Resolve owner pids for a port via lsof/ss. psutil's net_connections cannot always
    attribute a socket to a pid (permissions / namespace), so freeing a port -- a
    destructive action -- must fall back to a pid-resolving tool."""
    pids: List[int] = []
    if shutil.which("lsof"):
        try:
            completed = subprocess.run(["lsof", "-ti", f"tcp:{port}"], capture_output=True, text=True, timeout=6, check=False)
            pids = [int(x) for x in (completed.stdout or "").split() if x.strip().isdigit()]
        except Exception:
            pids = []
    if not pids and shutil.which("ss"):
        try:
            completed = subprocess.run(["ss", "-tlnpH", f"sport = :{port}"], capture_output=True, text=True, timeout=6, check=False)
            for match in re.finditer(r"pid=(\d+)", completed.stdout or ""):
                pids.append(int(match.group(1)))
        except Exception:
            pass
    # Dedup, preserve order.
    out: List[int] = []
    for pid in pids:
        if pid not in out:
            out.append(pid)
    return out


def find_port_owners(port: int) -> Dict[str, Any]:
    """Which pids are listening on ``port`` -- used to free a port."""
    port = int(port)
    ports = list_listening_ports().get("ports") or []
    owners = [row for row in ports if int(row.get("port") or 0) == port and row.get("pid")]
    source = "psutil"
    if not owners:
        # psutil could not attribute the socket to a pid; resolve via lsof/ss instead.
        source = "cli"
        for pid in _port_pids_via_cli(port):
            detail = process_detail(pid)
            owners.append({
                "proto": "tcp",
                "address": "",
                "port": port,
                "status": "LISTEN",
                "pid": pid,
                "process": detail.get("name") if detail.get("ok") else "",
                "cmdline": detail.get("cmdline") if detail.get("ok") else "",
                "user": detail.get("user") if detail.get("ok") else "",
            })
    return {
        "ok": True,
        "port": port,
        "count": len(owners),
        "owners": owners,
        "source": source,
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Environment
# --------------------------------------------------------------------------------------

def environment_report(root: Optional[Path] = None) -> Dict[str, Any]:
    import platform

    in_venv = bool(getattr(sys, "base_prefix", sys.prefix) != sys.prefix or os.environ.get("VIRTUAL_ENV"))
    python = {
        "version": sys.version.split()[0],
        "full_version": _truncate(sys.version, 200),
        "executable": sys.executable,
        "prefix": sys.prefix,
        "base_prefix": getattr(sys, "base_prefix", sys.prefix),
        "in_virtualenv": in_venv,
        "virtualenv": os.environ.get("VIRTUAL_ENV") or "",
        "implementation": platform.python_implementation(),
    }
    interpreters = [
        command_version("python3", ["--version"]),
        command_version("python", ["--version"]),
        command_version("node", ["--version"]),
        command_version("npm", ["--version"]),
        command_version("pnpm", ["--version"]),
        command_version("yarn", ["--version"]),
        command_version("pip3", ["--version"]),
        command_version("git", ["--version"]),
        command_version("docker", ["--version"]),
        command_version("rustc", ["--version"]),
        command_version("go", ["version"]),
    ]
    env_vars: List[Dict[str, Any]] = []
    for name in sorted(os.environ):
        value = os.environ.get(name, "")
        if _SECRET_ENV.search(name):
            env_vars.append({"name": name, "value": "***redacted***", "redacted": True})
        elif name in _SAFE_ENV_ALLOWLIST:
            env_vars.append({"name": name, "value": _truncate(value, 600), "redacted": False})
    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    return {
        "ok": True,
        "beast_object_type": "beast_ide_environment",
        "version": "1.0",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "node": platform.node(),
        },
        "python": python,
        "interpreters": interpreters,
        "path_entries": path_entries[:80],
        "env_vars": env_vars,
        "env_var_note": "Secret-like variables are redacted; only an allowlist of non-secret vars is shown.",
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Package management
# --------------------------------------------------------------------------------------

def _installed_python_distributions() -> Dict[str, str]:
    try:
        import importlib.metadata as md
    except Exception:
        return {}
    installed: Dict[str, str] = {}
    try:
        for dist in md.distributions():
            name = (dist.metadata.get("Name") if dist.metadata else None) or ""
            if name:
                installed[name.lower().replace("_", "-")] = dist.version or ""
    except Exception:
        return installed
    return installed


def _parse_requirements(text: str) -> List[str]:
    names: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)", line)
        if match:
            names.append(match.group(1))
    return names


def package_report(root: Path) -> Dict[str, Any]:
    root = Path(root)
    installed = _installed_python_distributions()

    # --- Python side ---
    req_files = sorted(str(p.relative_to(root)) for p in root.glob("requirements*.txt") if p.is_file())
    declared_py: List[str] = []
    for rel in req_files:
        try:
            declared_py.extend(_parse_requirements((root / rel).read_text(encoding="utf-8", errors="replace")))
        except Exception:
            continue
    pyproject = root / "pyproject.toml"
    pyproject_deps: List[str] = []
    if pyproject.exists() and tomllib is not None:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
            project = data.get("project") if isinstance(data.get("project"), dict) else {}
            for spec in project.get("dependencies", []) or []:
                match = re.match(r"^([A-Za-z0-9_.\-]+)", str(spec))
                if match:
                    pyproject_deps.append(match.group(1))
        except Exception:
            pyproject_deps = []
    declared_py = sorted(set(declared_py) | set(pyproject_deps))
    python_deps = [
        {
            "name": name,
            "installed_version": installed.get(name.lower().replace("_", "-"), ""),
            "installed": name.lower().replace("_", "-") in installed,
        }
        for name in declared_py[:400]
    ]

    # --- Node side ---
    node_pkgs: List[Dict[str, Any]] = []
    node_scripts: Dict[str, str] = {}
    node_manifests = []
    for rel_dir in ("", "desktop-ide", "vscode-extension"):
        manifest = (root / rel_dir / "package.json") if rel_dir else (root / "package.json")
        if not manifest.exists():
            continue
        try:
            pkg = __import__("json").loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        node_modules = (manifest.parent / "node_modules").exists()
        lockfile = next((lf for lf in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock") if (manifest.parent / lf).exists()), "")
        manager = {"package-lock.json": "npm", "pnpm-lock.yaml": "pnpm", "yarn.lock": "yarn"}.get(lockfile, "npm")
        deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
        scripts = pkg.get("scripts") or {}
        if rel_dir == "":
            node_scripts = {k: str(v) for k, v in scripts.items()}
        node_manifests.append({
            "location": rel_dir or ".",
            "name": pkg.get("name") or "",
            "dependency_count": len(deps),
            "node_modules_installed": node_modules,
            "lockfile": lockfile,
            "manager": manager,
            "scripts": sorted(scripts.keys()),
            "install_command": f"{manager} install",
        })
        for name, ver in sorted(deps.items())[:200]:
            node_pkgs.append({"location": rel_dir or ".", "name": name, "declared": str(ver)})

    suggestions = []
    if req_files:
        suggestions.append({"label": "Install Python requirements", "command": f"pip install -r {req_files[0]}", "risk": "medium"})
    for manifest in node_manifests:
        if not manifest["node_modules_installed"]:
            loc = manifest["location"]
            prefix = f"cd {loc} && " if loc != "." else ""
            suggestions.append({"label": f"Install node deps ({loc})", "command": f"{prefix}{manifest['install_command']}", "risk": "medium"})

    return {
        "ok": True,
        "beast_object_type": "beast_ide_packages",
        "version": "1.0",
        "workspace_root": str(root),
        "python": {
            "requirement_files": req_files,
            "has_pyproject": pyproject.exists(),
            "declared_count": len(declared_py),
            "installed_distribution_count": len(installed),
            "dependencies": python_deps,
        },
        "node": {
            "manifests": node_manifests,
            "root_scripts": node_scripts,
            "dependencies": node_pkgs,
        },
        "suggested_commands": suggestions,
        "execution_note": "Suggested commands are advisory; run them only through the governed terminal (/edgek/safety-governor/execute-command).",
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Extensions / tools
# --------------------------------------------------------------------------------------

def extensions_report(root: Path) -> Dict[str, Any]:
    import json as _json

    root = Path(root)

    def read_json(path: Path) -> Dict[str, Any]:
        try:
            return _json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return {}

    vsix = read_json(root / "vscode-extension" / "package.json")
    contributes = vsix.get("contributes") if isinstance(vsix.get("contributes"), dict) else {}
    commands = contributes.get("commands") if isinstance(contributes.get("commands"), list) else []
    vscode_extension = {
        "present": bool(vsix),
        "name": vsix.get("name") or "",
        "display_name": vsix.get("displayName") or "",
        "version": vsix.get("version") or "",
        "publisher": vsix.get("publisher") or "",
        "engine": (vsix.get("engines") or {}).get("vscode", ""),
        "main": vsix.get("main") or "",
        "activation_events": vsix.get("activationEvents") or [],
        "command_count": len(commands),
        "commands": [{"command": c.get("command"), "title": c.get("title")} for c in commands[:60] if isinstance(c, dict)],
    }

    desktop = read_json(root / "desktop-ide" / "package.json")
    desktop_ide = {
        "present": bool(desktop),
        "name": desktop.get("name") or "",
        "version": desktop.get("version") or "",
        "main": desktop.get("main") or "",
        "scripts": sorted((desktop.get("scripts") or {}).keys()),
    }

    plugins_dir = root / "plugins"
    plugins: List[str] = []
    if plugins_dir.exists():
        plugins = sorted(child.name for child in plugins_dir.iterdir() if child.is_dir())[:100]

    mcp_servers: List[str] = []
    cursor_mcp = root / ".cursor" / "mcp.json"
    if cursor_mcp.exists():
        data = read_json(cursor_mcp)
        servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
        mcp_servers = sorted(servers.keys())

    return {
        "ok": True,
        "beast_object_type": "beast_ide_extensions",
        "version": "1.0",
        "workspace_root": str(root),
        "vscode_extension": vscode_extension,
        "desktop_ide": desktop_ide,
        "plugins": {"directory": str(plugins_dir), "count": len(plugins), "names": plugins},
        "mcp": {"config": str(cursor_mcp), "configured": cursor_mcp.exists(), "servers": mcp_servers},
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Curated catalog (recommended MCP servers / tools / editor extensions)
# --------------------------------------------------------------------------------------

def _repo_root() -> Path:
    # app/kernel/workspaces/system_inspector.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def catalog_report(root: Optional[Path] = None) -> Dict[str, Any]:
    """Load the curated catalog and enrich it with live install/availability state.

    Advisory only: this never installs or executes anything. It reports which MCP
    runners (npx/uvx) and CLI tools are present so the IDE can show actionable,
    honest 'recommended install' state.
    """
    import json as _json

    candidates = []
    if root:
        candidates.append(Path(root) / "catalog" / "beast-ide-catalog.json")
    candidates.append(_repo_root() / "catalog" / "beast-ide-catalog.json")
    data: Dict[str, Any] = {}
    catalog_path = ""
    for path in candidates:
        if path.exists():
            try:
                data = _json.loads(path.read_text(encoding="utf-8", errors="replace"))
                catalog_path = str(path)
                break
            except Exception:
                continue

    mcp_servers = data.get("mcp_servers") if isinstance(data.get("mcp_servers"), list) else []
    tools = data.get("tools") if isinstance(data.get("tools"), list) else []
    extensions = data.get("vscode_extensions") if isinstance(data.get("vscode_extensions"), list) else []

    for server in mcp_servers:
        runner = str(server.get("runner") or server.get("command") or "")
        server["runner_available"] = bool(runner and shutil.which(runner))
        # mcpServers-format config snippet for copy/paste into an MCP client.
        server["mcp_config"] = {
            "mcpServers": {
                server.get("id", "server"): {
                    "command": server.get("command"),
                    "args": server.get("args", []),
                    **({"env": server["env"]} if server.get("env") else {}),
                }
            }
        }
    installed_tools = 0
    for tool in tools:
        present = bool(shutil.which(str(tool.get("detect") or tool.get("id") or "")))
        tool["installed"] = present
        installed_tools += 1 if present else 0

    return {
        "ok": bool(data),
        "beast_object_type": "beast_ide_catalog_report",
        "version": "1.0",
        "catalog_path": catalog_path,
        "note": data.get("note", ""),
        "summary": {
            "mcp_servers": len(mcp_servers),
            "mcp_runners_available": sum(1 for s in mcp_servers if s.get("runner_available")),
            "tools": len(tools),
            "tools_installed": installed_tools,
            "vscode_extensions": len(extensions),
        },
        "mcp_servers": mcp_servers,
        "tools": tools,
        "vscode_extensions": extensions,
        "read_only": True,
    }


# --------------------------------------------------------------------------------------
# Aggregate snapshot
# --------------------------------------------------------------------------------------

def system_snapshot(root: Path, *, port_limit: int = 60, process_limit: int = 30, process_query: str = "") -> Dict[str, Any]:
    ports = list_listening_ports(limit=port_limit)
    processes = list_processes(query=process_query, limit=process_limit)
    environment = environment_report(root)
    packages = package_report(root)
    extensions = extensions_report(root)
    return {
        "ok": True,
        "beast_object_type": "beast_ide_system_snapshot",
        "version": "1.0",
        "workspace_root": str(root),
        "psutil_available": psutil is not None,
        "capabilities": {
            "ports": True,
            "processes": True,
            "process_kill": True,
            "port_free": True,
            "environment": True,
            "packages": True,
            "extensions": True,
        },
        "summary": {
            "listening_ports": ports.get("count", 0),
            "processes_total": processes.get("total", 0),
            "python": environment.get("python", {}).get("version", ""),
            "in_virtualenv": environment.get("python", {}).get("in_virtualenv", False),
            "python_dependencies": packages.get("python", {}).get("declared_count", 0),
            "node_manifests": len(packages.get("node", {}).get("manifests", []) or []),
            "vscode_commands": extensions.get("vscode_extension", {}).get("command_count", 0),
        },
        "ports": ports,
        "processes": processes,
        "environment": environment,
        "packages": packages,
        "extensions": extensions,
        "read_only": True,
    }
