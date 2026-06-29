import importlib
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.compute.crystal_distillation import (
    CrystalToAdapterDistiller,
    privacy_scan_training_row,
    validate_agent_awareness_proposal,
)


def write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def test_phase7_builds_lattice_dataset_and_candidate(tmp_path):
    results = tmp_path / "results"
    write_jsonl(results / "run_a" / "crystallization_events.jsonl", [
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": "schema_validation_o03_v1",
            "impact_fingerprint_hash": "sha256:" + "a" * 64,
            "provider": "groq",
            "source_provider": "nvidia_nim",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        },
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "provider_alias_normalization",
            "task_id": "provider_alias_normalization_o03_v1",
            "impact_fingerprint_hash": "sha256:" + "b" * 64,
            "provider": "cohere",
            "source_provider": "mistral",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        },
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": "schema_validation_fail_v1",
            "impact_fingerprint_hash": "sha256:" + "c" * 64,
            "provider": "local",
            "state": "failed",
            "occurrence": 1,
        },
    ])
    report = CrystalToAdapterDistiller(results_root=results, output_root=tmp_path / "phase7").harvest()

    assert report["beast_object_type"] == "crystal_to_adapter_distillation_report"
    assert report["signal_count"] == 3
    assert report["task_family_count"] == 2
    assert report["dataset"]["row_count"] == 3
    assert report["dataset"]["public_export_allowed"] is False
    assert report["adapter_candidate"]["authority"] == "proposal_only"
    assert report["adapter_candidate"]["credit_eligible"] is False
    assert report["mutation_suite"]["checks"]
    assert Path(report["dataset"]["dataset_path"]).is_file()


def test_crystal_lora_lattice_trains_real_parameter_matrices(tmp_path):
    results = tmp_path / "results"
    write_jsonl(results / "run_a" / "crystallization_events.jsonl", [
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": "schema_1",
            "impact_fingerprint_hash": "sha256:" + "a" * 64,
            "provider": "groq",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        },
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "route_diagnostics",
            "task_id": "route_1",
            "impact_fingerprint_hash": "sha256:" + "b" * 64,
            "provider": "local",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        },
    ])
    distiller = CrystalToAdapterDistiller(results_root=results, output_root=tmp_path / "phase7")
    distiller.harvest()
    receipt = distiller.train_crystal_lora_lattice(dimension=64, rank=4, epochs=5, learning_rate=0.1)
    sft = distiller.export_sft_training_package()

    assert receipt["beast_object_type"] == "crystal_lora_lattice_training_receipt"
    assert receipt["parameter_shapes"]["lora_A"] == [64, 4]
    assert receipt["parameter_shapes"]["lora_B"][0] == 4
    assert receipt["parameter_shapes"]["delta_W"][0] == 64
    assert Path(receipt["weights_path"]).is_file()
    assert sft["row_count"] == 2
    assert Path(sft["path"]).is_file()


def test_true_lora_package_export_is_peft_ready(tmp_path):
    results = tmp_path / "results"
    write_jsonl(results / "run_a" / "crystallization_events.jsonl", [
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": "schema_1",
            "impact_fingerprint_hash": "sha256:" + "a" * 64,
            "provider": "groq",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        }
    ])
    distiller = CrystalToAdapterDistiller(results_root=results, output_root=tmp_path / "phase7")
    distiller.harvest()
    manifest = distiller.export_true_lora_package(base_model_name="Qwen/Qwen2.5-0.5B-Instruct", rank=2, max_rows=10)
    package_dir = Path(manifest["package_dir"])

    assert manifest["beast_object_type"] == "true_lora_training_package"
    assert package_dir.joinpath("adapter_config.json").is_file()
    assert package_dir.joinpath("training_args.json").is_file()
    assert package_dir.joinpath("requirements.txt").is_file()
    config = json.loads(package_dir.joinpath("adapter_config.json").read_text(encoding="utf-8"))
    assert config["peft_type"] == "LORA"
    assert config["r"] == 2
    assert "q_proj" in config["target_modules"]


def test_distillation_training_row_privacy_scan_blocks_raw_private_content():
    scan = privacy_scan_training_row({
        "task_family": "bad",
        "raw_prompt": "please inspect /home/byron/private/project",
    })
    assert scan["passed"] is False
    assert scan["violation_count"] >= 1


def test_agent_awareness_validator_requires_beast_system_linkage():
    valid = validate_agent_awareness_proposal({
        "beast_object_type": "adapter_assisted_local_proposal",
        "task_family": "route_diagnostics",
        "task_envelope": {},
        "prec_stage": "reason",
        "beast_systems_used": ["compute_governor", "commons_spaces", "compute_forge", "chronicle"],
        "agent_awareness": {"linked": True, "authority": "proposal_only", "must_use_beast_systems": True},
        "authority": "proposal_only",
    })
    invalid = validate_agent_awareness_proposal({
        "authority": "proposal_only",
        "agent_awareness": {"linked": True, "authority": "proposal_only", "must_use_beast_systems": False},
        "beast_systems_used": ["compute_governor"],
    })
    assert valid["passed"] is True
    assert invalid["passed"] is False
    assert "agent_awareness.must_use_beast_systems_must_be_true" in invalid["violations"]


@pytest.mark.asyncio
async def test_phase7_api_build(monkeypatch, tmp_path):
    main = importlib.import_module("app.main")
    results = tmp_path / "results"
    output = tmp_path / "phase7"
    write_jsonl(results / "run_a" / "crystallization_events.jsonl", [
        {
            "beast_object_type": "mega_crystallization_event",
            "family": "schema_validation",
            "task_id": "schema_validation_o03_v1",
            "impact_fingerprint_hash": "sha256:" + "d" * 64,
            "provider": "groq",
            "state": "crystallized",
            "occurrence": 3,
            "cross_provider_reuse": True,
        }
    ])
    monkeypatch.setattr(main, "crystal_to_adapter_distiller", CrystalToAdapterDistiller(results_root=results, output_root=output))

    async with AsyncClient(transport=ASGITransport(app=main.app), base_url="http://test") as client:
        built = await client.post("/edgek/proof-local/distillation/build", json={
            "results_root": str(results),
            "output_root": str(output),
            "limit": 20,
        })
        latest = await client.get("/edgek/proof-local/distillation")
        dataset = await client.get("/edgek/proof-local/distillation/dataset", params={"limit": 5})

    assert built.status_code == 200
    assert built.json()["signal_count"] == 1
    assert latest.status_code == 200
    assert latest.json()["adapter_candidate"]["authority"] == "proposal_only"
    assert dataset.status_code == 200
    assert dataset.json()["public_export_allowed"] is False
