"""Synthetic frozen batches: safe aggregates, independent state and real notifications."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.learning_overview import aggregate_batch, grade, load_batches
from app.backend import Backend
from app.roster_sync import sync_roster


def dashboard(total=4, version=3, lessons=(1, 2), course=3, homework=2):
    def rows(done):
        return [dict(lesson=n, completed=done, completedRate=f'{100*done/total:.2f}%') for n in lessons]
    return dict(version=version, total=total, opened=max(lessons, default=0), courses=rows(course), homework=rows(homework))


def records():
    return [('A', dict(roster_status='在读', completed_courses='0', wechat='否', exemption_date='2099-01-01')),
            ('B', dict(roster_status='在读', completed_courses='1')),
            ('C', dict(roster_status='在读', completed_courses='2')),
            ('D', dict(roster_status='在读', completed_courses='2')),
            ('E', dict(roster_status='退课', completed_courses='0')),
            ('P', dict(roster_status='在读', is_placeholder=True, completed_courses='0'))]


def seed(conn, batch, data=None, members=None, marks=None):
    conn.execute('INSERT INTO campaigns(id,class_name,created_at,template) VALUES(?,?,?,?)',
                 (batch, '虚构测试班', f'2026-10-{batch:02d}T12:00:00', ''))
    for position, (sid, snap) in enumerate(members if members is not None else records()):
        defaults = dict(priority=0, position=position, courses='', homework='', missing_total='0/0',
                        completed_total='0/0', completed_homework='0')
        snap = dict(defaults, **snap)
        conn.execute('INSERT INTO campaign_students(batch_id,student_id,name,remark,snapshot,eligible,reason,message,send_state) VALUES(?,?,?,?,?,?,?,?,?)',
                     (batch, sid, '虚构学员'+sid, '虚构学员'+sid, json.dumps(snap), 0, '', '', '不发送'))
    if data is not None:
        conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)', (batch, json.dumps(data)))
    for sid, mark in (marks or {}).items():
        conn.execute('INSERT INTO campaign_followup_status VALUES(?,?,?)', (batch, sid, mark))


class OverviewAggregateTests(unittest.TestCase):
    def test_scope_counts_and_manual_coverage_are_independent_of_feedback(self):
        b = aggregate_batch(1, '', dashboard(), records(), {'A':'是', 'B':'否', 'C':'是', 'E':'是', 'P':'是'})
        self.assertEqual(b['total'], 4)
        self.assertEqual([r['people'] for r in b['completion']], [2, 1, 1])
        self.assertEqual([r['cumulative'] for r in b['completion']], [2, 3, 4])
        self.assertEqual([r['followable'] for r in b['completion']], [1, 0, 1])
        self.assertEqual(b['followupSummary'], dict(total=4, marked=3, yes=2, no=1, unmarked=1))
        self.assertEqual(b['lessons'][-1]['courseDone'], 3)
        self.assertEqual(b['lessons'][-1]['gap'], 25)
        unmarked = aggregate_batch(1, '', dashboard(), records(), {})
        self.assertTrue(all(r['followable'] is None for r in unmarked['completion']))
        all_no = aggregate_batch(1, '', dashboard(), records(), dict.fromkeys('ABCD', '否'))
        self.assertTrue(all(r['followable'] == 0 for r in all_no['completion']))

    def test_unknown_never_falls_back_or_becomes_zero_and_exact_counts_survive(self):
        snaps = records()[:4]
        snaps[0][1].update(completed_courses='', completed_total='1/1')
        snaps[1][1].pop('completed_courses')
        snaps[1][1]['completed_total'] = '1/0'
        snaps[2][1]['completed_courses'] = '5'
        snaps[3][1]['completed_courses'] = None
        b = aggregate_batch(1, '', dashboard(), snaps, {})
        self.assertEqual(b['unknown'], 2)
        buckets = {r['count']:r for r in b['completion']}
        self.assertEqual(buckets[0]['people'], 0)
        self.assertEqual(buckets[5]['people'], 1)
        self.assertEqual(buckets[1]['people'], 1)
        self.assertEqual(buckets[0]['cumulativeRate'], 50)
        self.assertIn('仍保留在全班分母', b['completionNotice'])

    def test_missing_legacy_and_scope_mismatch_preserve_members_without_estimates(self):
        for data in ({}, dashboard(version=1), dashboard(total=5)):
            with self.subTest(data=data):
                b = aggregate_batch(1, '', data, records(), {})
                self.assertEqual(b['lessons'], [])
                self.assertEqual(b['total'], 4)
                self.assertEqual(sum(r['people'] for r in b['completion']), 4)
                self.assertTrue(b['learningNotice'])
        malformed = dashboard()
        malformed['courses'][0]['completedRate'] = 'NaN%'
        malformed['courses'][1]['completed'] = 9
        self.assertEqual(aggregate_batch(1, '', malformed, records(), {})['lessons'], [])

    def test_old_batches_survive_missing_tables_or_dashboard_with_select_only(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        self.assertEqual(load_batches(conn), [])
        conn.executescript('CREATE TABLE campaigns(id INTEGER,class_name TEXT,created_at TEXT,template TEXT); '
                           'CREATE TABLE campaign_students(batch_id INTEGER,student_id TEXT,name TEXT,remark TEXT,snapshot TEXT,eligible INTEGER,reason TEXT,message TEXT,send_state TEXT); '
                           'CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT); '
                           'CREATE TABLE campaign_followup_status(batch_id INTEGER,student_id TEXT,status TEXT);')
        seed(conn, 1)
        seed(conn, 2, dashboard(version=2))
        conn.execute('DROP TABLE campaign_followup_status')
        conn.execute('PRAGMA query_only=ON')
        batches = load_batches(conn)
        self.assertEqual([b['id'] for b in batches], [2, 1])
        self.assertTrue(batches[0]['lessons'])
        self.assertFalse(batches[1]['lessons'])
        self.assertEqual(batches[1]['members'], 6)

    def test_grades_include_boundary_and_negative_gaps(self):
        self.assertEqual([grade(n) for n in (-5, 5, 5.01, 10, 10.01, 15, 15.01)],
                         ['优秀', '优秀', '良好', '良好', '及格', '及格', '不合格'])


class OverviewIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.backend = Backend(Path(self.folder.name)/'overview.db')
        self.addCleanup(self.backend.deleteLater)
        with self.backend.db.connect() as conn:
            seed(conn, 1)
            seed(conn, 2, dashboard(lessons=(1,)), marks={'A':'是'})
            seed(conn, 3, dashboard(), marks=dict.fromkeys('ABCD', '否'))
        self.w = self.backend.workflow
        self.w.reload_batches()
        self.o = self.backend.learningOverview
        self.o.setActive(True)

    def test_four_tabs_selection_isolation_latest_fixed_and_class_reset(self):
        selected = (self.w._batch, self.w.selected.get('student_id'))
        self.o.selectBatch('history', 2)
        self.o.selectBatch('goal', 1)
        self.o.selectBatch('compare', 1)
        self.o.selectBatch('baseline', 0)
        self.o.selectTab(2)
        self.assertEqual(self.o.view['selectedLesson'], 1)
        self.assertEqual(len(self.o.view['rateChart']['series']), 4)
        self.assertTrue(all(s['dashed'] for s in self.o.view['rateChart']['series'][2:]))
        self.o.selectTab(0)
        self.assertIn('第3次', self.o.view['title'])
        self.o.selectTab(1)
        self.assertIn('第1次', self.o.view['title'])
        self.assertEqual(self.o.lessonOptions, [])
        self.o.selectTab(3)
        self.assertIn('第2次', self.o.view['title'])
        self.o.setTarget(0, '95')
        self.assertEqual((self.w._batch, self.w.selected.get('student_id')), selected)
        self.w._classes.append(dict(name='另一个测试班', path=str(Path(self.folder.name)/'other.db')))
        self.w.selectClass(1)
        self.assertFalse(self.o.view['available'])
        self.assertEqual(self.o.goalIndex, -1)
        self.assertEqual(self.o.targets, ['85', '85', '15'])

    def test_goals_same_lesson_recent_five_and_invalid_input(self):
        self.o.selectTab(3)
        v = self.o.view
        self.assertEqual([c['need'] for c in v['goalCards']], [1, 2, 1])
        self.assertEqual(v['trends'][0]['series'][0]['values'], [None, None, 75])
        self.assertTrue(all(row['cells'][1] == '第1～2节' for row in v['trendRows']))
        for invalid in ('', '-1', '101', 'nan', 'inf', 'abc'):
            self.o.setTarget(0, invalid)
            self.assertIsNone(self.o.view['goalCards'][0]['need'])
            self.assertEqual(self.o.view['trends'][0]['thresholds'], [])
        self.o.setTarget(0, '0')
        self.assertEqual(self.o.view['goalCards'][0]['need'], 0)
        for n in range(4, 8):
            with self.backend.db.connect() as conn:
                seed(conn, n, dashboard())
        self.o.reload()
        self.o.selectBatch('goal', 0)
        self.assertEqual(self.o.view['trends'][0]['labels'], [3, 4, 5, 6, 7])

    def test_homework_candidates_require_completed_courses_in_selected_cumulative_lessons(self):
        members = records()
        members[0][1].update(courses='3', completed_courses='2', homework='1,3', completed_homework='1')
        members[1][1].update(courses='2', completed_courses='2', homework='2', completed_homework='1')
        members[2][1].update(homework='2', completed_homework='1')
        members[3][1].update(homework='未获取', completed_homework='')
        members[4][1].update(homework='1', completed_homework='0')
        members[5][1].update(homework='1', completed_homework='0')
        with self.backend.db.connect() as conn:
            seed(conn, 4, dashboard(homework=1), members,
                 {'A':'是', 'B':'是', 'C':'否', 'D':'是', 'E':'是', 'P':'是'})
        self.o.reload()
        self.o.selectTab(3)
        self.o.selectBatch('goal', 0)
        original_cursor = (self.w._batch, self.w.editorKey)
        candidates = self.o.view['homeworkCandidates']
        self.assertTrue(candidates['available'])
        self.assertEqual([row['cells'][1:] for row in candidates['rows']],
                         [['虚构学员A', 'A', '1'], ['虚构学员C', 'C', '2']])
        self.assertIn('1名学员学习数据未知', candidates['notice'])
        self.o.selectLesson(1)
        self.assertEqual([row['cells'][2] for row in self.o.view['homeworkCandidates']['rows']], ['A'])
        self.assertIn('候选人数比所需人数少 1人', self.o.view['homeworkCandidates']['notice'])
        self.o.selectBatch('goal', 1)  # 第3次无欠交作业，不继承第4次学习结果
        self.assertEqual(self.o.view['homeworkCandidates']['rows'], [])
        self.assertEqual((self.w._batch, self.w.editorKey), original_cursor)
        self.o.selectBatch('goal', 3)  # 第1次没有累计快照
        self.assertFalse(self.o.view['homeworkCandidates']['available'])

    def test_homework_candidates_reject_unmatched_and_malformed_snapshots(self):
        members = records()
        for _, snap in members:
            snap.update(homework='1', completed_homework='0')
        members[0][1]['matched'] = False
        members[1][1]['homework'] = '1,x'
        members[2][1]['homework'] = '0,33'
        members[3][1]['homework'] = '3'  # 所选第1～2节以外
        with self.backend.db.connect() as conn:
            seed(conn, 4, dashboard(), members, dict.fromkeys('ABCDEP', '是'))
        self.o.reload(); self.o.selectTab(3); self.o.selectBatch('goal', 0)
        self.assertEqual(self.o.view['homeworkCandidates']['rows'], [])
        self.assertIn('3名学员学习数据未知', self.o.view['homeworkCandidates']['notice'])

    def test_homework_candidates_match_zero_course_missing_and_ignore_followup_marks(self):
        from app.campaigns import learning_snapshot
        members = records()[:4]
        for sid, snap in members:
            flags = {f'{kind}{n}':'T' for kind in ('c','z') for n in range(1,6)}
            if sid == 'A': flags.update(c1='F', z1='F')
            if sid == 'B': flags['z2'] = 'F'
            if sid == 'C': flags['z5'] = 'F'
            snap.update(learning_snapshot(flags))
        with self.backend.db.connect() as conn:
            seed(conn, 4, dashboard(lessons=(1,2,3,4,5), homework=1), members,
                 {'A':'是', 'B':'否', 'D':'是'})
        self.o.reload(); self.o.selectTab(3); self.o.selectBatch('goal', 0)
        self.o.selectLesson(5)
        self.assertEqual([row['cells'][1:] for row in self.o.view['homeworkCandidates']['rows']],
                         [['虚构学员B','B','2'], ['虚构学员C','C','5']])
        self.o.selectLesson(1)
        self.assertEqual(self.o.view['homeworkCandidates']['rows'], [])

    def test_first_lesson_candidates_include_students_with_later_courses_pending(self):
        from app.campaigns import learning_snapshot
        from app.dashboard import learning_dashboard
        members, source = [], {}
        for index in range(165):
            sid = f'S{index+1:03d}'
            flags = {f'{kind}{n}': 'T' for kind in ('c', 'z') for n in range(1, 6)}
            if index < 20:
                flags['z1'] = 'F'
                if index >= 4:
                    flags.update({f'c{n}': 'F' for n in range(2, 6)})
            elif index >= 147:
                flags.update(c1='F', z1='F')
            source[sid] = flags
            members.append((sid, dict(roster_status='在读', matched=True, **learning_snapshot(flags))))
        data = learning_dashboard([dict(student_id=sid, **snap) for sid, snap in members], source)
        with self.backend.db.connect() as conn:
            seed(conn, 4, data, members)
        self.o.reload(); self.o.selectTab(3); self.o.selectBatch('goal', 0)
        cursor = (self.w._batch, self.w.editorKey)
        self.o.selectLesson(1)
        candidates = self.o.view['homeworkCandidates']
        self.assertEqual([row['cells'][2:] for row in candidates['rows']],
                         [[f'S{n:03d}', '1'] for n in range(1, 21)])
        self.assertEqual(candidates['scope'], '第1节')
        self.assertIn('排除第1节内仍有未完课程', candidates['filterText'])
        self.assertIn('保留第1节内仍有欠交作业', candidates['filterText'])
        self.assertEqual(self.o.view['metrics'][2]['value'], '12.12pp')
        self.o.selectLesson(5)
        self.assertEqual([row['cells'][2] for row in self.o.view['homeworkCandidates']['rows']],
                         [f'S{n:03d}' for n in range(1, 5)])
        self.assertEqual(self.o.view['homeworkCandidates']['scope'], '第1～5节')
        self.assertEqual((self.w._batch, self.w.editorKey), cursor)

    def test_hidden_class_roundtrip_resets_choices_and_inspection_does_not_change_evaluation(self):
        self.o.selectTab(2)
        self.o.inspectLesson(1)
        self.assertEqual(self.o.view['selectedLesson'], 1)  # baseline第2次仅有第1节
        self.o.selectBatch('baseline', 0)
        self.o.selectLesson(2)
        self.o.inspectLesson(1)
        self.assertEqual(self.o.view['detailLesson'], 1)
        self.assertEqual(self.o.view['selectedLesson'], 2)
        self.o.selectBatch('history', 2)
        self.o.setActive(False)
        self.w._classes.append(dict(name='另一个班', path=str(Path(self.folder.name)/'other.db')))
        self.w.selectClass(1)
        self.w.selectClass(0)
        self.o.setActive(True)
        self.assertEqual(self.o.historyIndex, 0)

    def test_no_common_lessons_same_batch_zero_change_and_different_population(self):
        self.o.selectTab(2)
        self.o.selectBatch('baseline', 2)
        self.assertEqual(self.o.lessonOptions, [])
        self.assertEqual(self.o.view['metrics'][0]['value'], '—')
        self.assertTrue(self.o.view['completionRows'])
        self.o.selectBatch('baseline', 0)
        self.assertTrue(all(r['cells'][3] == '+0.00pp' for r in self.o.view['lessonRows']))
        self.assertTrue(all(r['cells'][3] == '+0.00人' for r in self.o.view['distributionRows']))
        with self.backend.db.connect() as conn:
            seed(conn, 4, dashboard(total=5), records()[:4]+[('Q',dict(roster_status='在读', completed_courses='0'))])
        self.o.reload()
        self.o.selectBatch('compare', 0)
        self.assertIn('分母不同', self.o.view['notice'])

    def test_real_mark_notification_preserves_workbench_cursor_and_future_marks(self):
        self.w.filterRows('all', '虚构学员A')
        cursor = (self.w._batch, self.w.selected.get('student_id'), list(self.w._model.rows))
        self.assertTrue(self.w.setFollowupStatusForSelection(self.w.editorKey, '是'))
        self.assertIn('是 1', self.o.view['followup'])
        self.assertEqual((self.w._batch, self.w.selected.get('student_id')), cursor[:2])
        self.assertTrue(self.w.setFollowupStatusForSelection(self.w.editorKey, ''))
        self.assertIn('未填写 1', self.o.view['followup'])
        self.o.selectTab(1)
        self.o.selectBatch('history', 1)
        self.assertIn('是 1', self.o.view['followup'])
        with self.backend.db.connect() as conn:
            self.assertEqual(conn.execute('SELECT status FROM campaign_followup_status WHERE batch_id=2 AND student_id="A"').fetchone()[0], '是')

    def test_fetch_refresh_updates_latest_while_history_and_workbench_batch_stay_fixed(self):
        term = dict(termId=551, termNo='P2026169', termName='测试采集班')
        sid = 'P2026169001A'
        sync_roster(self.backend.db, term, [dict(student_id=sid, name='虚构采集学员', status='在读', source='接口学员', student_type='新生', nickname='')])
        self.backend.repo.update_profile_field(sid, '微信', '是')
        flags = {'c1':'T','z1':'F'}
        self.backend.repo.set_setting('snapshot', json.dumps([dict(student_id=sid, flags=flags)]))
        self.w.createBatch()
        older = self.w._batch
        self.w.createBatch()
        latest = self.w._batch
        self.w.selectBatch(1)
        before = self.w.store.dashboard(older)
        self.backend.repo.set_setting('snapshot', json.dumps([dict(student_id=sid, flags={'c1':'T','z1':'T'})]))
        self.w.refresh_live()
        self.assertEqual(self.w._batch, older)
        self.assertEqual(self.w.store.dashboard(older), before)
        self.assertIn(f'第{latest}次', self.o.view['title'])
        self.assertEqual(self.o.view['metrics'][1]['value'], '100.00%')


if __name__ == '__main__':
    unittest.main()
