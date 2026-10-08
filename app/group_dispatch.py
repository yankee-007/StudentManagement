"""Independent persisted name/message lists, linked to campaigns only when sourced there."""
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from collections import Counter
from . import sending_store as source
from .send_options import normalize
from .message_content import prepare_content, render_content, describe, file_versions


class GroupStore:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as conn:
            conn.executescript('''
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                kind TEXT NOT NULL, source_path TEXT, source_batch INTEGER,
                prefix TEXT NOT NULL DEFAULT '', options TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY, list_id INTEGER NOT NULL REFERENCES lists(id),
                name TEXT NOT NULL, message TEXT NOT NULL, source_sid TEXT,
                learning_data TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT '待发送',
                detail TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
                source_attempt INTEGER, sync_pending INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL REFERENCES recipients(id),
                contact TEXT NOT NULL, message TEXT NOT NULL, options TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT, result TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
            ''')
            for table,columns in {'lists':{'content_template':"TEXT NOT NULL DEFAULT '[]'"},'recipients':{'content':"TEXT NOT NULL DEFAULT '[]'",'base_message':"TEXT NOT NULL DEFAULT ''"},'attempts':{'content':"TEXT NOT NULL DEFAULT '[]'"}}.items():
                existing={r[1] for r in conn.execute(f'PRAGMA table_info({table})')}
                for name,kind in columns.items():
                    if name not in existing:conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
            conn.execute("UPDATE recipients SET base_message=message WHERE base_message='' AND content='[]'")
            conn.execute("UPDATE recipients SET state='已发送' WHERE state='已执行发送'")
            conn.execute("UPDATE attempts SET result='已发送' WHERE result='已执行发送'")

    @contextmanager
    def connect(self):
        conn=sqlite3.connect(self.path,timeout=10)
        conn.row_factory=sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            yield conn;conn.commit()
        except Exception:
            conn.rollback();raise
        finally:conn.close()

    def lists(self):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT l.*,count(r.id) AS count FROM lists l LEFT JOIN recipients r ON r.list_id=l.id GROUP BY l.id ORDER BY l.id DESC')]

    def get(self,list_id):
        with self.connect() as conn:
            row=conn.execute('SELECT * FROM lists WHERE id=?',(list_id,)).fetchone()
        return dict(row,options=normalize(json.loads(row['options'])),content_template=json.loads(row['content_template'])) if row else None

    def rows(self,list_id):
        with self.connect() as conn:
            return [dict(r) for r in conn.execute('SELECT * FROM recipients WHERE list_id=? ORDER BY id',(list_id,))]

    def create(self,title,people,source_store=None,batch=None,*,content_template=None):
        title=title.strip()
        if not title:raise ValueError('请填写名单名称')
        if not people:raise ValueError('名单为空')
        template=prepare_content(content_template) if content_template else []
        names=[];contents=[]
        for r in people:
            name=str(r.get('name','')).strip();message=str(r.get('message',''))
            if not name or any(c in name for c in '\r\n\0'):raise ValueError('每行必须有有效姓名')
            raw_content=r.get('content')
            content=prepare_content(raw_content or message) if (raw_content or message) else []
            if template:
                variables=dict(r.get('learning_data',{}).get('profile_fields') or {})
                variables.update({'姓名':name,'学号':r.get('learning_data',{}).get('student_id','')})
                for item in content:
                    if item['type']=='text':_ensure_resolved(item['text'],variables,name,variables.get('学号'))
            contents.append(content)
            names.append(name)
        if len(set(names))!=len(names):raise ValueError('名单内姓名重复，不能唯一定位联系人')
        with self.connect() as conn:
            result=conn.execute('INSERT INTO lists(title,created_at,kind,source_path,source_batch,options) VALUES(?,?,?,?,?,?)',
                (title,datetime.now().isoformat(timespec='seconds'),'催办名单' if source_store else '自定义名单',str(source_store.db.path.resolve()) if source_store else None,batch,json.dumps(normalize()))).lastrowid
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),result))
            for name,r,content in zip(names,people,contents):
                conn.execute('INSERT INTO recipients(list_id,name,message,source_sid,learning_data,content,base_message) VALUES(?,?,?,?,?,?,?)',
                    (result,name,describe(content),r.get('source_sid') or (r['student_id'] if source_store else None),json.dumps(r.get('learning_data',{}),ensure_ascii=False),json.dumps(content,ensure_ascii=False),r.get('message','')))
        return result

    def save_content(self,list_id,fields):
        fields=prepare_content(fields)
        updates=[]
        for row in self.rows(list_id):
            if row['state'] in source.PROTECTED:continue
            old=json.loads(row['content']) or []
            variables=json.loads(row['learning_data'] or '{}').get('profile_fields',{})
            content=[]
            for i,item in enumerate(fields):
                prior=old[i] if i<len(old) else {}
                if prior.get('personal_override'):
                    content.append(prior);continue
                if item['type']=='text':
                    raw=item.get('template',item['text'])
                    rendered=render_content([dict(type='text',text=raw)],row['name'],row['base_message'],variables)[0]
                    _ensure_resolved(rendered['text'],variables,row['name'])
                    content.append(dict(type='text',text=rendered['text'],template=raw))
                else:content.append(dict(item,template=item['path']))
            updates.append((json.dumps(content,ensure_ascii=False),describe(content),row['id']))
        if not updates:raise ValueError('当前没有可修改的待发送人员')
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('正在发送，不能修改消息')
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(fields,ensure_ascii=False),list_id))
            conn.executemany('UPDATE recipients SET content=?,message=? WHERE id=?',updates)

    def configure(self,list_id,prefix,options):
        if any(c in prefix for c in '\r\n\0'):raise ValueError('前缀不能包含换行或空字符')
        options=normalize(options)
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('名单正在发送，不能修改参数')
            conn.execute('UPDATE lists SET prefix=?,options=? WHERE id=?',(prefix,json.dumps(options),list_id))

    def save_default_row(self,list_id,fields,template,override_personal=False):
        """Apply a complete draft in one transaction, retaining unchanged variants."""
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=list(conn.execute('SELECT * FROM recipients WHERE list_id=? ORDER BY id',(list_id,)))
            if any(row['state']==source.RUNNING for row in rows):raise ValueError('发送期间不能修改消息')
            editable=[row for row in rows if row['state'] not in source.PROTECTED]
            if not editable:raise ValueError('当前没有可修改的待发送人员')
            updates=[]
            for row in editable:
                old=json.loads(row['content']) or []
                if not old and row['message']:old=[dict(type='text',text=row['message'])]
                variables=json.loads(row['learning_data'] or '{}').get('profile_fields',{})
                content=[]
                for field in fields:
                    index=field['sourceIndex']
                    prior=old[index] if 0<=index<len(old) else None
                    replacement=field['item']
                    if replacement is None or (prior and prior.get('personal_override') and not override_personal):
                        if prior:content.append(prior)
                        continue
                    if replacement['type']=='text':
                        raw=replacement['text']
                        item=render_content([replacement],row['name'],row['base_message'],variables)[0]
                        _ensure_resolved(item['text'],variables,row['name'],variables.get('学号'))
                        content.append(dict(type='text',text=item['text'],template=raw))
                    else:content.append(dict(replacement,template=replacement['path']))
                updates.append((json.dumps(content,ensure_ascii=False),describe(content),row['id']))
            # Validate every recipient before writing any content or template.
            conn.executemany('UPDATE recipients SET content=?,message=? WHERE id=?',updates)
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),list_id))
        return len(updates)

    def save_recipient_content(self,list_id,recipient_id,fields):
        content=prepare_content(fields)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT state FROM recipients WHERE id=? AND list_id=?',(recipient_id,list_id)).fetchone()
            if not row:raise ValueError('人员不属于当前名单')
            if row['state'] in source.PROTECTED:raise ValueError('已发送、发送中或待核实的消息不可修改')
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('发送期间不能修改消息')
            content=[dict(item,template=item.get('template',item.get('text',item.get('path',''))),personal_override=True) for item in content]
            conn.execute('UPDATE recipients SET content=?,message=? WHERE id=? AND list_id=?',
                         (json.dumps(content,ensure_ascii=False),describe(content),recipient_id,list_id))

    def save_recipient_field(self,list_id,recipient_id,index,item):
        value=prepare_content([item])[0]
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM recipients WHERE id=? AND list_id=?',(recipient_id,list_id)).fetchone()
            if not row:raise ValueError('人员不属于当前名单')
            if row['state'] in source.PROTECTED:raise ValueError('该学员当前发送状态不允许修改消息')
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():
                raise ValueError('发送期间不能修改消息')
            items=json.loads(row['content']) or []
            if not 0<=index<len(items):raise ValueError('消息字段已变化，请重新选择单元格')
            if value['type']=='text':
                raw=value['text']
                learning=json.loads(row['learning_data'] or '{}')
                variables=learning.get('profile_fields',{})
                rendered=render_content([dict(type='text',text=raw)],row['name'],row['base_message'],variables)[0]
                _ensure_resolved(rendered['text'],variables,row['name'],learning.get('student_id'))
                value=dict(type='text',text=rendered['text'],template=raw,personal_override=True)
            else:value=dict(type='file',path=value['path'],template=value['path'],personal_override=True)
            items[index]=value
            conn.execute('UPDATE recipients SET content=?,message=? WHERE id=? AND list_id=?',
                         (json.dumps(items,ensure_ascii=False),describe(items),recipient_id,list_id))

    def copy_list(self,list_id,title,copy_messages=True):
        title=title.strip()
        if not title:raise ValueError('请填写新批次名称')
        job=self.get(list_id)
        if not job:raise ValueError('原批次不存在')
        originals=self.rows(list_id);people=[]
        raw_template=job.get('content_template') or []
        if copy_messages and not raw_template and job.get('source_path') and job.get('source_batch'):
            try:
                with sqlite3.connect(job['source_path']) as source_db:
                    legacy=source_db.execute('SELECT template FROM campaigns WHERE id=?',(job['source_batch'],)).fetchone()
                if legacy and legacy[0]:raw_template=[dict(type='text',text=legacy[0])]
            except sqlite3.Error:
                pass
        for row in originals:
            learning=json.loads(row['learning_data'] or '{}')
            variables=dict(learning.get('profile_fields') or {})
            copy_name=row['name']
            sid=learning.get('student_id') or row.get('source_sid')
            db_path=learning.get('profile_path') or job.get('source_path')
            if sid and db_path and not Path(db_path).is_file() and copy_messages:
                raise ValueError(f'学员画像数据库不可用（{sid}），无法刷新变量，未创建新批次')
            if sid and db_path and Path(db_path).is_file():
                from .database import Database
                from .repository import StudentRepository
                current=StudentRepository(Database(db_path)).get(sid)
                if current:
                    copy_name=current.get('name') or copy_name
                    variables=dict(current.get('profile_fields') or {})
                    variables.update({'学号':sid,'姓名':copy_name,'状态':current.get('roster_status',current.get('status','')),
                                      '免催日期':current.get('exemption_text','')})
                    variables.update({'欠课':','.join(current.get('pending_courses',[])),
                                      '欠作业':','.join(current.get('pending_homework',[])),
                                      '欠交合计':f"{len(current.get('pending_courses',[]))}/{len(current.get('pending_homework',[]))}"})
                    completed_courses=variables.get('合计完课','')
                    completed_homework=variables.get('合计作业','')
                    if completed_courses or completed_homework:
                        variables.setdefault('完成合计',f'{completed_courses}/{completed_homework}')
                    variables.setdefault('欠课',variables.get('差的课程',''))
                    variables.setdefault('欠作业',variables.get('差的作业',''))
                elif copy_messages:
                    raise ValueError(f"无法匹配学员 {sid}，未创建新批次")
            row_template=raw_template
            if not row_template:
                legacy_content=json.loads(row['content']) or []
                if not legacy_content and row['message']:legacy_content=[dict(type='text',text=row['message'])]
                row_template=[dict(i) for i in legacy_content] if copy_messages else []
                for item in row_template:
                    if item.get('type')=='text':item['text']=item.get('template',item['text'])
                    item.pop('personal_override',None)
            content=[]
            if copy_messages:
                previous=json.loads(row['content']) or []
                for index in range(max(len(row_template),len(previous))):
                    item=row_template[index] if index<len(row_template) else previous[index]
                    is_personal=index<len(previous) and bool(previous[index].get('personal_override'))
                    prior=previous[index] if index<len(previous) else {}
                    source_item=prior if (is_personal or 'template' in prior) else item
                    if source_item['type']=='text':
                        raw=source_item.get('template',source_item.get('text',item.get('text','')))
                        rendered=render_content([dict(type='text',text=raw)],copy_name,row['base_message'],variables)[0]
                        _ensure_resolved(rendered['text'],variables,copy_name,sid)
                        content.append(dict(type='text',text=rendered['text'],template=raw,**({'personal_override':True} if is_personal else {})))
                    else:
                        path=source_item.get('path',item.get('path',''))
                        content.append(dict(type='file',path=path,template=source_item.get('template',path),**({'personal_override':True} if is_personal else {})))
            if sid:
                learning.update(student_id=sid)
                if db_path:learning['profile_path']=db_path
                learning['profile_fields']=variables
            people.append(dict(name=copy_name,content=content,
                               message=row['base_message'],learning_data=learning,source_sid=row['source_sid']))
        new_id=self.create(title,people,content_template=raw_template if copy_messages else [])
        return new_id

    def bulk_field(self,list_id,index,item,*,override_personal=False):
        item=prepare_content([item])[0]
        rows=self.rows(list_id)
        if index<0:raise ValueError('消息字段位置无效')
        updates=[]
        for row in rows:
            if row['state'] in source.PROTECTED:continue
            items=json.loads(row['content']) or []
            if index>=len(items):continue
            if items[index].get('personal_override') and not override_personal:continue
            if item['type']=='text':
                learning=json.loads(row['learning_data'] or '{}');variables=learning.get('profile_fields',{})
                raw=item.get('template',item['text'])
                rendered=render_content([dict(type='text',text=raw)],row['name'],row['base_message'],variables)[0]
                _ensure_resolved(rendered['text'],variables,row['name'],learning.get('student_id'))
                value=dict(type='text',text=rendered['text'],template=raw)
            else:value=dict(type='file',path=item['path'],template=item['path'])
            items[index]=value
            updates.append((json.dumps(items,ensure_ascii=False),describe(items),row['id']))
        if not updates:raise ValueError('本列没有可修改的待发送人员')
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('发送期间不能编辑')
            conn.executemany('UPDATE recipients SET content=?,message=? WHERE id=?',updates)
            job=conn.execute('SELECT content_template FROM lists WHERE id=?',(list_id,)).fetchone()
            template=json.loads(job[0] or '[]') if job else []
            while len(template)<=index:template.append(dict(item))
            template[index]=dict(item)
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),list_id))
        return len(updates)

    def append_field(self,list_id,item):
        item=prepare_content([item])[0];count=0
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('发送期间不能编辑')
            rows=list(conn.execute("SELECT * FROM recipients WHERE list_id=? AND state NOT IN (%s)" % ','.join('?'*len(source.PROTECTED)),(list_id,*source.PROTECTED)))
            for row in rows:
                items=json.loads(row['content']) or []
                value=dict(item,template=item.get('text',item.get('path','')))
                if value['type']=='text':
                    learning=json.loads(row['learning_data'] or '{}');raw=value['text']
                    rendered=render_content([dict(type='text',text=raw)],row['name'],row['base_message'],learning.get('profile_fields',{}))[0]
                    _ensure_resolved(rendered['text'],learning.get('profile_fields',{}),row['name'],learning.get('student_id'))
                    value['text']=rendered['text']
                items.append(value);count+=1
                conn.execute('UPDATE recipients SET content=?,message=? WHERE id=?',(json.dumps(items,ensure_ascii=False),describe(items),row['id']))
            if not count:raise ValueError('当前没有可新增字段的待发送人员')
            job=conn.execute('SELECT content_template FROM lists WHERE id=?',(list_id,)).fetchone()
            template=json.loads(job[0] or '[]') if job else []
            template.append(item)
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),list_id))
        return count

    def remove_field(self,list_id,index):
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('发送期间不能编辑')
            rows=list(conn.execute("SELECT * FROM recipients WHERE list_id=? AND state NOT IN (%s)" % ','.join('?'*len(source.PROTECTED)),(list_id,*source.PROTECTED)))
            if not rows:raise ValueError('当前没有可调整的待发送人员')
            for row in rows:
                items=json.loads(row['content']) or []
                if 0<=index<len(items):items.pop(index)
                conn.execute('UPDATE recipients SET content=?,message=? WHERE id=?',(json.dumps(items,ensure_ascii=False),describe(items),row['id']))
            job=conn.execute('SELECT content_template FROM lists WHERE id=?',(list_id,)).fetchone()
            template=json.loads(job[0] or '[]') if job else []
            if 0<=index<len(template):template.pop(index)
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),list_id))

    def move_field(self,list_id,index,direction):
        target=index+direction
        if index<0 or target<0:raise ValueError('消息字段位置无效')
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM recipients WHERE list_id=? AND state='发送中'",(list_id,)).fetchone():raise ValueError('发送期间不能编辑')
            rows=list(conn.execute("SELECT * FROM recipients WHERE list_id=? AND state NOT IN (%s)" % ','.join('?'*len(source.PROTECTED)),(list_id,*source.PROTECTED)))
            if not rows:raise ValueError('当前没有可调整的待发送人员')
            for row in rows:
                items=json.loads(row['content']) or []
                if target<len(items):items[index],items[target]=items[target],items[index]
                conn.execute('UPDATE recipients SET content=?,message=? WHERE id=?',(json.dumps(items,ensure_ascii=False),describe(items),row['id']))
            job=conn.execute('SELECT content_template FROM lists WHERE id=?',(list_id,)).fetchone()
            template=json.loads(job[0] or '[]') if job else []
            if target<len(template):template[index],template[target]=template[target],template[index]
            conn.execute('UPDATE lists SET content_template=? WHERE id=?',(json.dumps(template,ensure_ascii=False),list_id))


    @staticmethod
    def origin(job):
        if not job['source_path']:return None
        from .database import Database
        from .repository import StudentRepository
        from .campaigns import CampaignStore
        if not Path(job['source_path']).is_file():raise ValueError('来源班级数据库不存在，未发送')
        db=Database(job['source_path'])
        return CampaignStore(db,StudentRepository(db))

    def plan(self,list_id):
        job=self.get(list_id)
        if not job:raise ValueError('请选择群发名单')
        origin=self.origin(job)
        eligible=None
        if origin:
            if not origin.batches() or origin.batches()[0]['id']!=job['source_batch']:
                raise ValueError('来源催办已成为历史批次，请在当前催办重新生成名单')
            source_rows=origin.rows(job['source_batch'])
            counts=Counter(r['name'].strip() for r in source_rows if r['name'].strip())
            eligible={r['student_id']:r for r in source_rows if r.get('current_eligible') and r['send_state'] not in source.PROTECTED}
        result=[]
        for r in self.rows(list_id):
            if r['state'] in source.PROTECTED:continue
            if eligible is not None and (r['source_sid'] not in eligible or eligible[r['source_sid']]['name']!=r['name']):continue
            if eligible is not None and counts[r['name']]!=1:raise ValueError('来源班级出现同名学员，请核实名单后重新生成')
            raw_content=json.loads(r['content'])
            if not raw_content and r['message']:raw_content=[dict(type='text',text=r['message'])]
            if not raw_content:raise ValueError(f"{r['name']} 尚未配置消息字段，不能预览发送")
            content=prepare_content(raw_content)
            for item in content:
                if item['type']=='text':_ensure_resolved(item['text'],json.loads(r['learning_data'] or '{}').get('profile_fields',{}),r['name'],r.get('source_sid'))
            result.append(dict(student_id=str(r['id']),name=r['name'],contact=job['prefix']+r['name'],message=r['message'],content=content,file_versions=file_versions(content),learning_data=json.loads(r['learning_data'])))
        counts=Counter(r['contact'] for r in result)
        if any(n>1 for n in counts.values()):raise ValueError('联系人备注重复，未发送')
        return result

    def claim(self,list_id,task):
        if task not in self.plan(list_id):return None
        job=self.get(list_id)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row=conn.execute('SELECT * FROM recipients WHERE id=? AND list_id=?',(task['student_id'],list_id)).fetchone()
            if not row or row['state'] in source.PROTECTED:return None
            attempt=conn.execute('INSERT INTO attempts(recipient_id,contact,message,options,started_at,result,content) VALUES(?,?,?,?,?,?,?)',
                (row['id'],task['contact'],task['message'],json.dumps(job['options']),datetime.now().isoformat(timespec='seconds'),source.RUNNING,json.dumps(task['content'],ensure_ascii=False))).lastrowid
            conn.execute('UPDATE recipients SET state=?,contact=?,detail=?,source_attempt=NULL,sync_pending=0 WHERE id=?',(source.RUNNING,task['contact'],'正在处理',row['id']))
        origin=self.origin(job)
        if origin:
            origin_task={**task,'student_id':row['source_sid']}
            source_attempt=source.claim_snapshot(origin,job['source_batch'],origin_task)
            if source_attempt is None:
                self.finish(list_id,task,attempt,source.FAILED,'来源条件已变化或已被其他名单处理，未发送')
                return None
            with self.connect() as conn:
                conn.execute('UPDATE recipients SET source_attempt=? WHERE id=?',(source_attempt,row['id']))
        return attempt

    def finish(self,list_id,task,attempt,result,detail):
        with self.connect() as conn:
            conn.execute('UPDATE attempts SET result=?,detail=?,finished_at=? WHERE id=?',(result,detail,datetime.now().isoformat(timespec='seconds'),attempt))
            conn.execute('UPDATE recipients SET state=?,detail=?,sync_pending=CASE WHEN source_attempt IS NOT NULL THEN 1 ELSE 0 END WHERE id=? AND list_id=?',
                (result,detail,task['student_id'],list_id))
        self.sync_results(task['student_id'])

    def sync_results(self,recipient_id=None):
        with self.connect() as conn:
            query='SELECT * FROM recipients WHERE sync_pending=1'
            rows=[dict(r) for r in conn.execute(query+(' AND id=?' if recipient_id is not None else ''),(recipient_id,) if recipient_id is not None else ())]
        for row in rows:
            job=self.get(row['list_id'])
            origin=self.origin(job)
            with origin.db.connect() as conn:
                latest=conn.execute('SELECT max(id) FROM send_attempts WHERE batch_id=? AND student_id=?',(job['source_batch'],row['source_sid'])).fetchone()[0]
            if latest!=row['source_attempt']:raise ValueError('来源存在更新的发送记录，停止回写，需人工核查')
            with self.connect() as conn:
                last=conn.execute('SELECT finished_at FROM attempts WHERE recipient_id=? ORDER BY id DESC LIMIT 1',(row['id'],)).fetchone()
            source.finish(origin,job['source_batch'],dict(student_id=row['source_sid']),row['source_attempt'],row['state'],row['detail'],finished_at=last[0] if last else None)
            with self.connect() as conn:conn.execute('UPDATE recipients SET sync_pending=0 WHERE id=?',(row['id'],))

    def recover(self):
        with self.connect() as conn:
            conn.execute("UPDATE attempts SET result=?,detail='中断，需人工核实' WHERE result=?",(source.UNKNOWN,source.RUNNING))
            conn.execute("UPDATE recipients SET state=?,detail='中断，需人工核实',sync_pending=CASE WHEN source_attempt IS NOT NULL THEN 1 ELSE 0 END WHERE state=?",(source.UNKNOWN,source.RUNNING))
        self.sync_results()

    def resolve(self,list_id,recipient_id,was_sent):
        with self.connect() as conn:
            row=conn.execute('SELECT * FROM recipients WHERE list_id=? AND id=?',(list_id,recipient_id)).fetchone()
            if not row or row['state'] not in (source.UNKNOWN,'仅粘贴未发送'):raise ValueError('只可核实结果待确认或仅粘贴的记录')
            state=source.SENT if was_sent else source.FAILED
            detail='人工核实：已发送' if was_sent else '人工核实：未发送，可重新预览'
            conn.execute('UPDATE recipients SET state=?,detail=?,sync_pending=CASE WHEN source_attempt IS NOT NULL THEN 1 ELSE 0 END WHERE id=?',(state,detail,recipient_id))
            conn.execute("UPDATE attempts SET detail=detail || '；' || ? WHERE id=(SELECT max(id) FROM attempts WHERE recipient_id=?)",(detail,recipient_id))
        self.sync_results(recipient_id)


def claim(store,batch,task):return store.claim(batch,task)
def finish(store,batch,task,attempt,result,detail):return store.finish(batch,task,attempt,result,detail)

def _ensure_resolved(text,variables,name,sid=''):
    missing=sorted(set(re.findall(r'\{([^{}]+)\}',text)))
    if missing:raise ValueError(f"{('学员 '+str(sid)+' ' if sid else '')}{name}缺少变量字段："+'、'.join(missing)+'；未应用更改')
