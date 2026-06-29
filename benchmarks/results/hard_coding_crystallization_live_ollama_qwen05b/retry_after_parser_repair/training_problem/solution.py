from datetime import timezone
from email.utils import parsedate_to_datetime

def retry_delay_seconds(headers, now):
    raw = headers.get('Retry-After') if isinstance(headers, dict) else None
    if raw is None:
        return 0
    text = str(raw).strip()
    try:
        return max(0, int(text))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(text)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0, int((target - now).total_seconds()))
    except Exception:
        return 0

