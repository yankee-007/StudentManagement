"""Durable per-student dispatch receipts; no desktop automation in this module."""
import json
from collections import Counter
from datetime import datetime

SENT = '已发送'
UNKNOWN = '结果待确认'
FAILED = '未发送失败'
RUNNING = '发送中'
PROTECTED = (SENT, '已执行发送', UNKNOWN, RUNNING, '仅粘贴未发送')


def initialize(db):
    with db.connect() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS campaign_send_config (
            batch_id INTEGER PRIMARY KEY REFERENCES campaigns(id), prefix TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS send_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id INTEGER NOT NULL, student_id TEXT NOT NULL,
            contact TEXT NOT NULL, message TEXT NOT NULL,
            started_at TEXT NOT NULL, finished_at TEXT, result TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '',
            FOREIGN KEY(batch_id,student_id) REFERENCES campaign_students(batch_id,student_id));
        ''')


def recover(db):
    """Called only when no sender owns this database; never retry interrupted sends."""
    initialize(db)
    with db.connect() as conn:
        conn.execute("UPDATE send_attempts SET result=?,detail='程序中断，需人工核对企业微信；不会自动重发' WHERE result=?",(UNKNOWN,RUNNING))
        conn.execute("UPDATE campaign_students SET send_state=?,reason='程序中断，发送结果待人工核对' WHERE send_state=?",(UNKNOWN,RUNNING))


def config(store,batch):
    initialize(store.db)
    with store.db.connect() as conn:
        row=conn.execute('SELECT template FROM campaigns WHERE id=?',(batch,)).fetchone()
        prefix=conn.execute('SELECT prefix FROM campaign_send_config WHERE batch_id=?',(batch,)).fetchone()
    return {'template':row[0] if row else '', 'prefix':prefix[0] if prefix else ''}


def render(template,row):
    message=template.format(**{'姓名':row['name'],'欠课':row['courses'] or '无',
        '欠作业':row['homework'] or '无','欠交合计':row['missing_total'],'完成合计':row['completed_total']})
    if not message.strip() or '\0' in message:raise ValueError('消息不能为空或包含空字符')
    return message


def save_config(store,batch,prefix,template):
    if not store.batches() or batch!=store.batches()[0]['id']:raise ValueError('历史批次不能配置发送')
    if any(c in prefix for c in '\r\n\0'):raise ValueError('前缀不能包含换行或空字符')
    template=template.strip()
    try:render(template,dict(name='测试',courses='1',homework='2',missing_total='1/1',completed_total='2/2'))
    except (KeyError,IndexError,ValueError) as exc:raise ValueError('请检查话术及变量：姓名、欠课、欠作业、欠交合计、完成合计') from exc
    rows=store.rows(batch)
    messages=[(render(template,r),batch,r['student_id']) for r in rows if r['send_state'] not in PROTECTED]
    initialize(store.db)
    with store.db.connect() as conn:
        conn.execute('INSERT INTO campaign_send_config VALUES(?,?) ON CONFLICT(batch_id) DO UPDATE SET prefix=excluded.prefix',(batch,prefix))
        conn.execute('UPDATE campaigns SET template=? WHERE id=?',(template,batch))
        conn.executemany('UPDATE campaign_students SET message=? WHERE batch_id=? AND student_id=?',messages)
    store.repo.set_setting('campaign_template',template)


def plan(store,batch):
    if not store.batches() or batch!=store.batches()[0]['id']:raise ValueError('只能发送当前最新催办批次')
    settings=config(store,batch)
    rows=store.rows(batch)
    # Include non-target classmates in the collision check: same-name contacts are ambiguous.
    counts=Counter(settings['prefix']+r['name'].strip() for r in rows if r['name'].strip())
    tasks=[]
    for row in rows:
        if not row.get('current_eligible') or row['send_state'] in PROTECTED:continue
        if not any(int(v)>0 for v in row['missing_total'].split('/') if v.isdigit()):continue
        contact=settings['prefix']+row['name'].strip()
        if counts[contact]!=1:raise ValueError(f'联系人备注重复：{contact}，无法唯一对应学员，未开始发送')
        if not contact.strip() or any(c in contact for c in '\r\n\0'):raise ValueError('联系人备注无效')
        tasks.append(dict(student_id=row['student_id'],name=row['name'],contact=contact,message=render(settings['template'],row),
                          learning_data={key:row[key] for key in ('courses','homework','missing_total','completed_courses','completed_homework')}))
    missing={r['student_id']:sum(int(v) for v in r['missing_total'].split('/') if v.isdigit()) for r in rows}
    return sorted(tasks,key=lambda r:(-missing[r['student_id']],r['student_id']))


def claim(store,batch,task):
    # Revalidate exemptions, membership and WeChat immediately before each student.
    current=next((r for r in plan(store,batch) if r['student_id']==task['student_id']),None)
    if current!=task:return None
    return claim_snapshot(store,batch,task)


def claim_snapshot(store,batch,task):
    """Claim a frozen group-center payload, while rechecking source eligibility."""
    if not store.batches() or store.batches()[0]['id']!=batch:return None
    row=next(iter(store.rows(batch,task['student_id'])),None)
    if not row or not row.get('current_eligible') or row['name']!=task['name']:return None
    with store.db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT send_state FROM campaign_students WHERE batch_id=? AND student_id=?',(batch,task['student_id'])).fetchone()
        if not row or row[0] in PROTECTED:return None
        now=datetime.now().isoformat(timespec='seconds')
        attempt=conn.execute('INSERT INTO send_attempts(batch_id,student_id,contact,message,started_at,result) VALUES(?,?,?,?,?,?)',
            (batch,task['student_id'],task['contact'],task['message'],now,RUNNING)).lastrowid
        conn.execute('UPDATE campaign_students SET send_state=?,remark=?,message=? WHERE batch_id=? AND student_id=?',
            (RUNNING,task['contact'],task['message'],batch,task['student_id']))
        return attempt


def finish(store,batch,task,attempt,result,detail,finished_at=None):
    if result not in (SENT,UNKNOWN,FAILED,'仅粘贴未发送'):raise ValueError('发送结果无效')
    now=finished_at or datetime.now().isoformat(timespec='seconds')
    with store.db.connect() as conn:
        conn.execute('UPDATE send_attempts SET finished_at=?,result=?,detail=? WHERE id=?',(now,result,detail,attempt))
        conn.execute('UPDATE campaign_students SET send_state=?,sent_at=?,reason=?,eligible=1 WHERE batch_id=? AND student_id=?',
            (result,now if result==SENT else None,detail,batch,task['student_id']))


def resolve(store,batch,sid,was_sent):
    if not store.batches() or batch!=store.batches()[0]['id']:raise ValueError('历史批次不可修改')
    with store.db.connect() as conn:
        row=conn.execute('SELECT send_state FROM campaign_students WHERE batch_id=? AND student_id=?',(batch,sid)).fetchone()
        if not row or row[0]!=UNKNOWN:raise ValueError('只能人工核实结果待确认的记录')
        result=SENT if was_sent else FAILED
        detail='人工核实：已发送' if was_sent else '人工核实：未发送，可重新预览后发送'
        now=datetime.now().isoformat(timespec='seconds')
        conn.execute('UPDATE campaign_students SET send_state=?,sent_at=?,reason=? WHERE batch_id=? AND student_id=?',
            (result,now if was_sent else None,detail,batch,sid))
        conn.execute("UPDATE send_attempts SET detail=detail || '；' || ? WHERE id=(SELECT max(id) FROM send_attempts WHERE batch_id=? AND student_id=?)",(detail,batch,sid))
