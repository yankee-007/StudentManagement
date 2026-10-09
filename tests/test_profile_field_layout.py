import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.profile_module import FIXED_COLUMNS
from app.profile_storage import definitions
from app.repository import StudentRepository
from tests.profile_fixtures import insert_profile


class ProfileFieldLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        passwords = patch('app.settings_module.get_password', return_value=None)
        passwords.start()
        self.addCleanup(passwords.stop)
        self.path = Path(self.folder.name) / 'fields.db'
        self.backend = Backend(self.path)
        with self.backend.db.connect() as conn:
            for sid, name in [('001', '示例甲'), ('002', '示例乙'), ('003', '示例丙')]:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-10-09'))
                insert_profile(conn, sid, name, int(sid))
        self.profiles = self.backend.profilesModule
        self.profiles.refresh()

    def test_move_keeps_frozen_rows_cursor_and_sort_without_reloading_roster(self):
        p = self.profiles
        p.setColumnFilter('profile:所在地区', 'empty', [], '')
        p.sortField('name', True)
        p.selectRow(1)
        p.autoSaveField(p.selected['student_id'], '所在地区', '上海')
        rows, selected, frozen = p.tableModel.rows, p.selected, p._frozen.copy()
        row_keys = [r['_record_key'] for r in rows]
        filters = dict(p._filters)
        with patch.object(self.backend.repo, 'list_students', side_effect=AssertionError('Layout must reuse loaded students')):
            self.assertTrue(p.moveField('column:name', 0))
            self.assertFalse(p.moveField('missing', 1))
            self.assertTrue(p.moveField('column:name', 0))
        self.assertIs(p.tableModel.rows, rows)
        self.assertIs(p.selected, selected)
        self.assertEqual([r['_record_key'] for r in rows], row_keys)
        self.assertEqual(p._frozen, frozen)
        self.assertEqual(p._filters, filters)
        self.assertTrue(selected['_filter_stale'])
        self.assertEqual(p.tableModel.columns[p._sort][0], 'name')
        self.assertTrue(p._descending)
        p.reapplyFilters()
        self.assertNotIn(selected['_record_key'], [r['_record_key'] for r in p.tableModel.rows])
        reopened = Backend(self.path)
        self.assertEqual(reopened.profilesModule.managedFields[0]['field_id'], 'column:name')

    def test_reset_keeps_values_custom_fields_deletions_and_other_class_settings(self):
        b, p = self.backend, self.profiles
        self.assertTrue(p.addField('联系时间', 'choice', '上午\n晚上', False))
        custom = next(f for f in p.managedFields if f['name'] == '联系时间')
        self.assertTrue(p.autoSaveField('001', '联系时间', '晚上'))
        self.assertTrue(p.deleteField('default_2'))
        p.setFieldVisible('column:profile:QQ', False)
        p.moveField(custom['field_id'], 0)
        values = b.repo.get('001')['profile_fields']
        expected = ['column:' + key for key, _ in FIXED_COLUMNS] + [f['field_id'] for f in definitions(b.db)]
        b.workflow._classes.append({'name': '第二班', 'path': str(Path(self.folder.name) / 'other.db')})
        b.workflow.selectClass(1)
        p.moveField('column:name', 0)
        p.setFieldVisible('column:profile:QQ', False)
        other_layout = p.managedFields
        b.workflow.selectClass(0)
        with patch.object(b.repo, 'list_students', side_effect=AssertionError('Reset must reuse loaded students')):
            self.assertTrue(p.resetFieldLayout())
        self.assertEqual([f['field_id'] for f in p.managedFields], expected)
        self.assertTrue(all(f['show_column'] for f in p.managedFields))
        self.assertEqual(b.repo.get('001')['profile_fields'], values)
        self.assertEqual(next(f for f in p.managedFields if f['field_id'] == custom['field_id'])['options'], ['上午', '晚上'])
        self.assertNotIn('default_2', expected)
        with b.db.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM deleted_profile_fields WHERE field_id='default_2'").fetchone())
        reopened = Backend(self.path)
        self.assertEqual([f['field_id'] for f in reopened.profilesModule.managedFields], expected)
        self.assertEqual(reopened.repo.get('001')['profile_fields'], values)
        b.workflow.selectClass(1)
        self.assertEqual(p.managedFields, other_layout)

    def test_all_classes_does_not_allow_reset(self):
        p = self.profiles
        p.moveField('column:name', 0)
        p.setFieldVisible('column:profile:QQ', False)
        layout = p.managedFields
        p.setAllClasses(True)
        self.assertFalse(p.resetFieldLayout())
        self.assertFalse(p.moveField('column:student_id', 0))
        p.setAllClasses(False)
        self.assertEqual(p.managedFields, layout)

    def test_queued_moves_do_not_wait_for_storage_and_stay_in_the_original_class(self):
        b, p = self.backend, self.profiles
        original_db = b.db
        entered, release = threading.Event(), threading.Event()
        real_save = StudentRepository.set_setting

        def delayed_save(repo, key, value):
            if key == 'profile_field_order':
                entered.set()
                if not release.wait(5):raise TimeoutError('test write was not released')
            real_save(repo, key, value)

        with patch.object(StudentRepository, 'set_setting', autospec=True, side_effect=delayed_save):
            try:
                self.assertTrue(p.moveFieldAsync('column:name', 0))
                self.assertTrue(entered.wait(1))
                self.assertTrue(p.fieldOrderSaving)
                self.assertEqual(p.managedFields[0]['field_id'], 'column:name')
                self.assertTrue(p.moveFieldAsync('column:student_id', 0))
                expected = [f['field_id'] for f in p.managedFields]
                b.workflow._classes.append({'name': '第二班', 'path': str(Path(self.folder.name) / 'other.db')})
                timer = threading.Timer(0.05, release.set)
                timer.start()
                b.workflow.selectClass(1)
                timer.join()
            finally:
                release.set()
                p.flushFieldOrder()
        self.assertFalse(p.fieldOrderSaving)
        self.assertEqual(StudentRepository(original_db).get_setting('profile_field_order'), json.dumps(expected))
        self.assertEqual(p.managedFields[0]['field_id'], 'column:class_name')

    def test_reset_waits_for_queued_order_and_failed_save_rolls_back_layout(self):
        b, p = self.backend, self.profiles
        initial = p.managedFields
        release = threading.Event()
        real_save = StudentRepository.set_setting

        def delayed_save(repo, key, value):
            if not release.wait(5):raise TimeoutError('test write was not released')
            real_save(repo, key, value)

        with patch.object(StudentRepository, 'set_setting', autospec=True, side_effect=delayed_save):
            try:
                self.assertTrue(p.moveFieldAsync('column:name', 0))
                timer = threading.Timer(0.05, release.set)
                timer.start()
                self.assertTrue(p.resetFieldLayout())
                timer.join()
            finally:
                release.set()
                p.flushFieldOrder()
        self.assertEqual(p.managedFields, initial)
        self.assertEqual(b.repo.get_setting('profile_field_order', '[]'), '[]')
        with patch.object(StudentRepository, 'set_setting', side_effect=OSError('模拟写入失败')):
            self.assertTrue(p.moveFieldAsync('column:name', 0))
            self.assertFalse(p.flushFieldOrder())
        self.assertEqual(p.managedFields, initial)
        self.assertIn('保存失败', p.notice)
        self.assertFalse(p.fieldOrderSaving)
        with patch.object(b.db, 'connect', side_effect=OSError('模拟重置失败')):
            self.assertFalse(p.resetFieldLayout())
        self.assertEqual(p.managedFields, initial)
        self.assertIn('恢复默认失败', p.notice)


if __name__ == '__main__':
    unittest.main()
