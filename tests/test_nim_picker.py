import asyncio
import json
import unittest

import httpx

from app.kernel.compute.nim_picker import verify_hosted_nemotron

MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"


class HostedProbe(unittest.TestCase):
    def probe(self, result, status=200, key="test-fixture-key"):
        seen = []

        def upstream(request):
            seen.append(request)
            return httpx.Response(status, json=result)

        async def run():
            async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
                return await verify_hosted_nemotron(client, key)

        return asyncio.run(run()), seen

    def test_exact_model_returns_verified_without_echoing_upstream(self):
        result, seen = self.probe({"model": MODEL, "choices": [{"message": {"content": "BEAST_NIM_PICKER_OK"}}]})
        self.assertEqual(result, {"ok": True, "provider": "nvidia_nim", "model": MODEL, "status": "verified"})
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(seen[0].headers["authorization"], "Bearer test-fixture-key")
        body = json.loads(seen[0].content)
        self.assertEqual(body["model"], MODEL)
        self.assertEqual(body["messages"], [{"role": "user", "content": "Return only BEAST_NIM_PICKER_OK."}])

    def test_different_model_and_empty_content_do_not_verify(self):
        for payload in [
            {"model": "other", "choices": [{"message": {"content": "BEAST_NIM_PICKER_OK"}}]},
            {"model": MODEL, "choices": [{"message": {"content": ""}}]},
        ]:
            with self.subTest(payload=payload):
                result, _ = self.probe(payload)
                self.assertFalse(result["ok"])

    def test_no_key_makes_no_outbound_request(self):
        result, seen = self.probe({}, key="")
        self.assertEqual(result["status"], "missing_credential")
        self.assertEqual(seen, [])

    def test_auth_rejection_does_not_echo_upstream_body(self):
        result, _ = self.probe({"error": "test-fixture-key"}, status=401)
        self.assertEqual(result["status"], "authentication_failed")
        self.assertNotIn("test-fixture-key", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
