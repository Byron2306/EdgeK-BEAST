import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.deployment import DeploymentManager
from app.main import app


def _policies():
    return {
        "meta_rules": {"runtime_provider_timeout_seconds": 120},
        "providers": {
            "openai": {
                "enabled": True,
                "base_url": "https://api.openai.com/v1",
                "default_model": "gpt-4o-mini",
                "rate_limit_rpm": 60,
                "rate_limit_tpm": 90000,
            },
            "google": {
                "enabled": True,
                "base_url": "https://generativelanguage.googleapis.com",
                "default_model": "gemini-2.5-flash",
                "rate_limit_rpm": 15,
            },
            "disabled": {"enabled": False, "default_model": "nope"},
        },
        "prompt_cache_keepalive": {"enabled": True},
    }


def test_litellm_config_generator_maps_enabled_providers(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    config = manager.generate_litellm_config(beast_base_url="http://beast.local")
    yaml_text = manager.generate_litellm_yaml(beast_base_url="http://beast.local")

    names = {item["model_name"] for item in config["model_list"]}
    assert "gpt-4o-mini" in names
    assert "gemini-flash" in names
    assert "nope" not in names
    assert "edgek_beast_middleware.preprocess_request" not in yaml_text
    assert config["litellm_settings"]["drop_params"] is True
    assert "http://beast.local" in yaml_text


def test_nginx_config_generator_routes_protocols(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    config = manager.generate_nginx_config(server_name="beast.local", listen_port=8088)

    assert "server_name beast.local;" in config
    assert "listen 8088;" in config
    assert "/v1/messages" in config
    assert "/v1/chat/completions" in config
    assert "generateContent" in config


def test_keepalive_requires_authorization_and_ticks_dry_run(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    with pytest.raises(ValueError):
        manager.register_keepalive(provider="google", model="gemini", cache_key="abc")

    registered = manager.register_keepalive(
        provider="google",
        model="gemini-2.5-flash",
        cache_key="large-prefix",
        interval_seconds=60,
        ttl_seconds=120,
        authorized=True,
        dry_run=True,
        cache_id="test-cache",
    )

    assert registered["cache_key_hash"] != "large-prefix"
    assert manager.keepalive_state()["active"] == 1

    with manager._connect() as conn:
        conn.execute("UPDATE prompt_cache_keepalives SET next_ping_at = 0 WHERE cache_id = ?", ("test-cache",))
    tick = manager.tick_keepalives()

    assert tick["processed"] == 1
    assert tick["events"][0]["status"] == "dry_run"
    assert manager.recent_keepalive_events()[0]["event_type"] == "ping"


@pytest.mark.asyncio
async def test_deploy_and_prompt_cache_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        litellm = await client.get("/edgek/deploy/litellm-config")
        nginx = await client.get("/edgek/deploy/nginx-config")
        rejected = await client.post(
            "/edgek/prompt-cache/keepalives",
            json={"provider": "google", "model": "gemini", "cache_key": "abc"},
        )

    assert litellm.status_code == 200
    assert litellm.json()["model_list"]
    assert nginx.status_code == 200
    assert "/v1/messages" in nginx.text
    assert rejected.status_code == 400
