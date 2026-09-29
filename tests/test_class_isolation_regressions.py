import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from openpyxl import load_workbook

from app.backend import Backend
from app.database import Database
from app.repository import StudentRepository
from app.campaigns import CampaignStore
from app.profile_storage import definitions, set_exemption
from app.roster_sync import sync_roster
from tests.profile_fixtures import insert_profile
from tests.test_business_logic import seeded, merged_row, TERM
from app.importer import import_rows


def add_student(db, sid='001', name='张三'):
    with db.connect() as conn:
        conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid,name,'2026-09-27'))
        insert_profile(conn,sid,name,1,{'微信':'是'})


class ClassIsolationRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_fields_visibility_values_and_delete_stay_in_class(self):
        with tempfile.TemporaryDirectory() as folder:
            b = Backend(Path(folder)/'first.db')
            other = Database(Path(folder)/'second.db')
            add_student(b.db)
            add_student(other)
            b.workflow._classes.append(dict(name='第二班',path=str(other.path)))
            b.workflow.registry.set_setting('workflow_classes',json.dumps(b.workflow._classes))
            p = b.profilesModule
            p.refresh()
            first_key = p.selected['_record_key']
            self.assertTrue(p.addField('本班计划','text','',True))
            p.setFieldVisible('column:profile:QQ',False)
            p.moveField('column:profile:学习目的',0)
            self.assertTrue(p.saveEditorField(first_key,'本班计划','甲班内容'))
            p.autoSaveField('001','画像情况','甲班保留')
            set_exemption(b.db,'001','2099-01-01')
            b.workflow.selectClass(1)
            self.assertNotIn('本班计划',[r['name'] for r in p.extraFields])
            self.assertIn('QQ',p.columnLabels)
            self.assertNotEqual(p.managedFields[0]['name'],'学习目的')
            self.assertEqual(b.repo.get('001')['exemption_date'],'')
            self.assertFalse(p.saveEditorField(first_key,'所在地区','错误班期'))
            self.assertTrue(p.addField('本班计划','choice','乙选项',True))
            self.assertTrue(p.autoSaveField('001','本班计划','乙选项'))
            self.assertTrue(p.deleteField('default_2'))
            b.workflow.selectClass(0)
            self.assertEqual(p.fields[0]['label'],'学习目的')
            self.assertNotIn('QQ',p.columnLabels)
            self.assertEqual(p.selected['profile_fields']['画像情况'],'甲班保留')
            self.assertEqual(p.selected['profile_fields']['本班计划'],'甲班内容')
            first_field=next(r['field_id'] for r in p.extraFields if r['name']=='本班计划')
            self.assertTrue(p.deleteField(first_field))
            self.assertEqual(StudentRepository(other).get('001')['profile_fields']['本班计划'],'乙选项')
            p.setAllClasses(True)
            self.assertFalse(p.addField('总览不允许添加','text','',True))
            self.assertFalse(p.deleteField('default_0'))
            self.assertEqual(p.total,2)
            reopened=Backend(Path(folder)/'first.db')
            reopened.workflow.selectClass(1)
            self.assertIn('QQ',reopened.profilesModule.columnLabels)
            self.assertNotIn('画像情况',[r['name'] for r in definitions(reopened.db)])

    def test_float_retries_failures_and_refreshes_same_contact(self):
        with tempfile.TemporaryDirectory() as folder:
            b=Backend(Path(folder)/'first.db')
            c=b.profileCompanion
            c._active_wecom_title=lambda:'py169张三'
            c.refreshContact()
            self.assertFalse(c.student)
            # Same caption after roster arrival must be retried, even without a UI refresh.
            add_student(b.db)
            c.setEditing(True)  # Simulate a delayed/stale Qt focus notification.
            c.refreshContact()
            self.assertEqual(c.student['student_id'],'001')
            b.repo.update_profile_field('001','所在地区','上海')
            c._last_checked=0
            c.refreshContact()
            self.assertEqual(c.student['profile_fields']['所在地区'],'上海')
            b.repo.update_profile_field('001','所在地区','北京')
            c._active_wecom_title=lambda:''  # Clicking retry activates our own window.
            c.retryContact()
            self.assertEqual(c.student['profile_fields']['所在地区'],'北京')
            previous=c.student['_record_key']
            other=Database(Path(folder)/'second.db')
            add_student(other,name='李四')
            b.workflow._classes.append(dict(name='第二班',path=str(other.path)))
            b.workflow.selectClass(1)
            self.assertFalse(c.student)
            self.assertFalse(c.saveEditorField(previous,'所在地区','误写'))
            c._active_wecom_title=lambda:'李四'
            c.refreshContact()
            self.assertEqual(c.student['name'],'李四')
            c._active_wecom_title=lambda:'企业微信'
            c.refreshContact()
            self.assertFalse(c.student)

    def test_profile_float_does_not_match_prefix_of_another_name(self):
        with tempfile.TemporaryDirectory() as folder:
            b = Backend(Path(folder) / 'first.db')
            add_student(b.db, '001', '测试甲')
            c = b.profileCompanion
            c._active_wecom_title = lambda: '测试甲乙'
            c.refreshContact()
            self.assertFalse(c.student)
            add_student(b.db, '002', '测试甲乙')
            c.refreshContact()
            self.assertEqual(c.student['student_id'], '002')
            c._active_wecom_title = lambda: 'py169测试甲（备注）'
            c.refreshContact()
            self.assertEqual(c.student['student_id'], '001')
            c._active_wecom_title = lambda: '其他测试甲'
            c.refreshContact()
            self.assertFalse(c.student)
            self.assertFalse(c.saveEditorField(str(b.db.path) + '|001', '所在地区', '误写'))

    def test_feedback_date_headers_content_only_and_custom_export(self):
        with seeded(2) as b, tempfile.TemporaryDirectory() as folder:
            import_rows(b.db,[merged_row(i,f'学员{i}') for i in (1,2)])
            w=b.workflow
            w.createBatch()
            first=w._batch
            with b.db.connect() as conn:
                conn.execute("UPDATE campaigns SET created_at='2026-09-25T18:00:00' WHERE id=?",(first,))
            w.reload_batches()
            w.simulate(False)
            self.assertTrue(w.submit('军训太忙，国庆补'))
            self.assertEqual(w.store.rows(first,'P2026169001A')[0]['feedback'],'军训太忙，国庆补')
            self.assertEqual(dict(w.tableModel.columns)['feedback'],'本次反馈情况（9月25号）')
            with b.db.connect() as conn:
                self.assertNotIn('created_at',[r[1] for r in conn.execute('PRAGMA table_info(campaign_feedback)')])
            w.createBatch()
            w.selectBatch(1)
            w.filterRows('targets','不存在的姓名')
            target=Path(folder)/'selected.xlsx'
            self.assertEqual(w.export_to_path(['name','feedback'],target),2)
            book=load_workbook(target)
            self.assertEqual(list(book.active.values),[
                ('姓名','本次反馈情况（9月25号）'),('学员1','军训太忙，国庆补'),('学员2',None)])
            book.close()
            with self.assertRaises(ValueError):w.export_to_path([],target)
            with self.assertRaises(ValueError):w.export_to_path(['unknown'],target)
            self.assertIn('军训太忙',b.profilesModule.history)

    def test_feedback_timestamp_migration_preserves_content_and_identity(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            b.workflow.createBatch()
            b.workflow.simulate(False)
            b.workflow.submit('保留此内容')
            with b.db.connect() as conn:
                conn.execute("ALTER TABLE campaign_feedback ADD COLUMN created_at TEXT NOT NULL DEFAULT '2026-09-25T20:30:00'")
                before=tuple(conn.execute('SELECT id,batch_id,student_id,content,kind FROM campaign_feedback').fetchone())
            migrated=CampaignStore(b.db,b.repo)
            with b.db.connect() as conn:
                self.assertEqual(tuple(conn.execute('SELECT id,batch_id,student_id,content,kind FROM campaign_feedback').fetchone()),before)
                self.assertNotIn('created_at',[r[1] for r in conn.execute('PRAGMA table_info(campaign_feedback)')])
                self.assertFalse(conn.execute('PRAGMA foreign_key_check').fetchall())
            self.assertEqual(migrated.rows(b.workflow._batch)[0]['feedback'],'保留此内容')

    def test_wrong_class_roster_rejected_without_touching_data(self):
        with seeded(1) as b:
            b.repo.set_setting('term_id','551')
            before=b.repo.list_students()
            with self.assertRaises(ValueError):
                sync_roster(b.db,dict(TERM,termId=999),[])
            with self.assertRaises(ValueError):
                sync_roster(b.db,TERM,[dict(student_id='P2026175001A',name='另一班')])
            self.assertEqual(b.repo.list_students(),before)


if __name__ == '__main__':unittest.main()
