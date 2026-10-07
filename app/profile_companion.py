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
        self._class_path = ""
        self._repositories = {}
        self._notice = "打开企业微信的学员聊天窗口以自动识别"
        self._editing = False
        self._last_signature = None
        self._last_checked = 0.0
        self._last_title = ''
        self._pending_edits = {}
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
        if not self._flush_pending():
            return
        self._last_signature = None
        paths = {str(entry['path']) for entry in self.owner.workflow._classes}
        if self._class_path and self._class_path not in paths:
            self._class_path = ''
        if self._student and self._student.get('_db_path') not in paths:
            self._student = {}
        self.changed.emit()

    @Property('QStringList', notify=changed)
    def classOptions(self):
        return ['自动识别'] + [entry['name'] for entry in self.owner.workflow._classes]

    @Property(int, notify=changed)
    def classIndex(self):
        return next((i + 1 for i, entry in enumerate(self.owner.workflow._classes)
                     if str(entry['path']) == self._class_path), 0)

    @Property(str, notify=changed)
    def displayName(self):
        if not self._student:
            return '等待识别'
        return ' '.join(value for value in (self._student.get('_contact_prefix', ''),
                                           self._student['name']) if value)

    @Slot(int)
    def selectClass(self, index):
        entries = self.owner.workflow._classes
        if not 0 <= index <= len(entries) or not self._flush_pending():
            return
        self._class_path = str(entries[index - 1]['path']) if index else ''
        self._last_signature = None
        self._student = {}
        self.changed.emit()
        title = self._active_wecom_title() or self._last_title
        if title:
            self._last_title = title
            self._match_title(title)
        else:
            self._set_notice('请激活企业微信的独立聊天窗口')

    def _repository(self, path):
        path = str(path)
        if path == str(self.owner.db.path):
            return self.owner.repo
        if path not in self._repositories:
            self._repositories[path] = StudentRepository(Database(path))
        return self._repositories[path]

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
        if not self._flush_pending():
            return
        if self._student:
            previous = self._student
            row = self._repository(previous['_db_path']).get(previous['student_id'])
            self._student = dict(row, _db_path=previous['_db_path'], _record_key=previous['_record_key'], class_name=previous['class_name'], _contact_prefix=previous.get('_contact_prefix', '')) if row else {}
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
        entries = [entry for entry in self.owner.workflow._classes
                   if not self._class_path or str(entry['path']) == self._class_path]
        signature = (tuple(str(entry['path']) for entry in entries), title)
        now = monotonic()
        if signature == self._last_signature and now - self._last_checked < 2:
            return
        # Flush even for the same caption: a periodic refresh must not erase typing.
        if not self._flush_pending():
            return
        self._last_checked = now
        candidates, precise = [], []
        try:
            default_prefix = self.owner.workflow.registry.get_setting('contact_default_prefix', '')
            for entry in entries:
                repo = self._repository(entry['path'])
                prefixes = list(dict.fromkeys(value.strip() for value in (
                    repo.get_setting('profile_remark_prefix', ''),
                    repo.get_setting('profile_contact_prefix', default_prefix)) if value.strip()))
                prefix = prefixes[0] if prefixes else ''
                with repo.db.connect() as conn:
                    has_contacts = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='student_contacts'").fetchone()
                    remarks = {r['student_id']: r['remark'] for r in conn.execute('SELECT student_id,remark FROM student_contacts')} if has_contacts else {}
                for row in repo.list_students():
                    if not name_in_chat_title(row.get('name'), title):
                        continue
                    row = dict(row, _db_path=str(entry['path']),
                               _record_key=str(entry['path']) + '|' + row['student_id'],
                               class_name=entry['name'], _contact_prefix=prefix)
                    candidates.append(row)
                    remark = str(remarks.get(row['student_id'], '') or '').strip()
                    compact_title = ''.join(title.split())
                    matched_prefix = next((value for value in prefixes
                                           if name_in_chat_title(''.join((value + row['name']).split()), compact_title)), '')
                    if ((remark and name_in_chat_title(''.join(remark.split()), compact_title)) or matched_prefix):
                        if matched_prefix:
                            row['_contact_prefix'] = matched_prefix
                        precise.append(row)
        except Exception:
            self._last_signature = None
            self._student = {}
            self.changed.emit()
            self._set_notice('班级名单读取失败，请检查班级数据')
            return
        matches = precise or candidates
        if len(matches) != 1:
            self._last_signature = None
            if self._student:
                self._student = {}
                self.changed.emit()
            self._set_notice('匹配到多名学员，请在下拉框选择班级' if matches else
                             '当前聊天名称未匹配到所选班级学员' if self._class_path else
                             '当前聊天名称未匹配到已登记班级的学员')
            return
        self._last_signature = signature
        row = matches[0]
        if self._student != row:
            self._student = row
            self.changed.emit()
        self._set_notice(row['class_name'] + ' · 修改后自动保存')

    @Slot(str, str, result=bool)
    def saveField(self, label, value):
        if not self._student:
            self._set_notice('未定位学员，无法保存')
            return False
        try:
            path = self._student['_db_path']
            repo = self._repository(path)
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
            self._student['_contact_prefix'] = previous.get('_contact_prefix', '')
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
        self._save_timer.start()
        return True

    def _flush_pending(self):
        self._save_timer.stop()
        pending, self._pending_edits = self._pending_edits, {}
        for label, value in pending.items():
            if not self.saveField(label, value):
                self._pending_edits[label] = value
        return not self._pending_edits

    @Slot(bool)
    def setEditing(self, value):
        self._editing = bool(value)
