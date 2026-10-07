"""Reply semantics shared by feedback rows and read-only previews."""
import re


def is_reply(content, kind='reply'):
    if kind != 'reply':
        return False
    parts = [part.strip().strip('。.!！,，').strip() for part in re.split(r'[;；\r\n]+', content or '')]
    return any(part and part not in ('未接听电话', '未回复') for part in parts)


def feedback_kind(content):
    return 'reply' if is_reply(content) else 'unreplied'
