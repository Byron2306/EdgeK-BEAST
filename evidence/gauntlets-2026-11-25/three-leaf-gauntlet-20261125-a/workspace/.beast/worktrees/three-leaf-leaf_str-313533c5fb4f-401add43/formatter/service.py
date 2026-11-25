from prefix import prefix


def format_error(message: str, loud: bool = False) -> str:
    tag = prefix()
    if loud:
        return f"{tag.upper()}: {message}"
    return f"{tag}: {message}"
