import tempfile
import unittest
import json
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

    def test_default_row_updates_atomically_and_preserves_personal_and_protected(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createStructured('统一行','甲\n乙\n丙\n丁',[
                dict(type='text',text='{姓名}-原消息'),dict(type='text',text='第二条')]))
            list_id=group.selected['id'];rows=group.rows
            self.assertTrue(group.saveRecipientField(list_id,rows[0]['id'],0,dict(type='text',text='甲的个人消息')))
            with group.store.connect() as conn:
                conn.execute("UPDATE recipients SET state='已发送' WHERE id=?",(rows[2]['id'],))
                conn.execute("UPDATE recipients SET state='结果待确认' WHERE id=?",(rows[3]['id'],))
            group.refresh()
            self.assertEqual(group.statistics,dict(success=1,failed=0,pending=2,uncertain=1))
            self.assertTrue(group.prepare('前缀',{}))
            fields=group.defaultFields
            fields[0]['value']='{姓名}-新消息';fields[1]['value']='更新第二条'
            self.assertTrue(group.saveDefaultRow(list_id,group.contentRevision,fields,False),group.status)
            content=[json.loads(r['content']) for r in group.rows]
            self.assertEqual(content[0][0]['text'],'甲的个人消息')
            self.assertEqual(content[1][0]['text'],'乙-新消息')
            self.assertEqual([r[1]['text'] for r in content[:2]],['更新第二条']*2)
            self.assertEqual([r[1]['text'] for r in content[2:]],['第二条']*2)
            self.assertEqual(group.preview,[])
            self.assertFalse(group.start())
            self.assertTrue(group.saveDefaultRow(list_id,group.contentRevision,group.defaultFields,True),group.status)
            self.assertEqual(json.loads(group.rows[0]['content'])[0]['text'],'甲-新消息')

    def test_default_row_failure_preserves_all_content_template_and_confirmation(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createStructured('原子失败','甲\n乙',[dict(type='text',text='原消息')]))
            list_id=group.selected['id'];rows=group.rows;template=group.selected['content_template']
            self.assertTrue(group.prepare('前缀',{}))
            fields=group.defaultFields
            fields[0]['value']='第一条改动'
            fields.append(dict(sourceIndex=-1,type='text',value='{不存在的变量}'))
            self.assertFalse(group.saveDefaultRow(list_id,group.contentRevision,fields,False))
            self.assertEqual(group.rows,rows)
            self.assertEqual(group.selected['content_template'],template)
            self.assertTrue(group.preview)
            fields[-1]['value']=''
            self.assertFalse(group.saveDefaultRow(list_id,group.contentRevision,fields,False))
            self.assertEqual(group.rows,rows)

    def test_default_row_mixed_legacy_and_personal_variants_survive_other_changes(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createCustom('旧名单','甲|甲的话术\n乙|乙的话术'))
            self.assertTrue(group.defaultFields[0]['mixed'])
            fields=group.defaultFields
            fields.append(dict(sourceIndex=-1,type='text',value='{姓名}-新增'))
            self.assertTrue(group.saveDefaultRow(group.selected['id'],group.contentRevision,fields,False),group.status)
            content=[json.loads(r['content']) for r in group.rows]
            self.assertEqual([r[0]['text'] for r in content],['甲的话术','乙的话术'])
            self.assertEqual([r[1]['text'] for r in content],['甲-新增','乙-新增'])
            self.assertEqual(group.selected['content_template'],[])
            fields=group.defaultFields
            fields[0]['value']='统一-{姓名}'
            self.assertTrue(group.saveDefaultRow(group.selected['id'],group.contentRevision,fields,False),group.status)
            self.assertEqual([json.loads(r['content'])[0]['text'] for r in group.rows],['统一-甲','统一-乙'])

    def test_default_row_reorder_delete_and_names_only(self):
        with seeded(1) as backend, tempfile.TemporaryDirectory() as folder:
            group=backend.groupCenter;file=Path(folder)/'附件.txt';file.write_text('虚构附件',encoding='utf-8')
            self.assertTrue(group.createStructured('顺序','甲\n乙',[
                dict(type='text',text='第一条'),dict(type='file',path=str(file)),dict(type='text',text='第三条')]))
            fields=group.defaultFields
            self.assertTrue(group.saveDefaultRow(group.selected['id'],group.contentRevision,[fields[1],fields[0]],False))
            self.assertEqual([i['type'] for i in json.loads(group.rows[0]['content'])],['file','text'])
            self.assertTrue(group.saveDefaultRow(group.selected['id'],group.contentRevision,[],False))
            self.assertEqual(group.pendingFieldCount,0)
            self.assertFalse(group.prepare('前缀',{}))
            self.assertTrue(group.saveDefaultRow(group.selected['id'],group.contentRevision,[dict(sourceIndex=-1,type='text',value='重新配置-{姓名}')],False))
            self.assertTrue(group.prepare('前缀',{}))
            self.assertEqual(group.preview[1]['content'][0]['text'],'重新配置-乙')

    def test_default_row_stale_list_revision_and_active_guards(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createStructured('防陈旧','甲',[dict(type='text',text='原消息')]))
            list_id=group.selected['id'];revision=group.contentRevision;fields=group.defaultFields
            fields[0]['value']='未应用的草稿'
            self.assertTrue(group.saveRecipientField(list_id,group.rows[0]['id'],0,dict(type='text',text='另一个编辑器')))
            self.assertFalse(group.saveDefaultRow(list_id,revision,fields,False))
            self.assertIn('草稿仍保留',group.status)
            group._worker=object()
            self.assertFalse(group.saveDefaultRow(list_id,group.contentRevision,fields,False));group._worker=None
            self.assertTrue(group.createStructured('另一名单','乙',[dict(type='text',text='另一消息')]))
            self.assertFalse(group.saveDefaultRow(list_id,group.contentRevision,fields,False))
            self.assertEqual(json.loads(group.rows[0]['content'])[0]['text'],'另一消息')

    def test_default_fields_belong_to_selected_list_before_table_refresh(self):
        with seeded(1) as backend:
            group=backend.groupCenter
            self.assertTrue(group.createStructured('三条消息','甲',[
                dict(type='text',text='一'),dict(type='text',text='二'),dict(type='text',text='三')]))
            observed=[]
            group.selectionChanged.connect(lambda:observed.append((group.selected['title'],group.defaultFields)))
            self.assertTrue(group.createCustom('单条消息','乙|单条默认消息'))
            self.assertEqual(observed[-1],('单条消息',[dict(sourceIndex=0,type='text',value='单条默认消息',mixed=False)]))
            group.selectList(1)
            self.assertEqual([f['value'] for f in observed[-1][1]],['一','二','三'])


if __name__=='__main__':
    unittest.main()
