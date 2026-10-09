"""Qt-facing AI configuration and frozen campaign generation sessions."""
import hashlib
import json
from threading import Event

from PySide6.QtCore import QObject, Property, QCoreApplication, QThread, Signal, Slot

from . import ai_campaign as ai
from .credentials import get_password, set_password
from .sending_store import PROTECTED

CONFIG_KEY = 'ai_campaign_config'


class GenerationWorker(QThread):
    completed = Signal(object)
    progress = Signal(int, int)

    def __init__(self, students, config, key, template, connection_test=False, parent=None):
        super().__init__(parent)
        self.students, self.config, self.key, self.template = students, config, key, template
        self.connection_test = connection_test
        self.cancel = Event()

    def run(self):
        try:
            if self.connection_test:
                raw = ai.chat(self.config, self.key, [dict(role='user', content='只返回JSON：{"ok":true}')])
                if json.loads(raw) != {'ok': True}:
                    raise ValueError('连接可达，但模型未按要求返回 JSON')
                result = dict(test=True)
            else:
                valid, failures = ai.generate(self.students, self.config, self.key, self.template,
                                               self.cancel, self.progress.emit)
                result = dict(valid=valid, failures=failures)
        except ValueError as exc:
            result = dict(error=str(exc))
        except Exception:
            # Unexpected provider/transport exceptions may contain tokens or student data.
            result = dict(error='AI 请求未完成，请检查配置、网络或模型 JSON 支持')
        finally:
            self.key = ''
        self.completed.emit(result)


class AiCampaignModule(QObject):
    changed = Signal()
    configChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._config = dict(ai.DEFAULTS)
        try:
            raw = json.loads(owner.workflow.registry.get_setting(CONFIG_KEY, '{}'))
            self._config.update({k: v for k, v in raw.items() if k in ai.DEFAULTS})
        except (ValueError, AttributeError):
            pass
        self._worker = None
        self._purpose = ''
        self._notice = '先在设置中保存 AI 服务配置；生成时会把姓名、学号及当前欠账发送至该服务。'
        self._students = []
        self._results = {}
        self._failures = {}
        self._fingerprint = ''
        self._template = {}
        self._completed = 0
        self._total = 0
        self._ready = False
        self._retry_list = 0
        self.owner.groupCenter.rowsChanged.connect(self.changed.emit)
        self.owner.workflow.changed.connect(self.changed.emit)
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    @Property('QVariantMap', notify=configChanged)
    def config(self):
        return dict(self._config)

    @Property(bool, notify=changed)
    def busy(self):
        return self._worker is not None

    @Property(str, notify=changed)
    def notice(self):
        return self._notice

    @Property(int, notify=changed)
    def currentLesson(self):
        return int(self.owner.workflow.dashboard.get('opened') or 0)

    @Property(int, notify=changed)
    def completed(self):
        return self._completed

    @Property(int, notify=changed)
    def total(self):
        return self._total

    @Property(bool, notify=changed)
    def ready(self):
        return self._ready and not self.busy

    @Property(int, notify=changed)
    def failureCount(self):
        return len(self._failures)

    @Property('QVariantList', notify=changed)
    def results(self):
        return [dict(studentId=s['student_id'], name=s['name'], text=self._results.get(s['student_id'], ''),
                     error=self._failures.get(s['student_id'], ''), kind=s['diagnostic']['kind']) for s in self._students]

    def _credential_id(self, config):
        return config['provider'] + '|' + config['base_url']

    @Slot('QVariantMap', str, result=bool)
    def saveConfig(self, raw, key):
        if self.busy:
            return False
        try:
            config = ai.normalize_config(raw)
            account = self._credential_id(config)
            try:
                if key.strip():
                    set_password('ai_campaign', account, key.strip())
                    saved = True
                else:
                    saved = bool(get_password('ai_campaign', account))
            except Exception:
                raise ValueError('无法访问 Windows 凭据管理器，请检查凭据服务') from None
            if not saved:
                raise ValueError('请填写 API Key；服务地址改变后需重新保存对应密钥')
            self.owner.workflow.registry.set_setting(CONFIG_KEY, json.dumps(config, ensure_ascii=False))
            self._config = config
            self.configChanged.emit()
            self._notice = 'AI 配置已保存，API Key 由 Windows 凭据管理器保管，不在界面回显。'
            self.changed.emit()
            return True
        except (ValueError, TypeError, OverflowError) as exc:
            self._notice = '保存失败：' + str(exc)
        except Exception:
            self._notice = '保存失败，请检查本地设置与 Windows 凭据管理器。'
        self.changed.emit()
        return False

    def _launch(self, students, template, mode, purpose):
        if self.busy:
            return False
        try:
            config = ai.normalize_config(dict(self._config, mode=mode))
            try:
                key = get_password('ai_campaign', self._credential_id(config))
            except Exception:
                raise ValueError('无法读取 Windows 凭据，请检查凭据服务') from None
            if not key:
                raise ValueError('请先在设置中保存 API Key')
            worker = GenerationWorker(students, config, key, template, purpose == 'test', self)
            self._worker = worker
            self._purpose = purpose
            self._completed = 0
            self._total = len(students)
            self._notice = '正在测试连接…' if purpose == 'test' else f'正在生成 {len(students)} 人的话术…'
            worker.progress.connect(self._progress)
            worker.completed.connect(self._receive)
            worker.finished.connect(self._finished)
            worker.start()
            self.changed.emit()
            return True
        except ValueError as exc:
            self._notice = str(exc)
        except Exception:
            self._notice = '无法读取 AI 配置或 Windows 凭据，请检查设置。'
        self.changed.emit()
        return False

    @Slot(result=bool)
    def testConnection(self):
        return self._launch([], {}, self._config['mode'], 'test')

    def _capture(self, keys):
        wf = self.owner.workflow
        if not wf.canEdit or not keys or list(keys) != wf.recipientKeys:
            raise ValueError('班期、批次或筛选已变化，请重新打开生成窗口')
        students = []
        for row in wf._scope_rows():
            if not row.get('name', '').strip() or row.get('is_placeholder'):
                continue
            students.append(dict(student_id=row['student_id'], name=row['name'],
                                 diagnostic=ai.diagnose(row.get('courses'), row.get('homework'))))
        if len({s['student_id'] for s in students}) != len(students):
            raise ValueError('学号重复，不能生成话术')
        if len({s['name'].strip() for s in students}) != len(students):
            raise ValueError('名单姓名重复，不能唯一定位联系人')
        snapshot = [list(keys), students, self.currentLesson]
        fingerprint = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False).encode('utf-8')).hexdigest()
        return students, fingerprint

    @Slot(result=bool)
    def reset(self):
        if self.busy:
            return False
        self._students, self._results, self._failures = [], {}, {}
        self._fingerprint = ''
        self._ready = False
        self._completed = self._total = 0
        self.changed.emit()
        return True

    @Slot('QVariantList', int, str, result=bool)
    def start(self, keys, lesson, mode):
        if self.busy or self.owner.busy or self.owner.termsModule.busy or self.owner.groupCenter.active:
            return False
        try:
            students, fingerprint = self._capture(keys)
            selected_lesson = lesson or self.currentLesson
            if selected_lesson < 1:
                raise ValueError('快照没有已开课节次，请手动选择话术模板')
            template = ai.load_template(selected_lesson)
            if not self._launch(students, template, mode, 'campaign'):
                return False
            self._students, self._fingerprint, self._template = students, fingerprint, template
            self._results, self._failures, self._ready = {}, {}, False
            self.changed.emit()
            return True
        except ValueError as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    @Slot('QVariantList', str, result=bool)
    def retryFailed(self, keys, mode):
        if self.busy or not self._ready:
            return False
        try:
            if self._capture(keys)[1] != self._fingerprint:
                raise ValueError('学习数据或名单已变化，请重新生成')
            students = [s for s in self._students if s['student_id'] in self._failures]
            return bool(students) and self._launch(students, self._template, mode, 'campaign')
        except ValueError as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    @Slot(str, str, result=bool)
    def editResult(self, sid, text):
        if self.busy or not self._ready:
            return False
        student = next((s for s in self._students if s['student_id'] == sid), None)
        if not student:
            return False
        try:
            self._results[sid] = ai.validate_text(text, student['diagnostic'])
            self._failures.pop(sid, None)
            self._notice = '该学员话术已补齐。'
            self.changed.emit()
            return True
        except ValueError as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    @Slot(str, 'QVariantList', result=bool)
    def createList(self, title, keys):
        if self.busy or not self._ready or self.owner.busy or self.owner.termsModule.busy:
            return False
        try:
            students, fingerprint = self._capture(keys)
            if fingerprint != self._fingerprint:
                raise ValueError('学习数据或名单已变化，请重新生成')
            created = self.owner.groupCenter.createFromAiCampaign(title, students, self._results,
                                                                  self._failures, self._template['index'])
            if not created:
                self._notice = self.owner.groupCenter.status
                self.changed.emit()
            return created
        except ValueError as exc:
            self._notice = str(exc)
            self.changed.emit()
            return False

    def _retry_rows(self):
        center = self.owner.groupCenter
        return [row for row in center._rows_cache if not json.loads(row['content'])
                and not row['message'] and row['state'] not in PROTECTED
                and json.loads(row['learning_data']).get('ai_generation', {}).get('error')]

    @Property(int, notify=changed)
    def listFailureCount(self):
        return len(self._retry_rows())

    @Slot(int, result=bool)
    def retryList(self, list_id):
        center = self.owner.groupCenter
        if self.busy or center.active or list_id != center.selected.get('id'):
            return False
        rows = self._retry_rows()
        if not rows:
            return False
        try:
            metadata = [json.loads(r['learning_data'])['ai_generation'] for r in rows]
            indices = {m['template_index'] for m in metadata}
            # Lists created by this module have one selected template.
            if len(indices) != 1:
                raise ValueError('该名单包含不同模板，请分别手动补写')
            students = [m['student'] for m in metadata]
            template = ai.load_template(next(iter(indices)))
            self._retry_list = list_id
            return self._launch(students, template, self._config['mode'], 'list')
        except (ValueError, KeyError):
            self._notice = '无法恢复失败项的模板或学习数据，请在个人消息中补写。'
            self.changed.emit()
            return False

    def _progress(self, completed, total):
        self._completed, self._total = completed, total
        self.changed.emit()

    def _receive(self, result):
        if result.get('error'):
            self._notice = result['error']
            if self._purpose == 'campaign':
                for student in self._students:
                    sid = student['student_id']
                    if sid not in self._results:
                        self._failures[sid] = result['error']
                self._ready = True
            return
        if result.get('test'):
            self._notice = '连接测试通过，模型可返回 JSON（仅发送了虚构测试文本）。'
            return
        if self._purpose == 'list':
            self.owner.groupCenter.applyAiRetries(self._retry_list, result['valid'], result['failures'])
            self._notice = self.owner.groupCenter.status
            return
        else:
            self._results.update(result['valid'])
            for sid in result['valid']:
                self._failures.pop(sid, None)
            self._failures.update(result['failures'])
            self._ready = True
        self._notice = f"本轮成功 {len(result['valid'])} 人，失败 {len(result['failures'])} 人；可补写或重试后创建名单，不会自动发送。"

    def _finished(self):
        worker = self._worker
        self._worker = None
        if worker:
            worker.deleteLater()
        self.changed.emit()

    @Slot()
    def cancel(self):
        if self._worker:
            self._worker.cancel.set()
            self._notice = '正在停止，等待当前请求返回；已生成的结果会保留。'
            self.changed.emit()

    def shutdown(self):
        if self._worker:
            self._worker.cancel.set()
            self._worker.wait()
