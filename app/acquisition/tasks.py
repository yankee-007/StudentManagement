"""Background network work; workers never touch SQLite or Qt models."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QThread, Signal

from .completion import CompletionClient
from .homework import HomeworkClient
from .merge_data import merge_students


class AcquisitionTask(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action, completion=None, homework=None, cache_dir=None, term_id=None, resource_id=None, binding=None, parent=None):
        super().__init__(parent)
        self.action, self.completion, self.homework = action, completion, homework
        self.cache_dir = Path(cache_dir)
        self.term_id, self.resource_id, self.binding = term_id, resource_id, binding

    def run(self):
        client = None
        try:
            if self.action in ('verify_completion', 'verify_homework'):
                # A fresh session proves the supplied password, not an old cookie.
                with TemporaryDirectory(prefix='student-login-check-') as folder:
                    if self.action == 'verify_completion':
                        client = CompletionClient(*self.completion, Path(folder) / 'cookies.txt')
                        try:
                            count = len(client.terms())
                        finally:
                            client.close()
                            client = None
                    else:
                        h = HomeworkClient(*self.homework, Path(folder) / 'session.txt')
                        count = len(h.classes())
                    result = {'count': count}
            elif self.action == 'homework_classes':
                h = HomeworkClient(*self.homework, self.cache_dir / 'homework_session.txt')
                result = h.classes()
            else:
                client = CompletionClient(*self.completion, self.cache_dir / 'completion_cookies.txt')
                if self.action == 'terms':
                    result = client.terms()
                elif self.action == 'lessons':
                    result = client.lessons(self.term_id)
                elif self.action == 'students':
                    result = client.students(self.term_id, self.resource_id)
                elif self.action == 'learning':
                    h = HomeworkClient(*self.homework, self.cache_dir / 'homework_session.txt')
                    available = h.classes()
                    bound = next((r for r in available if r['id'] == self.binding['class_id']), None)
                    if not bound or self.binding['course_id'] not in bound['course_ids']:
                        raise ValueError('作业班期或课程已变更，请在设置中重新确认对应关系。')
                    completion = client.learning(self.term_id)
                    homework = h.records(self.binding['class_id'], self.binding['course_id'])
                    result = merge_students(completion, homework)
                    if not result[0]:
                        raise ValueError('两平台没有匹配的在读学员，旧数据未覆盖。')
                else:
                    raise ValueError('未知采集任务')
            self.succeeded.emit(result)
        except ValueError as exc:
            self.failed.emit('登录验证失败，请检查账号、密码、网络及班期访问权限。' if self.action.startswith('verify_') else str(exc))
        except Exception:
            self.failed.emit('登录验证失败，请检查账号、密码、网络及班期访问权限。' if self.action.startswith('verify_') else '获取失败，请检查网络、平台账号和访问权限；原有数据未覆盖。')
        finally:
            self.completion = self.homework = None
            if client:
                client.close()
