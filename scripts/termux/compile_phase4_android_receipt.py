#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def junit(path: Path, minimum: int = 1) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall(".//testsuite"))
    def total(name: str) -> int:
        values = [int(float(item.attrib.get(name, "0") or 0)) for item in suites]
        declared = int(float(root.attrib.get(name, "0") or 0)) if root.tag == "testsuites" else 0
        return max(declared, sum(values))
    cases = sorted({
        str(case.attrib.get("name") or "").strip()
        for case in root.findall(".//testcase")
        if str(case.attrib.get("name") or "").strip()
    })
    result = {
        "path": path.name,
        "digest": sha256(path),
        "tests": total("tests"),
        "failures": total("failures"),
        "errors": total("errors"),
        "skipped": total("skipped"),
        "test_cases": cases,
    }
    result["passed"] = (
        result["tests"] >= minimum
        and result["failures"] == 0
        and result["errors"] == 0
        and result["skipped"] == 0
    )
    return result


def get_json(url: str, timeout: float = 4.0) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"ok": response.status < 400, "url": url, "payload": payload}
    except Exception as exc:
        return {"ok": False, "url": url, "error": f"{type(exc).__name__}: {exc}"}


def command(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as exc:
        return f"unavailable: {type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--md-out", type=Path, required=True)
    args = parser.parse_args()

    prefix = str(os.environ.get("PREFIX") or "")
    termux = bool(os.environ.get("TERMUX_VERSION") or "/com.termux/" in prefix or "/com.termux/" in sys.executable)

    groups = {
        "canonical_phase4": junit(args.input_dir / "phase4-canonical.xml", 20),
        "live_durable_authority": junit(args.input_dir / "phase4-live-approval.xml", 6),
        "permission_modes": junit(args.input_dir / "phase4-modes.xml", 5),
        "sensitive_external_controls": junit(args.input_dir / "phase4-sensitive-external.xml", 3),
        "phase3_regression": junit(args.input_dir / "phase3-regression.xml", 20),
        "desktop_renderer_ingress": junit(args.input_dir / "desktop-ingress.xml", 1),
        "live_local_ollama": junit(args.input_dir / "live-ollama.xml", 1),
        "planner_endurance": junit(args.input_dir / "planner-endurance.xml", 5),
    }

    required_live = {
        "test_live_planner_uses_one_use_phase4_capability",
        "test_review_mode_lifts_read_only_tool_into_durable_approval",
        "test_restart_paused_approval_consumes_exact_capability",
        "test_request_replan_continues_same_run_with_governance_observation",
        "test_permanent_deny_persists_tool_revocation_across_runs",
        "test_restart_approval_route_executes_exact_step_before_worker_relaunch",
    }
    observed = set(groups["live_durable_authority"]["test_cases"])
    groups["live_durable_authority"]["missing_required_tests"] = sorted(required_live - observed)
    if groups["live_durable_authority"]["missing_required_tests"]:
        groups["live_durable_authority"]["passed"] = False

    health = {
        "gateway": get_json("http://127.0.0.1:8101/health"),
        "proxy": get_json("http://127.0.0.1:8101/proxy/health"),
        "mcp_gateway": get_json("http://127.0.0.1:8101/mcp/health"),
        "providers": get_json("http://127.0.0.1:8101/edgek/providers/state"),
        "desktop_contract": get_json("http://127.0.0.1:8101/edgek/control-plane/desktop-compatibility"),
        "mcp_http": get_json("http://127.0.0.1:8765/mcp/health"),
        "ollama": get_json("http://127.0.0.1:11434/api/tags"),
    }
    backend_ready = all(item["ok"] for item in health.values())
    all_tests = all(bool(item.get("passed")) for item in groups.values())
    passed = termux and backend_ready and all_tests

    report = {
        "schema": "beast.coding_agent.phase4.termux_android_acceptance.v1",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verified": passed,
        "platform": {
            "termux_detected": termux,
            "python": platform.python_version(),
            "machine": platform.machine(),
            "platform": platform.platform(),
            "executable": sys.executable,
            "prefix": prefix,
            "android_release": command("getprop", "ro.build.version.release"),
        },
        "git": {
            "head": command("git", "rev-parse", "HEAD"),
            "branch": command("git", "branch", "--show-current"),
        },
        "ollama": {
            "version": command("ollama", "--version"),
            "model": os.environ.get("BEAST_LIVE_OLLAMA_MODEL", "qwen2.5:0.5b"),
            "remote_inference_used": False,
        },
        "backend_ready": backend_ready,
        "health": health,
        "gates": groups,
        "claims": {
            "termux_android_phase4": passed,
            "durable_approval_restart": bool(groups["live_durable_authority"]["passed"]),
            "permission_modes": bool(groups["permission_modes"]["passed"]),
            "sensitive_external_controls": bool(groups["sensitive_external_controls"]["passed"]),
            "desktop_renderer_ingress": bool(groups["desktop_renderer_ingress"]["passed"]),
            "local_android_ollama_provider": bool(groups["live_local_ollama"]["passed"]),
            "planner_endurance": bool(groups["planner_endurance"]["passed"]),
            "full_native_backend": backend_ready,
            "electron_desktop_shell_native_bionic": False,
            "electron_desktop_shell_via_proot_x11": "separate manual/UI validation",
        },
    }
    args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# BEAST Phase 4 Termux / Android Acceptance",
        "",
        f"**Status:** {'PASS' if passed else 'REFUSE'}",
        "",
        f"- Git head: `{report['git']['head']}`",
        f"- Android: `{report['platform']['android_release']}`",
        f"- Architecture: `{report['platform']['machine']}`",
        f"- Python: `{report['platform']['python']}`",
        f"- Ollama: `{report['ollama']['version']}`",
        f"- Model: `{report['ollama']['model']}`",
        f"- Native backend ready: `{backend_ready}`",
        "",
        "## Gates",
        "",
        "| Gate | State | Tests | Digest |",
        "|---|---|---:|---|",
    ]
    for name, gate in groups.items():
        lines.append(
            f"| `{name}` | **{'PASS' if gate['passed'] else 'FAIL'}** | {gate['tests']} | `{gate['digest']}` |"
        )
    lines += [
        "",
        "## Boundary",
        "",
        "This receipt proves the BEAST Phase 4 coding-agent backend, durable authority controls,",
        "renderer-to-backend ingress, local Ollama provider exchange and planner endurance on",
        "native Android/Termux. The Electron desktop shell is intentionally a separate",
        "Debian-proot + Termux:X11 UI validation because stock Linux Electron is glibc-based,",
        "not a native Android/Bionic executable.",
        "",
    ]
    args.md_out.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"verified": passed, "backend_ready": backend_ready, "gates": {k: v["passed"] for k, v in groups.items()}}, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
