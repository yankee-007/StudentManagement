"""The newest batch follows later fetches; every older batch keeps its snapshot.

Run: python -m unittest tests.test_latest_batch_refresh -v
Synthetic roster, disposable databases, acquisition success path invoked directly (no network).
"""
import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.profile_storage import set_exemption
from app.roster_sync import sync_roster
from app.term_roster import arrange_students


TERM = dict(termId=551, termNo='P2026169', termName='刷新测试班')
LEARNING = ('courses','homework','missing_total','completed_total','completed_courses','completed_homework')


def sid(n):
    return f'P2026169{n:03d}A'


def row(n, name, flags=None):
    data = {'学号': sid(n), '姓名': name}
    data.update({f'{p}{i}': 'N' for p in ('C','Z') for i in range(1,33)})
    data.update(flags or {})
    return data


class LatestBatchRefreshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.b = Backend(Path(self.folder.name)/'refresh.db')
        raw = [dict(student_id=sid(i), name=f'学员{i}', status='在读') for i in (1,2)]
        sync_roster(self.b.db, TERM, arrange_students(TERM['termNo'], raw))
        for student in raw:
            self.b.repo.update_profile_field(student['student_id'], '微信', '是')
        self.b.refresh()
        self.w = self.b.workflow
        self.w.refresh_live()

    def fetch(self, rows, create=False):
        """Drive the real 获取数据 success path without any platform call."""
        self.b._fetch_db_path = str(self.b.db.path)
        self.b._class_name = '刷新测试班'
        self.b._create_after_fetch = create
        self.b._busy = True
        self.b._fetch_succeeded((rows, {'双方在读并导出': len(rows)}))

    def learning(self, batch, student):
        payload = self.w.store.rows(batch, student)[0]
        return {key: payload[key] for key in LEARNING}

    def table(self):
        return {r['student_id']: r for r in self.w.tableModel.rows}

    def batch_time(self, batch):
        return next(r['created_at'] for r in self.w.store.batches() if r['id'] == batch)

    def set_batch_time(self, batch, value):
        with self.b.db.connect() as conn:
            conn.execute('UPDATE campaigns SET created_at=? WHERE id=?',(value,batch))

    def test_newest_batch_follows_fetch_and_older_batch_stays_frozen(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        first = self.w._batch
        self.assertEqual(self.learning(first,sid(1))['missing_total'],'0/1')
        self.assertIn('创建时的数据快照', self.w.dashboard['notice'])

        self.fetch([row(1,'学员1',{'C1':'T','Z1':'T','C2':'T','Z2':'T'}), row(2,'学员2',{'C1':'T','Z1':'T'})])
        self.assertEqual(self.learning(first,sid(1))['missing_total'],'0/0')
        self.assertEqual(self.learning(first,sid(1))['completed_total'],'2/2')
        self.assertEqual(self.table()[sid(1)]['completed_total'],'2/2')
        self.assertEqual([r['completedRate'] for r in self.w.dashboard['courses']][:2],['100.00%','50.00%'])
        self.assertIn('获取刷新', self.w.dashboard['notice'])

        self.w.createBatch()
        newest = self.w._batch
        self.assertNotEqual(newest, first)
        self.fetch([row(1,'学员1',{'C1':'F','Z1':'F','C2':'F','Z2':'F'}), row(2,'学员2',{'C1':'F','Z1':'F'})])
        self.assertEqual(self.learning(newest,sid(1))['missing_total'],'2/2')
        self.assertEqual(self.learning(first,sid(1))['missing_total'],'0/0')
        self.assertEqual(self.learning(first,sid(1))['completed_total'],'2/2')

    def test_create_after_fetch_preserves_previous_batch(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        first = self.w._batch
        yesterday = '2026-10-06T18:56:00'
        self.set_batch_time(first, yesterday)
        with self.b.db.connect() as conn:
            before = list(conn.execute('SELECT snapshot FROM campaign_students WHERE batch_id=? ORDER BY student_id', (first,)))
            before = [r['snapshot'] for r in before]
            dashboard = conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?', (first,)).fetchone()['data']
        self.fetch([row(1,'学员1',{'C1':'F','Z1':'T'}), row(2,'学员2',{'C1':'F','Z1':'T'})], create=True)
        newest = self.w._batch
        self.assertNotEqual(first, newest)
        self.assertEqual(self.batch_time(first), yesterday)
        with self.b.db.connect() as conn:
            self.assertEqual([r['snapshot'] for r in conn.execute('SELECT snapshot FROM campaign_students WHERE batch_id=? ORDER BY student_id', (first,))], before)
            self.assertEqual(conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?', (first,)).fetchone()['data'], dashboard)
        self.assertEqual(self.learning(newest, sid(1))['missing_total'], '1/0')
        self.assertEqual(self.learning(first, sid(1))['missing_total'], '0/1')

    def test_student_missing_from_fetch_keeps_known_data(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        first = self.w._batch
        before = self.learning(first,sid(2))
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'T'})])
        self.assertEqual(self.learning(first,sid(2)), before)
        self.assertEqual(self.learning(first,sid(1))['missing_total'],'0/0')

    def test_refresh_keeps_feedback_draft_exemption_and_send_state(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        batch = self.w._batch
        self.assertTrue(self.w.saveDraft(sid(1),'待整理草稿'))
        self.w.store.submit(batch,sid(2),'已经回复')
        set_exemption(self.b.db,sid(2),'2099-12-31')
        self.w.store.simulate(batch,False)
        before = self.w.store.rows(batch)
        states = {r['student_id']: (r['send_state'],r['reply_state'],r['draft'],r['feedback'],r['exemption_text'],r['eligible']) for r in before}

        self.fetch([row(1,'学员1',{'C1':'T','Z1':'T'}), row(2,'学员2',{'C1':'T','Z1':'T','C2':'T'})])
        after = self.w.store.rows(batch)
        self.assertEqual({r['student_id']: (r['send_state'],r['reply_state'],r['draft'],r['feedback'],r['exemption_text'],r['eligible']) for r in after}, states)
        self.assertEqual(self.learning(batch,sid(1))['missing_total'],'0/0')
        self.assertFalse(next(r for r in after if r['student_id']==sid(2))['current_eligible'])

    def test_newest_batch_time_follows_refresh_and_old_batch_time_stays_frozen(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        first = self.w._batch
        self.set_batch_time(first,'2020-01-01T00:00:00')
        self.w.reload_batches(first)
        self.assertEqual(dict(self.w.tableModel.columns)['feedback'],'本次反馈情况（1月1号）')

        self.fetch([row(1,'学员1',{'C1':'T','Z1':'T'}), row(2,'学员2',{'C1':'T','Z1':'T'})])
        stamp = max(r['source_sync'] for r in self.w.store.rows(first))
        self.assertTrue(stamp and stamp[:10] != '2020-01-01')
        self.assertEqual(self.batch_time(first),stamp)
        self.assertIn(stamp.replace('T',' '),next(r['label'] for r in self.w.batches if r['id']==first))
        self.assertEqual(dict(self.w.tableModel.columns)['feedback'],f'本次反馈情况（{int(stamp[5:7])}月{int(stamp[8:10])}号）')

        self.w.createBatch()
        second = self.w._batch
        self.set_batch_time(second,'2020-01-02T00:00:00')
        self.fetch([row(1,'学员1',{'C1':'F','Z1':'F'}), row(2,'学员2',{'C1':'F','Z1':'F'})])
        self.assertNotEqual(self.batch_time(second),'2020-01-02T00:00:00')
        self.assertEqual(self.batch_time(first),stamp)

    def test_missing_dashboard_row_is_not_resurrected(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        with self.b.db.connect() as conn:
            conn.execute('DELETE FROM campaign_dashboards WHERE batch_id=?',(self.w._batch,))
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'T'}), row(2,'学员2',{'C1':'T','Z1':'T'})])
        self.assertFalse(self.w.dashboard['available'])
        self.assertIn('无法准确还原',self.w.dashboard['notice'])

    def test_without_batch_only_the_preview_changes(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})])
        self.assertEqual(self.w.store.batches(),[])
        self.assertEqual(self.table()[sid(1)]['missing_total'],'0/1')

    def test_repeated_refresh_without_new_data_writes_nothing(self):
        self.fetch([row(1,'学员1',{'C1':'T','Z1':'F'}), row(2,'学员2',{'C1':'T','Z1':'F'})], create=True)
        batch = self.w._batch
        with self.b.db.connect() as conn:
            before = [tuple(r) for r in conn.execute('SELECT * FROM campaign_students WHERE batch_id=? ORDER BY student_id',(batch,))]
            dashboard = conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?',(batch,)).fetchone()[0]
            created = conn.execute('SELECT created_at FROM campaigns WHERE id=?',(batch,)).fetchone()[0]
        self.assertEqual(self.w.refresh_live(),0)
        self.assertEqual(self.w.refresh_live(),0)
        with self.b.db.connect() as conn:
            self.assertEqual([tuple(r) for r in conn.execute('SELECT * FROM campaign_students WHERE batch_id=? ORDER BY student_id',(batch,))], before)
            self.assertEqual(conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?',(batch,)).fetchone()[0], dashboard)
            self.assertEqual(conn.execute('SELECT created_at FROM campaigns WHERE id=?',(batch,)).fetchone()[0], created)
        self.assertEqual(json.loads(dashboard).get('refreshed_at',''),'')


if __name__=='__main__':unittest.main()
