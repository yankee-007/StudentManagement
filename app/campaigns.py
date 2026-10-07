"""Class snapshots and student-linked campaign feedback.

Only the newest batch follows later fetches; every older batch keeps the snapshot it was created with.
"""
import json
import re
from datetime import date, datetime
from .dashboard import learning_dashboard
from .feedback_status import feedback_kind, is_reply
from .profile_storage import format_exemption
from .remark_scan import SCHEMA as REMARK_SCHEMA

EXPORT_COLUMNS = [('student_id','学号'), ('name','姓名'), ('courses','未完课次'),
                  ('homework','未完作业'), ('missing_total','欠交合计'),
                  ('completed_courses','合计完成课程'), ('completed_homework','合计完成作业'),
                  ('feedback','本次反馈情况'),
                  ('roster_status','状态'), ('wechat','微信'), ('exemption_text','免催日期')]
TEST_TEMPLATE = '{姓名}同学，你好：待补课程：{欠课}；待交作业：{欠作业}。请安排时间完成，有特殊情况请回复。'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS campaigns (
 id INTEGER PRIMARY KEY AUTOINCREMENT, class_name TEXT NOT NULL,
 created_at TEXT NOT NULL, template TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaign_students (
 batch_id INTEGER NOT NULL REFERENCES campaigns(id), student_id TEXT NOT NULL,
 name TEXT NOT NULL, remark TEXT NOT NULL, snapshot TEXT NOT NULL,
 eligible INTEGER NOT NULL, reason TEXT NOT NULL,
 message TEXT NOT NULL, send_state TEXT NOT NULL, sent_at TEXT,
 PRIMARY KEY(batch_id,student_id)
);
CREATE TABLE IF NOT EXISTS campaign_feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id INTEGER NOT NULL,
 student_id TEXT NOT NULL, content TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('reply','unreplied')),
 FOREIGN KEY(batch_id,student_id) REFERENCES campaign_students(batch_id,student_id)
);
CREATE INDEX IF NOT EXISTS idx_campaign_feedback_student ON campaign_feedback(batch_id,student_id,id);
CREATE TABLE IF NOT EXISTS campaign_drafts (
 batch_id INTEGER NOT NULL, student_id TEXT NOT NULL, content TEXT NOT NULL,
 PRIMARY KEY(batch_id,student_id),
 FOREIGN KEY(batch_id,student_id) REFERENCES campaign_students(batch_id,student_id)
);
CREATE TABLE IF NOT EXISTS student_contacts (student_id TEXT PRIMARY KEY, remark TEXT NOT NULL);
''' + REMARK_SCHEMA + '''
CREATE TABLE IF NOT EXISTS campaign_dashboards (
 batch_id INTEGER PRIMARY KEY REFERENCES campaigns(id), data TEXT NOT NULL
);
'''


def lessons(value):
    if value is None or value == '':
        return ''
    return ','.join(re.findall(r'\d+', str(value)))


def learning_snapshot(flags):
    """Learning columns for one student's T/F/N/U flags.

    Single shared derivation: snapshot creation and newest-batch refresh must never disagree.
    """
    courses = ','.join(str(i) for i in range(1,33) if flags.get(f'c{i}') == 'F')
    homework = ','.join(str(i) for i in range(1,33) if flags.get(f'z{i}') == 'F')
    ctotal = sum(flags.get(f'c{i}') == 'T' for i in range(1,33))
    ztotal = sum(flags.get(f'z{i}') == 'T' for i in range(1,33))
    missing = f'{len(courses.split(",")) if courses else 0}/{len(homework.split(",")) if homework else 0}'
    completed = f'{ctotal}/{ztotal}'
    if 'U' in flags.values():
        missing_parts = missing.split('/')
        if any(flags.get(f'c{i}') == 'U' for i in range(1,33)):
            courses, ctotal, missing_parts[0] = '未获取', None, '—'
        if any(flags.get(f'z{i}') == 'U' for i in range(1,33)):
            homework, ztotal, missing_parts[1] = '未获取', None, '—'
        missing = '/'.join(missing_parts)
        completed = f'{ctotal if ctotal is not None else "—"}/{ztotal if ztotal is not None else "—"}'
    return dict(courses=courses,homework=homework,missing_total=missing,completed_total=completed,
                completed_courses='' if ctotal is None else str(ctotal),
                completed_homework='' if ztotal is None else str(ztotal))


class CampaignStore:
    def __init__(self, db, repo):
        self.db, self.repo = db, repo
        with db.connect() as conn:
            conn.executescript(SCHEMA)
            if 'created_at' in {r[1] for r in conn.execute('PRAGMA table_info(campaign_feedback)')}:
                # The batch owns its date; individual feedback stores only the original content.
                conn.execute('ALTER TABLE campaign_feedback DROP COLUMN created_at')
            conn.execute("UPDATE campaign_students SET send_state='已发送' WHERE send_state='已执行发送'")

    def batches(self):
        with self.db.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM campaigns ORDER BY id DESC')]

    def dashboard(self,batch):
        with self.db.connect() as conn:
            row=conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?',(batch,)).fetchone()
        if row:
            data=json.loads(row['data'])
            notice=(f"第 {batch} 次催办 · 学习数据已跟随 {data['refreshed_at']} 的获取刷新"
                    if data.get('refreshed_at') else f'第 {batch} 次催办 · 创建时的数据快照')
            if data.get('version',1)<2:
                # Old aggregates cannot recover the intersection of students across lessons.
                for item in data['courses']+data['homework']:
                    item.update(singleCompleted=item['completed'],singleRate=item['completedRate'],
                                completed='—',completedRate='—',difference='—')
                notice+=' · 旧版仅保存单节数据，累计指标无法还原，显示 —'
            if data.get('version',1)<3:
                # 累计人数与完课次数分布是 version 3 才写入快照的；旧快照只在累计率可还原时显示 —。
                if data.get('version',1)>=2:
                    data['cumulative']=dict(opened=0,courses='—',homework='—')
                    data['cumulativeCourse']=data['cumulativeHomework']='—'
                data['completion']={'courses':[],'homework':[]}
                notice+=' · 旧版快照未保存完课次数分布，该分栏暂无数据'
            return dict(data,notice=notice,available=True)
        return dict(total=0,matched=0,courses=[],homework=[],available=False,
                    notice='该历史批次未保存看板快照，无法准确还原；请新建催办生成快照' if batch else '尚未建立催办，请新建催办生成学习数据快照')

    def create(self, class_name, template):
        self.sync_current_identity()
        students = self.repo.list_students()
        if not students:
            raise ValueError('请先在班期学员模块获取名单，画像会自动同步')
        # Validate placeholders before beginning the transaction.
        try:
            template.format(**{'姓名':'测试','欠课':'1','欠作业':'2','欠交合计':'1/1','完成合计':'2/2'})
        except (KeyError, ValueError, IndexError) as exc:
            raise ValueError('话术变量仅支持：姓名、欠课、欠作业、欠交合计、完成合计') from exc
        if not template.strip():
            raise ValueError('话术不能为空')
        source = self.repo.learning_source()
        now = datetime.now().isoformat(timespec='seconds')
        with self.db.connect() as conn:
            contacts = {r['student_id']:r['remark'] for r in conn.execute('SELECT * FROM student_contacts')}
            batch = conn.execute('INSERT INTO campaigns(class_name,created_at,template) VALUES(?,?,?)', (class_name,now,template)).lastrowid
            conn.execute('INSERT INTO campaign_dashboards VALUES(?,?)',
                         (batch,json.dumps(learning_dashboard(students,source),ensure_ascii=False)))
            for position, student in enumerate(students):
                sid = student['student_id']
                fields = student.get('profile_fields', {})
                flags = source.get(sid)
                learning = learning_snapshot(flags) if flags is not None else None
                if learning is None:
                    course=homework=missing=completed=''
                else:
                    course,homework = learning['courses'],learning['homework']
                    missing,completed = learning['missing_total'],learning['completed_total']
                placeholder = student.get('is_placeholder',False)
                if placeholder:
                    course=homework=missing=completed=''
                remark = contacts.get(sid, student['name'])
                leave = student['status'] == '请假' and (student.get('exemption_end') or '9999-12-31') >= now[:10]
                reason = ('缺号补位' if placeholder else '未匹配本次数据' if flags is None else '不属于催办范围' if fields.get('学员状态') in ('退课','异动','未加') or student.get('roster_status','') not in ('','在读')
                          else '完课或作业数据缺失' if 'U' in flags.values()
                          else '免催中' if leave else '已完成' if not course and not homework
                          else '姓名或备注缺失' if not student['name'] or not remark.strip()
                          else '微信未添加' if fields.get('微信') != '是' else '')
                snap = dict(courses=course,homework=homework,missing_total=missing,completed_total=completed,
                            completed_courses='' if placeholder or learning is None else learning['completed_courses'],
                            completed_homework='' if placeholder or learning is None else learning['completed_homework'],
                            position=position,priority=0 if not course and homework else 1,
                            source_sync=(student.get('last_sync_at') or '') if flags is not None else '',matched=flags is not None,
                            exemption_end=student.get('exemption_date') or '',exemption_date=student.get('exemption_date') or '',is_placeholder=placeholder,
                            roster_status=student.get('roster_status',''),wechat=fields.get('微信',''))
                message = template.format(**{'姓名':student['name'],'欠课':course or '无','欠作业':homework or '无','欠交合计':missing,'完成合计':completed})
                conn.execute('INSERT INTO campaign_students VALUES(?,?,?,?,?,?,?,?,?,NULL)',
                             (batch,sid,student['name'],remark,json.dumps(snap,ensure_ascii=False),int(not reason),reason,message,'待发送' if not reason else '不发送'))
        return batch

    def refresh_latest_learning(self):
        """Follow the newest batch with the current learning data; older snapshots stay frozen.

        Membership, feedback, drafts, exemption and send state are never touched here, and a student
        missing from this fetch keeps the data already obtained instead of being blanked.
        """
        batches = self.batches()
        if not batches:return 0
        latest = batches[0]['id']
        source = self.repo.learning_source()
        if not source:return 0
        student_list = self.repo.list_students()
        students = {r['student_id']:r for r in student_list}
        refreshed = 0
        with self.db.connect() as conn:
            batch = list(conn.execute('SELECT student_id,snapshot FROM campaign_students WHERE batch_id=?',(latest,)))
            stamps = [students.get(r['student_id'],{}).get('last_sync_at') or '' for r in batch if r['student_id'] in source]
            for record in batch:
                flags = source.get(record['student_id'])
                if flags is None:continue
                learning = learning_snapshot(flags)
                learning['source_sync'] = students.get(record['student_id'],{}).get('last_sync_at') or ''
                snapshot = json.loads(record['snapshot'])
                if all(snapshot.get(key) == value for key,value in learning.items()):continue
                snapshot.update(learning)
                conn.execute('UPDATE campaign_students SET snapshot=? WHERE batch_id=? AND student_id=?',
                             (json.dumps(snapshot,ensure_ascii=False),latest,record['student_id']))
                refreshed += 1
            stamp = (max(stamps) if stamps else datetime.now().isoformat(timespec='seconds')) if refreshed else ''
            if refreshed:
                # 最新批次的时间跟随最近一次获取；历史批次的时间不动。
                conn.execute('UPDATE campaigns SET created_at=? WHERE id=?',(stamp,latest))
            # A missing dashboard row is not resurrected: 丢失快照仍显示"无法准确还原"。
            row = conn.execute('SELECT data FROM campaign_dashboards WHERE batch_id=?',(latest,)).fetchone()
            if row and stamps:
                stored = json.loads(row['data'])
                data = learning_dashboard(student_list,source)
                if refreshed:
                    data['refreshed_at'] = stamp
                elif stored.get('refreshed_at'):
                    data['refreshed_at'] = stored['refreshed_at']
                if stored != data:
                    conn.execute('UPDATE campaign_dashboards SET data=? WHERE batch_id=?',(json.dumps(data,ensure_ascii=False),latest))
        return refreshed

    def sync_current_identity(self):
        """Only the newest batch follows current identity; prior snapshots are frozen."""
        with self.db.connect() as conn:
            latest=conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]
            if latest is None:return
            rows=list(conn.execute('''SELECT c.student_id,c.name AS snapshot_name,c.snapshot,r.name,r.status,r.is_placeholder,p.fields
                FROM campaign_students c JOIN class_roster r ON r.student_id=c.student_id
                LEFT JOIN profiles p ON p.student_id=c.student_id WHERE c.batch_id=?''',(latest,)))
            for row in rows:
                snap=json.loads(row['snapshot'])
                fields=json.loads(row['fields'] or '{}')
                status='已退课' if row['is_placeholder'] else row['status']
                wechat=fields.get('微信','')
                if row['snapshot_name']==row['name'] and snap.get('roster_status')==status and snap.get('wechat')==wechat:
                    continue
                snap.update(roster_status=status,wechat=wechat)
                conn.execute('UPDATE campaign_students SET name=?,snapshot=? WHERE batch_id=? AND student_id=?',
                             (row['name'],json.dumps(snap,ensure_ascii=False),latest,row['student_id']))

    def rows(self, batch, student_id=None):
        self.sync_current_identity()
        with self.db.connect() as conn:
            latest = conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]
            current_students = {}
            if batch == latest:
                query = '''SELECT s.student_id,e.exemption_date,r.status AS roster_status,
                    r.active,r.is_placeholder FROM students s LEFT JOIN class_roster r ON r.student_id=s.student_id
                    LEFT JOIN exemptions e ON e.student_id=s.student_id'''
                current_students = {r['student_id']: r for r in conn.execute(query + (' WHERE s.student_id=?' if student_id else ''), (student_id,) if student_id else ())}
            clause=' AND student_id=?' if student_id is not None else ''
            args=(batch,student_id) if student_id is not None else (batch,)
            feedback = {}
            for r in conn.execute('SELECT * FROM campaign_feedback WHERE batch_id=?'+clause+' ORDER BY id',args):
                feedback.setdefault(r['student_id'],[]).append(dict(r))
            drafts = {r['student_id']:r['content'] for r in conn.execute('SELECT * FROM campaign_drafts WHERE batch_id=?'+clause,args)}
            rows = []
            for record in conn.execute('SELECT * FROM campaign_students WHERE batch_id=?'+clause,args):
                item = dict(record)
                item.update(json.loads(item.pop('snapshot')))
                if 'completed_courses' not in item or 'completed_homework' not in item:
                    totals=str(item.get('completed_total') or '').split('/',1)
                    item.setdefault('completed_courses',totals[0] if len(totals)==2 else '')
                    item.setdefault('completed_homework',totals[1] if len(totals)==2 else '')
                entries = feedback.get(item['student_id'],[])
                item['feedback'] = '\n'.join(r['content'] for r in entries)
                item['reply_state'] = '—' if item.get('is_placeholder') or not item['name'].strip() else '已回复' if any(is_reply(r['content'], r['kind']) for r in entries) else '未回复' if entries else '待反馈'
                item['draft'] = drafts.get(item['student_id'],'')
                replies = '\n'.join(r['content'] for r in entries)
                item['feedback_edit'] = '\n'.join(v for v in (replies, item['draft']) if v)
                if batch == latest:
                    student = current_students.get(item['student_id'])
                    value=(student['exemption_date'] or '') if student else ''
                    leave = bool(value and value >= date.today().isoformat())
                    item['exemption_date'] = value
                    item['current_eligible'] = bool((item['eligible'] or item['reason'] in ('免催中','微信未添加')) and student and not leave and item.get('wechat')=='是'
                        and student['roster_status'] in (None,'','在读') and student['active'] != 0 and not student['is_placeholder'])
                value=item.get('exemption_date',item.get('exemption_end','')) or ''
                item.update(exemption_date=value,exemption_text=format_exemption(value),exemption_expired=bool(value and value < date.today().isoformat()))
                rows.append(item)
            return sorted(rows,key=lambda r:(r['priority'],r['position']))

    def simulate(self, batch, failures=False):
        """Local simulation only. Never dispatches messages to any external system."""
        eligible_ids={r['student_id'] for r in self.rows(batch) if r.get('current_eligible',r['eligible'])}
        with self.db.connect() as conn:
            pending = list(conn.execute("SELECT student_id FROM campaign_students WHERE batch_id=? AND (send_state IN ('待发送','待模拟','模拟失败') OR (send_state='不发送' AND reason IN ('免催中','微信未添加'))) ORDER BY student_id",(batch,)))
            for i, row in enumerate(pending):
                member=conn.execute('SELECT status,is_placeholder,active FROM class_roster WHERE student_id=?',(row['student_id'],)).fetchone()
                if member and (member['is_placeholder'] or not member['active'] or member['status'] not in ('','在读')):
                    conn.execute("UPDATE campaign_students SET send_state='不发送',reason='当前学籍状态不在催办范围' WHERE batch_id=? AND student_id=?",(batch,row['student_id']))
                    continue
                current = conn.execute('SELECT exemption_date FROM exemptions WHERE student_id=?',(row['student_id'],)).fetchone()
                if current and current['exemption_date'] >= date.today().isoformat():
                    conn.execute("UPDATE campaign_students SET send_state='不发送',reason='免催中' WHERE batch_id=? AND student_id=?",(batch,row['student_id']))
                    continue
                if row['student_id'] not in eligible_ids:continue
                profile=conn.execute('SELECT fields FROM profiles WHERE student_id=?',(row['student_id'],)).fetchone()
                if not profile or json.loads(profile['fields']).get('微信')!='是':continue
                conn.execute("UPDATE campaign_students SET eligible=1,send_state=?,sent_at=?,reason=CASE WHEN reason IN ('免催中','微信未添加') THEN '' ELSE reason END WHERE batch_id=? AND student_id=?",
                             ('模拟失败' if failures and (i+1)%5==0 else '模拟成功', datetime.now().isoformat(timespec='seconds'),batch,row['student_id']))
            return len(pending)

    def draft(self,batch,sid,content):
        with self.db.connect() as conn:
            self._feedback_member(conn,batch,sid)
            conn.execute('INSERT INTO campaign_drafts VALUES(?,?,?) ON CONFLICT(batch_id,student_id) DO UPDATE SET content=excluded.content',(batch,sid,content))

    @staticmethod
    def _feedback_member(conn,batch,sid):
        latest=conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]
        row=conn.execute('''SELECT s.name,s.snapshot,r.is_placeholder AS current_placeholder
            FROM campaign_students s LEFT JOIN class_roster r ON r.student_id=s.student_id
            WHERE s.batch_id=? AND s.student_id=?''',(batch,sid)).fetchone()
        if batch != latest or not row or not row['name'].strip() or json.loads(row['snapshot']).get('is_placeholder') or row['current_placeholder']:
            raise ValueError('仅最新批次的真实学员可以登记反馈')

    def submit(self,batch,sid,content):
        if not content.strip():
            raise ValueError('请先粘贴反馈文字')
        with self.db.connect() as conn:
            self._feedback_member(conn,batch,sid)
            conn.execute('INSERT INTO campaign_feedback(batch_id,student_id,content,kind) VALUES(?,?,?,?)',(batch,sid,content.strip(),feedback_kind(content)))
            conn.execute('DELETE FROM campaign_drafts WHERE batch_id=? AND student_id=?',(batch,sid))

    def save_feedback(self, batch, sid, content):
        """Replace this batch's editable feedback, preserving all other batches."""
        with self.db.connect() as conn:
            self._feedback_member(conn, batch, sid)
            conn.execute('DELETE FROM campaign_feedback WHERE batch_id=? AND student_id=?', (batch, sid))
            if content.strip():
                conn.execute('INSERT INTO campaign_feedback(batch_id,student_id,content,kind) VALUES(?,?,?,?)',
                             (batch, sid, content, feedback_kind(content)))
            conn.execute('DELETE FROM campaign_drafts WHERE batch_id=? AND student_id=?', (batch, sid))

    def mark_unreplied(self,batch,student_ids=None):
        with self.db.connect() as conn:
            if batch != conn.execute('SELECT max(id) FROM campaigns').fetchone()[0]:
                raise ValueError('历史批次不可修改反馈')
            requested=None if student_ids is None else set(student_ids)
            if requested is not None and not requested:return 0
            candidates=[]
            for row in conn.execute('''SELECT s.student_id,s.name,s.snapshot,r.is_placeholder AS current_placeholder,
                d.content AS draft FROM campaign_students s
                LEFT JOIN class_roster r ON r.student_id=s.student_id
                LEFT JOIN campaign_drafts d ON d.batch_id=s.batch_id AND d.student_id=s.student_id
                WHERE s.batch_id=? AND NOT EXISTS(SELECT 1 FROM campaign_feedback f
                    WHERE f.batch_id=s.batch_id AND f.student_id=s.student_id)''',(batch,)):
                if requested is not None and row['student_id'] not in requested:continue
                if not row['name'].strip() or row['current_placeholder'] or json.loads(row['snapshot']).get('is_placeholder'):continue
                if (row['draft'] or '').strip():continue
                candidates.append(row['student_id'])
            conn.executemany('INSERT INTO campaign_feedback(batch_id,student_id,content,kind) VALUES(?,?,?,?)',[(batch,sid,'未回复','unreplied') for sid in candidates])
            return len(candidates)
