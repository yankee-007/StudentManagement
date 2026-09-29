from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from typing import Any

from .database import Database
from .engine import validate_status
from .profile_fields import CHOICES, DISPLAY_LABELS, REMOVED_FIELDS, PROFILE_INPUT_LABELS, canonical_fields
from .learning_store import overlay
from .profile_storage import apply_exemption, base_fields, definitions, set_exemption
from .profile_fields import BASE_PROFILE_LABELS


JSON_FIELDS = {"pending_courses", "pending_homework", "pending_items", "new_f", "persistent_f", "resolved_f"}
EDITABLE_FIELDS = {"name", "status", "exemption_end", "next_followup_at"}


def _decode(row: Any) -> dict[str, Any]:
    data = dict(row)
    for field in JSON_FIELDS:
        try:
            data[field] = json.loads(data.get(field) or "[]")
        except (TypeError, json.JSONDecodeError):
            data[field] = []

    data["pending_courses_text"] = "、".join(data["pending_courses"])
    data["pending_homework_text"] = "、".join(data["pending_homework"])
    data["pending_items_text"] = "、".join(data["pending_items"])
    return data


class StudentRepository:
    def __init__(self, db: Database):
        self.db = db

    def list_students(self, view: str = "all", search: str = "") -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            reminders = {r['student_id']:r for r in conn.execute('SELECT * FROM reminder_data')}
            membership = {r['student_id']:r for r in conn.execute('SELECT * FROM class_roster')}
            managed = conn.execute("SELECT 1 FROM settings WHERE key='roster_managed' AND value='1'").fetchone()
            rows = [_decode(overlay(r,reminders.get(r['student_id']),membership.get(r['student_id']))) for r in conn.execute("SELECT * FROM students ORDER BY pending_count DESC, name")]
            profiles = list(conn.execute('SELECT p.* FROM profiles p JOIN class_roster r ON r.student_id=p.student_id ORDER BY r.ordinal,p.student_id'))
            extras = {}
            for r in conn.execute('SELECT v.student_id,d.name,v.value FROM profile_field_values v JOIN profile_field_definitions d ON d.field_id=v.field_id'):
                extras.setdefault(r['student_id'],{})[r['name']]=r['value']
            dates = {r['student_id']:r['exemption_date'] for r in conn.execute('SELECT * FROM exemptions')}
            feedback_by_student = {}
            if profiles:
                for item in conn.execute('SELECT student_id,created_at,content FROM learning_feedback ORDER BY id'):
                    feedback_by_student.setdefault(item['student_id'], []).append(item)
        if profiles:
            by_id = {r['student_id']: r for r in rows}
            rows = [self._profile(by_id[p['student_id']], p, feedback_by_student.get(p['student_id'], []),extras.get(p['student_id'],{})) for p in profiles]
        rows = [apply_exemption(r,dates.get(r['student_id'])) for r in rows]
        if managed:
            rows = [r for r in rows if r['student_id'] in membership and membership[r['student_id']]['active']]
        search = search.strip().lower()
        snapshot = self.get_setting('snapshot')
        if snapshot and not profiles:
            active_ids = {r['student_id'] for r in json.loads(snapshot)}
            rows = [r for r in rows if r['student_id'] in active_ids]
        if search:
            rows = [r for r in rows if search in f"{r['student_id']} {r['name']}".lower()]
        return rows

    def get(self, student_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM students WHERE student_id=?", (student_id,)).fetchone()
            profile = conn.execute('SELECT * FROM profiles WHERE student_id=?', (student_id,)).fetchone()
            reminder = conn.execute('SELECT * FROM reminder_data WHERE student_id=?',(student_id,)).fetchone()
            membership = conn.execute('SELECT * FROM class_roster WHERE student_id=?',(student_id,)).fetchone()
            exemption = conn.execute('SELECT exemption_date FROM exemptions WHERE student_id=?',(student_id,)).fetchone()
        decoded = _decode(overlay(row,reminder,membership)) if row else None
        if decoded:apply_exemption(decoded,exemption[0] if exemption else '')
        return self._profile(decoded, profile) if decoded and profile else decoded

    def _profile(self, data, profile, feedback=None, extras=None):
        fields = json.loads(profile['fields'])
        if extras is None:
            with self.db.connect() as conn:
                extras = {r['name']:r['value'] for r in conn.execute('SELECT d.name,v.value FROM profile_field_values v JOIN profile_field_definitions d ON d.field_id=v.field_id WHERE student_id=?',(data['student_id'],))}
        fields.update(extras)
        fields.update(data.get('system_fields',{}))
        data['profile_fields'] = fields
        data['sync_state'] = data.get('sync_state','尚未获取')
        data.update({'profile:' + k: v for k, v in fields.items()})
        if feedback is None:
            with self.db.connect() as conn:
                feedback = list(conn.execute('SELECT created_at,content FROM learning_feedback WHERE student_id=? ORDER BY id', (data['student_id'],)))
        for entry in feedback:
            key = 'feedback:' + entry['created_at'][:10]
            data[key] = (data.get(key, '') + '\n' + entry['created_at'][11:] + ' ' + entry['content']).strip()
        data['feedback_history'] = '\n'.join(r['created_at'].replace('T',' ') + ' ' + r['content'] for r in feedback)
        return data

    def add_feedback(self, student_id, content):
        if not content.strip():
            raise ValueError('请填写学习反馈')
        created_at = datetime.now().isoformat(timespec='seconds')
        with self.db.connect() as conn:
            if not conn.execute('SELECT 1 FROM profiles WHERE student_id=?', (student_id,)).fetchone():
                raise ValueError('请先导入画像名单')
            cursor = conn.execute('INSERT INTO learning_feedback(student_id,created_at,content) VALUES(?,?,?)', (student_id, created_at, content.strip()))
            # Draft cleanup and append are atomic. No student/profile row is written.
            conn.execute('DELETE FROM settings WHERE key=?', ('feedback_draft:' + student_id,))
            return {'id':cursor.lastrowid, 'student_id':student_id, 'created_at':created_at, 'content':content.strip()}

    def update_profile_field(self, student_id, label, value):
        from .profiles import SYSTEM_LABELS
        extra = next((r for r in definitions(self.db) if r['name']==label),None)
        if label not in BASE_PROFILE_LABELS and extra is None:
            raise ValueError('该字段已删除或属于只读身份字段')
        if label in REMOVED_FIELDS:
            raise ValueError('该字段已删除')
        if label in CHOICES and value not in CHOICES[label]:
            raise ValueError('请从下拉框选择有效选项，可留空')
        if label in SYSTEM_LABELS or label in {'学号', '学员姓名', '姓名'} or '学员学习反馈' in label:
            raise ValueError('身份、学习数据及历史反馈不可在此修改')
        with self.db.connect() as conn:
            row = conn.execute('SELECT fields FROM profiles WHERE student_id=?', (student_id,)).fetchone()
            if not row:
                raise ValueError('画像不存在')
            if extra:
                if extra['kind']=='date' and value:
                    try:value=date.fromisoformat(value).isoformat()
                    except ValueError:raise ValueError('请选择有效日期')
                if extra['kind']=='choice' and value and value not in extra['options']:
                    raise ValueError('请从下拉框选择有效选项')
                conn.execute('INSERT INTO profile_field_values VALUES(?,?,?) ON CONFLICT(student_id,field_id) DO UPDATE SET value=excluded.value',(student_id,extra['field_id'],value))
            else:
                fields = base_fields(json.loads(row[0]))
                fields[label] = value
                conn.execute('UPDATE profiles SET fields=? WHERE student_id=?', (json.dumps(fields,ensure_ascii=False),student_id))

    def profile_columns(self):
        headers = json.loads(self.get_setting('profile_headers', '[]'))
        if not headers:
            return []
        first = [('name','姓名')] + [('profile:' + h,h) for h in ('合计完课','差的课程','合计作业','差的作业')]
        rest = [('student_id','学号')] + [('profile:' + h,DISPLAY_LABELS.get(h,h)) for h in headers if h not in {'学号','姓名','学员姓名','合计完课','差的课程','合计作业','差的作业'} | REMOVED_FIELDS]
        with self.db.connect() as conn:
            dates = [r[0] for r in conn.execute('SELECT DISTINCT substr(created_at,1,10) FROM learning_feedback ORDER BY 1')]
        return first + rest + [('feedback:' + d, '学员学习反馈（' + d + '）') for d in dates] + [('sync_state','数据匹配')]

    def update_manual(self, student_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        current = self.get(student_id)
        if not current:
            raise ValueError("学员不存在")
        if 'status' in changes and changes['status'] not in ('正常','请假'):
            raise ValueError('状态只能为正常或请假')
        if changes.get('status')=='正常':
            set_exemption(self.db,student_id,'')
        elif 'exemption_end' in changes or changes.get('status')=='请假':
            value=changes.get('exemption_end',current.get('exemption_end',''))
            if not value:raise ValueError('请选择免催日期')
            set_exemption(self.db,student_id,value)
        return self.get(student_id)

    def get_setting(self, key: str, default: str = "") -> str:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.db.connect() as conn:
            conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            if key == 'snapshot':
                conn.execute('UPDATE reminder_data SET matched=0')
                for row in json.loads(value):
                    if conn.execute('SELECT 1 FROM students WHERE student_id=?',(row['student_id'],)).fetchone():
                        conn.execute('INSERT INTO reminder_data(student_id,flags,matched) VALUES(?,?,1) ON CONFLICT(student_id) DO UPDATE SET flags=excluded.flags,matched=1',
                                     (row['student_id'],json.dumps(row['flags'])))

    def learning_source(self):
        with self.db.connect() as conn:
            return {r['student_id']:json.loads(r['flags']) for r in conn.execute('SELECT student_id,flags FROM reminder_data WHERE matched=1')}
