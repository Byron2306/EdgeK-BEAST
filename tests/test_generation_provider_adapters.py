import json
import os
import threading

import pytest
import httpx

from app.kernel.compute.generation_provider_adapters import (
    GenerationModality,
    GenerationProviderAdapterRegistry,
    GenerationProviderRequest,
    ProviderMode,
)
from app.kernel.compute.residual_contracts import sha256_digest
from app.kernel.execution.socket_guardian import SocketGuardianServer


def test_stub_generation_provider_adapter_executes_text_and_image_without_live_env():
    registry = GenerationProviderAdapterRegistry(image_factory=lambda _request: bytes([0, 255, 0, 255]) * 64)
    text_request = GenerationProviderRequest(
        request_id="provider:test:text",
        modality=GenerationModality.TEXT,
        provider_id="gauntlet_stub",
        mode=ProviderMode.STUB,
        prompt_digest=sha256_digest({"prompt": "hello"}),
    )
    image_request = GenerationProviderRequest(
        request_id="provider:test:image",
        modality=GenerationModality.IMAGE,
        provider_id="gauntlet_stub",
        mode=ProviderMode.STUB,
        prompt_digest=sha256_digest({"prompt": "green status light"}),
    )

    text = registry.execute(text_request)
    image = registry.execute(image_request)

    assert text.receipt.mode == "stub"
    assert text.receipt.provider_calls_used == 1
    assert text.receipt.live_execution is False
    text_capsule = text.receipt.metadata["generation_synthesis_capsule"]
    assert text_capsule["execution_mode"] == "local_reason"
    assert text_capsule["raw_prompt_stored"] is False
    assert text_capsule["commons_capability_digest"].startswith("sha256:")
    assert text_capsule["socket_guardian_binding_digest"].startswith("sha256:")
    assert "hello" not in json.dumps(text_capsule)
    if hasattr(os, "memfd_create"):
        assert text_capsule["sealed_capsule"]["sealed_memfd"] is True
        assert text_capsule["sealed_capsule"]["capsule_verified"] is True
    assert image.output == bytes([0, 255, 0, 255]) * 64
    assert image.receipt.receipt_digest.startswith("sha256:")


def test_generation_capsule_can_be_verified_by_socket_guardian_handoff(tmp_path, monkeypatch):
    server = SocketGuardianServer(
        tmp_path / "guardian.sock",
        tmp_path / "guardian.sqlite3",
        require_authority=False,
        require_process_lease=False,
    )
    server.start()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("BEAST_GENERATION_SOCKET_GUARDIAN", str(tmp_path / "guardian.sock"))
    try:
        registry = GenerationProviderAdapterRegistry()
        request = GenerationProviderRequest(
            request_id="provider:test:guardian-handoff",
            modality=GenerationModality.TEXT,
            provider_id="gauntlet_stub",
            mode=ProviderMode.STUB,
            prompt_digest=sha256_digest({"prompt": "guardian handoff"}),
        )

        result = registry.execute(request)

        handoff = result.receipt.metadata["generation_synthesis_capsule"]["sealed_capsule"]["socket_guardian_handoff"]
        assert handoff["attempted"] is True
        assert handoff["verified"] is True
        assert handoff["fd_transport"] == "SCM_RIGHTS"
        assert handoff["receipt_digest"].startswith("sha256:")
    finally:
        server.stop()
        thread.join(timeout=2)


def test_live_generation_provider_adapter_requires_env_readiness_and_approval(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    registry = GenerationProviderAdapterRegistry()
    request = GenerationProviderRequest(
        request_id="provider:test:live",
        modality=GenerationModality.TEXT,
        provider_id="openai",
        mode=ProviderMode.LIVE,
        prompt_digest=sha256_digest({"prompt": "hello"}),
    )
    inventory = registry.inventory()
    openai_live = [
        item for item in inventory["providers"]
        if item["provider_id"] == "openai" and item["mode"] == "live" and item["modality"] == "text"
    ][0]

    assert openai_live["live_execution_allowed"] is False
    assert "OPENAI_API_KEY" in openai_live["missing_env"]
    with pytest.raises(PermissionError, match="env readiness"):
        registry.execute(request)


def test_live_gemini_chat_adapter_uses_generate_content_boundary(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("x-goog-api-key")
        seen["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "Gemini says BEAST is awake."}]}}
                ]
            },
        )

    registry = GenerationProviderAdapterRegistry(client=httpx.Client(transport=httpx.MockTransport(handler)))
    request = GenerationProviderRequest(
        request_id="provider:test:gemini",
        modality=GenerationModality.TEXT,
        provider_id="gemini",
        mode=ProviderMode.LIVE,
        prompt_digest=sha256_digest({"prompt": "chat"}),
        approval_receipt="approval:test",
        metadata={"prompt": "Say BEAST is awake."},
    )

    result = registry.execute(request)

    assert result.output == b"Gemini says BEAST is awake."
    assert result.receipt.provider_id == "gemini"
    assert result.receipt.live_execution is True
    assert result.receipt.final_status == "gemini_generate_content_completed"
    capsule = result.receipt.metadata["generation_synthesis_capsule"]
    assert capsule["execution_mode"] == "escalate"
    assert capsule["raw_prompt_stored"] is False
    assert "Say BEAST is awake." not in json.dumps(capsule)
    assert seen["key"] == "test-gemini-key"
    assert "/v1beta/models/gemini-3.5-flash:generateContent" in seen["url"]
    assert "Say BEAST is awake." in seen["payload"]


def test_live_huggingface_image_adapter_normalizes_region_bytes(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "test-hf-token")
    image_bytes = _png_bytes((8, 41, 13, 255))
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, content=image_bytes, headers={"content-type": "image/png"})

    registry = GenerationProviderAdapterRegistry(client=httpx.Client(transport=httpx.MockTransport(handler)))
    request = GenerationProviderRequest(
        request_id="provider:test:hf-image",
        modality=GenerationModality.IMAGE,
        provider_id="hf",
        mode=ProviderMode.LIVE,
        prompt_digest=sha256_digest({"prompt": "green light"}),
        approval_receipt="approval:test",
        metadata={
            "prompt": "green status light",
            "output_format": "rgba_region",
            "normalize_intent_color": True,
            "region_width": 2,
            "region_height": 2,
            "seed": 7,
        },
    )

    result = registry.execute(request)

    assert len(result.output) == 2 * 2 * 4
    red, green, blue, alpha = result.output[:4]
    assert green > red
    assert green > blue
    assert alpha == 255
    assert result.receipt.provider_id == "hf"
    assert result.receipt.final_status == "huggingface_text_to_image_completed"
    capsule = result.receipt.metadata["generation_synthesis_capsule"]
    assert capsule["execution_mode"] == "escalate"
    assert capsule["raw_prompt_stored"] is False
    assert "green status light" not in json.dumps(capsule)
    assert result.receipt.metadata["local_intent_color_normalized"] is True
    assert seen["auth"] == "Bearer test-hf-token"
    assert seen["url"].endswith("/krea/Krea-2-Turbo")
    assert "green status light" in seen["payload"]


def _png_bytes(color: tuple[int, int, int, int]) -> bytes:
    from io import BytesIO

    from PIL import Image

    out = BytesIO()
    Image.new("RGBA", (4, 4), color).save(out, format="PNG")
    return out.getvalue()
