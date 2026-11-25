from open_gate import default_open


def admit(ticket: str | None) -> bool:
    if ticket:
        return True
    return default_open()
