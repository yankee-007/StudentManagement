import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
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
            c.setLocked(True)
            c._active_wecom_title = lambda: '李四'
            c.refreshContact()
            self.assertEqual(c.student['student_id'],'001')
            c.setLocked(False)
            c.refreshContact()
            self.assertEqual(c.student['student_id'],'002')
            self.assertFalse(c.saveEditorField(key,'所在地区','误写'))
            self.assertEqual(b.repo.get('001')['profile_fields']['所在地区'],'北京')
            reopened = Backend(path)
            self.assertEqual(reopened.profilesModule.fields[0]['label'],'学习目的')
            self.assertNotIn('QQ',[f['label'] for f in reopened.profilesModule.fields])


if __name__ == '__main__':
    unittest.main()
