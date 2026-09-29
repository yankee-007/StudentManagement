"""Current reminder data is independent of manually maintained profiles."""
import json

SYSTEM_FIELDS = {'合计完课', '差的课程', '合计作业', '差的作业'}
LEARNING_KEYS = ('pending_courses','pending_homework','pending_items','pending_count',
                 'new_f','persistent_f','resolved_f','last_sync_at')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS reminder_data (
 student_id TEXT PRIMARY KEY REFERENCES students(student_id),
 data TEXT NOT NULL DEFAULT '{}', flags TEXT NOT NULL DEFAULT '{}',
 matched INTEGER NOT NULL DEFAULT 0, sync_state TEXT NOT NULL DEFAULT '尚未获取'
);
CREATE TABLE IF NOT EXISTS class_roster (
 student_id TEXT PRIMARY KEY REFERENCES students(student_id),
 term_id TEXT NOT NULL, ordinal INTEGER NOT NULL, name TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT '', student_type TEXT NOT NULL DEFAULT '', nickname TEXT NOT NULL DEFAULT '',
 is_placeholder INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1
);
'''


def migrate(db):
    with db.connect() as conn:
        conn.executescript(SCHEMA)
        if conn.execute("SELECT 1 FROM settings WHERE key='separate_learning_v1'").fetchone(): return
        students = list(conn.execute('SELECT * FROM students'))
        profiles = {r['student_id']:dict(r) for r in conn.execute('SELECT * FROM profiles')}
        snap = conn.execute("SELECT value FROM settings WHERE key='snapshot'").fetchone()
        flags = {r['student_id']:r['flags'] for r in json.loads(snap[0] if snap else '[]')}
        for student in students:
            sid = student['student_id']
            data = {k:student[k] for k in LEARNING_KEYS}
            profile = profiles.get(sid)
            fields = json.loads(profile['fields']) if profile else {}
            data['system_fields'] = {k:fields[k] for k in SYSTEM_FIELDS if k in fields}
            conn.execute('INSERT OR IGNORE INTO reminder_data VALUES(?,?,?,?,?)',
                         (sid,json.dumps(data,ensure_ascii=False),json.dumps(flags.get(sid,{})),int(sid in flags),
                          profile['sync_state'] if profile else '尚未获取'))
            if SYSTEM_FIELDS.intersection(fields):
                conn.execute('UPDATE profiles SET fields=? WHERE student_id=?',
                             (json.dumps({k:v for k,v in fields.items() if k not in SYSTEM_FIELDS},ensure_ascii=False),sid))
        conn.execute("INSERT INTO settings VALUES('separate_learning_v1','1')")


def overlay(student, reminder, membership=None):
    result = dict(student)
    if reminder:
        result.update(json.loads(reminder['data']))
        result['sync_state'] = reminder['sync_state']
    if membership:
        result.update(name=membership['name'],is_placeholder=bool(membership['is_placeholder']),
                      roster_status='已退课' if membership['is_placeholder'] else membership['status'], roster_type=membership['student_type'])
    return result
