import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from app.backend import Backend
from tests.profile_fixtures import insert_profile


class FeedbackAutosaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backend = Backend(Path(self.tmp.name) / 'test.db')
        with self.backend.db.connect() as conn:
            for sid, name in [('1', '甲'), ('2', '乙')]:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-10-06'))
                insert_profile(conn, sid, name, int(sid), {'微信': '是'})
        self.w = self.backend.workflow
        self.w.createBatch()
        self.key = self.w.editorKey

    def test_typing_coalesces_and_replaces_without_advancing(self):
        with patch.object(self.w.store, 'save_feedback', wraps=self.w.store.save_feedback) as save:
            for i in range(100):
                self.assertTrue(self.w.queueFeedbackForSelection(self.key, str(i)))
            save.assert_not_called()
            QTest.qWait(650)
            self.assertEqual(save.call_count, 1)
        self.assertEqual(self.w.selected['feedback'], '99')
        self.assertEqual(self.w.editorKey, self.key)
        self.assertTrue(self.w.queueFeedbackForSelection(self.key, '修改'))
        self.assertTrue(self.w.flushFeedback())
        self.assertEqual(self.w.selected['feedback'], '修改')
        self.assertEqual(self.w.selected['reply_state'], '已回复')
        self.w.queueFeedbackForSelection(self.key, '')
        self.w.flushFeedback()
        self.assertEqual(self.w.selected['reply_state'], '待反馈')

    def test_switch_flushes_and_rejects_stale_keys(self):
        self.w.queueFeedbackForSelection(self.key, '甲的内容')
        self.w.selectRow(1)
        self.assertEqual(self.w.store.rows(self.w._batch, '1')[0]['feedback'], '甲的内容')
        self.assertFalse(self.w.queueFeedbackForSelection(self.key, '错人'))
        self.w.queueFeedbackForSelection(self.w.editorKey, '乙的内容')
        old_batch = self.w._batch
        self.w.createBatch()
        self.assertEqual(self.w.store.rows(old_batch, '2')[0]['feedback'], '乙的内容')
        self.assertFalse(self.w.queueFeedback(self.key, '错批次'))
        with self.assertRaises(ValueError):
            self.w.store.save_feedback(old_batch, '1', '历史修改')
        self.w._classes.append({'name': '另一班', 'path': str(Path(self.tmp.name) / 'other.db')})
        self.w.queueFeedbackForSelection(self.w.editorKey, '切班前内容')
        store = self.w.store
        batch = self.w._batch
        sid = self.w.selected['student_id']
        self.w.selectClass(1)
        self.assertEqual(store.rows(batch, sid)[0]['feedback'], '切班前内容')

    def test_failure_preserves_pending_text_and_blocks_switch(self):
        self.w.queueFeedbackForSelection(self.key, '保留内容')
        with patch.object(self.w.store, 'save_feedback', side_effect=OSError('模拟写入失败')):
            self.w.selectRow(1)
            self.assertEqual(self.w.editorKey, self.key)
            self.assertEqual(self.w.feedbackValue(self.key), '保留内容')
            self.assertFalse(self.w.flushFeedback())
        self.assertTrue(self.w.flushFeedback())
        self.assertEqual(self.w.selected['feedback'], '保留内容')

    def test_clicked_identity_survives_feedback_sort_change(self):
        self.w.sortField('feedback', False)
        self.w.queueFeedbackForSelection(self.key, '排序到后面')
        self.w.selectRow(1)
        self.assertEqual(self.w.selected['student_id'], '2')
        self.assertEqual(self.w._model.rows[-1]['student_id'], '1')

    def test_legacy_records_and_draft_preserved_until_edit(self):
        batch = self.w._batch
        self.w.store.submit(batch, '1', '原反馈一')
        self.w.store.submit(batch, '1', '原反馈二')
        self.w.store.draft(batch, '1', '旧草稿')
        self.w.reload_rows()
        self.assertEqual(self.w.feedbackValue(self.key), '原反馈一\n原反馈二\n旧草稿')
        self.w.queueFeedbackForSelection(self.key, '修改后的内容')
        self.w.flushFeedback()
        row = self.w.store.rows(batch, '1')[0]
        self.assertEqual(row['feedback'], '修改后的内容')
        self.assertEqual(row['draft'], '')

    def test_frozen_pending_and_float_independent_selection(self):
        self.w.filterRows('pending', '')
        self.w.queueFeedbackForSelection(self.key, '已回复')
        self.w.flushFeedback()
        self.assertEqual(self.w.visibleCount, 2)
        self.assertEqual(self.w.matchedCount, 1)
        self.assertEqual(self.w.editorKey, self.key)
        companion = self.backend.campaignCompanion
        with patch.object(self.backend.profileCompanion, '_active_wecom_title', return_value='乙'):
            companion.refreshContact()
        self.assertTrue(companion.queueFeedbackForSelection(companion.editorKey, '乙的浮窗内容'))
        self.assertFalse(companion.queueFeedbackForSelection(self.key, '错学员'))
        companion.close()
        self.assertEqual(self.w.store.rows(self.w._batch, '2')[0]['feedback'], '乙的浮窗内容')
        self.assertEqual(self.w.editorKey, self.key)


if __name__ == '__main__':
    unittest.main()
