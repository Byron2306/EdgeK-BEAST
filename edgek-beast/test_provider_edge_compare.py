from benchmarks import provider_edge_compare as compare


def test_beast_messages_reduce_telemetry_prompt_shape():
    scenario = [item for item in compare.build_scenarios() if item["kind"] == "telemetry"][0]

    raw = compare.raw_messages(scenario)
    beast, metadata = compare.beast_messages(scenario)

    assert compare.estimate_tokens(beast) < compare.estimate_tokens(raw)
    assert metadata["governance"] == "edgek_beast_preprocessed"
    assert "isolation_forest" in metadata
    assert "ast_compression" in metadata


def test_provider_compare_dry_run_without_env(monkeypatch):
    for name in ("NVIDIA_API_KEY", "OPENROUTER_API_KEY", "LOCAL_NIM_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    report = compare.run_compare(dry_run=True)

    assert report["configured_providers"] == []
    assert len(report["scenarios"]) == 3
    assert "No provider calls executed" in report["summary"]["note"]
