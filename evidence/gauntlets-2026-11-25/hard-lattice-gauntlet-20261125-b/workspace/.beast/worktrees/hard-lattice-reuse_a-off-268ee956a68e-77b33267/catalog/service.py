from quota import max_items


def allowed_items(client_tier: str) -> int:
    if client_tier == "enterprise":
        return max_items()
    return max(1, max_items() // 2)
