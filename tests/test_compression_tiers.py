"""Experimental Task 1: real context compression tiers (repo map, RTK/sqz detection, LongCodeZip-style)."""
from __future__ import annotations

import ast
import stat
import textwrap

import pytest

from app.context.compression_tiers import (
    TIERS_ENV,
    CompressionTierRouter,
    detect_compressors,
    long_code_compress,
    measure,
    repo_map,
    tiers_enabled,
)
from app.kernel.governance.governor_spine import ComputeGovernorSpine

MODULE = textwrap.dedent('''
    import os
    from typing import Any


    def load_config(path: str) -> dict:
        """Read configuration."""
        data = {}
        for line in open(path):
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip()
        return data


    def compute_rate(base: float, tax: float) -> float:
        total = base
        for _ in range(3):
            total = total * (1 + tax)
        return round(total, 2)


    class Ledger:
        def __init__(self, path: str) -> None:
            self.path = path
            self.rows = []

        def append(self, row: Any) -> None:
            self.rows.append(row)
            if len(self.rows) > 100:
                self.rows = self.rows[-100:]

        def balance(self) -> float:
            return sum(float(r) for r in self.rows)


    def unrelated_helper(x):
        y = x * 2
        z = y + 1
        w = z - 3
        return w
''')


def _repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "rates.py").write_text(MODULE)
    (tmp_path / "pkg" / "app.py").write_text("from pkg.rates import compute_rate, Ledger\n\n\n"
                                            "def main():\n    return compute_rate(1.0, 0.1)\n")
    (tmp_path / "pkg" / "other.py").write_text("from pkg import rates\n\n\ndef other():\n    return rates.load_config('x')\n")
    return tmp_path


def _fake_binary(tmp_path, name, version_output):
    path = tmp_path / "bin" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(f"#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '{version_output}'; exit 0; fi\ncat\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path.parent


def test_flag_default_off():
    assert TIERS_ENV == "BEAST_COMPRESSION_TIERS"
    assert tiers_enabled({}) is False and tiers_enabled({TIERS_ENV: "1"}) is True


def test_rtk_sqz_never_falsely_ready_without_identified_binary(tmp_path):
    status = detect_compressors(env={"PATH": str(tmp_path / "empty")})
    for name in ("rtk", "sqz"):
        assert status[name]["ready"] is False and status[name]["real_tool"] is False
        assert status[name]["fallback"] == "beast_native"
    impostor = _fake_binary(tmp_path, "rtk", "some other tool 1.0")
    status = detect_compressors(env={"PATH": str(impostor)})
    assert status["rtk"]["ready"] is False and status["rtk"]["reason"] == "binary_identity_unverified"


def test_identified_rtk_binary_reports_ready(tmp_path):
    bindir = _fake_binary(tmp_path, "rtk", "rtk 0.9.2")
    _fake_binary(tmp_path, "sqz", "sqz 1.4.0")
    status = detect_compressors(env={"PATH": str(bindir)})
    assert status["rtk"]["ready"] is True and status["rtk"]["version"] == "rtk 0.9.2"
    assert status["sqz"]["ready"] is True and status["rtk"]["real_tool"] is True
    assert status["longcodezip"]["real_tool"] is False and status["longcodezip"]["implementation"] == "beast_native"


def test_repo_map_symbols_resolve_and_rank_by_focus_and_imports(tmp_path):
    root = _repo(tmp_path)
    result = repo_map(root, focus=["compute_rate"], budget_tokens=400)
    assert result["fidelity"]["passed"] is True and result["fidelity"]["symbols_checked"] > 0
    first = result["entries"][0]
    assert first["file"] == "pkg/rates.py"  # most imported + focus hit
    names = [s["name"] for e in result["entries"] for s in e["symbols"]]
    assert "compute_rate" in names and "Ledger.append" in names
    for entry in result["entries"]:
        lines = (root / entry["file"]).read_text().splitlines()
        for symbol in entry["symbols"]:
            assert symbol["name"].split(".")[-1] in lines[symbol["line"] - 1]
    m = result["metrics"]
    assert m["compressed_tokens"] < m["original_tokens"] and m["savings_ratio"] > 0.3


def test_repo_map_respects_budget(tmp_path):
    root = _repo(tmp_path)
    tiny = repo_map(root, focus=[], budget_tokens=30)
    assert tiny["metrics"]["compressed_tokens"] <= 30 + 20  # one entry header slack


def test_long_code_compress_keeps_relevant_and_edit_targets_exact():
    result = long_code_compress(MODULE, query="fix compute_rate tax rounding", budget_ratio=0.5,
                                edit_targets=["balance"])
    out = result["content"]
    ast.parse(out)
    assert "def compute_rate(base: float, tax: float) -> float:\n    total = base" in out  # body kept exactly
    assert "return sum(float(r) for r in self.rows)" in out  # edit target body kept
    assert "def unrelated_helper(x):" in out and "w = z - 3" not in out  # stubbed signature
    assert result["fidelity"]["passed"] is True
    assert result["metrics"]["savings_ratio"] > 0.2


def test_long_code_compress_fidelity_failure_zeroes_savings():
    broken = "def f(:\n    pass\n" * 30
    result = long_code_compress(broken, query="f", budget_ratio=0.3)
    assert result["fidelity"]["passed"] is False
    assert result["content"] == broken and result["metrics"]["counted_savings_tokens"] == 0


def test_measure_counts_savings_only_with_fidelity():
    assert measure("a" * 400, "a" * 100, fidelity_passed=True)["counted_savings_tokens"] == 75
    assert measure("a" * 400, "a" * 100, fidelity_passed=False)["counted_savings_tokens"] == 0


def test_router_routes_every_tier_through_governor_with_receipt(tmp_path):
    root = _repo(tmp_path)
    governor = ComputeGovernorSpine(enforce=True)
    router = CompressionTierRouter(governor=governor, env={TIERS_ENV: "1", "PATH": str(tmp_path / "none")})
    out = router.compress("longcodezip", MODULE, query="compute_rate")
    assert out["governor"]["outcome"] == "admit" and out["governor"]["receipt_id"]
    assert out["tier"] == "longcodezip" and out["fidelity"]["passed"]
    rm = router.compress("repo_map", str(root), query="Ledger")
    assert rm["governor"]["receipt_id"] != out["governor"]["receipt_id"]
    rtk = router.compress("rtk", "line\nline\n\nFAILED tests/x.py::t - AssertionError\n", query="")
    assert rtk["backend"] in {"beast_native_rtk_stub", "passthrough"} and rtk["real_tool"] is False
    assert "FAILED tests/x.py::t - AssertionError" in rtk["content"]


def test_router_refuses_when_flag_off():
    with pytest.raises(PermissionError, match=TIERS_ENV):
        CompressionTierRouter(governor=ComputeGovernorSpine(enforce=True), env={}).compress("longcodezip", MODULE)


def test_economizer_applies_tiers_only_to_marked_messages_when_enabled(monkeypatch):
    from app.context.economizer import ContextEconomizer
    from app.kernel.compute.perceive import EdgeKIR

    msgs = [{"role": "user", "content": "fix compute_rate"},
            {"role": "user", "content": MODULE, "context_tier": "longcodezip", "tier_query": "compute_rate"},
            {"role": "user", "content": MODULE}]
    ir = EdgeKIR(messages=msgs, model="m")
    monkeypatch.delenv(TIERS_ENV, raising=False)
    off = ContextEconomizer().economize(ir)
    assert off.ir.messages[1]["content"] == MODULE
    monkeypatch.setenv(TIERS_ENV, "1")
    on = ContextEconomizer().economize(ir)
    assert on.ir.messages[1]["content"] != MODULE and on.ir.messages[2]["content"] == MODULE  # unmarked untouched
    tiers = on.ir.metadata["context_tiers"]
    assert tiers[0]["tier"] == "longcodezip" and tiers[0]["fidelity_passed"] is True
    assert tiers[0]["governor_receipt_id"]


def test_registry_refuses_impostor_rtk_when_tiers_flag_on(tmp_path, monkeypatch):
    from app.kernel.registry.tool_integrations import RequiredIntegrationRegistry

    impostor = tmp_path / "rtk"
    impostor.write_text("#!/bin/sh\necho 'some other tool 1.0'\n")
    impostor.chmod(0o755)
    monkeypatch.setattr("app.kernel.registry.tool_integrations.shutil.which",
                        lambda n: str(impostor) if n == "rtk" else None)
    monkeypatch.setenv(TIERS_ENV, "1")
    backend = next(b for b in RequiredIntegrationRegistry().compressor_status()["backends"] if b["name"] == "rtk")
    assert backend["ready"] is False
    monkeypatch.delenv(TIERS_ENV)
    backend = next(b for b in RequiredIntegrationRegistry().compressor_status()["backends"] if b["name"] == "rtk")
    assert backend["ready"] is True  # default-off: legacy behaviour unchanged


def test_quality_cascade_command_output_routes_through_governed_rtk_tier(tmp_path, monkeypatch):
    import sys

    from app.kernel.data_processing.quality_cascade import QualityCascade

    script = "print('ok'); print('FAILED tests/test_x.py::test_y - AssertionError')"
    monkeypatch.delenv(TIERS_ENV, raising=False)
    off = QualityCascade()._run_command([sys.executable, "-c", script], tmp_path, 20)
    assert "context_tier" not in off["output_compression"]
    monkeypatch.setenv(TIERS_ENV, "1")
    on = QualityCascade()._run_command([sys.executable, "-c", script], tmp_path, 20)
    tier = on["output_compression"]["context_tier"]
    assert tier["tier"] == "rtk" and tier["governor"]["outcome"] == "admit" and tier["governor"]["receipt_id"]
    assert tier["metrics"]["token_count_kind"] == "estimated_chars_div_4"
    assert "FAILED tests/test_x.py::test_y" in on["output_compact"]


# --- Real sqz (ojuschugh1/sqz, `sqz compress`) invocation contract -------------------------------------------
LOG = "\n".join(["INFO step ok"] * 40 + ["FAILED tests/test_x.py::test_y - AssertionError", "app/x.py:12: in f"])


def _recording_sqz(tmp_path, *, drop_failed=False):
    record = tmp_path / "argv.txt"
    body = "grep -v FAILED" if drop_failed else "awk '!seen[$0]++'"
    path = tmp_path / "sqz"
    path.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo 'sqz 2.2.0'; exit 0; fi\n"
                    f"echo \"$@|$SQZ_DB_PATH\" > {record}\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return record


def test_real_sqz_is_invoked_as_compress_without_dedup_and_isolated_db(tmp_path):
    record = _recording_sqz(tmp_path)
    router = CompressionTierRouter(governor=ComputeGovernorSpine(enforce=True),
                                   env={TIERS_ENV: "1", "PATH": str(tmp_path), "HOME": "/home/nobody"})
    out = router.compress("sqz", LOG)
    argv, db = record.read_text().strip().split("|")
    assert argv.split()[:1] == ["compress"] and "--no-cache" in argv.split() and "--no-abbrev" in argv.split()
    assert db and not db.startswith("/home/")
    assert out["backend"] == "sqz_binary" and out["real_tool"] is True and out["fidelity"]["passed"] is True
    assert out["metrics"]["counted_savings_tokens"] > 0


def test_real_sqz_dropping_a_failure_line_fails_fidelity(tmp_path):
    _recording_sqz(tmp_path, drop_failed=True)
    router = CompressionTierRouter(governor=ComputeGovernorSpine(enforce=True),
                                   env={TIERS_ENV: "1", "PATH": str(tmp_path)})
    out = router.compress("sqz", LOG)
    assert out["fidelity"]["passed"] is False and out["content"] == LOG
    assert out["metrics"]["counted_savings_tokens"] == 0


def test_tool_integrations_invokes_real_tools_with_their_subcommands(monkeypatch):
    import app.kernel.registry.tool_integrations as ti

    calls = []

    class Done:
        returncode, stdout = 0, "compressed"

    monkeypatch.setattr(ti.shutil, "which", lambda name: f"/opt/{name}")
    monkeypatch.setattr(ti.subprocess, "run", lambda argv, **kw: calls.append(argv) or Done())
    interceptor = ti.ToolCallInterceptor()
    interceptor.compress_text("x" * 200, "sqz")
    interceptor.compress_text("x" * 200, "rtk")
    assert calls[0][:2] == ["sqz", "compress"] and "--no-cache" in calls[0]
    assert calls[1] == ["rtk", "log"]


def test_real_tools_run_with_telemetry_blocked_and_kind_specific_sqz_formatter(tmp_path, monkeypatch):
    record = _recording_sqz(tmp_path)
    router = CompressionTierRouter(governor=ComputeGovernorSpine(enforce=True),
                                   env={TIERS_ENV: "1", "PATH": str(tmp_path)})
    router.compress("sqz", LOG, kind="lint")
    argv = record.read_text().split("|")[0].split()
    assert argv[argv.index("--cmd") + 1] == "ruff"
    rtk = tmp_path / "rtk"
    rtk.write_text(f"#!/bin/sh\necho \"$RTK_TELEMETRY_DISABLED\" > {tmp_path / 'rtk_env.txt'}\nhead -3\n")
    rtk.chmod(rtk.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    from app.kernel.data_processing.cascade_output_compressor import compress_cascade_output

    compress_cascade_output(LOG, kind="log")
    assert (tmp_path / "rtk_env.txt").read_text().strip() == "1"


def test_exact_lines_see_through_ansi_colour():
    from app.kernel.data_processing.cascade_output_compressor import exact_lines

    coloured = "\x1b[1mapp/main.py\x1b[0m\x1b[36m:\x1b[0m3805\x1b[36m:\x1b[0m9\x1b[36m:\x1b[0m \x1b[1m\x1b[31mB904\x1b[0m except"
    assert exact_lines("noise\n" + coloured) == [coloured]
