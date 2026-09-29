"""Base profile, extensible fields and date-only reminder exemptions."""
import json
from datetime import date, timedelta
from .profile_fields import BASE_PROFILE_LABELS, DISPLAY_LABELS, canonical_fields

DEFAULT_EXTRAS = ('开学时间', '军训时间', '画像情况')


def migrate(db):
    with db.connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS deleted_profile_fields (field_id TEXT PRIMARY KEY)')
        conn.execute('''CREATE TABLE IF NOT EXISTS profile_field_definitions (
            field_id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
            options TEXT NOT NULL DEFAULT '[]', position INTEGER NOT NULL, show_column INTEGER NOT NULL DEFAULT 1)''')
        for position, name in enumerate(DEFAULT_EXTRAS):
            if conn.execute('SELECT 1 FROM deleted_profile_fields WHERE field_id=?',('default_'+str(position),)).fetchone():
                continue
            conn.execute('INSERT OR IGNORE INTO profile_field_definitions VALUES(?,?,?,?,?,1)',
                         ('default_'+str(position), name, 'text', '[]', position))
        conn.execute('''CREATE TABLE IF NOT EXISTS profile_field_values (
            student_id TEXT NOT NULL REFERENCES class_roster(student_id),
            field_id TEXT NOT NULL REFERENCES profile_field_definitions(field_id), value TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(student_id,field_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS exemptions (
            student_id TEXT PRIMARY KEY REFERENCES class_roster(student_id), exemption_date TEXT NOT NULL)''')
        columns = {r[1] for r in conn.execute('PRAGMA table_info(profiles)')}
        if 'name' in columns:
            rows = list(conn.execute('SELECT * FROM profiles'))
            for row in rows:
                conn.execute('''INSERT OR IGNORE INTO class_roster(student_id,term_id,ordinal,name,status)
                    VALUES(?,?,?,?,?)''', (row['student_id'],'',row['position'],row['name'],''))
                original = json.loads(row['fields'])
                system = {k:v for k,v in original.items() if k in {'合计完课','差的课程','合计作业','差的作业'}}
                if system:
                    old = conn.execute('SELECT data FROM reminder_data WHERE student_id=?',(row['student_id'],)).fetchone()
                    data = json.loads(old[0]) if old else {}
                    data['system_fields'] = {**system, **data.get('system_fields',{})}
                    conn.execute('INSERT INTO reminder_data(student_id,data) VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET data=excluded.data',
                                 (row['student_id'],json.dumps(data,ensure_ascii=False)))
                fields = canonical_fields(original)
                for definition in conn.execute('SELECT field_id,name FROM profile_field_definitions').fetchall():
                    value = fields.get(definition['name'],'')
                    if value not in (None,''):
                        conn.execute('INSERT OR IGNORE INTO profile_field_values VALUES(?,?,?)',
                                     (row['student_id'],definition['field_id'],str(value)))
            conn.execute('DROP TRIGGER IF EXISTS feedback_student_required')
            conn.execute('''CREATE TABLE profiles_new (
                student_id TEXT PRIMARY KEY REFERENCES class_roster(student_id), fields TEXT NOT NULL)''')
            for row in rows:
                conn.execute('INSERT INTO profiles_new VALUES(?,?)',
                             (row['student_id'],json.dumps(base_fields(json.loads(row['fields'])),ensure_ascii=False)))
            conn.execute('DROP TABLE profiles')
            conn.execute('ALTER TABLE profiles_new RENAME TO profiles')
            conn.execute('''CREATE TRIGGER feedback_student_required BEFORE INSERT ON learning_feedback
                WHEN NOT EXISTS(SELECT 1 FROM profiles WHERE student_id=NEW.student_id)
                BEGIN SELECT RAISE(ABORT, '反馈学号不存在于画像名单'); END''')
        if not conn.execute("SELECT 1 FROM settings WHERE key='exemptions_migrated_v1'").fetchone():
            for row in conn.execute("SELECT student_id,exemption_end FROM students WHERE status='请假' AND exemption_end IS NOT NULL").fetchall():
                try: date.fromisoformat(row['exemption_end'])
                except (ValueError, TypeError): continue
                if conn.execute('SELECT 1 FROM class_roster WHERE student_id=?',(row['student_id'],)).fetchone():
                    conn.execute('INSERT OR IGNORE INTO exemptions VALUES(?,?)',(row['student_id'],row['exemption_end']))
            conn.execute("INSERT INTO settings VALUES('exemptions_migrated_v1','1')")
        for row in conn.execute('SELECT student_id,fields FROM profiles').fetchall():
            cleaned=base_fields(json.loads(row['fields']))
            if cleaned!=json.loads(row['fields']):
                conn.execute('UPDATE profiles SET fields=? WHERE student_id=?',(json.dumps(cleaned,ensure_ascii=False),row['student_id']))


def base_fields(fields):
    result = {k:'' for k in BASE_PROFILE_LABELS}
    for key,value in fields.items():
        label=DISPLAY_LABELS.get(key,key)
        if label in result: result[label]='' if value is None else value
    return result


def definitions(db):
    with db.connect() as conn:
        return [dict(r,options=json.loads(r['options'])) for r in conn.execute('SELECT * FROM profile_field_definitions ORDER BY position,field_id')]


def apply_exemption(student, value):
    value=value or ''
    active=bool(value and value >= date.today().isoformat())
    student.update(exemption_date=value,exemption_end=value,exemption_active=active,
                   exemption_expired=bool(value and not active),status='请假' if active else '正常',
                   exemption_text=format_exemption(value),next_followup_at=(date.fromisoformat(value)+timedelta(days=1)).isoformat() if value else '')
    return student


def format_exemption(value):
    if not value:return ''
    parsed=date.fromisoformat(value)
    return f'至{parsed.month}月{parsed.day}号'


def set_exemption(db,sid,value):
    if value:
        parsed=date.fromisoformat(value)
        if parsed < date.today():raise ValueError('免催日期不能早于今天')
        value=parsed.isoformat()
    with db.connect() as conn:
        if not conn.execute('SELECT 1 FROM class_roster WHERE student_id=?',(sid,)).fetchone():
            raise ValueError('班期学员不存在')
        if value:
            conn.execute('INSERT INTO exemptions VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET exemption_date=excluded.exemption_date',(sid,value))
        else:conn.execute('DELETE FROM exemptions WHERE student_id=?',(sid,))
