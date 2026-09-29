import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from tests.profile_fixtures import insert_profile


class AutosaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_scoped_updates_drafts_and_status(self):
        with tempfile.TemporaryDirectory() as folder:
            backend = Backend(Path(folder) / 'test.db')
            with backend.db.connect() as conn:
                for sid in ['001','002']:
                    conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)", (sid,sid,'2026-09-23'))
                    insert_profile(conn,sid,sid,int(sid),{'画像情况':'原值'})
            backend.refresh()
            backend.selectRow(1)
            notifications = []
            backend.selectedStudentChanged.connect(lambda: notifications.append(True))
            self.assertTrue(backend.autoSaveField('001','画像情况','新计划'))
            self.assertEqual(backend.repo.get('001')['profile_fields']['画像情况'],'新计划')
            self.assertEqual(backend.repo.get('002')['profile_fields']['画像情况'],'原值')
            self.assertEqual(notifications, [])
            self.assertFalse(backend.autoSaveField('001','学号','003'))
            self.assertIn('失败',backend.saveNotice)
            self.assertTrue(backend.saveFeedbackDraft('001','未写完的反馈'))
            reopened = Backend(backend.db.path)
            self.assertEqual(reopened.feedbackDraft('001'),'未写完的反馈')
            self.assertEqual(reopened.feedbackDraft('002'),'')
            self.assertTrue(backend.autoSaveStatus('001',{'status':'请假','exemption_end':'2026-12-31'}))
            self.assertEqual(backend.repo.get('001')['next_followup_at'],'2027-01-01')
            self.assertFalse(backend.autoSaveStatus('002',{'status':'请假','exemption_end':''}))
            self.assertEqual(backend.repo.get('002')['status'],'正常')
            backend.repo.set_setting('profile_headers', json.dumps(['学号','姓名','学习计划']))
            backend.refresh()
            backend.selectRow(0)
            before = backend.repo.get('001')['profile_fields'].copy()
            resets, inserts = [], []
            backend.studentModel.modelReset.connect(lambda: resets.append(True))
            backend.studentModel.columnsInserted.connect(lambda *args: inserts.append(True))
            with patch.object(backend, 'refresh', side_effect=AssertionError('不得刷新全班')), patch.object(backend.repo, 'list_students', side_effect=AssertionError('不得读取全班')):
                self.assertTrue(backend.addFeedback('第一次反馈'))
                self.assertTrue(backend.addFeedback('第二次反馈'))
            self.assertEqual(resets, [])
            self.assertEqual(len(inserts), 1)
            self.assertIn('第一次反馈', backend.feedbackHistory)
            self.assertIn('第二次反馈', backend.feedbackHistory)
            self.assertEqual(backend.feedbackDraft('001'), '')
            self.assertEqual(backend.repo.get('001')['profile_fields'], before)
            backend.selectRow(1)
            self.assertNotIn('第一次反馈', backend.feedbackHistory)
            reopened = Backend(backend.db.path)
            self.assertIn('第二次反馈', reopened.repo.get('001')['feedback_history'])
