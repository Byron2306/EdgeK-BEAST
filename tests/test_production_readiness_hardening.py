import json

from app.kernel.readiness_hardening import ProductionReadinessHardeningGauntlet


def test_production_readiness_hardening_gauntlet_writes_executable_receipt(tmp_path):
    from scripts.production_ops_drill import main as ops_main
    from scripts.workload_frequency_pilot import main as workload_main

    ops_main()
    workload_main()
    report = ProductionReadinessHardeningGauntlet(tmp_path).run()

    assert report["beast_object_type"] == "beast_production_readiness_hardening_gauntlet"
    assert report["receipt_hash"].startswith("sha256:")
    assert report["summary"]["local_lab_hardened"] is True
    assert report["summary"]["production_claim_ready"] is True
    assert report["summary"]["blocked"] == []
    assert report["summary"]["needs_external_evidence"] == []

    latest = tmp_path / "production_readiness_hardening_latest.json"
    assert latest.is_file()
    persisted = json.loads(latest.read_text(encoding="utf-8"))
    assert persisted["receipt_hash"] == report["receipt_hash"]


def test_hardening_federation_gate_exercises_churn_and_tamper_rejection(tmp_path):
    gate = ProductionReadinessHardeningGauntlet(tmp_path).federation_durability_gate()

    assert gate["status"] == "satisfied"
    assert all(gate["checks"].values())
    assert gate["reputation"]["successful_reproductions"] == 1


def test_adapter_gate_keeps_lora_behavior_improvement_as_real_blocker(tmp_path):
    gate = ProductionReadinessHardeningGauntlet(tmp_path).adapter_proof_gate()

    assert gate["artifact_status"] == "satisfied"
    assert gate["status"] == "satisfied"
    assert gate["checks"]["adapter_remains_proposal_only"] is True
    assert gate["improvement_checks"]["lora_hidden_verifier_passes"] is True
