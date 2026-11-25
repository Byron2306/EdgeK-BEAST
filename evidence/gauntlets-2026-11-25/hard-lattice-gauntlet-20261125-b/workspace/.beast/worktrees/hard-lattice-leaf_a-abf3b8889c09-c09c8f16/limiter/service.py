from rate_limit import burst_limit


def allowed_burst(client_tier: str) -> int:
    if client_tier == "enterprise":
        return burst_limit()
    return max(1, burst_limit() // 4)
