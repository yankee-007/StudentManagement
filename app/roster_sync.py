"""Auto-provision term-backed classes and join independent tables by student ID."""
import hashlib
import json
from datetime import datetime

from .database import Database
from .repository import StudentRepository
from .profile_fields import DISPLAY_LABELS, PROFILE_INPUT_LABELS
from .profile_storage import base_fields

INPUT_LABELS = PROFILE_INPUT_LABELS


def match_entry(entries, term):
    tid, prefix = str(term['termId']), term['termNo']
    bound = next((e for e in entries if str(e.get('term_id','')) == tid), None)
    if bound: return bound
    aliases = {str(term.get(k,'')).casefold().replace('期','') for k in ('termAlias','termName','termNo')}
    aliases.add('py'+str(int(prefix[-3:])))
    candidates = []
    for entry in entries:
        if entry.get('term_id'): continue
        db = Database(entry['path'])
        with db.connect() as conn:
            ids = [r[0] for r in conn.execute('SELECT student_id FROM profiles')]
        alias_match = entry['name'].casefold().replace('期','') in aliases
        if alias_match and ids and not all(sid.startswith(prefix) for sid in ids):
            # A display-name coincidence must not reassign another class's profiles.
            continue
        if alias_match or (ids and all(sid.startswith(prefix) for sid in ids)): candidates.append(entry)
    if len(candidates) > 1:
        raise ValueError(f"{term['termName']} 对应多个已有名单，需先确认映射，未合并")
    if not candidates:
        # A brand-new registry database doubles as the first class database.
        # Reuse it only while it has no identities or campaign history.
        for entry in entries:
            if entry.get('term_id') or entry['name'] != '当前班级':
                continue
            with Database(entry['path']).connect() as conn:
                empty = not conn.execute('SELECT 1 FROM profiles LIMIT 1').fetchone() and not conn.execute('SELECT 1 FROM campaigns LIMIT 1').fetchone()
            if empty:
                return entry
    return candidates[0] if candidates else None


def ensure_classes(registry, entries, terms):
    result = [dict(e) for e in entries]
    for term in terms:
        entry = match_entry(result, term)
        if entry is None:
            path = registry.db.path.parent / f"class_term_{term['termId']}.db"
            entry = dict(name=term['termName'],path=str(path))
            result.append(entry)
        entry.update(term_id=str(term['termId']),term_no=term['termNo'],name=term['termName'])
        repo = StudentRepository(Database(entry['path']))
        previous = repo.get_setting('term_id')
        if previous and previous != entry['term_id']:
            raise ValueError('班期数据库映射冲突，未覆盖已有数据')
        repo.set_setting('term_id',entry['term_id'])
        repo.set_setting('class_name',entry['name'])
    registry.set_setting('workflow_classes',json.dumps(result,ensure_ascii=False))
    return result


def sync_roster(db, term, rows):
    repo = StudentRepository(db)
    bound = repo.get_setting('term_id')
    if bound and bound != str(term['termId']):
        raise ValueError('班期与目标数据库不一致，未写入学员名单')
    ids = [row['student_id'] for row in rows]
    if len(ids) != len(set(ids)) or any(not sid.startswith(term['termNo']) for sid in ids):
        raise ValueError('学员名单包含其他班期学号或重复学号，未更新')
    signature = hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    if repo.get_setting('roster_signature') == signature: return False
    now = datetime.now().isoformat(timespec='seconds')
    with db.connect() as conn:
        previous = {r['student_id']:dict(r) for r in conn.execute('SELECT * FROM profiles')}
        conn.execute('UPDATE class_roster SET active=0')
        headers = []
        for position,row in enumerate(rows):
            sid = row['student_id']
            placeholder = row['source'] == '缺号补位'
            fields = base_fields(json.loads(previous[sid]['fields']) if sid in previous else {})
            conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?) ON CONFLICT(student_id) DO UPDATE SET name=excluded.name',
                         (sid,row['name'],now))
            conn.execute('''INSERT INTO class_roster VALUES(?,?,?,?,?,?,?,?,1)
                         ON CONFLICT(student_id) DO UPDATE SET term_id=excluded.term_id,ordinal=excluded.ordinal,
                         name=excluded.name,status=excluded.status,student_type=excluded.student_type,
                         nickname=excluded.nickname,is_placeholder=excluded.is_placeholder,active=1''',
                         (sid,str(term['termId']),int(sid[len(term['termNo']):len(term['termNo'])+3]),row['name'],
                          '已退课' if placeholder else row.get('status',''),row.get('student_type',''),row.get('nickname',''),int(placeholder)))
            conn.execute('INSERT OR IGNORE INTO profiles(student_id,fields) VALUES(?,?)',
                         (sid,json.dumps(fields,ensure_ascii=False)))
            conn.execute('INSERT OR IGNORE INTO reminder_data(student_id) VALUES(?)',(sid,))
            for key in fields:
                if key not in headers: headers.append(key)
        for key,value in [('roster_managed','1'),('roster_signature',signature),('profile_headers',json.dumps(headers,ensure_ascii=False))]:
            conn.execute('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
    return True
