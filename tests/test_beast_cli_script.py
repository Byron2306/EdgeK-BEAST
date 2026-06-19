import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BEAST = ROOT / "bin" / "beast"


def run_beast(*args):
    return subprocess.run(
        [str(BEAST), *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )


def test_beast_agent_welcome_is_json():
    result = run_beast("--agent")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["service"] == "EdgeK BEAST CLI"
    assert "openclaw-plan" in payload["commands"]
    assert "scout" in payload["commands"]
    assert "diagnose" in payload["commands"]
    assert "route" in payload["commands"]
    assert "verify" in payload["commands"]
    assert "chronicle" in payload["commands"]
    assert "promote" in payload["commands"]
    assert "prec" in payload["commands"]
    assert "handoff-prepare" in payload["commands"]


def test_beast_mcp_config_uses_absolute_cli_path():
    result = run_beast("--agent", "mcp-config")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    server = payload["config"]["servers"]["edgek-beast"]
    assert server["type"] == "stdio"
    assert server["command"] == str(BEAST)
    assert server["args"][0] == "mcp"


def test_beast_doctor_reports_gateway_unavailable_without_failing():
    result = run_beast("--agent", "--gateway", "http://127.0.0.1:9", "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "doctor"
    assert payload["status"] == "attention"
    assert payload["gateway"]["ok"] is False


def test_beast_providers_prints_proxy_urls():
    result = run_beast("--agent", "--gateway", "http://127.0.0.1:8000", "providers")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["exports"]["OPENAI_BASE_URL"] == "http://127.0.0.1:8000/proxy/openai/v1"
    assert payload["exports"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8000/proxy/anthropic"


def test_beast_compressors_reports_builtin_fallback():
    result = run_beast("--agent", "compressors")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    backends = {item["name"]: item for item in payload["compressors"]["backends"]}
    assert backends["edgek_prune"]["ready"] is True
    assert backends["rtk"]["fallback"] == "edgek_builtin_prune"


def test_beast_zeroclaw_local_plan_is_planning_only():
    result = run_beast(
        "--agent",
        "zeroclaw-plan",
        "--local-only",
        "--use-ollama",
        "false",
        "--objective",
        "Plan a read-only repo inspection",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "zeroclaw"
    assert payload["ready"] is True
    assert payload["canon"]["valid"] is True
    assert payload["profile"]["default_execution"] == "planning_only"
    assert payload["actions"]
    assert all(action["risk"] == "advisory" for action in payload["actions"])


def test_beast_hermes_local_plan_binds_swarm_roles():
    result = run_beast(
        "--agent",
        "hermes-plan",
        "--local-only",
        "--use-ollama",
        "false",
        "--objective",
        "Coordinate swarm diagnosis",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "hermes"
    assert payload["ready"] is True
    assert payload["canon"]["valid"] is True
    assert payload["swarm_binding"]["available"] is True
    assert "planner" in payload["swarm_binding"]["roles"]


def test_beast_handoff_prepare_requires_task_markup():
    result = run_beast(
        "--agent",
        "handoff-prepare",
        "--local-only",
        "--persist-task",
        "false",
        "--objective",
        "Prepare cloud handoff without enough markup",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    assert payload["reason"] == "current_task_markup_required"
    assert "scope" in payload["current_task"]["missing"]


def test_beast_handoff_prepare_accepts_complete_task_markup():
    result = run_beast(
        "--agent",
        "handoff-prepare",
        "--local-only",
        "--persist-task",
        "false",
        "--objective",
        "Prepare provider diagnostic handoff",
        "--scope",
        "provider diagnostics",
        "--constraint",
        "local first",
        "--success-criteria",
        "ranked evidence included",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert payload["current_task"]["valid"] is True
    assert payload["insight_packet"]["ranked"] is True


def test_beast_cli_aliases_run_locally():
    diagnose = run_beast("--agent", "diagnose", "--local-only", "--provider", "huggingface", "--chronicle", "false")
    route = run_beast("--agent", "route", "--local-only", "--provider", "huggingface", "--persist", "false")
    verify = run_beast(
        "--agent",
        "verify",
        "--local-only",
        "--provider",
        "huggingface",
        "--objective",
        "Diagnose Hugging Face route failure",
    )
    promote = run_beast("--agent", "promote", "--local-only")

    assert diagnose.returncode == 0
    assert json.loads(diagnose.stdout)["provider"] == "huggingface"
    assert route.returncode == 0
    assert json.loads(route.stdout)["route_id"] == "route_provider_diagnostic_huggingface"
    assert verify.returncode == 0
    assert json.loads(verify.stdout)["beast_object_type"] == "quality_cascade_report"
    assert promote.returncode == 0
    assert json.loads(promote.stdout)["ready"] is False


def test_beast_prec_cli_runs_locally():
    started = run_beast(
        "--agent",
        "prec",
        "start",
        "--local-only",
        "--objective",
        "Track CLI PREC task",
        "--kind",
        "ide_session",
        "--scope",
        "workspace",
    )

    assert started.returncode == 0
    started_payload = json.loads(started.stdout)
    lifecycle_id = started_payload["lifecycle_id"]
    assert started_payload["command"] == "prec"
    assert started_payload["action"] == "start"

    advanced = run_beast(
        "--agent",
        "prec",
        "advance",
        "--local-only",
        lifecycle_id,
        "--phase",
        "perceive",
        "--summary",
        "CLI task marked up",
        "--signal",
        "cli_prec",
    )
    traced = run_beast("--agent", "prec", "trace", "--local-only", lifecycle_id)
    snapshot = run_beast("--agent", "prec", "snapshot", "--local-only", lifecycle_id, "--max-chars", "2200")

    assert advanced.returncode == 0
    assert traced.returncode == 0
    assert snapshot.returncode == 0
    trace_payload = json.loads(traced.stdout)
    assert trace_payload["lifecycle_id"] == lifecycle_id
    assert trace_payload["phase_events"][0]["phase"] == "perceive"
    snapshot_payload = json.loads(snapshot.stdout)
    assert snapshot_payload["beast_object_type"] == "prec_lifecycle_snapshot"
    assert snapshot_payload["compaction"]["omits_raw_payloads"] is True


def test_beast_scout_local_surfaces_operator_packet():
    result = run_beast(
        "--agent",
        "scout",
        "--local-only",
        "--use-ollama",
        "false",
        "--objective",
        "Diagnose provider circuit timeout",
        "--forensic-layer",
        "L3",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    packet = payload["packet"]
    assert payload["command"] == "scout"
    assert payload["source"] == "local"
    assert "ranked_chunks" in packet
    assert "chronicle_summary" in packet
    assert "fallback_recommendations" in packet
    assert "forensic_context" in packet


def test_beast_hermes_plan_can_attach_handoff_precheck():
    result = run_beast(
        "--agent",
        "hermes-plan",
        "--local-only",
        "--use-ollama",
        "false",
        "--persist-task",
        "false",
        "--objective",
        "Coordinate cloud handoff",
        "--scope",
        "provider diagnostics",
        "--success-criteria",
        "handoff precheck ready",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["mode"] == "hermes"
    assert payload["handoff_precheck"]["ready"] is True
    assert payload["handoff_precheck"]["current_task"]["valid"] is True
    assert payload["local_insight"]["available"] is True
    assert "ranked_chunks" in payload["local_inference"]
    assert "chronicle_summary" in payload["local_inference"]
    assert "fallback_recommendations" in payload["local_inference"]
    assert any(action["action_id"].startswith("inspect_insight") for action in payload["actions"])
