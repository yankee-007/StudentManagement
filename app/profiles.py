"""Authoritative roster import. Never modify the source workbook."""
import json
from datetime import datetime
from openpyxl import load_workbook
from .profile_fields import REMOVED_FIELDS, canonical_fields
from .profile_storage import base_fields

DEFAULT_LABELS = ['姓名', '合计完课', '差的课程', '合计作业', '差的作业']
SYSTEM_LABELS = {'合计完课', '差的课程', '合计作业', '差的作业'}


def import_profiles(db, path):
    book = load_workbook(path, data_only=True, read_only=True)
    try:
        candidates = []
        for sheet in book:
            rows = list(sheet.values)
            if rows and '学号' in rows[0] and ('学员姓名' in rows[0] or '姓名' in rows[0]):
                candidates.append(rows)
        if len(candidates) != 1:
            raise ValueError('画像表必须有且仅有一个包含学号和姓名的名单工作表')
        rows = candidates[0]
        headers = [str(v) if v is not None else '' for v in rows[0]]
        labels = [h for h in headers if h and h not in REMOVED_FIELDS]
        if len(labels) != len(set(labels)):
            raise ValueError('画像表存在重复字段名')
        id_col = headers.index('学号')
        name_col = headers.index('学员姓名' if '学员姓名' in headers else '姓名')
        records, seen = [], set()
        for number, row in enumerate(rows[1:], 2):
            if not any(v is not None for v in row):
                continue
            sid, name = str(row[id_col] or '').strip(), str(row[name_col] or '').strip()
            if not sid or sid in seen:
                raise ValueError(f'第 {number} 行学号缺失或重复，未导入')
            if any(v is not None and not headers[i] for i, v in enumerate(row)):
                raise ValueError(f'第 {number} 行存在无标题内容，请先补充字段名')
            seen.add(sid)
            fields = {h: row[i] for i, h in enumerate(headers) if h and h not in REMOVED_FIELDS}
            records.append((sid, name, number, json.dumps(fields, ensure_ascii=False, default=str)))
        if not records:
            raise ValueError('画像名单为空')
        now = datetime.now().isoformat(timespec='seconds')
        with db.connect() as conn:
            if conn.execute('SELECT count(*) FROM profiles').fetchone()[0]:
                raise ValueError('已建立画像名单，为避免覆盖人工内容，暂不允许重复导入')
            for sid, name, position, fields in records:
                original = json.loads(fields)
                manual = canonical_fields(original)
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?) ON CONFLICT(student_id) DO UPDATE SET name=excluded.name', (sid,name,now))
                conn.execute("INSERT OR IGNORE INTO class_roster(student_id,term_id,ordinal,name,status) VALUES(?,'',?,?,'')",(sid,position,name))
                conn.execute('INSERT INTO profiles(student_id,fields) VALUES(?,?)', (sid,json.dumps(base_fields(manual),ensure_ascii=False)))
                for definition in conn.execute('SELECT field_id,name FROM profile_field_definitions').fetchall():
                    value=manual.get(definition['name'],'')
                    if value:conn.execute('INSERT INTO profile_field_values VALUES(?,?,?)',(sid,definition['field_id'],str(value)))
                conn.execute('INSERT INTO reminder_data(student_id,data) VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET data=excluded.data,matched=0',
                             (sid,json.dumps({'system_fields':{k:original[k] for k in SYSTEM_LABELS if k in original}},ensure_ascii=False)))
            conn.execute("INSERT INTO settings(key,value) VALUES('profile_headers',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (json.dumps(labels,ensure_ascii=False),))
            # Old snapshots may come from a different roster; require a fresh matched fetch.
            conn.execute("DELETE FROM settings WHERE key='snapshot'")
        return len(records)
    finally:
        book.close()
