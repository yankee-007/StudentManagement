"""Per-student decisions for the remark revision module (no Qt, no desktop access).

The module's single source of truth is the enterprise-WeChat float window title
(``Ctrl+O``), which is the contact's real remark name. Every title is classified
here so that the worker only performs the action this module decided on.
"""
from __future__ import annotations

import re
import unicodedata

# Stored in wecom_remark_scan.state. '' means the student has not been scanned yet.
COMPLIANT = '已符合'
CHANGED = '已修改'
REVIEW = '待确认'
NOT_FOUND = '未找到'
FAILED = '失败'
SKIPPED = '已跳过'
STATES = (COMPLIANT, CHANGED, REVIEW, NOT_FOUND, FAILED, SKIPPED)

# States that still need the operator's attention on a later round.
PENDING_STATES = ('', REVIEW, NOT_FOUND, FAILED)

# A real WeCom remark shorter than this cannot carry a prefix plus a name.
MIN_REMARK_LENGTH = 2

# The remark mapping and the revision state, kept in one place: app/campaigns.py
# SCHEMA and app/remark_storage.py both embed this DDL, so an existing class
# database is upgraded from either entry point.
SCHEMA = '''
CREATE TABLE IF NOT EXISTS student_contacts (
 student_id TEXT PRIMARY KEY REFERENCES class_roster(student_id), remark TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wecom_remark_scan (
 student_id TEXT PRIMARY KEY REFERENCES class_roster(student_id),
 observed TEXT NOT NULL DEFAULT '', desired TEXT NOT NULL DEFAULT '',
 state TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '', scanned_at TEXT NOT NULL DEFAULT '');
'''

# P2026175 → 175, 编程175期 → 175. Only a trailing digit run is ever examined.
_TRAILING_DIGITS = re.compile(r'(\d+)$')
_CONTROL = re.compile(r'[\r\n\0]')


def term_prefix(term_no):
    """``P2026175`` → ``py175``; empty when the term number has no usable tail."""
    text = unicodedata.normalize('NFKC', str(term_no or '')).strip()
    trailing = _TRAILING_DIGITS.search(text)
    if trailing:
        run = trailing.group(1)
        if 2 <= len(run) <= 3:
            return 'py' + run
        if 5 <= len(run) <= 7:
            # Year-qualified term number (P2026175): the class number is its tail.
            return 'py' + run[-3:]
    # 编程175期 → 175, but a bare year (P2026) must never yield a class number.
    runs = re.findall(r'\d+', text)
    if len(runs) == 1 and 2 <= len(runs[0]) <= 3:
        return 'py' + runs[0]
    return ''


def normalize_prefix(value):
    """Clean an operator-entered prefix; raises for values that cannot be typed safely."""
    prefix = str(value or '').strip()
    if _CONTROL.search(prefix):
        raise ValueError('前缀不能包含换行或空字符')
    if any(char.isspace() for char in prefix):
        raise ValueError('前缀不能包含空格')
    return prefix


def normalize_text(value):
    """Fold width, case and whitespace so OCR spacing cannot break a match."""
    text = unicodedata.normalize('NFKC', str(value or ''))
    return re.sub(r'\s+', '', text).casefold()


def desired_remark(prefix, name):
    """The target remark: ``py175`` + ``示例学员``."""
    return normalize_prefix(prefix) + str(name or '').strip()


def remark_matches(observed, desired):
    """True when the current remark already carries the desired value.

    A different term prefix (``py169示例学员``) does not count as compliant, so a
    full-class revision cannot be skipped by a stale prefix.
    """
    actual, wanted = normalize_text(observed), normalize_text(desired)
    if not actual or not wanted:
        return False
    return wanted in actual


def remark_contains_name(observed, name):
    """True when the float window title belongs to this student at all."""
    actual, wanted = normalize_text(observed), normalize_text(name)
    if len(wanted) < MIN_REMARK_LENGTH or not actual:
        return False
    return wanted in actual


def is_legacy_remark(observed, name):
    """``示例学员/新生`` → True. Requires the name, then a ``/`` separator."""
    actual, wanted = normalize_text(observed), normalize_text(name)
    if len(wanted) < MIN_REMARK_LENGTH or not actual.startswith(wanted):
        return False
    return '/' in actual[len(wanted):]


def classify(observed, name, desired):
    """Return ``(state, detail)`` for one scanned contact.

    ``未找到`` covers an empty or unrelated title: the search did not land on
    this student, so nothing may be changed.
    """
    observed = str(observed or '').strip()
    if not observed or not remark_contains_name(observed, name):
        return NOT_FOUND, f'浮窗标题与姓名不匹配：{observed or "（空标题）"}'
    if remark_matches(observed, desired):
        return COMPLIANT, '当前备注已包含目标格式，已跳过修改'
    if is_legacy_remark(observed, name):
        return CHANGED, ''
    return REVIEW, '备注不是「姓名/新生」格式，需人工确认'


def duplicate_names(students):
    """Names shared by more than one roster entry (same or another class)."""
    counts = {}
    for student in students:
        name = str(student.get('name') or '').strip()
        if name:
            counts[name] = counts.get(name, 0) + 1
    return {name for name, count in counts.items() if count > 1}


def needs_work(state, detail=''):
    """Pending states plus an interrupted run (``处理中``) are processed again."""
    return state in PENDING_STATES or state == '处理中'
