from salute import word


def banner(shout: bool) -> str:
    text = word()
    return text.upper() if shout else text
