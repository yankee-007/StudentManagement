import json
import tempfile
import unittest
from pathlib import Path
from app.database import Database
from app.repository import StudentRepository
from app.profile_fields import CHOICES, REMOVED_FIELDS, PROFILE_INPUT_LABELS
from tests.profile_fixtures import legacy_profiles


class ProfileChoiceTests(unittest.TestCase):
    def test_migration_choices_and_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'test.db'
            db = Database(path)
            fields = {k:'原始值' for k in CHOICES}
            fields.update({k:'历史内容' for k in REMOVED_FIELDS})
            with db.connect() as conn:
                legacy_profiles(conn)
                conn.execute("INSERT INTO students(student_id,name,updated_at) VALUES('001','测试','2026-09-23')")
                conn.execute("INSERT INTO profiles(student_id,name,position,fields) VALUES('001','测试',1,?)", (json.dumps(fields),))
                conn.execute("INSERT OR REPLACE INTO settings VALUES('profile_headers',?)", (json.dumps(list(fields)),))
            repo = StudentRepository(Database(path))
            self.assertFalse(path.with_suffix('.before-field-removal.db').exists())
            self.assertFalse(REMOVED_FIELDS.intersection(repo.get('001')['profile_fields']))
            self.assertNotIn('学员状态',repo.get('001')['profile_fields'])
            for label, options in CHOICES.items():
                if label not in PROFILE_INPUT_LABELS: continue
                for value in options:
                    repo.update_profile_field('001',label,value)
                    self.assertEqual(repo.get('001')['profile_fields'][label],value)
                with self.assertRaises(ValueError):
                    repo.update_profile_field('001',label,'非法选项')
            self.assertFalse(REMOVED_FIELDS.intersection(json.loads(repo.get_setting('profile_headers'))))
