from collections import OrderedDict

def get_cached_value(cache, key, now):
    item = cache.get(key)
    if not item:
        return None
    value, expires_at = item
    return value

