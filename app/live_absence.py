"""第 7 个模块：未进直播间名单（按节次）。

口径（见 ADR-009，2026-09-30 与用户确认）：
- 追光鲸鱼「班期学员直播数据」接口按节次返回 ``hisLearningTime``（页面上叫「直播观看时长」，
  单位秒）。``null`` 表示该学员这节课没有观看记录，即没有进入过直播间；``0`` 是「有记录但时长为
  0」，默认仍算已进入，操作者可勾选把它一起算作未进入。
- 进入提醒范围的只有「平台在读 + 画像微信=是 + 当前非有效免催」的学员，按学号与班期名单关联。
- 同一班期同一节次默认只提醒一次：标记在「生成群发名单」成功创建时写入本班数据库，
  表格仍然显示这些人（标「已提醒」），只是默认不再进入新名单，可手动取消勾选或清除记录。

本模块只读平台数据，不写名单缓存、不发送消息；发送仍由群发中心显式启动。
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Property, QCoreApplication, QObject, Signal, Slot

from . import live_storage as storage
from . import remark_scan as scan
from . import remark_storage as contacts
from .acquisition.tasks import AcquisitionTask
from .credentials import get_password
from .message_content import render_content
from .qt_models import DictTableModel
from .term_roster import TermRosterStore

COLUMNS = [('ordinal', '序号'), ('student_id', '学员学号'), ('name', '学员姓名'),
           ('live_text', '直播观看时长'), ('status', '平台状态'), ('wechat', '微信'),
           ('remark', '企微备注'), ('remind_state', '本节提醒')]
ABSENT = '未进入'
READING = '在读'
PLACEHOLDERS = ['姓名', '学号', '班期', '状态', '课程', '直播观看时长']


def format_seconds(value):
    if value is None:
        return ABSENT
    return f'{value // 60}:{value % 60:02d}'


class LiveAbsence(QObject):
    changed = Signal()
    noticeChanged = Signal()
    activityChanged = Signal()
    lessonChanged = Signal()
    resultChanged = Signal()
    optionsChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._store = TermRosterStore(owner.workflow.registry.db)
        self._model = DictTableModel(COLUMNS, self)
        self._entry = {}
        self._context_key = None
        self._term_id = ''
        self._term_no = ''
        self._lessons = []
        self._lesson_index = -1
        self._lesson_resource = ''
        self._snapshot = None
        self._listable = []
        self._counters = self._empty_counters()
        self._fetched_at = ''
        self._include_zero = False
        self._exclude_reminded = True
        self._show_all = False
        self._busy = False
        self._cancelled = False
        self._task = None
        self._action = ''
        self._request = {}
        self._notice = '选择节次后点「获取未进直播间名单」；只统计在读、画像微信=是且非免催的学员'
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)
        self.reload()

    # ------------------------------------------------------------------ properties
    @staticmethod
    def _empty_counters():
        return dict(api=0, ready=0, unnamed=0, missing=0, no_wechat=0, exempt=0,
                    eligible=0, absent=0, entered=0, zero=0, reminded=0, duplicate=0)

    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property(str, notify=noticeChanged)
    def notice(self): return self._notice
    @Property(bool, notify=activityChanged)
    def busy(self): return self._busy
    @Property('QVariantList', notify=lessonChanged)
    def lessons(self): return [dict(r) for r in self._lessons]
    @Property(int, notify=lessonChanged)
    def lessonIndex(self): return self._lesson_index
    @Property(str, notify=lessonChanged)
    def lessonLabel(self):
        return self._lessons[self._lesson_index]['label'] if 0 <= self._lesson_index < len(self._lessons) else ''
    @Property(str, notify=changed)
    def className(self): return str(self._entry.get('name') or '')
    @Property(str, notify=resultChanged)
    def fetchedAt(self): return self._fetched_at
    @Property(bool, notify=resultChanged)
    def hasResult(self): return self._snapshot is not None
    @Property('QVariantList', constant=True)
    def messagePlaceholders(self): return list(PLACEHOLDERS)
    @Property(bool, notify=optionsChanged)
    def includeZero(self): return self._include_zero
    @Property(bool, notify=optionsChanged)
    def excludeReminded(self): return self._exclude_reminded
    @Property(bool, notify=optionsChanged)
    def showAll(self): return self._show_all
    @Property(int, notify=changed)
    def visibleCount(self): return len(self._model.rows)
    @Property(int, notify=changed)
    def recipientCount(self): return len(self._listable)
    @Property('QVariantList', notify=changed)
    def recipientKeys(self): return list(self._listable)
    @Property(int, notify=changed)
    def apiCount(self): return self._counters['api']
    @Property(int, notify=changed)
    def readyCount(self): return self._counters['ready']
    @Property(int, notify=changed)
    def eligibleCount(self): return self._counters['eligible']
    @Property(int, notify=changed)
    def absentCount(self): return self._counters['absent']
    @Property(int, notify=changed)
    def enteredCount(self): return self._counters['entered']
    @Property(int, notify=changed)
    def zeroCount(self): return self._counters['zero']
    @Property(int, notify=changed)
    def remindedCount(self): return self._counters['reminded']
    @Property(int, notify=changed)
    def duplicateCount(self): return self._counters['duplicate']
    @Property(int, notify=changed)
    def missingCount(self): return self._counters['missing']
    @Property(int, notify=changed)
    def noWechatCount(self): return self._counters['no_wechat']
    @Property(int, notify=changed)
    def exemptCount(self): return self._counters['exempt']
    @Property(str, notify=changed)
    def summary(self):
        c = self._counters
        zero = f' · 观看 0 秒 {c["zero"]}' if c['zero'] else ''
        return (f'本节返回 {c["api"]} 人 · 在读 {c["ready"]} · 可提醒范围 {c["eligible"]} 人'
                f'（微信=是、非免催）· 未进入 {c["absent"]} · 已进入 {c["entered"]}{zero}'
                f' · 本节已提醒 {c["reminded"]}')
    @Property(str, notify=changed)
    def issues(self):
        c = self._counters
        parts = []
        if c['missing']:
            parts.append(f'{c["missing"]} 人不在本班名单（名单可能落后，建议在「班期学员」重新获取）')
        if c['no_wechat']:
            parts.append(f'{c["no_wechat"]} 人画像微信不是「是」')
        if c['exempt']:
            parts.append(f'{c["exempt"]} 人在免催中')
        if c['unnamed']:
            parts.append(f'{c["unnamed"]} 人接口未返回姓名')
        if c['duplicate']:
            parts.append(f'{c["duplicate"]} 人存在重名，生成名单会被拦截')
        return '；'.join(parts)

    # ------------------------------------------------------------------ context
    def _context(self):
        workflow = self.owner.workflow
        classes = getattr(workflow, '_classes', []) or []
        index = getattr(workflow, 'class_index', 0)
        entry = classes[index] if 0 <= index < len(classes) else {}
        return dict(entry), str(entry.get('term_id') or ''), str(entry.get('term_no') or '')

    def _load_lessons(self):
        if not self._term_id:
            return []
        try:
            return list(self._store.load_lessons(self._term_id)['lessons'])
        except Exception:
            return []

    @Slot(result=bool)
    def reload(self):
        """Re-read the class, its lesson cache and this lesson's reminder marks."""
        try:
            entry, term_id, term_no = self._context()
        except Exception as exc:
            self._set_notice('读取当前班级失败：' + str(exc))
            return False
        key = (str(entry.get('path') or ''), term_id)
        if key != self._context_key:
            # Another class or term: the old snapshot and lesson choice do not apply.
            self._context_key = key
            self._snapshot = None
            self._lesson_resource = ''
        self._entry, self._term_id, self._term_no = entry, term_id, term_no
        self._lessons = self._load_lessons()
        self._lesson_index = next((i for i, r in enumerate(self._lessons)
                                   if str(r.get('resource_id') or '') == self._lesson_resource), -1)
        self._lesson_resource = self._lessons[self._lesson_index]['resource_id'] if self._lesson_index >= 0 else ''
        self._rebuild()
        self.lessonChanged.emit()
        if not self._term_id:
            self._set_notice('当前班级还没有绑定班期：请先在「班期学员」获取班期，或到「设置」确认绑定。')
        elif not self._lessons:
            self._set_notice('本班期还没有课程列表，正在获取…')
        elif self._snapshot:
            counters = self._counters
            self._set_notice(f'{self.lessonLabel} · 上次获取 {self._fetched_at.replace("T", " ")}：'
                             f'未进入 {counters["absent"]} 人'
                             + (f'，其中 {counters["reminded"]} 人本节已提醒' if counters['reminded'] else '')
                             + '；可重新获取或直接生成名单。')
        else:
            self._set_notice(f'{self.className} · 共 {len(self._lessons)} 个节次；选择节次后点「获取未进直播间名单」。')
        return True

    def _blocked(self):
        """Another module owning the network or the desktop blocks a new request."""
        return self._busy or self.owner.busy or self.owner.termsModule.busy

    @Slot()
    def activate(self):
        if self._blocked():
            return
        self.reload()
        if self._term_id and not self._lessons:
            self.refreshLessons()

    @Slot(int)
    def selectLesson(self, index):
        if self._busy or not 0 <= index < len(self._lessons):
            return
        resource = str(self._lessons[index].get('resource_id') or '')
        if resource == self._lesson_resource:
            return
        self._lesson_resource = resource
        self._lesson_index = index
        # Another lesson: the previous result and its marks belong to the old one.
        self._snapshot = None
        self._fetched_at = ''
        self._rebuild()
        self.lessonChanged.emit()
        self._set_notice(f'已选择 {self.lessonLabel}；点「获取未进直播间名单」刷新本节数据。')

    # ------------------------------------------------------------------ options
    # Deliberately not named set<Property>: a slot with the property's setter name is
    # published as the property write accessor instead and is not callable from QML.
    @Slot(bool)
    def applyIncludeZero(self, value):
        value = bool(value)
        if value == self._include_zero:
            return
        self._include_zero = value
        self.optionsChanged.emit()
        self._rebuild()

    @Slot(bool)
    def applyExcludeReminded(self, value):
        value = bool(value)
        if value == self._exclude_reminded:
            return
        self._exclude_reminded = value
        self.optionsChanged.emit()
        self._rebuild()

    @Slot(bool)
    def applyShowAll(self, value):
        value = bool(value)
        if value == self._show_all:
            return
        self._show_all = value
        self.optionsChanged.emit()
        self._rebuild()

    @Slot(result=bool)
    def clearReminders(self):
        if self._busy or not self._term_id or not self._lesson_resource:
            return False
        try:
            removed = storage.clear_reminders(self.owner.db, self._term_id, self._lesson_resource)
        except Exception as exc:
            self._set_notice('清除本节提醒记录失败：' + str(exc))
            return False
        self._rebuild()
        self._set_notice(f'已清除本节（{self.lessonLabel or "未选择"}）提醒记录 {removed} 条。')
        return True

    # ------------------------------------------------------------------ fetch
    @Slot()
    def refreshLessons(self):
        if self._blocked():
            return
        if not self._term_id:
            self._set_notice('当前班级还没有绑定班期，无法获取课程列表。')
            return
        self._start('lessons')

    @Slot()
    def fetchRows(self):
        if self._blocked():
            return
        if self.owner.groupCenter.active or self.owner.workflow.send_busy:
            self._set_notice('群发中心正在运行，请先结束或暂停本轮发送再获取。')
            return
        if not self._term_id or not self._lesson_resource:
            self._set_notice('请先选择要检查的节次。')
            return
        self._start('live')

    def _start(self, action):
        username = self.owner.workflow.registry.get_setting('completion_username', '')
        password = get_password('completion', username)
        if not password:
            self._set_notice('请先在设置中保存追光鲸鱼账号和密码。')
            return
        self._action = action
        self._cancelled = False
        self._request = dict(term_id=self._term_id, resource_id=self._lesson_resource)
        task = AcquisitionTask(action, (username, password),
                               cache_dir=self.owner.workflow.registry.db.path.parent / 'platform_sessions',
                               term_id=self._request['term_id'], resource_id=self._request['resource_id'], parent=self)
        self._task = task
        task.succeeded.connect(self._succeeded)
        task.failed.connect(self._failed)
        task.finished.connect(self._release_task)
        task.finished.connect(task.deleteLater)
        self._busy = True
        self._notice = {'lessons': '正在获取本班期课程列表…',
                        'live': '正在获取本节直播间数据…'}[action]
        self.activityChanged.emit()
        self.noticeChanged.emit()
        task.start()

    @Slot()
    def cancel(self):
        if self._busy:
            self._cancelled = True
            self._set_notice('已取消，正在等待当前网络请求结束；返回结果将被丢弃。')

    def _release_task(self):
        if self.sender() is self._task:
            self._task = None

    def _failed(self, message):
        self._set_notice('已取消获取，原有数据保持不变。' if self._cancelled else message)
        self._finish()

    def _succeeded(self, data):
        if not self._busy:
            return
        if self._cancelled:
            self._set_notice('已取消获取，原有数据保持不变。')
            self._finish()
            return
        try:
            if self._action == 'lessons':
                self._accept_lessons(data)
            else:
                self._accept_live(data)
        except Exception as exc:
            self._set_notice(str(exc) if isinstance(exc, ValueError) else '结果读取或保存失败；请重试。')
        finally:
            self._finish()

    def _finish(self):
        self._busy = False
        self.activityChanged.emit()

    def _accept_lessons(self, lessons):
        if self._context()[1] != self._request['term_id']:
            self._set_notice('班期已切换，本次课程结果已丢弃。')
            return
        rows = [r for r in lessons if isinstance(r, dict) and r.get('resource_id')]
        if not rows:
            raise ValueError('本班期暂无可选课程。')
        saved = self._store.load_lessons(self._request['term_id'])
        # The 班期学员 page owns the default resource id of the term cache; keep it as it is.
        self._store.save_lessons(self._request['term_id'], rows, saved.get('resource_id', ''))
        self._lessons = rows
        self._lesson_index = next((i for i, r in enumerate(rows)
                                   if str(r.get('resource_id') or '') == self._lesson_resource), -1)
        self._lesson_resource = rows[self._lesson_index]['resource_id'] if self._lesson_index >= 0 else ''
        self._rebuild()
        self.lessonChanged.emit()
        self._set_notice(f'已获取 {len(rows)} 个节次；选择节次后点「获取未进直播间名单」。')

    def _accept_live(self, rows):
        if self._context()[1] != self._request['term_id']:
            self._set_notice('班期已切换，本次获取结果已丢弃，原有数据保持不变。')
            return
        if str(self._lesson_resource) != self._request['resource_id']:
            self._set_notice('节次已切换，本次获取结果已丢弃，原有数据保持不变。')
            return
        self._snapshot = dict(term_id=self._request['term_id'], resource_id=self._request['resource_id'],
                              rows=list(rows), fetched_at=datetime.now().isoformat(timespec='seconds'))
        self._rebuild()
        c = self._counters
        self._set_notice(f'已获取 {self.lessonLabel or "本节"} 的直播间数据：'
                         f'未进入 {c["absent"]} 人'
                         + (f'，其中 {c["reminded"]} 人本节已提醒' if c['reminded'] else '')
                         + '。')

    # ------------------------------------------------------------------ rebuild
    def _rebuild(self):
        counters = self._empty_counters()
        rows, listable = [], []
        snapshot = self._snapshot
        if snapshot and snapshot.get('term_id') == self._term_id:
            try:
                everybody = contacts.load_students(self.owner.db, require_wechat=False)
            except Exception as exc:
                self._set_notice('读取本班名单失败：' + str(exc))
                everybody = []
            known = {p['student_id']: p for p in everybody}
            try:
                exempt = storage.active_exemptions(self.owner.db)
                reminders = storage.load_reminders(self.owner.db, self._term_id, snapshot['resource_id'])
            except Exception as exc:
                exempt, reminders = set(), {}
                self._set_notice('读取本节提醒记录失败：' + str(exc))
            # Pass 1: who is in scope for this lesson (在读 + 微信=是 + 非免催 + 有姓名).
            scoped = []
            for source in sorted(snapshot['rows'], key=lambda r: str(r.get('student_id') or '')):
                counters['api'] += 1
                sid, name = str(source.get('student_id') or ''), str(source.get('name') or '')
                if source.get('status') != READING:
                    continue
                counters['ready'] += 1
                if not name:
                    counters['unnamed'] += 1
                    continue
                person = known.get(sid)
                if person is None or person.get('is_placeholder'):
                    counters['missing'] += 1
                    continue
                if person.get('wechat') != '是':
                    counters['no_wechat'] += 1
                    continue
                if sid in exempt:
                    counters['exempt'] += 1
                    continue
                counters['eligible'] += 1
                scoped.append(dict(student_id=sid, name=name, status=str(source.get('status') or ''),
                                   seconds=source.get('live_seconds'), person=person))
            # 重名有两种来源：全班名单里同名（企业微信搜索可能撞名），以及本节范围内同名
            # （名单内重名会被 GroupStore 直接拦截，永远建不出名单）。
            duplicates = scan.duplicate_names(everybody)
            seen = {}
            for member in scoped:
                seen[member['name']] = seen.get(member['name'], 0) + 1
            duplicates |= {name for name, count in seen.items() if count > 1}
            # Pass 2: classify and build the display rows.
            for member in scoped:
                sid, name, seconds = member['student_id'], member['name'], member['seconds']
                zero = seconds == 0
                absent = seconds is None or (zero and self._include_zero)
                if zero:
                    counters['zero'] += 1
                reminded_at = str(reminders.get(sid) or '')
                if absent:
                    counters['absent'] += 1
                    if reminded_at:
                        counters['reminded'] += 1
                else:
                    counters['entered'] += 1
                if name in duplicates:
                    counters['duplicate'] += 1
                if absent and not (self._exclude_reminded and reminded_at):
                    listable.append(sid)
                if not absent and not self._show_all:
                    continue
                person = member['person']
                rows.append(dict(ordinal=len(rows) + 1, student_id=sid, name=name, live_seconds=seconds,
                                 live_text=format_seconds(seconds), status=member['status'],
                                 wechat=str(person.get('wechat') or ''), remark=str(person.get('remark') or ''),
                                 remind_state=(f'已提醒 {reminded_at[11:16]}' if reminded_at else ''),
                                 duplicate=name in duplicates, absent=absent))
        self._counters = counters
        self._listable = listable
        self._fetched_at = str((snapshot or {}).get('fetched_at') or '')
        self._model.set_rows(rows)
        self.changed.emit()
        self.resultChanged.emit()

    # ------------------------------------------------------------------ output list
    def build_people(self, fields):
        """Rendered recipients for one new independent group list (called by GroupCenter)."""
        wanted = set(self._listable)
        people = []
        for row in self._model.rows:
            if row['student_id'] not in wanted:
                continue
            variables = {'学号': row['student_id'], '班期': self.className, '状态': row['status'],
                         '课程': self.lessonLabel, '直播观看时长': row['live_text']}
            people.append(dict(name=row['name'],
                               content=render_content(fields, row['name'], variables=variables),
                               learning_data=dict(student_id=row['student_id'], class_name=self.className,
                                                  profile_path=str(self.owner.db.path), profile_fields=variables)))
        return people

    def mark_reminded(self, student_ids, list_id=None):
        """Record this lesson's reminder marks after a list was really created."""
        if not self._term_id or not self._lesson_resource:
            return ''
        stamp = storage.save_reminders(self.owner.db, self._term_id, self._lesson_resource, student_ids, list_id)
        self._rebuild()
        return stamp

    # ------------------------------------------------------------------ lifecycle
    def _set_notice(self, text):
        self._notice = str(text)
        self.noticeChanged.emit()

    def shutdown(self):
        if self._task and self._task.isRunning():
            self._task.wait()
