"""未进直播间模块回归：不联网、不启动界面、不发送任何消息。

Run: python -m unittest tests.test_live_absence -v
"""
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

from PySide6.QtCore import QCoreApplication

from app import live_storage as storage
from app.acquisition.completion import CompletionClient
from app.database import Database
from app.live_absence import LiveAbsence, format_seconds
from app.profile_storage import set_exemption
from tests.test_business_logic import TERM, seeded

LESSONS = [dict(resource_id='pre', label='【9月30日19：30课前准备】VIP专属预热课'),
           dict(resource_id='L01', label='01【Python核心语法精讲】_09HHQC14'),
           dict(resource_id='L02', label='02【运算符与数据处理】_09HHQC14')]
TERM_ID = str(TERM['termId'])


def live_row(n, name=None, seconds=None, status='在读'):
    """One row as CompletionClient.live_students returns it."""
    return dict(student_id=f'P2026169{n:03d}A', name=f'学员{n}' if name is None else name,
                live_seconds=seconds, status=status, student_type='新生')


class LiveRowParsingTests(unittest.TestCase):
    """hisLearningTime null/0/秒 必须保持区分，异常载荷必须整体拒绝。"""

    def client(self, rows):
        client = CompletionClient.__new__(CompletionClient)
        client._single_page = Mock(return_value=rows)
        return client

    def test_null_zero_and_seconds_stay_distinct(self):
        client = self.client([
            dict(studentNo='P2026169001A', realname='甲', hisLearningTime=None, status='0', studentType='0'),
            dict(studentNo='P2026169002A', realname='乙', hisLearningTime=0, status='0', studentType='0'),
            dict(studentNo='P2026169003A', realname='丙', hisLearningTime=137, status='0', studentType='0'),
            dict(studentNo='P2026169004A', realname='丁', hisLearningTime='', status='0', studentType='0'),
            dict(studentNo='P2026169005A', realname='戊', hisLearningTime='457', status='2', studentType='1'),
        ])
        rows = client.live_students(TERM_ID, 'L01')
        self.assertEqual([r['live_seconds'] for r in rows], [None, 0, 137, None, 457])
        self.assertEqual(rows[0]['status'], '在读')
        self.assertEqual(rows[4]['status'], '已退课')
        self.assertEqual(rows[4]['student_type'], '重修')
        form = client._single_page.call_args.kwargs['form']
        self.assertEqual((form['pageSize'], form['pageNum'], form['termId'], form['resourceId']),
                         (500, 1, TERM_ID, 'L01'))
        self.assertEqual(form['params[hisLearningTimeGeOrLe]'], '0')

    def test_malformed_payloads_are_rejected_as_a_whole(self):
        for rows in ([dict(studentNo='', realname='甲')],
                     [dict(studentNo='P2026169001A', unexpected='甲')],
                     [dict(studentNo='P2026169001A', realname='甲', hisLearningTime='很久')]):
            with self.assertRaises(ValueError):
                self.client(rows).live_students(TERM_ID, 'L01')
        with self.assertRaises(ValueError):
            self.client([]).live_students(TERM_ID, '')

    def test_seconds_are_formatted_for_the_table(self):
        self.assertEqual(format_seconds(None), '未进入')
        self.assertEqual(format_seconds(0), '0:00')
        self.assertEqual(format_seconds(137), '2:17')


class LiveAbsenceModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def module(self, count=4, wechat=None):
        context = seeded(count)
        b = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        entry = b.workflow._classes[b.workflow.class_index]
        entry.update(term_id=TERM_ID, term_no=TERM['termNo'], name=TERM['termName'])
        for i, value in enumerate(wechat or ('是',) * count, start=1):
            b.repo.update_profile_field(f'P2026169{i:03d}A', '微信', value)
        module = b.liveAbsence
        self.assertIsInstance(module, LiveAbsence)
        module._store.save_lessons(TERM_ID, LESSONS, '')
        self.assertTrue(module.reload(), module.notice)
        module.selectLesson(1)
        return b, module

    def feed(self, module, rows, term_id=TERM_ID, resource_id=None):
        """Drive the success path without a thread, exactly like a finished task."""
        module._request = dict(term_id=term_id, resource_id=resource_id or module._lesson_resource)
        module._busy = True
        module._succeeded(list(rows))

    def test_scope_requires_reading_wechat_and_no_live_exemption(self):
        b, m = self.module(5, wechat=('是', '否', '是', '是', '是'))
        set_exemption(b.db, 'P2026169003A', (date.today() + timedelta(days=2)).isoformat())
        self.feed(m, [live_row(1), live_row(2), live_row(3),
                      live_row(4, status='已退课'), live_row(5, status='预备')])
        self.assertEqual([r['student_id'] for r in m.tableModel.rows], ['P2026169001A'])
        self.assertEqual((m.apiCount, m.readyCount, m.eligibleCount, m.absentCount), (5, 3, 1, 1))
        self.assertEqual((m.noWechatCount, m.exemptCount), (1, 1))
        self.assertIn('1 人画像微信不是「是」', m.issues)
        self.assertIn('1 人在免催中', m.issues)

    def test_an_expired_exemption_no_longer_excludes_the_student(self):
        b, m = self.module(1)
        with b.db.connect() as conn:
            conn.execute('INSERT INTO exemptions VALUES(?,?)',
                         ('P2026169001A', (date.today() - timedelta(days=1)).isoformat()))
        self.feed(m, [live_row(1)])
        self.assertEqual(m.exemptCount, 0)
        self.assertEqual(m.recipientKeys, ['P2026169001A'])

    def test_students_outside_the_local_roster_are_only_reported(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(9)])
        self.assertEqual(m.missingCount, 1)
        self.assertEqual(m.recipientKeys, ['P2026169001A'])
        self.assertIn('1 人不在本班名单', m.issues)

    def test_zero_seconds_counts_as_entered_by_default_and_can_be_included(self):
        b, m = self.module(3)
        self.feed(m, [live_row(1), live_row(2, seconds=0), live_row(3, seconds=137)])
        self.assertEqual(m.recipientKeys, ['P2026169001A'])
        self.assertEqual((m.absentCount, m.enteredCount, m.zeroCount), (1, 2, 1))
        m.applyIncludeZero(True)
        self.assertEqual(m.recipientKeys, ['P2026169001A', 'P2026169002A'])
        self.assertEqual((m.absentCount, m.enteredCount), (2, 1))
        self.assertEqual(m.visibleCount, 2, '默认只显示未进入的人')
        m.applyShowAll(True)
        self.assertEqual(m.visibleCount, 3)
        self.assertEqual(m.recipientKeys, ['P2026169001A', 'P2026169002A'], '显示全部不改变可提醒范围')

    def test_one_reminder_per_lesson_keeps_rows_visible(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(2)])
        self.assertEqual(m.recipientCount, 2)
        self.assertTrue(m.mark_reminded(['P2026169001A'], 77))
        self.assertEqual(m.remindedCount, 1)
        self.assertEqual(m.recipientKeys, ['P2026169002A'])
        self.assertEqual(m.visibleCount, 2, '已提醒的学员仍然显示，只是不再进新名单')
        row = next(r for r in m.tableModel.rows if r['student_id'] == 'P2026169001A')
        self.assertTrue(row['remind_state'].startswith('已提醒 '), row['remind_state'])
        m.applyExcludeReminded(False)
        self.assertEqual(m.recipientCount, 2)
        m.applyExcludeReminded(True)
        self.assertEqual(m.recipientCount, 1)

    def test_reminder_marks_are_per_lesson_and_cleareable(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(2)])
        m.mark_reminded(['P2026169001A'], 77)
        m.selectLesson(2)
        self.assertFalse(m.hasResult)
        self.feed(m, [live_row(1), live_row(2)])
        self.assertEqual(m.remindedCount, 0, '另一个节次的提醒标记不适用')
        self.assertEqual(m.recipientCount, 2)
        m.selectLesson(1)
        self.feed(m, [live_row(1), live_row(2)])
        self.assertEqual(m.recipientCount, 1, '回到本节仍然记得已经提醒过')
        self.assertTrue(m.clearReminders())
        self.assertEqual(m.remindedCount, 0)
        self.assertEqual(m.recipientCount, 2)

    def test_duplicate_names_are_reported_and_block_list_creation(self):
        b, m = self.module(2)
        with b.db.connect() as conn:
            conn.execute("UPDATE class_roster SET name='同名同学' WHERE student_id IN (?,?)",
                         ('P2026169001A', 'P2026169002A'))
        self.feed(m, [live_row(1, name='同名同学'), live_row(2, name='同名同学')])
        self.assertEqual(m.duplicateCount, 2)
        self.assertIn('存在重名', m.issues)
        keys = list(m.recipientKeys)
        self.assertFalse(b.groupCenter.createFromLiveAbsence('重名名单', [dict(type='text', text='{姓名}')], keys))
        self.assertIn('名单内姓名重复', b.groupCenter.status)
        self.assertEqual(m.remindedCount, 0, '创建失败不得写入提醒标记')

    def test_create_list_renders_variables_and_records_the_marks(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(2, seconds=137)])
        g = b.groupCenter
        keys = list(m.recipientKeys)
        fields = [dict(type='text', text='{姓名}同学，{课程}已经开始了，请尽快进入直播间')]
        self.assertTrue(g.createFromLiveAbsence('本节未进直播间', fields, keys), g.status)
        list_id = g.selected['id']
        rows = g.store.rows(list_id)
        self.assertEqual([r['name'] for r in rows], ['学员1'])
        self.assertEqual(json.loads(rows[0]['content'])[0]['text'],
                         '学员1同学，01【Python核心语法精讲】_09HHQC14已经开始了，请尽快进入直播间')
        self.assertEqual(g.selected['prefix'], '', '联系人前缀保持空白，由群发中心参数区填写')
        self.assertEqual(m.remindedCount, 1)
        self.assertEqual(m.recipientCount, 0, '本节只提醒一次：刚创建的人不再进入下一批')

    def test_stale_keys_block_list_creation(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(2)])
        keys = list(m.recipientKeys)
        self.feed(m, [live_row(1)])
        self.assertFalse(b.groupCenter.createFromLiveAbsence('旧名单', [dict(type='text', text='{姓名}')], keys))
        self.assertIn('已变化', b.groupCenter.status)
        self.assertEqual(b.groupCenter.store.lists(), [])
        self.assertEqual(m.remindedCount, 0)

    def test_results_arriving_after_a_switch_are_discarded(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1)], term_id='552')
        self.assertFalse(m.hasResult)
        self.assertIn('班期已切换', m.notice)
        self.feed(m, [live_row(1)], resource_id='L02')
        self.assertFalse(m.hasResult)
        self.assertIn('节次已切换', m.notice)

    def test_lesson_refresh_keeps_the_roster_page_default_course(self):
        b, m = self.module(2)
        m._store.save_lessons(TERM_ID, LESSONS, 'L01')
        m._action = 'lessons'
        m._request = dict(term_id=TERM_ID, resource_id='')
        m._busy = True
        m._succeeded(LESSONS)
        self.assertEqual(m._store.load_lessons(TERM_ID)['resource_id'], 'L01',
                         '本模块只刷新课程缓存，不改「班期学员」页的第 1 节默认值')

    def test_switching_class_drops_the_previous_snapshot(self):
        b, m = self.module(2)
        self.feed(m, [live_row(1), live_row(2)])
        self.assertTrue(m.hasResult)
        entry = b.workflow._classes[b.workflow.class_index]
        entry.update(term_id='552', term_no='P2026176', name='另一个班')
        self.assertTrue(m.reload())
        self.assertFalse(m.hasResult, '切班后上一班的结果和提醒标记都不再适用')
        self.assertEqual(m.visibleCount, 0)


class LiveReminderStorageTests(unittest.TestCase):
    def test_reminder_table_is_created_on_first_use_of_an_old_class_database(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'old_class.db')
            with db.connect() as conn:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('live_reminders', tables, '测试前提：旧库还没有提醒表')
            self.assertEqual(storage.load_reminders(db, TERM_ID, 'L01'), {})
            stamp = storage.save_reminders(db, TERM_ID, 'L01', ['S1'], 5)
            self.assertEqual(storage.load_reminders(db, TERM_ID, 'L01'), {'S1': stamp})
            self.assertEqual(storage.load_reminders(db, TERM_ID, 'L02'), {})
            storage.save_reminders(db, TERM_ID, 'L01', ['S1'], 6)
            self.assertEqual(len(storage.load_reminders(db, TERM_ID, 'L01')), 1, '同一学员只保留一行')
            self.assertEqual(storage.clear_reminders(db, TERM_ID, 'L01'), 1)
            self.assertEqual(storage.load_reminders(db, TERM_ID, 'L01'), {})


if __name__ == '__main__':
    unittest.main()
