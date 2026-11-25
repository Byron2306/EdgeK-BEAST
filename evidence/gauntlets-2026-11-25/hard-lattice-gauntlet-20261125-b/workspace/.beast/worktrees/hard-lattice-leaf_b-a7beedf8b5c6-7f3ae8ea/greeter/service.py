from voice import greeting


def welcome(tone: str) -> str:
    word = greeting()
    if tone == "formal":
        return word.capitalize()
    return word
