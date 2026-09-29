import unittest
from app.table_query import matches, sort_value
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
