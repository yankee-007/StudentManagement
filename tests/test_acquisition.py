import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.acquisition.tasks import AcquisitionTask


class AcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_login_verification_never_reuses_existing_session(self):
        used_paths=[]
        class Client:
            def __init__(self,username,password,path):
                assert (username,password)==('test','raw-password')
                assert not path.exists()
                used_paths.append(path)
            def terms(self):return [1,2]
            def classes(self):return [1,2]
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder, patch('app.acquisition.tasks.CompletionClient',Client), patch('app.acquisition.tasks.HomeworkClient',Client):
            for platform in ('completion','homework'):
                task=AcquisitionTask('verify_'+platform,cache_dir=folder,**{platform:('test','raw-password')})
                results,errors=[],[]
                task.succeeded.connect(results.append)
                task.failed.connect(errors.append)
                task.run()
                self.assertEqual(results,[{'count':2}])
                self.assertFalse(errors)
                self.assertIsNone(task.completion)
                self.assertIsNone(task.homework)
            self.assertTrue(all(not path.parent.exists() for path in used_paths))

    def test_confirmed_binding_is_persistent_and_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = Backend(Path(folder) / 'main.db')
            backend.workflow._classes[0]['term_id'] = '551'
            settings = backend.settingsModule
            settings._homework_classes = [{'id': 23, 'name': '正式课py169', 'course_ids': [2]}]
            self.assertFalse(settings.saveBinding('551', 23, 3))
            self.assertTrue(settings.saveBinding('551', 23, 2))
            self.assertEqual(settings.bindingFor('551')['course_id'], 2)
            self.assertFalse(settings.bindingFor('564'))
            reopened = Backend(Path(folder) / 'main.db')
            self.assertEqual(reopened.settingsModule.bindingFor('551')['class_id'], 23)

    def test_learning_task_merges_native_clients_without_legacy_scripts(self):
        row = {'studentNo': 'P2026169001A', 'realname': '测试学员', 'status': 0,
               **{f'classNum_{i}': None for i in range(1, 33)}}
        row['classNum_1'] = '直播'
        row['classNum_2'] = '未学习'
        homework = {'P2026169001A': {'name': '测试学员', 'status': '在读', 'flags': {1: 'F', 2: 'T'}}}

        class Completion:
            def __init__(self, *args): pass
            def learning(self, term_id):
                assert term_id == 551
                return {'rows': [row]}
            def close(self): pass

        class Homework:
            def __init__(self, *args): pass
            def classes(self): return [{'id': 23, 'course_ids': [2]}]
            def records(self, class_id, course_id):
                assert (class_id, course_id) == (23, 2)
                return homework

        with tempfile.TemporaryDirectory() as folder, patch('app.acquisition.tasks.CompletionClient', Completion), patch('app.acquisition.tasks.HomeworkClient', Homework):
            task = AcquisitionTask('learning', ('user', 'password'), ('admin', 'password'), folder,
                term_id=551, binding={'class_id': 23, 'course_id': 2})
            results, errors = [], []
            task.succeeded.connect(results.append)
            task.failed.connect(errors.append)
            task.run()
            self.assertFalse(errors)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0][0][0]['C1'], 'T')
            self.assertEqual(results[0][0][0]['C2'], 'F')
            self.assertEqual(results[0][0][0]['Z1'], 'F')
            self.assertEqual(results[0][0][0]['Z2'], 'T')


if __name__ == '__main__':
    unittest.main()
