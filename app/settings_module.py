"""Account names in the registry database; passwords only in Windows Vault."""
from PySide6.QtCore import QObject, Property, Signal, Slot, QCoreApplication

from .credentials import get_password, set_password
from .acquisition.tasks import AcquisitionTask

ACCOUNT_KEYS = {'completion':'completion_username','homework':'homework_admin_id'}


class SettingsModule(QObject):
    changed = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self._accounts={}
        self._homework_classes=[]
        self._busy=False
        self._task=None
        self._verification={}
        self._verifying_platform=''
        self._notice='此页保存的账号写入本工具数据库，密码写入当前 Windows 用户的凭据管理器。'
        app=QCoreApplication.instance()
        if app:app.aboutToQuit.connect(self.shutdown)
        self.refresh()

    def shutdown(self):
        if self._task and self._task.isRunning():self._task.wait()

    @Property('QVariantMap',notify=changed)
    def accounts(self):return self._accounts

    @Property(str,notify=changed)
    def notice(self):return self._notice

    @Property('QVariantList',notify=changed)
    def homeworkClasses(self):return self._homework_classes

    @Property(bool,notify=changed)
    def busy(self):return self._busy

    @Property('QVariantMap',notify=changed)
    def verification(self):return self._verification

    @Property(str,notify=changed)
    def verifyingPlatform(self):return self._verifying_platform

    @Slot(str)
    def clearVerification(self,platform):
        self._verification.pop(platform,None)
        self.changed.emit()

    @Slot(str,str,str,result=bool)
    def verifyLogin(self,platform,username,password):
        if self._busy or self.owner.busy or self.owner.termsModule.busy:
            self._notice='请等待当前获取或验证任务完成。';self.changed.emit();return False
        try:
            if platform not in ACCOUNT_KEYS:raise ValueError('未知平台')
            username=username.strip()
            if not username:raise ValueError('请填写账号')
            password=password or get_password(platform,username)
            if not password:raise ValueError('请填写密码，或先保存该账号的密码')
            task=AcquisitionTask('verify_'+platform,cache_dir=self.owner.workflow.registry.db.path.parent/'platform_sessions',
                                 parent=self,**{platform:(username,password)})
            self._task=task
            self._verifying_platform=platform
            self._verification[platform]={'state':'pending','message':'正在重新登录并验证班期访问权限…'}
            task.succeeded.connect(self._login_verified)
            task.failed.connect(self._login_failed)
            task.finished.connect(self._release_task)
            task.finished.connect(task.deleteLater)
            self._busy=True
            self.changed.emit()
            task.start()
            return True
        except ValueError as exc:
            self._notice=str(exc)
        except Exception:
            self._notice='无法读取保存的密码或启动验证，请检查凭据管理器。'
        self.changed.emit();return False

    def _login_verified(self,result):
        self._verification[self._verifying_platform]={'state':'success','message':f"登录验证成功，可访问 {result['count']} 个班期。"}
        self._verifying_platform=''
        self._busy=False
        self.changed.emit()

    def _login_failed(self,message):
        self._verification[self._verifying_platform]={'state':'error','message':message}
        self._verifying_platform=''
        self._busy=False
        self.changed.emit()

    def _release_task(self):
        if self.sender() is self._task:self._task=None

    @Property('QVariantList',notify=changed)
    def termClasses(self):
        return [{'termId':r.get('term_id') or '', 'name':r['name']} for r in self.owner.workflow._classes if r.get('term_id')]

    @Slot(str,result='QVariantMap')
    def bindingFor(self,term_id):
        with self.owner.workflow.registry.db.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS homework_bindings (term_id TEXT PRIMARY KEY, class_id INTEGER NOT NULL, course_id INTEGER NOT NULL, class_name TEXT NOT NULL)')
            row=conn.execute('SELECT class_id,course_id,class_name FROM homework_bindings WHERE term_id=?',(str(term_id),)).fetchone()
            return dict(row) if row else {}

    @Slot()
    def fetchHomeworkClasses(self):
        if self._busy or self.owner.busy or self.owner.termsModule.busy:return
        username=self.owner.workflow.registry.get_setting('homework_admin_id','')
        password=get_password('homework',username)
        if not password:
            self._notice='请先保存作业平台账号和密码。';self.changed.emit();return
        task=AcquisitionTask('homework_classes',homework=(username,password),cache_dir=self.owner.workflow.registry.db.path.parent/'platform_sessions',parent=self)
        self._task=task
        task.succeeded.connect(self._classes_loaded)
        task.failed.connect(self._classes_failed)
        task.finished.connect(self._release_task)
        task.finished.connect(task.deleteLater)
        self._busy=True;self._notice='正在获取作业平台班级…';self.changed.emit()
        task.start()

    def _classes_loaded(self,classes):
        self._homework_classes=classes;self._busy=False
        self._notice=f'已获取 {len(classes)} 个作业平台班级；请选择并确认对应关系。'
        self.changed.emit()

    def _classes_failed(self,message):
        self._busy=False;self._notice=message;self.changed.emit()

    @Slot(str,int,int,result=bool)
    def saveBinding(self,term_id,class_id,course_id):
        try:
            if not term_id or not any(str(r.get('term_id'))==str(term_id) for r in self.owner.workflow._classes):
                raise ValueError('请选择追光鲸鱼班期。')
            entry=next((r for r in self._homework_classes if r['id']==class_id),None)
            if not entry or course_id not in entry['course_ids']:
                raise ValueError('请选择有效的作业班级和课程。')
            with self.owner.workflow.registry.db.connect() as conn:
                conn.execute('CREATE TABLE IF NOT EXISTS homework_bindings (term_id TEXT PRIMARY KEY, class_id INTEGER NOT NULL, course_id INTEGER NOT NULL, class_name TEXT NOT NULL)')
                conn.execute('INSERT INTO homework_bindings(term_id,class_id,course_id,class_name) VALUES(?,?,?,?) ON CONFLICT(term_id) DO UPDATE SET class_id=excluded.class_id,course_id=excluded.course_id,class_name=excluded.class_name',
                             (str(term_id),class_id,course_id,entry['name']))
            self._notice='班期对应关系已确认并保存。';self.changed.emit();return True
        except ValueError as exc:
            self._notice=str(exc);self.changed.emit();return False

    @Slot()
    def refresh(self):
        accounts={}
        try:
            for platform,key in ACCOUNT_KEYS.items():
                username=self.owner.workflow.registry.get_setting(key,'')
                accounts[platform]={'username':username,'saved':bool(get_password(platform,username))}
            self._accounts=accounts
        except Exception:
            self._notice='无法访问 Windows 凭据管理器，请检查当前用户的凭据服务。'
        self.changed.emit()

    @Slot(str,str,str,result=bool)
    def saveAccount(self,platform,username,password):
        if self._busy:return False
        try:
            if platform not in ACCOUNT_KEYS:raise ValueError('未知平台')
            username=username.strip()
            if not username:raise ValueError('请填写账号')
            saved=get_password(platform,username)
            if password:
                set_password(platform,username,password)
            elif not saved:
                raise ValueError('请填写密码；更换账号时需重新输入密码')
            self.owner.workflow.registry.set_setting(ACCOUNT_KEYS[platform],username)
            self._notice='已保存。此页输入的密码已写入 Windows 凭据管理器，下次从界面获取数据时生效。'
            self.refresh()
            return True
        except Exception as exc:
            self._notice='保存失败：'+str(exc)
            self.changed.emit()
            return False
