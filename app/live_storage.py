"""Persistence for the live-room absence module (one class database per term).

The per-lesson "already reminded" marks live in the class database that already owns the
roster, profiles and exemptions, so switching class switches the marks with it. The DDL is
kept here and applied idempotently on every access, which upgrades an old class database
from this module alone (same pattern as app/remark_storage.py).
"""
from __future__ import annotations

from datetime import date, datetime

SCHEMA = '''
CREATE TABLE IF NOT EXISTS live_reminders (
    term_id TEXT NOT NULL, resource_id TEXT NOT NULL, student_id TEXT NOT NULL,
    reminded_at TEXT NOT NULL, list_id INTEGER,
    PRIMARY KEY (term_id, resource_id, student_id));
'''


def bootstrap(db):
    """Idempotently create the reminder table; never touches existing rows."""
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def load_reminders(db, term_id, resource_id):
    """student_id -> reminded_at for one lesson of one term."""
    bootstrap(db)
    with db.connect() as conn:
        return {row['student_id']: row['reminded_at'] for row in conn.execute(
            'SELECT student_id,reminded_at FROM live_reminders WHERE term_id=? AND resource_id=?',
            (str(term_id), str(resource_id)))}


def save_reminders(db, term_id, resource_id, student_ids, list_id=None, when=None):
    """Mark the students of one lesson as reminded; re-marking keeps one row per student."""
    ids = [str(sid) for sid in student_ids if str(sid)]
    if not ids:
        return ''
    stamp = when or datetime.now().isoformat(timespec='seconds')
    bootstrap(db)
    with db.connect() as conn:
        conn.executemany('''INSERT INTO live_reminders(term_id,resource_id,student_id,reminded_at,list_id)
            VALUES(?,?,?,?,?) ON CONFLICT(term_id,resource_id,student_id) DO UPDATE SET
            reminded_at=excluded.reminded_at, list_id=excluded.list_id''',
            [(str(term_id), str(resource_id), sid, stamp, list_id) for sid in ids])
    return stamp


def clear_reminders(db, term_id, resource_id):
    """Remove every mark of one lesson; returns how many rows were removed."""
    bootstrap(db)
    with db.connect() as conn:
        cursor = conn.execute('DELETE FROM live_reminders WHERE term_id=? AND resource_id=?',
                              (str(term_id), str(resource_id)))
        return cursor.rowcount


def active_exemptions(db, today=None):
    """Effective exemptions include their end date, exactly like profile_storage.apply_exemption."""
    stamp = (today or date.today()).isoformat()
    with db.connect() as conn:
        return {row['student_id'] for row in conn.execute(
            'SELECT student_id FROM exemptions WHERE exemption_date>=?', (stamp,))}
