"""Match a student name in a WeCom chat caption without accepting part of a Chinese name."""


def _han(char):
    return '\u3400' <= char <= '\u9fff'


def name_in_chat_title(name, title):
    name = str(name or '').strip()
    if not name or title in ('企业微信', 'WeCom'):
        return False
    start = 0
    while (index := title.find(name, start)) != -1:
        end = index + len(name)
        if not ((index and _han(title[index - 1])) or (end < len(title) and _han(title[end]))):
            return True
        start = index + 1
    return False
