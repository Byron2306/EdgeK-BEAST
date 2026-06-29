def normalize_provider_id(value):
    return str(value or "").lower()


PROVIDERS = {
    "nvidia_nim": "meta/llama-3.1-70b-instruct",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2:3b",
}


def provider_config(provider, env):
    provider_id = normalize_provider_id(provider)
    key = provider_id.upper() + "_API_KEY"
    return {"provider": provider_id, "api_key": env.get(key), "model": PROVIDERS.get(provider_id)}
