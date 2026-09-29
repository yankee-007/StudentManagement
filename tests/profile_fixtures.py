import json
from app.profile_storage import base_fields
from app.profile_fields import canonical_fields


def insert_profile(conn,sid,name,position,fields=None):
    fields=fields or {}
    conn.execute("INSERT OR IGNORE INTO class_roster(student_id,term_id,ordinal,name,status) VALUES(?,'',?,?,'')",(sid,position,name))
    conn.execute('INSERT INTO profiles VALUES(?,?)',(sid,json.dumps(base_fields(fields),ensure_ascii=False)))
    normalized=canonical_fields(fields)
    for d in conn.execute('SELECT * FROM profile_field_definitions').fetchall():
        if normalized.get(d['name']):
            conn.execute('INSERT INTO profile_field_values VALUES(?,?,?)',(sid,d['field_id'],str(normalized[d['name']])))
    system={k:v for k,v in fields.items() if k in {'合计完课','差的课程','合计作业','差的作业'}}
    if system:conn.execute('INSERT OR REPLACE INTO reminder_data(student_id,data) VALUES(?,?)',(sid,json.dumps({'system_fields':system})))


def legacy_profiles(conn):
    conn.execute('DROP TRIGGER IF EXISTS feedback_student_required')
    conn.execute('DROP TABLE profiles')
    conn.execute('CREATE TABLE profiles(student_id TEXT PRIMARY KEY REFERENCES students(student_id),name TEXT NOT NULL,position INTEGER NOT NULL,fields TEXT NOT NULL,sync_state TEXT NOT NULL DEFAULT "尚未获取")')
