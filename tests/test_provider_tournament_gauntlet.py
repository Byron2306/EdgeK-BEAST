import httpx

import app.kernel.compute.provider_tournament_gauntlet as tournament_module
from app.kernel.compute.provider_tournament_gauntlet import ProviderTournamentGauntlet
from app.kernel.registry.provider_registry import ProviderRegistry
from app.kernel.security.secret_vault import SecretVault


def _empty_vault(tmp_path):
    return SecretVault(str(tmp_path / "missing_provider_secrets.env"))


def _clear_registry_env(monkeypatch):
    for record in ProviderRegistry().records(include_disabled=True):
        for name in record.env:
            monkeypatch.delenv(name, raising=False)
    for name in ("GOOGLE_API_KEY", "NVIDIA_NIM_BASE_URL", "OLLAMA_BASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_provider_tournament_covers_every_registry_provider_offline(tmp_path, monkeypatch):
    _clear_registry_env(monkeypatch)

    receipt = ProviderTournamentGauntlet(
        tmp_path / "tournament",
        run_live=False,
        secret_vault=_empty_vault(tmp_path),
    ).run()
    registry_ids = {record.provider_id for record in ProviderRegistry().records(include_disabled=True)}
    inventory_ids = {row["provider_id"] for row in receipt["provider_inventory_rows"]}
    tournament_ids = {row["provider_id"] for row in receipt["tournament_rows"]}

    assert receipt["beast_object_type"] == "provider_tournament_gauntlet"
    assert inventory_ids == registry_ids
    assert tournament_ids == registry_ids
    assert receipt["scoreboard"]["reviewer_safe_claims"]["all_registry_providers_have_inventory_rows"] is True
    assert receipt["scoreboard"]["reviewer_safe_claims"]["all_registry_providers_have_tournament_rows"] is True
    assert (tmp_path / "tournament" / "provider_tournament_gauntlet.json").is_file()


def test_provider_tournament_smoke_only_mocked_ollama_google_openai(tmp_path, monkeypatch):
    _clear_registry_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "test-google-key")

    def handler(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen2.5:0.5b"}]})
        if "generativelanguage.googleapis.com" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "BEAST_PROVIDER_TOURNAMENT_OK:google:return a + b"}
                                ]
                            }
                        }
                    ],
                    "usageMetadata": {"totalTokenCount": 12},
                },
            )
        if "api.openai.com" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "BEAST_PROVIDER_TOURNAMENT_OK:openai:return a + b"
                            }
                        }
                    ],
                    "usage": {"total_tokens": 10},
                },
            )
        return httpx.Response(404, json={"error": {"message": "unmocked"}})

    receipt = ProviderTournamentGauntlet(
        tmp_path / "mocked",
        run_live=True,
        run_deep_crystallization=False,
        secret_vault=_empty_vault(tmp_path),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).run()

    rows = {row["provider_id"]: row for row in receipt["tournament_rows"]}
    assert rows["ollama"]["status"] == "passed"
    assert rows["google"]["status"] == "passed"
    assert rows["openai"]["status"] == "passed"
    assert rows["nvidia_nim"]["status"] == "skipped"
    assert receipt["scoreboard"]["covered_provider_count"] == receipt["scoreboard"]["provider_count"]


def test_provider_tournament_records_litellm_runtime_gap(tmp_path, monkeypatch):
    _clear_registry_env(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setattr(tournament_module.importlib.util, "find_spec", lambda name: None if name == "litellm" else object())

    receipt = ProviderTournamentGauntlet(
        tmp_path / "litellm-gap",
        run_live=True,
        run_deep_crystallization=False,
        secret_vault=_empty_vault(tmp_path),
    ).run()
    rows = {row["provider_id"]: row for row in receipt["tournament_rows"]}

    assert rows["groq"]["test"] == "litellm_completion_smoke"
    assert rows["groq"]["status"] == "skipped"
    assert rows["groq"]["reason"] == "litellm_runtime_not_installed"
