"""Independent group-messaging module. Campaigns merely publish source lists."""
from pathlib import Path
import csv
import json
import hashlib
from PySide6.QtCore import QObject, Property, Signal, Slot, QCoreApplication, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog
from .group_dispatch import GroupStore
from . import group_dispatch as adapter
from . import sending_store as receipts
from .send_options import normalize
from .send_controller import F11Hotkey, SendWorker
from .message_content import render_content, prepare_content
from .qt_models import DictTableModel


class GroupCenter(QObject):
    changed=Signal()
    listsChanged=Signal()
    selectionChanged=Signal()
    rowsChanged=Signal()
    previewChanged=Signal()
    statusChanged=Signal()
    activityChanged=Signal()
    modelInfoChanged=Signal()
    def __init__(self,owner):
        super().__init__(owner)
        self.owner=owner
        path=owner.workflow.registry.db.path.parent/'group_messaging.db'
        if path.resolve() in {Path(e['path']).resolve() for e in owner.workflow._classes}:raise ValueError('群发中心数据库路径与班级数据库冲突')
        self.store=GroupStore(path)
        self._notice='选择群发名单，配置参数并预览后发送'
        try:self.store.recover()
        except Exception as exc:self._notice='有待回写结果，恢复失败：'+str(exc)
        initial_lists=self.store.lists()
        self._id=initial_lists[0]['id'] if initial_lists else 0
        self._lists_cache=[dict(r,label=f"{r['title']} · {r['count']} 人 · {r['created_at'].replace('T',' ')}") for r in initial_lists]
        self._selected_cache={}
        self._rows_cache=[]
        self._default_fields_cache=[]
        self._content_revision=''
        self._preview=[];self._confirmation=None
        self._worker=None;self._paused=False;self._pause_requested=False
        self._hotkey=F11Hotkey(self.pause)
        self._pending_model=DictTableModel([],self)
        self._sent_model=DictTableModel([],self)
        self._pending_messages=DictTableModel([],self)
        self._sent_messages=DictTableModel([],self)
        self._table_signature=None
        self.rowsChanged.connect(self._refresh_tables)
        self._reload_snapshot(notify=False)
        self._refresh_tables()
        app=QCoreApplication.instance()
        if app:app.aboutToQuit.connect(self.shutdown)

    @Property('QVariantList',notify=listsChanged)
    def lists(self):return self._lists_cache
    @Property(int,notify=selectionChanged)
    def selectedIndex(self):return next((i for i,r in enumerate(self._lists_cache) if r['id']==self._id),-1)
    @Property('QVariantMap',notify=selectionChanged)
    def selected(self):return self._selected_cache
    @Property('QVariantList',notify=rowsChanged)
    def rows(self):
        # Explicit callers receive current persisted results; QML uses table models
        # and columnInfo instead of transferring the entire roster.
        return self.store.rows(self._id)
    @Property('QVariantList',notify=previewChanged)
    def preview(self):return self._preview
    @Property(str,notify=statusChanged)
    def status(self):return self._notice
    @Property(bool,notify=activityChanged)
    def active(self):return self._worker is not None
    @Property(bool,notify=activityChanged)
    def isPaused(self):return self._paused
    @Property(bool,notify=activityChanged)
    def pauseRequested(self):return self._pause_requested

    @Property(QObject,constant=True)
    def pendingModel(self):return self._pending_model
    @Property(QObject,constant=True)
    def sentModel(self):return self._sent_model
    @Property(QObject,constant=True)
    def pendingMessageModel(self):return self._pending_messages
    @Property(QObject,constant=True)
    def sentMessageModel(self):return self._sent_messages
    @Property(int,notify=modelInfoChanged)
    def pendingCount(self):return self._pending_model.rowCount()
    @Property(int,notify=modelInfoChanged)
    def sentCount(self):return self._sent_model.rowCount()
    @Property(int,notify=modelInfoChanged)
    def pendingFieldCount(self):return max(0,len(self._pending_model.columns)-3)
    @Property(int,notify=modelInfoChanged)
    def sentFieldCount(self):return max(0,len(self._sent_model.columns)-3)

    @Property('QVariantList',notify=modelInfoChanged)
    def messageColumns(self):
        return [dict(index=index,label=column[1])
                for index,column in enumerate(self._pending_model.columns[1:-2])]

    @Property('QVariantMap',notify=rowsChanged)
    def statistics(self):
        rows=self._rows_cache
        return dict(success=sum(r['state']==receipts.SENT for r in rows),
                    failed=sum(r['state']==receipts.FAILED for r in rows),
                    pending=sum(r['state'] not in receipts.PROTECTED and r['state']!=receipts.FAILED for r in rows),
                    uncertain=sum(r['state'] in (receipts.UNKNOWN,'仅粘贴未发送') for r in rows))

    @Property(str,notify=rowsChanged)
    def contentRevision(self):
        return self._content_revision

    @Property('QVariantList',notify=rowsChanged)
    def defaultFields(self):
        return [dict(field) for field in self._default_fields_cache]

    def _build_default_fields(self):
        template=self._selected_cache.get('content_template',[])
        # selectionChanged is emitted before the table models are refreshed.
        # Build defaults from the already-reloaded snapshot of the selected list.
        rows=[]
        for row in self._rows_cache:
            if row['state'] in receipts.PROTECTED:continue
            items=json.loads(row['content']) or []
            if not items and row['message']:items=[dict(type='text',text=row['message'])]
            rows.append(dict(items=items))
        count=max(len(template),max((len(r['items']) for r in rows),default=0))
        fields=[]
        for index in range(count):
            item=template[index] if index<len(template) else None
            if item is None:
                variants={(f['type'],f.get('template',f.get('text',f.get('path',''))))
                          for r in rows if index<len(r['items'])
                          for f in [r['items'][index]] if not f.get('personal_override')}
                if len(variants)==1:
                    kind,value=next(iter(variants));item=dict(type=kind,**({'text':value} if kind=='text' else {'path':value}))
            fields.append(dict(sourceIndex=index,type=item['type'] if item else 'text',
                               value=item.get('template',item.get('text',item.get('path',''))) if item else '',
                               mixed=item is None))
        return fields

    @Slot(int,str,'QVariantList',bool,result=bool)
    def saveDefaultRow(self,list_id,revision,draft,override_personal):
        if self.active or list_id!=self._id:return False
        try:
            if revision!=self.contentRevision:raise ValueError('名单消息已变化，请重载配置后再应用；当前草稿仍保留')
            original=self.defaultFields;seen=set();fields=[];template=[];complete=True
            for raw in draft:
                field=dict(raw);index=int(field['sourceIndex'])
                if index < -1 or index>=len(original) or (index>=0 and index in seen):raise ValueError('消息位置已变化，请重载配置')
                seen.add(index)
                kind=field['type'];value=field['value']
                previous=original[index] if index>=0 else None
                changed=previous is None or previous['type']!=kind or previous['value']!=value or (override_personal and not previous['mixed'])
                item=prepare_content([dict(type=kind,**({'text':value} if kind=='text' else {'path':value}))])[0] if changed else None
                fields.append(dict(sourceIndex=index,item=item))
                if item:template.append(item)
                elif previous and not previous['mixed']:
                    template.append(dict(type=kind,**({'text':value} if kind=='text' else {'path':value})))
                else:complete=False
            count=self.store.save_default_row(list_id,fields,template if complete else [],override_personal)
            self._preview=[];self._confirmation=None
            self._notice=(f'默认消息已应用到 {count} 位待处理人员；' if count else '消息模板已保存（名单暂无待发送人员）；')+'个人改动'+('已覆盖' if override_personal else '已保留')+'，请重新预览'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='默认消息保存失败：'+str(exc);self._notify_status();return False

    @Slot(int,bool,result='QVariantMap')
    def columnInfo(self,index,include_personal):
        """Only return the small column summary, never marshal the full roster."""
        count=0
        kind='text'
        found=False
        kinds=set()
        personal_count=0
        protected_count=0
        for row in self._pending_model.rows:
            if not 0<=index<len(row['items']):continue
            item=row['items'][index]
            kinds.add(item['type'])
            if not found:kind=item['type'];found=True
            if row['editable']:
                if item.get('personal_override'):personal_count+=1
                if include_personal or not item.get('personal_override'):count+=1
            else:protected_count+=1
        return dict(type=kind,count=count,mixed=len(kinds)>1,
                    personalCount=personal_count,protectedCount=protected_count)

    @Slot(int,bool,result='QVariantMap')
    def recipientForView(self,recipient_id,sent):
        model=self._sent_model if sent else self._pending_model
        return next((row for row in model.rows if row['id']==recipient_id),{})

    def _reload_snapshot(self,*,lists=False,selection=True,notify=True):
        if lists:
            self._lists_cache=[dict(r,label=f"{r['title']} · {r['count']} 人 · {r['created_at'].replace('T',' ')}") for r in self.store.lists()]
        self._selected_cache=self.store.get(self._id) or dict(id=0,title='',prefix='',options=normalize(),kind='',content_template=[])
        self._rows_cache=self.store.rows(self._id) if self._id else []
        self._default_fields_cache=self._build_default_fields()
        snapshot=[self._id,self._selected_cache.get('content_template',[]),
                  [(r['id'],r['state'],r['content'],r['message']) for r in self._rows_cache]]
        self._content_revision=hashlib.sha256(json.dumps(snapshot,ensure_ascii=False).encode('utf-8')).hexdigest()
        if notify:
            if lists:self.listsChanged.emit()
            if selection:self.selectionChanged.emit()
            self.rowsChanged.emit()
            self.changed.emit()

    def _notify_status(self):
        self.statusChanged.emit();self.changed.emit()

    def _notify_preview(self):
        self.previewChanged.emit();self.changed.emit()

    def _notify_activity(self):
        self.activityChanged.emit();self.changed.emit()

    def _refresh_tables(self):
        source_rows=self._rows_cache
        signature=(self._id,len(self._default_fields_cache),tuple((r['id'],r['state'],r['content'],r['message'],r['detail'],r['sync_pending'],r['learning_data']) for r in source_rows))
        if signature==self._table_signature:return
        self._table_signature=signature
        rows=[]
        for source_row in source_rows:
            source_row = dict(source_row)
            ai_error = json.loads(source_row['learning_data']).get('ai_generation', {}).get('error')
            if ai_error and not json.loads(source_row['content']):
                source_row['detail'] = 'AI 生成失败（话术留空）：' + ai_error
            content=json.loads(source_row['content'])
            if not content and source_row['message']:content=[dict(type='text',text=source_row['message'])]
            row=dict(source_row,items=content,editable=source_row['state'] not in receipts.PROTECTED,
                     _record_key=str(source_row['id']))
            for i,item in enumerate(content):row['message_'+str(i)]=item.get('text',item.get('path',''))
            rows.append(row)
        for model,sent in ((self._pending_model,False),(self._sent_model,True)):
            members=[r for r in rows if (r['state']==receipts.SENT)==sent]
            columns=[('name','名字')]
            counts={'text':0,'file':0}
            for i in range(max((len(r['items']) for r in members),default=0)):
                kinds={r['items'][i]['type'] for r in members if i<len(r['items'])}
                if len(kinds)==1:
                    kind=next(iter(kinds));counts[kind]+=1
                    label=('话术' if kind=='text' else '文件')+str(counts[kind])
                else:label=f'消息{i+1}（文字/文件）'
                columns.append(('message_'+str(i),label))
            columns.extend([('state','状态'),('detail','处理说明')])
            message_model=self._sent_messages if sent else self._pending_messages
            field_count=max(1,len(columns)-3,0 if sent else len(self._default_fields_cache))
            message_columns=[('message_'+str(i),'消息'+str(i+1)) for i in range(field_count)]
            for target,target_columns in ((model,columns),(message_model,message_columns)):
                same_shape=(target.columns==target_columns and len(target.rows)==len(members)
                            and all(a['id']==b['id'] for a,b in zip(target.rows,members)))
                if same_shape:
                    for i,row in enumerate(members):
                        if target.rows[i]!=row:
                            target.rows[i]=row
                            target.dataChanged.emit(target.index(i,0),target.index(i,len(target_columns)-1))
                else:
                    target.beginResetModel();target.columns=target_columns;target.rows=members;target.endResetModel()
        self.modelInfoChanged.emit()

    @Slot(int,int,'QVariantList',result=bool)
    def saveRecipientContent(self,list_id,recipient_id,fields):
        if self.active or list_id!=self._id:return False
        try:
            self.store.save_recipient_content(list_id,recipient_id,fields)
            self._preview=[];self._confirmation=None
            self._notice='该学员消息已保存，请重新预览；其他学员未修改'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice=str(exc);self._notify_status();return False

    @Slot(int,int,int,'QVariantMap',result=bool)
    def saveRecipientField(self,list_id,recipient_id,index,item):
        if self.active or list_id!=self._id:return False
        try:
            self.store.save_recipient_field(list_id,recipient_id,index,dict(item))
            self._preview=[];self._confirmation=None
            self._notice='该学员的消息已保存，请重新预览'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='保存失败：'+str(exc);self._notify_status();return False

    @Slot(str,'QVariantList','QVariantList',result=bool)
    def createFromDailySelection(self,title,fields,record_keys):
        if self.active or self.owner.workflow.send_busy or self.owner.busy:return False
        try:
            source=self.owner.dailyWorkspace
            people=source.build_people(fields,record_keys)
            self._id=self.store.create(title,people,content_template=fields)
            try: source.store.link_list(people,self._id)
            except Exception as exc:
                self.owner.toast.emit('名单已创建，跟进关联记录未保存：'+str(exc))
            self._preview=[];self._confirmation=None
            self._notice=f'已从今日工作台创建{len(people)}人名单，尚未发送'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status()
            return True
        except Exception as exc:
            self._notice='创建失败：'+str(exc);self._notify_status();return False

    @Slot(str,'QVariantList','QVariantList',result=bool)
    def createFromProfiles(self,title,fields,record_keys):
        if self.active:return False
        try:
            profiles=self.owner.profilesModule
            if list(record_keys)!=profiles.recipientKeys:raise ValueError('班期或筛选结果已变化，请重新打开创建名单窗口')
            people=[]
            keys=set(record_keys)
            for row in profiles.tableModel.rows:
                if row['_record_key'] not in keys:continue
                variables=dict(row.get('profile_fields') or {})
                variables.update({'学号':row.get('student_id',''),'班期':row.get('class_name',''),
                                  '状态':row.get('roster_status',''),'免催日期':row.get('exemption_text','')})
                people.append(dict(name=row['name'],content=render_content(fields,row['name'],variables=variables),
                    learning_data=dict(student_id=row['student_id'],class_name=row['class_name'],profile_path=row['_db_path'],profile_fields=variables)))
            self._id=self.store.create(title,people,content_template=fields)
            self._preview=[];self._confirmation=None
            self._notice=f'已从画像筛选结果创建 {len(people)} 人的独立名单，尚未发送'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='创建失败：'+str(exc);self._notify_status();return False

    @Slot(str,'QVariantList','QVariantList',result=bool)
    def createFromLiveAbsence(self,title,fields,record_keys):
        """Independent list of the students the live-absence module is currently showing."""
        if self.active:return False
        try:
            source=self.owner.liveAbsence
            if list(record_keys)!=source.recipientKeys:raise ValueError('班级、节次或名单已变化，请重新打开生成名单窗口')
            people=source.build_people(fields)
            if not people:raise ValueError('当前没有可提醒的未进入学员')
            self._id=self.store.create(title,people,content_template=fields)
            # 每节课只提醒一次：名单真的建出来以后才写下本节的提醒标记。
            # 名单已经存在，标记失败只能提示，不能让操作者以为创建失败。
            try:source.mark_reminded([p['learning_data']['student_id'] for p in people],self._id)
            except Exception as exc:mark_error='；本节提醒标记写入失败：'+str(exc)
            else:mark_error=''
            self._preview=[];self._confirmation=None
            self._notice=f'已创建 {len(people)} 人的独立名单，尚未发送'+mark_error
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='创建失败：'+str(exc);self._notify_status();return False

    @Slot(str,'QVariantList','QVariantList',bool,result=bool)
    def createFromCampaignSelection(self,title,fields,record_keys,names_only):
        wf=self.owner.workflow
        if self.active or wf.send_busy or self.owner.busy or self.owner.termsModule.busy:return False
        try:
            if not wf.canEdit:raise ValueError('请先选择当前催办批次')
            if not record_keys or list(record_keys)!=wf.recipientKeys:
                raise ValueError('班期或筛选结果已变化，请重新打开生成名单窗口')
            people=[]
            for row in wf._model.rows:
                if not row.get('name','').strip() or row.get('is_placeholder'):continue
                profile=self.owner.repo.get(row['student_id']) or {}
                variables=dict(profile.get('profile_fields') or {})
                variables.update({'学号':row['student_id'],'班期':wf.className,
                    '状态':row.get('roster_status',''),'免催日期':row.get('exemption_text',''),
                    '欠课':row.get('courses',''),'欠作业':row.get('homework','')})
                people.append(dict(name=row['name'],
                    content=[] if names_only else render_content(fields,row['name'],variables=variables),
                    learning_data=dict(student_id=row['student_id'],class_name=wf.className,
                        profile_path=str(self.owner.db.path),profile_fields=variables)))
            # Like profile selection, this is an independent list of exactly the visible people.
            self._id=self.store.create(title,people,content_template=[] if names_only else fields)
            self._preview=[];self._confirmation=None
            self._notice=f'已从当前筛选结果生成 {len(people)} 人名单'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:
            self._notice='生成失败：'+str(exc);self._notify_status();return False

    @Slot()
    def refresh(self):
        self._reload_snapshot(lists=True);self._notify_status()

    def createFromAiCampaign(self, title, students, results, failures, template_index):
        if self.active or self.owner.workflow.send_busy or self.owner.busy:
            return False
        try:
            from .ai_campaign import validate_text
            captured, _ = self.owner.aiCampaign._capture(self.owner.workflow.recipientKeys)
            if captured != students:
                raise ValueError('名单或学习数据已变化，请重新生成')
            ids = {s['student_id'] for s in students}
            if set(results) | set(failures) != ids or set(results) & set(failures):
                raise ValueError('AI 结果不完整，请重新生成')
            people = []
            for student in students:
                sid = student['student_id']
                text = validate_text(results[sid], student['diagnostic']) if sid in results else ''
                people.append(dict(name=student['name'],
                    content=[dict(type='text', text=text, personal_override=True)] if text else [],
                    learning_data=dict(student_id=sid, class_name=self.owner.workflow.className,
                        profile_path=str(self.owner.db.path),
                        ai_generation=dict(student=student, template_index=template_index,
                                           error=failures.get(sid, '')))))
            self._id = self.store.create(title, people)
            self._preview = []; self._confirmation = None
            self._notice = f'已创建 {len(people)} 人 AI 话术名单；{len(failures)} 人话术留空，请补齐后预览。尚未发送。'
            self._reload_snapshot(lists=True); self._notify_preview(); self._notify_status()
            return True
        except Exception as exc:
            self._notice = '生成名单失败：' + str(exc)
            self._notify_status()
            return False

    def applyAiRetries(self, list_id, results, failures):
        """Only fill still-empty failed rows; edits and protected send states win."""
        if self.active:
            self._notice = '正在发送，未应用 AI 重试结果；请稍后重新重试。'
            self._notify_status()
            return
        from .ai_campaign import validate_text
        from .message_content import describe
        changed = 0
        try:
            with self.store.connect() as conn:
                rows = conn.execute('SELECT * FROM recipients WHERE list_id=?', (list_id,)).fetchall()
                for row in rows:
                    if json.loads(row['content']) or row['message'] or row['state'] in receipts.PROTECTED:
                        continue
                    learning = json.loads(row['learning_data'])
                    metadata = learning.get('ai_generation', {})
                    if not metadata.get('error'):
                        continue
                    sid = learning.get('student_id')
                    if sid in results:
                        text = validate_text(results[sid], metadata['student']['diagnostic'])
                        content = [dict(type='text', text=text, personal_override=True)]
                        metadata['error'] = ''
                        conn.execute('UPDATE recipients SET content=?,message=?,learning_data=? WHERE id=?',
                            (json.dumps(content, ensure_ascii=False), describe(content),
                             json.dumps(learning, ensure_ascii=False), row['id']))
                        changed += 1
                    elif sid in failures:
                        metadata['error'] = failures[sid]
                        conn.execute('UPDATE recipients SET learning_data=? WHERE id=?',
                                     (json.dumps(learning, ensure_ascii=False), row['id']))
            if list_id == self._id:
                if changed:
                    self._preview = []; self._confirmation = None; self._notify_preview()
                self._reload_snapshot()
            self._notice = f'AI 重试已补齐 {changed} 人；已有消息及发送记录保留。'
        except Exception:
            self._notice = 'AI 重试结果未能保存，请重试或在个人消息中补写。'
        self._notify_status()
    @Slot(int)
    def selectList(self,index):
        if self.active:return
        records=self._lists_cache
        if 0<=index<len(records):
            selected_id=records[index]['id']
            if selected_id==self._id:return
            self._id=selected_id;self._preview=[];self._confirmation=None
            self._reload_snapshot();self._notify_preview();self._notify_status()

    @Slot(str,result=bool)
    def generateCampaign(self,template):
        wf=self.owner.workflow
        if self.active or wf.sender.active or self.owner.busy or self.owner.termsModule.busy or not wf.canEdit:return False
        try:
            receipts.save_config(wf.store,wf._batch,'',template)
            people=receipts.plan(wf.store,wf._batch)
            for person in people:
                sid=person.get('student_id','')
                current=wf.store.repo.get(sid) if sid else None
                if current:
                    person['learning_data'].update(student_id=sid,
                        profile_fields=dict(current.get('profile_fields') or {}),
                        profile_path=str(wf.store.db.path.resolve()))
            self._id=self.store.create(f'{wf.className} · 第{wf._batch}次催办',people,wf.store,wf._batch,
                content_template=[dict(type='text',text=template)])
            self._preview=[];self._confirmation=None
            wf.reload_rows(keep_query=True)
            self._notice=f'已生成群发名单，共 {len(people)} 人；尚未发送。请配置前缀和参数'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='生成失败：'+str(exc);self._notify_status();return False

    @Slot(str,str,result=bool)
    def createCustom(self,title,content):
        if self.active:return False
        try:
            people=[]
            for i,line in enumerate(content.splitlines(),1):
                if not line.strip():continue
                delimiter='\t' if '\t' in line else '|'
                if delimiter not in line:raise ValueError(f'第 {i} 行请使用 Tab 或 | 分隔姓名和话术')
                name,message=line.split(delimiter,1)
                people.append(dict(name=name.strip(),message=message.replace('\\n','\n')))
            self._id=self.store.create(title,people)
            self._preview=[];self._confirmation=None
            self._notice='自定义名单已保存；仅提供姓名和话术，无需学习数据。请预览后确认发送'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='保存失败：'+str(exc);self._notify_status();return False

    @Slot(str,str,'QVariantList',result=bool)
    def createStructured(self,title,names,fields):
        if self.active:return False
        try:
            people=[dict(name=name.strip(),content=render_content(fields,name.strip())) for name in names.splitlines() if name.strip()]
            self._id=self.store.create(title,people)
            self.store.save_content(self._id,fields)
            self._preview=[];self._confirmation=None
            self._notice='名单和消息字段已保存，按字段顺序发送'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='保存失败：'+str(exc);self._notify_status();return False

    @Slot(int,'QVariantList',result=bool)
    def saveContent(self,list_id,fields):
        if self.active or list_id!=self._id:return False
        try:
            self.store.save_content(list_id,fields)
            self._preview=[];self._confirmation=None
            self._notice='消息字段已更新；已发送和异常待确认记录保留原内容'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='保存失败：'+str(exc);self._notify_status();return False

    @Slot(str,result=bool)
    def createEmptyList(self,title):
        """新建群发方案只取名：成员和消息随后在群发名单和消息模板里补。"""
        if self.active:
            self._notice='发送运行中，不能新建群发方案';self._notify_status();return False
        try:
            self._id=self.store.create(title,[],allow_empty=True)
            self._preview=[];self._confirmation=None
            self._notice=f'已新建群发方案「{title.strip()}」；请在「群发名单」填写姓名，再配置消息模板'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='创建失败：'+str(exc);self._notify_status();return False

    @Slot(int,'QVariantList',result='QVariantMap')
    def addNames(self,list_id,names):
        if self.active:
            self._notice='发送运行中，不能添加名单人员';self._notify_status();return {}
        try:
            if list_id!=self._id or not self.store.get(list_id):raise ValueError('群发名单已变化，请重新选择')
            result=self.store.add_recipients(list_id,list(names))
            self._preview=[];self._confirmation=None
            summary=[]
            if result['added']:summary.append(f"已添加 {len(result['added'])} 人")
            if result['skipped']:summary.append(f"名单里已有同名，跳过 {len(result['skipped'])} 人")
            if result['no_message']:summary.append(f"{len(result['no_message'])} 人还没有套用上模板消息（模板含无法解析的变量或文件），请双击单独填写")
            self._notice=('；'.join(summary)+'；请重新预览') if summary else '没有可添加的姓名'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status()
            return dict(result,list_id=list_id)
        except Exception as exc:
            self._notice='添加失败：'+str(exc);self._notify_status();return {}

    @Slot(int,'QVariantList',result=bool)
    def removeNames(self,list_id,recipient_ids):
        if self.active:
            self._notice='发送运行中，不能删除名单人员';self._notify_status();return False
        try:
            if list_id!=self._id or not self.store.get(list_id):raise ValueError('群发名单已变化，请重新选择')
            result=self.store.remove_recipients(list_id,list(recipient_ids))
            self._preview=[];self._confirmation=None
            self._notice=f"已从名单删除 {len(result['removed'])} 人；已发送记录未受影响，请重新预览"
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='删除失败：'+str(exc);self._notify_status();return False

    @Slot(int,str,result=bool)
    def renameList(self,list_id,title):
        if self.active:
            self._notice='发送运行中，不能修改名单名称';self._notify_status();return False
        try:
            if list_id!=self._id or not self.store.get(list_id):
                raise ValueError('群发名单已变化，请重新选择')
            title=self.store.rename_list(list_id,title)
            # 只换标题：人员、消息、发送记录与已确认的预览都保持有效。
            self._reload_snapshot(lists=True)
            self._notice=f'名单名称已改为“{title}”；人员、消息和发送记录未变'
            self._notify_status();return True
        except Exception as exc:
            self._notice='重命名失败：'+str(exc);self._notify_status();return False

    @Slot(int,str,'QVariantMap',result=bool)
    def saveOptions(self,list_id,prefix,options):
        if self.active:
            self._notice='发送运行中，不能修改发送设置';self._notify_status();return False
        try:
            if list_id!=self._id or not self.store.get(list_id):
                raise ValueError('群发名单已变化，请重新选择')
            self.store.configure(list_id,prefix,dict(options))
            self._selected_cache=self.store.get(list_id) or self._selected_cache
            self._preview=[];self._confirmation=None
            self._notice='发送设置已保存，请重新预览'
            self.selectionChanged.emit();self._notify_preview();self._notify_status();return True
        except Exception as exc:
            self._notice='设置保存失败：'+str(exc);self._notify_status();return False

    @Property(int,notify=rowsChanged)
    def editableCount(self):return sum(r['state'] not in receipts.PROTECTED for r in self._rows_cache)

    @Slot(str,bool,result=bool)
    def copyList(self,title,copy_messages):
        if self.active:return False
        try:
            self._id=self.store.copy_list(self._id,title,copy_messages)
            self._preview=[];self._confirmation=None
            self._notice='已复制人员名单并新建独立批次；所有人员均为待发送状态，请复核后预览'
            self._reload_snapshot(lists=True);self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='复制失败：'+str(exc);self._notify_status();return False

    @Slot(int,int,'QVariantMap',bool,result=bool)
    def bulkField(self,list_id,index,item,override_personal):
        if self.active or list_id!=self._id:return False
        try:
            count=self.store.bulk_field(list_id,index,dict(item),override_personal=override_personal)
            self._preview=[];self._confirmation=None
            self._notice=f'整列已更新 {count} 人；单独编辑过的内容'+('已覆盖' if override_personal else '已保留')+'；请重新预览后发送'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='整列更新失败：'+str(exc);self._notify_status();return False

    @Slot('QVariantMap',result=bool)
    def appendField(self,item):
        if self.active or not self._id:return False
        try:
            count=self.store.append_field(self._id,dict(item))
            self._preview=[];self._confirmation=None
            self._notice=f'新字段已追加，更新 {count} 位可发送学员；发送历史未变，请重新预览'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='新增字段失败：'+str(exc);self._notify_status();return False

    @Slot(int,result=bool)
    def removeField(self,index):
        if self.active:return False
        try:
            self.store.remove_field(self._id,index);self._preview=[];self._confirmation=None
            self._notice='字段已从可发送人员中删除；已发送、发送中、待核实记录保持不变'
            self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='删除失败：'+str(exc);self._notify_status();return False

    @Slot(int,int,result=bool)
    def moveField(self,index,direction):
        if self.active:return False
        try:
            self.store.move_field(self._id,index,direction);self._preview=[];self._confirmation=None
            self._notice='字段顺序已调整，请重新预览后发送';self._reload_snapshot();self._notify_preview();self._notify_status();return True
        except Exception as exc:self._notice='调整顺序失败：'+str(exc);self._notify_status();return False

    @Slot(result=str)
    def chooseMessageFile(self):
        path,_=QFileDialog.getOpenFileName(None,'选择要群发的文件','','所有文件 (*)')
        return path

    @Slot('QVariantList',result='QVariantMap')
    def messageFiles(self,urls):
        """Validate a complete dropped/copied file batch before changing the draft."""
        try:
            paths=[]
            for value in urls:
                url=value if isinstance(value,QUrl) else QUrl(str(value))
                if not url.isLocalFile():raise ValueError('请粘贴或拖入本地文件')
                paths.append(dict(type='file',path=url.toLocalFile()))
            if not paths:return dict(files=[],error='没有可添加的文件')
            return dict(files=[item['path'] for item in prepare_content(paths)],error='')
        except (ValueError,OSError) as exc:return dict(files=[],error=str(exc))

    @Slot(result='QVariantMap')
    def clipboardMessageFiles(self):
        mime=QGuiApplication.clipboard().mimeData()
        urls=mime.urls() if mime and mime.hasUrls() else []
        if not any(url.isLocalFile() for url in urls):return dict(handled=False,files=[],error='')
        return dict(self.messageFiles(urls),handled=True)

    @Slot(result=str)
    def importNames(self):
        path,_=QFileDialog.getOpenFileName(None,'导入姓名名单','','名单 (*.csv *.txt)')
        if not path:return ''
        try:
            raw=Path(path).read_bytes()
            try:text=raw.decode('utf-8-sig')
            except UnicodeDecodeError:text=raw.decode('gb18030')
            rows=list(csv.reader(text.splitlines())) if path.lower().endswith('.csv') else [[line] for line in text.splitlines()]
            names=[cell.strip() for i,row in enumerate(rows) for cell in row if cell.strip() and not (i==0 and cell.strip() in ('姓名','名字','学员姓名'))]
            return '\n'.join(names)
        except Exception as exc:self._notice='导入失败：'+str(exc);self._notify_status();return ''

    @Slot(str,'QVariantMap',result=bool)
    def prepare(self,prefix,options):
        if self.active:return False
        self._preview=[];self._confirmation=None
        try:
            self.store.configure(self._id,prefix,dict(options))
            self._selected_cache=self.store.get(self._id) or self._selected_cache
            self._preview=self.store.plan(self._id)
            self._confirmation=(self._id,self.selected['options'])
            self._notice=f'本轮待处理 {len(self._preview)} 人；已执行、待确认、仅粘贴及不再符合催办条件者均跳过'
            self.selectionChanged.emit();self._notify_preview();self._notify_status();return bool(self._preview)
        except Exception as exc:self._notice='预览失败：'+str(exc);self._notify_preview();self._notify_status();return False

    @Slot(result=bool)
    def start(self):
        if self.active or not self._preview:return False
        try:
            if self.owner.contactOpener.active:raise ValueError('正在打开画像联系人，请等待完成')
            if self.owner.profilesModule.wechatVerifier.active:raise ValueError('正在批量验证微信，请等待完成')
            if self.owner.busy or self.owner.termsModule.busy or self.owner.workflow.sender.active:raise ValueError('其他任务正在运行，请等待完成')
            if self._confirmation!=(self._id,self.selected['options']) or self.store.plan(self._id)!=self._preview:raise ValueError('名单或参数已变更，请重新预览')
            from .wecom_sender import WeComSender
            options=self.selected['options']
            driver=WeComSender(options)
            self._hotkey.start()
            # 发送失败不中断本轮：失败者保留在待处理，其余联系人继续处理。
            self._worker=SendWorker(self.store,self._id,list(self._preview),lambda:driver,self,adapter=adapter,options=options,continue_on_failure=True)
            self._worker.progress.connect(self._progress)
            self._worker.rowFinished.connect(self._row_finished)
            self._worker.paused.connect(self._on_paused)
            self._worker.finished.connect(self._finished)
            self._paused=self._pause_requested=False
            self._notice='正在处理，请勿操作电脑；F11 请求当前联系人结束后暂停'
            self._worker.start();self._notify_activity();self._notify_status();return True
        except Exception as exc:
            self._hotkey.close();self._notice='未开始：'+str(exc);self._notify_activity();self._notify_status();return False

    @Slot()
    def pause(self):
        if self._worker and not self._paused:
            self._worker.pause();self._pause_requested=True
            self._notice='等待当前联系人完成后暂停';self._notify_activity();self._notify_status()
    @Slot()
    def resume(self):
        if self._worker and self._paused:
            self._paused=self._pause_requested=False;self._worker.resume()
            self._notice='继续处理剩余名单，请勿操作电脑';self._notify_activity();self._notify_status()
    @Slot()
    def stop(self):
        if self._worker:self._worker.stop();self._notice='当前联系人结束后停止本轮';self._notify_status()
    @Slot(int,int,bool,result=bool)
    def resolve(self,list_id,recipient_id,was_sent):
        if self.active or list_id!=self._id:return False
        try:
            self.store.resolve(list_id,recipient_id,was_sent)
            self.owner.workflow.refresh_live(keep_query=True)
            self._notice='人工核实结果已保存';self._reload_snapshot(selection=False);self._notify_status();return True
        except Exception as exc:self._notice=str(exc);self._notify_status();return False
    @Slot(str)
    def _progress(self,message):self._notice=message;self._notify_status()
    @Slot()
    def _row_finished(self):
        self.owner.workflow.refresh_live(keep_query=True);self._reload_snapshot(selection=False)
    @Slot()
    def _on_paused(self):self._paused=True;self._notice='已暂停，可以操作电脑';self._notify_activity();self._notify_status()
    @Slot()
    def _finished(self):
        worker=self._worker;self._worker=None
        self._paused=self._pause_requested=False;self._hotkey.close()
        if worker:worker.deleteLater()
        try:self.store.recover()
        except Exception as exc:self._notice='结果回写待处理：'+str(exc)
        self.owner.workflow.refresh_live(keep_query=True);self._reload_snapshot(selection=False);self._notify_activity();self._notify_status()
    def shutdown(self):
        if self._worker:self._worker.stop();self._worker.wait()
        self._hotkey.close()
