"""Protection policy for ``beast heal`` (and anything else that stops/kills/restarts local services).

Never stopped, killed or restarted by heal, whatever the flags:
* listeners on protected ports: 8101 (live gateway) and 8131 (lab units), plus ``BEAST_HEAL_PROTECTED_PORTS``;
* ARDA and seraph processes/units/containers (cmdline, comm or cgroup mentions ``arda`` / ``seraph``);
* the system Ollama service (``ollama.service`` or any ``ollama`` process not owned by this uid) -- heal never
  spawns a second ``ollama serve`` while one exists or the system unit is installed;
* anything in ``system.slice``, docker/containerd/libpod cgroups, owned by another uid, PID 1 or this process.
Each refusal carries a reason and, where useful, the command the operator would run instead.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

DEFAULT_PROTECTED_PORTS = frozenset({8101, 8131})
PROTECTED_WORDS = ("arda", "seraph")
FOREIGN_CGROUP_MARKERS = ("system.slice", "docker", "containerd", "libpod", "machine.slice")


def protected_ports(env: Optional[Dict[str, str]] = None) -> frozenset[int]:
    env = os.environ if env is None else env
    extra = {int(p) for p in str(env.get("BEAST_HEAL_PROTECTED_PORTS", "")).replace(" ", "").split(",") if p.isdigit()}
    return frozenset(DEFAULT_PROTECTED_PORTS | extra)


def _read(path: str) -> str:
    try:
        return Path(path).read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def process_facts(pid: int) -> Dict[str, Any]:
    try:
        uid = os.stat(f"/proc/{pid}").st_uid
    except OSError:
        uid = None
    return {"pid": pid, "uid": uid, "comm": _read(f"/proc/{pid}/comm"), "cmdline": _read(f"/proc/{pid}/cmdline")[:400],
            "cgroup": _read(f"/proc/{pid}/cgroup")[:400]}


def pid_protection(pid: int, *, port: Optional[int] = None, facts: Optional[Dict[str, Any]] = None,
                   env: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    """(protected, reason). Fail closed: unknown processes on protected ports stay protected."""
    if port is not None and int(port) in protected_ports(env):
        return True, f"protected_port:{int(port)}"
    if pid <= 1 or pid == os.getpid():
        return True, "init_or_self"
    f = facts or process_facts(pid)
    text = " ".join(str(f.get(k) or "") for k in ("comm", "cmdline", "cgroup")).lower()
    for word in PROTECTED_WORDS:
        if word in text:
            return True, f"protected_owner:{word}"
    if "ollama" in text:
        return True, "system_ollama"
    if f.get("uid") is not None and f["uid"] != os.getuid():
        return True, "foreign_uid"
    if any(m in str(f.get("cgroup") or "") for m in FOREIGN_CGROUP_MARKERS):
        return True, "foreign_cgroup"
    return False, ""


def filter_killable(pids: Iterable[int], *, port: Optional[int] = None) -> Tuple[list[int], list[Dict[str, Any]]]:
    allowed, refused = [], []
    for pid in sorted(set(int(p) for p in pids)):
        protected, reason = pid_protection(pid, port=port)
        (refused.append({"pid": pid, "reason": reason}) if protected else allowed.append(pid))
    return allowed, refused


def systemd_unit_state(unit: str, *, user: bool = False) -> str:
    cmd = ["systemctl", *(["--user"] if user else []), "is-active", unit]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=4, check=False).stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def ollama_is_system_service() -> Dict[str, Any]:
    """True when Ollama is (or would be) managed by the system: never start/stop it from heal."""
    unit_files = [p for p in ("/etc/systemd/system/ollama.service", "/lib/systemd/system/ollama.service",
                              "/usr/lib/systemd/system/ollama.service") if Path(p).exists()]
    state = systemd_unit_state("ollama.service")
    foreign = []
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit() and _read(f"/proc/{entry}/comm") == "ollama":
                try:
                    if os.stat(f"/proc/{entry}").st_uid != os.getuid():
                        foreign.append(int(entry))
                except OSError:
                    continue
    except OSError:
        pass
    return {"system": bool(unit_files or state in {"active", "activating", "reloading"} or foreign),
            "unit_state": state, "unit_files": unit_files, "foreign_pids": foreign[:8],
            "operator_command": "sudo systemctl restart ollama.service"}


def nginx_check(port: int = 80, *, url_ready=None, probe=None) -> Dict[str, Any]:
    """nginx is 'ok' only when it serves BEAST's /health; 'listening' distinguishes a missing route from a dead nginx."""
    import urllib.error
    import urllib.request

    url = f"http://127.0.0.1:{int(port)}/health"
    status: Optional[int] = None
    if probe is not None:
        status = probe(url)
    else:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as r:  # noqa: S310 - loopback only
                status = r.status
        except urllib.error.HTTPError as exc:
            status = exc.code
        except (OSError, ValueError):
            status = None
    out = {"ok": status == 200, "listening": status is not None, "http_status": status, "port": int(port), "path": url}
    if status is not None and status != 200:
        out["diagnosis"] = "nginx_listening_without_beast_health_route"
        out["operator_command"] = ("sudo install -m 644 deploy/generated/nginx.edgek.80.conf /etc/nginx/sites-available/edgek-beast "
                                   "&& sudo ln -sf /etc/nginx/sites-available/edgek-beast /etc/nginx/sites-enabled/edgek-beast "
                                   "&& sudo nginx -t && sudo systemctl reload nginx")
    elif status is None:
        out["diagnosis"] = "nothing_listening"
        out["operator_command"] = "sudo systemctl start nginx"
    return out


__all__ = ["DEFAULT_PROTECTED_PORTS", "filter_killable", "nginx_check", "ollama_is_system_service", "pid_protection",
           "process_facts", "protected_ports", "systemd_unit_state"]
