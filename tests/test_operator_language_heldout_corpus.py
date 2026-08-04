from pathlib import Path
import subprocess

import pytest

from app.kernel.compute.operator_language import MeaningResolutionState, OperatorMeaningDomain
from app.kernel.compute.operator_language_acceptance import (
    HeldOutOperatorPromptCase,
    failures_by_case,
    run_held_out_operator_corpus,
)
from app.kernel.compute.operator_language_plane import OperatorLanguagePlane
from app.kernel.networking.commons_spaces import build_manifest, build_reduction_receipt, write_space
from app.kernel.registry.commons_space_registry import CommonsSpaceRegistry


def test_held_out_operator_prompt_corpus_has_zero_provider_calls_actions_or_mismatches(tmp_path: Path):
    plane = _heldout_plane(tmp_path)
    cases = _heldout_cases()

    receipt = run_held_out_operator_corpus(plane, cases, minimum_cases=40)

    assert receipt.case_count == len(cases)
    assert receipt.passed is True, failures_by_case(receipt)
    assert receipt.provider_calls == 0
    assert receipt.actions_taken == 0
    assert receipt.failed_count == 0
    assert receipt.receipt_digest.startswith("sha256:")


def test_held_out_operator_corpus_enforces_minimum_size(tmp_path: Path):
    plane = _heldout_plane(tmp_path)

    with pytest.raises(ValueError, match="at least 40 cases"):
        run_held_out_operator_corpus(plane, _heldout_cases()[:3], minimum_cases=40)


def _heldout_plane(tmp_path: Path) -> OperatorLanguagePlane:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    subprocess.run(["git", "init"], cwd=workspace, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    subprocess.run(["git", "config", "user.email", "beast@example.local"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "BEAST Test"], cwd=workspace, check=True)
    (workspace / "app").mkdir()
    (workspace / "app" / "main.py").write_text("print('beast')\n", encoding="utf-8")
    (workspace / "docs").mkdir()
    (workspace / "docs" / "plan.md").write_text("# Plan\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "heldout"], cwd=workspace, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    (workspace / "scratch.py").write_text("dirty = True\n", encoding="utf-8")

    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    (evidence_root / "guardian-runtime-health.json").write_text(
        '{"status":"passed","services":{"beast":"healthy","commons":"healthy"}}\n',
        encoding="utf-8",
    )
    (evidence_root / "synthesis-route.json").write_text(
        '{"final_status":"verified","health":{"operator_language":"passed"}}\n',
        encoding="utf-8",
    )

    return OperatorLanguagePlane(
        registry_path=_registry(tmp_path),
        workspace_root=workspace,
        commons_registry=_commons_registry(tmp_path),
        evidence_root=evidence_root,
        container_snapshot_provider=lambda: (
            {"name": "beast-api", "image": "edgek/beast:local", "status": "running", "id": "abc123"},
            {"name": "commons-api", "image": "edgek/commons:local", "status": "running", "id": "def456"},
        ),
    )


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
  arda:
    hostname: arda.test
    upstream: 127.0.0.1:18401
    port: 18401
    health_path: /docs
    trust_domain: witness
""".lstrip(),
        encoding="utf-8",
    )
    return registry


def _commons_registry(tmp_path: Path) -> CommonsSpaceRegistry:
    registry = CommonsSpaceRegistry(root=tmp_path / "commons")
    for space_id, calls in (("demo_space", 2), ("vision_space", 1)):
        root = registry.root / space_id
        root.mkdir(parents=True)
        (root / "evidence.json").write_text('{"verified": true}\n', encoding="utf-8")
        manifest = build_manifest(
            root,
            space_id=space_id,
            name=space_id.replace("_", " ").title(),
            task_class="operator_language_demo",
            artifacts=[{"path": "evidence.json", "artifact_type": "evidence"}],
            hardware_profile={"gpu_required": False},
            verifier_bundles=[],
            reduction_claims={"provider_calls_avoided": calls},
            safety={"approval_required": True, "promotion_state": "quarantined_hypothesis"},
        )
        receipt = build_reduction_receipt(
            space_manifest=manifest,
            baseline_route={"route_id": "provider"},
            optimized_route={"route_id": "local"},
            displacement={"provider_calls_avoided": calls},
            verifier={"passed": True},
            resource_deltas={"gpu_avoided": True},
            provenance={"source": "heldout-operator-corpus"},
            rollback_available=True,
            approval_required=True,
        )
        write_space(root, manifest, receipt)
    registry.replay("demo_space")
    return registry


def _case(
    case_id: str,
    utterance: str,
    domain: OperatorMeaningDomain,
    intent: str,
    state: MeaningResolutionState,
    names: tuple[str, ...] = (),
    contains: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
) -> HeldOutOperatorPromptCase:
    return HeldOutOperatorPromptCase(
        case_id=case_id,
        utterance=utterance,
        expected_domain=domain,
        expected_intent=intent,
        expected_state=state,
        expected_bound_names=names,
        must_contain=contains,
        must_not_contain=excludes,
    )


def _heldout_cases() -> tuple[HeldOutOperatorPromptCase, ...]:
    S = OperatorMeaningDomain.SERVICE
    M = OperatorMeaningDomain.MODEL
    C = OperatorMeaningDomain.CONTAINER
    L = OperatorMeaningDomain.LOG
    R = OperatorMeaningDomain.REPOSITORY
    F = OperatorMeaningDomain.FILE
    P = OperatorMeaningDomain.SPACE
    RES = MeaningResolutionState.RESOLVED
    AMB = MeaningResolutionState.AMBIGUOUS
    UNS = MeaningResolutionState.UNSUPPORTED
    return (
        _case("svc-001", "where is beast listening", S, "read_service_endpoint", RES, ("beast",), ("8101",)),
        _case("svc-002", "beast endpoint please", S, "read_service_endpoint", RES, ("beast",), ("127.0.0.1:8101",)),
        _case("svc-003", "what is commons health", S, "read_service_health", RES, ("commons",), ("8601",)),
        _case("svc-004", "arda health check", S, "read_service_health", RES, ("arda",), ("18401",)),
        _case("svc-005", "what endpoint should i use", S, "read_service_endpoint", AMB, (), ("Ambiguous", "beast")),
        _case("svc-006", "show service registry", S, "summarize_service_registry", RES, ("beast", "commons", "arda"), ("BEAST service registry",)),
        _case("safe-001", "restart beast right now", S, "unsupported_action", UNS, ("beast",), ("no action was taken",), ("restarted",)),
        _case("safe-002", "delete commons service", S, "unsupported_action", UNS, ("commons",), ("no action was taken",), ("deleted",)),
        _case("model-001", "what model does ollama use", M, "read_model_provider", RES, ("ollama",), ("backend ollama",)),
        _case("model-002", "provider codex model", M, "read_model_provider", RES, ("codex",), ("gpt-5-codex",)),
        _case("model-003", "hf provider backend", M, "read_model_provider", RES, ("huggingface",), ("huggingface",)),
        _case("model-004", "local-nim model lane", M, "read_model_provider", RES, ("local_nim",), ("local-nim-model",)),
        _case("model-005", "show providers", M, "read_model_provider", AMB, ("ollama", "codex", "openai", "huggingface", "nvidia_nim"), ("Name one provider",)),
        _case("model-006", "nvidia provider model", M, "read_model_provider", RES, ("nvidia_nim",), ("nvidia",)),
        _case("ctr-001", "container beast-api status", C, "read_container_state", RES, ("beast-api",), ("running",)),
        _case("ctr-002", "show commons-api docker image", C, "read_container_state", RES, ("commons-api",), ("edgek/commons:local",)),
        _case("ctr-003", "show containers", C, "read_container_state", AMB, ("beast-api", "commons-api"), ("Name one container",)),
        _case("ctr-004", "image beast-api", C, "read_container_state", RES, ("beast-api",), ("edgek/beast:local",)),
        _case("log-001", "guardian log please", L, "read_evidence_log", RES, ("guardian-runtime-health.json",), ("status=passed",)),
        _case("log-002", "show synthesis evidence receipt", L, "read_evidence_log", RES, ("synthesis-route.json",), ("operator_language",)),
        _case("log-003", "latest evidence log", L, "read_evidence_log", RES, ("synthesis-route.json",), ("verified",)),
        _case("repo-001", "what git branch is this", R, "read_repository_state", RES, ("active-repository",), ("changed paths",)),
        _case("repo-002", "workspace repository status", R, "read_repository_state", RES, ("active-repository",), ("Repository",)),
        _case("repo-003", "repo commit", R, "read_repository_state", RES, ("active-repository",), ("commit",)),
        _case("repo-004", "worktree state", R, "read_repository_state", RES, ("active-repository",), ("changed paths",)),
        _case("file-001", "does file app/main.py exist", F, "read_file_state", RES, ("app/main.py",), ("present",)),
        _case("file-002", "file docs/plan.md state", F, "read_file_state", RES, ("docs/plan.md",), ("present",)),
        _case("file-003", "file missing.py exists", F, "read_file_state", RES, ("missing.py",), ("missing",)),
        _case("file-004", "file app/../../secret.env exists", F, "read_file_state", AMB, (), ("escapes the workspace",)),
        _case("file-005", "file .git/config exists", F, "read_file_state", AMB, (), ("git metadata",)),
        _case("space-001", "show demo_space commons space details", P, "read_commons_space", RES, ("demo_space",), ("provider calls avoided 2", "remain hypotheses")),
        _case("space-002", "demo_space reproduction trust", P, "read_commons_space", RES, ("demo_space",), ("integrity_reproduced",)),
        _case("space-003", "vision_space commons package", P, "read_commons_space", RES, ("vision_space",), ("provider calls avoided 1",)),
        _case("space-004", "show commons spaces", P, "read_commons_space", AMB, (), ("Name one Commons space",)),
        _case("space-005", "unknown_space commons trust", P, "read_commons_space", AMB, (), ("Name one Commons space",)),
        _case("unsupported-001", "what is the weather in chicago", S, "unsupported_query", UNS, (), ("Unsupported",)),
        _case("unsupported-002", "explain quantum networking", S, "unsupported_query", UNS, (), ("Unsupported",)),
        _case("unsupported-003", "summon the beast mascot", S, "unsupported_query", UNS, (), ("Unsupported",)),
        _case("safe-003", "publish demo_space commons package", S, "unsupported_action", UNS, ("commons",), ("no action was taken",), ("published",)),
        _case("safe-004", "run replay for demo_space", S, "unsupported_action", UNS, (), ("no action was taken",)),
        _case("safe-005", "kill container beast-api", S, "unsupported_action", UNS, (), ("no action was taken",), ("killed",)),
        _case("safe-006", "deploy provider codex", S, "unsupported_action", UNS, (), ("no action was taken",), ("deployed",)),
    )
