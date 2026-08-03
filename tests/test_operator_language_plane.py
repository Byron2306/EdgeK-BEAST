from pathlib import Path
import subprocess

from app.kernel.compute.compute_plane import ComputePlane
from app.kernel.compute.operator_language import MeaningResolutionState
from app.kernel.compute.operator_language_plane import OperatorLanguagePlane
from app.kernel.networking.commons_spaces import build_manifest, build_reduction_receipt, write_space
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry


def _registry(path: Path) -> Path:
    registry = path / "services.yaml"
    registry.write_text(
        """
version: 1
services:
  reverse_proxy:
    port: 80
  beast:
    hostname: beast.test
    upstream: 127.0.0.1:8101
    port: 8101
    health_path: /health
    trust_domain: operator
  commons:
    hostname: commons.test
    upstream: 127.0.0.1:8601
    port: 8601
    health_path: /edgek/control-plane/commons
    trust_domain: commons
""".lstrip(),
        encoding="utf-8",
    )
    return registry


def test_operator_language_resolves_beast_endpoint_from_service_registry(tmp_path: Path):
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path))

    response = plane.answer("what endpoint is BEAST on?")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "service"
    assert response.receipt.bound_names == ("beast",)
    assert response.receipt.intent == "read_service_endpoint"
    assert response.receipt.service_names == ("beast",)
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False
    assert "127.0.0.1:8101" in response.output
    assert "http://127.0.0.1:8101/health" in response.output
    assert response.answer_frame is not None


def test_operator_language_resolves_commons_health_contract(tmp_path: Path):
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path))

    response = plane.answer({"utterance": "what is commons health endpoint?", "tone": "neutral"})

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.intent == "read_service_health"
    assert response.receipt.service_names == ("commons",)
    assert "http://127.0.0.1:8601/edgek/control-plane/commons" in response.output
    assert response.receipt.receipt_digest.startswith("sha256:")


def test_operator_language_names_ambiguity_instead_of_guessing_service(tmp_path: Path):
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path))

    response = plane.answer("what endpoint should I use?")

    assert response.receipt.state is MeaningResolutionState.AMBIGUOUS
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False
    assert "Ambiguous" in response.output
    assert "beast" in response.output
    assert "commons" in response.output
    assert response.answer_frame is None


def test_operator_language_refuses_actions_in_read_only_path(tmp_path: Path):
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path))

    response = plane.answer("restart beast now")

    assert response.receipt.state is MeaningResolutionState.UNSUPPORTED
    assert response.receipt.intent == "unsupported_action"
    assert response.receipt.service_names == ("beast",)
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False
    assert "no action was taken" in response.output.casefold()


def test_compute_plane_records_operator_language_receipt_without_provider_call(tmp_path: Path):
    plane = ComputePlane(root=tmp_path)

    response = plane.answer_operator_prompt("what is beast endpoint?", interface="test")
    report = plane.reachability_report()

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.provider_called is False
    assert report["components"]["operator_language_plane"] == "OperatorLanguagePlane"
    assert report["call_counters"]["operator_language.resolved"] == 1
    assert report["last_receipt_ids"]["operator_language"]


def test_operator_language_resolves_provider_model_from_provider_registry(tmp_path: Path):
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path), workspace_root=tmp_path)

    response = plane.answer("what model does ollama use?")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "model"
    assert response.receipt.bound_names == ("ollama",)
    assert response.receipt.intent == "read_model_provider"
    assert response.receipt.service_names == ("ollama",)
    assert response.receipt.provider_called is False
    assert "qwen" in response.output.casefold()
    assert "backend ollama" in response.output.casefold()


def test_operator_language_resolves_container_from_injected_runtime_inventory(tmp_path: Path):
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        container_snapshot_provider=lambda: (
            {"name": "beast-api", "image": "edgek/beast:local", "status": "running", "id": "abc123"},
        ),
    )

    response = plane.answer("show container beast-api")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "container"
    assert response.receipt.bound_names == ("beast-api",)
    assert response.receipt.intent == "read_container_state"
    assert response.receipt.provider_called is False
    assert "edgek/beast:local" in response.output
    assert "running" in response.output


def test_operator_language_reports_container_ambiguity_without_guessing(tmp_path: Path):
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        container_snapshot_provider=lambda: (
            {"name": "beast-api", "image": "edgek/beast:local"},
            {"name": "commons-api", "image": "edgek/commons:local"},
        ),
    )

    response = plane.answer("show containers")

    assert response.receipt.state is MeaningResolutionState.AMBIGUOUS
    assert response.receipt.domain.value == "container"
    assert response.receipt.bound_names == ("beast-api", "commons-api")
    assert "Name one container" in response.output


def test_operator_language_resolves_evidence_log_receipt(tmp_path: Path):
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    (evidence_root / "guardian-runtime-health.json").write_text(
        '{"status":"passed","services":{"beast":"healthy","commons":"healthy"}}\n',
        encoding="utf-8",
    )
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        evidence_root=evidence_root,
    )

    response = plane.answer("show guardian log")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "log"
    assert response.receipt.bound_names == ("guardian-runtime-health.json",)
    assert response.receipt.intent == "read_evidence_log"
    assert response.receipt.provider_called is False
    assert "status=passed" in response.output
    assert "services=beast,commons" in response.output


def test_operator_language_reports_repository_state_from_workspace(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "beast@example.local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=tmp_path, check=True)
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    subprocess.run(["git", "add", "app.py"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path), workspace_root=tmp_path)
    response = plane.answer("what repository branch is this workspace on?")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "repository"
    assert response.receipt.bound_names == ("active-repository",)
    assert response.receipt.intent == "read_repository_state"
    assert response.receipt.provider_called is False
    assert str(tmp_path) in response.output
    assert "changed paths" in response.output


def test_operator_language_reports_file_state_without_reading_outside_workspace(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app").mkdir()
    (workspace / "app" / "main.py").write_text("print('beast')\n", encoding="utf-8")
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path), workspace_root=workspace)

    response = plane.answer("does file app/main.py exist?")
    escape = plane.answer("does file app/../../secrets.env exist?")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "file"
    assert response.receipt.bound_names == ("app/main.py",)
    assert response.receipt.intent == "read_file_state"
    assert response.receipt.service_names == ("app/main.py",)
    assert "app/main.py is present" in response.output
    assert escape.receipt.state is MeaningResolutionState.AMBIGUOUS
    assert "escapes the workspace" in escape.output


def test_operator_language_preserves_case_sensitive_file_paths(tmp_path: Path):
    workspace = tmp_path / "workspace"
    target = workspace / "Config" / "Production.JSON"
    target.parent.mkdir(parents=True)
    target.write_text('{"mode":"prod"}\n', encoding="utf-8")
    plane = OperatorLanguagePlane(registry_path=_registry(tmp_path), workspace_root=workspace)

    response = plane.answer("does file Config/Production.JSON exist?")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.bound_names == ("Config/Production.JSON",)
    assert "Config/Production.JSON is present" in response.output


def test_operator_language_handles_empty_commons_space_catalog_without_cloud_claims(tmp_path: Path):
    commons_root = tmp_path / "commons"
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        commons_registry=CommonsSpaceRegistry(root=commons_root),
    )

    response = plane.answer("show commons spaces")

    assert response.receipt.state is MeaningResolutionState.UNSUPPORTED
    assert response.receipt.domain.value == "space"
    assert response.receipt.bound_names == ()
    assert response.receipt.intent == "read_commons_space"
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False
    assert "No local Commons Spaces are registered" in response.output


def test_operator_language_reports_commons_space_detail_without_promoting_hypothesis(tmp_path: Path):
    registry = _space_registry_with_demo_space(tmp_path)
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        commons_registry=registry,
    )

    response = plane.answer("show demo_space commons space details")

    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.receipt.domain.value == "space"
    assert response.receipt.bound_names == ("demo_space",)
    assert response.answer_frame is not None
    assert response.answer_frame.slots["artifact_count"] == 1
    assert response.answer_frame.slots["provider_calls_avoided"] == 2
    assert response.answer_frame.slots["reproduction_count"] == 0
    assert "remain hypotheses" in response.output
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False


def test_operator_language_reports_commons_reproduction_state_read_only(tmp_path: Path):
    registry = _space_registry_with_demo_space(tmp_path)
    reproduction = registry.replay("demo_space")
    plane = OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=tmp_path,
        commons_registry=registry,
    )

    response = plane.answer("show demo_space reproduction trust")

    assert reproduction["reproduced"] is True
    assert response.receipt.state is MeaningResolutionState.RESOLVED
    assert response.answer_frame is not None
    assert response.answer_frame.slots["reproduction_count"] == 1
    assert response.answer_frame.slots["best_reproduction_trust_class"] == "integrity_reproduced"
    assert response.answer_frame.slots["best_reproduction_trust_score"] >= 0.75
    assert "1 reproduction receipt" in response.output
    assert "integrity_reproduced" in response.output
    assert response.receipt.provider_called is False
    assert response.receipt.action_taken is False


def _space_registry_with_demo_space(tmp_path: Path) -> CommonsSpaceRegistry:
    registry = CommonsSpaceRegistry(root=tmp_path / "commons")
    root = registry.root / "demo_space"
    root.mkdir(parents=True)
    (root / "evidence.json").write_text('{"verified": true}\n', encoding="utf-8")
    manifest = build_manifest(
        root,
        space_id="demo_space",
        name="Demo Space",
        task_class="operator_language_demo",
        artifacts=[{"path": "evidence.json", "artifact_type": "evidence"}],
        hardware_profile={"gpu_required": False},
        verifier_bundles=[],
        reduction_claims={"provider_calls_avoided": 2},
        safety={"approval_required": True, "promotion_state": "quarantined_hypothesis"},
    )
    receipt = build_reduction_receipt(
        space_manifest=manifest,
        baseline_route={"route_id": "provider"},
        optimized_route={"route_id": "local"},
        displacement={"provider_calls_avoided": 2},
        verifier={"passed": True},
        resource_deltas={"gpu_avoided": True},
        provenance={"source": "operator-language-test"},
        rollback_available=True,
        approval_required=True,
    )
    write_space(root, manifest, receipt)
    return registry
