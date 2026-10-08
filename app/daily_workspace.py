"""Goal-driven daily work, with evidence-based commitment verification."""
import json
import math
import re
import sqlite3
from contextlib import closing
from datetime import date, datetime
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from .followup_store import FollowupStore, items, now
from .learning_overview import load_batches, integer
from .qt_models import DictTableModel
from .table_query import next_cursor


def item_label(item):
    return f'第{item[1:]}节' + ('课程' if item[0] == 'c' else '作业')


def facts(snapshot, lesson, flags=None):
    if snapshot.get('matched') is False:
        return None
    if flags is not None and all(flags.get(prefix+str(i)) in ('T','F') for prefix in ('c','z') for i in range(1,lesson+1)):
        return {prefix:[prefix+str(i) for i in range(1,lesson+1) if flags[prefix+str(i)]=='F'] for prefix in ('c','z')}
    result = {}
    for key, prefix in (('courses', 'c'), ('homework', 'z')):
        raw = snapshot.get(key)
        count = integer(snapshot.get('completed_' + key), 32)
        if count is None or not isinstance(raw, str) or not re.fullmatch(r'(?:\d+(?:,\d+)*)?', raw):
            return None
        numbers = [int(value) for value in raw.split(',')] if raw else []
        if any(not 1 <= value <= 32 for value in numbers):
            return None
        pending = sorted(set(value for value in numbers if value <= lesson))
        if not pending and count < lesson:
            return None
        result[prefix] = [prefix + str(number) for number in pending]
    return result


def goal_summary(goal, batch):
    point = next((row for row in batch.get('lessons', []) if row['lesson'] == goal.get('lesson')), None)
    total = batch.get('total', 0)
    if not goal or not point or not total:
        return dict(valid=False, metrics=[], notice=batch.get('learningNotice') or '请先建立有效累计批次并保存班级目标', needs={})
    needs = dict(course=max(0, math.ceil(goal['course'] * total / 100 - 1e-9) - point['courseDone']),
                 homework=max(0, math.ceil(goal['homework'] * total / 100 - 1e-9) - point['homeworkDone']),
                 gap=max(0, math.ceil(point['courseDone'] - point['homeworkDone'] - goal['gap'] * total / 100 - 1e-9)))
    metrics = [dict(title=title, value=f'{point[key]:.1f}' + ('pp' if key == 'gap' else '%'),
                    target=str(goal[key]) + ('pp' if key == 'gap' else '%'), need=needs[key])
               for key, title in (('course', '累计完课率'), ('homework', '累计作业率'), ('gap', '差值'))]
    original = set(goal['members'])
    current = {row['student_id'] for row in batch['population']}
    added, removed = len(current - original), len(original - current)
    return dict(valid=True, metrics=metrics, needs=needs, met=not any(needs.values()), total=total,
                notice=('综合目标已达标' if not any(needs.values()) else '三项须同时达标') +
                       (f' · 较周期开始新增{added}人、移出{removed}人；变化包含人员调整' if added or removed else ''),
                added=added, removed=removed, time=batch['time'], deadline=goal['deadline'],
                days=(date.fromisoformat(goal['deadline']) - date.today()).days)


def recommendation(pending, summary):
    if not pending or not summary.get('valid') or summary.get('met'):
        return {}, []
    needs = summary['needs']
    candidates = []
    for chosen in (pending['c'], pending['z'], pending['c'] + pending['z']):
        if not chosen:
            continue
        dc = int(bool(pending['c']) and set(pending['c']).issubset(chosen))
        dh = int(bool(pending['z']) and set(pending['z']).issubset(chosen))
        contribution = int(bool(needs['course']) and dc) + int(bool(needs['homework']) and dh) + int(bool(needs['gap']) and dh > dc)
        if not contribution:
            continue
        gap_priority = 0 if needs['gap'] and dh > dc else 1
        value = dict(items=items(chosen), dc=dc, dh=dh, gap=dc-dh, cost=len(chosen),
                     title='课程与作业一起补齐' if dc and dh else '补齐作业' if dh else '补齐课程',
                     contribution=contribution)
        candidates.append(((len(chosen), gap_priority, -contribution), value))
    candidates.sort(key=lambda candidate: candidate[0])
    return (candidates[0][1] if candidates else {}), [value for _, value in candidates]


class DailyWorkspace(QObject):
    changed = Signal()
    selectionChanged = Signal()
    saved = Signal(str, bool, str)

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._model = DictTableModel([('name', '选择 / 姓名'), ('proposal', '建议 / 承诺'),
                                      ('cost', '待补项数'), ('delta', '补齐后的变化'), ('status', '进度 / 联系资格')], self)
        self._path = ''
        self._goal, self._batch, self._summary = {}, {}, {}
        self._tasks, self._students, self._rows = [], {}, []
        self._frozen, self._checked, self._drafts = [], set(), {}
        self._selected, self._tab, self._search = '', 0, ''
        self._notice, self._active, self._dirty = '', False, True
        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self.reload(True) if self._active else self.invalidate())
        self._timer.start(60000)
        owner.workflow.overviewSourceChanged.connect(self.invalidate)
        self.reload()

    @property
    def store(self):
        return FollowupStore(self.owner.db)

    @Slot()
    def invalidate(self):
        self._dirty = True
        if self._active or str(self.owner.db.path.resolve()) != self._path:
            self.reload(True)
        else:
            self.changed.emit()

    @Slot(bool)
    def setActive(self, active):
        self._active = active
        if active and self._dirty:
            self.reload()

    def reload(self, keep=True):
        path = str(self.owner.db.path.resolve())
        reset = path != self._path
        if reset:
            self._selected, self._tab, self._search = '', 0, ''
            self._checked.clear()
            keep = False
        self._path = path
        self._goal, self._tasks = self.store.goal(), self.store.tasks()
        self._students = {row['student_id']: row for row in self.owner.repo.list_students()}
        learning = self.owner.repo.learning_source()
        try:
            with closing(sqlite3.connect(self.owner.db.path.as_uri() + '?mode=ro', uri=True)) as conn:
                conn.execute('BEGIN')
                batches = load_batches(conn)
            self._batch = batches[0] if batches else {}
        except (sqlite3.Error, ValueError, TypeError):
            self._batch = {}
        self._summary = goal_summary(self._goal, self._batch)
        active = {task['student_id']: task for task in self._tasks if task['lifecycle'] == 'active'}
        population = {row['student_id']: row for row in self._batch.get('population', [])}
        all_ids = list(dict.fromkeys(list(population) + [task['student_id'] for task in self._tasks]))
        current = datetime.now()
        rows = []
        for sid in all_ids:
            snapshot, student, task = population.get(sid, {}), self._students.get(sid, {}), active.get(sid, {})
            flags = learning.get(sid) if snapshot.get('source_sync') and snapshot.get('source_sync') == student.get('last_sync_at') else None
            pending = facts(snapshot, self._goal['lesson'], flags) if self._goal and sid in population else None
            proposal, alternatives = recommendation(pending, self._summary)
            exemption = student.get('exemption_date') or ''
            reason = ('已不在最新批次范围' if sid not in population else
                      '非当前在读学员' if student.get('roster_status') != '在读' or student.get('is_placeholder') else
                      '免催中' if exemption >= date.today().isoformat() else
                      '微信未添加' if student.get('profile_fields', {}).get('微信') != '是' else '')
            overdue = bool(task and datetime.fromisoformat(task['due_at']) <= current)
            due = bool(task and datetime.fromisoformat(task['review_at']) <= current)
            review_needed = due and (not task.get('evidence', {}).get('time') or
                            datetime.fromisoformat(task['evidence']['time']) < datetime.fromisoformat(task['review_at']))
            last = next((value for value in self._tasks if value['student_id'] == sid), {})
            status = task.get('result') or last.get('result') or ('数据未知' if pending is None else '待联系')
            if task or last:
                status = '承诺' + status
            if last.get('lifecycle') == 'cancelled' and not task:
                status = '已取消'
            if overdue: status += ' · 逾期'
            if review_needed: status += ' · 需新数据复查'
            if reason: status += ' · ' + reason
            amount = 100 / self._summary['total'] if self._summary.get('valid') else 0
            delta = (f'完课+{proposal["dc"]*amount:.2f}pp / 作业+{proposal["dh"]*amount:.2f}pp / 差值{proposal["gap"]*amount:+.2f}pp'
                     if proposal else '')
            rows.append(dict(student_id=sid, _record_key=sid, name=student.get('name') or snapshot.get('name') or last.get('name') or sid,
                             pending=pending, recommendation=proposal, alternatives=alternatives, proposal=proposal.get('title') or
                             ('承诺：' + '、'.join(item_label(item) for item in task['items']) if task else ''),
                             cost=proposal.get('cost', ''), delta=delta, status=status, task=task, overdue=overdue,
                             review_needed=review_needed, reason=reason, in_population=sid in population))
        self._rows = sorted(rows, key=lambda row: (row['recommendation'].get('cost', 1000),
                            0 if self._summary.get('needs', {}).get('gap') and row['recommendation'].get('gap', 0) < 0 else 1,
                            -row['recommendation'].get('contribution', 0), row['student_id']))
        self._apply(keep)
        self._dirty = False
        self.changed.emit()
        self.selectionChanged.emit()

    def _matches(self, row):
        return (not self._search or self._search in (row['name'] + ' ' + row['student_id']).lower()) and (
            bool(row['recommendation']) if self._tab == 0 else bool(row['task'] and (row['review_needed'] or row['overdue'])) if self._tab == 1 else True)

    def _apply(self, keep):
        old = list(self._model.rows)
        if not keep:
            self._frozen = [row['student_id'] for row in self._rows if self._matches(row)]
        by_id = {row['student_id']: row for row in self._rows}
        visible = [dict(by_id[sid], _filter_stale=not self._matches(by_id[sid])) for sid in self._frozen if sid in by_id]
        self._model.reconcile_rows(visible)
        keys = {row['student_id'] for row in visible}
        self._checked.intersection_update(keys)
        if self._selected not in keys:
            selected = next_cursor(visible, lambda row: row['student_id'], self._selected, [row['student_id'] for row in old])
            self._selected = selected.get('student_id', '')

    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property('QVariantMap', notify=changed)
    def goal(self): return self._goal
    @Property(str, notify=changed)
    def goalContext(self): return json.dumps([self._path, self._goal.get('id', 0)])
    @Property(str, notify=changed)
    def contactPrefix(self): return self.owner.repo.get_setting('campaign_contact_prefix', self.owner.contactOpener.defaultPrefix)
    @Property('QVariantMap', notify=changed)
    def summary(self):
        return dict(self._summary, reviewCount=sum(bool(row['task'] and (row['review_needed'] or row['overdue'])) for row in self._rows),
                    visibleCount=len(self._model.rows), selectedCount=len(self._checked), notice=self._notice or self._summary.get('notice', ''),
                    cursor=f'正在处理 第{next((i+1 for i,r in enumerate(self._model.rows) if r["student_id"]==self._selected),0)} / {len(self._model.rows)}条')
    @Property('QVariantList', notify=changed)
    def lessonOptions(self): return [dict(value=row['lesson'], label=f'第1～{row["lesson"]}节') for row in self._batch.get('lessons', [])]
    @Property('QVariantList', notify=changed)
    def selectedIds(self): return sorted(self._checked)
    @Property(str, notify=selectionChanged)
    def selectedId(self): return self._selected
    @Property(int, notify=changed)
    def tabIndex(self): return self._tab

    @Slot(int)
    def selectTab(self, index):
        if 0 <= index <= 2 and self.flushEditor():
            self._tab = index
            self._apply(False)
            self.changed.emit(); self.selectionChanged.emit()

    @Slot(str)
    def search(self, text):
        if self.flushEditor():
            self._search = text.strip().lower()
            self._apply(False)
            self.changed.emit(); self.selectionChanged.emit()

    @Slot()
    def reapply(self):
        if self.flushEditor():
            self.reload(False)

    @Slot(int)
    def selectRow(self, index):
        if 0 <= index < len(self._model.rows) and self.flushEditor():
            self._selected = self._model.rows[index]['student_id']
            self.selectionChanged.emit(); self.changed.emit()

    @Slot(str, bool)
    def check(self, sid, checked):
        if sid in {row['student_id'] for row in self._model.rows}:
            if checked: self._checked.add(sid)
            else: self._checked.discard(sid)
            self.changed.emit()

    @Slot(bool)
    def checkAll(self, value):
        self._checked = {row['student_id'] for row in self._model.rows if not row.get('_filter_stale')} if value else set()
        self.changed.emit()

    @Slot(str, result='QVariantMap')
    def detailsFor(self, sid):
        if self._dirty:
            self.reload(True)
        row = next((row for row in self._rows if row['student_id'] == sid), {})
        task = next((task for task in self._tasks if task['student_id'] == sid and task['lifecycle'] == 'active'), {})
        student = self._students.get(sid, {})
        pending = row.get('pending')
        options = sorted(set((pending['c'] + pending['z'] if pending else []) + task.get('items', [])), key=lambda value: (int(value[1:]), value[0]))
        editable = bool(sid and student.get('roster_status') == '在读' and not student.get('is_placeholder') and (pending is not None or task))
        key = json.dumps([self._path, sid, task.get('id', 0), task.get('revision', 0), self._goal.get('id', 0)]) if editable else ''
        events = self.store.events(sid) if sid else []
        history = '\n'.join(event['created_at'][:19].replace('T',' ') + ' · ' + event['kind'] + ' · ' +
                   ('、'.join(item_label(item) for item in event['payload'].get('items', [])) + ' ' +
                    (event['payload'].get('result') or event['payload'].get('reason') or event['payload'].get('due_at') or
                     event['payload'].get('note') or
                     ('名单 #' + str(event['payload']['list_id']) if 'list_id' in event['payload'] else ''))) for event in events)
        sends = []
        group = getattr(self.owner, '_group_center', None)
        if group and sid:
            with group.store.connect() as conn:
                for value in conn.execute('SELECT id,list_id,state,detail,learning_data FROM recipients'):
                    data = json.loads(value['learning_data'] or '{}')
                    if data.get('profile_path') == self._path and data.get('student_id') == sid and data.get('daily_goal_id') is not None:
                        sends.append(f'名单 #{value["list_id"]} · {value["state"]} {value["detail"]}')
        return dict(row, key=key, editable=editable, task=task, options=[dict(key=item, label=item_label(item)) for item in options],
                    selectedItems=task.get('items') or (pending['c'] + pending['z'] if pending else []),
                    history=history, sends='\n'.join(sends[-10:]), profile=' · '.join(str(student.get('profile_fields', {}).get(k) or '') for k in ('学习目的','学习计划') if student.get('profile_fields', {}).get(k)))

    @Slot(str, 'QVariantList', result=str)
    def estimate(self, sid, selected):
        row = next((row for row in self._rows if row['student_id'] == sid), {})
        pending = row.get('pending')
        if pending is None or not self._summary.get('valid'): return '暂无有效数据，不能试算指标贡献'
        dc = int(bool(pending['c']) and set(pending['c']).issubset(selected))
        dh = int(bool(pending['z']) and set(pending['z']).issubset(selected))
        amount = 100/self._summary['total']
        return f'当前选择全部完成后：完课+{dc*amount:.2f}pp，作业+{dh*amount:.2f}pp，差值{(dc-dh)*amount:+.2f}pp。部分补齐不一定增加累计人数。'

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def saveContactNote(self, key, text, editor=''):
        try:
            sid, task_id, _, _, _ = self._context(key)
            if not text.strip(): raise ValueError('请填写联系记录')
            self.store.bootstrap()
            with self.owner.db.connect() as conn:
                self.store.event(conn, task_id, sid, '联系记录', dict(note=text.strip()))
            self.discardDraft(key, editor)
            self._notice = '联系记录已保存，未登记新的承诺'
            self.reload(True)
            self.saved.emit(key, True, editor)
            return True
        except (ValueError, TypeError, sqlite3.Error, OSError) as exc:
            self._notice = str(exc); self.changed.emit(); return False

    def _context(self, key):
        path, sid, task_id, revision, goal_id = json.loads(key)
        current = self.store.goal()
        if path != str(self.owner.db.path.resolve()) or goal_id != current.get('id', 0):
            raise ValueError('班级或目标已变化，输入已保留')
        student = self.owner.repo.get(sid)
        if not student or student.get('is_placeholder') or student.get('roster_status') != '在读':
            raise ValueError('该学员已不属于当前在读真实学员')
        return sid, task_id, revision, goal_id, student

    @Slot(str, 'QVariantMap', result=bool)
    @Slot(str, 'QVariantMap', str, result=bool)
    def queueDraft(self, key, values, editor=''):
        if not key: return False
        self._drafts[editor or key] = dict(key=key, values=dict(values))
        return True

    @Slot(str)
    @Slot(str, str)
    def discardDraft(self, key, editor=''):
        for token, draft in list(self._drafts.items()):
            if draft['key'] == key and (not editor or token == editor):
                self._drafts.pop(token, None)

    @Slot(str, result=bool)
    @Slot(str, str, result=bool)
    def hasDraft(self, key, editor=''):
        return any(draft['key']==key and (not editor or token==editor) for token,draft in self._drafts.items())

    @Slot(result=bool)
    def flushEditor(self):
        for editor, draft in list(self._drafts.items()):
            if not self.saveCommitment(draft['key'], draft['values'], editor): return False
        return True

    @Slot(str, 'QVariantMap', result=bool)
    @Slot(str, 'QVariantMap', str, result=bool)
    def saveCommitment(self, key, values, editor=''):
        try:
            sid, task_id, revision, goal_id, student = self._context(key)
            selected = items(list(values.get('items', [])))
            allowed = {value['key'] for value in self.detailsFor(sid)['options']}
            if not set(selected).issubset(allowed): raise ValueError('项目已变化，请重新检查欠交数据')
            self.store.save_task(sid, student['name'], goal_id, selected, values.get('due_at', ''),
                                 values.get('review_at', ''), values.get('note', ''), task_id, revision)
            self._drafts.pop(editor or key, None)
            self._notice = '承诺已保存；完成情况以之后的平台数据核验'
            self.reload(True); self.saved.emit(key, True, editor)
            return True
        except (ValueError, TypeError, KeyError, sqlite3.Error, OSError) as exc:
            self._notice = '保存失败：' + str(exc)
            self.changed.emit(); self.saved.emit(key, False, editor)
            return False

    @Slot('QVariantMap', result=bool)
    def saveGoal(self, values):
        try:
            if values.get('context') != self.goalContext:
                raise ValueError('班级或目标已变化，请重新打开目标设置')
            if not self.flushEditor(): return False
            if int(values.get('lesson', 0)) not in [row['lesson'] for row in self._batch.get('lessons', [])]:
                raise ValueError('请选择有效累计节次；无有效批次时请先新建催办')
            self.store.save_goal(dict(values), [row['student_id'] for row in self._batch['population']])
            self._notice = '班级目标已保存'
            self.reload(False)
            return True
        except (ValueError, TypeError, KeyError, sqlite3.Error, OSError) as exc:
            self._notice = str(exc); self.changed.emit(); return False

    @Slot(str, str, result=bool)
    @Slot(str, str, str, result=bool)
    def cancelTask(self, key, reason, editor=''):
        try:
            sid, task_id, revision, _, _ = self._context(key)
            self.store.cancel(task_id, revision, reason)
            self.discardDraft(key, editor)
            self._notice = '承诺已取消，历史保留'
            self.reload(True)
            return True
        except (ValueError, TypeError, sqlite3.Error) as exc:
            self._notice = str(exc); self.changed.emit(); return False

    def after_fetch(self, returned_rows, started_at=None):
        names = {str(row['学号']): str(row['姓名']) for row in returned_rows}
        records = {}
        completed_at = now()
        with self.owner.db.connect() as conn:
            for row in conn.execute('SELECT d.student_id,d.flags,d.data,r.name FROM reminder_data d JOIN class_roster r USING(student_id) WHERE d.matched=1'):
                if names.get(row['student_id']) == row['name']:
                    records[row['student_id']] = dict(flags=json.loads(row['flags']), time=completed_at,
                        started_at=started_at or completed_at, source_time=json.loads(row['data']).get('last_sync_at', ''))
        self.store.verify(records)
        self._notice = f'本次核验采用实际返回的{len(records)}名匹配学员；未返回者保留原结果'
        self.reload(False)

    @Slot(result='QVariantMap')
    def listPreview(self):
        included, excluded = [], []
        for row in self._model.rows:
            if row['student_id'] not in self._checked: continue
            reason = '已不符合当前筛选' if row.get('_filter_stale') else row['reason']
            if not row.get('task') and not row.get('recommendation'): reason = reason or '没有待跟进项目'
            (excluded if reason else included).append(dict(student_id=row['student_id'], name=row['name'], reason=reason))
        keys = [self._list_key(row['student_id']) for row in included]
        return dict(included=included, excluded=excluded, keys=keys,
                    description='纳入：' + '、'.join(row['name'] for row in included) +
                    '\n排除：' + '；'.join(row['name']+'（'+row['reason']+'）' for row in excluded))

    def _list_key(self, sid):
        row = next(row for row in self._rows if row['student_id'] == sid)
        task = row['task']
        return json.dumps([self._path, self._goal.get('id', 0), self._batch.get('id'), self._batch.get('time'), sid,
                           task.get('id'), task.get('revision'), row['recommendation'].get('items'), row['reason']])

    def build_people(self, fields, keys):
        from .message_content import render_content
        if not self.flushEditor(): raise ValueError('请先完成承诺保存')
        self.reload(True)
        preview = self.listPreview()
        if list(keys) != preview['keys']: raise ValueError('人员、筛选或承诺已变化，请重新预览名单')
        people = []
        for row in preview['included']:
            detail = self.detailsFor(row['student_id'])
            task = detail['task']
            selected = task.get('items') or detail['recommendation'].get('items', [])
            variables = dict(self._students[row['student_id']].get('profile_fields') or {})
            variables.update({'学号':row['student_id'], '班期':self.owner.workflow.className,
                              '承诺项目':'、'.join(item_label(item) for item in selected), '期限':task.get('due_at') or self._goal.get('deadline', '')})
            people.append(dict(name=row['name'], content=render_content(fields, row['name'], variables=variables),
                               learning_data=dict(student_id=row['student_id'], profile_path=self._path,
                                  daily_goal_id=self._goal.get('id', 0), task_id=task.get('id'), task_revision=task.get('revision'), profile_fields=variables)))
        return people
