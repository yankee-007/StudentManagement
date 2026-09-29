"""Display-only filtering/sorting. Never changes stored or exported snapshots."""
import re


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
