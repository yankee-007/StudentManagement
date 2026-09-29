"""Full student roster, independent of campaign selection and eligibility."""
import json
import uuid
from collections import Counter
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QObject, Property, Signal, Slot
from .database import Database
from .repository import StudentRepository
from .qt_models import DictTableModel
from .profile_fields import CHOICES, DISPLAY_LABELS, REMOVED_FIELDS, PROFILE_INPUT_LABELS
from .table_query import sort_value
from .table_query import matches
from .profile_fields import BASE_PROFILE_LABELS
from .profile_storage import definitions, set_exemption
from .xlsx_export import export_table

FIXED_COLUMNS = [('class_name','班期'),('student_id','学号'),('name','姓名'),('roster_status','状态')] + [('profile:'+k,k) for k in BASE_PROFILE_LABELS] + [('exemption_text','免催日期')]

class ProfileModule(QObject):
    changed = Signal()
    selectionChanged = Signal()
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
        self._context_path=str(owner.db.path)
        self._all=False
        self._sort=-1
        self._descending=False
        self._notice='修改后自动保存'
        self.refresh()

    @Property(QObject,constant=True)
    def tableModel(self):return self._model
    @Property('QVariantList',notify=changed)
    def columnLabels(self):return [label for key,label in self._model.columns]
    @Property(int,notify=changed)
    def total(self):return len(self._rows)
    @Property(int,notify=changed)
    def visibleCount(self):return len(self._model.rows)
    @Property('QVariantList',notify=changed)
    def filteredKeys(self):return list(self._filters)
    @Property('QVariantList',notify=changed)
    def recipientKeys(self):return [r['_record_key'] for r in self._model.rows if r.get('name','').strip() and not r.get('is_placeholder')]
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
        self.apply()

    @Slot()
    def clearFilters(self):self._filters.clear();self.apply()
    @Property(bool,notify=changed)
    def allClasses(self):return self._all
    @Property('QVariantMap',notify=selectionChanged)
    def selected(self):return self._selected
    @Property(str,notify=changed)
    def notice(self):return self._notice
    @Property('QVariantList',notify=selectionChanged)
    def fields(self):
        return self.editor_fields(self._selected, not self._all)

    def editor_fields(self, student, editable=True):
        fields = student.get('profile_fields', {})
        result = []
        if not student:return []
        db = Database(student['_db_path']) if student.get('_db_path') else self.owner.db
        for item in self.managed_fields(db):
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
        if not self._model.rows:raise ValueError('当前没有可导出的学员')
        model=DictTableModel([(k,allowed[k]) for k in keys])
        model.set_rows([dict(r) for r in self._model.rows])
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

    @Property('QVariantList',notify=changed)
    def managedFields(self):
        return self.managed_fields(self.owner.db)

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
        ids=[r['field_id'] for r in self.managedFields]
        if field_id not in ids:return False
        ids.remove(field_id)
        ids.insert(max(0,min(index,len(ids))),field_id)
        self.owner.repo.set_setting('profile_field_order',json.dumps(ids))
        self.refresh()
        self.layoutChanged.emit()
        return True

    @Slot(str,result=bool)
    def deleteField(self,field_id):
        if self._all:return False
        try:
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
    def refresh(self):
        if self._context_path!=str(self.owner.db.path):
            self._context_path=str(self.owner.db.path)
            self._filters.clear()
            self._sort=-1
        entries=self.owner.workflow._classes if self._all else [self.owner.workflow._classes[self.owner.workflow.class_index]]
        rows=[]
        headers=[]
        for entry in entries:
            repo=self.owner.repo if str(self.owner.db.path)==entry['path'] else StudentRepository(Database(entry['path']))
            source=repo.learning_source()
            with repo.db.connect() as conn:
                exists=conn.execute("SELECT 1 FROM sqlite_master WHERE name='student_contacts'").fetchone()
                contacts={r['student_id']:r['remark'] for r in conn.execute('SELECT * FROM student_contacts')} if exists else {}
            for r in repo.list_students():
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
        if columns!=self._model.columns:
            self._filters={k:v for k,v in self._filters.items() if k in dict(columns)}
            self._model.beginResetModel()
            self._model.columns=columns
            self._model.endResetModel()
            self._sort=-1
        self._rows=rows
        self.apply()
        self.rosterChanged.emit()

    def _searched_rows(self):
        query=self._search.strip().casefold()
        return [r for r in self._rows if not query or query in (r['class_name']+' '+r['student_id']+' '+r['name']+' '+r['remark']).casefold()]

    def _display_rows(self):
        rows=[r for r in self._searched_rows() if self._matches_filters(r)]
        if 0<=self._sort<len(self._model.columns):
            key=self._model.columns[self._sort][0]
            rows=sorted(rows,key=lambda r:sort_value(r,key),reverse=self._descending)
        return rows

    def _refresh_query_after_save(self):
        # Re-evaluate the table without switching the student under an active editor.
        if self._filters or self._sort>=0:
            rows=self._display_rows()
            if [r['_record_key'] for r in rows]!=[r['_record_key'] for r in self._model.rows]:
                self._model.set_rows(rows)

    def apply(self):
        rows=self._display_rows()
        self._model.set_rows(rows)
        old=self._selected.get('_record_key')
        self._selected=next((r for r in rows if r['_record_key']==old),rows[0] if rows else {})
        self.changed.emit()
        self.selectionChanged.emit()

    @Slot(bool)
    def setAllClasses(self,value):self._all=value;self.refresh()
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
        self.apply()

    @Slot(str,str,str,result=bool)
    def saveEditorField(self,record_key,label,value):
        if self._all or not record_key or record_key != self._selected.get('_record_key') or self._selected.get('_db_path') != str(self.owner.db.path):
            self._notice='未保存：编辑对象已切换，请重新选择学员'
            self.changed.emit()
            return False
        return self.autoSaveField(self._selected['student_id'],label,value)

    def reflect_saved(self,path,sid):
        current=StudentRepository(Database(path)).get(sid)
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
        self._refresh_query_after_save()
        self.changed.emit()

    @Slot(str,str,str,result=bool)
    def autoSaveField(self,sid,label,value):
        if self._all:return False
        try:
            if label=='免催日期':
                set_exemption(self.owner.db,sid,value)
                self.refresh()
                self.owner.workflow.refresh_live()
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
            self.owner.workflow.refresh_live()
            self._refresh_query_after_save()
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
