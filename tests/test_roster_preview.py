import json
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from tests.profile_fixtures import insert_profile


class RosterPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_existing_roster_without_batch_and_live_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.db'
            b=Backend(path)
            with b.db.connect() as conn:
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','测试','2026-09-24')")
                insert_profile(conn,'001','测试',1,{'合计完课':2,'差的课程':'3','合计作业':1,'差的作业':'2、3'})
            b=Backend(path)
            w=b.workflow
            self.assertEqual(w.visibleCount,1)
            self.assertEqual(w.tableModel.rows[0]['missing_total'],'')
            self.assertEqual(w.tableModel.rows[0]['completed_total'],'')
            self.assertFalse(w.canEdit)
            self.assertEqual(w.store.batches(),[])
            w.filterRows('pending','测试')
            self.assertEqual(w.visibleCount,1)
            w.filterRows('all','不存在')
            self.assertEqual(w.visibleCount,0)
            w.filterRows('all','')
            b.repo.set_setting('snapshot',json.dumps([{'student_id':'001','flags':{'c1':'T','z1':'F'}}]))
            w.refresh_live()
            self.assertEqual(w.tableModel.rows[0]['completed_total'],'1/0')
            w.createBatch()
            batch=w._batch
            b.repo.set_setting('snapshot',json.dumps([{'student_id':'001','flags':{'c1':'T','c2':'T','z1':'T'}}]))
            w.refresh_live()
            # The newest batch follows later learning data.
            self.assertEqual(w.tableModel.rows[0]['completed_total'],'2/1')
            self.assertEqual(w._batch,batch)
            w.createBatch()
            newest=w._batch
            self.assertNotEqual(newest,batch)
            b.repo.set_setting('snapshot',json.dumps([{'student_id':'001','flags':{'c1':'F','z1':'F'}}]))
            w.refresh_live()
            self.assertEqual(w.store.rows(newest)[0]['missing_total'],'1/1')
            self.assertEqual(w.store.rows(batch)[0]['completed_total'],'2/1')
