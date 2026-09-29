import json
import uuid
from collections import Counter
from datetime import date
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot
from PySide6.QtWidgets import QFileDialog
from .database import Database
from .repository import StudentRepository
from .profiles import import_profiles
from .campaigns import CampaignStore, EXPORT_COLUMNS, TEST_TEMPLATE, lessons
from .qt_models import DictTableModel
from .xlsx_export import export_table
from .table_query import matches, sort_value, next_cursor
from .profile_storage import set_exemption

TABLE_COLUMNS = EXPORT_COLUMNS + [('reply_state','反馈状态')]


class Workflow(QObject):
    changed = Signal()
    selectionChanged = Signal()
    queryChanged = Signal()
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.registry = StudentRepository(owner.db)
        saved = self.registry.get_setting('workflow_classes')
        class_name=owner.repo.get_setting('class_name')
        if not class_name:
            class_name='当前班级'
        self._classes = json.loads(saved) if saved else [{'name':class_name,'path':str(owner.db.path)}]
        self.class_index = 0
        self._batch = 0
        self._filter = 'all'
        self._search = ''
        self._column_filters = {}
        self._frozen = None
        self._stale_changed = set()
        self._sort_column = -1
        self._sort_key = ''
        self._sort_descending = False
        self._selected = {}
        self._rows = []
        self._model = DictTableModel(TABLE_COLUMNS,self)
        self.store = CampaignStore(owner.db,owner.repo)
        from .send_controller import SendController
        from .sending_store import recover
        recover(self.store.db)
        self._sender=SendController(self)
        self.changed.connect(self._sender.changed.emit)
        self.reload_batches()

    @Property(QObject,constant=True)
    def sender(self):return self._sender

    @property
    def send_busy(self):
        return self.sender.active or (hasattr(self.owner,'_group_center') and self.owner.groupCenter.active) or (hasattr(self.owner,'_contact_opener') and self.owner.contactOpener.active)

    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property('QVariantList',notify=changed)
    def classes(self): return [r['name'] for r in self._classes]
    @Property(int,notify=changed)
    def classIndex(self): return self.class_index
    @Property(str,notify=changed)
    def className(self): return self._classes[self.class_index]['name']
    @Property('QVariantList',notify=changed)
    def batches(self):
        return [{'id':r['id'],'label':r['created_at'].replace('T',' ')+' · 第'+str(r['id'])+'次'} for r in self._batches]
    @Property(int,notify=changed)
    def batchIndex(self): return next((i for i,r in enumerate(self._batches) if r['id']==self._batch),-1)
    @Property(bool,notify=changed)
    def canEdit(self): return bool(self._batches and self._batch==self._batches[0]['id'])
    @Property(bool,notify=changed)
    def canSetExemption(self):return not self._batch or self.canEdit
    @Property(str,notify=selectionChanged)
    def editorKey(self):
        return json.dumps([str(self.owner.db.path),self._batch,self._selected.get('student_id','')],ensure_ascii=False)

    @Property(str,notify=selectionChanged)
    def contactRemark(self):
        sid=self._selected.get('student_id','')
        with self.owner.db.connect() as conn:
            row=conn.execute('SELECT remark FROM student_contacts WHERE student_id=?',(sid,)).fetchone()
        return row['remark'] if row else self._selected.get('remark','')

    @Slot(str,str,str,result=bool)
    def saveEditorValue(self,key,kind,value):
        if not self.canEdit or key != self.editorKey or not self._selected:
            self.owner.toast.emit('未保存：学员、班期或催办批次已切换')
            return False
        sid=self._selected['student_id']
        if kind=='draft':return self.saveDraft(sid,value)
        if kind=='submit':return self.submit(value)
        if kind=='remark':return self.saveRemark(sid,value)
        return False
    @Property(int,notify=selectionChanged)
    def visibleCount(self): return self._model.rowCount()
    @Property(int,notify=changed)
    def matchedCount(self): return sum(1 for r in self._model.rows if not r.get('_filter_stale'))
    @Property(int,notify=changed)
    def staleCount(self): return sum(1 for r in self._model.rows if r.get('_filter_stale'))
    @Property(bool,notify=changed)
    def hasStale(self): return any(r.get('_filter_stale') for r in self._model.rows)
    @Property(str,notify=selectionChanged)
    def cursorText(self):
        sid=self._selected.get('student_id')
        index=next((i for i,r in enumerate(self._model.rows) if r['student_id']==sid),-1)
        if index<0:return ''
        return f"正在处理 第 {index+1} / {len(self._model.rows)} 条 · {self._selected.get('name','')}"
    @Property(int,notify=queryChanged)
    def sortColumnIndex(self): return next((i for i,c in enumerate(self._model.columns) if c[0]==self._sort_key),-1) if self._sort_key else next((i for i,c in enumerate(self._model.columns) if c[0]==('missing_total' if self._filter=='targets' else 'student_id')),0)
    @Property(bool,notify=queryChanged)
    def sortDescending(self): return self._sort_descending if self._sort_key else self._filter=='targets'
    @Property('QVariantList',notify=queryChanged)
    def filteredColumns(self): return [i for i,(key,_) in enumerate(self._model.columns) if key in self._column_filters]
    @Property(bool,notify=queryChanged)
    def hasColumnQuery(self): return bool(self._column_filters or self._sort_key)

    @Property('QVariantList',notify=changed)
    def columnKeys(self): return [key for key,_ in self._model.columns]

    @Property('QVariantList',notify=selectionChanged)
    def recipientKeys(self):
        if not self._batch:return []
        return [json.dumps([str(self.owner.db.path),self._batch,r['student_id']],ensure_ascii=False)
                for r in self._scope_rows() if r.get('student_id') and str(r.get('name') or '').strip() and not r.get('is_placeholder')]

    def _searched_rows(self):
        return [r for r in self._rows if self._matches_view(r) and self._matches_search(r)]

    def _matches_view(self,row):
        if self._batch and self._filter=='pending' and row['reply_state']!='待反馈':return False
        if self._filter=='targets' and not (row.get('wechat')=='是' and not row.get('is_placeholder') and row.get('roster_status','') in ('','在读')
                                            and self.missing_count(row)>0 and (not self._batch or row.get('current_eligible',row['eligible']))):return False
        if self._batch and self._filter=='failed' and row['send_state'] not in ('未发送失败','结果待确认','模拟失败'):return False
        return True

    def _matches_search(self,row):
        needle=self._search.strip().lower()
        return not needle or needle in (row['student_id']+' '+row['name']+' '+row['remark']).lower()

    def _row_matches_query(self,row):
        return self._matches_view(row) and self._matches_search(row) and self._matches_filters(row)

    def _matches_filters(self,row,skip=None):
        for key,rule in self._column_filters.items():
            if key==skip:continue
            if rule['mode']=='values':
                if str(row.get(key) or '') not in rule['values']:return False
            elif not matches(row,{key:rule}):return False
        return True

    def _query_active(self):
        if self._column_filters or self._search.strip():return True
        if self._filter=='targets':return True
        return bool(self._batch) and self._filter in ('pending','failed')

    def _matched_rows(self):return [r for r in self._rows if self._row_matches_query(r)]

    def _recompute_freeze(self):
        # ADR-007: 冻结本次应用筛选时命中的学员；没有查询条件时保持实时视图。
        self._frozen={r['student_id'] for r in self._matched_rows()} if self._query_active() else None

    def _visible_rows(self):
        if self._frozen is None:return self._matched_rows()
        return [r for r in self._rows if r['student_id'] in self._frozen]

    def _mark_stale(self,rows):
        # 行数据变化后不重新筛选，只标记“已不符合当前筛选”；只有重新应用筛选才会移除。
        changed=set()
        for row in rows:
            stale=not self._row_matches_query(row)
            if '_filter_stale' not in row or bool(row['_filter_stale'])!=stale:
                row['_filter_stale']=stale
                changed.add(row['student_id'])
        return changed

    def _scope_rows(self):
        # 业务范围（名单生成、批量未回复）只取真正匹配筛选的学员，过期行仅供显示。
        return [r for r in self.display_rows() if not r.get('_filter_stale')]

    @Slot(int,result='QVariantMap')
    def columnFilterInfo(self,index):
        if not 0<=index<len(self._model.columns):return {}
        key,label=self._model.columns[index]
        counts=Counter(str(r.get(key) or '') for r in self._searched_rows() if self._matches_filters(r,key))
        rule=self._column_filters.get(key,dict(mode='values',values=list(counts)))
        return dict(key=key,label=label,options=[dict(value=v,label=v or '(空白单元格)',count=counts[v]) for v in sorted(counts,key=lambda v:sort_value({key:v},key))],
                    mode=rule['mode'],values=rule.get('values',list(counts)),value=rule.get('value',''))

    @Slot(int,result='QVariantMap')
    def columnInfo(self, index):
        if not 0 <= index < len(self._model.columns): return {}
        key, label = self._model.columns[index]
        values = sorted({str(r.get(key) or '') for r in self._rows}, key=lambda v:sort_value({key:v},key)) if key != 'feedback' else []
        rule = self._column_filters.get(key, {'mode':'contains','value':''})
        return dict(label=label, options=values, **rule)

    @Slot(int,bool)
    def sortColumn(self, index, descending):
        if not -1 <= index < len(self._model.columns): return
        self._sort_column, self._sort_descending = index, descending
        self._sort_key=self._model.columns[index][0] if index>=0 else ''
        self.apply_filter(recompute=False)
        self.queryChanged.emit()

    @Slot(str,bool)
    def sortField(self,key,descending):
        self.sortColumn(next((i for i,c in enumerate(self._model.columns) if c[0]==key),-1),descending)

    @Slot(int,str,str)
    @Slot(str,str,'QVariantList',str)
    def setColumnFilter(self, index, mode, values, value=None):
        if isinstance(index,int):
            if not 0 <= index < len(self._model.columns):return
            key=self._model.columns[index][0]
            value=values
            values=[]
        else:key=index
        if key not in dict(self._model.columns) or mode not in ('contains','exact','empty','notempty','values','clear'):return
        if mode == 'clear' or (mode == 'contains' and not value.strip()):
            self._column_filters.pop(key, None)
        elif mode=='values':
            self._column_filters[key]=dict(mode=mode,values=[str(v) for v in values])
        else:
            self._column_filters[key] = dict(mode=mode,value=value)
        self.apply_filter()
        self.queryChanged.emit()

    @Slot()
    def clearColumnQuery(self):
        self._column_filters.clear()
        self._sort_column = -1
        self._sort_key = ''
        self.apply_filter()
        self.queryChanged.emit()
    @Property('QVariantMap',notify=selectionChanged)
    def selected(self): return self._selected
    @Property(str,notify=changed)
    def summary(self):
        rows = self._rows
        if not self._batch:
            return f'当前全班名单 {len(rows)} 人 · 尚未建立催办批次，显示现有学习数据'
        return f"全班 {len(rows)} 人 · 待反馈 {sum(r['reply_state']=='待反馈' for r in rows)} · 已回复 {sum(r['reply_state']=='已回复' for r in rows)} · 未回复 {sum(r['reply_state']=='未回复' for r in rows)}"
    @Property('QVariantMap',notify=changed)
    def dashboard(self): return self._dashboard

    def refresh_dashboard(self):
        self._dashboard=self.store.dashboard(self._batch)
    @Property(str,notify=changed)
    def template(self): return self.owner.repo.get_setting('campaign_template',TEST_TEMPLATE)
    @Property(str,notify=changed)
    def batchTitle(self):
        return self._batches[self.batchIndex]['created_at'].replace('T',' ') if self.batchIndex>=0 else '尚无催办批次'

    @Property(str,notify=changed)
    def dataNote(self):
        with self.owner.db.connect() as conn:
            managed=conn.execute("SELECT 1 FROM settings WHERE key='roster_managed' AND value='1'").fetchone()
            total=conn.execute('SELECT count(*) FROM class_roster WHERE active=1' if managed else 'SELECT count(*) FROM profiles').fetchone()[0]
            last=max((json.loads(r[0]).get('last_sync_at') or '' for r in conn.execute('SELECT data FROM reminder_data')),default='')
        if self._batch:
            snapshot_last=max((r.get('source_sync') or '' for r in self._rows),default='')
            return f'当前名单 {total} 人 · 所选催办数据获取 {snapshot_last or "未获取"} · 当前学习数据最近获取 {last or "尚未获取"}'
        return f'当前名单 {total} 人 · 当前学习数据最近获取 {last or "尚未获取"}'

    @Property(str,notify=selectionChanged)
    def leaveNote(self):
        value=self._selected.get('exemption_date','')
        if value:return self._selected.get('exemption_text','') + (' · 已到期，恢复催办' if self._selected.get('exemption_expired') else ' · 包含当天') + ('（历史快照）' if not self.canSetExemption else '')
        return '未设置免催日期'

    @Property(str,notify=selectionChanged)
    def previousFeedback(self):
        sid=self._selected.get('student_id','')
        if not sid:return ''
        with self.owner.db.connect() as conn:
            entries=list(conn.execute('SELECT c.created_at,f.content FROM campaign_feedback f JOIN campaigns c ON c.id=f.batch_id WHERE f.student_id=? AND f.batch_id<? ORDER BY f.id DESC LIMIT 10',(sid,self._batch)))
        lines=[r['created_at'].replace('T',' ')+' '+r['content'] for r in entries]
        old=self.owner.repo.get(sid) or {}
        if old.get('feedback_history'):lines.append('迁移前反馈：\n'+old['feedback_history'])
        for key,value in old.get('profile_fields',{}).items():
            if '学员学习反馈' in key and value:lines.append(key+'：'+str(value))
        return '\n'.join(lines) or '暂无以往反馈'

    def reload_batches(self, batch=None, students=None):
        self._batches = self.store.batches()
        self._batch = batch if batch is not None else (self._batches[0]['id'] if self._batches else 0)
        self.reload_rows(students=students)

    def reload_rows(self, prefer=None, students=None, keep_query=False):
        self._model.columns = self.batch_columns([(key,dict(TABLE_COLUMNS)[key]) for key in self._field_order()])
        self.refresh_dashboard()
        self._rows = self.store.rows(self._batch) if self._batch else self.live_roster(students)
        self.apply_filter(prefer, recompute=not keep_query)
        self.changed.emit()

    def live_roster(self, students=None):
        """Read-only preview: viewing the roster must not create a campaign."""
        students=students if students is not None else self.owner.repo.list_students()
        source=self.owner.repo.learning_source()
        with self.owner.db.connect() as conn:
            contacts={r['student_id']:r['remark'] for r in conn.execute('SELECT * FROM student_contacts')}
        rows=[]
        for position,student in enumerate(students):
            sid=student['student_id']
            fields=student.get('profile_fields',{})
            courses=lessons(fields.get('差的课程',student['pending_courses_text']))
            homework=lessons(fields.get('差的作业',student['pending_homework_text']))
            ctotal,ztotal=fields.get('合计完课'),fields.get('合计作业')
            flags=source.get(sid)
            if flags is not None:
                courses=','.join(str(i) for i in range(1,33) if flags.get(f'c{i}')=='F')
                homework=','.join(str(i) for i in range(1,33) if flags.get(f'z{i}')=='F')
                ctotal=sum(flags.get(f'c{i}')=='T' for i in range(1,33))
                ztotal=sum(flags.get(f'z{i}')=='T' for i in range(1,33))
            else:
                courses=homework=''
                ctotal=ztotal=None
            rows.append(dict(student_id=sid,name=student['name'],remark=contacts.get(sid,student['name']),
                courses=courses,homework=homework,
                missing_total=f'{len(courses.split(",")) if courses else 0}/{len(homework.split(",")) if homework else 0}' if flags is not None else '',
                completed_total=f'{ctotal}/{ztotal}' if flags is not None else '',
                completed_courses='' if ctotal is None else str(ctotal),completed_homework='' if ztotal is None else str(ztotal),
                feedback='',draft='',message='',eligible=0,send_state='未建立批次',reply_state='—',
                reason='缺号补位' if student.get('is_placeholder') else student.get('sync_state',''),position=position,
                is_placeholder=student.get('is_placeholder',False),
                exemption_date=student.get('exemption_date',''),exemption_text=student.get('exemption_text',''),exemption_expired=student.get('exemption_expired',False),
                roster_status=student.get('roster_status',''),wechat=fields.get('微信','')))
            if flags is not None and 'U' in flags.values():
                missing_parts = rows[-1]['missing_total'].split('/')
                completed_parts = rows[-1]['completed_total'].split('/')
                for index,prefix,key,total_key in ((0,'c','courses','completed_courses'),(1,'z','homework','completed_homework')):
                    if any(flags.get(f'{prefix}{i}') == 'U' for i in range(1,33)):
                        rows[-1][key], rows[-1][total_key] = '未获取', ''
                        missing_parts[index] = completed_parts[index] = '—'
                rows[-1].update(missing_total='/'.join(missing_parts),completed_total='/'.join(completed_parts),reason='完课或作业数据缺失')
            if student.get('is_placeholder'):
                rows[-1].update(courses='',homework='',missing_total='',completed_total='',completed_courses='',completed_homework='')
        return rows

    @Slot(result=int)
    def refresh_live(self, keep_query=False):
        # New imports/fetches update the preview and follow the newest batch; older snapshots stay frozen.
        refreshed = self.store.refresh_latest_learning()
        self.store.sync_current_identity()
        if refreshed:self._batches = self.store.batches()
        if not self._batch or self.canEdit:self.reload_rows(keep_query=keep_query)
        else:
            self.refresh_dashboard()
            self.changed.emit()
        return refreshed

    def display_rows(self):
        rows = self._visible_rows()
        if self._sort_key:
            key = self._sort_key
            rows = sorted(rows,key=lambda r:self.missing_count(r) if key=='missing_total' else sort_value(r,key),reverse=self._sort_descending)
        elif self._filter == 'targets':
            rows = sorted(rows,key=lambda r:(-self.missing_count(r),r['student_id']))
        else:
            rows = sorted(rows,key=lambda r:r['student_id'])
        self._stale_changed = self._mark_stale(rows)
        return rows

    @staticmethod
    def missing_count(row):
        return sum(int(v) for v in str(row.get('missing_total') or '').split('/') if v.isdigit())

    def apply_filter(self, prefer=None, recompute=True):
        previous = [r['student_id'] for r in self._model.rows]
        if recompute:self._recompute_freeze()
        rows = self.display_rows()
        self._model.set_rows(rows)
        sid = prefer if prefer is not None else self._selected.get('student_id')
        self._selected = next_cursor(rows, lambda r: r['student_id'], sid or '', previous)
        self.selectionChanged.emit()

    @Slot()
    def reapplyFilters(self):
        self.apply_filter()
        self.queryChanged.emit()

    @Slot(str,str)
    def filterRows(self, view, search):
        if view != self._filter:
            self._sort_column = -1
            self._sort_key = ''
            self.queryChanged.emit()
        self._filter,self._search=view,search
        self.apply_filter()

    @Slot(int)
    def selectRow(self,row):
        if 0<=row<len(self._model.rows):
            self._selected=self._model.rows[row]
            self.selectionChanged.emit()

    @Slot()
    def activate(self):
        # 进入模块只重读数据，不重新筛选：处理中的名单不因切换页面而改变（ADR-007）。
        self.refresh_live(keep_query=True)

    @Slot(int)
    def selectBatch(self,index):
        if self.send_busy:return
        if 0<=index<len(self._batches):
            self._batch=self._batches[index]['id']
            self._selected={}
            self.reload_rows()

    @Slot(str)
    def saveTemplate(self,value):
        self.owner.repo.set_setting('campaign_template',value)

    @Slot()
    def createBatch(self):
        if self.owner.busy or self.send_busy: return
        try:
            batch=self.store.create(self.className,self.template)
            self._search=''
            self.reload_batches(batch)
            self.owner.toast.emit('已保存全班快照，可筛选名单并登记反馈')
        except Exception as exc: self.owner.toast.emit(str(exc))

    def simulate(self,failures):
        # Legacy regression-test helper; deliberately not exposed to QML.
        if not self.canEdit: return
        try:
            self.store.simulate(self._batch,failures)
            self.reload_rows()
            self.owner.toast.emit('模拟完成，未向微信发送任何消息')
        except Exception as exc: self.owner.toast.emit(str(exc))

    @Slot(str,str,result=bool)
    def saveDraft(self,sid,content):
        if not self.canEdit or not sid: return False
        try:
            self.store.draft(self._batch,sid,content)
            for row in self._rows:
                if row['student_id']==sid: row['draft']=content
            self.selectionChanged.emit()
            self.changed.emit()
            return True
        except Exception as exc:
            self.owner.toast.emit('草稿保存失败：'+str(exc))
            return False

    @Slot(str,result=bool)
    def submit(self,content):
        if not self.canEdit or not self._selected: return False
        try:
            sid=self._selected['student_id']
            visible=self._model.rows
            index=next(i for i,r in enumerate(visible) if r['student_id']==sid)
            next_id=visible[index+1]['student_id'] if index+1<len(visible) else ''
            self.store.submit(self._batch,sid,content)
            current=self.store.rows(self._batch,sid)[0]
            self._rows=[current if r['student_id']==sid else r for r in self._rows]
            self._model.reconcile_rows(self.display_rows())
            self._selected=next((r for r in self._model.rows if r['student_id']==next_id),self._model.rows[0] if self._model.rows else {})
            self.selectionChanged.emit()
            self.changed.emit()
            self.owner.toast.emit('反馈已记录')
            return True
        except Exception as exc:
            self.owner.toast.emit(str(exc))
            return False

    @Slot()
    def markUnreplied(self):
        if not self.canEdit or self._filter not in ('targets','pending'):return
        try:
            count=self.store.mark_unreplied(self._batch,[r['student_id'] for r in self._scope_rows()])
            self.reload_rows(keep_query=True)
            self.owner.toast.emit(f'已标记 {count} 人未回复；有反馈或草稿者已跳过')
        except Exception as exc:self.owner.toast.emit(str(exc))

    @Slot()
    def setLeave(self):
        if not self.canSetExemption or not self._selected:return
        key=self.editorKey
        value=self.owner.chooseDate(self._selected.get('exemption_date',''))
        if not value:return
        if key != self.editorKey or not self.canSetExemption:
            self.owner.toast.emit('未设置免催：操作期间学员或批次已切换，请重新选择')
            return
        try:
            set_exemption(self.owner.db,self._selected['student_id'],value)
            self.reload_rows(keep_query=True)
            self.owner.profilesModule.refresh(keep_query=True)
            self.owner.toast.emit('免催日期已保存，包含当天；到期后恢复催办')
        except Exception as exc:self.owner.toast.emit(str(exc))

    @Slot()
    def clearLeave(self):
        if not self.canSetExemption or not self._selected:return
        set_exemption(self.owner.db,self._selected['student_id'],'')
        self.reload_rows(keep_query=True)
        self.owner.profilesModule.refresh(keep_query=True)
        self.owner.toast.emit('已清除免催日期，当前催办重新判断')

    @Slot(str,str,result=bool)
    def saveRemark(self,sid,value):
        if not self.canEdit or not sid:return False
        try:
            with self.owner.db.connect() as conn:
                conn.execute('INSERT INTO student_contacts VALUES(?,?) ON CONFLICT(student_id) DO UPDATE SET remark=excluded.remark',(sid,value.strip()))
            return True
        except Exception as exc:
            self.owner.toast.emit('备注保存失败：'+str(exc))
            return False

    def batch_columns(self, columns):
        stamp = next((r['created_at'][:10] for r in self._batches if r['id'] == self._batch), '')
        label = '本次反馈情况'
        if stamp:
            day = date.fromisoformat(stamp)
            label += f'（{day.month}月{day.day}号）'
        return [(key, label if key == 'feedback' else name) for key, name in columns]

    def _field_order(self):
        keys=[key for key,_ in TABLE_COLUMNS]
        try:saved=json.loads(self.owner.repo.get_setting('workflow_field_order','[]'))
        except (ValueError,TypeError):saved=[]
        return list(dict.fromkeys(key for key in saved if key in keys))+[key for key in keys if key not in saved]

    @Property('QVariantList',notify=changed)
    def managedFields(self):
        labels=dict(self.batch_columns(TABLE_COLUMNS))
        try:visible=json.loads(self.owner.repo.get_setting('workflow_field_visibility','{}'))
        except (ValueError,TypeError):visible={}
        return [dict(field_id=key,name=labels[key],show_column=(key=='name' or bool(visible.get(key,key!='student_id'))),
                     locked=key=='name',deletable=False) for key in self._field_order()]

    @Slot(str,bool,result=bool)
    def setFieldVisible(self,key,visible):
        if key not in dict(TABLE_COLUMNS) or key=='name':return False
        values={f['field_id']:f['show_column'] for f in self.managedFields}
        values[key]=bool(visible)
        self.owner.repo.set_setting('workflow_field_visibility',json.dumps(values,ensure_ascii=False))
        self.changed.emit();self.selectionChanged.emit();self.queryChanged.emit()
        return True

    @Slot(str,int,result=bool)
    def moveField(self,key,index):
        keys=self._field_order()
        if key not in keys:return False
        keys.remove(key)
        keys.insert(max(0,min(index,len(keys))),key)
        self.owner.repo.set_setting('workflow_field_order',json.dumps(keys,ensure_ascii=False))
        self.reload_rows()
        self.selectionChanged.emit();self.queryChanged.emit()
        return True

    @Slot('QVariantMap',result='QVariantList')
    def detailFieldsFor(self,row):
        return [dict(key=f['field_id'],label=f['name'],value=str(row.get(f['field_id']) or '')) for f in self.managedFields if f['show_column']]

    def _export_preferences(self):
        keys=[key for key,_ in TABLE_COLUMNS]
        try:data=json.loads(self.owner.repo.get_setting('workflow_export_preferences','{}'))
        except (ValueError,TypeError):data={}
        order=data.get('order',[])
        order=list(dict.fromkeys(k for k in order if k in keys))+[k for k in keys if k not in order]
        selected=data.get('selected',[key for key,_ in EXPORT_COLUMNS])
        selected=set(k for k in selected if k in keys)
        return order,selected

    @Property('QVariantList', notify=changed)
    def exportFields(self):
        order,selected=self._export_preferences()
        labels=dict(self.batch_columns(TABLE_COLUMNS))
        return [dict(key=key,name=labels[key],selected=key in selected) for key in order]

    @Slot('QVariantList','QVariantList',result=bool)
    def saveExportPreferences(self,order,selected):
        keys={key for key,_ in TABLE_COLUMNS}
        if len(order)!=len(keys) or set(order)!=keys or len(set(order))!=len(order) or len(set(selected))!=len(selected) or not set(selected)<=keys:return False
        self.owner.repo.set_setting('workflow_export_preferences',json.dumps(dict(order=order,selected=selected),ensure_ascii=False))
        self.changed.emit()
        return True

    def export_to_path(self, keys, path, *, store=None, batch=None, columns=None):
        store = store or self.store
        batch = self._batch if batch is None else batch
        allowed = dict(columns if columns is not None else self.batch_columns(TABLE_COLUMNS))
        keys = list(dict.fromkeys(keys))
        if not batch:raise ValueError('请先选择催办批次')
        if not keys:raise ValueError('请至少选择一个导出字段')
        if any(key not in allowed for key in keys):raise ValueError('导出字段无效，请重新选择')
        model = DictTableModel([(key,allowed[key]) for key in keys])
        model.set_rows(sorted(store.rows(batch),key=lambda r:r['student_id']))
        return export_table(model,path,set())

    @Slot('QVariantList')
    def exportBatch(self, keys):
        if not self._batch:return
        store,batch=self.store,self._batch
        columns = self.batch_columns(TABLE_COLUMNS)
        if not keys:
            self.owner.toast.emit('请至少选择一个导出字段')
            return
        path,_=QFileDialog.getSaveFileName(None,'导出所选批次全班记录',f'催办记录_{self._batch}.xlsx','Excel (*.xlsx)')
        if not path:return
        try:
            if not path.lower().endswith('.xlsx'):path+='.xlsx'
            count = self.export_to_path(keys,path,store=store,batch=batch,columns=columns)
            self.owner.toast.emit(f'已导出全班 {count} 人，不受筛选影响')
        except Exception as exc:self.owner.toast.emit('导出失败：'+str(exc))

    @Slot(int, result=int)
    def classRosterSize(self, index):
        """Cached roster size of a class, known before a switch so the loading hint is not a lie.

        Read-only probe: never constructs/migrates the target class database. -1 means unknown.
        """
        if not 0 <= index < len(self._classes):
            return -1
        path = self._classes[index]['path']
        if not hasattr(self, '_class_sizes'):
            self._class_sizes = {}
        if path not in self._class_sizes:
            size = -1
            try:
                import sqlite3
                conn = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)
                try:
                    size = conn.execute('SELECT count(*) FROM class_roster WHERE active=1').fetchone()[0]
                finally:
                    conn.close()
            except Exception:
                size = -1
            self._class_sizes[path] = size
        return self._class_sizes[path]

    @Slot(int)
    def selectClass(self,index):
        if self.owner.busy or self.send_busy or not 0<=index<len(self._classes):return
        if hasattr(self.owner,'_terms_module') and self.owner.termsModule.busy:return
        entry=self._classes[index]
        if not hasattr(self, '_class_contexts'):
            self._class_contexts={str(self.owner.db.path):(self.owner.db,self.owner.repo,self.store)}
        context=self._class_contexts.get(entry['path'])
        if context is None:
            db=Database(entry['path'])
            repo=StudentRepository(db)
            store=CampaignStore(db,repo)
            from .sending_store import recover
            recover(db)
            context=(db,repo,store)
            self._class_contexts[entry['path']]=context
        self.owner.db,self.owner.repo,self.store=context
        self.owner.fetchIssuesChanged.emit()
        self.owner._selected={}
        self.class_index=index
        self._selected={}
        self._column_filters.clear()
        self._sort_column = -1
        self._sort_key = ''
        self.queryChanged.emit()
        students=self.owner.refresh()
        self.reload_batches(students=students)
        self.owner._refresh_statistics(students)
        if hasattr(self.owner,'_terms_module') and entry.get('term_id'):
            self.owner.termsModule.alignTerm(entry['term_id'])

    def select_term_id(self, term_id):
        index=next((i for i,e in enumerate(self._classes) if str(e.get('term_id'))==str(term_id)),-1)
        if index >= 0 and index != self.class_index: self.selectClass(index)

    def sync_terms(self, terms, roster_store=None):
        if not terms: return
        from .roster_sync import ensure_classes, sync_roster
        current_path = str(self.owner.db.path)
        self._classes = ensure_classes(self.registry,self._classes,terms)
        if roster_store:
            for term in terms:
                saved = roster_store.load(term['termId'])
                if saved['fetched_at']:
                    entry = next(e for e in self._classes if str(e.get('term_id'))==str(term['termId']))
                    sync_roster(Database(entry['path']),term,saved['rows'])
        self.class_index = next((i for i,e in enumerate(self._classes) if e['path']==current_path),0)
        self.changed.emit()
        if hasattr(self.owner,'_profiles_module'):
            self.owner.refresh()
            self.refresh_live()

    @Slot(str)
    def addClass(self,name):
        name=name.strip()
        if not name or any(c['name']==name for c in self._classes):
            self.owner.toast.emit('请填写不重复的班级名称')
            return
        path,_=QFileDialog.getOpenFileName(None,'选择该班完整画像名单','','Excel (*.xlsx)')
        if not path:return
        try:
            db_path=self.registry.db.path.parent / ('class_'+uuid.uuid4().hex+'.db')
            db=Database(db_path)
            import_profiles(db,path)
            StudentRepository(db).set_setting('class_name',name)
            self._classes.append({'name':name,'path':str(db_path)})
            self.registry.set_setting('workflow_classes',json.dumps(self._classes,ensure_ascii=False))
            self.selectClass(len(self._classes)-1)
        except Exception as exc:self.owner.toast.emit(str(exc))
