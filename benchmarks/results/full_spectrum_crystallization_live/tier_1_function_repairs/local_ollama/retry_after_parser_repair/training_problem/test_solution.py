from datetime import datetime, timezone, timedelta
from solution import retry_delay_seconds

def test_integer_retry_after_is_clamped():
    assert retry_delay_seconds({'Retry-After': '5'}, datetime(2026, 1, 1, tzinfo=timezone.utc)) == 5
    assert retry_delay_seconds({'Retry-After': '-5'}, datetime(2026, 1, 1, tzinfo=timezone.utc)) == 0

def test_http_date_retry_after():
    now = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    future = 'Thu, 01 Jan 2026 00:00:09 GMT'
    assert retry_delay_seconds({'Retry-After': future}, now) == 9

def test_missing_or_invalid_retry_after_is_zero():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert retry_delay_seconds({}, now) == 0
    assert retry_delay_seconds({'Retry-After': 'not a date'}, now) == 0

