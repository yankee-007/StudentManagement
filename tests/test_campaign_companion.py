import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from tests.profile_fixtures import insert_profile


class CampaignCompanionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = Backend(Path(self.tmp.name) / 'test.db')
        with self.backend.db.connect() as conn:
            for sid, name in [('001', '张三'), ('002', '李四')]:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-09-29'))
                insert_profile(conn, sid, name, int(sid))
        self.backend.workflow.createBatch()
        self.companion = self.backend.campaignCompanion

    def match(self, title):
        with patch.object(self.backend.profileCompanion, '_active_wecom_title', return_value=title):
            self.companion.refreshContact()

    def test_independent_selection_draft_submit_and_main_selection(self):
        wf = self.backend.workflow
        main = wf.selected['student_id']
        self.match('李四 - 企业微信')
        self.assertEqual(self.companion.selected['student_id'], '002')
        key = self.companion.editorKey
        self.assertTrue(self.companion.saveEditorValue(key, 'draft', '待核实'))
        self.assertEqual(wf.store.rows(wf._batch, '002')[0]['draft'], '待核实')
        self.assertTrue(self.companion.saveEditorValue(key, 'submit', '已处理'))
        self.assertIn('已处理', wf.store.rows(wf._batch, '002')[0]['feedback'])
        self.assertEqual(wf.selected['student_id'], main)
        self.assertEqual(self.companion.selected['student_id'], '002')
        self.assertFalse(self.companion.saveEditorValue(key, 'remark', 'x'))

    def test_ambiguity_stale_key_and_historical_batch(self):
        self.match('张三')
        stale = self.companion.editorKey
        self.match('李四')
        self.assertFalse(self.companion.saveEditorValue(stale, 'submit', 'wrong'))
        self.match('张三 李四')
        self.assertEqual(self.companion.selected, {})
        self.assertFalse(self.companion.saveEditorValue(stale, 'draft', 'wrong'))
        self.match('张三')
        self.companion.setLocked(True)
        old_batch = self.backend.workflow._batch
        self.backend.workflow.createBatch()
        self.assertEqual(self.companion.selected, {})
        self.assertFalse(self.companion.locked)
        self.assertFalse(self.companion.saveEditorValue(stale, 'submit', 'wrong'))
        self.backend.workflow.selectBatch(1)
        self.match('张三')
        self.assertEqual(self.companion.selected, {})
        self.assertEqual(self.backend.workflow._batch, old_batch)

    def test_main_draft_refreshes_float_and_calendar_cannot_write_new_identity(self):
        wf=self.backend.workflow
        self.match('张三')
        self.assertTrue(wf.saveEditorValue(wf.editorKey,'draft','同步草稿'))
        self.assertEqual(self.companion.selected['draft'],'同步草稿')
        self.backend.chooseDate=lambda current:(self.match('李四') or '2099-01-01')
        self.companion.setLeave()
        self.assertFalse(self.backend.repo.get('001').get('exemption_date'))
        self.assertFalse(self.backend.repo.get('002').get('exemption_date'))

    def test_contact_open_uses_current_float_identity_and_separate_prefix(self):
        self.match('李四')
        opener = self.backend.contactOpener
        key = self.companion.editorKey
        with patch('app.contact_opener.ContactOpenTask') as factory:
            self.assertFalse(opener.openCampaignContact('stale', 'x'))
            factory.assert_not_called()
            self.assertTrue(opener.openCampaignContact(key, 'camp-'))
            self.assertEqual(factory.call_args.args[0], 'camp-李四')
            self.assertEqual(opener.campaignPrefix(key), 'camp-')
            self.assertEqual(self.backend.repo.get_setting('profile_contact_prefix', ''), '')
            opener._finished()
        self.match('张三')
        self.assertFalse(opener.openCampaignContact(key, ''))

    def test_class_switch_invalidates_float_key_and_lock(self):
        self.match('张三')
        key = self.companion.editorKey
        self.companion.setLocked(True)
        wf = self.backend.workflow
        wf._classes.append({'name': '另一班', 'path': str(Path(self.tmp.name) / 'other.db')})
        wf.selectClass(1)
        self.assertEqual(self.companion.selected, {})
        self.assertFalse(self.companion.locked)
        self.assertFalse(self.companion.saveEditorValue(key, 'draft', 'wrong'))
        self.assertFalse(self.backend.contactOpener.openCampaignContact(key, ''))


if __name__ == '__main__':
    unittest.main()
