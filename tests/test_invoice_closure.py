from app.kernel.networking.invoice_closure import EXPECTED_FAILURE_SIGNATURE, run_invoice_closure


def test_invoice_fixture_closes_through_governed_swarm(tmp_path):
    result = run_invoice_closure(root=str(tmp_path / "invoice-repo"))

    assert result["status"] == "passed"
    assert result["fixture"] == {
        "repository_files": 4,
        "selected_files": ["pricing.py", "invoice.py"],
        "primary_file": "pricing.py",
        "selected_symbol": "apply_discount",
    }
    assert result["baseline"]["failure_signature"] == EXPECTED_FAILURE_SIGNATURE
    assert result["residual"]["status"] == "solved"
    assert result["residual"]["provider_called"] is True
    assert result["residual"]["packet_body_matches_boundary"] is True
    assert result["residual"]["contribution_accounting"]["fields_supplied_by_beast"] == 7
    assert result["residual"]["contribution_accounting"]["fields_supplied_by_ollama"] == 1
    assert result["execution"]["mutation_applied"] is True
    assert result["verification"]["passed"] is True
    assert result["critic"]["passed"] is True
    assert result["archive"]["packet_hash"].startswith("sha256:")
    assert result["source_plan"]["status"] == "review_pending"
    assert result["source_plan"]["operator_decision"] == "pending"
    assert result["crystal_strengthening"]["assistance_mode"] == "advisory"
