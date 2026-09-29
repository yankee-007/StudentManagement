import unittest
from app.dashboard import learning_dashboard


class DashboardTests(unittest.TestCase):
    def test_active_denominator_and_unknown(self):
        students=[dict(student_id=str(i),roster_status=status,status='请假' if i==1 else '正常',is_placeholder=i==6)
                  for i,status in enumerate(['在读','在读','在读','在读','已退课','冻结','在读',''])]
        source={'0':{'c1':'T','z1':'F','c2':'N'},'1':{'c1':'F','z1':'T','c2':'N'},
                '2':{'c1':'N','z1':'N'},'4':{'c1':'T','c3':'T'},'6':{'c1':'T'}}
        data=learning_dashboard(students,source)
        self.assertEqual((data['total'],data['matched']),(4,3))
        self.assertEqual(data['courses'],[dict(lesson=1,pending=1,completed=1,singleCompleted=1,singleRate='25.00%',pendingRate='25.00%',completedRate='25.00%',unopened=1,unknown=1,difference='0.00%')])
        self.assertEqual(data['homework'][0]['pendingRate'],'25.00%')

    def test_empty_and_lesson_order(self):
        self.assertEqual(learning_dashboard([],{}),dict(version=2,total=0,matched=0,courses=[],homework=[]))
        data=learning_dashboard([dict(student_id='a',roster_status='在读')],{'a':{'c32':'F','c2':'T','z3':'T'}})
        self.assertEqual([r['lesson'] for r in data['courses']],[2,32])
        self.assertEqual(data['homework'][0]['completedRate'],'0.00%')
        self.assertEqual(data['homework'][0]['singleRate'],'100.00%')
        self.assertEqual(data['homework'][0]['difference'],'—')

    def test_difference_rounding_and_negative(self):
        students=[dict(student_id=str(i),roster_status='在读') for i in range(3)]
        source={'0':{'c1':'T','z1':'T','c2':'F','z2':'T'},
                '1':{'c1':'T','z1':'F'},'2':{'c1':'F','z1':'F'}}
        data=learning_dashboard(students,source)
        self.assertEqual(data['courses'][0]['completedRate'],'66.67%')
        self.assertEqual(data['courses'][0]['difference'],'33.33%')
        self.assertEqual(data['homework'][1]['difference'],'-33.33%')

    def test_cumulative_requires_same_students_all_lessons(self):
        students=[dict(student_id=str(i),roster_status='在读') for i in range(4)]
        source={'0':{'c1':'T','c2':'T','z1':'T','z2':'F'},
                '1':{'c1':'F','c2':'T','z1':'T','z2':'T'},
                '2':{'c1':'T','c2':'F','z1':'F','z2':'T'},
                '3':{'c1':'N','c2':'T','z2':'T'}}
        data=learning_dashboard(students,source)
        row=data['courses'][1]
        self.assertEqual((row['completed'],row['completedRate'],row['singleRate']),(1,'25.00%','75.00%'))
        self.assertEqual(data['homework'][1]['completedRate'],'25.00%')
        self.assertEqual(row['difference'],'0.00%')
