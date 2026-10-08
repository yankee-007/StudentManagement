"""Temporary rosters and simulated WeCom only; no desktop or real students."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.database import Database
from app.profile_wechat import (WechatVerificationWorker, matches_contact,
                                FOUND, NOT_FOUND, REVIEW, FAILED, SKIPPED, PENDING)
from app.wecom_sender import ContactNotFoundError
from tests.profile_fixtures import insert_profile


class FakeDriver:
    def __init__(self, titles=None):
        self.titles = titles or {}
        self.sender = Mock()
        self.reads = []

    def read_remark(self, name):
        self.reads.append(name)
        value = self.titles.get(name)
        if isinstance(value, Exception):
            raise value
        return value


class ProfileWechatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.backend = Backend(Path(self.folder.name) / 'test.db')
        self.profiles = self.backend.profilesModule
        self.verifier = self.profiles.wechatVerifier

    def seed(self, rows):
        with self.backend.db.connect() as conn:
            for ordinal, (sid, name, status, wechat) in enumerate(rows, 1):
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (sid, name, '2026-10-08'))
                insert_profile(conn, sid, name, ordinal, {'微信': wechat, '所在地区': '测试地区'})
                conn.execute('UPDATE class_roster SET status=? WHERE student_id=?', (status, sid))
        self.profiles.refresh()

    def run_round(self, driver):
        self.assertTrue(self.verifier.prepare(), self.verifier.notice)
        worker = WechatVerificationWorker(list(self.verifier.tableModel.rows), lambda: driver)
        worker.checked.connect(self.verifier._checked)
        worker.run()
        return self.verifier.tableModel.rows

    def test_unfiltered_defaults_to_non_retired_and_keeps_existing_yes_in_scope(self):
        self.seed([('1', '示例甲', '在读', '否'), ('2', '示例乙', '', '是'),
                   ('3', '退课学员', '已退课', '否'), ('4', '補位学员', '在读', '否')])
        with self.backend.db.connect() as conn:
            conn.execute("UPDATE class_roster SET is_placeholder=1 WHERE student_id='4'")
        self.profiles.refresh()
        rows = self.run_round(FakeDriver({'示例甲': '示例甲/新生', '示例乙': '示例乙'}))
        self.assertEqual([r['student_id'] for r in rows], ['1', '2'])
        self.assertEqual([r['state'] for r in rows], [FOUND, FOUND])
        self.assertEqual(self.verifier.updated, 1)
        self.assertEqual(self.backend.repo.get('3')['profile:微信'], '否')

    def test_search_and_filters_use_current_sorted_matching_scope(self):
        self.seed([('1', '示例甲', '在读', '否'), ('2', '示例乙', '在读', '是'),
                   ('3', '示例丙', '在读', '否')])
        self.profiles.setColumnFilter('profile:微信', 'values', ['否'], '')
        self.profiles.sortField('student_id', True)
        self.verifier.prepare()
        self.assertEqual([r['student_id'] for r in self.verifier.tableModel.rows], ['3', '1'])
        self.profiles.search('示例甲')
        driver = FakeDriver({'示例甲': '示例甲', '示例丙': '示例丙'})
        rows = self.run_round(driver)
        self.assertEqual([r['student_id'] for r in rows], ['1'])
        self.assertEqual(driver.reads, ['示例甲'])
        self.assertEqual(self.backend.repo.get('3')['profile:微信'], '否')

    def test_explicit_filtered_retired_student_can_be_verified(self):
        self.seed([('1', '在读学员', '在读', '否'), ('2', '退课学员', '已退课', '否')])
        self.profiles.setColumnFilter('roster_status', 'values', ['已退课'], '')
        rows = self.run_round(FakeDriver({'退课学员': '退课学员'}))
        self.assertEqual([r['student_id'] for r in rows], ['2'])
        self.assertEqual(rows[0]['state'], FOUND)
        self.assertEqual(self.backend.repo.get('2')['profile:微信'], '是')
        self.assertEqual(self.backend.repo.get('1')['profile:微信'], '否')

    def test_empty_filtered_scope_does_not_fall_back_to_the_class(self):
        self.seed([('1', '示例甲', '在读', '否')])
        self.profiles.search('不存在的姓名')
        self.assertTrue(self.verifier.prepare())
        self.assertEqual(self.verifier.total, 0)
        with patch.object(self.verifier, '_driver_factory') as factory:
            self.assertFalse(self.verifier.start())
            factory.assert_not_called()

    def test_stale_frozen_rows_are_excluded_and_changed_query_rebuilds_preview(self):
        self.seed([('1', '示例甲', '在读', '否'), ('2', '示例乙', '在读', '否')])
        self.profiles.setColumnFilter('profile:微信', 'values', ['否'], '')
        self.profiles.autoSaveField('1', '微信', '是')
        driver = FakeDriver({'示例乙': '示例乙'})
        self.run_round(driver)
        self.assertEqual(driver.reads, ['示例乙'])
        self.assertTrue(self.verifier.prepare())
        self.assertEqual(self.verifier.completed, 1, '值变化保留上轮结果')
        self.profiles.clearFilters()
        self.assertTrue(self.verifier.prepare())
        self.assertEqual(self.verifier.completed, 0)
        self.assertEqual(self.verifier.total, 2)

    def test_only_wechat_changes_and_filter_freeze_and_selection_are_preserved(self):
        self.seed([('1', '示例甲', '在读', '否'), ('2', '示例乙', '在读', '否')])
        self.profiles.setColumnFilter('profile:微信', 'values', ['否'], '')
        selected = self.profiles.selected['_record_key']
        self.run_round(FakeDriver({'示例甲': '示例甲', '示例乙': None}))
        self.assertEqual(self.profiles.visibleCount, 2)
        self.assertEqual(self.profiles.staleCount, 1)
        self.assertEqual(self.profiles.selected['_record_key'], selected)
        self.assertEqual(self.backend.repo.get('1')['profile:所在地区'], '测试地区')
        self.assertEqual(next(f['value'] for f in self.profiles.fields if f['label'] == '微信'), '是')
        self.assertEqual(self.backend.repo.get('2')['profile:微信'], '否')

    def test_not_found_review_and_failure_preserve_original_values_and_continue(self):
        self.seed([('1', '示例甲', '', '是'), ('2', '示例乙', '', ''),
                   ('3', '示例丙', '', '否'), ('4', '示例丁', '', '否')])
        rows = self.run_round(FakeDriver({'示例甲': ContactNotFoundError('未打开联系人浮窗'),
                                        '示例乙': '其他示例乙', '示例丙': RuntimeError('窗口焦点已变化'),
                                        '示例丁': '示例丁'}))
        self.assertEqual([r['state'] for r in rows], [NOT_FOUND, REVIEW, FAILED, FOUND])
        self.assertEqual([self.backend.repo.get(str(i))['profile:微信'] for i in range(1, 5)], ['是', '', '否', '是'])

    def test_local_remark_does_not_count_without_live_verification(self):
        self.seed([('1', '示例甲', '', '否')])
        with self.backend.db.connect() as conn:
            conn.execute("INSERT INTO student_contacts VALUES('1','py175示例甲')")
        self.run_round(FakeDriver())
        self.assertEqual(self.backend.repo.get('1')['profile:微信'], '否')

    def test_duplicate_or_invalid_names_are_reviewed_without_search(self):
        self.seed([('1', '示例甲', '', '否'), ('2', '示例甲', '已退课', '否'),
                   ('3', '', '', '否')])
        driver = FakeDriver({'示例甲': '示例甲'})
        rows = self.run_round(driver)
        self.assertEqual(driver.reads, [])
        self.assertEqual([r['state'] for r in rows], [REVIEW, REVIEW])

    def test_exact_known_prefix_legacy_and_saved_remark_matches(self):
        task = {'name': '张三', 'prefixes': ['py175', '测试前缀'], 'remark': 'VIP-张三'}
        for title in ('张三', '张三/新生', 'py175张三', '测试前缀张三', 'VIP-张三'):
            self.assertTrue(matches_contact(task, title), title)
        for title in ('李张三', '张三丰', 'py169张三', '张三同学群', '张三、李四', ''):
            self.assertFalse(matches_contact(task, title), title)

    def test_status_or_identity_changes_before_result_do_not_write(self):
        self.seed([('1', '示例甲', '', '否'), ('2', '示例乙', '', '否')])
        self.verifier.prepare()
        with self.backend.db.connect() as conn:
            conn.execute("UPDATE class_roster SET status='已退课' WHERE student_id='1'")
            conn.execute("UPDATE class_roster SET name='改名学员' WHERE student_id='2'")
        for sid in ('1', '2'):
            self.verifier._checked(sid, FOUND, '示例甲', '')
        self.assertEqual([r['state'] for r in self.verifier.tableModel.rows], [SKIPPED, SKIPPED])
        self.assertEqual(self.verifier.updated, 0)

    def test_stale_class_context_cannot_start_or_write(self):
        self.seed([('1', '示例甲', '', '否')])
        self.verifier.prepare()
        original = self.backend.repo
        self.backend.db = Database(Path(self.folder.name) / 'other.db')
        with patch.object(self.verifier, '_driver_factory') as factory:
            self.assertFalse(self.verifier.start())
            factory.assert_not_called()
        self.verifier._checked('1', FOUND, '示例甲', '')
        self.assertEqual(original.get('1')['profile:微信'], '否')
        self.assertEqual(self.verifier.tableModel.rows[0]['state'], FAILED)

    def test_save_failure_is_visible_and_does_not_count_as_found(self):
        self.seed([('1', '示例甲', '', '否')])
        with patch.object(self.backend.repo, 'update_profile_field', side_effect=RuntimeError('测试写入失败')):
            rows = self.run_round(FakeDriver({'示例甲': '示例甲'}))
        self.assertEqual(rows[0]['state'], FAILED)
        self.assertIn('测试写入失败', rows[0]['detail'])
        self.assertEqual(self.verifier.updated, 0)

    def test_all_classes_empty_roster_and_other_automation_block_start(self):
        self.profiles.setAllClasses(True)
        self.assertFalse(self.verifier.prepare())
        self.profiles.setAllClasses(False)
        self.assertTrue(self.verifier.prepare())
        self.assertFalse(self.verifier.start())
        self.seed([('1', '示例甲', '', '否')])
        self.verifier.prepare()
        with patch.object(self.verifier, '_driver_factory') as factory:
            self.backend.remarkRenamer._worker = Mock()
            self.assertFalse(self.verifier.start())
            self.backend.remarkRenamer._worker = None
            self.backend.contactOpener._worker = Mock()
            self.assertFalse(self.verifier.start())
            self.backend.contactOpener._worker = None
            factory.assert_not_called()

    def wait_until(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertTrue(condition())

    def test_pause_stop_and_mutual_exclusion(self):
        self.seed([('1', '示例甲', '', '否'), ('2', '示例乙', '', '否'), ('3', '示例丙', '', '否')])
        driver = FakeDriver({'示例甲': '示例甲', '示例乙': '示例乙'})
        entered, release = threading.Event(), threading.Event()
        read = driver.read_remark

        def blocked_read(name):
            entered.set()
            release.wait(5)
            return read(name)

        driver.read_remark = blocked_read
        self.verifier.prepare()
        with patch.object(self.verifier, '_driver_factory', return_value=driver), patch.object(self.verifier._hotkey, 'start'), patch.object(self.verifier._hotkey, 'close'):
            self.assertTrue(self.verifier.start())
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.backend.workflow.send_busy)
                self.profiles.setAllClasses(True)
                self.assertFalse(self.profiles.allClasses)
                self.assertFalse(self.backend.contactOpener.openContact(self.profiles.selected['_record_key'], ''))
                self.backend.workflow.sender._test_mode = True
                self.backend.workflow.sender._preview = [{}]
                self.assertFalse(self.backend.workflow.sender.start())
                self.backend.groupCenter._preview = [{}]
                self.assertFalse(self.backend.groupCenter.start())
                self.verifier.togglePause()
                release.set()
                self.wait_until(lambda: self.verifier.isPaused)
                self.assertEqual(driver.reads, ['示例甲'])
                self.verifier.stop()
                self.wait_until(lambda: not self.verifier.active)
                self.assertEqual(self.verifier.completed, 1)
                self.assertEqual(self.verifier.tableModel.rows[1]['state'], PENDING)
                self.assertEqual(self.backend.repo.get('1')['profile:微信'], '是')
                self.assertFalse(self.backend.workflow.send_busy)
            finally:
                release.set()
                self.verifier.shutdown()

    def test_shutdown_delivers_the_last_completed_contact_before_exit(self):
        self.seed([('1', '示例甲', '', '否')])
        driver = FakeDriver({'示例甲': '示例甲'})
        self.verifier.prepare()
        with patch.object(self.verifier, '_driver_factory', return_value=driver), patch.object(self.verifier._hotkey, 'start'), patch.object(self.verifier._hotkey, 'close'):
            self.assertTrue(self.verifier.start())
            self.assertTrue(self.verifier._worker.wait(3000))
            # No event processing has delivered the queued result yet.
            self.assertEqual(self.backend.repo.get('1')['profile:微信'], '否')
            self.verifier.shutdown()
            self.assertEqual(self.backend.repo.get('1')['profile:微信'], '是')
            self.assertFalse(self.verifier.active)


if __name__ == '__main__':
    unittest.main()
