"""Term-specific roster storage. Placeholders never become real students."""
import json
import re
from datetime import datetime

COLUMNS = [('ordinal','序号'), ('student_id','学员学号'), ('name','学员姓名'),
           ('status','状态'), ('student_type','类型'), ('nickname','昵称')]


def display_row(row):
    """Normalize old caches too; keep source metadata out of all visible columns."""
    result = dict(row)
    for key, _ in COLUMNS:
        if key != 'student_id' and row.get('source') == '缺号补位':
            result[key] = '已退课' if key == 'status' else ''
        elif result.get(key) is None:
            result[key] = ''
    return result


def arrange_students(term_no, students):
    if not re.fullmatch(r'P\d{7}', term_no):
        raise ValueError('班期编号不符合 P年份+三位班期规则，未生成补位学号。')
    pattern = re.compile(re.escape(term_no) + r'(\d{3})([A-E])')
    slots, ids = {}, set()
    for row in students:
        sid = row['student_id']
        match = pattern.fullmatch(sid)
        if not match or int(match[1]) == 0:
            raise ValueError(f'学号格式或所属班期不一致：{sid}；原名单未覆盖。')
        if sid in ids:
            raise ValueError(f'接口返回重复学号：{sid}；原名单未覆盖。')
        ids.add(sid)
        ordinal = int(match[1])
        slots.setdefault(ordinal, []).append(dict(student_id=sid, name=row.get('name',''),
                                                  ordinal=ordinal, source='接口学员',
                                                  status=row.get('status',''),
                                                  student_type=row.get('student_type',''),
                                                  nickname=row.get('nickname','')))
    result, previous_letter = [], 'A'
    for ordinal in range(1, max(slots, default=0) + 1):
        if ordinal in slots:
            ordered = sorted(slots[ordinal], key=lambda r:r['student_id'])
            result.extend(ordered)
            previous_letter = ordered[-1]['student_id'][-1]
        else:
            result.append(dict(ordinal=ordinal, student_id=f'{term_no}{ordinal:03d}{previous_letter}',
                               name='', source='缺号补位'))
    return [display_row(row) for row in result]


class TermRosterStore:
    def __init__(self, db):
        self.db = db
        with db.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS term_rosters (
                term_id TEXT PRIMARY KEY, term_json TEXT NOT NULL,
                rows_json TEXT NOT NULL, resource_id TEXT NOT NULL, fetched_at TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS term_lessons (
                term_id TEXT PRIMARY KEY, lessons_json TEXT NOT NULL,
                resource_id TEXT NOT NULL, fetched_at TEXT NOT NULL)''')

    def save_lessons(self, term_id, lessons, resource_id=''):
        with self.db.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO term_lessons VALUES(?,?,?,?)',
                         (str(term_id), json.dumps(lessons, ensure_ascii=False), resource_id,
                          datetime.now().isoformat(timespec='seconds')))

    def load_lessons(self, term_id):
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM term_lessons WHERE term_id=?', (str(term_id),)).fetchone()
        return dict(lessons=json.loads(row['lessons_json']), resource_id=row['resource_id'],
                    fetched_at=row['fetched_at']) if row else dict(lessons=[],resource_id='',fetched_at='')

    def save(self, term, students, resource_id):
        rows = arrange_students(term['termNo'], students)
        if not students and self.load(term['termId'])['rows']:
            raise ValueError('本次返回空名单，已保留上次名单，请检查课程选择。')
        with self.db.connect() as conn:
            conn.execute('INSERT OR REPLACE INTO term_rosters VALUES(?,?,?,?,?)',
                (str(term['termId']),json.dumps(term,ensure_ascii=False),
                 json.dumps(rows,ensure_ascii=False),resource_id,datetime.now().isoformat(timespec='seconds')))
        return self.load(term['termId'])

    def load(self, term_id):
        with self.db.connect() as conn:
            row = conn.execute('SELECT * FROM term_rosters WHERE term_id=?',(str(term_id),)).fetchone()
        return dict(rows=[display_row(r) for r in json.loads(row['rows_json'])], fetched_at=row['fetched_at'],
                    resource_id=row['resource_id']) if row else dict(rows=[],fetched_at='',resource_id='')
