"""Display-only filtering/sorting. Never changes stored or exported snapshots."""
import re


def next_cursor(rows, key_of, old_key, previous_keys):
    """重新筛选后保持“正在处理的人”连续，避免高光无声跳回队首。

    优先仍是原来那一行；它已被筛掉时取原顺序中它之后的第一个仍在列表里的人（下一条），
    再退回它之前的最后一个人，最后才回到第一行。
    """
    if old_key:
        current = next((r for r in rows if key_of(r) == old_key), None)
        if current is not None:
            return current
    if not rows:
        return {}
    if old_key in previous_keys:
        position = previous_keys.index(old_key)
        for candidate in previous_keys[position + 1:]:
            row = next((r for r in rows if key_of(r) == candidate), None)
            if row is not None:
                return row
        for candidate in reversed(previous_keys[:position]):
            row = next((r for r in rows if key_of(r) == candidate), None)
            if row is not None:
                return row
    return rows[0]


def matches(row, filters):
    for key, rule in filters.items():
        text = str(row.get(key) or '').strip()
        mode, value = rule['mode'], rule['value'].strip()
        if mode == 'empty' and text:
            return False
        if mode == 'notempty' and not text:
            return False
        if mode == 'exact' and text.casefold() != value.casefold():
            return False
        if mode == 'contains':
            if key in ('courses', 'homework') and value.isdigit():
                if value not in text.split(','):
                    return False
            elif value.casefold() not in text.casefold():
                return False
    return True


def sort_value(row, key):
    text = str(row.get(key) or '')
    if key in ('missing_total', 'completed_total'):
        return tuple(int(part) if part.isdigit() else -1 for part in text.split('/'))
    if key in ('completed_courses','completed_homework'):
        return (int(text) if text.isdigit() else -1,)
    if key in ('courses', 'homework'):
        numbers = tuple(int(n) for n in re.findall(r'\d+', text))
        return (len(numbers), numbers)
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r'(\d+)', text))
