import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.database import Database
from app.repository import StudentRepository
from tests.profile_fixtures import insert_profile


class ProfileEditorLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_shared_visibility_order_sync_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.db'
            b = Backend(path)
            with b.db.connect() as conn:
                for sid, name in [('001', '张三'), ('002', '李四')]:
                    conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid,name,'2026-09-27'))
                    insert_profile(conn,sid,name,1)
            p, c = b.profilesModule, b.profileCompanion
            p.refresh()
            c._active_wecom_title = lambda: 'py169张三'
            c.refreshContact()
            self.assertEqual(c.student['student_id'],'001')
            self.assertEqual(c.fields,p.fields)
            p.setFieldVisible('column:profile:QQ',False)
            p.setFieldVisible('default_2',False)
            self.assertNotIn('QQ',[f['label'] for f in p.fields])
            self.assertNotIn('画像情况',[f['label'] for f in c.fields])
            p.moveField('column:profile:学习目的',0)
            self.assertEqual(p.fields[0]['label'],'学习目的')
            self.assertEqual(c.fields,p.fields)
            key = c.student['_record_key']
            self.assertTrue(c.saveEditorField(key,'所在地区','上海'))
            self.assertEqual(p.selected['profile_fields']['所在地区'],'上海')
            self.assertTrue(p.saveEditorField(p.selected['_record_key'],'所在地区','北京'))
            self.assertEqual(c.student['profile_fields']['所在地区'],'北京')
            c._active_wecom_title = lambda: '李四'
            c.refreshContact()
            self.assertEqual(c.student['student_id'],'002')
            self.assertFalse(c.saveEditorField(key,'所在地区','误写'))
            self.assertEqual(b.repo.get('001')['profile_fields']['所在地区'],'北京')
            reopened = Backend(path)
            self.assertEqual(reopened.profilesModule.fields[0]['label'],'学习目的')
            self.assertNotIn('QQ',[f['label'] for f in reopened.profilesModule.fields])

    def test_float_coalesces_typing_and_flushes_before_contact_change(self):
        with tempfile.TemporaryDirectory() as folder:
            b = Backend(Path(folder) / 'test.db')
            with b.db.connect() as conn:
                for sid, name in [('001', '测试甲'), ('002', '测试乙')]:
                    conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-09-29'))
                    insert_profile(conn, sid, name, int(sid))
            c = b.profileCompanion
            c._active_wecom_title = lambda: '测试甲'
            c.refreshContact()
            first_key = c.student['_record_key']
            self.assertTrue(c.queueEditorField(first_key, '所在地区', '上'))
            self.assertTrue(c.queueEditorField(first_key, '所在地区', '上海'))
            self.assertEqual(b.repo.get('001')['profile_fields']['所在地区'], '')
            c._active_wecom_title = lambda: '测试乙'
            c.refreshContact()
            self.assertEqual(b.repo.get('001')['profile_fields']['所在地区'], '上海')
            self.assertEqual(c.student['student_id'], '002')
            self.assertFalse(c.queueEditorField(first_key, '所在地区', '误写'))
            second_key = c.student['_record_key']
            self.assertTrue(c.queueEditorField(second_key, '所在地区', '北京'))
            c.close()
            self.assertEqual(b.repo.get('002')['profile_fields']['所在地区'], '北京')
            c._active_wecom_title = lambda: '测试甲'
            c.refreshContact()
            self.assertTrue(c.queueEditorField(first_key, '所在地区', '深圳'))
            other = Database(Path(folder) / 'other.db')
            with other.connect() as conn:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', ('001', '测试甲', '2026-09-29'))
                insert_profile(conn, '001', '测试甲', 1)
            b.workflow._classes.append({'name': '第二班', 'path': str(other.path)})
            b.workflow.selectClass(1)
            self.assertEqual(StudentRepository(Database(Path(folder) / 'test.db')).get('001')['profile_fields']['所在地区'], '深圳')
            self.assertEqual(c.student['_record_key'], first_key)


if __name__ == '__main__':
    unittest.main()
