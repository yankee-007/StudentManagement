import csv
import tempfile
import unittest
from pathlib import Path
from datetime import date

from app.database import Database
from app.profiles import import_profiles
from app.importer import import_csv
from app.repository import StudentRepository


class ProfileTests(unittest.TestCase):
    def test_authoritative_roster_and_feedback(self):
        source = Path('C:/Users/AAA/Desktop/学员画像表.xlsx')
        if not source.exists():
            self.skipTest('用户画像源表不在本机')
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / 'test.db')
            count = import_profiles(db, source)
            repo = StudentRepository(db)
            rows = repo.list_students()
            self.assertEqual(len(rows), count)
            self.assertEqual(count, 207)
            first, second, third = rows[:3]
            original = second['profile_fields'].copy()
            path = Path(folder) / 'fetch.csv'
            fields = ['学号','姓名'] + [f'{p}{i}' for p in ('c','z') for i in range(1,33)]
            with path.open('w',newline='',encoding='utf-8-sig') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for sid, name in [(first['student_id'],first['name']), (second['student_id'],'姓名不符'), ('outside','名单外')]:
                    writer.writerow({**{key:'N' for key in fields},'学号':sid,'姓名':name,'c1':'T','c2':'F','z1':'F'})
            result = import_csv(db,path)
            self.assertEqual(result['matched'],1)
            self.assertEqual(result['mismatched'],1)
            self.assertEqual(result['unknown'],1)
            self.assertEqual(len(repo.list_students()),207)
            self.assertEqual(repo.get(second['student_id'])['profile_fields'],original)
            self.assertIn('未获取',repo.get(third['student_id'])['sync_state'])
            updated = repo.get(first['student_id'])['profile_fields']
            self.assertEqual(updated['合计完课'],1)
            self.assertEqual(updated['差的课程'],'2')
            self.assertEqual(updated['差的作业'],'1')
            self.assertNotIn('学员学习反馈（922）',updated)
            repo.add_feedback(first['student_id'],'第一次')
            repo.add_feedback(first['student_id'],'第二次')
            repo.update_profile_field(first['student_id'],'画像情况','每天学习')
            reopened = StudentRepository(Database(db.path))
            item = reopened.get(first['student_id'])
            self.assertIn('第一次',item['feedback_history'])
            self.assertIn('第二次',item['feedback_history'])
            self.assertEqual(item['profile_fields']['画像情况'],'每天学习')
            self.assertIn(('feedback:'+date.today().isoformat(),'学员学习反馈（'+date.today().isoformat()+'）'),reopened.profile_columns())
            with self.assertRaises(ValueError):
                import_profiles(db,source)
