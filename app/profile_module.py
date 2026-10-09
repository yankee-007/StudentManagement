"""Full student roster, independent of campaign selection and eligibility."""
import json
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QCoreApplication, QObject, Property, Signal, Slot, QTimer
from .database import Database
from .repository import StudentRepository
from .qt_models import DictTableModel
from .profile_fields import CHOICES, DISPLAY_LABELS, REMOVED_FIELDS, PROFILE_INPUT_LABELS
from .table_query import sort_value
from .table_query import matches
from .table_query import next_cursor
from .profile_fields import BASE_PROFILE_LABELS
from .profile_storage import definitions, set_exemption
from .xlsx_export import export_table

FIXED_COLUMNS = [('class_name','班期'),('student_id','学号'),('name','姓名'),('roster_status','状态')] + [('profile:'+k,k) for k in BASE_PROFILE_LABELS] + [('exemption_text','免催日期')]

class ProfileModule(QObject):
    changed = Signal()
    selectionChanged = Signal()
    fieldLayoutChanged = Signal()
    editorFieldsChanged = Signal()
    fieldOrderSavingChanged = Signal()
    layoutChanged = Signal()
    fieldSaved = Signal(str, str, str)
    rosterChanged = Signal()
    def __init__(self, owner):
        super().__init__(owner)
        self.owner=owner
        self._model=DictTableModel([],self)
        self._rows=[]
        self._selected={}
        self._search=''
        self._filters={}
        self._frozen=None
        self._stale_changed=set()
        self._context_path=str(owner.db.path)
        self._all=False
        self._sort=-1
        self._descending=False
        self._notice='修改后自动保存'
        self._managed_fields=None
        self._order_executor=None
        self._order_jobs=[]
        self._order_sequence=0
        self._order_timer=QTimer(self)
        self._order_timer.setInterval(40)
        self._order_timer.timeout.connect(self._finish_field_orders)
        if QCoreApplication.instance():
            QCoreApplication.instance().aboutToQuit.connect(self.flushFieldOrder)
        self.changed.connect(self.fieldLayoutChanged)
        self.selectionChanged.connect(self.editorFieldsChanged)
        self.refresh()
        from .profile_wechat import ProfileWechatVerifier
        self._wechat_verifier = ProfileWechatVerifier(self)

    @Property(QObject,constant=True)
    def wechatVerifier(self):return self._wechat_verifier

    @Property(QObject,constant=True)
    def tableModel(self):return self._model
    @Property('QVariantList',notify=fieldLayoutChanged)
    def columnLabels(self):return [label for key,label in self._model.columns]
    @Property('QVariantList',notify=fieldLayoutChanged)
    def columnKeys(self):return [key for key,label in self._model.columns]
    @Property(int,notify=changed)
    def total(self):return len(self._rows)
    @Property(int,notify=changed)
    def visibleCount(self):return len(self._model.rows)
    @Property(int,notify=changed)
    def matchedCount(self):return sum(1 for r in self._model.rows if not r.get('_filter_stale'))
    @Property(int,notify=changed)
    def staleCount(self):return sum(1 for r in self._model.rows if r.get('_filter_stale'))
    @Property(bool,notify=changed)
    def hasStale(self):return any(r.get('_filter_stale') for r in self._model.rows)
    @Property(str,notify=selectionChanged)
    def cursorText(self):
        key=self._selected.get('_record_key')
        index=next((i for i,r in enumerate(self._model.rows) if r['_record_key']==key),-1)
        if index<0:return ''
        return f"正在处理 第 {index+1} / {len(self._model.rows)} 条 · {self._selected.get('name','')}"
    @Property('QVariantList',notify=changed)
    def filteredKeys(self):return list(self._filters)
    @Property('QVariantList',notify=changed)
    def recipientKeys(self):return [r['_record_key'] for r in self._scope_rows() if r.get('name','').strip() and not r.get('is_placeholder')]
    @Property('QVariantList',notify=changed)
    def messagePlaceholders(self):
        labels=['姓名','学号','班期','状态','免催日期']+list(BASE_PROFILE_LABELS)
        labels += [r['name'] for r in definitions(self.owner.db)]
        return list(dict.fromkeys(labels))

    def _matches_filters(self,row,skip=None):
        for key,rule in self._filters.items():
            if key==skip:continue
            value=str(row.get(key) or '')
            if rule['mode']=='values':
                if value not in rule['values']:return False
            elif not matches(row,{key:rule}):return False
        return True

    def _row_key(self,row):return row.get('_record_key') or row.get('student_id','')

    def _query_active(self):return bool(self._filters) or bool(self._search.strip())

    def _matched_rows(self):return [r for r in self._rows if self._row_matches_query(r)]

    def _recompute_freeze(self):
        # ADR-007: 冻结本次应用筛选时命中的学员；没有查询条件时保持实时视图，新学员照常出现。
        self._frozen={self._row_key(r) for r in self._matched_rows()} if self._query_active() else None

    def _visible_rows(self):
        if self._frozen is None:return self._matched_rows()
        return [r for r in self._rows if self._row_key(r) in self._frozen]

    def _mark_stale(self,rows):
        # 行数据变化后不重新筛选，只标记“已不符合当前筛选”；只有重新应用筛选才会移除。
        changed=set()
        for row in rows:
            stale=not self._row_matches_query(row)
            if '_filter_stale' not in row or bool(row['_filter_stale'])!=stale:
                row['_filter_stale']=stale
                changed.add(self._row_key(row))
        return changed

    def _scope_rows(self):
        # 业务范围（名单生成、导出）只取真正匹配筛选的学员，过期行仅供显示。
        return [r for r in self._display_rows() if not r.get('_filter_stale')]

    @Slot(int,result='QVariantMap')
    def columnFilterInfo(self,index):
        if not 0<=index<len(self._model.columns):return {}
        key,label=self._model.columns[index]
        counts=Counter(str(r.get(key) or '') for r in self._searched_rows() if self._matches_filters(r,key))
        rule=self._filters.get(key,dict(mode='values',values=list(counts)))
        return dict(key=key,label=label,options=[dict(value=v,label=v or '(空白单元格)',count=counts[v]) for v in sorted(counts)],
                    mode=rule['mode'],values=rule.get('values',list(counts)),value=rule.get('value',''))

    @Slot(str,str,'QVariantList',str)
    def setColumnFilter(self,key,mode,values,value):
        if key not in dict(self._model.columns):return
        if mode=='clear':self._filters.pop(key,None)
        elif mode=='values':self._filters[key]=dict(mode=mode,values=[str(v) for v in values])
        elif mode in ('contains','exact','empty','notempty'):self._filters[key]=dict(mode=mode,value=value)
        else:return
        self.apply()

    @Slot(str,bool)
    def sortField(self,key,descending):
        self._sort=next((i for i,c in enumerate(self._model.columns) if c[0]==key),-1)
        self._descending=descending
        self.apply(recompute=False)

    @Slot()
    def clearFilters(self):self._filters.clear();self.apply()
    @Property(bool,notify=changed)
    def allClasses(self):return self._all
    @Property('QVariantMap',notify=selectionChanged)
    def selected(self):return self._selected
    @Property(str,notify=changed)
    def notice(self):return self._notice
    @Property('QVariantList',notify=editorFieldsChanged)
    def fields(self):
        return self.editor_fields(self._selected, not self._all)

    def editor_fields(self, student, editable=True):
        fields = student.get('profile_fields', {})
        result = []
        if not student:return []
        path = student.get('_db_path')
        db = self.owner.db if not path or path == str(self.owner.db.path) else Database(path)
        layout = self.managedFields if db is self.owner.db else self.managed_fields(db)
        for item in layout:
            if not item['show_column']:continue
            label=item['name']
            if not item['deletable'] and label not in BASE_PROFILE_LABELS and label!='免催日期':continue
            kind=item.get('kind', 'exemption' if label=='免催日期' else 'choice' if label in CHOICES else 'text')
            options=item.get('options', CHOICES.get(label, []))
            if kind=='choice' and '' not in options:options=['']+options
            value=student.get('exemption_date','') if label=='免催日期' else fields.get(label,'')
            result.append(dict(label=label,displayLabel=label,studentId=student['student_id'],recordKey=student['_record_key'],
                               value=str(value or ''),options=options,kind=kind,expired=student.get('exemption_expired',False) if label=='免催日期' else False,editable=editable))
        return result

    @Property('QVariantList',notify=changed)
    def extraFields(self):
        if not self._all:return definitions(self.owner.db)
        result = {}
        for entry in self.owner.workflow._classes:
            for field in definitions(Database(entry['path'])):
                result.setdefault(field['name'], field)
        return list(result.values())

    @Property('QVariantList',notify=changed)
    def exportFields(self):
        defaults=[('student_id','学号'),('name','姓名')]+[('profile:'+k,k) for k in BASE_PROFILE_LABELS]
        optional=[(k,v) for k,v in FIXED_COLUMNS if k not in dict(defaults)]
        optional += [('profile:'+r['name'],r['name']) for r in self.extraFields]
        return [dict(key=k,name=v,selected=True) for k,v in defaults]+[dict(key=k,name=v,selected=False) for k,v in optional]

    def export_to_path(self,keys,path):
        allowed={r['key']:r['name'] for r in self.exportFields}
        keys=list(dict.fromkeys(keys))
        if not keys:raise ValueError('请至少选择一个导出字段')
        if any(k not in allowed for k in keys):raise ValueError('导出字段已变更，请重新选择')
        rows=self._scope_rows()
        if not rows:raise ValueError('当前没有可导出的学员')
        model=DictTableModel([(k,allowed[k]) for k in keys])
        model.set_rows([dict(r) for r in rows])
        return export_table(model,path,set())

    @Slot('QVariantList',result=bool)
    def exportXlsx(self,keys):
        if not keys:
            self._notice='请至少选择一个导出字段';self.changed.emit();return False
        path,_=QFileDialog.getSaveFileName(None,'导出学员画像','学员画像.xlsx','Excel 工作簿 (*.xlsx)')
        if not path:return False
        if Path(path).suffix.lower()!='.xlsx':path+='.xlsx'
        try:
            count=self.export_to_path(keys,path)
            self._notice=f'已导出 {count} 位学员的画像：{path}'
            self.changed.emit();return True
        except Exception as exc:
            self._notice='导出失败：'+str(exc);self.changed.emit();return False

    def _visibility(self, db=None):
        return json.loads(StudentRepository(db or self.owner.db).get_setting('profile_column_visibility','{}'))

    @Property('QVariantList',notify=fieldLayoutChanged)
    def managedFields(self):
        if self._managed_fields is None:
            self._managed_fields=self.managed_fields(self.owner.db)
        return self._managed_fields

    def managed_fields(self, db):
        visible=self._visibility(db)
        result=[dict(field_id='column:'+key,name=label,show_column=visible.get(key,True) or key in ('student_id','name'),locked=key in ('student_id','name'),deletable=False) for key,label in FIXED_COLUMNS]
        result += [dict(r,locked=False,deletable=True) for r in definitions(db)]
        order=json.loads(StudentRepository(db).get_setting('profile_field_order','[]'))
        ranks={key:i for i,key in enumerate(order)}
        return sorted(result,key=lambda r:ranks.get(r['field_id'],len(ranks)))

    @Slot(str,int,result=bool)
    def moveField(self,field_id,index):
        if self._all:return False
        self.flushFieldOrder()
        return self._move_field(field_id,index,False)

    @Slot(str,int,result=bool)
    def moveFieldAsync(self,field_id,index):
        if self._all:return False
        return self._move_field(field_id,index,True)

    def _move_field(self,field_id,index,background):
        fields=list(self.managedFields)
        source=next((i for i,f in enumerate(fields) if f['field_id']==field_id),-1)
        if source<0:return False
        target=max(0,min(index,len(fields)-1))
        if target==source:return True
        fields.insert(target,fields.pop(source))
        value=json.dumps([f['field_id'] for f in fields])
        if background:
            if self._order_executor is None:
                self._order_executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='profile-field-order')
            self._order_sequence+=1
            # Capture the current database; later class changes cannot redirect this write.
            future=self._order_executor.submit(StudentRepository(self.owner.db).set_setting,'profile_field_order',value)
            was_saving=bool(self._order_jobs)
            self._order_jobs.append((self._order_sequence,str(self.owner.db.path),future))
            if not was_saving:self.fieldOrderSavingChanged.emit()
            self._order_timer.start()
        else:
            self.owner.repo.set_setting('profile_field_order',value)
        self._apply_field_layout(fields)
        return True

    @Property(bool,notify=fieldOrderSavingChanged)
    def fieldOrderSaving(self):return bool(self._order_jobs)

    def _finish_field_orders(self,wait=False):
        failures=[]
        finished=[]
        for job in self._order_jobs:
            sequence,path,future=job
            if not wait and not future.done():continue
            try:future.result()
            except Exception as exc:failures.append((sequence,path,str(exc)))
            finished.append(job)
        was_saving=bool(self._order_jobs)
        self._order_jobs=[job for job in self._order_jobs if job not in finished]
        if not self._order_jobs:
            self._order_timer.stop()
            if was_saving:self.fieldOrderSavingChanged.emit()
        for sequence,path,error in failures:
            # A later successful queued order supersedes an older failed write.
            if sequence!=self._order_sequence:continue
            self._notice='字段排序保存失败：'+error
            if path==str(self.owner.db.path):
                self._apply_field_layout(self.managed_fields(self.owner.db))
            self.changed.emit()
        return not failures

    @Slot(result=bool)
    def flushFieldOrder(self):
        return self._finish_field_orders(wait=True)

    def _apply_field_layout(self,fields):
        # Layout changes reuse loaded rows, their frozen scope and the current cursor.
        self._managed_fields=fields
        sort_key=self._model.columns[self._sort][0] if 0<=self._sort<len(self._model.columns) else None
        columns=[(f['field_id'][7:] if f['field_id'].startswith('column:') else 'profile:'+f['name'],f['name'])
                 for f in fields if f['show_column']]
        if columns!=self._model.columns:
            self._model.beginResetModel()
            self._model.columns=columns
            self._model.endResetModel()
        self._sort=next((i for i,c in enumerate(columns) if c[0]==sort_key),-1)
        self.fieldLayoutChanged.emit()
        self.editorFieldsChanged.emit()
        self.layoutChanged.emit()

    @Slot(result=bool)
    def resetFieldLayout(self):
        if self._all:return False
        try:
            self.flushFieldOrder()
            with self.owner.db.connect() as conn:
                conn.execute("DELETE FROM settings WHERE key IN ('profile_field_order','profile_column_visibility')")
                conn.execute('UPDATE profile_field_definitions SET show_column=1')
            fields=self.managed_fields(self.owner.db)
        except Exception as exc:
            self._notice='恢复默认失败：'+str(exc);self.changed.emit();return False
        self._notice='已恢复默认顺序和显示，字段及填写内容已保留'
        self._apply_field_layout(fields)
        self.changed.emit()
        return True

    @Slot(str,result=bool)
    def deleteField(self,field_id):
        if self._all:return False
        try:
            self.flushFieldOrder()
            with self.owner.db.connect() as conn:
                if not conn.execute('SELECT 1 FROM profile_field_definitions WHERE field_id=?',(field_id,)).fetchone():
                    raise ValueError('仅能删除存在的额外字段')
                conn.execute('INSERT OR IGNORE INTO deleted_profile_fields VALUES(?)',(field_id,))
                conn.execute('DELETE FROM profile_field_values WHERE field_id=?',(field_id,))
                conn.execute('DELETE FROM profile_field_definitions WHERE field_id=?',(field_id,))
            self._sync_fields()
            self._notice='本班额外字段及填写内容已删除，其他班期不受影响'
            self.changed.emit();return True
        except Exception as exc:
            self._notice='删除失败：'+str(exc);self.changed.emit();return False

    @Slot(str,str,str,bool,result=bool)
    def addField(self,name,kind,options,show_column):
        if self._all:return False
        try:
            self.flushFieldOrder()
            name=name.strip()
            if not name or name in set(PROFILE_INPUT_LABELS)|{'学号','姓名','状态','班期','免催日期','合计完课','合计作业','差的课程','差的作业'} or name in REMOVED_FIELDS:
                raise ValueError('字段名称为空、已存在或属于系统字段')
            if kind not in ('text','date','choice'):raise ValueError('字段类型无效')
            choices=list(dict.fromkeys(v.strip() for v in options.splitlines() if v.strip()))
            if kind=='choice' and not choices:raise ValueError('请填写下拉选项，每行一个')
            with self.owner.db.connect() as conn:
                if conn.execute('SELECT 1 FROM profile_field_definitions WHERE name=?',(name,)).fetchone():raise ValueError('字段已存在')
                position=conn.execute('SELECT coalesce(max(position),-1)+1 FROM profile_field_definitions').fetchone()[0]
                conn.execute('INSERT INTO profile_field_definitions VALUES(?,?,?,?,?,?)',(uuid.uuid4().hex,name,kind,json.dumps(choices if kind=='choice' else [],ensure_ascii=False),position,int(show_column)))
            self._sync_fields()
            self._notice='字段已添加，仅当前班期使用';self.changed.emit();return True
        except Exception as exc:
            self._notice='添加失败：'+str(exc);self.changed.emit();return False

    @Slot(str,bool)
    def setFieldVisible(self,field_id,visible):
        if self._all:return
        self.flushFieldOrder()
        if field_id.startswith('column:'):
            key=field_id[len('column:'):]
            if key in ('student_id','name') or key not in dict(FIXED_COLUMNS):return
            values=self._visibility();values[key]=bool(visible)
            self.owner.repo.set_setting('profile_column_visibility',json.dumps(values))
            self.refresh()
            self.layoutChanged.emit()
            return
        with self.owner.db.connect() as conn:
            conn.execute('UPDATE profile_field_definitions SET show_column=? WHERE field_id=?',(int(visible),field_id))
        self._sync_fields()

    def _sync_fields(self):
        self.refresh()
        self.layoutChanged.emit()

    @Property(str,notify=selectionChanged)
    def history(self):
        if not self._selected:return ''
        row=self._selected
        repo=StudentRepository(Database(row['_db_path']))
        with repo.db.connect() as conn:
            exists=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_feedback'").fetchone()
            entries=list(conn.execute('SELECT f.batch_id,c.created_at,f.content FROM campaign_feedback f JOIN campaigns c ON c.id=f.batch_id WHERE f.student_id=? ORDER BY f.id DESC',(row['student_id'],))) if exists else []
        lines=[f"第{r['batch_id']}次 · {r['created_at'].replace('T',' ')}  {r['content']}" for r in entries]
        if row.get('feedback_history'):lines.append('早期记录：\n'+row['feedback_history'])
        for k,v in row.get('profile_fields',{}).items():
            if '学员学习反馈' in k and v:lines.append(k+'：'+str(v))
        return '\n'.join(lines) or '暂无反馈记录'

    @Property('QVariantList',notify=selectionChanged)
    def lessons(self):
        flags=self._selected.get('_flags',{})
        labels={'T':'完成','F':'未完成','N':'未开启'}
        return [dict(lesson=i,course=labels.get(flags.get('c'+str(i)),'未获取'),homework=labels.get(flags.get('z'+str(i)),'未获取')) for i in range(1,33)]

    @Slot()
    def refresh(self, current_students=None, keep_query=False):
        self.flushFieldOrder()
        self._managed_fields=None
        if self._context_path!=str(self.owner.db.path):
            self._context_path=str(self.owner.db.path)
            self._filters.clear()
            self._sort=-1
            keep_query=False
        entries=self.owner.workflow._classes if self._all else [self.owner.workflow._classes[self.owner.workflow.class_index]]
        rows=[]
        headers=[]
        for entry in entries:
            repo=self.owner.repo if str(self.owner.db.path)==entry['path'] else StudentRepository(Database(entry['path']))
            source=repo.learning_source()
            with repo.db.connect() as conn:
                exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='student_contacts'").fetchone()
                contacts={r['student_id']:r['remark'] for r in conn.execute('SELECT * FROM student_contacts')} if exists else {}
            students = current_students if current_students is not None and entry['path'] == str(self.owner.db.path) else repo.list_students()
            for r in students:
                r = dict(r)
                r.update(class_name=entry['name'],remark=contacts.get(r['student_id'],r['name']),
                         _db_path=entry['path'],_record_key=entry['path']+'|'+r['student_id'],_flags=source.get(r['student_id'],{}))
                rows.append(r)
                for key in r.get('profile_fields',{}):
                    if key not in headers and key not in REMOVED_FIELDS:headers.append(key)
        visible=self._visibility()
        columns=[(key,label) for key,label in FIXED_COLUMNS if key in ('student_id','name') or visible.get(key,True)]
        columns += [('profile:'+r['name'],r['name']) for r in self.extraFields if r['show_column']]
        ranks={r['name']:i for i,r in enumerate(self.managedFields)}
        columns.sort(key=lambda c:ranks.get(c[1],len(ranks)))
        columns_changed=columns!=self._model.columns
        if columns_changed:
            self._filters={k:v for k,v in self._filters.items() if k in dict(columns)}
            self._model.beginResetModel()
            self._model.columns=columns
            self._model.endResetModel()
            self._sort=-1
        self._rows=rows
        # 列集合变化时筛选条件可能被裁剪，必须重算，不能沿用旧冻结集。
        self.apply(recompute=(not keep_query) or columns_changed)
        self.rosterChanged.emit()

    def _matches_search(self,row):
        query=self._search.strip().casefold()
        return not query or query in (row['class_name']+' '+row['student_id']+' '+row['name']+' '+row['remark']).casefold()

    def _row_matches_query(self,row):
        return self._matches_search(row) and self._matches_filters(row)

    def _searched_rows(self):
        return [r for r in self._rows if self._matches_search(r)]

    def _display_rows(self):
        rows=self._visible_rows()
        if 0<=self._sort<len(self._model.columns):
            key=self._model.columns[self._sort][0]
            rows=sorted(rows,key=lambda r:sort_value(r,key),reverse=self._descending)
        self._stale_changed=self._mark_stale(rows)
        return rows

    def _refresh_after_data_change(self):
        # 值变化不重新筛选：只同步单元格数据与“已不符合当前筛选”标记，也不切换正在编辑的学员。
        rows=self._display_rows()
        if [r['_record_key'] for r in rows]!=[r['_record_key'] for r in self._model.rows]:
            self._model.set_rows(rows)
            return
        last=len(self._model.columns)-1
        for i,row in enumerate(rows):
            if self._model.rows[i] is not row:
                self._model.rows[i]=row
                self._model.dataChanged.emit(self._model.index(i,0),self._model.index(i,last))
            elif self._row_key(row) in self._stale_changed:
                self._model.dataChanged.emit(self._model.index(i,0),self._model.index(i,last))

    def apply(self,recompute=True):
        previous=[self._row_key(r) for r in self._model.rows]
        if recompute:self._recompute_freeze()
        rows=self._display_rows()
        self._model.set_rows(rows)
        self._selected=next_cursor(rows,self._row_key,self._selected.get('_record_key',''),previous)
        self.changed.emit()
        self.selectionChanged.emit()

    @Slot()
    def reapplyFilters(self):self.apply()

    @Slot()
    def activate(self):
        # 进入模块只重读数据，不重新筛选：处理中的名单不因切换页面而改变（ADR-007）。
        self.refresh(keep_query=True)

    @Slot(bool)
    def setAllClasses(self,value):
        if self.wechatVerifier.active:return
        self._all=value;self.refresh()
    @Slot(str)
    def search(self,value):self._search=value;self.apply()
    @Slot(int)
    def selectRow(self,index):
        if 0<=index<len(self._model.rows):
            self._selected=self._model.rows[index]
            self.selectionChanged.emit()
    @Slot(int)
    def sortColumn(self,index):
        self._descending=not self._descending if self._sort==index else False
        self._sort=index
        self.apply(recompute=False)

    @Slot(str,str,str,result=bool)
    def saveEditorField(self,record_key,label,value):
        if self._all or not record_key or record_key != self._selected.get('_record_key') or self._selected.get('_db_path') != str(self.owner.db.path):
            self._notice='未保存：编辑对象已切换，请重新选择学员'
            self.changed.emit()
            return False
        return self.autoSaveField(self._selected['student_id'],label,value)

    def reflect_saved(self,path,sid):
        repo=self.owner.repo if path==str(self.owner.db.path) else StudentRepository(Database(path))
        current=repo.get(sid)
        if not current:return
        for row in self._rows:
            if row['_db_path']==path and row['student_id']==sid:row.update(current)
        for i,row in enumerate(self._model.rows):
            if row['_db_path']==path and row['student_id']==sid:
                row.update(current)
                self._model.dataChanged.emit(self._model.index(i,0),self._model.index(i,len(self._model.columns)-1))
        if self._selected.get('_db_path')==path and self._selected.get('student_id')==sid:
            self._selected.update(current)
            self.selectionChanged.emit()
        self._refresh_after_data_change()
        self.changed.emit()

    @Slot(str,str,str,result=bool)
    def autoSaveField(self,sid,label,value):
        if self._all:return False
        try:
            if label=='免催日期':
                set_exemption(self.owner.db,sid,value)
                self.refresh(keep_query=True)
                self.owner.workflow.refresh_live(keep_query=True)
                self._notice='免催日期已保存，包含当天；到期后自动恢复催办'
                self.changed.emit()
                self.fieldSaved.emit(str(self.owner.db.path),sid,label)
                return True
            self.owner.repo.update_profile_field(sid,label,value)
            for row in self._rows:
                if row['student_id']==sid:
                    row['profile_fields'][label]=value
                    row['profile:'+label]=value
            for i,row in enumerate(self._model.rows):
                if row['student_id']==sid:
                    self._model.dataChanged.emit(self._model.index(i,0),self._model.index(i,len(self._model.columns)-1))
            self.owner.workflow.refresh_live(keep_query=True)
            self._refresh_after_data_change()
            self._notice='已自动保存；当前催办身份信息同步，历史批次不变'
            self.changed.emit()
            self.fieldSaved.emit(str(self.owner.db.path),sid,label)
            if any(r['name']==label and r['kind']=='date' for r in definitions(self.owner.db)):
                self.selectionChanged.emit()
            return True
        except Exception as exc:
            self._notice='保存失败：'+str(exc)
            self.changed.emit()
            return False
