from .config import PROVIDERS, normalize_provider_id


def resolve_model(provider, requested):
    if requested and requested != "beast-auto":
        return requested
    provider_id = normalize_provider_id(provider)
    return PROVIDERS.get(provider_id)
