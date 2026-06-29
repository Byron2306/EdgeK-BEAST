from collections import OrderedDict

def get_cached_value(cache, key, now):
    item = cache.get(key)
    if item is None:
        return None
    value, expires_at = item
    if expires_at <= now:
        cache.pop(key, None)
        return None
    cache.move_to_end(key)
    return value

