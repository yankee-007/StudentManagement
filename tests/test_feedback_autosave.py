import json
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
        self.backend.repo.set_setting('snapshot', json.dumps([dict(student_id=sid, flags={'c1':'F', 'z1':'F'}) for sid in ('1', '2')]))
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

    def test_followup_is_explicit_and_feedback_does_not_overwrite_it(self):
        self.w.store.save_feedback(self.w._batch, '1', '未接听电话')
        self.w.reload_rows()
        self.assertEqual(self.w.selected['reply_state'], '已回复')
        self.assertEqual(self.w.selected['followup_status'], '否')
        self.assertTrue(self.w.setFollowupStatusForSelection(self.key, '是'))
        self.w.queueFeedbackForSelection(self.key, '新的反馈')
        self.w.flushFeedback()
        self.assertEqual(self.w.selected['followup_status'], '是')
        self.assertFalse(self.w.setFollowupStatusForSelection(self.key, '其他'))
        self.assertFalse(self.w.setFollowupStatusForSelection(json.dumps(['wrong',self.w._batch,'1']), '否'))
        self.assertTrue(self.w.setFollowupStatusForSelection(self.key, '否'))
        self.assertIn(('followup_status','可跟进状态'),self.w._model.columns)

    def test_followup_history_annotation_preserves_feedback_and_batch_isolation(self):
        old = self.w._batch
        self.w.store.save_feedback(old, '1', '好的')
        self.w.store.set_followup_status(old, '1', '是')
        self.w.createBatch()
        self.assertEqual(self.w.selected['followup_status'], '否')
        self.w.selectBatch(1)
        self.assertFalse(self.w.canEdit)
        self.assertEqual(self.w.selected['followup_status'], '是')
        self.assertTrue(self.w.setFollowupStatusForSelection(self.w.editorKey, '否'))
        self.assertEqual(self.w.selected['feedback'], '好的')
        self.assertFalse(self.w.queueFeedbackForSelection(self.w.editorKey, '禁止覆盖历史'))
        self.assertEqual(len(self.w.batches),2)

    def test_followup_filter_export_and_reopen(self):
        self.assertTrue(self.w.setFollowupStatusForSelection(self.key,'是'))
        self.w.setColumnFilter('followup_status','values',['是'],'')
        self.assertEqual(self.w.visibleCount,1)
        self.assertTrue(self.w.setFollowupStatusForSelection(self.key,'否'))
        self.assertEqual(self.w.visibleCount,1)  # 冻结筛选，标记修改不跳走。
        self.w.reapplyFilters()
        self.assertEqual(self.w.visibleCount,0)
        from openpyxl import load_workbook
        output=Path(self.tmp.name)/'followup.xlsx'
        self.w.export_to_path(['name','followup_status'],str(output))
        book=load_workbook(output,read_only=True)
        values=list(book.active.values)
        self.assertEqual(values[0],('姓名','可跟进状态'))
        self.assertTrue(all(row[1]=='否' for row in values[1:]))
        book.close()
        self.w.store.set_followup_status(self.w._batch,'1','是')
        reopened=Backend(self.backend.db.path)
        self.assertEqual(reopened.workflow.store.rows(self.w._batch,'1')[0]['followup_status'],'是')

    def test_followup_counts_use_flags_not_reply_and_preserve_filtered_selection(self):
        with self.backend.db.connect() as conn:conn.execute("UPDATE class_roster SET status='在读'")
        self.w.createBatch()
        key = self.w.editorKey
        self.w.store.save_feedback(self.w._batch, '1', '好的')
        self.w.reload_rows()
        self.assertEqual(sum(r['followable'] for r in self.w.dashboard['completion']['courses']),0)
        self.assertTrue(self.w.setFollowupStatusForSelection(key,'是'))
        self.assertEqual(sum(r['followable'] for r in self.w.dashboard['completion']['courses']),1)
        self.assertEqual(self.w.editorKey,key)
        self.w.createBatch()
        self.w.selectBatch(1)
        self.assertEqual(sum(r['followable'] for r in self.w.dashboard['completion']['courses']),1)
        with self.assertRaises(ValueError):self.w.store.set_followup_status(self.w._batch,'unknown','是')

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

    def test_frozen_blank_feedback_and_float_independent_selection(self):
        self.w.filterRows('targets', '')
        self.w.setColumnFilter('feedback', 'empty', [], '')
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

    def test_shortcuts_persist_deduplicate_and_are_class_local(self):
        self.assertEqual(self.w.feedbackShortcuts, ['答应补课', '未接听电话'])
        self.assertTrue(self.w.addFeedbackShortcut('  已联系家长  '))
        self.assertTrue(self.w.addFeedbackShortcut('已联系家长'))
        self.assertFalse(self.w.addFeedbackShortcut('   '))
        self.assertFalse(self.w.addFeedbackShortcut('多行\n选项'))
        expected = ['答应补课', '未接听电话', '已联系家长']
        self.assertEqual(self.w.feedbackShortcuts, expected)
        self.assertEqual(Backend(self.backend.db.path).workflow.feedbackShortcuts, expected)
        self.w._classes.append({'name': '另一班', 'path': str(Path(self.tmp.name) / 'other.db')})
        self.w.selectClass(1)
        self.assertEqual(self.w.feedbackShortcuts, ['答应补课', '未接听电话'])
        self.w.selectClass(0)
        self.assertEqual(self.w.feedbackShortcuts, expected)


if __name__ == '__main__':
    unittest.main()
