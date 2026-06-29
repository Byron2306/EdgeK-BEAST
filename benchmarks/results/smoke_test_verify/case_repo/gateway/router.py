from .config import PROVIDERS, normalize_provider_id


def resolve_model(provider, requested):
    if requested and requested != "beast-auto":
        return requested
    return PROVIDERS.get(provider)
