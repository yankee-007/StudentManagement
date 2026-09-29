"""Floating profile editor bound to the active WeCom chat window."""
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer

from .database import Database
from .repository import StudentRepository
from .profile_storage import definitions
from .contact_match import name_in_chat_title


class ProfileCompanion(QObject):
    changed = Signal()
    noticeChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._student = {}
        self._notice = "打开企业微信的学员聊天窗口以自动识别"
        self._editing = False
        self._last_signature = None
        self._last_checked = 0.0
        self._last_title = ''
        self._pending_edits = {}
        self._pending_title = ''
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(180)
        self._save_timer.timeout.connect(self._flush_pending)
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self.refreshContact)
        owner.profilesModule.layoutChanged.connect(self.reloadStudent)
        owner.profilesModule.fieldSaved.connect(self._profile_saved)
        owner.profilesModule.rosterChanged.connect(self.invalidate)

    @Slot()
    def invalidate(self):
        self._flush_pending()
        self._last_signature = None
        current_path = str(self.owner.db.path)
        if self.owner.profilesModule.allClasses or (self._student and self._student.get('_db_path') != current_path):
            self._student = {}
            self._last_title = ''
            self.changed.emit()
            self._set_notice('班期已切换，请激活该班学员的独立聊天窗口')

    @Property('QVariantMap', notify=changed)
    def student(self):
        return self._student

    @Property(str, notify=noticeChanged)
    def notice(self):
        return self._notice

    @Property('QVariantList', notify=changed)
    def fields(self):
        return self.owner.profilesModule.editor_fields(self._student)

    def _profile_saved(self, path, sid, label):
        if path == self._student.get('_db_path') and sid == self._student.get('student_id'):
            self.reloadStudent()

    @Slot()
    def reloadStudent(self):
        self._flush_pending()
        if self._student:
            previous = self._student
            row = StudentRepository(Database(previous['_db_path'])).get(previous['student_id'])
            self._student = dict(row, _db_path=previous['_db_path'], _record_key=previous['_record_key'], class_name=previous['class_name']) if row else {}
        self.changed.emit()

    def _set_notice(self, value):
        if value != self._notice:
            self._notice = value
            self.noticeChanged.emit()

    @Slot()
    def open(self):
        self._last_signature = None
        self._timer.start()
        self.refreshContact()

    @Slot()
    def close(self):
        self._flush_pending()
        self._timer.stop()

    def _active_wecom_title(self):
        """Return title only when the foreground HWND belongs to WeCom."""
        if not __import__('sys').platform.startswith('win'):
            return ''
        try:
            import win32gui
            import win32process
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindow(hwnd):
                return ''
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            process_handle = kernel32.OpenProcess(0x1000, False, pid)
            if not process_handle:
                return ''
            try:
                buffer = ctypes.create_unicode_buffer(32768)
                size = ctypes.c_ulong(len(buffer))
                if not kernel32.QueryFullProcessImageNameW(process_handle, 0, buffer, ctypes.byref(size)):
                    return ''
                executable = Path(buffer.value).name.casefold()
            finally:
                kernel32.CloseHandle(process_handle)
            if executable not in ('wxwork.exe', 'wecom.exe'):
                return ''
            return win32gui.GetWindowText(hwnd).strip()
        except Exception:
            return ''

    @Slot()
    def refreshContact(self):
        # Trust the actual foreground HWND, not a potentially delayed Qt focus signal.
        title = self._active_wecom_title()
        if not title:
            self._last_signature = None
            if not self._student:
                self._set_notice('请激活企业微信的独立聊天窗口')
            return
        self._last_title = title
        self._match_title(title)

    @Slot()
    def retryContact(self):
        """Retry the last observed WeCom caption even while this editor has focus."""
        self._last_signature = None
        title = self._active_wecom_title() or self._last_title
        if title:self._match_title(title)
        else:self._set_notice('请先激活企业微信的独立聊天窗口')

    def _match_title(self, title):
        if self._pending_edits and title != self._pending_title:
            self._flush_pending()
        profile_module = self.owner.profilesModule
        if profile_module.allClasses:
            if self._student:
                self._student = {}
                self.changed.emit()
            self._last_signature = None
            self._set_notice('请先在画像模块选择单个班期')
            return
        entry = self.owner.workflow._classes[self.owner.workflow.class_index]
        signature = (str(entry['path']), title)
        now = monotonic()
        if signature == self._last_signature and now - self._last_checked < 2:
            return
        self._last_checked = now
        repo = self.owner.repo
        # Avoid matching the main window, whose caption has no contact name.
        candidates = [row for row in repo.list_students() if name_in_chat_title(row.get('name'), title)]
        if len(candidates) != 1:
            self._last_signature = None
            if self._student:
                self._student = {}
                self.changed.emit()
            self._set_notice('当前窗口无法唯一匹配学员' if candidates else '当前聊天名称未匹配到本班学员')
            return
        self._last_signature = signature
        row = candidates[0]
        row['_db_path'] = str(entry['path'])
        row['_record_key'] = str(entry['path']) + '|' + row['student_id']
        row['class_name'] = entry['name']
        if self._student != row:
            self._student = row
            self.changed.emit()
        self._set_notice('已定位当前聊天学员 · 修改后自动保存')

    @Slot(str, str, result=bool)
    def saveField(self, label, value):
        if not self._student:
            self._set_notice('未定位学员，无法保存')
            return False
        try:
            path = self._student['_db_path']
            repo = self.owner.repo if path == str(self.owner.db.path) else StudentRepository(Database(path))
            previous = self._student
            date_field = label == '免催日期' or any(item['name'] == label and item['kind'] == 'date' for item in definitions(repo.db))
            if label == '免催日期':
                from .profile_storage import set_exemption
                set_exemption(repo.db, self._student['student_id'], value)
            else:
                repo.update_profile_field(self._student['student_id'], label, value)
            self._student = repo.get(self._student['student_id']) or self._student
            self._student['_db_path'] = str(repo.db.path)
            self._student['_record_key'] = previous['_record_key']
            self._student['class_name'] = previous.get('class_name', '')
            if date_field:
                self.changed.emit()
            self._set_notice('已自动保存')
            if path == str(self.owner.db.path) and label in {'微信', '免催日期', '学员状态', '差的课程', '差的作业', '合计完课', '合计作业'}:
                self.owner.workflow.refresh_live(keep_query=True)
            self.owner.profilesModule.reflect_saved(str(repo.db.path),self._student['student_id'])
            return True
        except Exception as exc:
            self._set_notice('保存失败：' + str(exc))
            return False

    @Slot(str,str,str,result=bool)
    def saveEditorField(self, key, label, value):
        if key != self._student.get('_record_key'):
            self._set_notice('学员已切换，未保存')
            return False
        self._pending_edits.pop(label, None)
        self._flush_pending()
        return self.saveField(label,value)

    @Slot(str,str,str,result=bool)
    def queueEditorField(self, key, label, value):
        if key != self._student.get('_record_key'):
            self._set_notice('学员已切换，未保存')
            return False
        self._pending_edits[label] = value
        self._pending_title = self._last_title
        self._save_timer.start()
        return True

    def _flush_pending(self):
        self._save_timer.stop()
        pending, self._pending_edits = self._pending_edits, {}
        for label, value in pending.items():
            self.saveField(label, value)

    @Slot(bool)
    def setEditing(self, value):
        self._editing = bool(value)
