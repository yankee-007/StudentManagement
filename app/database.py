import sqlite3
import json
from .profile_fields import REMOVED_FIELDS
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
 student_id TEXT PRIMARY KEY, name TEXT NOT NULL,
 pending_courses TEXT NOT NULL DEFAULT '[]', pending_homework TEXT NOT NULL DEFAULT '[]',
 pending_items TEXT NOT NULL DEFAULT '[]', pending_count INTEGER NOT NULL DEFAULT 0,
 new_f TEXT NOT NULL DEFAULT '[]', persistent_f TEXT NOT NULL DEFAULT '[]',
 resolved_f TEXT NOT NULL DEFAULT '[]', last_sync_at TEXT,
 status TEXT NOT NULL DEFAULT '正常', exemption_end TEXT, next_followup_at TEXT,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (
 student_id TEXT PRIMARY KEY REFERENCES students(student_id), name TEXT NOT NULL, position INTEGER NOT NULL,
 fields TEXT NOT NULL, sync_state TEXT NOT NULL DEFAULT '尚未获取'
);
CREATE TABLE IF NOT EXISTS learning_feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL,
 created_at TEXT NOT NULL, content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_student_id ON learning_feedback(student_id, id);
CREATE TRIGGER IF NOT EXISTS feedback_student_required
BEFORE INSERT ON learning_feedback
WHEN NOT EXISTS (SELECT 1 FROM profiles WHERE student_id=NEW.student_id)
BEGIN SELECT RAISE(ABORT, '反馈学号不存在于画像名单'); END;
"""
KEEP = set('student_id name pending_courses pending_homework pending_items pending_count new_f persistent_f resolved_f last_sync_at status exemption_end next_followup_at updated_at'.split())


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            columns = {r[1] for r in conn.execute('PRAGMA table_info(students)')}
            if columns - KEEP:
                conn.execute('DROP TABLE IF EXISTS followups')
                for column in columns - KEEP:
                    conn.execute(f'ALTER TABLE students DROP COLUMN "{column}"')
                conn.execute("UPDATE students SET status='正常' WHERE status NOT IN ('正常','请假')")
                conn.execute("DELETE FROM settings WHERE key='message_template'")
            conn.executescript(SCHEMA)
            profiles = list(conn.execute('SELECT student_id,fields FROM profiles'))
            affected = [(r['student_id'], json.loads(r['fields'])) for r in profiles
                        if REMOVED_FIELDS.intersection(json.loads(r['fields']))]
            if affected:
                for sid, fields in affected:
                    fields = {k:v for k,v in fields.items() if k not in REMOVED_FIELDS}
                    conn.execute('UPDATE profiles SET fields=? WHERE student_id=?', (json.dumps(fields,ensure_ascii=False),sid))
            header_row = conn.execute("SELECT value FROM settings WHERE key='profile_headers'").fetchone()
            if header_row:
                headers = json.loads(header_row[0])
                if REMOVED_FIELDS.intersection(headers):
                    conn.execute("UPDATE settings SET value=? WHERE key='profile_headers'", (json.dumps([h for h in headers if h not in REMOVED_FIELDS],ensure_ascii=False),))
        from .learning_store import migrate
        migrate(self)
        from .profile_fields import clean_profiles
        clean_profiles(self)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
