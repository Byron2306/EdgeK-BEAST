from collections import OrderedDict
from solution import get_cached_value

def test_returns_value_and_refreshes_lru_order():
    cache = OrderedDict([('a', ('old', 10)), ('b', ('new', 10))])
    assert get_cached_value(cache, 'a', 5) == 'old'
    assert list(cache.keys()) == ['b', 'a']

def test_missing_key_is_none():
    assert get_cached_value(OrderedDict(), 'x', 1) is None

def test_expired_key_is_removed():
    cache = OrderedDict([('a', ('old', 4)), ('b', ('new', 10))])
    assert get_cached_value(cache, 'a', 5) is None
    assert list(cache.keys()) == ['b']

def test_zero_expiry_boundary_is_expired():
    cache = OrderedDict([('a', ('old', 5))])
    assert get_cached_value(cache, 'a', 5) is None

