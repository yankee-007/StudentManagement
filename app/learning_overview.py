"""Read-only batch aggregates and independent learning overview selections.

Never use Workflow's filtered/live rows: members and learning come from the
saved batch, while manual follow-up marks remain independent of feedback.
"""
import json
import math
import re
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot


def integer(value, maximum=None):
    if isinstance(value, bool) or not re.fullmatch(r'\d+', str(value)):
        return None
    number = int(value)
    return number if maximum is None or number <= maximum else None


def object_json(raw):
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def grade(gap):
    return '优秀' if gap <= 5 else '良好' if gap <= 10 else '及格' if gap <= 15 else '不合格'


def fmt(value, suffix='', signed=False):
    if value is None:
        return '—'
    return (f'{value:+.2f}' if signed else f'{value:.2f}') + suffix


def aggregate_batch(batch_id, stamp, data, records, marks):
    population = [(sid, snap) for sid, snap in records
                  if snap.get('roster_status') == '在读' and not snap.get('is_placeholder')]
    total = len(population)
    counts, followable = Counter(), Counter()
    unknown = 0
    for sid, snap in population:
        value = snap.get('completed_courses')
        if 'completed_courses' not in snap:
            legacy = re.fullmatch(r'(\d+)/\d+', str(snap.get('completed_total', '')))
            value = legacy.group(1) if legacy else None
        count = integer(value, 32)
        if count is None:
            unknown += 1
            continue
        counts[count] += 1
        if marks.get(sid) == '是':
            followable[count] += 1
    yes = sum(marks.get(sid) == '是' for sid, _ in population)
    no = sum(marks.get(sid) == '否' for sid, _ in population)
    summary = dict(total=total, marked=yes + no, yes=yes, no=no, unmarked=total-yes-no)
    def lesson_rows(key):
        rows = data.get(key)
        return {integer(r.get('lesson'), 32): r for r in rows if isinstance(r, dict)} if isinstance(rows, list) else {}
    courses, homework = lesson_rows('courses'), lesson_rows('homework')
    opened = max([integer(data.get('opened'), 32) or 0] + [k for k in courses if k])
    completion = []
    cumulative = 0
    if counts:
        for count in range(max(opened, max(counts)), -1, -1):
            cumulative += counts[count]
            completion.append(dict(count=count, people=counts[count], cumulative=cumulative,
                                   ratio=100*counts[count]/total, cumulativeRate=100*cumulative/total,
                                   followable=followable[count] if yes+no else None))
    lessons = []
    notice = ''
    if integer(data.get('version', 1)) is None or int(data.get('version', 1)) < 2:
        notice = '本批次未保存有效累计快照，旧单节数据不能还原第1～N节累计率。'
    elif data.get('total') != total:
        notice = f'原累计看板按{data.get("total", "未知")}人保存，成员快照在读为{total}人；累计指标暂停展示，原记录保留。'
    elif total:
        for lesson in sorted(k for k in courses if k and k in homework):
            c, h = courses[lesson], homework[lesson]
            cd, hd = integer(c.get('completed'), total), integer(h.get('completed'), total)
            if cd is None or hd is None:
                continue
            try:
                cr, hr = float(c['completedRate'].rstrip('%')), float(h['completedRate'].rstrip('%'))
                if not all(math.isfinite(r) and 0 <= r <= 100 for r in (cr, hr)):
                    continue
                if abs(cr-100*cd/total) > .011 or abs(hr-100*hd/total) > .011:
                    continue
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
            lessons.append(dict(lesson=lesson, course=100*cd/total, homework=100*hd/total,
                                gap=100*(cd-hd)/total, courseDone=cd, homeworkDone=hd))
        if not lessons:
            notice = '本批次暂无双方有效的已开课累计节次；缺失指标不估算。'
    else:
        notice = '本批次暂无在读非补位学员。'
    completion_notice = '完课次数读取本批成员保存的完成计数；人数为恰好k节，完课人数为完成不少于k节。'
    if unknown:
        completion_notice += f' {unknown}人在读学员完成计数未知，不归入0次，仍保留在全班分母中。'
    if not yes+no:
        completion_notice += ' 尚未填写人工标记，可跟进显示 —。'
    elif yes+no < total:
        completion_notice += ' 仅统计已确认是者，未填写不等于否。'
    return dict(id=batch_id, time=stamp, label=f'第{batch_id}次 · {stamp.replace("T", " ")}',
                total=total, members=len(records), lessons=lessons, completion=completion,
                followupSummary=summary, unknown=unknown, learningNotice=notice,
                completionNotice=completion_notice,
                population=[dict(snap, student_id=sid, followup_status=marks.get(sid, ''))
                            for sid, snap in population])


def load_batches(connection):
    """All batch IDs survive missing dashboard rows. SELECT only, no schema writes."""
    tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {'campaigns', 'campaign_students'} <= tables:
        return []
    dashboards = dict(connection.execute('SELECT batch_id,data FROM campaign_dashboards')) if 'campaign_dashboards' in tables else {}
    snapshots, marks = {}, {}
    for batch, sid, name, raw in connection.execute('SELECT batch_id,student_id,name,snapshot FROM campaign_students'):
        snapshots.setdefault(batch, []).append((sid, dict(object_json(raw), name=name)))
    if 'campaign_followup_status' in tables:
        for batch, sid, status in connection.execute('SELECT batch_id,student_id,status FROM campaign_followup_status'):
            marks.setdefault(batch, {})[sid] = status
    return [aggregate_batch(bid, stamp, object_json(dashboards.get(bid)), snapshots.get(bid, []), marks.get(bid, {}))
            for bid, stamp in connection.execute('SELECT id,created_at FROM campaigns ORDER BY id DESC')]


def followup_text(batch):
    s = batch['followupSummary']
    return f'第{batch["id"]}次可跟进标记：已填写 {s["marked"]}/{s["total"]} · 是 {s["yes"]} · 否 {s["no"]} · 未填写 {s["unmarked"]}'


class LearningOverview(QObject):
    changed = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._path = None
        self._active = False
        self._dirty = True
        self._reset_pending = False
        self._batches = []
        self._choices = dict(history=0, compare=0, baseline=0, goal=0)
        self._lessons = {i: 0 for i in range(4)}
        self._details = {i: 0 for i in range(4)}
        self._tab = 0
        self._targets = ['85', '85', '15']
        self._error = ''
        owner.workflow.overviewSourceChanged.connect(self.invalidate)

    @Slot()
    def invalidate(self):
        self._dirty = True
        if self._path != Path(self.owner.db.path).resolve():
            self._reset_pending = True
        if self._active:
            self.reload()

    @Slot(bool)
    def setActive(self, active):
        self._active = active
        if active and self._dirty:
            self.reload()

    @Slot()
    def reload(self):
        path = Path(self.owner.db.path).resolve()
        reset = path != self._path or self._reset_pending
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as conn:
                conn.execute('BEGIN')
                batches = load_batches(conn)
            self._error = ''
        except (sqlite3.Error, ValueError, TypeError) as exc:
            batches = []
            self._error = '读取学习快照失败：' + str(exc)
        self._path, self._batches, self._dirty = path, batches, False
        self._reset_pending = False
        latest = batches[0]['id'] if batches else 0
        ids = {b['id'] for b in batches}
        if reset:
            self._choices = dict(history=latest, compare=latest,
                                 baseline=batches[1]['id'] if len(batches)>1 else latest, goal=latest)
            self._lessons = {i: 0 for i in range(4)}
            self._details = {i: 0 for i in range(4)}
            self._targets = ['85', '85', '15']
        else:
            self._choices = {k: v if v in ids else latest for k, v in self._choices.items()}
        self._normalize_lessons()
        self.changed.emit()

    def _batch(self, key=None):
        bid = self._choices.get(key) if key else (self._batches[0]['id'] if self._batches else 0)
        return next((b for b in self._batches if b['id'] == bid), None)

    def _current(self, tab=None):
        tab = self._tab if tab is None else tab
        return self._batch([None, 'history', 'compare', 'goal'][tab])

    def _lesson_options(self, tab=None):
        tab = self._tab if tab is None else tab
        b = self._current(tab)
        rows = b['lessons'] if b else []
        if tab == 2:
            base = self._batch('baseline')
            shared = {r['lesson'] for r in base['lessons']} if base else set()
            rows = [r for r in rows if r['lesson'] in shared]
        return [dict(id=r['lesson'], label=f'第1～{r["lesson"]}节累计') for r in rows]

    def _normalize_lessons(self):
        for tab in range(4):
            options = self._lesson_options(tab)
            if tab == 0 or self._lessons[tab] not in {r['id'] for r in options}:
                self._lessons[tab] = options[-1]['id'] if options else 0
            self._details[tab] = self._lessons[tab]

    @Property('QVariantList', notify=changed)
    def batches(self):
        return [dict(id=b['id'], label=b['label']) for b in self._batches]

    def _index(self, key):
        return next((i for i, b in enumerate(self._batches) if b['id']==self._choices[key]), -1)

    @Property(int, notify=changed)
    def historyIndex(self): return self._index('history')
    @Property(int, notify=changed)
    def compareIndex(self): return self._index('compare')
    @Property(int, notify=changed)
    def baselineIndex(self): return self._index('baseline')
    @Property(int, notify=changed)
    def goalIndex(self): return self._index('goal')
    @Property(int, notify=changed)
    def tabIndex(self): return self._tab
    @Property('QVariantList', notify=changed)
    def lessonOptions(self): return self._lesson_options()
    @Property(int, notify=changed)
    def lessonIndex(self):
        return next((i for i, r in enumerate(self._lesson_options()) if r['id']==self._lessons[self._tab]), -1)
    @Property('QVariantList', notify=changed)
    def targets(self): return self._targets

    @Slot(int)
    def selectTab(self, index):
        if 0 <= index < 4:
            self._tab = index
            self.changed.emit()

    @Slot(str, int)
    def selectBatch(self, key, index):
        if key in self._choices and 0 <= index < len(self._batches):
            self._choices[key] = self._batches[index]['id']
            self._normalize_lessons()
            self.changed.emit()

    @Slot(int)
    def selectLesson(self, lesson):
        self.inspectLesson(lesson)
        if self._tab != 0 and lesson in {r['id'] for r in self._lesson_options()}:
            self._lessons[self._tab] = lesson
            self.changed.emit()

    @Slot(int)
    def inspectLesson(self, lesson):
        batches = [self._current()]
        if self._tab == 2: batches.append(self._batch('baseline'))
        if self._details[self._tab] != lesson and any(self._point(b, lesson) for b in batches):
            self._details[self._tab] = lesson
            self.changed.emit()

    @Slot(int, str)
    def setTarget(self, index, value):
        if 0 <= index < 3:
            self._targets[index] = value
            self.changed.emit()

    def _point(self, b, lesson):
        return next((r for r in b['lessons'] if r['lesson']==lesson), None) if b else None

    def _series(self, b, key, labels, dashed=False):
        names = dict(course='完课率', homework='作业率', gap='差值')
        return dict(name=f'第{b["id"]}次 {names[key]}' + ('（虚线）' if dashed else ''),
                    color=dict(course='#285db4', homework='#14765a', gap='#9b5d13')[key], dashed=dashed,
                    values=[self._point(b, n).get(key) if self._point(b, n) else None for n in labels])

    def _detail(self, b, base, n):
        r, old = self._point(b, n), self._point(base, n)
        def part(batch, row):
            return f'第{batch["id"]}次：' + ('暂无该节快照' if not row else
                f'完课 {fmt(row["course"], "%")} · 作业 {fmt(row["homework"], "%")} · 差值 {fmt(row["gap"], "pp")}')
        return f'第1～{n}节累计\n' + part(b, r) + ('\n'+part(base, old) if base else '')

    @Property('QVariantMap', notify=changed)
    def view(self):
        b = self._current()
        if not b:
            return dict(available=False, notice=self._error or '当前班期尚无催办批次。请先在催办工作台获取学习数据并新建催办。')
        base = self._batch('baseline') if self._tab==2 else None
        lesson = self._lessons[self._tab]
        r, old = self._point(b, lesson), self._point(base, lesson)
        metrics = []
        for key, name in [('course', '累计完课率'), ('homework', '累计作业率'), ('gap', '累计差值')]:
            value = r.get(key) if r else None
            note = f'第1～{lesson}节累计' if r else '暂无有效评估节次'
            if base:
                note += f' · 第{base["id"]}次 {fmt(old.get(key) if old else None, "pp" if key=="gap" else "%")}'
                note += ' · 变化 '+fmt(value-old[key] if r and old else None, 'pp', True)
            elif r and key != 'gap':
                note += f' · {r[key+"Done"]}/{b["total"]}人'
            metrics.append(dict(title=name, value=fmt(value, 'pp' if key=='gap' else '%'), note=note))
        metrics.append(dict(title='全班在读人数', value=str(b['total'])+'人',
                            note=f'批次成员 {b["members"]}人 · 未知计数 {b["unknown"]}人'))
        notice = '范围：本批全班在读非补位，含免催、无微信及已完成。累计率＝第1～N节全部完成人数÷全班在读人数。'
        if base:
            notice += f' 第{b["id"]}次 / 第{base["id"]}次分母 {b["total"]} / {base["total"]}人。'
            notice += '两批分母不同，变化包含人员变化。' if b['total'] != base['total'] else ''
            notice += '变化不代表催办的因果效果。'
            if not self._lesson_options(): notice += ' 双方暂无共同节次，评估指标留空。'
            if base['learningNotice']: notice += f' 第{base["id"]}次：'+base['learningNotice']
        notice += ' '+b['learningNotice']
        labels = sorted({p['lesson'] for p in b['lessons']} | ({p['lesson'] for p in base['lessons']} if base else set()))
        rates = [self._series(b, key, labels) for key in ('course', 'homework')]
        gaps = [self._series(b, 'gap', labels)]
        if base:
            rates += [self._series(base, key, labels, True) for key in ('course', 'homework')]
            gaps += [self._series(base, 'gap', labels, True)]
        details = [self._detail(b, base, n) for n in labels]
        rows = []
        headers = ['累计节次', '完课率', '作业率', '差值', '考核']
        if base:
            headers = ['累计节次']+[f'{name} · {label}' for name in ('完课率', '作业率', '差值') for label in (f'第{b["id"]}次', f'第{base["id"]}次', '变化')]+['考核']
        for n in labels:
            point, previous = self._point(b, n), self._point(base, n)
            cells = [f'第1～{n}节']
            for key in ('course', 'homework', 'gap'):
                value = point.get(key) if point else None
                cells.append(fmt(value, 'pp' if key=='gap' else '%'))
                if base:
                    cells += [fmt(previous.get(key) if previous else None, 'pp' if key=='gap' else '%'),
                              fmt(value-previous[key] if point and previous else None, 'pp', True)]
            cells.append(grade(point['gap']) if point else '—')
            rows.append(dict(key=n, cells=cells))
        completion_rows = [dict(key=p['count'], cells=[str(p['count']), str(p['people']), fmt(p['ratio'], '%'),
                          str(p['followable']) if p['followable'] is not None else '—', '', '',
                          fmt(p['cumulativeRate'], '%'), str(p['cumulative'])]) for p in b['completion']]
        distribution_rows = []
        if base:
            current = {p['count']:p for p in b['completion']}
            before = {p['count']:p for p in base['completion']}
            for count in sorted(current.keys() | before.keys(), reverse=True):
                p, prev = current.get(count), before.get(count)
                cells = [str(count)]
                for key in ('people', 'ratio', 'followable'):
                    a, z = p.get(key) if p else None, prev.get(key) if prev else None
                    suffix = '%' if key=='ratio' else ''
                    cells += [fmt(a, suffix) if key=='ratio' else str(a) if a is not None else '—',
                              fmt(z, suffix) if key=='ratio' else str(z) if z is not None else '—',
                              fmt(a-z, 'pp' if key=='ratio' else '人', True) if a is not None and z is not None else '—']
                distribution_rows.append(dict(key=count, cells=cells))
        result = dict(available=True, title=b['label'], latest=self._tab==0, metrics=metrics,
                      grade=grade(r['gap']) if r else '暂无有效累计数据', notice=notice, selectedLesson=lesson,
                      detailLesson=self._details[self._tab],
                      rateChart=dict(labels=labels, series=rates, details=details, suffix='%', thresholds=[]),
                      gapChart=dict(labels=labels, series=gaps, details=details, suffix='pp', thresholds=[5, 10, 15]),
                      lessonHeaders=headers, lessonRows=rows, completionRows=completion_rows,
                      completionNotice=b['completionNotice'], followup=followup_text(b)+('；'+followup_text(base) if base else ''),
                      distributionHeaders=['次数']+[f'{name} · {label}' for name in ('人数', '比例', '可跟进') for label in (f'第{b["id"]}次', f'第{base["id"]}次' if base else '', '变化')],
                      distributionRows=distribution_rows, goalCards=[], trends=[])
        if self._tab==3:
            result.update(self._goals(b, r, lesson))
        return result

    def _goals(self, b, r, lesson):
        cards, trends = [], []
        recent = list(reversed([batch for batch in self._batches if batch['id']<=b['id']][:5])) if r else []
        for i, key in enumerate(('course', 'homework', 'gap')):
            try: target = float(self._targets[i])
            except ValueError: target = float('nan')
            valid = math.isfinite(target) and 0 <= target <= 100 and (i != 2 or target in (5,10,15))
            message = '请选择有效节次并输入0～100%的目标。'
            if valid and r:
                need = (max(0, math.ceil(target*b['total']/100-1e-9)-r[key+'Done']) if i < 2 else
                        max(0, math.ceil(r['courseDone']-r['homeworkDone']-target*b['total']/100-1e-9)))
                message = ('已达到目标' if need==0 else f'还需 {need}人'+('补齐作业' if i==2 else '完成'))
                message += f' · 当前 {fmt(r[key], "pp" if i==2 else "%")}'
            cards.append(dict(title=['累计完课目标', '累计作业目标', '差值目标'][i], message=message,
                              need=need if valid and r else None))
            points = [self._point(batch, lesson) for batch in recent]
            trends.append(dict(labels=[batch['id'] for batch in recent],
                               series=[dict(name=f'第1～{lesson}节 · '+['完课率', '作业率', '差值'][i],
                                            color=['#285db4', '#14765a', '#9b5d13'][i], dashed=False,
                                            values=[p[key] if p else None for p in points])],
                               details=[self._detail(batch, None, lesson) for batch in recent],
                               suffix='pp' if i==2 else '%', thresholds=[target] if valid else []))
        trend_rows = []
        for batch in recent:
            point = self._point(batch, lesson)
            trend_rows.append(dict(key=batch['id'], cells=[f'第{batch["id"]}次', f'第1～{lesson}节', str(batch['total'])]+
                              [fmt(point[key] if point else None, 'pp' if key=='gap' else '%') for key in ('course','homework','gap')]+
                              [grade(point['gap']) if point else '—']))
        candidates, unknown = [], 0
        if r and cards[2]['need'] is not None:
            for snap in b['population']:
                if snap['followup_status'] != '是':
                    continue
                raw = snap.get('homework')
                if (snap.get('matched') is False or integer(snap.get('completed_homework'), 32) is None
                        or not isinstance(raw, str) or not re.fullmatch(r'(?:\d+(?:,\d+)*)?', raw)):
                    unknown += 1
                    continue
                missing = [integer(n, 32) for n in raw.split(',')] if raw else []
                if any(n is None or n == 0 for n in missing):
                    unknown += 1
                    continue
                missing = sorted({n for n in missing if n <= lesson})
                if missing:
                    candidates.append(dict(student_id=snap['student_id'], name=snap.get('name', ''),
                                           missing=missing))
        candidates.sort(key=lambda row: row['student_id'])
        need = cards[2]['need']
        note = (f'差值目标还需 {need}人补齐作业；符合条件的候选 {len(candidates)}人。'
                if need is not None else '暂无有效累计节次或差值目标。')
        if need is not None and need > len(candidates):
            note += f' 候选人数比所需人数少 {need-len(candidates)}人。'
        note += ' 每人须补齐第1～'+str(lesson)+'节全部欠交作业才计入累计作业完成人数；名单不代表已完成。'
        if unknown:
            note += f' {unknown}名可跟进学员作业数据未知，未列入。'
        return dict(goalCards=cards, trends=trends, trendRows=trend_rows,
                    homeworkCandidates=dict(available=r is not None and need is not None,
                                            title=b['label']+f' · 第1～{lesson}节', notice=note,
                                            rows=[dict(key=i, cells=[str(i+1), row['name'], row['student_id'],
                                                  '、'.join(map(str, row['missing']))])
                                                  for i, row in enumerate(candidates)]))
