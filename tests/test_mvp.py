import unittest
from app.engine import validate_status
from app.importer import pending_from_row


class MVPTests(unittest.TestCase):
    def test_pending_order(self):
        self.assertEqual(pending_from_row({'c2':'F','z2':'F','c4':'F','z1':'T'})[2],
                         ['第2节完课','第2节作业','第4节完课'])

    def test_only_two_statuses(self):
        self.assertEqual(validate_status({'status':'正常'}), [])
        self.assertEqual(validate_status({'status':'请假','exemption_end':'2026-12-31'}), [])
        self.assertTrue(validate_status({'status':'请假'}))
        self.assertTrue(validate_status({'status':'已升级'}))
