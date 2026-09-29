import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.database import Database
from app.importer import import_csv
from app.repository import StudentRepository
from app.roster_sync import INPUT_LABELS
from app.profile_fields import BASE_PROFILE_LABELS
from tests.profile_fixtures import legacy_profiles

TERM=dict(termId=551,termNo='P2026169',termName='编程169期',termAlias='PY169期')
OTHER=dict(termId=564,termNo='P2026175',termName='编程175期',termAlias='PY175期')


def sid(i): return f'P2026169{i:03d}A'


class SeparatedModulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_auto_roster_profiles_and_snapshots(self):
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(Path(folder)/'root.db')
            t=b.termsModule
            t._accept('terms',[TERM,OTHER])
            self.assertEqual(len(b.workflow.classes),2)
            self.assertEqual(b.workflow.className,'编程169期')
            t._request_term=TERM
            t._accept('lessons',[dict(resource_id='first',label='01【Python】')])
            t._resource='first'
            real=[dict(student_id=sid(i),name=f'学员{i}',status='在读',student_type='新生',nickname='') for i in (1,2,4,5)]
            t._accept('students',real)
            self.assertEqual(b.profilesModule.total,5)
            self.assertEqual(len(b.profilesModule.fields),10)
            b.repo.update_profile_field(sid(2),'学习目的','转行')
            b.repo.add_feedback(sid(2),'原有反馈不能丢')
            source=Path(folder)/'data.csv'
            columns=['学号','姓名']+[f'{p}{i}' for p in ('c','z') for i in range(1,33)]
            def write_data(completed=False):
                with source.open('w',encoding='utf-8-sig',newline='') as stream:
                    writer=csv.DictWriter(stream,fieldnames=columns)
                    writer.writeheader()
                    for i,c,z in ((1,0,0),(2,1,4),(4,3,1),(5,2,4)):
                        row={k:'N' for k in columns}
                        row.update(学号=sid(i),姓名=f'学员{i}')
                        for n in range(1,5):
                            row[f'c{n}']='F' if n<=c and not completed else 'T'
                            row[f'z{n}']='F' if n<=z and not completed else 'T'
                        writer.writerow(row)
            write_data()
            with b.db.connect() as conn:
                before=[tuple(r) for r in conn.execute('SELECT * FROM profiles ORDER BY student_id')]
            import_csv(b.db,source)
            with b.db.connect() as conn:
                self.assertEqual(before,[tuple(r) for r in conn.execute('SELECT * FROM profiles ORDER BY student_id')])
                self.assertEqual(conn.execute('SELECT count(*) FROM class_roster WHERE active=1').fetchone()[0],5)
                self.assertEqual(conn.execute('SELECT count(*) FROM reminder_data WHERE matched=1').fetchone()[0],4)
                self.assertEqual(conn.execute('SELECT count(*) FROM profiles').fetchone()[0],5)
                self.assertNotIn('合计完课',json.loads(conn.execute('SELECT fields FROM profiles LIMIT 1').fetchone()[0]))
            w=b.workflow
            for student in b.repo.list_students():
                b.repo.update_profile_field(student['student_id'],'微信','是')
            w.refresh_live()
            self.assertEqual([r['student_id'] for r in w.tableModel.rows],[sid(i) for i in range(1,6)])
            w.createBatch()
            batch=w._batch
            self.assertEqual([r['student_id'] for r in w.tableModel.rows],[sid(i) for i in range(1,6)])
            blank=w.tableModel.rows[2]
            self.assertEqual(blank['name'],'')
            self.assertEqual(blank['missing_total'],'')
            self.assertFalse(blank['eligible'])
            w.filterRows('targets','')
            self.assertEqual([r['student_id'] for r in w.tableModel.rows],[sid(5),sid(2),sid(4)])
            self.assertEqual(w.sortColumnIndex,4)
            self.assertTrue(w.sortDescending)
            w.filterRows('all','')
            self.assertEqual(w.sortColumnIndex,0)
            self.assertFalse(w.sortDescending)
            write_data(True)
            import_csv(b.db,source)
            w.refresh_live()
            # The newest batch follows the new import instead of keeping the creation snapshot.
            self.assertEqual(w.store.rows(batch,sid(2))[0]['missing_total'],'0/0')
            w.createBatch()
            w.filterRows('targets','')
            self.assertEqual(w.visibleCount,0)
            # Fetching the same roster doesn't overwrite manual profile data.
            t._accept('students',real)
            self.assertEqual(b.repo.get(sid(2))['profile_fields']['学习目的'],'转行')
            self.assertIn('原有反馈不能丢',b.repo.get(sid(2))['feedback_history'])
            with patch.object(t,'_start') as start:
                t.selectTerm(1)
                start.assert_called_once_with('lessons')
            self.assertEqual(w.className,'编程175期')
            self.assertEqual(b.profilesModule.total,0)
            w.selectClass(0)
            self.assertEqual(t.termIndex,0)
            reopened=Backend(Path(folder)/'root.db')
            self.assertEqual(reopened.profilesModule.total,5)
            self.assertEqual(reopened.repo.get(sid(2))['profile_fields']['学习目的'],'转行')

    def test_migration_preserves_allowed_fields_without_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'legacy.db'
            db=Database(path)
            with db.connect() as conn:
                legacy_profiles(conn)
                conn.execute("DELETE FROM settings WHERE key='separate_learning_v1'")
                conn.execute('INSERT INTO students(student_id,name,pending_count,updated_at) VALUES(?,?,?,?)',(sid(1),'甲',3,'2026-09-24'))
                fields={'合计完课':2,'差的课程':'3','合计作业':1,'差的作业':'2,3','学习目的':'转行'}
                conn.execute('INSERT INTO profiles(student_id,name,position,fields) VALUES(?,?,?,?)',(sid(1),'甲',1,json.dumps(fields)))
                conn.execute('INSERT INTO learning_feedback(student_id,created_at,content) VALUES(?,?,?)',(sid(1),'2026-09-24','已沟通'))
            migrated=Database(path)
            repo=StudentRepository(migrated)
            self.assertFalse(path.with_suffix('.before-separated-tables.db').exists())
            self.assertEqual(repo.get(sid(1))['profile_fields']['合计完课'],2)
            self.assertIn('已沟通',repo.get(sid(1))['feedback_history'])
            with migrated.connect() as conn:
                raw=json.loads(conn.execute('SELECT fields FROM profiles').fetchone()[0])
                self.assertEqual(raw['学习目的'],'转行')
                self.assertEqual(set(raw),set(BASE_PROFILE_LABELS))
                self.assertEqual(conn.execute('SELECT count(*) FROM reminder_data').fetchone()[0],1)


if __name__=='__main__': unittest.main()
