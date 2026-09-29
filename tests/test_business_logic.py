"""Business regressions from the 2026-09-26 audit.

Run: python -m unittest tests.test_business_logic -v
All data is synthetic and stored in disposable databases; no network calls.
"""
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.acquisition.merge_data import merge_students
from app.importer import import_rows
from app.roster_sync import sync_roster
from app.term_roster import arrange_students


TERM = dict(termId=551, termNo='P2026169', termName='审计测试班')


def completion(n=1, name='学员1', status=0):
    return dict(studentNo=f'P2026169{n:03d}A', realname=name, status=status,
                **{f'classNum_{i}': '直播' if i == 1 else None for i in range(1,33)})


def merged_row(n=1, name='学员1'):
    return {'学号': f'P2026169{n:03d}A', '姓名': name,
            **{f'{p}{i}': 'N' for p in ('C','Z') for i in range(1,33)}, 'C1':'T','Z1':'F'}


@contextmanager
def seeded(count=2):
    with tempfile.TemporaryDirectory() as directory:
        backend=Backend(Path(directory)/'audit.db')
        raw=[dict(student_id=f'P2026169{i:03d}A',name=f'学员{i}',status='在读') for i in range(1,count+1)]
        sync_roster(backend.db,TERM,arrange_students(TERM['termNo'],raw))
        for row in raw:
            backend.repo.update_profile_field(row['student_id'],'微信','是')
        backend.refresh()
        yield backend


class BusinessAudit(unittest.TestCase):
    def test_wechat_required_for_targets_and_sending(self):
        with seeded(3) as b:
            ids=[f'P2026169{i:03d}A' for i in range(1,4)]
            b.repo.update_profile_field(ids[1],'微信','否')
            b.repo.update_profile_field(ids[2],'微信','')
            import_rows(b.db,[merged_row(i,f'学员{i}') for i in range(1,4)])
            w=b.workflow
            w._batch=w.store.create('测试',w.template)
            w.reload_rows()
            w.filterRows('targets','')
            self.assertEqual([r['student_id'] for r in w.tableModel.rows],[ids[0]])
            w.store.simulate(w._batch)
            self.assertEqual(sum(r['send_state']=='模拟成功' for r in w.store.rows(w._batch)),1)
            b.repo.update_profile_field(ids[1],'微信','是')
            w.store.simulate(w._batch)
            rows=w.store.rows(w._batch)
            self.assertEqual(sum(r['send_state']=='模拟成功' for r in rows),2)
            self.assertTrue(next(r for r in rows if r['student_id']==ids[1])['current_eligible'])
            b.repo.update_profile_field(ids[0],'微信','否')
            w.reload_rows()
            self.assertEqual([r['student_id'] for r in w.tableModel.rows],[ids[1]])
            w.filterRows('all','')
            self.assertEqual(len(w.tableModel.rows),3)

    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_A01_withdrawn_student_must_not_abort_whole_class(self):
        rows,_=merge_students({'rows':[completion(),completion(2,'退课学员',2)]},
            {'P2026169001A':dict(name='学员1',status='在读',flags={1:'F'})})
        self.assertEqual(len(rows),1)

    def test_A02_name_conflict_must_be_reported_not_silently_merged(self):
        with self.assertRaises(ValueError):
            merge_students({'rows':[completion()]},
                {'P2026169001A':dict(name='另一名学员',status='在读',flags={1:'F'})})

    def test_A03_missing_homework_must_not_erase_known_completion(self):
        with seeded() as b:
            rows,_=merge_students({'rows':[completion(),completion(2,'学员2')]},
                {'P2026169001A':dict(name='学员1',status='在读',flags={1:'F'})})
            import_rows(b.db,rows)
            batch=b.workflow.store.create('审计测试班',b.workflow.template)
            dashboard=b.workflow.store.dashboard(batch)
            self.assertEqual(dashboard['courses'][0]['singleCompleted'],2)
            self.assertEqual(dashboard['courses'][0]['singleRate'],'100.00%')
            partial = next(r for r in b.workflow.store.rows(batch) if r['student_id']=='P2026169002A')
            self.assertEqual(partial['completed_homework'],'')
            self.assertEqual(partial['homework'],'未获取')
            self.assertFalse(partial['eligible'])

    def test_A04_partial_fetch_must_not_silently_create_full_class_campaign(self):
        with seeded(200) as b:
            import_rows(b.db,[merged_row(i,f'学员{i}') for i in range(1,201)])
            old=b.repo.learning_source()
            b._fetch_db_path=str(b.db.path)
            b._class_name='审计测试班'
            b._create_after_fetch=True
            b._busy=True
            b._fetch_succeeded(([merged_row()],{'双方在读并导出':1}))
            self.assertEqual(len(b.workflow.store.batches()),0)
            self.assertEqual(b.repo.learning_source(),old)
            self.assertEqual(len(b.fetchIssues.splitlines()),199)

    def test_partial_homework_only_preserves_homework_and_shows_unknown_course(self):
        with seeded(1) as b:
            rows,_=merge_students({'rows':[]},{'P2026169001A':dict(name='学员1',status='在读',flags={1:'T'})})
            import_rows(b.db,rows)
            preview=b.workflow.live_roster()[0]
            self.assertEqual(preview['courses'],'未获取')
            self.assertEqual(preview['completed_courses'],'')
            self.assertEqual(preview['completed_homework'],'1')
            self.assertEqual(preview['missing_total'],'—/0')

    def test_new_campaign_rejects_single_platform_missing_but_fetch_keeps_known_data(self):
        with seeded(1) as b:
            rows,stats=merge_students({'rows':[completion()]},{})
            b._fetch_db_path=str(b.db.path)
            b._class_name='审计测试班'
            b._create_after_fetch=True
            b._busy=True
            b._fetch_succeeded((rows,stats))
            self.assertEqual(b.workflow.store.batches(),[])
            self.assertEqual(b.repo.learning_source(),{})
            b._busy=True
            b._fetch_succeeded((rows,stats))
            self.assertEqual(b.repo.learning_source()['P2026169001A']['c1'],'T')
            self.assertEqual(b.repo.learning_source()['P2026169001A']['z1'],'U')

    def test_A05_cancelled_roster_request_must_not_write_response(self):
        with seeded(1) as b:
            t=b.termsModule
            t._accept('terms',[TERM])
            t._request_term=TERM
            t._resource='lesson-one'
            t._accept('students',[dict(student_id='P2026169001A',name='原姓名',status='在读')])
            t._busy=True
            t._action='students'
            t.cancel()
            t._succeeded([dict(student_id='P2026169001A',name='取消后的姓名',status='在读')])
            self.assertEqual(t.store.load(551)['rows'][0]['name'],'原姓名')

    def test_A06_current_leave_must_remove_student_from_current_targets(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            b.workflow.createBatch()
            b.repo.update_manual('P2026169001A',{'status':'请假','exemption_end':'2099-12-31'})
            b.workflow.refresh_live()
            b.workflow.filterRows('targets','')
            self.assertEqual(b.workflow.visibleCount,0)

    def test_current_leave_does_not_change_historical_target_membership(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            b.workflow.createBatch()
            first=b.workflow._batch
            b.workflow.createBatch()
            b.repo.update_manual('P2026169001A',{'status':'请假','exemption_end':'2099-12-31'})
            b.workflow.refresh_live()
            b.workflow.filterRows('targets','')
            self.assertEqual(b.workflow.visibleCount,0)
            b.workflow.selectBatch(1)
            self.assertEqual(b.workflow.visibleCount,1)
            self.assertNotIn('current_eligible',b.workflow.store.rows(first)[0])

    def test_A07_previous_feedback_must_not_include_later_campaign(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            b.workflow.createBatch()
            b.workflow.createBatch()
            b.workflow.simulate(False)
            b.workflow.store.submit(b.workflow._batch,'P2026169001A','后续批次的反馈')
            b.workflow.selectBatch(1)
            b.workflow.selectRow(0)
            self.assertNotIn('后续批次的反馈',b.workflow.previousFeedback)

    def test_control_duplicate_import_rolls_back_existing_data(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            before=b.repo.learning_source()
            with self.assertRaises(ValueError):
                import_rows(b.db,[merged_row(),merged_row()])
            self.assertEqual(b.repo.learning_source(),before)

    def test_control_leave_blocks_send_and_old_learning_snapshot_is_frozen(self):
        with seeded(1) as b:
            import_rows(b.db,[merged_row()])
            b.workflow.createBatch()
            first=b.workflow._batch
            before=b.workflow.store.rows(first)[0]['homework']
            b.repo.update_manual('P2026169001A',{'status':'请假','exemption_end':'2099-12-31'})
            b.workflow.simulate(False)
            self.assertEqual(b.workflow.store.rows(first)[0]['send_state'],'不发送')
            import_rows(b.db,[dict(merged_row(),Z1='T')])
            b.workflow.createBatch()
            self.assertEqual(b.workflow.store.rows(first)[0]['homework'],before)


if __name__=='__main__':unittest.main()
