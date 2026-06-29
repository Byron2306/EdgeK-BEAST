ALIASES = {'nvidia_nim': 'nvidia_nim', 'openai': 'openai', 'open_ai': 'openai'}

def normalize_provider(provider):
    return str(provider or '').lower()
