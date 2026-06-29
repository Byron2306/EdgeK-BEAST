from __future__ import annotations

from pathlib import Path

import pytest

from app.kernel.data_processing.generative_crystals import GenerativeCrystalStore, run_phase5_generative_crystal_gauntlet


def _context() -> dict:
    return {
        "task_family": "route_diagnostics",
        "repository_fingerprint": "sha256:repo",
        "tool_schema_fingerprint": "sha256:tools",
        "policy_fingerprint": "sha256:policy",
    }


def _register(store: GenerativeCrystalStore) -> str:
    context = _context()
    result = store.register_template(
        task_family="route_diagnostics",
        boundary={
            "task_family": context["task_family"],
            "repository_fingerprint": context["repository_fingerprint"],
            "tool_schema_fingerprint": context["tool_schema_fingerprint"],
            "policy_fingerprint": context["policy_fingerprint"],
        },
        required_parameters=["task_id", "task_family", "verifier"],
        action_ir_template={"route": "local_verifier_first", "task_id": "{{task_id}}", "family": "{{task_family}}"},
        verifier_plan=["provider_fitness_check", "{{verifier}}"],
        rollback_template={"rollback_action": "discard_instantiation", "task_id": "{{task_id}}"},
        approval_required=True,
        risk_class="medium",
        source_evidence_hash="sha256:evidence",
    )
    assert result["validation"]["valid"] is True
    return result["template"]["template_id"]


def test_generative_crystal_instantiates_and_renders_verifier_plan(tmp_path: Path) -> None:
    store = GenerativeCrystalStore(tmp_path)
    template_id = _register(store)
    inst = store.instantiate(
        template_id,
        parameters={"task_id": "a", "task_family": "route_diagnostics", "verifier": "schema_validation"},
        context=_context(),
    )
    assert inst["hit"] is True
    payload = inst["instantiation"]
    assert payload["action_ir"]["task_id"] == "a"
    assert payload["verifier_plan"] == ["provider_fitness_check", "schema_validation"]
    assert payload["approval_required"] is True
    assert payload["rollback"]["rollback_action"] == "discard_instantiation"


def test_generative_crystal_boundary_mutation_misses(tmp_path: Path) -> None:
    store = GenerativeCrystalStore(tmp_path)
    template_id = _register(store)
    context = dict(_context(), tool_schema_fingerprint="sha256:mutated")
    miss = store.instantiate(
        template_id,
        parameters={"task_id": "a", "task_family": "route_diagnostics", "verifier": "schema_validation"},
        context=context,
    )
    assert miss["hit"] is False
    assert miss["reason"] == "boundary_hash_mismatch"


def test_generative_crystal_false_hits_demote_and_trigger_credit_reversal(tmp_path: Path) -> None:
    store = GenerativeCrystalStore(tmp_path, false_hit_threshold=2)
    template_id = _register(store)
    inst = store.instantiate(
        template_id,
        parameters={"task_id": "bad", "task_family": "route_diagnostics", "verifier": "schema_validation"},
        context=_context(),
    )
    first = store.record_verifier_result(inst["instantiation"], verifier_results={"provider_fitness_check": True, "schema_validation": False})
    second = store.record_verifier_result(inst["instantiation"], verifier_results={"provider_fitness_check": False, "schema_validation": False})
    assert first["template_state"] != "demoted"
    assert second["template_state"] == "demoted"
    assert second["credit_reversal_required"] is True
    with pytest.raises(ValueError, match="template is not valid"):
        store.instantiate(
            template_id,
            parameters={"task_id": "later", "task_family": "route_diagnostics", "verifier": "schema_validation"},
            context=_context(),
        )


def test_phase5_gauntlet_exit_criteria(tmp_path: Path) -> None:
    receipt = run_phase5_generative_crystal_gauntlet(store=GenerativeCrystalStore(tmp_path))
    assert receipt["status"] == "implemented"
    assert all(receipt["exit_criteria"].values())
