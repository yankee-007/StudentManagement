"""Remark revision regressions. No desktop, no enterprise WeChat, no network.

Run: python -m unittest tests.test_remark_renamer -v
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

from app import remark_scan as scan
from app import remark_storage as storage
from app.database import Database
from app.wecom_renamer import (RemarkDriver, RemarkRenameError, RemarkRenamer,
                               RemarkWorker, load_change_remark)
from tests.profile_fixtures import insert_profile
from tests.test_business_logic import seeded


class FakeSender:
    """Stands in for WeComSender; records the search keys it was given."""

    def __init__(self, titles=None, fail_with=None):
        self.titles = dict(titles or {})
        self.fail_with = dict(fail_with or {})
        self.searched = []
        self.keys = Mock()
        self.gui = Mock()
        self.process = Mock()
        self.keys.getWindowsWithTitle.return_value = [Mock(title='企业微信', isMinimized=False)]
        self.gui.GetForegroundWindow.return_value = 1
        self.process.GetWindowThreadProcessId.side_effect = lambda hwnd: (1, 777)

    def _check(self, hwnd, title, pid):
        """WeComSender._check is stubbed out: no real window focus exists in tests."""

    def search_contact_v2(self, contact, options, *, close_on_success=True,
                          activate_on_close=False, capture_title=False):
        self.searched.append(contact)
        if contact in self.fail_with:
            raise RuntimeError(self.fail_with[contact])
        return (2, 777, self.titles.get(contact, ''))


class FakeDriver:
    """Stands in for RemarkDriver; every call is recorded for assertions."""

    def __init__(self, titles=None, fail_with=None, fail_errors=None):
        self.titles = dict(titles or {})
        self.fail_with = dict(fail_with or {})
        self.fail_errors = dict(fail_errors or {})
        self.reads = []
        self.changes = []

    def read_remark(self, name):
        self.reads.append(name)
        if name in self.fail_errors:
            raise self.fail_errors[name]
        return self.titles.get(name)

    def change_remark(self, observed, desired):
        self.changes.append((observed, desired))
        if observed in self.fail_with:
            raise RemarkRenameError(self.fail_with[observed])
        return desired


class RemarkScanTests(unittest.TestCase):
    def test_prefix_derives_from_term_number_and_can_be_overridden(self):
        self.assertEqual(scan.term_prefix('P2026175'), 'py175')
        self.assertEqual(scan.term_prefix('P2026169'), 'py169')
        self.assertEqual(scan.term_prefix('编程175期'), 'py175')
        self.assertEqual(scan.term_prefix('P2026'), '', '不把年份当班号')
        self.assertEqual(scan.term_prefix(''), '')
        for bad in ('py 175', 'py\n175'):
            with self.assertRaises(ValueError):
                scan.normalize_prefix(bad)

    def test_classification_covers_the_four_outcomes(self):
        self.assertEqual(scan.classify('示例学员/新生', '示例学员', 'py175示例学员'), (scan.CHANGED, ''))
        self.assertEqual(scan.classify('示例学员/退课', '示例学员', 'py175示例学员')[0], scan.CHANGED)
        self.assertEqual(scan.classify('py175示例学员', '示例学员', 'py175示例学员')[0], scan.COMPLIANT)
        self.assertEqual(scan.classify('示例学员', '示例学员', 'py175示例学员')[0], scan.REVIEW)
        self.assertEqual(scan.classify('李明', '示例学员', 'py175示例学员')[0], scan.NOT_FOUND)
        self.assertEqual(scan.classify('', '示例学员', 'py175示例学员')[0], scan.NOT_FOUND)

    def test_a_different_prefix_is_not_treated_as_compliant(self):
        self.assertFalse(scan.remark_matches('py169示例学员', 'py175示例学员'))
        self.assertEqual(scan.classify('py169示例学员', '示例学员', 'py175示例学员')[0], scan.REVIEW)

    def test_duplicate_names_are_detected_across_the_whole_roster(self):
        duplicates = scan.duplicate_names([{'name': '甲'}, {'name': '甲'}, {'name': '乙'}])
        self.assertEqual(duplicates, {'甲'})

    def test_bootstrap_upgrades_an_old_class_database(self):
        """A class database created before this module must work on first use."""
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'old_class.db')
            with db.connect() as conn:
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('S1','老学员','2026-01-01')")
                conn.execute("INSERT INTO class_roster(student_id,term_id,ordinal,name,status) VALUES('S1','',1,'老学员','在读')")
                conn.execute("INSERT INTO profiles(student_id,fields) VALUES('S1',?)", (json.dumps({'微信': '是'}),))
            with db.connect() as conn:
                existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('wecom_remark_scan', existing, '测试前提：旧库还没有批改表')
            students = storage.load_students(db)
            self.assertEqual([s['student_id'] for s in students], ['S1'])
            self.assertIsNone(students[0]['scan'])
            storage.save_scan(db, 'S1', observed='py175老学员', desired='py175老学员',
                              state=scan.COMPLIANT, detail='')
            self.assertEqual(storage.load_students(db)[0]['scan']['state'], scan.COMPLIANT)


class RemarkModuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def backend(self, count=3):
        context = seeded(count)
        b = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        b.workflow._classes[b.workflow.class_index]['term_no'] = 'P2026175'
        renamer = RemarkRenamer(b)
        self.addCleanup(renamer.shutdown)
        return b, renamer

    def run_tasks(self, renamer, tasks, driver):
        worker = RemarkWorker(renamer.owner.db, tasks, lambda: driver)
        worker.run()
        renamer.reload()
        return worker

    def test_scope_is_only_the_wechat_yes_students(self):
        b, renamer = self.backend(3)
        b.repo.update_profile_field('P2026169002A', '微信', '否')
        b.repo.update_profile_field('P2026169003A', '微信', '')
        self.assertTrue(renamer.reload(), renamer.notice)
        self.assertEqual([r['student_id'] for r in renamer._rows], ['P2026169001A'])
        self.assertEqual(renamer.prefix, 'py175')
        self.assertEqual(renamer._rows[0]['desired'], 'py175学员1')

    def test_prefix_follows_a_late_term_binding(self):
        """The backend builds the module before the term binding is aligned."""
        b, renamer = self.backend(1)
        renamer._prefix = ''
        renamer._prefix_term = None
        b.repo.update_profile_field('P2026169001A', '微信', '是')
        b.workflow._classes[b.workflow.class_index]['term_no'] = 'P2026175'
        b.workflow._classes[b.workflow.class_index]['term_id'] = '564'
        self.assertTrue(renamer.reload(), renamer.notice)
        self.assertEqual(renamer.prefix, 'py175')
        self.assertEqual([r['desired'] for r in renamer._rows], ['py175学员1'])
        # A later binding of the same class must be picked up too.
        b.workflow._classes[b.workflow.class_index]['term_no'] = 'P2026169'
        b.workflow._classes[b.workflow.class_index]['term_id'] = '551'
        self.assertTrue(renamer.reload(), renamer.notice)
        self.assertEqual(renamer.prefix, 'py169')

    def test_save_options_accepts_missing_or_partial_parameters(self):
        """The regression: QML passes a map, and an empty/partial map must not fail."""
        b, renamer = self.backend(1)
        for passed in ({}, {'wait': 0.5}, {'wait': None, 'timeout': None}, None, ''):
            self.assertTrue(renamer.saveOptions('py175', passed), f'{passed!r} -> {renamer.notice}')
        self.assertEqual(renamer.prefix, 'py175')
        self.assertEqual(renamer._rows[0]['desired'], 'py175学员1')
        # A JSON string (script caller) and out-of-range values behave predictably.
        self.assertTrue(renamer.saveOptions('py175', '{"wait": 0.4, "timeout": 5}'), renamer.notice)
        self.assertIn('0.4', renamer.optionsSummary)
        self.assertFalse(renamer.saveOptions('py175', {'wait': 0}), renamer.notice)
        self.assertIn('保存失败', renamer.notice)
        self.assertFalse(renamer.saveOptions('py175', {'wait': 'abc'}), renamer.notice)

    def test_switching_class_rereads_the_roster_and_the_prefix(self):
        """The regression: switching class left the previous class's list on screen."""
        b, _ = self.backend(1)
        renamer = b.remarkRenamer  # the instance the class switch notifies
        self.assertTrue(renamer.reload(), renamer.notice)
        self.assertEqual(renamer.prefix, 'py175')
        other = Database(Path(b.db.path).parent / 'class_other.db')
        with other.connect() as conn:
            conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('P2026169001A','别班学员','2026-01-01')")
            insert_profile(conn, 'P2026169001A', '别班学员', 1, {'微信': '是'})
        b.workflow._classes.append({'name': '别班', 'path': str(other.path), 'term_id': '551', 'term_no': 'P2026169'})
        b.workflow.selectClass(1)
        self.assertEqual(str(b.db.path), str(other.path))
        self.assertEqual(renamer.prefix, 'py169', '切班后前缀应换成本班默认值')
        self.assertEqual([r['name'] for r in renamer.rows], ['别班学员'], '切班后应显示新班名单')
        self.assertEqual(renamer.rows[0]['desired'], 'py169别班学员')

    def test_saved_prefix_overrides_the_default(self):
        b, renamer = self.backend(1)
        self.assertTrue(renamer.saveOptions('py999', {'wait': 0.5, 'timeout': 3}), renamer.notice)
        self.assertEqual(storage.load_prefix(b.db, 'P2026175'), 'py999')
        self.assertEqual(renamer._rows[0]['desired'], 'py999学员1')
        again = RemarkRenamer(b)
        self.addCleanup(again.shutdown)
        self.assertEqual(again.prefix, 'py999')

    def test_legacy_remark_is_changed_and_written_back(self):
        b, renamer = self.backend(2)
        driver = FakeDriver({'学员1': '学员1/新生', '学员2': '学员2/新生'})
        renamer._driver_factory = lambda: driver
        with patch('app.send_controller.F11Hotkey.start'):
            self.assertTrue(renamer.start(), renamer.notice)
            self.assertTrue(renamer._worker.wait(10000), '批改线程未结束')
            for _ in range(200):
                if not renamer.active:
                    break
                self.app.processEvents()
        self.assertEqual(driver.changes, [('学员1/新生', 'py175学员1'), ('学员2/新生', 'py175学员2')])
        rows = {r['student_id']: r for r in renamer.rows}
        self.assertEqual(rows['P2026169001A']['state'], scan.CHANGED)
        self.assertEqual(rows['P2026169002A']['state'], scan.CHANGED)
        self.assertEqual(renamer.changedCount, 2)
        self.assertEqual(renamer.pendingCount, 0)

    def test_compliant_remark_is_skipped_and_recorded(self):
        b, renamer = self.backend(2)
        driver = FakeDriver({'学员1': 'py175学员1', '学员2': '学员2/新生'})
        self.run_tasks(renamer, [renamer._task(r, 'scan') for r in renamer._rows], driver)
        self.assertEqual(driver.changes, [('学员2/新生', 'py175学员2')], '已符合者不得改名')
        states = {r['name']: (r['scan'] or {}).get('state') for r in storage.load_students(b.db)}
        self.assertEqual(states['学员1'], scan.COMPLIANT)
        self.assertEqual(states['学员2'], scan.CHANGED)
        with b.db.connect() as conn:
            contacts = {r['student_id']: r['remark'] for r in conn.execute('SELECT * FROM student_contacts')}
        self.assertEqual(contacts, {'P2026169001A': 'py175学员1', 'P2026169002A': 'py175学员2'},
                         '成功与已符合都要回写备注对应表')

    def test_compliant_remark_survives_a_restart(self):
        b, renamer = self.backend(1)
        self.run_tasks(renamer, [renamer._task(renamer._rows[0], 'scan')],
                       FakeDriver({'学员1': 'py175学员1'}))
        self.assertTrue(renamer.reload())
        self.assertEqual(renamer.pendingCount, 0, '已入库的学员不应再次进入待处理')
        self.assertEqual(renamer.rows[0]['state'], scan.COMPLIANT)

    def test_unexpected_remark_is_recorded_for_review_only(self):
        b, renamer = self.backend(1)
        driver = FakeDriver({'学员1': '学员1'})
        self.run_tasks(renamer, [renamer._task(renamer._rows[0], 'scan')], driver)
        self.assertEqual(driver.changes, [])
        self.assertEqual(renamer.rows[0]['state'], scan.REVIEW)
        self.assertIn('人工确认', renamer.rows[0]['detail'])

    def test_force_selected_rewrites_the_review_row(self):
        b, renamer = self.backend(1)
        row = renamer._rows[0]
        self.run_tasks(renamer, [renamer._task(row, 'scan')], FakeDriver({'学员1': '学员1'}))
        self.assertEqual(renamer.rows[0]['state'], scan.REVIEW)
        driver = FakeDriver({'学员1': '学员1'})
        self.run_tasks(renamer, [renamer._task(renamer.rows[0], 'force')], driver)
        self.assertEqual(driver.changes, [('学员1', 'py175学员1')])
        self.assertEqual(renamer.rows[0]['state'], scan.CHANGED)

    def test_float_title_without_the_name_is_not_changed(self):
        b, renamer = self.backend(1)
        driver = FakeDriver({'学员1': None})
        self.run_tasks(renamer, [renamer._task(renamer._rows[0], 'scan')], driver)
        self.assertEqual(driver.changes, [])
        self.assertEqual(renamer.rows[0]['state'], scan.NOT_FOUND)
        self.assertEqual(renamer.issueCount, 1)

    def test_duplicate_names_are_marked_but_not_blocked(self):
        b, renamer = self.backend(2)
        with b.db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO students(student_id,name,updated_at) VALUES('P2026169009A','学员1','2026-01-01T00:00:00')")
            conn.execute("INSERT OR IGNORE INTO class_roster(student_id,term_id,ordinal,name,status) VALUES('P2026169009A','',9,'学员1','已退课')")
            conn.execute("INSERT OR IGNORE INTO profiles(student_id,fields) VALUES('P2026169009A','{}')")
        self.assertTrue(renamer.reload(), renamer.notice)
        marked = [r for r in renamer._rows if r['duplicate']]
        self.assertEqual([r['student_id'] for r in marked], ['P2026169001A'])
        self.assertEqual(marked[0]['mark'], '存在重名')
        self.assertEqual(renamer.duplicateCount, 1)
        self.assertTrue(renamer.start(['P2026169001A']), renamer.notice)

    def test_one_failure_does_not_stop_the_round(self):
        b, renamer = self.backend(3)
        driver = FakeDriver({'学员1': '学员1/新生', '学员2': '学员2/新生', '学员3': '学员3/新生'},
                            fail_with={'学员2/新生': '备注输入框核验失败'})
        self.run_tasks(renamer, [renamer._task(r, 'scan') for r in renamer._rows], driver)
        self.assertEqual([c[0] for c in driver.changes], ['学员1/新生', '学员2/新生', '学员3/新生'])
        states = {r['name']: r['state'] for r in renamer.rows}
        self.assertEqual(states, {'学员1': scan.CHANGED, '学员2': scan.FAILED, '学员3': scan.CHANGED})
        self.assertEqual(renamer.pendingCount, 1)
        self.assertIn('备注输入框核验失败', next(r['detail'] for r in renamer.rows if r['name'] == '学员2'))

    def test_skip_marks_a_row_and_keeps_it_out_of_the_next_round(self):
        b, renamer = self.backend(2)
        self.assertTrue(renamer.skip('P2026169002A'), renamer.notice)
        self.assertEqual([r['student_id'] for r in renamer._rows if scan.needs_work(r['state'])],
                         ['P2026169001A'])
        self.assertTrue(renamer.reload())
        self.assertEqual(renamer.rows[-1]['state'], scan.SKIPPED)

    def test_start_refuses_without_a_prefix_or_pending_rows(self):
        b, renamer = self.backend(1)
        renamer._prefix = ''
        self.assertFalse(renamer.start())
        self.assertIn('前缀', renamer.notice)
        renamer._prefix = 'py175'
        self.assertTrue(renamer.skip('P2026169001A'))
        self.assertFalse(renamer.start())
        self.assertIn('没有需要处理的学员', renamer.notice)

    def test_f11_pause_and_stop_are_wired(self):
        b, renamer = self.backend(1)
        with patch('app.send_controller.F11Hotkey.start') as hotkey, patch('app.send_controller.F11Hotkey.close'):
            renamer._driver_factory = lambda: FakeDriver({'学员1': '学员1/新生'})
            self.assertTrue(renamer.start(), renamer.notice)
            hotkey.assert_called_once()
            renamer.pause()
            self.assertTrue(renamer.pauseRequested)
            self.assertTrue(renamer._worker.pause_requested)
            renamer._on_paused()
            self.assertTrue(renamer.isPaused)
            renamer.resume()
            self.assertFalse(renamer.pauseRequested)
            self.assertFalse(renamer.isPaused)
            renamer.stop()
            self.assertTrue(renamer._worker.stop_requested)
            self.assertTrue(renamer._worker.wait(10000))
            for _ in range(200):
                if not renamer.active:
                    break
                self.app.processEvents()
        self.assertFalse(renamer.active)


class RemarkDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def driver(self, titles, errors=None):
        sender = FakeSender(titles, errors)
        return sender, RemarkDriver(sender, options={'wait': 0.1, 'timeout': 0.5})

    def test_search_uses_the_name_and_returns_the_float_title(self):
        sender, driver = self.driver({'示例学员': '示例学员/新生'})
        with patch('app.wecom_renamer.time.sleep'):
            self.assertEqual(driver.read_remark('示例学员'), '示例学员/新生')
        self.assertEqual(sender.searched, ['示例学员'], '搜索关键字必须是姓名')
        self.assertIn(('ctrl', 'w'), [c.args for c in sender.keys.hotkey.call_args_list])

    def test_unrelated_float_title_returns_none(self):
        sender, driver = self.driver({'示例学员': '李明'})
        with patch('app.wecom_renamer.time.sleep'):
            self.assertIsNone(driver.read_remark('示例学员'))

    def test_search_failure_is_reported_without_typing(self):
        sender, driver = self.driver({}, {'示例学员': '联系人浮窗标题不匹配，未发送'})
        with patch('app.wecom_renamer.time.sleep'):
            with self.assertRaises(RuntimeError):
                driver.read_remark('示例学员')

    def test_change_remark_is_skipped_when_already_correct(self):
        sender, driver = self.driver({})
        with patch('app.wecom_renamer.load_change_remark') as changer:
            self.assertEqual(driver.change_remark('py175示例学员', 'py175示例学员'), 'py175示例学员')
        changer.assert_not_called()

    def test_change_remark_calls_the_remark_entry_point(self):
        sender, driver = self.driver({})
        result = Mock(success=True, message='已修改')
        with patch('app.wecom_renamer.load_change_remark', return_value=Mock(return_value=result)) as changer:
            self.assertEqual(driver.change_remark('示例学员/新生', 'py175示例学员'), 'py175示例学员')
        self.assertEqual(changer.return_value.call_args.args, ('示例学员/新生', 'py175示例学员'))

    def test_failed_change_raises_instead_of_reporting_success(self):
        sender, driver = self.driver({})
        result = Mock(success=False, message='顶部备注名定位不唯一')
        with patch('app.wecom_renamer.load_change_remark', return_value=Mock(return_value=result)):
            with self.assertRaises(RemarkRenameError):
                driver.change_remark('示例学员/新生', 'py175示例学员')

    def test_change_entry_point_rejects_an_empty_original_remark(self):
        try:
            change = load_change_remark()
        except RemarkRenameError as exc:
            self.skipTest(f'本机缺少企微自动化依赖：{exc}')
        with self.assertRaises(Exception):
            change('', 'py175示例学员', dry_run=True)


if __name__ == '__main__':
    unittest.main()
