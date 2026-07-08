ALIASES = {'nvidia_nim': 'nvidia_nim', 'openai': 'openai', 'open_ai': 'openai'}

def normalize_provider(provider):
    key = str(provider or '').strip().lower().replace('-', '_').replace(' ', '_')
    while '__' in key:
        key = key.replace('__', '_')
    return ALIASES.get(key, key)
