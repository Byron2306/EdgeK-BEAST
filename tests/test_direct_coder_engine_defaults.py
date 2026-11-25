from __future__ import annotations

from pathlib import Path

import pytest

from app.cli.coder_client import CoderRuntimeClient
from app.kernel.agents.direct_coder_defaults import (
    DIRECT_CODER_ENV_DEFAULTS,
    apply_direct_coder_env_defaults,
)


def test_client_defaults_to_direct_coder(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BEAST_TLI_ENGINE", raising=False)
    client = CoderRuntimeClient("http://127.0.0.1:9", tmp_path)
    assert client.engine == "direct_coder"


def test_client_typed_planner_engine_override(tmp_path: Path):
    client = CoderRuntimeClient("http://127.0.0.1:9", tmp_path, engine="typed_planner")
    assert client.engine == "typed_planner"


def test_apply_direct_coder_env_defaults_sets_unset_flags_only():
    environ = {"BEAST_DIRECT_CODER_THINKING": "0"}
    apply_direct_coder_env_defaults(environ)
    assert environ["BEAST_DIRECT_CODER_THINKING"] == "0"
    for key, value in DIRECT_CODER_ENV_DEFAULTS.items():
        if key != "BEAST_DIRECT_CODER_THINKING":
            assert environ[key] == value


@pytest.mark.asyncio
async def test_start_run_launch_strategy_follows_engine(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BEAST_TLI_ENGINE", raising=False)
    captured = []

    async def fake_post(self, path, payload):
        captured.append(payload)
        return {"ok": True, "run": {"run_id": "run-1", "state": "planning"}}

    monkeypatch.setattr(CoderRuntimeClient, "_post_json", fake_post)

    default_client = CoderRuntimeClient("http://127.0.0.1:9", tmp_path)
    await default_client.start_run("s", "add a helper to beast", "ollama", "qwen", mode="agent")
    planner = CoderRuntimeClient("http://127.0.0.1:9", tmp_path, engine="typed_planner")
    await planner.start_run("s", "add a helper to beast", "ollama", "qwen", mode="agent")
    analysis = CoderRuntimeClient("http://127.0.0.1:9", tmp_path)
    await analysis.start_run(
        "s",
        "read through the beast file and suggest any weak spots that require patching.",
        "ollama",
        "qwen",
        mode="agent",
    )

    assert captured[0]["request"]["launch_strategy"] == "direct_coder"
    assert captured[0]["mode"] == "agent"
    assert captured[1]["request"]["launch_strategy"] == "typed_planner"
    assert captured[2]["mode"] == "analysis"
    assert captured[2]["request"]["launch_strategy"] == "typed_planner"
    assert captured[2]["request"]["apply_on_completion"] is False
