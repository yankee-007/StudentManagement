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
        self.assertEqual(learning_dashboard([],{}),dict(version=3,total=0,matched=0,courses=[],homework=[],opened=0,
            cumulativeCourse=0,cumulativeHomework=0,cumulative=dict(opened=0,courses=0,homework=0),
            completion=dict(courses=[],homework=[])))
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


class CumulativeHeadcountTests(unittest.TestCase):
    """看板顶部「累计完课人数／累计作业人数」与累计率的分子必须是同一个人数。"""

    def test_headcount_matches_cumulative_rate_numerator(self):
        students=[dict(student_id=str(i),roster_status='在读') for i in range(4)]
        source={'0':{'c1':'T','c2':'T','z1':'T','z2':'F'},
                '1':{'c1':'F','c2':'T','z1':'T','z2':'T'},
                '2':{'c1':'T','c2':'F','z1':'F','z2':'T'},
                '3':{'c1':'N','c2':'T','z2':'T'}}
        data=learning_dashboard(students,source)
        last=data['courses'][-1]
        self.assertEqual(data['opened'],2)
        self.assertEqual(data['cumulativeCourse'],last['completed'])
        self.assertEqual(data['cumulative']['courses'],last['completed'])
        self.assertEqual(data['cumulative']['homework'],data['homework'][-1]['completed'])
        # 完成第 1～2 节课程全部完成的只有学号 0。
        self.assertEqual(data['cumulative']['courses'],1)

    def test_no_opened_lesson_is_zero_not_missing(self):
        data=learning_dashboard([dict(student_id='a',roster_status='在读')],{'a':{'c1':'N','z1':'N'}})
        self.assertEqual((data['opened'],data['cumulative']['courses'],data['cumulative']['homework']),(0,0,0))

    def test_homework_only_batch_keeps_course_headcount_zero(self):
        data=learning_dashboard([dict(student_id='a',roster_status='在读')],{'a':{'z1':'T'}})
        self.assertEqual(data['opened'],0)
        self.assertEqual(data['cumulative']['homework'],0)


class CompletionDistributionTests(unittest.TestCase):
    """「完课次数」分栏：人数/所占比例按完成节数分桶，完课率与完课人数为累计口径。"""

    def test_buckets_percentages_and_cumulative(self):
        students=[dict(student_id='a',roster_status='在读'),dict(student_id='b',roster_status='在读'),
                  dict(student_id='c',roster_status='在读'),dict(student_id='d',roster_status='在读')]
        source={'a':{'c1':'T','c2':'T','c3':'T'},   # 完成 3 节
                'b':{'c1':'T','c2':'T','c3':'F'},   # 完成 2 节
                'c':{'c1':'T','c2':'F','c3':'F'},   # 完成 1 节
                'd':{'c1':'F','c2':'F','c3':'F'}}   # 完成 0 节
        rows=learning_dashboard(students,source)['completion']['courses']
        self.assertEqual([r['count'] for r in rows],[3,2,1,0])
        self.assertEqual([r['people'] for r in rows],[1,1,1,1])
        self.assertEqual([r['ratio'] for r in rows],['25.00%']*4)
        self.assertEqual([r['cumulative'] for r in rows],[1,2,3,4])
        self.assertEqual([r['cumulativeRate'] for r in rows],['25.00%','50.00%','75.00%','100.00%'])
        self.assertEqual(sum(r['people'] for r in rows),4)

    def test_bucket_zero_holds_students_without_any_completion(self):
        # 数据缺失（无记录）与 U 都按 0 节计入最后一桶，保证各桶人数合计＝在读人数。
        students=[dict(student_id='a',roster_status='在读'),dict(student_id='b',roster_status='在读'),
                  dict(student_id='c',roster_status='在读')]
        source={'a':{'c1':'T'},'b':{'c1':'U'}}
        rows=learning_dashboard(students,source)['completion']['courses']
        self.assertEqual(rows[-1]['count'],0)
        self.assertEqual(rows[-1]['people'],2)
        self.assertEqual(rows[-1]['cumulativeRate'],'100.00%')

    def test_completions_beyond_opened_lessons_merge_into_last_row(self):
        students=[dict(student_id=str(i),roster_status='在读') for i in range(4)]
        # 学号 0 完成 4 节（1、2、4、5），超过「已开课节次＝5」可以容纳的连续完成数：
        # 超过 opened 的人必须并进最高桶，各桶人数合计仍等于在读人数。
        source={'0':{'c1':'T','c2':'T','c3':'F','c4':'T','c5':'T'},'1':{'c1':'T','c2':'T','c3':'T','c4':'F','c5':'F'},
                '2':{'c1':'T','c2':'F','c3':'F','c4':'F','c5':'F'},'3':{'c1':'F','c2':'F','c3':'F','c4':'F','c5':'F'}}
        data=learning_dashboard(students,source)
        rows=data['completion']['courses']
        self.assertEqual(data['opened'],5)
        self.assertEqual([r['count'] for r in rows],[5,4,3,2,1,0])
        self.assertEqual([r['people'] for r in rows],[0,1,1,0,1,1])
        self.assertEqual(rows[0]['cumulative'],0)
        self.assertEqual(sum(r['people'] for r in rows),data['total'])

    def test_distribution_denominator_is_active_students_only(self):
        students=[dict(student_id='a',roster_status='在读'),
                  dict(student_id='b',roster_status='已退课'),
                  dict(student_id='c',roster_status='在读',is_placeholder=True)]
        rows=learning_dashboard(students,{'a':{'c1':'T'},'b':{'c1':'T'},'c':{'c1':'T'}})['completion']['courses']
        self.assertEqual(sum(r['people'] for r in rows),1)
        self.assertEqual(rows[0]['cumulativeRate'],'100.00%')

    def test_homework_distribution_uses_homework_flags(self):
        students=[dict(student_id='a',roster_status='在读'),dict(student_id='b',roster_status='在读')]
        source={'a':{'c1':'T','c2':'T','z1':'T','z2':'F'},'b':{'c1':'T','c2':'F','z1':'F','z2':'F'}}
        data=learning_dashboard(students,source)
        self.assertEqual([r['count'] for r in data['completion']['homework']],[2,1,0])
        self.assertEqual([r['people'] for r in data['completion']['homework']],[0,1,1])

    def test_empty_class_reports_no_rows(self):
        self.assertEqual(learning_dashboard([],{})['completion']['courses'],[])


if __name__ == '__main__':
    unittest.main()
