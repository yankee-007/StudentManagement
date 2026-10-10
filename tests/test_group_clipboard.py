"""Clipboard dispatch uses fictional people, temporary stores and simulated keys."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication

from app import clipboard_payload, group_dispatch as adapter, sending_store as receipts
from app.clipboard_payload import ClipboardPayload
from app.group_dispatch import GroupStore
from app.send_controller import SendWorker
from app.send_options import normalize
from app.wecom_sender import DispatchError
from tests.test_business_logic import seeded
from tests.test_message_content import fake_driver
from tests.test_real_sending import prepare


class ClipboardPayloadTests(unittest.TestCase):
    def native(self,data,names=None):
        native=Mock()
        ids=list(data)
        native.EnumClipboardFormats.side_effect=lambda previous:ids[ids.index(previous)+1] if previous and ids.index(previous)+1<len(ids) else (ids[0] if not previous and ids else 0)
        native.GetClipboardData.side_effect=lambda fmt:data[fmt]
        native.GetClipboardFormatName.side_effect=lambda fmt:(names or {})[fmt]
        return native

    def test_native_rich_image_text_order_and_no_borrowed_handles(self):
        native=self.native({0xC001:b'<html>notice</html>',2:1234,8:b'DIB fixture',13:'本周提醒',0xC002:b'pointer'},
                           {0xC001:'HTML Format',0xC002:'Ole Private Data'})
        with patch('app.clipboard_payload._native_clipboard',return_value=native):payload=clipboard_payload.capture()
        self.assertEqual(payload.formats,((0xC001,b'<html>notice</html>'),(8,b'DIB fixture'),(13,'本周提醒')))
        self.assertEqual(payload.preview['text'],'本周提醒')
        self.assertIn('图片',payload.preview['kindLabel'])
        native.EmptyClipboard.assert_not_called()
        target=Mock();payload.restore(target);payload.restore(target)
        self.assertEqual(target.SetClipboardData.call_args_list[:3],target.SetClipboardData.call_args_list[3:])
        self.assertEqual(target.SetClipboardData.call_args_list[0].args,(0xC001,b'<html>notice</html>'))
        self.assertNotIn(2,[call.args[0] for call in native.GetClipboardData.call_args_list])

    def test_native_file_drop_and_changed_file_rejected_before_clipboard_write(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'虚构附件 %甲.txt';file.write_text('notice',encoding='utf-8')
            native=self.native({15:(str(file),)})
            with patch('app.clipboard_payload._native_clipboard',return_value=native):payload=clipboard_payload.capture()
            self.assertEqual(payload.formats[0][1][20:].decode('utf-16le'),str(file)+'\0\0')
            self.assertEqual(payload.preview['files'],[str(file)])
            target=Mock();file.write_text('new notice',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'文件已变化'):payload.restore(target)
            target.OpenClipboard.assert_not_called()
            file.unlink()
            with self.assertRaisesRegex(ValueError,'文件已失效'):payload.validate()

    def test_empty_busy_or_failed_capture_never_changes_clipboard(self):
        failed=self.native({13:'notice'});failed.GetClipboardData.side_effect=OSError('cannot read')
        for native in (self.native({}),self.native({13:'   '}),failed):
            with patch('app.clipboard_payload._native_clipboard',return_value=native),self.assertRaises(ValueError):clipboard_payload.capture()
            native.EmptyClipboard.assert_not_called()
        native=self.native({13:'notice'});native.OpenClipboard.side_effect=OSError('busy')
        with patch('app.clipboard_payload._native_clipboard',return_value=native),self.assertRaisesRegex(ValueError,'占用'):clipboard_payload.capture()
        native.CloseClipboard.assert_not_called()


class GroupClipboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_empty_messages_preview_mode_persistence_and_original_content_preserved(self):
        with seeded(1) as backend:
            g=backend.groupCenter
            self.assertTrue(g.createEmptyList('虚构剪贴板名单'))
            self.assertTrue(g.addNames(g.selected['id'],['虚构甲','虚构乙']))
            original=g.rows
            payload=ClipboardPayload([(13,'你好 {姓名}\n请提交作业')],text='你好 {姓名}\n请提交作业')
            with patch('app.group_center.clipboard_payload.capture',return_value=payload):self.assertTrue(g.prepare('测试',{'clipboard_mode':True}))
            self.assertEqual(len(g.preview),2)
            self.assertEqual(g.preview[0]['content'],[dict(type='clipboard')])
            self.assertEqual(g.clipboardPreview['text'],'你好 {姓名}\n请提交作业')
            self.assertEqual(g.rows,original)
            self.assertTrue(GroupStore(g.store.path).get(g.selected['id'])['options']['clipboard_mode'])
            self.assertTrue(g.saveOptions(g.selected['id'],'测试',{'clipboard_mode':False}))
            self.assertEqual(g.clipboardPreview,{})
            self.assertIsNone(g._clipboard_payload)
            self.assertFalse(g.prepare('测试',{}))
            self.assertIn('尚未配置消息',g.status)

    def test_invalid_clipboard_clears_previous_confirmation_and_never_starts(self):
        with seeded(1) as backend:
            g=backend.groupCenter;self.assertTrue(g.createCustom('虚构名单','甲|原消息'))
            self.assertTrue(g.prepare('测试',{}))
            with patch('app.group_center.clipboard_payload.capture',side_effect=ValueError('剪贴板没有可发送的内容')):
                self.assertFalse(g.prepare('测试',{'clipboard_mode':True}))
            self.assertFalse(g.preview);self.assertIsNone(g._confirmation)
            with patch('app.wecom_sender.WeComSender') as factory:
                self.assertFalse(g.start());factory.assert_not_called()
            self.assertEqual(g.rows[0]['message'],'原消息')

    def test_adding_names_in_clipboard_mode_does_not_require_unresolved_template(self):
        with seeded(1) as backend:
            g=backend.groupCenter
            self.assertTrue(g.createEmptyList('虚构名单'))
            with g.store.connect() as conn:
                conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps([dict(type='text',text='{欠课}')]),g.selected['id']))
            self.assertTrue(g.saveOptions(g.selected['id'],'测试',{'clipboard_mode':True}))
            self.assertTrue(g.addNames(g.selected['id'],['甲'])['no_message'])
            self.assertNotIn('请双击',g.status)
            payload=ClipboardPayload([(13,'统一通知')],text='统一通知')
            with patch('app.group_center.clipboard_payload.capture',return_value=payload):self.assertTrue(g.prepare('测试',g.selected['options']))

    def test_start_uses_frozen_payload_and_blocks_invalidated_files(self):
        with seeded(1) as backend:
            g=backend.groupCenter;self.assertTrue(g.createCustom('虚构名单','甲|原消息'))
            payload=Mock(preview=dict(kindLabel='文字',text='本轮内容',files=[]))
            with patch('app.group_center.clipboard_payload.capture',return_value=payload):self.assertTrue(g.prepare('测试',{'clipboard_mode':True}))
            with patch('app.wecom_sender.WeComSender') as factory,patch.object(g._hotkey,'start'),patch.object(g._hotkey,'close'),patch('app.group_center.SendWorker') as worker:
                payload.validate.side_effect=ValueError('文件已变化')
                self.assertFalse(g.start());factory.assert_not_called()
                payload.validate.side_effect=None
                self.assertTrue(g.start())
                self.assertIs(factory.return_value.clipboard_payload,payload)
                worker.return_value.start.assert_called_once()
                g._worker=None

    def test_sender_restores_frozen_content_after_each_contact_search(self):
        payload=ClipboardPayload([(13,'统一内容 {姓名}')],text='统一内容 {姓名}')
        for confirm in (True,False):
            with self.subTest(confirm=confirm):
                driver,state=fake_driver(dict(clipboard_mode=True,confirm_send=confirm))
                driver.clipboard_payload=payload;driver.clip=Mock()
                copied={'text':''};pasted=[];original=driver.keys.hotkey.side_effect
                driver._clipboard.side_effect=lambda fmt,text:copied.update(text=text)
                driver.clip.SetClipboardData.side_effect=lambda fmt,text:copied.update(text=text)
                def hotkey(*keys):
                    original(*keys)
                    if keys==('ctrl','v'):pasted.append(copied['text'])
                driver.keys.hotkey.side_effect=hotkey
                with patch('app.wecom_sender.time.sleep'):
                    for _ in range(2):self.assertEqual(driver.send('测试甲',[]),'已发送' if confirm else '仅粘贴未发送')
                self.assertEqual(driver.clip.SetClipboardData.call_args_list[0].args,(13,'统一内容 {姓名}'))
                self.assertEqual(driver.clip.EmptyClipboard.call_count,2)
                self.assertEqual(pasted,['测试甲','统一内容 {姓名}']*2)
                self.assertEqual(driver.keys.press.call_count,4 if confirm else 2)
                self.assertEqual(sum(keys==('ctrl','v') for keys,_ in state['events']),4)
                self.assertEqual(driver._clipboard.call_count,2)  # Only contact searches write text.

    def test_failures_before_and_after_paste_keep_existing_result_rules(self):
        for after_paste in (False,True):
            driver,state=fake_driver({'clipboard_mode':True})
            payload=Mock();driver.clipboard_payload=payload;driver.clip=Mock()
            if after_paste:driver.keys.press.side_effect=[None,RuntimeError('enter failed')]
            else:driver.search_contact_v2=Mock(side_effect=RuntimeError('contact not found'))
            with patch('app.wecom_sender.time.sleep'),self.assertRaises(DispatchError) as result:driver.send('测试甲',[])
            self.assertEqual(result.exception.uncertain,after_paste)
            payload.restore.assert_called_once_with(driver.clip)

    def test_worker_continues_failure_protects_paste_only_and_claims_recheck_mode(self):
        with seeded(1) as backend:
            g=backend.groupCenter;self.assertTrue(g.createEmptyList('虚构名单'))
            self.assertTrue(g.addNames(g.selected['id'],['甲','乙','丙']))
            g.store.configure(g.selected['id'],'测试',{'clipboard_mode':True})
            tasks=g.store.plan(g.selected['id']);driver=Mock()
            driver.send.side_effect=[DispatchError('not found'),'仅粘贴未发送','已发送']
            SendWorker(g.store,g.selected['id'],tasks,lambda:driver,adapter=adapter,options={'clipboard_mode':True},continue_on_failure=True).run()
            rows=g.rows
            self.assertEqual([row['state'] for row in rows],[receipts.FAILED,'仅粘贴未发送',receipts.SENT])
            self.assertIn('剪贴板模式',rows[1]['detail'])
            self.assertEqual([task['name'] for task in g.store.plan(g.selected['id'])],['甲'])
            g.store.configure(g.selected['id'],'测试',{})
            with self.assertRaisesRegex(ValueError,'尚未配置消息'):g.store.claim(g.selected['id'],tasks[0])
            self.assertEqual(json.loads(rows[0]['content']),[])

    def test_old_source_list_still_rechecks_eligibility_and_syncs_results(self):
        with seeded(2) as backend:
            w,_=prepare(backend,2);g=backend.groupCenter
            g._id=g.store.create('旧来源',[dict(name='学员1',student_id='P2026169001A',message='')],w.store,w._batch)
            g._reload_snapshot(lists=True)
            payload=ClipboardPayload([(13,'本轮消息')],text='本轮消息')
            with patch('app.group_center.clipboard_payload.capture',return_value=payload):self.assertTrue(g.prepare('测试',{'clipboard_mode':True}))
            SendWorker(g.store,g.selected['id'],g.preview,lambda:Mock(send=Mock(return_value='已发送')),adapter=adapter,options={'clipboard_mode':True}).run()
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],receipts.SENT)
            self.assertFalse(g.store.plan(g.selected['id']))
            w.store.create('新批次',w.template)
            with self.assertRaisesRegex(ValueError,'历史批次'):g.store.plan(g.selected['id'])

    def test_mode_validation_and_legacy_default(self):
        self.assertFalse(normalize()['clipboard_mode'])
        with self.assertRaisesRegex(ValueError,'布尔值'):normalize({'clipboard_mode':'true'})


if __name__=='__main__':unittest.main()
