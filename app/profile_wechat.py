"""Verify the current class roster against WeCom without sending or renaming."""
from collections import Counter
import json
import threading

from PySide6.QtCore import QObject, Property, Signal, Slot, QThread, QCoreApplication, QEvent

from .contact_match import name_in_chat_title
from .qt_models import DictTableModel
from .remark_scan import normalize_text, term_prefix
from .remark_storage import load_prefix
from .send_controller import F11Hotkey
from .wecom_renamer import RemarkDriver
from .wecom_sender import WeComSender, ContactNotFoundError

PENDING = '待验证'
FOUND = '已添加'
NOT_FOUND = '未找到'
REVIEW = '待确认'
FAILED = '失败'
SKIPPED = '已跳过'
COLUMNS = [('student_id', '学号'), ('name', '姓名'), ('state', '结果'),
           ('observed', '企微联系人'), ('detail', '说明')]


def matches_contact(task, observed):
    """Only accept a complete name or a known remark, never part of a name."""
    actual, name = normalize_text(observed), normalize_text(task['name'])
    if not actual or not name:
        return False
    if actual == name or actual.startswith(name + '/'):
        return True
    if actual in {normalize_text(prefix + task['name']) for prefix in task['prefixes'] if prefix}:
        return True
    saved = task.get('remark', '')
    return bool(saved and actual == normalize_text(saved) and name_in_chat_title(task['name'], saved))


class WechatVerificationWorker(QThread):
    progress = Signal(int, str)
    checked = Signal(str, str, str, str)
    paused = Signal()
    failed = Signal(str)

    def __init__(self, tasks, driver_factory, parent=None):
        super().__init__(parent)
        self.tasks = tasks
        self.driver_factory = driver_factory
        self.pause_requested = threading.Event()
        self.stop_requested = threading.Event()
        self.wake = threading.Event()

    def run(self):
        try:
            driver = self.driver_factory()
            driver.sender.pause_requested = self.pause_requested.is_set
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        for index, task in enumerate(self.tasks):
            if self.pause_requested.is_set() and not self.stop_requested.is_set():
                self.paused.emit()
                while self.pause_requested.is_set() and not self.stop_requested.is_set():
                    self.wake.wait(.2)
                    self.wake.clear()
            if self.stop_requested.is_set():
                return
            self.progress.emit(index + 1, task['name'])
            observed = ''
            if task['review']:
                state, detail = REVIEW, task['review']
            else:
                try:
                    observed = driver.read_remark(task['name']) or ''
                    if not observed:
                        state, detail = NOT_FOUND, '未匹配到联系人，保留原微信值'
                    elif matches_contact(task, observed):
                        state, detail = FOUND, '联系人已匹配'
                    else:
                        state, detail = REVIEW, '联系人备注无法明确匹配，保留原微信值'
                except ContactNotFoundError as exc:
                    state, detail = NOT_FOUND, str(exc)
                except Exception as exc:
                    state, detail = FAILED, str(exc)
            self.checked.emit(task['student_id'], state, observed, detail)


class ProfileWechatVerifier(QObject):
    changed = Signal()

    def __init__(self, profiles):
        super().__init__(profiles)
        self.profiles = profiles
        self.owner = profiles.owner
        self._model = DictTableModel(COLUMNS, self)
        self._context = ''
        self._prepared_query = None
        self._scope_text = '未筛选时默认验证本班未退课学员；有筛选时按筛选名单验证，排除补位学员'
        self._class_name = ''
        self._worker = None
        self._paused = False
        self._stopping = False
        self._updated = 0
        self._failure = ''
        self._notice = self._scope_text
        self._hotkey = F11Hotkey(self.togglePause)
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property(bool, notify=changed)
    def active(self): return self._worker is not None
    @Property(bool, notify=changed)
    def isPaused(self): return self._paused
    @Property(bool, notify=changed)
    def pauseRequested(self): return bool(self._worker and self._worker.pause_requested.is_set())
    @Property(bool, notify=changed)
    def stopping(self): return self._stopping
    @Property(str, notify=changed)
    def notice(self): return self._notice
    @Property(str, notify=changed)
    def className(self): return self._class_name
    @Property(str, notify=changed)
    def scopeText(self): return self._scope_text
    @Property(int, notify=changed)
    def total(self): return len(self._model.rows)
    @Property(int, notify=changed)
    def completed(self): return sum(r['state'] != PENDING for r in self._model.rows)
    @Property(int, notify=changed)
    def updated(self): return self._updated

    def _tasks(self):
        # Use ADR-007's matching scope; a filtered empty list must stay empty.
        with self.owner.db.connect() as conn:
            roster = [dict(r) for r in conn.execute(
                'SELECT * FROM class_roster WHERE active=1 ORDER BY ordinal,student_id')]
            contacts = {r['student_id']: r['remark'] for r in conn.execute('SELECT * FROM student_contacts')}
            ids = {r[0] for r in conn.execute('SELECT student_id FROM profiles')}
        names = Counter(normalize_text(r['name']) for r in roster if not r['is_placeholder'])
        filtered = self.profiles._query_active()
        if filtered:
            by_id = {r['student_id']: r for r in roster}
            roster = [by_id[r['student_id']] for r in self.profiles._scope_rows()
                      if r['_db_path'] == str(self.owner.db.path) and r['student_id'] in by_id]
        entry = self.owner.workflow._classes[self.owner.workflow.class_index]
        prefixes = tuple(dict.fromkeys((
            term_prefix(entry.get('term_no')),
            load_prefix(self.owner.db, entry.get('term_no')),
            self.owner.repo.get_setting('profile_contact_prefix', self.owner.contactOpener.defaultPrefix))))
        tasks = []
        for row in roster:
            if (not filtered and row['status'].strip() == '已退课') or row['is_placeholder'] or row['student_id'] not in ids:
                continue
            name = row['name'].strip()
            review = ''
            if len(normalize_text(name)) < 2 or any(c in name for c in ('\r', '\n', '\0')):
                review = '姓名为空、过短或含控制字符，请人工确认'
            elif names[normalize_text(name)] > 1:
                review = '班期名单存在重名，无法唯一确认联系人'
            tasks.append(dict(student_id=row['student_id'], name=name, prefixes=prefixes,
                              allow_retired=filtered and row['status'].strip() == '已退课',
                              remark=contacts.get(row['student_id'], ''), review=review,
                              state=PENDING, observed='', detail=''))
        return tasks

    def _query_signature(self):
        return (self.profiles._search, json.dumps(self.profiles._filters, sort_keys=True),
                frozenset(self.profiles._frozen) if self.profiles._frozen is not None else None)

    def _describe_scope(self):
        return ('按当前搜索／筛选匹配名单验证，排除补位学员' if self.profiles._query_active()
                else '未设置筛选，默认验证当前班期未退课学员，排除补位学员')

    @Slot(result=bool)
    def prepare(self):
        if self.active:
            return True
        try:
            if self.profiles.allClasses:
                raise ValueError('全部班级为只读总览，请选择一个班期')
            if (self._context == str(self.owner.db.path) and self.completed
                    and self._prepared_query == self._query_signature()):
                return True
            tasks = self._tasks()
            self._context = str(self.owner.db.path)
            self._class_name = self.owner.workflow.className
            self._prepared_query = self._query_signature()
            self._scope_text = self._describe_scope()
            self._model.set_rows(tasks)
            self._updated = 0
            self._notice = f'本轮验证 {len(tasks)} 人；未找到或待确认时保留原微信值'
            self.changed.emit()
            return True
        except Exception as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    def _driver_factory(self):
        return RemarkDriver(WeComSender(), options={'wait': .5, 'timeout': 3.0})

    @Slot(result=bool)
    def start(self):
        if self.active:
            return False
        try:
            if self.profiles.allClasses or self._context != str(self.owner.db.path):
                raise ValueError('班期已切换，请重新打开验证窗口')
            if (self.owner.busy or self.owner.termsModule.busy or self.owner.workflow.send_busy
                    or self.owner.remarkRenamer.active):
                raise ValueError('其他任务正在运行，请等待完成')
            tasks = self._tasks()
            if not tasks:
                raise ValueError('当前名单没有可验证的学员')
            driver = self._driver_factory()
            self._hotkey.start()
            self._model.set_rows(tasks)
            self._prepared_query = self._query_signature()
            self._scope_text = self._describe_scope()
            self._updated = 0
            self._paused = self._stopping = False
            self._failure = ''
            worker = WechatVerificationWorker(tasks, lambda: driver, self)
            worker.progress.connect(self._progress)
            worker.checked.connect(self._checked)
            worker.paused.connect(self._on_paused)
            worker.failed.connect(self._failed)
            worker.finished.connect(self._finished)
            self._worker = worker
            self._notice = '验证已开始，请勿操作电脑；F11 可在当前联系人结束后暂停'
            worker.start()
            self.changed.emit()
            return True
        except Exception as exc:
            self._hotkey.close()
            self._notice = '未开始验证：' + str(exc)
            self.changed.emit()
            return False

    @Slot(int, str)
    def _progress(self, index, name):
        if self._stopping or self.pauseRequested:
            return
        self._notice = f'{index}/{self.total} · 正在验证：{name}；请勿操作电脑，F11 可暂停'
        self.changed.emit()

    @Slot(str, str, str, str)
    def _checked(self, sid, state, observed, detail):
        index = next((i for i, r in enumerate(self._model.rows) if r['student_id'] == sid), -1)
        if index < 0:
            return
        task = self._model.rows[index]
        if state == FOUND:
            try:
                if self._context != str(self.owner.db.path):
                    raise ValueError('班期已切换，未写入')
                with self.owner.db.connect() as conn:
                    member = conn.execute('SELECT * FROM class_roster WHERE student_id=?', (sid,)).fetchone()
                if (not member or not member['active'] or member['is_placeholder']
                        or (member['status'].strip() == '已退课' and not task['allow_retired'])
                        or member['name'].strip() != task['name']):
                    state, detail = SKIPPED, '学员身份或状态已变化，未写入'
                else:
                    current = self.owner.repo.get(sid)
                    if not current:
                        raise ValueError('学员已移出名单')
                    if current.get('profile:微信') == '是':
                        detail = '已确认联系人；微信原值已为是'
                    elif not self.profiles.autoSaveField(sid, '微信', '是'):
                        raise ValueError(self.profiles.notice)
                    else:
                        self._updated += 1
                        self.profiles.reflect_saved(self._context, sid)
                        detail = '已确认联系人；微信已改为是'
            except Exception as exc:
                state, detail = FAILED, str(exc)
        task.update(state=state, observed=observed, detail=detail)
        self._model.dataChanged.emit(self._model.index(index, 0), self._model.index(index, len(COLUMNS) - 1))
        self.changed.emit()

    @Slot()
    def _on_paused(self):
        if self._stopping:
            return
        self._paused = True
        self._notice = '已暂停，可以操作电脑；F11 或「继续验证」恢复'
        self.changed.emit()

    @Slot(str)
    def _failed(self, message):
        self._failure = message
        self._notice = '验证启动失败：' + message
        self.changed.emit()

    @Slot()
    def _finished(self):
        worker, self._worker = self._worker, None
        self._hotkey.close()
        self._paused = self._stopping = False
        counts = Counter(r['state'] for r in self._model.rows)
        self._notice = (f'已处理 {self.completed}/{self.total} 人；确认已添加 {counts[FOUND]} 人'
                        f'，微信新改为是 {self._updated} 人；未找到 {counts[NOT_FOUND]} 人'
                        f'，待确认 {counts[REVIEW]} 人，失败 {counts[FAILED]} 人，跳过 {counts[SKIPPED]} 人')
        if self._failure:
            self._notice = '验证启动失败：' + self._failure + '；' + self._notice
        if counts[PENDING]:
            self._notice += f'；剩余 {counts[PENDING]} 人未验证，可重新开始'
        if worker:
            worker.deleteLater()
        self.changed.emit()

    @Slot()
    def togglePause(self):
        if not self._worker or self._stopping:
            return
        if self._paused:
            self._worker.pause_requested.clear()
            self._worker.wake.set()
            self._paused = False
            self._notice = '继续验证，请勿操作电脑'
        else:
            self._worker.pause_requested.set()
            self._notice = '等待当前联系人结束后暂停'
        self.changed.emit()

    @Slot()
    def stop(self):
        if self._worker:
            self._stopping = True
            self._worker.stop_requested.set()
            self._worker.wake.set()
            self._notice = '当前联系人结束后停止；已保存的微信结果保留'
            self.changed.emit()

    def shutdown(self):
        if self._worker:
            self._worker.stop_requested.set()
            self._worker.wake.set()
            self._worker.wait()
            # Deliver the completed contact's queued write before application exit.
            QCoreApplication.sendPostedEvents(self, QEvent.MetaCall)
        self._hotkey.close()
