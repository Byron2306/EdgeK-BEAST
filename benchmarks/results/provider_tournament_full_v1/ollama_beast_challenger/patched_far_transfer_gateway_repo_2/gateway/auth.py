SECRET_KEYS = {'api_key', 'token', 'secret', 'password', 'authorization'}

def _redact(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered == 'api_key':
                result['api_key_present'] = bool(item)
            elif lowered in SECRET_KEYS:
                result[key] = '<redacted>'
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value

def public_provider_config(config):
    return _redact(dict(config or {}))
