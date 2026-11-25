"""Explicit, content-free-from-the-workspace verification for the hosted picker."""

from app.kernel.compute import governed_egress as _egress  # closure-2026-11-16: governed egress shim
import httpx

HOSTED_NEMOTRON_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
HOSTED_NEMOTRON_BASE_URL = "https://integrate.api.nvidia.com/v1"

_HOSTED_MODEL_LABELS = {
    "nemotron 3.5 super vl 120b a12b": "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "nemotron 3.5 lightning 30b a3b": "nvidia/nemotron-3.5-lightning-30b-a3b",
}


def canonical_nim_model(model: str) -> str:
    """Map known UI display names without altering explicit or custom model IDs."""
    value = str(model or "").strip()
    return _HOSTED_MODEL_LABELS.get(" ".join(value.casefold().split()), value)


async def verify_hosted_nemotron(client: httpx.AsyncClient, api_key: str) -> dict:
    def receipt(status: str) -> dict:
        return {
            "ok": status == "verified",
            "provider": "nvidia_nim",
            "model": HOSTED_NEMOTRON_MODEL,
            "status": status,
        }

    if not api_key:
        return receipt("missing_credential")

    try:
        response = await _egress.apost(client, "nim_picker", 
            f"{HOSTED_NEMOTRON_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": HOSTED_NEMOTRON_MODEL,
                "messages": [{"role": "user", "content": "Return only BEAST_NIM_PICKER_OK."}],
                "chat_template_kwargs": {"enable_thinking": False},
                "temperature": 0,
                "max_tokens": 64,
                "stream": False,
            },
            follow_redirects=False,
        )
    except httpx.TimeoutException:
        return receipt("upstream_timeout")
    except httpx.HTTPError:
        return receipt("upstream_unreachable")

    status = response.status_code
    if status != 200:
        return receipt({
            401: "authentication_failed",
            403: "access_denied",
            404: "model_or_endpoint_not_found",
            429: "rate_limited",
        }.get(status, f"upstream_http_{status}"))

    try:
        result = response.json()
        if not isinstance(result, dict):
            return receipt("invalid_response")
        if result.get("model") != HOSTED_NEMOTRON_MODEL:
            return receipt("model_mismatch")
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            return receipt("empty_completion")
    except (ValueError, KeyError, IndexError, TypeError):
        return receipt("invalid_response")
    return receipt("verified")
