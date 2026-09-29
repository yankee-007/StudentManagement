import tempfile
import unittest
import csv
import json
from pathlib import Path

from app.database import Database
from app.importer import import_csv
from app.repository import StudentRepository


class FetchWorkflowTests(unittest.TestCase):
    def test_snapshot_and_leave_followup(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'test.db')
            source = Path(folder) / 'daily.csv'
            with source.open('w', encoding='utf-8-sig', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['学号', '姓名', 'C1', 'Z1', 'C2', 'Z2'])
                writer.writerow(['001', '测试学员', 'T', 'F', 'N', 'N'])
            import_csv(db, source)
            repo = StudentRepository(db)
            students = repo.list_students()
            self.assertGreater(len(students), 0)
            student = repo.update_manual(students[0]['student_id'], {
                'status': '请假', 'exemption_end': '2026-12-31',
            })
            self.assertEqual(student['next_followup_at'], '2027-01-01')
            self.assertEqual(student['status'], '请假')
            snapshot = json.loads(repo.get_setting('snapshot'))
            self.assertEqual(snapshot[0]['flags']['c1'], 'T')
            self.assertEqual(snapshot[0]['flags']['c2'], 'N')
