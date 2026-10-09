import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtCore import QCoreApplication
from app.message_content import prepare_content
from app.send_options import normalize
from app.wecom_sender import WeComSender, DispatchError
from app.send_controller import SendWorker
from app import group_dispatch as adapter
from tests.test_business_logic import seeded
from tests.test_real_sending import prepare


def fake_driver(options):
    driver=WeComSender.__new__(WeComSender)
    driver.options=normalize(options)
    driver.keys=Mock();driver.gui=Mock();driver.process=Mock()
    driver._clipboard=Mock()
    driver.constants=SimpleNamespace(CF_UNICODETEXT=13,CF_HDROP=15)
    driver.pause_requested=lambda:False
    driver.keys.getWindowsWithTitle.return_value=[Mock(title='企业微信',isMinimized=False)]
    state={'hwnd':1,'events':[]}
    driver.gui.GetForegroundWindow.side_effect=lambda:state['hwnd']
    driver.gui.GetWindowText.side_effect=lambda h:'企业微信' if h==1 else '测试甲'
    driver.gui.IsWindow.return_value=True
    driver.process.GetWindowThreadProcessId.return_value=(1,777)
    def hotkey(*keys):
        state['events'].append((keys,state['hwnd']))
        if keys==('ctrl','o'):state['hwnd']=2
        if keys==('ctrl','w'):state['hwnd']=1
    driver.keys.hotkey.side_effect=hotkey
    driver.keys.press.side_effect=lambda key:state['events'].append(((key,),state['hwnd']))
    return driver,state


class MessageContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_original_defaults_and_legacy_options(self):
        defaults=normalize()
        self.assertEqual([defaults[k] for k in ('wait','timeout','focus_delay','paste_delay','interval')],[.5,3,.5,.5,0])
        self.assertTrue(defaults['single_send'])
        self.assertTrue(defaults['verify_contact'])
        self.assertNotIn('close_on_success',normalize({'close_on_success':False}))
        self.assertEqual(normalize({'paste_delay':.2})['paste_delay'],.2)
        self.assertEqual(normalize({'close_on_success':False,'paste_delay':.3})['paste_delay'],.5)

    def test_text_file_order_main_window_and_send_modes(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'作业笔记.png';file.write_bytes(b'fixture')
            content=[dict(type='text',text='第一条'),dict(type='file',path=str(file)),dict(type='text',text='第三条')]
            for single,confirm,count in ((True,True,4),(False,True,2),(True,False,1),(False,False,1)):
                with self.subTest(single=single,confirm=confirm):
                    driver,state=fake_driver(dict(single_send=single,confirm_send=confirm))
                    with patch('app.wecom_sender.time.sleep'):
                        result=driver.send('测试甲',content)
                    self.assertEqual(result,'已发送' if confirm else '仅粘贴未发送')
                    self.assertEqual(driver.keys.press.call_count,count)
                    self.assertTrue(all(hwnd==1 for keys,hwnd in state['events'] if keys in (('ctrl','v'),('enter',))))
                    closing=state['events'].index((('ctrl','w'),2))
                    self.assertEqual(sum(keys==('ctrl','v') for keys,_ in state['events'][closing+1:]),3)
                    if not confirm:
                        self.assertNotIn(('enter',),[keys for keys,_ in state['events'][closing+1:]])
                    calls=driver._clipboard.call_args_list
                    self.assertEqual(calls[1].args,(13,'第一条'))
                    self.assertEqual(calls[2].args[0],15)
                    self.assertEqual(calls[2].args[1][20:].decode('utf-16le'),str(file)+'\0\0')
                    self.assertEqual(calls[3].args,(13,'第三条'))

    def test_disabled_float_and_partial_failure(self):
        driver,state=fake_driver({'verify_contact':False})
        with patch('app.wecom_sender.time.sleep'):
            self.assertEqual(driver.send('测试甲','文字'),'已发送')
        self.assertNotIn(('ctrl','o'),[keys for keys,_ in state['events']])
        driver,state=fake_driver({})
        original=driver.copy_chat_item
        def fail_second(item):
            if item['text']=='第二条':raise RuntimeError('粘贴失败')
            original(item)
        driver.copy_chat_item=fail_second
        with patch('app.wecom_sender.time.sleep'),self.assertRaises(DispatchError) as result:
            driver.send('测试甲',[dict(type='text',text='第一条'),dict(type='text',text='第二条')])
        self.assertTrue(result.exception.uncertain)
        self.assertIn('已执行发送 1 次',str(result.exception))

    def test_gui_content_storage_file_preflight_and_success(self):
        with seeded(1) as b,tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'notes.zip';file.write_bytes(b'fixture')
            fields=[dict(type='text',text='{姓名}，你好'),dict(type='file',path=str(file))]
            g=b.groupCenter
            self.assertTrue(g.createStructured('文件测试','甲\n乙',fields),g.status)
            self.assertTrue(g.prepare('',{}))
            self.assertEqual(g.preview[0]['content'][0]['text'],'甲，你好')
            self.assertEqual(json.loads(g.rows[0]['content'])[1]['path'],str(file))
            file.write_bytes(b'changed-content')
            with patch('app.wecom_sender.WeComSender') as factory:
                self.assertFalse(g.start())
                factory.assert_not_called()
            self.assertTrue(g.prepare('',{}))
            tasks=list(g.preview)
            driver=Mock();driver.send.return_value='已发送'
            SendWorker(g.store,g.selected['id'],tasks,lambda:driver,adapter=adapter).run()
            self.assertEqual(driver.send.call_args_list[0].args,('甲',tasks[0]['content']))
            self.assertTrue(all(r['state']=='已发送' for r in g.rows))
            self.assertEqual(b.workflow.store.batches(),[])
            file.unlink()
            self.assertFalse(g.createStructured('无效','甲',fields))

    def test_campaign_personal_message_plus_attachment(self):
        with seeded(2) as b,tempfile.TemporaryDirectory() as folder:
            w,_=prepare(b,2);g=b.groupCenter
            self.assertTrue(g.generateCampaign('{姓名}补作业{欠作业}'))
            file=Path(folder)/'note.txt';file.write_text('fixture',encoding='utf-8')
            self.assertTrue(g.saveContent(g.selected['id'],[dict(type='text',text='{话术}'),dict(type='file',path=str(file))]))
            self.assertTrue(g.prepare('',{}))
            self.assertEqual(g.preview[0]['content'][0]['text'],'学员1补作业1')
            driver=Mock();driver.send.return_value='已发送'
            SendWorker(g.store,g.selected['id'],[g.preview[0]],lambda:driver,adapter=adapter).run()
            before=g.rows[0]['content']
            self.assertTrue(g.saveContent(g.selected['id'],[dict(type='text',text='新内容{姓名}')]))
            self.assertEqual(g.rows[0]['content'],before)
            self.assertEqual(w.store.rows(w._batch)[0]['send_state'],'已发送')


if __name__=='__main__':unittest.main()
