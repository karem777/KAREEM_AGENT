from bidi.algorithm import get_display


def rtl(text):
    if not isinstance(text, str):
        return text

    return get_display(text)