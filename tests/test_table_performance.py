import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from app.database import Database
from app.repository import StudentRepository
from app.qt_models import DictTableModel
from tests.profile_fixtures import insert_profile


class TablePerformanceTests(unittest.TestCase):
    def test_scalar_role_and_batch_feedback(self):
        model = DictTableModel([('name','姓名')])
        model.set_rows([{'student_id':'001','name':'测试','feedback_history':'长反馈' * 10000}])
        self.assertEqual(model.data(model.index(0,0),model.StudentIdRole),'001')
        roles = model.roleNames()
        model.columns.append(('feedback:2026-09-23','反馈'))
        self.assertEqual(model.roleNames(),roles)
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'test.db')
            with db.connect() as conn:
                for i in range(207):
                    conn.execute('INSERT INTO students(student_id,name,updated_at) VALUES(?,?,?)',(str(i),'测试','2026-09-23'))
                    insert_profile(conn,str(i),'测试',i)
            repo = StudentRepository(db)
            repo.add_feedback('0','反馈')
            count = []
            original = db.connect
            @contextmanager
            def counted():
                count.append(1)
                with original() as conn:
                    yield conn
            with patch.object(db,'connect',counted):
                students = repo.list_students()
            self.assertEqual(len(students),207)
            self.assertEqual(len(count),2)
            self.assertIn('反馈',students[0]['feedback_history'])
