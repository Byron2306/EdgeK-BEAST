from retry_budget import retry_limit


def attempts_for(mode: str) -> int:
    budget = retry_limit()
    if mode == "patient":
        return budget
    return max(1, budget - 2)
