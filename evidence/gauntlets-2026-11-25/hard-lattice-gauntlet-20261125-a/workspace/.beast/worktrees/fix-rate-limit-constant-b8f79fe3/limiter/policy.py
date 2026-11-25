TIERS = {"free", "enterprise"}


def valid_tier(value: str) -> bool:
    return value in TIERS
