"""Real acquisition/campaign integration on disposable synthetic class databases."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.backend import Backend
from app.daily_workspace import goal_summary, recommendation
from app.database import Database
from app.followup_store import FollowupStore
from app.profile_storage import set_exemption
from app.roster_sync import sync_roster
from app.term_roster import arrange_students
from tests.test_latest_batch_refresh import TERM, sid, row


class DailyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.b = Backend(Path(self.folder.name)/'daily.db')
        students = [dict(student_id=sid(i),name=f'虚构学员{i}',status='在读') for i in (1,2,3)]
        sync_roster(self.b.db, TERM, arrange_students(TERM['termNo'],students))
        for student in students: self.b.repo.update_profile_field(student['student_id'],'微信','是')
        self.b.refresh()
        self.fetch(self.learning(), True)
        self.d = self.b.dailyWorkspace
        self.assertTrue(self.goal())

    def learning(self):
        return [row(1,'虚构学员1',{'C1':'T','C2':'T','Z1':'F','Z2':'F'}),
                row(2,'虚构学员2',{'C1':'T','C2':'T','Z1':'T','Z2':'F'}),
                row(3,'虚构学员3',{'C1':'F','C2':'T','Z1':'T','Z2':'T'})]

    def fetch(self, rows, create=False):
        self.b._fetch_db_path = str(self.b.db.path)
        self.b._class_name='虚构测试班'; self.b._create_after_fetch=create; self.b._busy=True
        self.b._fetch_succeeded((rows, {'双方在读并导出':len(rows)}))

    def goal(self, lesson=2):
        d=self.b.dailyWorkspace
        return d.saveGoal(dict(context=d.goalContext,lesson=lesson,course=90,homework=85,gap=5,deadline='2099-12-31'))

    def commit(self, n=1, selected=None):
        detail=self.d.detailsFor(sid(n))
        due=(datetime.now()+timedelta(days=1)).isoformat(timespec='seconds')
        self.assertTrue(self.d.saveCommitment(detail['key'],dict(items=selected or detail['selectedItems'],due_at=due,review_at='',note='答应补齐')), self.d.summary)
        # Advance only the synthetic commitment baseline to avoid sleeping for importer seconds.
        with self.b.db.connect() as conn: conn.execute("UPDATE daily_tasks SET updated_at='2000-01-01T00:00:00' WHERE student_id=?",(sid(n),))
        self.d.reload()
        return self.d.detailsFor(sid(n))['task']

    def test_goal_persistence_fixed_range_archive_and_read_only(self):
        reopened=Backend(self.b.db.path)
        self.assertEqual(reopened.dailyWorkspace.goal['lesson'],2)
        before=self.d.goal['id']
        task=self.commit()
        self.assertTrue(self.goal(1))
        self.assertNotEqual(self.d.goal['id'],before)
        self.assertEqual(self.d.detailsFor(sid(1))['task']['id'],task['id'])
        with self.b.db.connect() as conn:
            before_tables=list(conn.execute('SELECT snapshot FROM campaign_students'))
        self.d.reload()
        with self.b.db.connect() as conn: self.assertEqual([r[0] for r in conn.execute('SELECT snapshot FROM campaign_students')],[r[0] for r in before_tables])
        self.assertTrue(Path(str(self.b.db.path)+'.before-daily-workspace.bak').exists())

    def test_summary_joint_targets_and_20_30_example(self):
        goal=dict(lesson=2,course=90,homework=85,gap=5,deadline='2099-12-31',members=[])
        batch=dict(total=200,population=[],time='test',lessons=[dict(lesson=2,course=90,homework=75,gap=15,courseDone=180,homeworkDone=150)])
        summary=goal_summary(goal,batch)
        self.assertEqual(summary['needs'],dict(course=0,homework=20,gap=20))
        batch['lessons'][0].update(course=95,gap=20,courseDone=190)
        self.assertEqual(goal_summary(goal,batch)['needs']['gap'],30)
        batch['lessons'][0].update(course=45,homework=43,gap=2,courseDone=90,homeworkDone=86)
        self.assertFalse(goal_summary(goal,batch)['met'])

    def test_smallest_improvement_first_gap_tie_and_population_change(self):
        self.assertEqual(self.d.tableModel.rows[0]['student_id'],sid(2))
        proposal,_=recommendation(dict(c=['c1'],z=['z1']),dict(valid=True,met=False,needs=dict(course=1,homework=1,gap=1),total=200))
        self.assertEqual(proposal['items'],['z1'])
        with self.b.db.connect() as conn:
            conn.execute('UPDATE campaigns SET created_at=?',(datetime.now().isoformat(),))
            conn.execute("DELETE FROM campaign_students WHERE student_id=?",(sid(3),))
            data=json.loads(conn.execute('SELECT data FROM campaign_dashboards').fetchone()[0]);data['total']=2
            for r in data['courses']:r.update(completed=2,completedRate='100.00%')
            for r in data['homework']:r.update(completed=0,completedRate='0.00%')
            conn.execute('UPDATE campaign_dashboards SET data=?',(json.dumps(data),))
        self.d._notice='刷新完成'
        self.d.reload(False)
        self.assertEqual(self.d.summary['removed'],1)
        self.assertIn('刷新完成',self.d.summary['notice'])
        self.assertIn('移出1人',self.d.summary['notice'])

    def test_partial_unknown_missing_old_then_complete(self):
        task=self.commit()
        self.d.store.verify({sid(1):dict(time='1999-01-01T00:00:00',flags={'z1':'T','z2':'T'})})
        self.assertEqual(self.d.store.tasks()[0]['result'],'待核验')
        values=self.learning();values[0]['Z1']='T'
        self.fetch(values)
        self.assertEqual(self.d.detailsFor(sid(1))['task']['result'],'部分完成')
        self.assertEqual(self.d.summary['metrics'][1]['value'],'33.3%')
        # Importer keeps known data for absent students; verifier must not reuse it.
        self.fetch(values[1:])
        self.assertEqual(self.d.detailsFor(sid(1))['task']['result'],'部分完成')
        values[0]['Z2']='U';self.fetch(values)
        self.assertEqual(self.d.detailsFor(sid(1))['task']['result'],'待核验')
        values[0]['Z2']='T';self.fetch(values)
        ended=next(t for t in self.d.store.tasks() if t['id']==task['id'])
        self.assertEqual((ended['result'],ended['lifecycle']),('已完成','completed'))
        self.assertTrue(any(e['kind']=='平台核验' for e in self.d.store.events(sid(1))))

    def test_selected_subset_completes_without_cumulative_credit(self):
        task=self.commit(selected=['z1'])
        values=self.learning();values[0]['Z1']='T';self.fetch(values)
        self.assertEqual(next(t for t in self.d.store.tasks() if t['id']==task['id'])['lifecycle'],'completed')
        self.assertEqual(self.d.summary['metrics'][1]['value'],'33.3%')

    def test_one_of_five_homework_items_is_partial_without_cumulative_credit(self):
        values=self.learning()
        for value in values:
            for number in range(3,6):
                value[f'C{number}']='T'
                value[f'Z{number}']='T'
        for number in range(1,6): values[0][f'Z{number}']='F'
        self.fetch(values,True)
        self.assertTrue(self.goal(5))
        task=self.commit()
        self.assertEqual(task['items'],['z1','z2','z3','z4','z5'])
        before=self.d.summary['metrics'][1]['value']
        values[0]['Z1']='T'
        self.fetch(values)
        current=self.d.detailsFor(sid(1))['task']
        self.assertEqual(current['result'],'部分完成')
        self.assertEqual(current['lifecycle'],'active')
        self.assertEqual(current['evidence']['completed'],['z1'])
        self.assertEqual(self.d.summary['metrics'][1]['value'],before)

    def test_new_batch_keeps_commitment_and_historical_learning(self):
        task=self.commit()
        with self.b.db.connect() as conn: before=[r[0] for r in conn.execute('SELECT snapshot FROM campaign_students WHERE batch_id=1 ORDER BY student_id')]
        self.fetch(self.learning(),True)
        self.assertEqual(self.d.detailsFor(sid(1))['task']['id'],task['id'])
        self.assertEqual(self.d.goal['lesson'],2)
        with self.b.db.connect() as conn: self.assertEqual([r[0] for r in conn.execute('SELECT snapshot FROM campaign_students WHERE batch_id=1 ORDER BY student_id')],before)

    def test_edit_failure_revision_class_isolation_and_contact_note(self):
        detail=self.d.detailsFor(sid(1))
        self.d.queueDraft(detail['key'],dict(items=['z1'],due_at='invalid',note='保留输入'))
        self.assertFalse(self.d.flushEditor())
        self.assertTrue(self.d.hasDraft(detail['key']))
        self.assertTrue(self.d.saveContactNote(detail['key'],'未接听电话'))
        self.assertFalse(self.d.hasDraft(detail['key']))
        self.assertEqual(self.d.store.tasks(),[])
        self.commit()
        self.assertFalse(self.d.saveCommitment(detail['key'],dict(items=['z1'],due_at='2099-12-31 20:00')))
        other=Database(Path(self.folder.name)/'other.db')
        self.assertEqual(FollowupStore(other).goal(),{})
        self.assertEqual(FollowupStore(other).tasks(),[])
        with other.connect() as conn: self.assertFalse(conn.execute("SELECT 1 FROM sqlite_master WHERE name='daily_goals'").fetchone())

    def test_list_exclusions_content_stale_context_and_sending_protection(self):
        set_exemption(self.b.db,sid(1),'2099-12-31')
        self.d.reload(False);self.d.checkAll(True)
        preview=self.d.listPreview()
        self.assertIn(sid(1),[r['student_id'] for r in preview['excluded']])
        fields=[dict(type='text',text='{姓名}：{承诺项目}，{期限}')]
        self.assertTrue(self.b.groupCenter.createFromDailySelection('虚构名单',fields,preview['keys']))
        people=self.b.groupCenter.store.rows(self.b.groupCenter._id)
        self.assertTrue(all('虚构学员1' != p['name'] and '第' in p['message'] for p in people))
        self.assertTrue(all(p['state']=='待发送' for p in people))
        self.assertEqual(self.d.store.tasks(),[])
        self.commit(2)
        self.assertFalse(self.b.groupCenter.createFromDailySelection('过期名单',fields,preview['keys']))

    def test_review_due_and_cancel_reason(self):
        task=self.commit()
        with self.b.db.connect() as conn: conn.execute("UPDATE daily_tasks SET due_at='2000-01-01T20:00:00',review_at='2000-01-01T20:00:00'")
        self.d.reload();self.d.selectTab(1)
        self.assertEqual(self.d.summary['reviewCount'],1)
        detail=self.d.detailsFor(sid(1))
        self.assertFalse(self.d.cancelTask(detail['key'],''))
        self.assertTrue(self.d.cancelTask(detail['key'],'重新安排'))
        self.assertEqual(self.d.store.tasks()[0]['lifecycle'],'cancelled')

    def test_same_student_two_editors_preserve_conflicting_input(self):
        key=self.d.detailsFor(sid(1))['key']
        first=dict(items=['z1'],due_at='2099-12-31 20:00',note='主界面输入')
        second=dict(items=['z2'],due_at='2099-12-30 20:00',note='浮窗输入')
        self.d.queueDraft(key,first,'main')
        self.d.queueDraft(key,second,'float')
        self.assertFalse(self.d.flushEditor())
        self.assertEqual(self.d.detailsFor(sid(1))['task']['note'],'主界面输入')
        self.assertTrue(self.d.hasDraft(key,'float'))
        self.assertEqual(self.d._drafts['float']['values']['note'],'浮窗输入')
        self.d.discardDraft(key,'float')
        self.assertTrue(self.d.flushEditor())

    def test_fetch_started_before_commitment_change_cannot_verify(self):
        task=self.commit(selected=['z1'])
        stamp=datetime.now().isoformat(timespec='microseconds')
        self.d.store.verify({sid(1):dict(time=stamp,started_at='1999-01-01T00:00:00',flags={'z1':'T'})})
        self.assertEqual(self.d.store.tasks()[0]['lifecycle'],'active')
        self.d.store.verify({sid(1):dict(time=stamp,started_at=stamp,flags={'z1':'T'})})
        self.assertEqual(self.d.store.tasks()[0]['lifecycle'],'completed')

    def test_unknown_later_lesson_does_not_block_fixed_range(self):
        values=self.learning();values[0]['Z3']='U'
        self.fetch(values)
        detail=self.d.detailsFor(sid(1))
        self.assertTrue(detail['editable'])
        self.assertEqual(detail['selectedItems'],['z1','z2'])
        self.assertTrue(detail['recommendation'])

    def test_class_switch_flush_failure_blocks_then_roundtrip_restores(self):
        key=self.d.detailsFor(sid(1))['key']
        path=Path(self.folder.name)/'second.db';Database(path)
        self.b.workflow._classes.append(dict(name='第二虚构班',path=str(path)))
        self.d.queueDraft(key,dict(items=['z1'],due_at='invalid'))
        self.b.workflow.selectClass(1)
        self.assertEqual(self.b.db.path.name,'daily.db')
        self.d.discardDraft(key)
        self.commit()
        goal_id=self.d.goal['id']
        self.b.workflow.selectClass(1)
        self.assertEqual(self.d.goal,{})
        self.assertEqual(self.d.detailsFor(sid(1))['key'],'')
        self.assertFalse(self.d.saveCommitment(key,dict(items=['z1'],due_at='2099-12-31 20:00')))
        self.b.workflow.selectClass(0)
        self.assertEqual(self.d.goal['id'],goal_id)
        self.assertTrue(self.d.detailsFor(sid(1))['task'])

    def test_frozen_review_row_excluded_after_cancel(self):
        self.commit()
        with self.b.db.connect() as conn: conn.execute("UPDATE daily_tasks SET review_at='2000-01-01T00:00:00'")
        self.d.reload();self.d.selectTab(1);self.d.checkAll(True)
        detail=self.d.detailsFor(sid(1))
        self.assertTrue(self.d.cancelTask(detail['key'],'重新约定'))
        self.assertTrue(self.d.tableModel.rows[0]['_filter_stale'])
        self.assertEqual(self.d.listPreview()['included'],[])
        self.d.reapply()
        self.assertEqual(self.d.tableModel.rows,[])


if __name__ == '__main__': unittest.main()
