"""Floating campaign feedback editor for the active WeCom contact."""
import json

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .profile_storage import set_exemption


class CampaignCompanion(QObject):
    changed = Signal()
    selectionChanged = Signal()
    noticeChanged = Signal()
    lockedChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._selected = {}
        self._context = None
        self._notice = '打开企业微信的学员聊天窗口以自动识别'
        self._locked = False
        self._editing = False
        self._last_title = ''
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refreshContact)
        owner.workflow.changed.connect(self._workflow_changed)

    def _current_context(self):
        wf = self.owner.workflow
        if not wf._batch or not wf.canEdit:
            return None
        with self.owner.db.connect() as conn:
            latest = conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]
        return (str(self.owner.db.path), wf._batch) if latest == wf._batch else None

    def _sync_context(self):
        context = self._current_context()
        if context == self._context:
            return bool(context)
        self._context = context
        self._last_title = ''
        self._editing = False
        if self._selected:
            self._selected = {}
            self.changed.emit()
            self.selectionChanged.emit()
        if self._locked:
            self._locked = False
            self.lockedChanged.emit()
        self._set_notice('请先选择当前最新催办批次' if not context else '班期或批次已切换，请重新识别学员')
        return bool(context)

    def _workflow_changed(self):
        if not self._sync_context():
            return
        if self._selected:
            sid = self._selected['student_id']
            row = next((r for r in self.owner.workflow._rows if r['student_id'] == sid), None)
            if row and self._real(row):
                if row != self._selected:
                    self._selected = dict(row)
                    self.changed.emit()
                    self.selectionChanged.emit()
            else:
                self._selected = {}
                self._locked = False
                self.changed.emit()
                self.selectionChanged.emit()
                self.lockedChanged.emit()

    @staticmethod
    def _real(row):
        return bool(str(row.get('name') or '').strip() and not row.get('is_placeholder'))

    def _set_notice(self, value):
        if value != self._notice:
            self._notice = value
            self.noticeChanged.emit()

    @Property('QVariantMap', notify=changed)
    def selected(self):
        self._sync_context()
        return self._selected

    @Property(str, notify=changed)
    def editorKey(self):
        self._sync_context()
        if not self._selected or not self._context:
            return ''
        return json.dumps([*self._context, self._selected['student_id']], ensure_ascii=False)

    @Property(bool, notify=changed)
    def canEdit(self):
        return self._sync_context() and bool(self._selected)

    @Property(bool, notify=changed)
    def canSetExemption(self):
        return self.canEdit

    @Property(str, notify=changed)
    def leaveNote(self):
        row = self.selected
        value = row.get('exemption_date', '')
        return (row.get('exemption_text', '') + (' · 已到期，恢复催办' if row.get('exemption_expired') else ' · 包含当天')) if value else '未设置免催日期'

    @Property(str, notify=changed)
    def previousFeedback(self):
        row = self.selected
        if not row:
            return ''
        sid = row['student_id']
        with self.owner.db.connect() as conn:
            entries = list(conn.execute('SELECT c.created_at,f.content FROM campaign_feedback f JOIN campaigns c ON c.id=f.batch_id WHERE f.student_id=? AND f.batch_id<? ORDER BY f.id DESC LIMIT 10', (sid, self._context[1])))
        lines = [r['created_at'].replace('T', ' ') + ' ' + r['content'] for r in entries]
        old = self.owner.repo.get(sid) or {}
        if old.get('feedback_history'):
            lines.append('迁移前反馈：\n' + old['feedback_history'])
        for key, value in old.get('profile_fields', {}).items():
            if '学员学习反馈' in key and value:
                lines.append(key + '：' + str(value))
        return '\n'.join(lines) or '暂无以往反馈'

    @Property(str, notify=noticeChanged)
    def notice(self):
        return self._notice

    @Property(bool, notify=lockedChanged)
    def locked(self):
        self._sync_context()
        return self._locked

    @Slot()
    def open(self):
        self._sync_context()
        self._timer.start()
        self.refreshContact()

    @Slot()
    def close(self):
        self._timer.stop()

    @Slot(bool)
    def setEditing(self, value):
        self._editing = bool(value)

    @Slot(bool)
    def setLocked(self, value):
        if not self._sync_context():
            return
        self._locked = bool(value) and bool(self._selected)
        self.lockedChanged.emit()

    @Slot()
    def refreshContact(self):
        if not self._sync_context() or self._locked:
            return
        title = self.owner.profileCompanion._active_wecom_title()
        if not title:
            if not self._selected:
                self._set_notice('请激活企业微信的独立聊天窗口')
            return
        self._last_title = title
        self._match_title(title)

    @Slot()
    def retryContact(self):
        if not self._sync_context():
            return
        if self._locked:
            self._set_notice('请先解除学员锁定，再重新识别')
            return
        title = self.owner.profileCompanion._active_wecom_title() or self._last_title
        if title:
            self._match_title(title)
        else:
            self._set_notice('请先激活企业微信的独立聊天窗口')

    def _match_title(self, title):
        if not self._sync_context():
            return
        candidates = [r for r in self.owner.workflow._rows if self._real(r) and r['name'].strip() in title] if title not in ('企业微信', 'WeCom') else []
        if len(candidates) != 1:
            if self._selected:
                self._selected = {}
                self.changed.emit()
                self.selectionChanged.emit()
            self._set_notice('当前窗口无法唯一匹配学员' if candidates else '当前聊天名称未匹配到本批次学员')
            return
        row = dict(candidates[0])
        if row != self._selected:
            self._selected = row
            self.changed.emit()
            self.selectionChanged.emit()
        self._set_notice('已定位当前聊天学员 · 修改后自动保存')

    def _valid_key(self, key):
        if not self._sync_context() or not self._selected or key != self.editorKey:
            return False
        return any(r['student_id'] == self._selected['student_id'] and self._real(r) for r in self.owner.workflow._rows)

    @Slot(str, str, str, result=bool)
    def saveEditorValue(self, key, kind, value):
        if not self._valid_key(key):
            self._set_notice('未保存：学员、班期或催办批次已切换')
            return False
        if kind not in ('draft', 'submit'):
            return False
        try:
            wf = self.owner.workflow
            sid = self._selected['student_id']
            if kind == 'draft':
                wf.store.draft(wf._batch, sid, value)
            else:
                wf.store.submit(wf._batch, sid, value)
            wf.reload_rows(prefer=wf._selected.get('student_id'))
            self._workflow_changed()
            self._set_notice('草稿已保存' if kind == 'draft' else '反馈已记录')
            return True
        except Exception as exc:
            self._set_notice('保存失败：' + str(exc))
            return False

    @Slot()
    def setLeave(self):
        key = self.editorKey
        if not self._valid_key(key):
            return
        value = self.owner.chooseDate(self._selected.get('exemption_date', ''))
        if value and self._valid_key(key):
            self._write_leave(key, value)
        elif value:
            self._set_notice('未设置免催：操作期间学员或批次已切换')

    @Slot()
    def clearLeave(self):
        key = self.editorKey
        if self._valid_key(key):
            self._write_leave(key, '')

    def _write_leave(self, key, value):
        if not self._valid_key(key):
            return
        try:
            sid = self._selected['student_id']
            set_exemption(self.owner.db, sid, value)
            self.owner.workflow.reload_rows(prefer=self.owner.workflow._selected.get('student_id'))
            self.owner.profilesModule.refresh()
            self._workflow_changed()
            self._set_notice('免催日期已保存' if value else '已清除免催日期')
        except Exception as exc:
            self._set_notice('保存失败：' + str(exc))
