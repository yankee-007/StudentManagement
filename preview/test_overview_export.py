import json
import sqlite3
import unittest
from build_overview import load_batches


class ExportCompletionTests(unittest.TestCase):
    def test_replied_counts_include_current_bucket_and_lower_buckets(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE campaigns(id INTEGER,created_at TEXT); CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT); CREATE TABLE campaign_students(batch_id INTEGER,student_id TEXT,snapshot TEXT); CREATE TABLE campaign_feedback(batch_id INTEGER,student_id TEXT,kind TEXT);')
            conn.executemany('INSERT INTO campaigns VALUES(?,?)', [(1, 'old'), (2, 'history'), (3, 'latest')])
            buckets = [dict(count=2, people=1, cumulative=1, followable=999),dict(count=1, people=2, cumulative=3),dict(count=0, people=4, cumulative=7)]
            for bid, version in [(1, 2), (2, 3), (3, 3)]:
                conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',(bid,json.dumps(dict(version=version,total=7,opened=2,completion=dict(courses=buckets)))))
            for sid,count,status,placeholder,kind in [('a',0,'在读',False,'reply'),('b',0,'在读',False,'reply'),('c',0,'在读',False,'reply'),('d',0,'在读',False,'unreplied'),('e',1,'在读',False,'reply'),('f',1,'在读',False,None),('g',2,'在读',False,'reply'),('h',0,'退课',False,'reply'),('i',0,'在读',True,'reply')]:
                conn.execute('INSERT INTO campaign_students VALUES(?,?,?)',(3,sid,json.dumps(dict(completed_courses=count,roster_status=status,is_placeholder=placeholder))))
                if kind:conn.execute('INSERT INTO campaign_feedback VALUES(?,?,?)',(3,sid,kind))
            conn.execute("INSERT INTO campaign_feedback VALUES(3,'a','reply')")
            before=load_batches(conn)
            self.assertTrue(all('followable' not in b for b in before[-1]['completion']))
            conn.execute('CREATE TABLE campaign_followup_status(batch_id INTEGER,student_id TEXT,status TEXT,PRIMARY KEY(batch_id,student_id))')
            for sid in ('a','b','c','e','g','h','i'):
                conn.execute("INSERT INTO campaign_followup_status VALUES(3,?,'是')",(sid,))
            conn.execute("INSERT INTO campaign_followup_status VALUES(3,'d','否')")
            rows=load_batches(conn)
            self.assertEqual(rows[0]['completion'],[])
            self.assertEqual([b['followable'] for b in rows[1]['completion']],[0,0,0])
            self.assertEqual([b['followable'] for b in rows[2]['completion']],[5,4,3])
            self.assertEqual([b['people'] for b in rows[2]['completion']],[1,2,4])
            requested=load_batches(conn,feedback_batch=2)[1]
            self.assertEqual([b['followable'] for b in requested['completion']],[0,0,0])
            conn.execute('UPDATE campaign_dashboards SET data=? WHERE batch_id=3',(json.dumps(dict(version=3,total=0,opened=2,completion=dict(courses=[dict(count=0,people=0,cumulative=0)]))),))
            latest=load_batches(conn)[-1]
            self.assertNotIn('followable',latest['completion'][0])
            self.assertIn('不一致',latest['completionNotice'])


if __name__=='__main__':
    unittest.main()
