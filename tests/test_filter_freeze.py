"""ADR-007: 筛选结果集冻结，业务范围只算真正匹配的行。

Run: python -m unittest tests.test_filter_freeze -v
All data is synthetic and stored in disposable databases; no network calls.
"""
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook
from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from tests.profile_fixtures import insert_profile
from tests.test_business_logic import seeded


def workbench(folder):
    """三个虚构学员 + 一个最新批次的临时工作台（同 tests/test_workbench_revision 的建库方式）。"""
    backend = Backend(Path(folder) / 'workbench.db')
    with backend.db.connect() as conn:
        for i, name in ((1, '一号'), (2, '二号'), (3, '三号')):
            conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)', (str(i), name, '2026-09-24'))
            insert_profile(conn, str(i), name, i, {'微信': '是'})
    backend.workflow.createBatch()
    return backend


class ProfileFilterFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_edit_keeps_row_until_reapply(self):
        with seeded(3) as b:
            p = b.profilesModule
            p.setColumnFilter('profile:微信', 'values', ['是'], '')
            key = next(r['_record_key'] for r in p.tableModel.rows if r['name'] == '学员1')
            self.assertTrue(p.saveEditorField(key, '微信', '否'))
            self.assertEqual((p.visibleCount, p.matchedCount, p.staleCount), (3, 2, 1))
            self.assertEqual(p.selected['_record_key'], key)
            row = next(r for r in p.tableModel.rows if r['_record_key'] == key)
            self.assertEqual(row['profile:微信'], '否')
            self.assertTrue(row['_filter_stale'])
            self.assertEqual(len(p.recipientKeys), 2)
            self.assertNotIn(key, p.recipientKeys)
            p.reapplyFilters()
            self.assertEqual((p.visibleCount, p.matchedCount, p.staleCount), (2, 2, 0))
            self.assertNotIn(key, [r['_record_key'] for r in p.tableModel.rows])

    def test_sort_only_reorders_but_search_and_clear_reevaluate(self):
        with seeded(3) as b:
            p = b.profilesModule
            p.setColumnFilter('profile:微信', 'values', ['是'], '')
            key = next(r['_record_key'] for r in p.tableModel.rows if r['name'] == '学员1')
            self.assertTrue(p.saveEditorField(key, '微信', '否'))
            p.sortField('name', True)
            self.assertEqual((p.visibleCount, p.staleCount), (3, 1))
            self.assertEqual([r['name'] for r in p.tableModel.rows], ['学员3', '学员2', '学员1'])
            p.search('学员')
            self.assertEqual((p.visibleCount, p.staleCount), (2, 0))
            self.assertNotIn(key, [r['_record_key'] for r in p.tableModel.rows])
            p.search('')
            p.clearFilters()
            self.assertEqual((p.visibleCount, p.staleCount), (3, 0))

    def test_export_scope_excludes_stale_rows(self):
        with seeded(3) as b, tempfile.TemporaryDirectory() as folder:
            p = b.profilesModule
            p.setColumnFilter('profile:微信', 'values', ['是'], '')
            key = next(r['_record_key'] for r in p.tableModel.rows if r['name'] == '学员1')
            self.assertTrue(p.saveEditorField(key, '微信', '否'))
            output = Path(folder) / 'scope.xlsx'
            self.assertEqual(p.export_to_path(['name', 'profile:微信'], str(output)), 2)
            book = load_workbook(output, read_only=True)
            rows = list(book.active.values)
            book.close()
            self.assertEqual(rows[0], ('姓名', '微信'))
            self.assertEqual({r[0] for r in rows[1:]}, {'学员2', '学员3'})

    def test_exemption_edit_keeps_row_until_reapply(self):
        with seeded(2) as b:
            p = b.profilesModule
            p.setColumnFilter('exemption_text', 'empty', [], '')
            self.assertEqual(p.visibleCount, 2)
            key = p.selected['_record_key']
            self.assertTrue(p.saveEditorField(key, '免催日期', '2099-12-31'))
            self.assertEqual((p.visibleCount, p.matchedCount, p.staleCount), (2, 1, 1))
            self.assertEqual(p.selected['_record_key'], key)
            self.assertTrue(next(r for r in p.tableModel.rows if r['_record_key'] == key)['_filter_stale'])
            p.reapplyFilters()
            self.assertEqual((p.visibleCount, p.staleCount), (1, 0))


class WorkbenchFilterFreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_pending_view_keeps_submitted_row_and_column_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            b = workbench(folder)
            w = b.workflow
            w.filterRows('pending', '')
            self.assertEqual(w.visibleCount, 3)
            self.assertTrue(w.submit('第一条反馈'))
            self.assertEqual((w.visibleCount, w.matchedCount, w.staleCount), (3, 2, 1))
            stale = next(r for r in w.tableModel.rows if r['name'] == '一号')
            self.assertEqual(stale['reply_state'], '已回复')
            self.assertTrue(stale['_filter_stale'])
            self.assertEqual(w.selected['name'], '二号')
            self.assertEqual(len(w.recipientKeys), 2)
            w.reapplyFilters()
            self.assertEqual((w.visibleCount, w.staleCount), (2, 0))
            w.setColumnFilter('reply_state', 'values', ['待反馈'], '')
            self.assertTrue(w.submit('第二条反馈'))
            self.assertEqual((w.visibleCount, w.matchedCount, w.staleCount), (2, 1, 1))
            self.assertTrue(next(r for r in w.tableModel.rows if r['name'] == '二号')['_filter_stale'])

    def test_view_switch_reevaluates_frozen_set(self):
        with tempfile.TemporaryDirectory() as folder:
            w = workbench(folder).workflow
            w.filterRows('pending', '')
            self.assertTrue(w.submit('反馈'))
            self.assertEqual((w.visibleCount, w.staleCount), (3, 1))
            w.filterRows('all', '')
            self.assertEqual((w.visibleCount, w.staleCount), (3, 0))

    def test_bulk_unreplied_only_touches_matching_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            b = workbench(folder)
            w = b.workflow
            w.filterRows('pending', '')
            w.setColumnFilter('wechat', 'values', ['是'], '')
            # 值变化：二号不再符合列筛选，但仍在待反馈视图中且没有任何反馈。
            b.repo.update_profile_field('2', '微信', '否')
            w.reload_rows(keep_query=True)
            self.assertEqual((w.visibleCount, w.matchedCount, w.staleCount), (3, 2, 1))
            w.markUnreplied()
            states = {r['student_id']: r['reply_state'] for r in w.store.rows(w._batch)}
            self.assertEqual(states['2'], '待反馈')
            self.assertEqual((states['1'], states['3']), ('未回复', '未回复'))
            # 批量未回复也是值变化：行保留为过期，需重新应用筛选才移除。
            self.assertEqual((w.visibleCount, w.staleCount), (3, 3))
            w.reapplyFilters()
            # 重新应用后只剩同时满足“待反馈 + 微信=是”的人：一号/三号已标记未回复，二号微信已改为否。
            self.assertEqual((w.visibleCount, w.staleCount), (0, 0))

    def test_module_switch_keeps_frozen_rows_and_cursor(self):
        # 切模块只重读数据、不重新筛选：处理中的名单与高光不因切页面而改变。
        with tempfile.TemporaryDirectory() as folder:
            b = workbench(folder)
            w = b.workflow
            w.filterRows('pending', '')
            self.assertTrue(w.submit('已回复'))
            self.assertEqual((w.visibleCount, w.staleCount, w.selected['name']), (3, 1, '二号'))
            b.profilesModule.activate()
            w.activate()
            self.assertEqual((w.visibleCount, w.staleCount, w.selected['name']), (3, 1, '二号'))
            self.assertEqual(w.cursorText, '正在处理 第 2 / 3 条 · 二号')

    def test_reevaluation_moves_cursor_to_next_not_first(self):
        # 高光必须落在“下一条”，不能无声跳回队首，否则会重复处理已完成的学员。
        with seeded(4) as b:
            p = b.profilesModule
            p.setColumnFilter('profile:微信', 'values', ['是'], '')
            p.selectRow(1)
            self.assertEqual(p.selected['name'], '学员2')
            self.assertEqual(p.cursorText, '正在处理 第 2 / 4 条 · 学员2')
            b.repo.update_profile_field('P2026169002A', '微信', '否')
            p.refresh(keep_query=True)
            self.assertEqual(p.selected['name'], '学员2')
            p.reapplyFilters()
            self.assertEqual(p.selected['name'], '学员3')
            self.assertEqual(p.cursorText, '正在处理 第 2 / 3 条 · 学员3')
            p.activate()
            self.assertEqual(p.selected['name'], '学员3')


if __name__ == '__main__':
    unittest.main()
