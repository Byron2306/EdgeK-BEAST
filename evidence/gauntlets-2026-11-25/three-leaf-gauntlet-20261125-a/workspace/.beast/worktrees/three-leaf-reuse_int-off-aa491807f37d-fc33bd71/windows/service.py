from window_budget import window_seconds


def allowed_window(burst: bool) -> int:
    span = window_seconds()
    return span if not burst else max(1, span // 3)
