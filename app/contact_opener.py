"""Open profile, campaign or overview contacts through the shared WeCom adapter."""
import json
from PySide6.QtCore import QObject, Property, Signal, Slot, QThread, QCoreApplication
from .database import Database
from .repository import StudentRepository


class ContactOpenTask(QThread):
    result = Signal(str)

    def __init__(self,contact,parent=None,*,keep_float=True,verify_contact=True):
        super().__init__(parent)
        self.contact=contact
        self.keep_float=keep_float
        self.verify_contact=verify_contact

    def run(self):
        try:
            from .wecom_sender import WeComSender
            WeComSender({'substring_mode':True}).open_contact(self.contact,keep_float=self.keep_float,verify_contact=self.verify_contact)
            message='已搜索联系人（未验证）：' if not self.verify_contact else '已打开联系人浮窗：' if self.keep_float else '已定位联系人，浮窗已关闭：'
            self.result.emit(message+self.contact)
        except Exception as exc:
            self.result.emit('打开联系人失败：'+str(exc))


class ContactOpener(QObject):
    changed = Signal()
    defaultPrefixChanged = Signal()

    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner
        self._worker=None
        self._notice='按姓名包含匹配，可选择是否保留企微浮窗'
        self._keep_float=owner.workflow.registry.get_setting('profile_contact_keep_float','1')=='1'
        self._verify_contact=owner.workflow.registry.get_setting('profile_contact_verify','1')=='1'
        app=QCoreApplication.instance()
        if app:app.aboutToQuit.connect(self.shutdown)

    @Property(bool,notify=changed)
    def active(self):return self._worker is not None

    @Property(str,notify=changed)
    def notice(self):return self._notice

    @Property(bool,notify=changed)
    def keepFloat(self):return self._keep_float

    @Property(bool,notify=changed)
    def verifyContact(self):return self._verify_contact

    @Property(str, notify=defaultPrefixChanged)
    def defaultPrefix(self):
        return self.owner.workflow.registry.get_setting('contact_default_prefix', '')

    @Slot(str, result=bool)
    def setDefaultPrefix(self, value):
        if self.active:
            return False
        value = value.strip()
        if any(ch in value for ch in ('\r', '\n', '\0')):
            self._notice = '联系人前缀不能包含换行'
            self.changed.emit()
            return False
        try:
            self.owner.workflow.registry.set_setting('contact_default_prefix', value)
        except Exception as exc:
            self._notice = '默认前缀保存失败：' + str(exc)
            self.changed.emit()
            return False
        self.defaultPrefixChanged.emit()
        return True

    @Slot(bool)
    def setVerifyContact(self,value):
        if self.active:return
        self.owner.workflow.registry.set_setting('profile_contact_verify','1' if value else '0')
        self._verify_contact=bool(value)
        self.changed.emit()

    @Slot(bool)
    def setKeepFloat(self,value):
        if self.active:return
        self.owner.workflow.registry.set_setting('profile_contact_keep_float','1' if value else '0')
        self._keep_float=bool(value)
        self.changed.emit()

    @Slot(str,result=str)
    def prefix(self,key):
        student=self.owner.profilesModule.selected
        if key!=student.get('_record_key'):return ''
        return StudentRepository(Database(student['_db_path'])).get_setting('profile_contact_prefix',self.defaultPrefix)

    def _campaign_student(self, key):
        wf = self.owner.workflow
        companion = self.owner.campaignCompanion
        try:
            path, batch, sid = json.loads(key)
        except (TypeError, ValueError):
            raise ValueError('学员已切换，请重新点击')
        if not wf.canEdit or path != str(self.owner.db.path) or batch != wf._batch:
            raise ValueError('班期或催办批次已切换，请重新点击')
        with self.owner.db.connect() as conn:
            latest = conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]
        if latest != batch:
            raise ValueError('仅当前最新批次可打开联系人')
        if key not in (wf.editorKey, companion.editorKey):
            raise ValueError('学员已切换，请重新点击')
        row = next((r for r in wf._rows if r.get('student_id') == sid), None)
        if not row or not str(row.get('name') or '').strip() or row.get('is_placeholder'):
            raise ValueError('补位学号或空姓名无法打开联系人')
        return row

    @Slot(str, result=str)
    def campaignPrefix(self, key):
        try:
            self._campaign_student(key)
            return self.campaignContactPrefix
        except ValueError:
            return ''

    @Property(str, notify=changed)
    def campaignContactPrefix(self):
        return self.owner.repo.get_setting('campaign_contact_prefix', self.defaultPrefix)

    @Slot(str, str, result=bool)
    def openCampaignContact(self, key, prefix):
        return self._open_campaign_contact(key, prefix, self._campaign_student)

    @Slot(str, str, result=bool)
    def openOverviewContact(self, key, prefix):
        return self._open_campaign_contact(key, prefix, self.owner.learningOverview.homeworkContact)

    def _open_campaign_contact(self, key, prefix, resolve_student):
        if self.active:
            return False
        try:
            if self.owner.workflow.send_busy:
                raise ValueError('群发正在运行，请结束群发后打开联系人')
            row = resolve_student(key)
            prefix = prefix.strip()
            contact = prefix + row['name'].strip()
            if any(ch in contact for ch in ('\r', '\n', '\0')):
                raise ValueError('联系人名称不能包含换行')
            self.owner.repo.set_setting('campaign_contact_prefix', prefix)
            worker = ContactOpenTask(contact, self, keep_float=self._keep_float, verify_contact=self._verify_contact)
            worker.result.connect(self._result)
            worker.finished.connect(self._finished)
            worker.finished.connect(worker.deleteLater)
            self._worker = worker
            self._notice = '正在打开：' + contact
            worker.start()
            self.changed.emit()
            return True
        except Exception as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    @Slot(str,str,result=bool)
    def openContact(self,key,prefix):
        if self.active:return False
        try:
            if self.owner.workflow.send_busy:raise ValueError('群发正在运行，请结束群发后打开联系人')
            student=self.owner.profilesModule.selected
            if not key or key!=student.get('_record_key'):raise ValueError('学员已切换，请重新点击')
            name=student.get('name','').strip()
            if not name or student.get('is_placeholder'):raise ValueError('补位学号或空姓名无法打开联系人')
            prefix=prefix.strip()
            contact=prefix+name
            if any(ch in contact for ch in ('\r','\n','\0')):raise ValueError('联系人名称不能包含换行')
            StudentRepository(Database(student['_db_path'])).set_setting('profile_contact_prefix',prefix)
            worker=ContactOpenTask(contact,self,keep_float=self._keep_float,verify_contact=self._verify_contact)
            worker.result.connect(self._result)
            worker.finished.connect(self._finished)
            worker.finished.connect(worker.deleteLater)
            self._worker=worker
            self._notice='正在打开：'+contact
            worker.start()
            self.changed.emit()
            return True
        except Exception as exc:
            self._notice=str(exc);self.changed.emit();return False

    @Slot(str)
    def _result(self,message):
        self._notice=message
        self.changed.emit()

    @Slot()
    def _finished(self):
        self._worker=None
        self.changed.emit()

    @Slot()
    def shutdown(self):
        if self._worker:self._worker.wait()
