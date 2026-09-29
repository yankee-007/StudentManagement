import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from unittest.mock import patch

from app.group_dispatch import GroupStore
from tests.test_business_logic import seeded


class GroupInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_save_options_persists_and_invalidates_preview_without_starting_driver(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createCustom('设置测试','测试号|测试消息'))
            list_id=group.selected['id']
            self.assertTrue(group.prepare('旧前缀',{}))
            self.assertTrue(group.preview)
            self.assertIsNotNone(group._confirmation)
            selection_events=[];preview_events=[];status_events=[]
            group.selectionChanged.connect(lambda:selection_events.append(True))
            group.previewChanged.connect(lambda:preview_events.append(True))
            group.statusChanged.connect(lambda:status_events.append(True))

            options={'wait':1.25,'confirm_send':False}
            self.assertTrue(group.saveOptions(list_id,'新前缀',options))
            self.assertEqual(group.status,'发送设置已保存，请重新预览')
            self.assertEqual(group.preview,[])
            self.assertIsNone(group._confirmation)
            self.assertTrue(selection_events and preview_events and status_events)
            self.assertEqual(group.selected['prefix'],'新前缀')
            self.assertEqual(group.selected['options']['wait'],1.25)
            reopened=GroupStore(group.store.path)
            saved=reopened.get(list_id)
            self.assertEqual(saved['prefix'],'新前缀')
            self.assertEqual(saved['options']['wait'],1.25)
            self.assertFalse(saved['options']['confirm_send'])

            with patch('app.wecom_sender.WeComSender') as driver_factory:
                self.assertFalse(group.start())
                driver_factory.assert_not_called()

    def test_save_options_rejects_invalid_stale_and_active_without_persisting(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createCustom('拒绝测试','测试号|测试消息'))
            list_id=group.selected['id']
            original=group.store.get(list_id)

            self.assertFalse(group.saveOptions(list_id,'无效',{'wait':-1}))
            self.assertIn('设置保存失败：',group.status)
            self.assertEqual(group.store.get(list_id)['prefix'],original['prefix'])
            self.assertFalse(group.saveOptions(list_id+999,'过期',{}))
            self.assertEqual(group.store.get(list_id)['prefix'],original['prefix'])

            group._worker=object()
            self.assertFalse(group.saveOptions(list_id,'运行中',{}))
            group._worker=None
            self.assertEqual(group.store.get(list_id)['prefix'],original['prefix'])

    def test_column_summaries_count_personal_protected_and_mixed_types(self):
        with seeded(1) as backend, tempfile.TemporaryDirectory() as folder:
            group=backend.groupCenter
            self.assertTrue(group.createCustom('列统计测试','甲|文字一\n乙|文字二\n丙|文字三'))
            list_id=group.selected['id']
            rows=group.store.rows(list_id)
            self.assertEqual(group.messageColumns,[{'index':0,'label':'话术1'}])

            protected_id=rows[2]['id']
            with group.store.connect() as conn:
                conn.execute("UPDATE recipients SET state='结果待确认' WHERE id=?",(protected_id,))
            file_path=Path(folder)/'消息.txt'
            file_path.write_text('附件',encoding='utf-8')
            self.assertTrue(group.saveRecipientField(list_id,rows[0]['id'],0,{'type':'file','path':str(file_path)}))

            summary=group.columnInfo(0,True)
            self.assertEqual(summary['count'],2)
            self.assertEqual(group.columnInfo(0,False)['count'],1)
            self.assertTrue(summary['mixed'])
            self.assertEqual(summary['personalCount'],1)
            self.assertEqual(summary['protectedCount'],1)
            self.assertEqual(group.messageColumns,[{'index':0,'label':'消息1（文字/文件）'}])

            notifications=[]
            group.modelInfoChanged.connect(lambda:notifications.append(True))
            with group.store.connect() as conn:
                conn.execute("UPDATE recipients SET state='已发送' WHERE id=?",(protected_id,))
            group._reload_snapshot()
            self.assertTrue(group.saveRecipientField(list_id,rows[1]['id'],0,{'type':'file','path':str(file_path)}))
            self.assertTrue(notifications)
            self.assertEqual(group.messageColumns,[{'index':0,'label':'文件1'}])


if __name__=='__main__':
    unittest.main()
