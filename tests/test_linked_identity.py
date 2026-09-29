import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.profile_fields import PROFILE_INPUT_LABELS
from app.profile_fields import BASE_PROFILE_LABELS
from app.campaigns import EXPORT_COLUMNS


class LinkedIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_current_identity_updates_history_frozen_and_profile_minimal(self):
        with tempfile.TemporaryDirectory() as directory:
            b=Backend(Path(directory)/'test.db')
            term=dict(termId=551,termNo='P2026169',termName='编程169期',termAlias='PY169期')
            t=b.termsModule
            t._accept('terms',[term])
            t._request_term=term
            t._accept('lessons',[dict(resource_id='first',label='01【Python】')])
            t._resource='first'
            students=[dict(student_id=f'P2026169{i:03d}A',name=f'学员{i}',status='在读',student_type='新生',nickname='') for i in (1,3)]
            t._accept('students',students)
            sid=students[0]['student_id']
            b.repo.set_setting('snapshot',json.dumps([dict(student_id=s['student_id'],flags={'c1':'T','z1':'F'}) for s in students]))
            b.repo.update_profile_field(sid,'微信','否')
            w=b.workflow
            w.createBatch()
            historical=w._batch
            w.createBatch()
            current=w._batch
            w.simulate(False)
            w.selectRow(0)
            w.saveDraft(sid,'当前草稿')
            with b.db.connect() as conn:
                old=[tuple(r) for r in conn.execute('SELECT * FROM campaign_students WHERE batch_id=? ORDER BY student_id',(historical,))]
            before=w.store.rows(current,sid)[0]
            students[0].update(name='新姓名',status='冻结')
            t._accept('students',students)
            b.profilesModule.selectRow(0)
            self.assertTrue(b.profilesModule.autoSaveField(sid,'微信','是'))
            after=w.store.rows(current,sid)[0]
            self.assertEqual((after['name'],after['roster_status'],after['wechat']),('新姓名','冻结','是'))
            for key in ('courses','homework','completed_total','missing_total','feedback','draft','message','send_state','sent_at'):
                self.assertEqual(after[key],before[key],key)
            with b.db.connect() as conn:
                self.assertEqual(old,[tuple(r) for r in conn.execute('SELECT * FROM campaign_students WHERE batch_id=? ORDER BY student_id',(historical,))])
                self.assertEqual(set(json.loads(conn.execute('SELECT fields FROM profiles WHERE student_id=?',(sid,)).fetchone()[0])),set(BASE_PROFILE_LABELS))
                self.assertTrue(list(conn.execute('PRAGMA foreign_key_list(profiles)')))
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute("INSERT INTO profiles VALUES('missing','{}')")
            self.assertEqual(b.profilesModule.columnLabels,['班期','学号','姓名','状态',*BASE_PROFILE_LABELS,'免催日期',*PROFILE_INPUT_LABELS[6:]])
            w.filterRows('targets','')
            self.assertNotIn(sid,[r['student_id'] for r in w.tableModel.rows])
            gap=b.repo.get('P2026169002A')
            self.assertEqual(gap['roster_status'],'已退课')
            self.assertEqual(t.store.load(551)['rows'][1]['status'],'已退课')
            w.createBatch()
            self.assertEqual(w.store.rows(w._batch,sid)[0]['wechat'],'是')
            self.assertEqual(w.store.rows(current,sid)[0]['wechat'],'是')
            b.repo.update_profile_field(sid,'微信','否')
            self.assertEqual(w.store.rows(w._batch,sid)[0]['wechat'],'否')
            self.assertEqual(w.store.rows(current,sid)[0]['wechat'],'是')
            self.assertEqual([x[0] for x in EXPORT_COLUMNS][-3:],['roster_status','wechat','exemption_text'])
            self.assertEqual(EXPORT_COLUMNS[0],('student_id','学号'))
            self.assertEqual(list(Path(directory).glob('*.before-*.db')),[])


if __name__=='__main__': unittest.main()
