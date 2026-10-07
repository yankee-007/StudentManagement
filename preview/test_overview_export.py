import json
import sqlite3
import unittest
from build_overview import load_batches


class ExportCompletionTests(unittest.TestCase):
    def test_snapshot_distribution_and_latest_reply_counts(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE campaigns(id INTEGER,created_at TEXT); CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT); CREATE TABLE campaign_students(batch_id INTEGER,student_id TEXT,snapshot TEXT); CREATE TABLE campaign_feedback(batch_id INTEGER,student_id TEXT,kind TEXT);')
            conn.executemany('INSERT INTO campaigns VALUES(?,?)', [(1,'old'),(2,'history'),(3,'latest')])
            bucket={'count':0,'people':2,'cumulative':2,'ratio':'100.00%','cumulativeRate':'100.00%','followable':999}
            for bid,version in [(1,2),(2,3),(3,3)]:
                conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',(bid,json.dumps({'version':version,'total':2,'opened':0,'completion':{'courses':[bucket]}})))
            for sid,status,placeholder,kind in [('a','在读',False,'reply'),('b','在读',False,'unreplied'),('c','退课',False,'reply'),('d','在读',True,'reply')]:
                conn.execute('INSERT INTO campaign_students VALUES(?,?,?)',(3,sid,json.dumps({'roster_status':status,'is_placeholder':placeholder,'completed_courses':0})))
                conn.execute('INSERT INTO campaign_feedback VALUES(?,?,?)',(3,sid,kind))
            conn.execute("INSERT INTO campaign_feedback VALUES(3,'a','reply')")
            rows=load_batches(conn)
            self.assertEqual(rows[0]['completion'],[])
            self.assertNotIn('followable',rows[1]['completion'][0])
            self.assertEqual(rows[2]['completion'][0]['followable'],1)
            self.assertEqual(rows[2]['completion'][0]['people'],2)
            conn.execute("UPDATE campaign_dashboards SET data=? WHERE batch_id=3",(json.dumps({'version':3,'total':0,'opened':0,'completion':{'courses':[dict(bucket,people=0)]}}),))
            latest=load_batches(conn)[-1]
            self.assertNotIn('followable',latest['completion'][0])
            self.assertIn('不一致',latest['completionNotice'])


if __name__=='__main__':
    unittest.main()
