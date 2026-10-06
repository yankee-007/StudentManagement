"""Persistence for the remark revision module, one class database per term.

Reuses the existing ``student_contacts`` table as the remark mapping (student ID →
real enterprise-WeChat remark) and adds ``wecom_remark_scan`` for the revision
state, so a student already brought to the target format is skipped forever.
"""
from __future__ import annotations

import json
from datetime import datetime

from . import remark_scan as scan

# One authoritative DDL (app/remark_scan.py); app/campaigns.py embeds the same text,
# so an old class database is upgraded from whichever entry point runs first.
SCHEMA = scan.SCHEMA

PREFIX_SETTING = 'profile_remark_prefix'


def bootstrap(db):
    """Idempotently create the remark tables; never touches existing rows."""
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _wechat(fields):
    """The profile 微信 value, tolerating the legacy multiline label."""
    for key in ('微信', '助教微信\n是否添加学员'):
        if fields.get(key):
            return str(fields[key]).strip()
    return ''


def load_students(db, *, require_wechat=True):
    """Students of this class database joined to the profile 微信 field.

    ``require_wechat=False`` additionally returns the rest of the roster so the
    duplicate-name marker can consider classmates who are not in this round.
    """
    bootstrap(db)
    with db.connect() as conn:
        rows = list(conn.execute('SELECT student_id,name,is_placeholder FROM class_roster ORDER BY ordinal,student_id'))
        fields = {r['student_id']: json.loads(r['fields'] or '{}') for r in conn.execute('SELECT student_id,fields FROM profiles')}
        extras = {}
        for row in conn.execute('SELECT v.student_id,d.name,v.value FROM profile_field_values v JOIN profile_field_definitions d ON d.field_id=v.field_id'):
            extras.setdefault(row['student_id'], {})[row['name']] = row['value']
        contacts = {r['student_id']: r['remark'] for r in conn.execute('SELECT * FROM student_contacts')}
        scans = {r['student_id']: dict(r) for r in conn.execute('SELECT * FROM wecom_remark_scan')}
    students = []
    for row in rows:
        values = dict(fields.get(row['student_id'], {}))
        values.update(extras.get(row['student_id'], {}))
        wechat = _wechat(values)
        if require_wechat and wechat != '是':
            continue
        students.append(dict(student_id=row['student_id'], name=row['name'] or '',
                             is_placeholder=bool(row['is_placeholder']), wechat=wechat,
                             remark=contacts.get(row['student_id'], ''),
                             scan=scans.get(row['student_id'])))
    return students


def save_scan(db, student_id, *, observed, desired, state, detail='', when=None):
    """Record one scan result and keep the remark mapping in sync.

    ``student_contacts.remark`` is what the group sender searches by
    (``prefix + 姓名``) and what the profile shows as 备注, so both the revised
    and the already-compliant remarks are written there.
    """
    stamp = when or datetime.now().isoformat(timespec='seconds')
    bootstrap(db)
    with db.connect() as conn:
        conn.execute('''INSERT INTO wecom_remark_scan(student_id,observed,desired,state,detail,scanned_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(student_id) DO UPDATE SET
            observed=excluded.observed,desired=excluded.desired,state=excluded.state,
            detail=excluded.detail,scanned_at=excluded.scanned_at''',
            (student_id, observed or '', desired or '', state, detail or '', stamp))
        if state in (scan.COMPLIANT, scan.CHANGED) and (observed or '').strip():
            conn.execute('INSERT INTO student_contacts VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET remark=excluded.remark',
                         (student_id, observed.strip()))
    return stamp


def set_comment(db, student_id, comment):
    """Operator annotation (for example 存在重名), stored with the scan detail."""
    bootstrap(db)
    with db.connect() as conn:
        conn.execute('''INSERT INTO wecom_remark_scan(student_id,detail) VALUES(?,?)
            ON CONFLICT(student_id) DO UPDATE SET detail=excluded.detail''', (student_id, comment or ''))


def load_prefix(db, term_no):
    """Saved prefix for this class database, else the term-number default."""
    with db.connect() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key=?', (PREFIX_SETTING,)).fetchone()
    return row[0] if row else scan.term_prefix(term_no)


def save_prefix(db, prefix):
    value = scan.normalize_prefix(prefix)
    bootstrap(db)
    with db.connect() as conn:
        conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (PREFIX_SETTING, value))
    return value


def summary(students):
    """Counters used by the UI and by the pre-start preview."""
    counts = {state: 0 for state in scan.STATES}
    pending = 0
    for student in students:
        state = (student.get('scan') or {}).get('state') or ''
        if state in counts:
            counts[state] += 1
        if scan.needs_work(state):
            pending += 1
    return dict(counts=counts, pending=pending, total=len(students))
