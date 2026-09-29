import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.database import Database
from app.repository import StudentRepository
from app.profile_module import PROFILE_INPUT_LABELS
from app.profile_fields import DISPLAY_LABELS
from tests.profile_fixtures import insert_profile


class ProfileModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_full_roster_independent_and_cross_class_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            backend=Backend(Path(folder)/'root.db')
            second=Database(Path(folder)/'other.db')
            for db,name in [(backend.db,'甲'),(second,'乙')]:
                with db.connect() as conn:
                    conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',('001',name,'2026-09-24'))
                    fields={next((k for k,v in DISPLAY_LABELS.items() if v==label),label):None for label in PROFILE_INPUT_LABELS}
                    fields.update({'学员状态':'退课','画像情况':'旧计划','合计完课':3})
                    insert_profile(conn,'001',name,1,fields)
            p=backend.profilesModule
            p.refresh()
            self.assertEqual(p.total,1)
            self.assertEqual([f['displayLabel'] for f in p.fields],list(PROFILE_INPUT_LABELS[:6])+['免催日期']+list(PROFILE_INPUT_LABELS[6:]))
            self.assertEqual(p.fields[0]['options'],['','是','否'])
            self.assertNotIn('学员状态',p.selected['profile_fields'])
            self.assertEqual(p.selected['profile_fields']['合计完课'],3)
            self.assertEqual(backend.workflow.batches,[])
            self.assertEqual(p.lessons[0]['course'],'未获取')
            self.assertTrue(p.autoSaveField('001','画像情况','新计划'))
            self.assertEqual(backend.repo.get('001')['profile_fields']['画像情况'],'新计划')
            backend.workflow._classes.append({'name':'第二班','path':str(second.path)})
            p.setAllClasses(True)
            self.assertEqual(p.total,2)
            self.assertEqual(len({r['_record_key'] for r in p.tableModel.rows}),2)
            self.assertFalse(p.autoSaveField('001','画像情况','不应写入'))
            self.assertEqual(StudentRepository(second).get('001')['profile_fields']['画像情况'],'旧计划')
            p.search('乙')
            self.assertEqual(p.visibleCount,1)
            self.assertEqual(p.selected['class_name'],'第二班')
            self.assertTrue(all(not r['editable'] for r in p.fields))
            p.search('')
            p.setAllClasses(False)
            backend.repo.add_feedback('001','迁移前记录')
            p.refresh()
            self.assertIn('迁移前记录',p.history)
            self.assertEqual(p.total,1)
