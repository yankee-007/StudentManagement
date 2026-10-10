"""Protect the expensive workbench paths using disposable data and read counts."""
import unittest
from unittest.mock import patch

from app.workflow import Workflow
from tests.test_business_logic import seeded, merged_row
from app.importer import import_rows


class WorkbenchPerformanceTests(unittest.TestCase):
    def campaign(self, backend):
        import_rows(backend.db, [merged_row(i) for i in range(1, 4)])
        backend.workflow.createBatch()
        return backend.workflow

    def test_reenter_reuses_snapshot_and_external_changes_invalidate_it(self):
        with seeded(3) as backend:
            w = self.campaign(backend)
            w.activate()  # initial reconciliation
            rows, selected = w.tableModel.rows, w.selected
            with patch.object(w.store, 'refresh_latest_learning', wraps=w.store.refresh_latest_learning) as refresh, \
                 patch.object(w.store, 'rows', wraps=w.store.rows) as reads:
                w.activate(); w.activate()
                refresh.assert_not_called(); reads.assert_not_called()
                self.assertIs(w.tableModel.rows, rows)
                self.assertIs(w.selected, selected)
                backend.repo.update_profile_field(selected['student_id'], '微信', '否')
                w.activate()
                self.assertEqual(refresh.call_count, 1)
                self.assertEqual(w.selected['wechat'], '否')

    def test_field_visibility_cache_and_single_person_save_do_not_reset_table(self):
        with seeded(3) as backend:
            w = self.campaign(backend)
            layout = w.managedFields
            with patch.object(backend.repo, 'get_setting', wraps=backend.repo.get_setting) as settings:
                for _ in range(20): self.assertEqual(w.managedFields, layout)
                settings.assert_not_called()
            self.assertTrue(w.setFieldVisible('student_id', True))
            self.assertTrue(next(f for f in w.managedFields if f['field_id'] == 'student_id')['show_column'])
            resets = []
            w.tableModel.modelReset.connect(lambda: resets.append(True))
            with patch.object(w.store, 'rows', wraps=w.store.rows) as reads:
                self.assertTrue(w.queueFeedback(w.editorKey, '虚构反馈'))
                self.assertTrue(w.flushFeedback())
                self.assertTrue(w.setFollowupStatusForSelection(w.editorKey, '是'))
            self.assertFalse(resets)
            self.assertTrue(all(call.args[1] == w.selected['student_id'] for call in reads.call_args_list))

    def test_each_history_field_has_independent_visibility_order_and_persistence(self):
        with seeded(3) as backend:
            w = self.campaign(backend)
            first = w._batch
            w.store.save_feedback(first, 'P2026169001A', '第一批虚构反馈')
            w.createBatch(); second = w._batch
            w.store.save_feedback(second, 'P2026169001A', '第二批虚构反馈')
            w.createBatch(); latest = w._batch
            one, two = f'previous_feedback_{first}', f'previous_feedback_{second}'
            self.assertFalse(next(f for f in w.managedFields if f['field_id'] == one)['show_column'])
            self.assertFalse(next(f for f in w.managedFields if f['field_id'] == one)['locked'])
            self.assertTrue(w.setFieldVisible(one, True))
            self.assertEqual(w._rows[0][one], '第一批虚构反馈')
            self.assertNotIn(two, w._rows[0])
            w.filterRows('all', '学员1')
            frozen = set(w._frozen)
            with patch.object(w.store, 'rows', wraps=w.store.rows) as reads:
                self.assertTrue(w.moveField(one, 0))
                reads.assert_not_called()
            self.assertEqual(w.columnKeys[0], one)
            self.assertEqual(w._frozen, frozen)
            self.assertTrue(w.setFieldVisible(two, True))
            self.assertTrue(w.setFieldVisible(one, False))
            self.assertNotIn(one, w._rows[0]); self.assertIn(two, w._rows[0])
            reopened = Workflow(backend)
            self.assertEqual(reopened._batch, latest)
            self.assertEqual(reopened.columnKeys[0], one)
            self.assertFalse(next(f for f in reopened.managedFields if f['field_id'] == one)['show_column'])
            self.assertTrue(next(f for f in reopened.managedFields if f['field_id'] == two)['show_column'])
            w.selectBatch(next(i for i, record in enumerate(w._batches) if record['id'] == first))
            self.assertTrue(w.moveField(two, 0))
            w.selectBatch(0)
            self.assertEqual(w.columnKeys[0], one, 'An unavailable history field must retain its saved position')
            w.createBatch()
            self.assertFalse(next(f for f in w.managedFields if f['field_id'] == f'previous_feedback_{latest}')['show_column'])

    def test_legacy_history_switch_migrates_without_losing_selections(self):
        with seeded(3) as backend:
            w = self.campaign(backend); first = w._batch
            w.createBatch(); second = w._batch
            backend.repo.set_setting('workflow_show_previous_feedback', '1')
            w.reload_rows()
            one = f'previous_feedback_{first}'
            self.assertTrue(next(f for f in w.managedFields if f['field_id'] == one)['show_column'])
            w.createBatch()
            two = f'previous_feedback_{second}'
            self.assertTrue(w.setFieldVisible(one, False))
            self.assertTrue(next(f for f in w.managedFields if f['field_id'] == two)['show_column'])
            w.setColumnFilter(two, 'contains', [], '无匹配')
            self.assertFalse(w.recipientKeys)
            w.setFieldVisible(two, False)
            self.assertIn(two, w._rows[0], 'A hidden field with an active filter still needs its values')

    def test_failed_history_preference_save_rolls_back_and_keeps_layout(self):
        with seeded(3) as backend:
            w=self.campaign(backend); first=w._batch
            w.createBatch(); key=f'previous_feedback_{first}'
            previous=w.managedFields
            with backend.db.connect() as conn:
                conn.execute("""CREATE TRIGGER reject_history_setting BEFORE INSERT ON settings
                    WHEN NEW.key='workflow_history_fields_configured'
                    BEGIN SELECT RAISE(ABORT, 'synthetic preference failure'); END""")
            self.assertFalse(w.setFieldVisible(key,True))
            self.assertEqual(w.managedFields,previous)
            self.assertEqual(backend.repo.get_setting('workflow_field_visibility'),'')


if __name__ == '__main__': unittest.main()
