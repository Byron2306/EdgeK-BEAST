import json

import httpx

from app.kernel.compute.full_spectrum_crystallization_gauntlet import FullSpectrumCrystallizationGauntlet


def test_full_spectrum_gauntlet_records_reachability_and_skips_offline(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:0.5b"}]})
        return httpx.Response(404, json={})

    receipt = FullSpectrumCrystallizationGauntlet(
        tmp_path / "spectrum",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        run_live=False,
    ).run()

    assert receipt["beast_object_type"] == "full_spectrum_crystallization_gauntlet"
    assert receipt["engine_reachability"]["endpoints"]["local_ollama"]["configured"] is True
    assert receipt["scoreboard"]["row_count"] >= 4
    assert receipt["scoreboard"]["skipped"] >= 3
    assert (tmp_path / "spectrum" / "full_spectrum_crystallization_gauntlet.json").is_file()


def test_full_spectrum_scoreboard_shape(tmp_path):
    receipt = FullSpectrumCrystallizationGauntlet(
        tmp_path / "offline",
        run_live=False,
    ).run()

    scoreboard = receipt["scoreboard"]
    assert scoreboard["beast_object_type"] == "full_spectrum_scoreboard"
    assert "reviewer_safe_claim" in scoreboard
    assert set(scoreboard["reviewer_safe_claim"]) == {
        "multi_task",
        "multi_file_architecture",
        "replayable_baselines",
        "negative_controls",
        "zero_replay_engine_calls",
    }
