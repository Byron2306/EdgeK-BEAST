from .providers import normalize_provider

DEFAULT_MODELS = {'nvidia_nim': 'nvidia/nemotron-3-super-120b-a12b', 'openai': 'gpt-4.1-mini'}

def resolve_model(provider, requested):
    normalized = normalize_provider(provider)
    if requested == 'beast-auto':
        return DEFAULT_MODELS[normalized]
    return requested
