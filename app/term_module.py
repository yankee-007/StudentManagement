import json
import re
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QApplication, QFileDialog
from .qt_models import DictTableModel
from .term_roster import TermRosterStore, COLUMNS
from .xlsx_export import export_table
from .acquisition.tasks import AcquisitionTask
from .credentials import get_password


class TermModule(QObject):
    changed = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        # Fixed registry DB, never the mutable currently-selected class DB.
        self.registry = owner.workflow.registry
        self.store = TermRosterStore(self.registry.db)
        self._terms = json.loads(self.registry.get_setting('remote_terms') or '[]')
        self._term_index = 0 if self._terms else -1
        self._lessons, self._rows = [], []
        self._lesson_index = -1
        self._notice = '选择班期即可查看；没有缓存时自动获取'
        self._force_roster = False
        self._search = ''
        self._busy = False
        self._cancelled = False
        self._model = DictTableModel(COLUMNS, self)
        self._task = None
        self._action = ''
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)
        self._load_cache()

    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property('QVariantList', notify=changed)
    def terms(self):
        return [dict(r, label=f"{r['termName']} · {r['termNo']}") for r in self._terms]
    @Property(int, notify=changed)
    def termIndex(self): return self._term_index
    @Property('QVariantList', notify=changed)
    def lessons(self): return self._lessons
    @Property(int, notify=changed)
    def lessonIndex(self): return self._lesson_index
    @Property(bool, notify=changed)
    def busy(self): return self._busy
    @Property(str, notify=changed)
    def notice(self): return self._notice
    @Property(int, notify=changed)
    def visibleCount(self): return len(self._model.rows)
    @Property(str, notify=changed)
    def summary(self):
        real = sum(r['source'] == '接口学员' for r in self._rows)
        return f'真实学员 {real} 人 · 缺号补位 {len(self._rows)-real} 行 · 当前显示 {self.visibleCount} 行'

    def _term(self):
        return self._terms[self._term_index] if self._term_index >= 0 else None

    def _load_cache(self):
        term = self._term()
        saved = self.store.load(term['termId']) if term else {'rows': [], 'fetched_at': ''}
        cached = self.store.load_lessons(term['termId']) if term else {'lessons': [], 'resource_id': ''}
        self._lessons = cached['lessons']
        self._lesson_index = self._choose_lesson(self._lessons, cached['resource_id'] or saved.get('resource_id', ''))
        self._rows = saved['rows']
        self.filterRows(self._search)
        if saved['fetched_at']:
            self._notice = '已读取数据库 · 获取时间 ' + saved['fetched_at'].replace('T', ' ') + ' · 如需更新请手动重新获取'
        else:
            self._notice = '本班期暂无名单缓存，将自动获取'
        self.changed.emit()

    @staticmethod
    def _choose_lesson(lessons, saved=''):
        first = [i for i, r in enumerate(lessons) if re.search(r'(?:第\s*(?:0?1|一)\s*[节课讲]|^\s*0?1\s*[【、.：:])', r['label']) and '预热' not in r['label']]
        return next((i for i,r in enumerate(lessons) if r['resource_id'] == saved), first[0] if len(first) == 1 else -1)

    def _next_missing(self):
        term = self._term()
        if not term: return None
        if not self.store.load_lessons(term['termId'])['fetched_at']:
            return 'lessons'
        if self._force_roster or not self.store.load(term['termId'])['fetched_at']:
            if self._choose_lesson(self._lessons) >= 0:
                return 'students'
            self._force_roster = False
            self._notice = '未能唯一识别第 1 节课，未获取学员；课程选择仅用于查看，不改变名单来源。'
            self.changed.emit()
        return None

    @Slot()
    def activate(self):
        if self._busy or self.owner.busy: return
        self._force_roster = False
        self._load_cache()
        action = 'terms' if not self._terms else self._next_missing()
        if action: self._start(action)

    @Slot()
    def refreshAll(self):
        if self._busy or self.owner.busy: return
        self._force_roster = True
        self._start('terms')

    @Slot(str)
    def filterRows(self, text):
        self._search = text.strip().casefold()
        self._model.set_rows([r for r in self._rows if not self._search or
                             self._search in ' '.join(str(r.get(k) or '') for k in
                                 ('student_id','name','status','student_type','nickname','source')).casefold()])
        self.changed.emit()

    @Slot(int)
    def selectTerm(self, index):
        if self._busy or self.owner.busy or self.owner.workflow.send_busy or not 0 <= index < len(self._terms): return
        self._term_index = index
        self.owner.workflow.select_term_id(self._term()['termId'])
        self.activate()

    def alignTerm(self, term_id):
        index=next((i for i,t in enumerate(self._terms) if str(t['termId'])==str(term_id)),-1)
        if index >= 0 and not self._busy:
            self._term_index=index
            self._load_cache()

    @Slot(int, result=int)
    def termRosterSize(self, index):
        """Cached roster row count of a term, known before a switch so the loading hint is not a lie.

        Read-only probe of the cache table; never fetches from the platform. -1 means unknown.
        """
        if not 0 <= index < len(self._terms):
            return -1
        term_id = str(self._terms[index]['termId'])
        if not hasattr(self, '_term_sizes'):
            self._term_sizes = {}
        if term_id not in self._term_sizes:
            size = -1
            try:
                import sqlite3
                conn = sqlite3.connect(Path(self.registry.db.path).as_uri() + '?mode=ro', uri=True)
                try:
                    row = conn.execute('SELECT rows_json FROM term_rosters WHERE term_id=?', (term_id,)).fetchone()
                    size = len(json.loads(row[0])) if row else 0
                finally:
                    conn.close()
            except Exception:
                size = -1
            self._term_sizes[term_id] = size
        return self._term_sizes[term_id]

    @Slot(int)
    def selectLesson(self, index):
        if not self._busy and 0 <= index < len(self._lessons):
            self._lesson_index = index
            self.store.save_lessons(self._term()['termId'], self._lessons, self._lessons[index]['resource_id'])
            self.changed.emit()

    @Slot()
    def fetchStudents(self):
        if self._term(): self._start('students')

    def _start(self, action):
        if self._busy or self.owner.busy:
            self.owner.toast.emit('已有获取任务正在运行，请等待完成。')
            return
        first_index = self._choose_lesson(self._lessons)
        if action == 'students' and first_index < 0:
            self._notice = '未能唯一识别第 1 节课，已保留原名单；不会使用当前选中的其他课程。'
            self.changed.emit()
            return
        self._action = action
        self._cancelled = False
        self._request_term = dict(self._term() or {})
        self._resource = self._lessons[first_index]['resource_id'] if first_index >= 0 else ''
        username = self.registry.get_setting('completion_username', '')
        password = get_password('completion', username)
        if not password:
            self._notice = '请先在设置中保存追光鲸鱼账号和密码。'
            self.changed.emit()
            return
        task = AcquisitionTask(action, (username, password), cache_dir=self.registry.db.path.parent / 'platform_sessions',
                               term_id=self._request_term.get('termId'), resource_id=self._resource, parent=self)
        self._task = task
        task.succeeded.connect(self._succeeded)
        task.failed.connect(self._failed)
        task.finished.connect(self._release_task)
        task.finished.connect(task.deleteLater)
        self._busy = True
        self._notice = {'terms': '正在获取账号班期…', 'lessons': '正在获取课程列表…',
                        'students': '正在获取全班名单并补齐缺号…'}[action]
        self.changed.emit()
        task.start()

    def _cleanup(self):
        self._busy = False
        self.changed.emit()

    def _release_task(self):
        if self.sender() is self._task:
            self._task = None

    def _failed(self, message):
        self._force_roster = False
        self._notice = '已取消获取，原名单保持不变。' if self._cancelled else message
        self._cleanup()

    def _succeeded(self, data):
        if not self._busy: return
        if self._cancelled:
            self._force_roster = False
            self._notice = '已取消获取，原名单保持不变。'
            self._cleanup()
            return
        next_action = None
        try:
            next_action = self._accept(self._action, data)
        except Exception as exc:
            self._force_roster = False
            self._notice = str(exc) if isinstance(exc, ValueError) else '结果读取或保存失败；请重试。'
        finally:
            self._cleanup()
        if next_action: self._start(next_action)

    def _accept(self, action, data):
        next_action = None
        if action == 'terms':
            old_id = str((self._term() or {}).get('termId', ''))
            self.registry.set_setting('remote_terms', json.dumps(data, ensure_ascii=False))
            self._terms = data
            self.owner.workflow.sync_terms(data,self.store)
            self._term_index = next((i for i, t in enumerate(data) if str(t['termId']) == old_id), 0 if data else -1)
            self._lessons, self._lesson_index = [], -1
            self._load_cache()
            if not data:
                self._notice = '当前账号没有可见班期。'
                self._force_roster = False
            else:
                next_action = 'lessons' if self._force_roster else self._next_missing()
        elif action == 'lessons':
            saved = self.store.load_lessons(self._request_term['termId'])['resource_id'] or self.store.load(self._request_term['termId'])['resource_id']
            index = self._choose_lesson(data, saved)
            self.store.save_lessons(self._request_term['termId'], data, data[index]['resource_id'] if index >= 0 else '')
            self._load_cache()
            next_action = self._next_missing()
        else:
            self.store.save(self._request_term, data, self._resource)
            self.owner.workflow.sync_terms(self._terms,self.store)
            self._force_roster = False
            self._load_cache()
        self.changed.emit()
        return next_action

    @Slot()
    def cancel(self):
        if self._busy:
            self._cancelled = True
            self._force_roster = False
            self._notice = '已取消，正在等待当前网络请求结束；返回结果将被丢弃。'
            self.changed.emit()

    def shutdown(self):
        if self._task and self._task.isRunning():
            self._task.wait()

    @Slot()
    def exportRoster(self):
        if not self._rows: return
        path, _ = QFileDialog.getSaveFileName(None, '导出当前显示名单', '班期学员.xlsx', 'Excel (*.xlsx)')
        if path:
            try:
                export_table(self._model, path if path.lower().endswith('.xlsx') else path + '.xlsx', [])
                self.owner.toast.emit('已按六列显示格式导出，补位状态为已退课')
            except Exception:
                self.owner.toast.emit('导出失败，请检查文件是否被占用。')
