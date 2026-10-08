"""Per-class goals and commitments, independent of campaign snapshots."""
import json
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path
from contextlib import closing


def now():
    return datetime.now().isoformat(timespec='microseconds')


def timestamp(value):
    text = str(value).strip().replace(' ', 'T')
    if 'T' not in text:
        raise ValueError('请填写日期和时间，例如2026-10-12 20:00')
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        raise ValueError('请使用本机日期和时间')
    return parsed.isoformat(timespec='seconds')


def items(value):
    if not isinstance(value, list) or not value:
        raise ValueError('请至少选择一项课程或作业')
    result = []
    for item in value:
        if not isinstance(item, str) or item[:1] not in ('c', 'z') or not item[1:].isdigit():
            raise ValueError('承诺项目无效')
        number = int(item[1:])
        if not 1 <= number <= 32 or item != item[0] + str(number):
            raise ValueError('承诺节次无效')
        if item not in result:
            result.append(item)
    return sorted(result, key=lambda item: (int(item[1:]), item[0]))


def decode(row):
    if row is None:
        return {}
    result = dict(row)
    for key in ('members', 'items', 'evidence', 'payload'):
        if key in result:
            result[key] = json.loads(result[key])
    return result


SCHEMA = '''
CREATE TABLE IF NOT EXISTS daily_goals (
 id INTEGER PRIMARY KEY, lesson INTEGER NOT NULL, course REAL NOT NULL,
 homework REAL NOT NULL, gap REAL NOT NULL, deadline TEXT NOT NULL,
 members TEXT NOT NULL, lifecycle TEXT NOT NULL DEFAULT 'active',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS daily_one_goal ON daily_goals(lifecycle) WHERE lifecycle='active';
CREATE TABLE IF NOT EXISTS daily_tasks (
 id INTEGER PRIMARY KEY, student_id TEXT NOT NULL, name TEXT NOT NULL,
 goal_id INTEGER REFERENCES daily_goals(id), items TEXT NOT NULL,
 due_at TEXT NOT NULL, review_at TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
 revision INTEGER NOT NULL, lifecycle TEXT NOT NULL DEFAULT 'active',
 result TEXT NOT NULL DEFAULT '待核验', evidence TEXT NOT NULL DEFAULT '{}',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS daily_one_task ON daily_tasks(student_id) WHERE lifecycle='active';
CREATE TABLE IF NOT EXISTS daily_events (
 id INTEGER PRIMARY KEY, task_id INTEGER REFERENCES daily_tasks(id),
 student_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
 created_at TEXT NOT NULL, payload TEXT NOT NULL);
'''


class FollowupStore:
    def __init__(self, db):
        self.db = db

    def _exists(self, conn):
        return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE name='daily_goals'").fetchone())

    def bootstrap(self):
        # Read paths do not migrate. Back up populated databases once before adding tables.
        with self.db.connect() as conn:
            if self._exists(conn):
                return
            populated = conn.execute('SELECT count(*) FROM students').fetchone()[0]
            if populated:
                path = Path(str(self.db.path) + '.before-daily-workspace.bak')
                if path.exists():
                    path = path.with_name(path.name + '.' + datetime.now().strftime('%Y%m%d%H%M%S%f'))
                with closing(sqlite3.connect(path)) as backup:
                    conn.backup(backup)
            conn.executescript('BEGIN;\n' + SCHEMA + '\nCOMMIT;')

    def goal(self):
        with self.db.connect() as conn:
            return decode(conn.execute("SELECT * FROM daily_goals WHERE lifecycle='active'").fetchone()) if self._exists(conn) else {}

    def tasks(self):
        with self.db.connect() as conn:
            return [decode(row) for row in conn.execute('SELECT * FROM daily_tasks ORDER BY id DESC')] if self._exists(conn) else []

    def events(self, sid):
        with self.db.connect() as conn:
            return [decode(row) for row in conn.execute('SELECT * FROM daily_events WHERE student_id=? ORDER BY id DESC', (sid,))] if self._exists(conn) else []

    @staticmethod
    def event(conn, task, sid, kind, payload):
        conn.execute('INSERT INTO daily_events(task_id,student_id,kind,created_at,payload) VALUES(?,?,?,?,?)',
                     (task or None, sid, kind, now(), json.dumps(payload, ensure_ascii=False)))

    def save_goal(self, values, members):
        try:
            lesson = int(values['lesson'])
            course, homework, gap = (float(values[key]) for key in ('course', 'homework', 'gap'))
            deadline = date.fromisoformat(values['deadline']).isoformat()
        except (KeyError, ValueError, TypeError):
            raise ValueError('请填写有效节次、百分比和考核日期')
        if not 1 <= lesson <= 32 or not all(math.isfinite(v) and 0 <= v <= 100 for v in (course, homework)) or gap not in (5, 10, 15):
            raise ValueError('百分比须为0～100，差值请选择5/10/15pp')
        self.bootstrap()
        stamp = now()
        with self.db.connect() as conn:
            current = conn.execute("SELECT * FROM daily_goals WHERE lifecycle='active'").fetchone()
            if current and current['lesson'] == lesson:
                conn.execute('UPDATE daily_goals SET course=?,homework=?,gap=?,deadline=?,updated_at=? WHERE id=?',
                             (course, homework, gap, deadline, stamp, current['id']))
            else:
                conn.execute("UPDATE daily_goals SET lifecycle='archived' WHERE lifecycle='active'")
                conn.execute('INSERT INTO daily_goals(lesson,course,homework,gap,deadline,members,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                             (lesson, course, homework, gap, deadline, json.dumps(sorted(members)), stamp, stamp))
        return self.goal()

    def save_task(self, sid, name, goal_id, selected_items, due, review, note, task_id=0, revision=0):
        selected_items = items(selected_items)
        due, review = timestamp(due), timestamp(review or due)
        self.bootstrap()
        stamp = now()
        with self.db.connect() as conn:
            current = conn.execute("SELECT * FROM daily_tasks WHERE student_id=? AND lifecycle='active'", (sid,)).fetchone()
            if current:
                if current['id'] != task_id or current['revision'] != revision:
                    raise ValueError('承诺已变化，请重新载入；输入已保留')
                changed = json.loads(current['items']) != selected_items or current['due_at'] != due or current['review_at'] != review
                conn.execute('UPDATE daily_tasks SET items=?,due_at=?,review_at=?,note=?,revision=revision+1,updated_at=?,result=?,evidence=? WHERE id=?',
                             (json.dumps(selected_items), due, review, note.strip(), stamp if changed else current['updated_at'],
                              '待核验' if changed else current['result'], '{}' if changed else current['evidence'], current['id']))
                task_id = current['id']
            else:
                if task_id or revision:
                    raise ValueError('该承诺已结束，请重新载入')
                task_id = conn.execute('INSERT INTO daily_tasks(student_id,name,goal_id,items,due_at,review_at,note,revision,created_at,updated_at) VALUES(?,?,?,?,?,?,?,1,?,?)',
                                       (sid, name, goal_id or None, json.dumps(selected_items), due, review, note.strip(), stamp, stamp)).lastrowid
            self.event(conn, task_id, sid, '登记承诺', dict(items=selected_items, due_at=due, review_at=review, note=note.strip()))
        return task_id

    def cancel(self, task_id, revision, reason):
        if not reason.strip():
            raise ValueError('请填写取消原因')
        with self.db.connect() as conn:
            task = conn.execute("SELECT * FROM daily_tasks WHERE id=? AND revision=? AND lifecycle='active'", (task_id, revision)).fetchone()
            if not task:
                raise ValueError('承诺已变化，请重新载入')
            conn.execute("UPDATE daily_tasks SET lifecycle='cancelled',revision=revision+1 WHERE id=?", (task_id,))
            self.event(conn, task_id, task['student_id'], '取消承诺', dict(reason=reason.strip()))

    def verify(self, records):
        """records contains only matched students actually returned by a successful fetch."""
        tasks = [task for task in self.tasks() if task['lifecycle'] == 'active']
        if not tasks:
            return 0
        changed = 0
        with self.db.connect() as conn:
            for task in tasks:
                record = records.get(task['student_id'])
                if not record:
                    continue
                stamp = record['time']
                started = record.get('started_at') or stamp
                if not stamp or datetime.fromisoformat(started) <= datetime.fromisoformat(task['updated_at']):
                    continue
                flags = record['flags']
                completed = [item for item in task['items'] if flags.get(item) == 'T']
                unknown = [item for item in task['items'] if flags.get(item) not in ('T', 'F')]
                result = ('待核验' if unknown else '已完成' if len(completed) == len(task['items']) else
                          '部分完成' if completed else '未完成')
                evidence = dict(time=stamp, started_at=started, source_time=record.get('source_time', stamp), completed=completed, unknown=unknown, items=task['items'])
                if task['evidence'] == evidence:
                    continue
                conn.execute('UPDATE daily_tasks SET result=?,evidence=?,lifecycle=?,revision=revision+1 WHERE id=? AND revision=?',
                             (result, json.dumps(evidence), 'completed' if result == '已完成' else 'active', task['id'], task['revision']))
                self.event(conn, task['id'], task['student_id'], '平台核验', dict(result=result, **evidence))
                changed += 1
        return changed

    def link_list(self, people, list_id):
        self.bootstrap()
        with self.db.connect() as conn:
            for person in people:
                data = person['learning_data']
                self.event(conn, data.get('task_id'), data['student_id'], '生成名单', dict(list_id=list_id))
