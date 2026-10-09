import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from app.backend import Backend
from app.database import Database
from app.campaigns import EXPORT_COLUMNS
from tests.profile_fixtures import insert_profile


class WorkbenchRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'first.db'
        self.backend=Backend(self.path)
        with self.backend.db.connect() as conn:
            for sid,name in [('1','一号'),('2','二号'),('3','三号'),('4','四号')]:
                conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',(sid,name,'2026-09-24'))
                insert_profile(conn,sid,name,int(sid),{'微信':'是'})
        self.w=self.backend.workflow
        self.w.createBatch()
        self.batch=self.w._batch

    def test_unsent_feedback_and_historical_guard(self):
        self.assertEqual(self.w.store.rows(self.batch,'1')[0]['reply_state'],'待反馈')
        self.assertTrue(self.w.saveDraft('1','待整理'))
        self.assertTrue(self.w.submit('已经回复'))
        self.assertEqual(self.w.store.rows(self.batch,'1')[0]['reply_state'],'已回复')
        self.w.createBatch()
        with self.assertRaises(ValueError):self.w.store.draft(self.batch,'2','历史草稿')
        with self.assertRaises(ValueError):self.w.store.submit(self.batch,'2','历史反馈')
        with self.assertRaises(ValueError):self.w.store.mark_unreplied(self.batch,['2'])

    def test_bulk_visible_scope_and_unicode_draft(self):
        self.w.saveDraft('2','已有内容')
        self.w.saveDraft('3','\u3000\u2003')
        self.assertEqual(self.w.store.mark_unreplied(self.batch,['1','2','3']),2)
        states={r['student_id']:r['reply_state'] for r in self.w.store.rows(self.batch)}
        self.assertEqual(states,{'1':'未回复','2':'待反馈','3':'未回复','4':'待反馈'})
        self.w.filterRows('pending','4')
        self.w.markUnreplied()
        self.assertEqual(self.w.store.rows(self.batch,'4')[0]['reply_state'],'未回复')
        self.assertEqual(self.w.store.rows(self.batch,'2')[0]['reply_state'],'待反馈')

    def test_layout_filters_export_preferences_and_reopen(self):
        self.assertFalse(next(f for f in self.w.managedFields if f['field_id']=='student_id')['show_column'])
        self.assertTrue(self.w.setFieldVisible('student_id',True))
        self.assertTrue(self.w.moveField('name',0))
        self.assertEqual(self.w.columnKeys[0],'name')
        self.w.sortField('name',True)
        self.assertEqual(self.w.sortColumnIndex,0)
        self.w.setColumnFilter('name','values',['一号','二号'],'')
        self.assertEqual(self.w.visibleCount,2)
        info=self.w.columnFilterInfo(self.w.columnKeys.index('name'))
        self.assertEqual(sum(o['count'] for o in info['options']),4)
        self.w.setColumnFilter('reply_state','values',[],'')
        self.assertEqual(self.w.visibleCount,0)
        info=self.w.columnFilterInfo(self.w.columnKeys.index('name'))
        self.assertEqual(sum(o['count'] for o in info['options']),0)
        self.w.setColumnFilter('reply_state','clear',[],'')
        self.assertEqual(self.w.visibleCount,2)
        order=[f['key'] for f in self.w.exportFields]
        order.reverse()
        self.assertTrue(self.w.saveExportPreferences(order,['name','reply_state']))
        self.assertEqual([f['key'] for f in self.w.exportFields],order)
        self.assertEqual([f['key'] for f in self.w.exportFields if f['selected']],['reply_state','name'])
        from openpyxl import load_workbook
        output=Path(self.folder.name)/'ordered.xlsx'
        self.w.export_to_path(['reply_state','name'],str(output))
        book=load_workbook(output,read_only=True)
        self.assertEqual(next(book.active.values),('反馈状态','姓名'))
        book.close()
        reopened=Backend(self.path).workflow
        self.assertEqual(reopened.columnKeys[0],'name')
        self.assertTrue(next(f for f in reopened.managedFields if f['field_id']=='student_id')['show_column'])
        self.assertEqual([f['key'] for f in reopened.exportFields],order)
        self.assertEqual([f['key'] for f in reopened.exportFields if f['selected']],['reply_state','name'])
        other=Path(self.folder.name)/'second.db'
        Database(other)
        self.w._classes.append({'name':'第二班','path':str(other)})
        self.w.selectClass(1)
        self.assertEqual(self.w.columnKeys[0],EXPORT_COLUMNS[0][0])
        self.assertFalse(next(f for f in self.w.managedFields if f['field_id']=='student_id')['show_column'])

    def test_recipient_and_details_follow_view(self):
        self.w.filterRows('all','1')
        self.assertEqual(self.w.recipientKeys,[json.dumps([str(self.path),self.batch,'1'],ensure_ascii=False)])
        detail=self.w.detailFieldsFor(self.w.selected)
        self.assertEqual([d['key'] for d in detail],[f['field_id'] for f in self.w.managedFields if f['show_column']])
        self.assertNotIn('student_id',[d['key'] for d in detail])
        self.assertEqual(next(d['value'] for d in detail if d['key']=='name'),'一号')


    def test_previous_feedback_columns_toggle(self):
        first = self.batch
        self.w.store.save_feedback(first, '1', '第一批反馈内容')
        self.w.createBatch()
        current = self.w._batch
        self.assertNotEqual(first, current)
        # 默认不勾选：无历史反馈列
        self.assertFalse(self.w.showPreviousFeedback)
        self.assertTrue(all(not key.startswith('previous_feedback_') for key in self.w.columnKeys))
        # 勾选后：按历史催办追加一列，并填充对应批次反馈
        self.assertTrue(self.w.setShowPreviousFeedback(True))
        self.assertTrue(self.w.showPreviousFeedback)
        key = f'previous_feedback_{first}'
        self.assertIn(key, self.w.columnKeys)
        day = date.fromisoformat(next(r['created_at'][:10] for r in self.w._batches if r['id'] == first))
        self.assertEqual(dict(self.w._model.columns)[key], f'以往反馈情况（{day.month}月{day.day}号）')
        row = self.w.store.rows(current, '1')[0]
        self.w._attach_previous_feedback([row])
        self.assertEqual(row[key], '第一批反馈内容')
        self.assertIn(key, [f['field_id'] for f in self.w.managedFields])
        self.assertTrue(next(f for f in self.w.managedFields if f['field_id'] == key)['show_column'])
        # 详情字段跟随显示历史反馈列
        detail_keys = [d['key'] for d in self.w.detailFieldsFor(row)]
        self.assertIn(key, detail_keys)
        # 编辑本次反馈后单行重建不丢失历史反馈列
        self.w.reload_rows()
        self.w.selectRow(0)
        self.assertTrue(self.w.submit('本次新反馈'))
        kept = next(r for r in self.w._rows if r['student_id'] == '1')
        self.assertEqual(kept[key], '第一批反馈内容')
        # 取消勾选后列消失
        self.assertTrue(self.w.setShowPreviousFeedback(False))
        self.assertFalse(any(k.startswith('previous_feedback_') for k in self.w.columnKeys))
        self.assertTrue(all(not f['field_id'].startswith('previous_feedback_') for f in self.w.managedFields))


if __name__=='__main__':unittest.main()
