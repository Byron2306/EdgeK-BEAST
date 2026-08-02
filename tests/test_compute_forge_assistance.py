from app.kernel.compute.compute_forge import ComputeForgeNode
from app.kernel.storage.durable_inference_storage import DurableInferenceStorage


def test_compute_forge_prepares_bounded_agent_assistance(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pricing.py").write_text("def apply_discount(amount, percent):\n    return amount - percent\n", encoding="utf-8")
    (repo / "invoice.py").write_text("from pricing import apply_discount\n", encoding="utf-8")
    node = ComputeForgeNode("forge-test", storage=DurableInferenceStorage(tmp_path / "storage"))

    receipt = node.prepare_agent_assistance(
        objective="repair percentage discount",
        workspace=str(repo),
        verifier_result={"ok": False, "stderr": "expected percent arithmetic"},
        target_paths=["pricing.py"],
        target_symbol="apply_discount",
        old="return amount - percent",
    )

    assert receipt["selected_file"] == "pricing.py"
    assert receipt["selected_symbol"] == "apply_discount"
    assert receipt["failure_classifier"]["family"] == "percentage arithmetic"
    assert receipt["patch_template"]["new"] == "<UNRESOLVED>"
    assert receipt["foreground_authority"] is False
    assert receipt["model_called"] is False
    assert receipt["assistance_digest"].startswith("sha256:")
