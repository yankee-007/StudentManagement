"""Synthetic AI generation tests; no real credentials or external calls."""
import json
from threading import Event
import time
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication

from app import ai_campaign as ai
from tests.test_business_logic import seeded


def student(sid='001', courses='', homework='2'):
    return dict(student_id=sid, name='测试学员', diagnostic=ai.diagnose(courses, homework))


def text_for(s):
    return s['name'] + '同学，请补齐' + '和'.join(s['diagnostic']['required']) + '，有困难可以找老师。' + ('可别越拖越多哦' if s['diagnostic']['multi'] else '')


def fake_chat(config, key, messages):
    body = json.loads(messages[-1]['content'])
    return json.dumps({s['student_id']: text_for(s) for s in body['students']}, ensure_ascii=False)


def wait_for(module):
    deadline = time.monotonic() + 5
    app = QCoreApplication.instance()
    while module.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert not module.busy, 'generation did not finish'


class PureAiTests(unittest.TestCase):
    def test_all_templates_and_clamping(self):
        for i in range(1, 33):
            template = ai.load_template(i)
            self.assertEqual(template['index'], i)
            self.assertIn('场景分支', template['template'])
        self.assertEqual(ai.load_template(80)['index'], 32)

    def test_diagnostics(self):
        self.assertEqual(ai.diagnose('1,5', '3')['kind'], '全未启动')
        self.assertEqual(ai.diagnose('3', '')['kind'], '缺课单节点')
        self.assertEqual(ai.diagnose('', '4')['kind'], '缺作业单节点')
        self.assertEqual(ai.diagnose('3,8', '3')['kind'], '散落多节点')
        self.assertEqual(ai.diagnose('3', '3')['nodes'], [3])
        self.assertFalse(ai.diagnose('3', '3')['multi'])
        self.assertEqual(ai.diagnose('N,U', '')['nodes'], [])

    def test_json_contract(self):
        people = [student()]
        valid = json.dumps({'001': text_for(people[0])})
        self.assertEqual(ai.parse_output(valid, people)[1], {})
        for raw in ('```json\n'+valid+'\n```', '{}', '[]', '{"001":"a","001":"b"}', '{"001":"a","002":"b"}'):
            with self.assertRaises(ValueError):
                ai.parse_output(raw, people)

    def test_fidelity(self):
        s = student(courses='3,8', homework='4')
        text = text_for(s)
        ai.validate_text(text, s['diagnostic'])
        for bad in ('', 'x'*201, '请完成第3节课', text+' 第9节课', text.replace('可别越拖越多哦', ''), text+'{姓名}', text+'\0'):
            with self.assertRaises(ValueError):
                ai.validate_text(bad, s['diagnostic'])
        with self.assertRaises(ValueError):
            ai.validate_text('你已完成', ai.diagnose('', ''))
        with self.assertRaises(ValueError):
            ai.validate_text('请完成第3节课的作业', ai.diagnose('3', '3'))
        with self.assertRaises(ValueError):
            ai.validate_text(text_for(student(courses='3', homework='4')) + '并补第3节课的作业', ai.diagnose('3','4'))

    def test_config_validation(self):
        config = ai.normalize_config(dict(model='example', key='must-not-store'))
        self.assertNotIn('key', config)
        for raw in (dict(model=''), dict(model='x',base_url='http://example.com/v1'),
                    dict(model='x',base_url='https://secret@example.com/v1'),
                    dict(model='x',batch_size=1.5), dict(model='x',concurrency=9),dict(model='x',temperature=float('nan'))):
            with self.assertRaises(ValueError): ai.normalize_config(raw)

    def test_modes(self):
        for mode, calls in (('person', 3), ('batch', 2), ('all', 1)):
            config = dict(ai.DEFAULTS, model='x', mode=mode, batch_size=2)
            request = MagicMock(side_effect=fake_chat)
            results, failures = ai.generate([student(str(i)) for i in range(3)], config, 'fake', {}, Event(), lambda *a: None, request)
            self.assertEqual(len(results), 3)
            self.assertFalse(failures)
            self.assertEqual(request.call_count, calls)

    def test_retry_only_invalid_people_and_backoff(self):
        people = [student('001'), student('002')]
        calls = []
        def request(c, k, messages):
            batch = json.loads(messages[-1]['content'])['students']
            calls.append([s['student_id'] for s in batch])
            if len(calls) == 1:
                return json.dumps({'001': text_for(people[0]), '002': ''})
            return json.dumps({'002': ''})
        cancel = MagicMock(); cancel.is_set.return_value = False; cancel.wait.return_value = False
        results, failures = ai.generate(people, dict(ai.DEFAULTS, model='x'), 'fake', {}, cancel, lambda *a: None, request)
        self.assertEqual(calls, [['001','002'],['002'],['002']])
        self.assertEqual(set(results), {'001'})
        self.assertEqual(set(failures), {'002'})
        self.assertEqual([c.args[0] for c in cancel.wait.call_args_list], [1, 2])

    def test_cancel_prevents_calls(self):
        cancel = Event(); cancel.set()
        request = MagicMock()
        valid, failed = ai.generate([student()], dict(ai.DEFAULTS,model='x'), 'fake', {}, cancel, lambda *a:None, request)
        request.assert_not_called(); self.assertFalse(valid); self.assertIn('001', failed)

    def test_unknown_and_empty_debt_do_not_call_ai(self):
        request = MagicMock()
        people = [student('001', '未获取', 'N')]
        valid, failed = ai.generate(people, dict(ai.DEFAULTS,model='x'), 'fake', {}, Event(), lambda *a:None, request)
        request.assert_not_called(); self.assertFalse(valid); self.assertIn('001', failed)

    def test_long_debt_ranges_remain_complete_and_short(self):
        numbers=','.join(map(str,range(1,33)))
        s=student(courses=numbers,homework=numbers)
        self.assertEqual(s['diagnostic']['required'],['第1～32节课','第1～32节课的作业'])
        text=text_for(s)
        self.assertLessEqual(len(text),200)
        ai.validate_text(text,s['diagnostic'])
        mixed='1,2,3,5,7,8,9,11'
        d=ai.diagnose(mixed,'')
        self.assertEqual(d['required'],['第1～3、5、7～9、11节课'])
        valid='请补'+d['required'][0]+'，可别越拖越多哦'
        ai.validate_text(valid,d)
        with self.assertRaises(ValueError):
            ai.validate_text(valid+' 第1～6、11节课',d)

    def test_http_contract_and_secret_redaction(self):
        response = MagicMock(); response.status_code = 200
        response.json.return_value = dict(choices=[dict(finish_reason='stop',message=dict(content='{"ok":true}'))])
        post = MagicMock(return_value=response)
        config = dict(ai.DEFAULTS,model='x')
        self.assertEqual(ai.chat(config,'fake-secret',[],post), '{"ok":true}')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertEqual(post.call_args.args[0], config['base_url']+'/chat/completions')
        config['base_url'] = 'https://api.openai.com/v1'
        ai.chat(config, 'fake-secret', [], post)
        self.assertIn('max_completion_tokens', post.call_args.kwargs['json'])
        response.status_code = 401
        with self.assertRaises(ValueError) as error: ai.chat(config, 'fake-secret', [], post)
        self.assertNotIn('fake-secret', str(error.exception))
        response.status_code = 200
        response.json.return_value['choices'][0]['finish_reason'] = 'length'
        with self.assertRaises(ValueError): ai.chat(config, 'fake-secret', [], post)


class AiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setup_campaign(self, b, count=2):
        flags = [{'student_id':f'P2026169{i:03d}A','flags':{'c1':'T','z1':'F','c2':'T','z2':'N','c3':'N','z3':'N'}} for i in range(1,count+1)]
        b.repo.set_setting('snapshot', json.dumps(flags))
        b.workflow.createBatch()
        b.aiCampaign._config = dict(ai.DEFAULTS, model='test', retries=0)

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    @patch('app.ai_campaign.chat', side_effect=fake_chat)
    def test_generation_current_lesson_and_storage(self, *_):
        with seeded(2) as b:
            self.setup_campaign(b)
            m = b.aiCampaign; keys = b.workflow.recipientKeys
            self.assertEqual(m.currentLesson, 2)
            self.assertTrue(m.start(keys, 0, 'batch'), m.notice)
            wait_for(m)
            self.assertTrue(m.ready, m.notice)
            self.assertEqual(m._template['index'], 2)
            self.assertTrue(m.createList('AI测试名单', keys), b.groupCenter.status)
            rows = b.groupCenter.rows
            self.assertEqual(len(rows), 2)
            self.assertIn('第1节课的作业', json.loads(rows[0]['content'])[0]['text'])
            self.assertTrue(json.loads(rows[0]['content'])[0]['personal_override'])
            self.assertIsNone(b.groupCenter.selected['source_batch'])
            self.assertFalse(b.groupCenter.active)
            b.workflow.filterRows('all','学员1')
            self.assertFalse(m.createList('陈旧名单', keys))

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    @patch('app.ai_campaign.chat', return_value='{}')
    def test_failures_create_empty_and_retry_preserves_manual(self, *_):
        with seeded(2) as b:
            self.setup_campaign(b)
            m = b.aiCampaign; keys=b.workflow.recipientKeys
            self.assertTrue(m.start(keys, 1, 'batch'))
            wait_for(m)
            self.assertEqual(m.failureCount,2)
            self.assertTrue(m.createList('失败名单',keys))
            g=b.groupCenter; rows=g.rows; list_id=g.selected['id']
            self.assertEqual(m.listFailureCount,2)
            self.assertIn('AI 生成失败',g.pendingModel.rows[0]['detail'])
            self.assertFalse(g.prepare('',{}))
            self.assertTrue(g.saveRecipientContent(list_id,rows[0]['id'],[dict(type='text',text='手写消息')]))
            self.assertEqual(m.listFailureCount,1)
            with patch('app.ai_campaign.chat',side_effect=fake_chat):
                self.assertTrue(m.retryList(list_id),m.notice); wait_for(m)
            self.assertEqual(m.listFailureCount,0)
            self.assertEqual(json.loads(g.rows[0]['content'])[0]['text'],'手写消息')
            self.assertIn('第1节课的作业',json.loads(g.rows[1]['content'])[0]['text'])

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    @patch('app.ai_campaign.chat', side_effect=fake_chat)
    def test_stale_learning_and_frozen_filter_scope(self, *_):
        with seeded(2) as b:
            self.setup_campaign(b)
            w=b.workflow; m=b.aiCampaign
            w.setColumnFilter('wechat','values',['是'],'')
            b.repo.update_profile_field('P2026169002A','微信','否')
            w.reload_rows(keep_query=True)
            keys=w.recipientKeys
            self.assertEqual(len(w.tableModel.rows),2)
            self.assertEqual(len(keys),1)
            self.assertTrue(m.start(keys,1,'person')); wait_for(m)
            self.assertEqual(len(m.results),1)
            b.repo.set_setting('snapshot',json.dumps([{'student_id':'P2026169001A','flags':{'c1':'F','z1':'F'}}]))
            w.store.refresh_latest_learning(); w.reload_rows(keep_query=True)
            self.assertFalse(m.createList('过期数据',keys))
            self.assertIn('学习数据',m.notice)

    @patch('app.ai_campaign_module.set_password')
    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    def test_configuration_keeps_key_out_of_database(self, get_key, set_key):
        with seeded(1) as b:
            m=b.aiCampaign
            self.assertTrue(m.saveConfig(dict(ai.DEFAULTS,model='test'),'synthetic-secret'))
            raw=b.workflow.registry.get_setting('ai_campaign_config')
            self.assertNotIn('synthetic-secret',raw)
            self.assertNotIn('api_key',raw)
            self.assertEqual(set_key.call_args.args[0],'ai_campaign')
            self.assertTrue(m.saveConfig(dict(ai.DEFAULTS,model='changed'),''))
            self.assertEqual(set_key.call_count,1)

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    @patch('app.ai_campaign.chat', side_effect=fake_chat)
    def test_manual_template_and_no_automatic_send(self, *_):
        with seeded(1) as b:
            self.setup_campaign(b,1)
            m=b.aiCampaign; keys=b.workflow.recipientKeys
            self.assertTrue(m.start(keys,32,'all')); wait_for(m)
            self.assertEqual(m._template['index'],32)
            self.assertFalse(b.groupCenter.rows)
            self.assertTrue(m.createList('手选话术',keys))
            self.assertFalse(b.groupCenter.active)

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    def test_retry_does_not_overwrite_edit_made_during_request(self, *_):
        with seeded(1) as b:
            self.setup_campaign(b,1)
            m=b.aiCampaign; keys=b.workflow.recipientKeys
            with patch('app.ai_campaign.chat',return_value='{}'):
                self.assertTrue(m.start(keys,1,'batch')); wait_for(m)
            self.assertTrue(m.createList('失败',keys))
            g=b.groupCenter; row=g.rows[0]; started=Event(); release=Event()
            def delayed(c,k,messages):
                started.set(); release.wait(3)
                return fake_chat(c,k,messages)
            with patch('app.ai_campaign.chat',side_effect=delayed):
                self.assertTrue(m.retryList(g.selected['id']))
                self.assertTrue(started.wait(2))
                self.assertTrue(g.saveRecipientContent(g.selected['id'],row['id'],[dict(type='text',text='请求期间手写')]))
                release.set(); wait_for(m)
            self.assertEqual(json.loads(g.rows[0]['content'])[0]['text'],'请求期间手写')

    @patch('app.ai_campaign_module.get_password', return_value='synthetic-key')
    @patch('app.ai_campaign.chat', return_value='{}')
    def test_retry_skips_protected_records(self, *_):
        with seeded(1) as b:
            self.setup_campaign(b,1)
            m=b.aiCampaign; keys=b.workflow.recipientKeys
            self.assertTrue(m.start(keys,1,'batch')); wait_for(m)
            self.assertTrue(m.createList('失败',keys))
            g=b.groupCenter; row=g.rows[0]
            metadata=json.loads(row['learning_data'])['ai_generation']
            with g.store.connect() as conn:
                conn.execute("UPDATE recipients SET state='结果待确认' WHERE id=?",(row['id'],))
            g.refresh()
            self.assertEqual(m.listFailureCount,0)
            s=metadata['student']
            g.applyAiRetries(g.selected['id'],{s['student_id']:text_for(s)},{})
            self.assertEqual(json.loads(g.rows[0]['content']),[])
            self.assertEqual(g.rows[0]['state'],'结果待确认')


if __name__ == '__main__':
    unittest.main()
