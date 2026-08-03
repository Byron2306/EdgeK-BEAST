import pytest
from httpx import ASGITransport, AsyncClient

from app.kernel.deployment.deployment import DeploymentManager
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
            "openrouter": {
                "enabled": True,
                "backend": "litellm",
                "default_model": "openrouter/meta-llama/llama-3.1-8b-instruct",
                "env": "OPENROUTER_API_KEY",
            },
            "ollama": {
                "enabled": True,
                "backend": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "default_model": "llama3.2:3b",
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
    assert config["edgek_beast"]["provider_registry"] == "http://beast.local/edgek/providers/registry"
    assert config["edgek_beast"]["governance"].startswith("BEAST remains")
    assert "http://beast.local" in yaml_text
    models = {item["model_name"]: item["litellm_params"] for item in config["model_list"]}
    assert models["llama3.2:3b"]["model"] == "ollama/llama3.2:3b"
    assert models["llama3.2:3b"]["api_base"] == "http://127.0.0.1:11434"
    assert "api_key" not in models["llama3.2:3b"]
    assert "mcp_servers" not in config


def test_nginx_config_generator_routes_protocols(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    config = manager.generate_nginx_config(server_name="beast.local", listen_port=8088)

    assert "server_name beast.local;" in config
    assert "listen 8088;" in config
    assert "/v1/messages" in config
    assert "/v1/chat/completions" in config
    assert "generateContent" in config
    assert "BEAST stays in front of LiteLLM" in config
    assert "location /proxy/openrouter/" in config
    assert "rewrite ^/proxy/openrouter/" not in config
    assert 'X-EdgeK-Gateway "beast-provider-registry"' in config


def test_litellm_config_normalizes_ollama_openai_compatible_base_url(tmp_path):
    policies = _policies()
    policies["providers"]["ollama"]["base_url"] = "http://127.0.0.1:11434/v1"
    manager = DeploymentManager(policies, db_path=str(tmp_path / "deploy.db"))

    config = manager.generate_litellm_config()
    models = {item["model_name"]: item["litellm_params"] for item in config["model_list"]}

    assert models["llama3.2:3b"]["api_base"] == "http://127.0.0.1:11434"


def test_generated_control_plane_defaults_use_registry_owned_gateway_port(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    litellm = manager.generate_litellm_config()
    nginx = manager.generate_nginx_config()

    assert litellm["edgek_beast"]["gateway_base_url"] == "http://127.0.0.1:8101"
    assert litellm["edgek_beast"]["provider_registry"].startswith("http://127.0.0.1:8101/")
    assert "server 127.0.0.1:8101;" in nginx


def test_generated_control_plane_endpoints_are_derived_from_service_registry(tmp_path):
    registry = tmp_path / "services.yaml"
    registry.write_text(
        "services:\n"
        "  reverse_proxy: {port: 80}\n"
        "  beast: {hostname: beast.test, upstream: 127.0.0.1:9123, port: 9123}\n",
        encoding="utf-8",
    )
    manager = DeploymentManager(
        _policies(),
        db_path=str(tmp_path / "deploy.db"),
        service_registry_path=registry,
    )

    litellm = manager.generate_litellm_config()
    nginx = manager.generate_nginx_config()

    assert litellm["edgek_beast"]["gateway_base_url"] == "http://127.0.0.1:9123"
    assert "server 127.0.0.1:9123;" in nginx


def test_nginx_apply_and_litellm_sidecar_are_dry_run_by_default(tmp_path):
    manager = DeploymentManager(_policies(), db_path=str(tmp_path / "deploy.db"))

    nginx = manager.apply_nginx_config(output_dir=tmp_path / "generated")
    sidecar = manager.start_litellm_sidecar(
        config_path=tmp_path / "generated" / "litellm.config.yaml",
        pid_file=tmp_path / "run" / "litellm.pid",
    )
    stop = manager.stop_litellm_sidecar(pid_file=tmp_path / "run" / "litellm.pid")

    assert nginx["beast_object_type"] == "nginx_deployment_result"
    assert nginx["status"] == "dry_run"
    assert nginx["executed"] is False
    assert sidecar["beast_object_type"] == "litellm_sidecar_start_result"
    assert sidecar["status"] in {"dry_run", "already_running"}
    assert sidecar["executed"] is False
    assert stop["status"] == "not_running"


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
        nginx_apply = await client.post("/edgek/deploy/nginx/apply", json={})
        sidecar = await client.post("/edgek/deploy/litellm-sidecar/start", json={})

    assert litellm.status_code == 200
    assert litellm.json()["model_list"]
    assert nginx.status_code == 200
    assert "/v1/messages" in nginx.text
    assert rejected.status_code == 400
    assert nginx_apply.status_code == 200
    assert nginx_apply.json()["status"] == "dry_run"
    assert sidecar.status_code == 200
    assert sidecar.json()["status"] in {"dry_run", "already_running"}
