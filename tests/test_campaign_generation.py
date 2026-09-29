import unittest
import json
from PySide6.QtCore import QCoreApplication
from tests.test_business_logic import seeded


class CampaignGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_both_modes_and_stale_filter(self):
        with seeded(3) as b:
            w=b.workflow;g=b.groupCenter
            w.createBatch();w.filterRows('all','学员2')
            keys=w.recipientKeys
            self.assertEqual(len(keys),1)
            self.assertTrue(g.createFromCampaignSelection('人员',[],keys,True),g.status)
            rows=g.store.rows(g.selected['id'])
            self.assertEqual([r['name'] for r in rows],['学员2'])
            self.assertEqual(json.loads(rows[0]['content']),[])
            self.assertFalse(g.prepare('',{}))
            fields=[{'type':'text','text':'你好，{姓名}'}]
            self.assertTrue(g.createFromCampaignSelection('消息',fields,keys,False),g.status)
            rows=g.store.rows(g.selected['id'])
            self.assertIn('学员2',json.loads(rows[0]['content'])[0]['text'])
            w.filterRows('all','学员1')
            previous=g.selected['id']
            self.assertFalse(g.createFromCampaignSelection('过期',fields,keys,False))
            self.assertEqual(g.selected['id'],previous)
            w.createBatch();w.selectBatch(1)
            self.assertFalse(g.createFromCampaignSelection('历史',[],w.recipientKeys,True))


if __name__=='__main__':unittest.main()
