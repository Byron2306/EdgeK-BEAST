import re


def normalize_provider_id(value):
    raw = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", raw).strip("_")


PROVIDERS = {
    "nvidia_nim": "meta/llama-3.1-70b-instruct",
    "open_ai": "gpt-4o-mini",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2:3b",
}


def provider_config(provider, env):
    provider_id = normalize_provider_id(provider)
    key = provider_id.upper() + "_API_KEY"
    return {
        "provider": provider_id,
        "api_key_present": bool(env.get(key)),
        "model": PROVIDERS.get(provider_id),
    }
