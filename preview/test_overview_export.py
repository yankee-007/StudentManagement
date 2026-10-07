import json
import sqlite3
import unittest
from build_overview import load_batches


class ExportCompletionTests(unittest.TestCase):
    def test_followup_counts_use_exact_bucket_and_target_population(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE campaigns(id INTEGER,created_at TEXT); CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT); CREATE TABLE campaign_students(batch_id INTEGER,student_id TEXT,snapshot TEXT,eligible INTEGER,name TEXT); CREATE TABLE campaign_feedback(batch_id INTEGER,student_id TEXT,kind TEXT);')
            conn.executemany('INSERT INTO campaigns VALUES(?,?)', [(1, 'old'), (2, 'history'), (3, 'latest')])
            buckets = [dict(count=2, people=1, cumulative=1, followable=999),dict(count=1, people=2, cumulative=3),dict(count=0, people=4, cumulative=7)]
            for bid, version in [(1, 2), (2, 3), (3, 3)]:
                conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',(bid,json.dumps(dict(version=version,total=7,opened=2,completion=dict(courses=buckets)))))
            for sid,count,status,placeholder,kind in [('a',0,'在读',False,'reply'),('b',0,'在读',False,'reply'),('c',0,'在读',False,'reply'),('d',0,'在读',False,'unreplied'),('e',1,'在读',False,'reply'),('f',1,'在读',False,None),('g',2,'在读',False,'reply'),('h',0,'退课',False,'reply'),('i',0,'在读',True,'reply')]:
                for bid in (2,3):
                    conn.execute('INSERT INTO campaign_students VALUES(?,?,?,?,?)',(bid,sid,json.dumps(dict(completed_courses=count,roster_status=status,is_placeholder=placeholder,wechat='是')),1,'测试学员'))
                if kind:conn.execute('INSERT INTO campaign_feedback VALUES(?,?,?)',(3,sid,kind))
            conn.execute("INSERT INTO campaign_feedback VALUES(3,'a','reply')")
            conn.execute('INSERT INTO campaign_students VALUES(?,?,?,?,?)',(3,'outside',json.dumps(dict(completed_courses=0,roster_status='在读',is_placeholder=False,wechat='是')),0,'范围外学员'))
            before=load_batches(conn)
            self.assertTrue(all('followable' not in b for b in before[-1]['completion']))
            conn.execute('CREATE TABLE campaign_followup_status(batch_id INTEGER,student_id TEXT,status TEXT,PRIMARY KEY(batch_id,student_id))')
            for sid in ('a','b','c','e','g','h','i','outside'):
                conn.execute("INSERT INTO campaign_followup_status VALUES(3,?,'是')",(sid,))
            conn.execute("INSERT INTO campaign_followup_status VALUES(3,'d','否')")
            rows=load_batches(conn)
            self.assertEqual(rows[0]['completion'],[])
            self.assertTrue(all('followable' not in b for b in rows[1]['completion']))
            self.assertEqual(rows[1]['followupSummary'],dict(total=7,marked=0,yes=0,no=0,unmarked=7))
            self.assertEqual([b['followable'] for b in rows[2]['completion']],[1,1,3])
            self.assertEqual([b['people'] for b in rows[2]['completion']],[1,2,4])
            self.assertEqual(rows[2]['completionTotal'],7)
            self.assertEqual(rows[2]['total'],7)
            self.assertEqual([b['cumulative'] for b in rows[2]['completion']],[1,3,7])
            self.assertEqual(rows[2]['followupSummary'],dict(total=7,marked=6,yes=5,no=1,unmarked=1))
            self.assertIn('尚有1人未填写',rows[2]['completionNotice'])
            requested=load_batches(conn,feedback_batch=2)[1]
            self.assertTrue(all('followable' not in b for b in requested['completion']))
            conn.execute('UPDATE campaign_students SET eligible=0 WHERE batch_id=3')
            latest=load_batches(conn)[-1]
            self.assertEqual(latest['completionTotal'],0)
            self.assertEqual(latest['completion'],[])

    def test_legacy_counts_without_cumulative_snapshot_and_unknown_counts(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE campaigns(id INTEGER,created_at TEXT); CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT); CREATE TABLE campaign_students(batch_id INTEGER,student_id TEXT,snapshot TEXT,eligible INTEGER,name TEXT); CREATE TABLE campaign_followup_status(batch_id INTEGER,student_id TEXT,status TEXT,PRIMARY KEY(batch_id,student_id));')
            conn.executemany('INSERT INTO campaigns VALUES(?,?)',[(1,'missing'),(2,'single'),(3,'cumulative')])
            snapshot=dict(total=5,opened=2,courses=[dict(lesson=1,completed=4,completedRate='80%')],homework=[dict(lesson=1,completed=3,completedRate='60%')])
            conn.execute('INSERT INTO campaign_dashboards VALUES(2,?)',(json.dumps(snapshot),))
            snapshot['version']=2
            conn.execute('INSERT INTO campaign_dashboards VALUES(3,?)',(json.dumps(snapshot),))
            for bid in (1,2,3):
                for sid,fields in [('zero',dict(completed_total='0/2')),('one',dict(completed_total='1/2')),('two',dict(completed_courses=2)),('unknown',dict(completed_courses='',completed_total='0/2')),('invalid',dict(completed_courses=33))]:
                    fields.update(roster_status='在读',wechat='是')
                    conn.execute('INSERT INTO campaign_students VALUES(?,?,?,?,?)',(bid,sid,json.dumps(fields),1,'虚拟姓名'))
                    if bid==2:conn.execute('INSERT INTO campaign_followup_status VALUES(?,?,?)',(bid,sid,'否'))
            rows=load_batches(conn)
            self.assertEqual([row['id'] for row in rows],[1,2,3])
            self.assertEqual(rows[0]['lessons'],[])
            self.assertIn('未保存累计学习快照',rows[0]['learningNotice'])
            self.assertEqual(rows[1]['lessons'],[])
            self.assertIn('仅保存单节',rows[1]['learningNotice'])
            self.assertEqual(rows[2]['lessons'][0]['gap'],20)
            for row in rows:
                self.assertEqual([b['people'] for b in row['completion']],[1,1,1])
                self.assertEqual(row['completionTotal'],5)
                self.assertEqual(row['members'],5)
                self.assertEqual(row['completion'][-1]['cumulativeRate'],'60.00%')
                self.assertEqual(row['completion'][-1]['ratio'],'20.00%')
                self.assertIn('2名催办学员未保存可用完成计数',row['completionNotice'])
            self.assertEqual([b['followable'] for b in rows[1]['completion']],[0,0,0])
            self.assertEqual(rows[1]['followupSummary'],dict(total=5,marked=5,yes=0,no=5,unmarked=0))
            self.assertTrue(all('followable' not in b for b in rows[0]['completion']))
            exported=json.dumps(rows,ensure_ascii=False)
            for private in ('虚拟姓名','student_id','completed_total','unknown'):
                self.assertNotIn(private,exported)


if __name__=='__main__':
    unittest.main()
