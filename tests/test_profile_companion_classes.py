import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.database import Database
from app.repository import StudentRepository
from tests.profile_fixtures import insert_profile


class ProfileCompanionClassesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.b = Backend(Path(self.folder.name) / 'first.db')
        self.other = Database(Path(self.folder.name) / 'second.db')
        self.b.workflow._classes.append(dict(name='第二班', path=str(self.other.path)))
        for db, name in ((self.b.db, '测试甲'), (self.other, '测试甲')):
            with db.connect() as conn:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', ('001', name, '2026-10-07'))
                insert_profile(conn, '001', name, 1)
        self.b.repo.set_setting('profile_remark_prefix', 'py101')
        StudentRepository(self.other).set_setting('profile_remark_prefix', 'py102')
        self.c = self.b.profileCompanion
        self.c._active_wecom_title = lambda: ''
        self.addCleanup(self.c.close)

    def test_prefix_disambiguates_and_keeps_main_class(self):
        self.c._match_title('py102 测试甲')
        self.assertEqual(self.c.student['_db_path'], str(self.other.path))
        self.assertEqual(self.c.displayName, 'py102 测试甲')
        self.assertEqual(self.b.workflow.class_index, 0)
        self.assertEqual(self.c.classIndex, 0)
        self.assertEqual(self.c.classOptions[0], '自动识别')
        StudentRepository(self.other).set_setting('profile_contact_prefix', 'py202')
        self.c._match_title('py202测试甲')
        self.assertEqual(self.c.displayName, 'py202 测试甲')
        self.b.profilesModule.setAllClasses(True)
        self.c._match_title('py102测试甲')
        self.assertEqual(self.c.student['_db_path'], str(self.other.path))

    def test_ambiguous_name_manual_scope_and_return_to_auto(self):
        self.c._last_title = '测试甲'
        self.c._match_title('测试甲')
        self.assertFalse(self.c.student)
        self.assertIn('多名', self.c.notice)
        self.c.selectClass(2)
        self.assertEqual(self.c.student['_db_path'], str(self.other.path))
        key = self.c.student['_record_key']
        self.c.queueEditorField(key, '所在地区', '上海')
        self.c.selectClass(1)
        self.assertEqual(StudentRepository(self.other).get('001')['profile_fields']['所在地区'], '上海')
        self.assertFalse(self.c.saveEditorField(key, '所在地区', '误写'))
        self.assertEqual(self.b.repo.get('001')['profile_fields']['所在地区'], '')
        self.c.selectClass(0)
        self.assertFalse(self.c.student)

    def test_saved_remark_and_unique_unprefixed_name(self):
        from app.remark_storage import bootstrap
        bootstrap(self.other)
        with self.other.connect() as conn:
            conn.execute("INSERT INTO student_contacts(student_id,remark) VALUES('001','历史备注 测试甲')")
            conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('002','测试乙','2026-10-07')")
            insert_profile(conn, '002', '测试乙', 2)
        self.c._match_title('历史备注 测试甲')
        self.assertEqual(self.c.student['_db_path'], str(self.other.path))
        self.c._match_title('测试乙')
        self.assertEqual(self.c.student['student_id'], '002')
        self.c._match_title('企业微信')
        self.assertFalse(self.c.student)

    def test_refresh_flushes_typing_and_failed_save_blocks_switch(self):
        self.c._match_title('py101测试甲')
        key = self.c.student['_record_key']
        self.c.queueEditorField(key, '所在地区', '北京')
        self.c._last_checked = 0
        self.c._match_title('py101测试甲')
        self.assertEqual(self.c.student['profile_fields']['所在地区'], '北京')
        self.c.queueEditorField(key, '所在地区', '深圳')
        with patch.object(self.c, 'saveField', return_value=False):
            self.c.selectClass(2)
            self.assertEqual(self.c.student['_record_key'], key)
            self.assertEqual(self.c.classIndex, 0)
            self.c._match_title('py102测试甲')
            self.assertEqual(self.c.student['_record_key'], key)
            self.assertEqual(self.c._pending_edits['所在地区'], '深圳')
        self.c._match_title('py102测试甲')
        self.assertEqual(self.b.repo.get('001')['profile_fields']['所在地区'], '深圳')
        self.assertEqual(self.c.student['_db_path'], str(self.other.path))


if __name__ == '__main__':
    unittest.main()
