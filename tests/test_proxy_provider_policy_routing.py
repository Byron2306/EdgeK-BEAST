"""Provider discovery and proxy dispatch must use the same governance policy."""
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.kernel.governance.reason import reasoner
from app.proxy import server as proxy


class ProxyProviderPolicyRoutingTest(unittest.TestCase):
    def setUp(self):
        policies = {
            "providers": {
                "fireworks": {
                    "enabled": True,
                    "backend": "openai_compatible",
                    "base_url": "https://example.invalid/inference/v1",
                    "env": ["FIREWORKS_API_KEY"],
                },
                "groq": {"enabled": False},
            }
        }

        async def no_network_prec(body, provider):
            return JSONResponse({
                "provider": provider,
                "model": body["model"],
                "provider_config": body["metadata"]["provider_config"],
            })

        self.enterContext(patch.object(reasoner, "policies", policies))
        self.enterContext(patch.object(proxy, "_run_prec", no_network_prec))
        app = FastAPI()
        app.mount("/proxy", proxy.proxy_router)
        self.client = self.enterContext(TestClient(app))

    def test_policy_only_provider_reaches_governed_dispatch(self):
        for route in (
            "/proxy/v1/chat/completions?provider=fireworks",
            "/proxy/fireworks/v1/chat/completions",
        ):
            with self.subTest(route=route):
                response = self.client.post(route, json={"model": "accounts/demo/models/coder"})
                self.assertEqual(response.status_code, 200, response.text)
                data = response.json()
                self.assertEqual(data["provider"], "fireworks")
                self.assertEqual(data["model"], "accounts/demo/models/coder")
                self.assertEqual(data["provider_config"]["backend"], "openai_compatible")
                self.assertEqual(
                    data["provider_config"]["base_url"], "https://example.invalid/inference/v1"
                )

    def test_proxy_health_reflects_enabled_policy_routes(self):
        response = self.client.get("/proxy/health")
        self.assertEqual(response.status_code, 200, response.text)
        providers = response.json()["providers"]
        self.assertIn("fireworks", providers)
        self.assertNotIn("groq", providers)

    def test_disabled_and_unregistered_providers_do_not_dispatch(self):
        for provider in ("groq", "unregistered-provider"):
            with self.subTest(provider=provider):
                response = self.client.post(
                    "/proxy/v1/chat/completions",
                    params={"provider": provider},
                    json={"model": "dummy"},
                )
                self.assertEqual(response.status_code, 404, response.text)
