import unittest
from app.table_query import matches, next_cursor, sort_value
from app.qt_models import DictTableModel
from PySide6.QtTest import QAbstractItemModelTester


class TableQueryTests(unittest.TestCase):
    def test_filters_and_numeric_order(self):
        self.assertTrue(matches({'courses':'1,3'}, {'courses':{'mode':'contains','value':'1'}}))
        self.assertFalse(matches({'courses':'10,11'}, {'courses':{'mode':'contains','value':'1'}}))
        self.assertTrue(matches({'feedback':''}, {'feedback':{'mode':'empty','value':''}}))
        self.assertFalse(matches({'feedback':''}, {'feedback':{'mode':'notempty','value':''}}))
        self.assertFalse(matches({'name':'甲','reply_state':'已回复'},{'name':{'mode':'exact','value':'甲'},'reply_state':{'mode':'exact','value':'未回复'}}))
        rows=[{'missing_total':v} for v in ['10/1','2/10','2/3']]
        self.assertEqual([r['missing_total'] for r in sorted(rows,key=lambda r:sort_value(r,'missing_total'))],['2/3','2/10','10/1'])
        rows=[{'courses':v} for v in ['10','2','1,2','']]
        self.assertEqual([r['courses'] for r in sorted(rows,key=lambda r:sort_value(r,'courses'))],['','2','10','1,2'])

    def test_cursor_keeps_processing_order_after_reevaluation(self):
        key=lambda r: r['student_id']
        rows=[{'student_id':s} for s in ('1','2','3','4')]
        # 原行仍在：保持不动。
        self.assertEqual(next_cursor(rows,key,'2',[r['student_id'] for r in rows])['student_id'],'2')
        # 原行被筛掉：落到原顺序中的下一条，而不是队首。
        remaining=[{'student_id':s} for s in ('1','3','4')]
        self.assertEqual(next_cursor(remaining,key,'2',['1','2','3','4'])['student_id'],'3')
        # 原行是最后一条：退到仍存在的前一条。
        remaining=[{'student_id':s} for s in ('1','3')]
        self.assertEqual(next_cursor(remaining,key,'4',['1','3','4'])['student_id'],'3')
        # 全部被筛掉：返回空选择。
        self.assertEqual(next_cursor([],key,'2',['2']),{})
        # 没有原记录时退回第一行。
        self.assertEqual(next_cursor(remaining,key,'',[])['student_id'],'1')

    def test_incremental_reorder(self):
        model=DictTableModel([('name','姓名')])
        tester=QAbstractItemModelTester(model,QAbstractItemModelTester.FailureReportingMode.Warning)
        model.set_rows([{'student_id':str(i),'name':str(i)} for i in range(5)])
        resets=[]
        model.modelReset.connect(lambda:resets.append(1))
        expected=[{'student_id':str(i),'name':'new'} for i in [3,1,7,0]]
        model.reconcile_rows(expected)
        self.assertEqual(model.rows,expected)
        self.assertEqual(resets,[])
