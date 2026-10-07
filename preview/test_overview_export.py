import json
import sqlite3
import unittest
from build_overview import load_batches


class ExportCompletionTests(unittest.TestCase):
    def test_below_target_counts_use_snapshot_without_feedback(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('CREATE TABLE campaigns(id INTEGER,created_at TEXT); CREATE TABLE campaign_dashboards(batch_id INTEGER,data TEXT);')
            conn.executemany('INSERT INTO campaigns VALUES(?,?)', [(1, 'old'), (2, 'history'), (3, 'latest')])
            buckets = [dict(count=2, people=1, cumulative=1, followable=999),
                       dict(count=1, people=2, cumulative=3),
                       dict(count=0, people=1, cumulative=4)]
            for bid, version in [(1, 2), (2, 3), (3, 3)]:
                conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',
                             (bid, json.dumps(dict(version=version, total=4, completion=dict(courses=buckets)))))
            rows = load_batches(conn)
            self.assertEqual(rows[0]['completion'], [])
            for batch in rows[1:]:
                self.assertEqual([r['followable'] for r in batch['completion']], [3, 1, 0])
            conn.execute('UPDATE campaign_dashboards SET data=? WHERE batch_id=3',
                         (json.dumps(dict(version=3, total=4, completion=dict(courses=[dict(count=2, people=1, cumulative=5)]))),))
            latest = load_batches(conn)[-1]
            self.assertNotIn('followable', latest['completion'][0])
            self.assertIn('无效', latest['completionNotice'])


if __name__ == '__main__':
    unittest.main()
