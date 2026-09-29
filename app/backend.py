from __future__ import annotations

from pathlib import Path
import json
from datetime import date

from PySide6.QtCore import Property, QObject, QStandardPaths, Signal, Slot, QDate, QTimer, QLocale, QCoreApplication
from PySide6.QtWidgets import QFileDialog, QDialog, QVBoxLayout, QCalendarWidget, QDialogButtonBox

from .database import Database
from .xlsx_export import export_table
from .calendar_widget import LeaveCalendar
from .importer import import_csv, import_rows
from .acquisition.tasks import AcquisitionTask
from .credentials import get_password
from .qt_models import DictTableModel
from .repository import StudentRepository
from .profiles import import_profiles
from .profile_fields import CHOICES, DISPLAY_LABELS, REMOVED_FIELDS


STUDENT_COLUMNS = [
    ("student_id", "学号"), ("name", "姓名"), ("pending_courses_text", "待催完课"),
    ("pending_homework_text", "待催作业"), ("pending_count", "完课/作业"),
    ("status", "状态"), ("next_followup_at", "下次跟进"),
]


class Backend(QObject):
    @Property(QObject, constant=True)
    def contactOpener(self):return self._contact_opener
    @Property(QObject, constant=True)
    def campaignCompanion(self):return self._campaign_companion
    @Property(QObject, constant=True)
    def groupCenter(self):return self._group_center
    @Property(QObject, constant=True)
    def workflow(self):
        return self._workflow
    @Property(QObject, constant=True)
    def profilesModule(self):
        return self._profiles_module
    @Property(QObject, constant=True)
    def profileCompanion(self):
        return self._profile_companion
    @Property(QObject, constant=True)
    def termsModule(self):
        return self._terms_module
    @Property(QObject, constant=True)
    def settingsModule(self):
        return self._settings_module
    toast = Signal(str)
    selectedStudentChanged = Signal()
    systemDateChanged = Signal()
    busyChanged = Signal()
    fetchIssuesChanged = Signal()
    statisticsChanged = Signal()
    columnsChanged = Signal()
    saveNoticeChanged = Signal()
    feedbackChanged = Signal()
    feedbackColumnInserted = Signal(int)

    @Property(str, notify=selectedStudentChanged)
    def selectedStudentId(self):
        return self._selected.get('student_id', '')

    @Property(int, notify=selectedStudentChanged)
    def selectedRow(self):
        return next((i for i, r in enumerate(self.studentModel.rows) if r['student_id'] == self.selectedStudentId), -1)

    @Property(int, notify=selectedStudentChanged)
    def visibleStudentCount(self):
        return len(self.studentModel.rows)

    @Slot(int)
    def moveStudent(self, offset):
        target = self.selectedRow + offset
        if 0 <= target < len(self.studentModel.rows):
            self.selectRow(target)

    @Property(str, notify=feedbackChanged)
    def feedbackHistory(self):
        return self._selected.get('feedback_history', '')

    @Property(str, notify=saveNoticeChanged)
    def saveNotice(self):
        return getattr(self, '_save_notice', '修改后自动保存')

    def _notice(self, text):
        self._save_notice = text
        self.saveNoticeChanged.emit()

    def _update_saved_row(self, student_id):
        # Do not reset the editor or steal focus during typing.
        current = self.repo.get(student_id)
        for index, row in enumerate(self.studentModel.rows):
            if row['student_id'] == student_id:
                self.studentModel.rows[index] = current
                self.studentModel.dataChanged.emit(self.studentModel.index(index, 0), self.studentModel.index(index, len(self.studentModel.columns)-1))
                break
        if self._selected.get('student_id') == student_id:
            self._selected = current

    @Slot(str, str, str, result=bool)
    def autoSaveField(self, student_id, label, value):
        try:
            self.repo.update_profile_field(student_id, label, value)
            self._update_saved_row(student_id)
            self._notice('已自动保存')
            return True
        except Exception as exc:
            self._notice('保存失败：' + str(exc))
            return False

    @Slot(str, 'QVariantMap', result=bool)
    def autoSaveStatus(self, student_id, values):
        try:
            self.repo.update_manual(student_id, dict(values))
            self._update_saved_row(student_id)
            self._refresh_statistics()
            self._notice('已自动保存')
            return True
        except Exception as exc:
            self._notice('保存失败：' + str(exc))
            return False

    @Slot(str, str, result=bool)
    def saveFeedbackDraft(self, student_id, content):
        try:
            if not self.repo.get(student_id):
                raise ValueError('学员不存在')
            self.repo.set_setting('feedback_draft:' + student_id, content)
            self._notice('反馈草稿已自动保存，追加后进入历史')
            return True
        except Exception as exc:
            self._notice('草稿保存失败：' + str(exc))
            return False

    @Slot(str, result=str)
    def feedbackDraft(self, student_id):
        return self.repo.get_setting('feedback_draft:' + student_id)

    @Slot(int, result='QVariantList')
    def editorFields(self, group):
        fields = self._selected.get('profile_fields', {})
        result = []
        for label, value in fields.items():
            if label in {'学号','学员姓名','姓名','合计完课','差的课程','合计作业','差的作业'} | REMOVED_FIELDS:
                continue
            category = 2 if '学员学习反馈' in label else (1 if label in {'学习目的','学习计划','开学时间','军训时间','免催','免催原因','免催结束日期'} or label.startswith('画像情况') else 0)
            if category == group:
                result.append({'label':label, 'displayLabel':DISPLAY_LABELS.get(label,label), 'options':CHOICES.get(label,[]), 'value':'' if value is None else str(value), 'editable':category != 2})
        return result

    @Property('QVariantList', notify=columnsChanged)
    def columnLabels(self):
        return [label for key, label in self.studentModel.columns]

    @Property('QVariantList', notify=columnsChanged)
    def defaultHiddenColumns(self):
        return list(range(5, len(self.studentModel.columns))) if self.repo.profile_columns() else [0]

    @Slot()
    def importProfile(self):
        if self._busy:
            return
        path, _ = QFileDialog.getOpenFileName(None, '导入完整画像名单', '', 'Excel 工作簿 (*.xlsx)')
        if path:
            try:
                count = import_profiles(self.db, path)
                self.refresh()
                self.workflow.refresh_live()
                self.toast.emit(f'已建立 {count} 人画像名单，原 Excel 未修改')
            except Exception as exc:
                self.toast.emit(str(exc))

    @Slot(str, result=bool)
    def addFeedback(self, content):
        try:
            entry = self.repo.add_feedback(self._selected.get('student_id',''), content)
            self._apply_feedback(entry)
            self._notice('反馈已追加保存')
            self.toast.emit('学习反馈已按系统日期追加保存')
            return True
        except Exception as exc:
            self.toast.emit(str(exc))
            return False

    def _apply_feedback(self, entry):
        """Update only the affected in-memory row; never reload the class."""
        stamp = entry['created_at']
        key = 'feedback:' + stamp[:10]
        columns = self.studentModel.columns
        if key not in [k for k, _ in columns] and any(k.startswith('profile:') for k, _ in columns):
            # Date columns remain chronological even if the system date changes.
            index = next((i for i, (k, _) in enumerate(columns)
                          if k == 'sync_state' or (k.startswith('feedback:') and k > key)), len(columns))
            from PySide6.QtCore import QModelIndex
            self.studentModel.beginInsertColumns(QModelIndex(), index, index)
            columns.insert(index, (key, '学员学习反馈（' + stamp[:10] + '）'))
            self.studentModel.endInsertColumns()
            self.feedbackColumnInserted.emit(index)
            self.columnsChanged.emit()
        current = dict(self._selected)
        current[key] = (current.get(key, '') + '\n' + stamp[11:] + ' ' + entry['content']).strip()
        current['feedback_history'] = (current.get('feedback_history', '') + '\n' + stamp.replace('T',' ') + ' ' + entry['content']).strip()
        for index, row in enumerate(self.studentModel.rows):
            if row['student_id'] == entry['student_id']:
                self.studentModel.rows[index] = current
                self.studentModel.dataChanged.emit(self.studentModel.index(index, 0), self.studentModel.index(index, len(columns)-1))
                break
        self._selected = current
        self.feedbackChanged.emit()

    @Slot(str, str)
    def saveProfileField(self, label, value):
        try:
            self.repo.update_profile_field(self._selected.get('student_id', ''), label, value)
            self.refresh()
            self.toast.emit('画像字段已保存')
        except Exception as exc:
            self.toast.emit(str(exc))

    def __init__(self, db_path: str | Path | None = None):
        super().__init__()
        if db_path is None:
            base = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation))
            db_path = base / "followup.db"
        self.db = Database(db_path)
        self.repo = StudentRepository(self.db)
        self.studentModel = DictTableModel(STUDENT_COLUMNS, self)
        self._view = "all"
        self._search = ""
        self._selected: dict = {}
        self._today = QDate.currentDate()
        self._date_timer = QTimer(self)
        self._date_timer.timeout.connect(self._check_date)
        self._date_timer.start(1000)
        self._busy = False
        self._statistics = ""
        self._fetch_task = None
        self._create_after_fetch = False
        self.refresh()
        from .workflow import Workflow
        self._workflow = Workflow(self)
        from .profile_module import ProfileModule
        self._profiles_module = ProfileModule(self)
        from .profile_companion import ProfileCompanion
        self._profile_companion = ProfileCompanion(self)
        from .term_module import TermModule
        self._terms_module = TermModule(self)
        from .settings_module import SettingsModule
        self._settings_module = SettingsModule(self)
        from .group_center import GroupCenter
        self._group_center = GroupCenter(self)
        from .contact_opener import ContactOpener
        self._contact_opener = ContactOpener(self)
        from .campaign_companion import CampaignCompanion
        self._campaign_companion = CampaignCompanion(self)
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self._wait_for_fetch)
        self._workflow.sync_terms(self._terms_module._terms,self._terms_module.store)
        entry=self._workflow._classes[self._workflow.class_index]
        if entry.get('term_id'): self._terms_module.alignTerm(entry['term_id'])

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Property(str, notify=fetchIssuesChanged)
    def fetchIssues(self):
        return '\n'.join(json.loads(self.repo.get_setting('last_fetch_issues', '[]')))

    @Property(str, notify=systemDateChanged)
    def systemDate(self):
        return QLocale(QLocale.Chinese, QLocale.China).toString(self._today, "yyyy年MM月dd日 dddd")

    def _check_date(self):
        today = QDate.currentDate()
        if today != self._today:
            self._today = today
            self.systemDateChanged.emit()
            self.refresh()
            self.workflow.reload_rows()

    @Property(str, notify=statisticsChanged)
    def statistics(self):
        return self._statistics

    @Slot(str, result=str)
    def chooseDate(self, current):
        return self._choose_date(current, True)

    @Slot(str, result=str)
    def chooseProfileDate(self, current):
        return self._choose_date(current, False)

    def _choose_date(self, current, exemption):
        dialog = QDialog()
        dialog.setWindowTitle("选择免催日期" if exemption else "选择日期")
        dialog.setFixedSize(340, 300)
        dialog.setStyleSheet('''
            QDialog { background: #ffffff; }
            QCalendarWidget { font-size: 14px; }
            QCalendarWidget QWidget#qt_calendar_navigationbar { background: #eef2ff; border-radius: 8px; }
            QCalendarWidget QToolButton { color: #335cff; padding: 10px; border: none; border-radius: 6px; }
            QCalendarWidget QToolButton:hover { background: #dce6ff; }
            QCalendarWidget QAbstractItemView { background: white; color: #344054; selection-background-color: #335cff; selection-color: white; border: none; outline: none; }
            QPushButton { padding: 9px 22px; border: 1px solid #d0d5dd; border-radius: 6px; background: #f9fafb; color: #344054; }
            QPushButton:default { background: #335cff; color: white; border: none; }
        ''')
        layout = QVBoxLayout(dialog)
        calendar = LeaveCalendar(dialog)
        calendar.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        calendar.setGridVisible(False)
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        if exemption:calendar.setMinimumDate(QDate.currentDate())
        calendar.setDateEditEnabled(False)
        parsed = QDate.fromString(current, "yyyy-MM-dd")
        calendar.setSelectedDate(parsed if parsed.isValid() and (not exemption or parsed >= QDate.currentDate()) else QDate.currentDate())
        date_timer = QTimer(dialog)
        date_timer.timeout.connect(lambda: calendar.setMinimumDate(QDate.currentDate()))
        if exemption:date_timer.start(1000)
        layout.addWidget(calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确认日期")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        return calendar.selectedDate().toString("yyyy-MM-dd") if dialog.exec() else current

    @Slot(str, result=str)
    def dayAfter(self, value):
        parsed = QDate.fromString(value, "yyyy-MM-dd")
        return parsed.addDays(1).toString("yyyy-MM-dd") if parsed.isValid() else ""

    @Slot()
    def createCampaign(self):
        if self._busy or self.termsModule.busy or self.workflow.send_busy:
            self.toast.emit('正在获取数据，请等待完成')
            return
        self._create_after_fetch = True
        if not self.fetchData():
            self._create_after_fetch = False

    @Slot(result=bool)
    def fetchData(self):
        if self._busy or self.workflow.send_busy:
            return False
        if self.termsModule.busy:
            self.toast.emit('班期名单正在获取，请等待完成。')
            return False
        try:
            entry = self.workflow._classes[self.workflow.class_index]
            term_id = entry.get('term_id')
            if not term_id:
                raise ValueError('当前班级未关联追光鲸鱼班期，请先在班期学员中选择班期。')
            binding = self.settingsModule.bindingFor(term_id)
            if not binding:
                raise ValueError('当前班期尚未确认作业平台班级，请到设置中绑定；未获取数据。')
            registry = self.workflow.registry
            c_user = registry.get_setting('completion_username', '')
            h_user = registry.get_setting('homework_admin_id', '')
            c_pass, h_pass = get_password('completion', c_user), get_password('homework', h_user)
            if not c_pass or not h_pass:
                raise ValueError('请先在设置中保存两个平台的账号和密码。')
            self._fetch_db_path = str(self.db.path)
            self._class_name = entry['name']
            task = AcquisitionTask('learning', (c_user, c_pass), (h_user, h_pass),
                self.workflow.registry.db.path.parent / 'platform_sessions', term_id, binding=binding, parent=self)
            self._fetch_task = task
            task.succeeded.connect(self._fetch_succeeded)
            task.failed.connect(self._fetch_failed)
            task.finished.connect(self._release_fetch_task)
            task.finished.connect(task.deleteLater)
            self._busy = True
            self.busyChanged.emit()
            task.start()
            return True
        except ValueError as exc:
            self.toast.emit(str(exc))
            return False
        except Exception:
            self.toast.emit('无法启动获取任务，请检查平台设置及依赖。')
            return False

    def _finish_fetch(self):
        self._busy = False
        self.busyChanged.emit()

    def _wait_for_fetch(self):
        if self._fetch_task and self._fetch_task.isRunning():
            self._fetch_task.wait()

    def _release_fetch_task(self):
        if self.sender() is self._fetch_task:
            self._fetch_task = None

    def _fetch_failed(self, message):
        self._create_after_fetch = False
        self.repo.set_setting('last_fetch_issues', json.dumps([message], ensure_ascii=False))
        self.fetchIssuesChanged.emit()
        self._finish_fetch()
        self.toast.emit(message)

    def _fetch_succeeded(self, payload):
        create_campaign = False
        try:
            if str(self.db.path) != self._fetch_db_path:
                raise ValueError('获取期间班期已切换，未导入数据或创建催办')
            rows, source_stats = payload
            # Validate the joined source before touching any class database.
            profiles = {r['student_id']: r['name'] for r in self.repo.list_students()}
            if profiles and not any(profiles.get(r['学号']) == r['姓名'] for r in rows):
                raise ValueError('两平台数据与当前班期名单无人匹配，旧数据未覆盖。')
            indexed = {r['学号']: r for r in rows}
            issues = []
            for student in self.repo.list_students():
                if student.get('is_placeholder') or student.get('roster_status','') not in ('','在读'):
                    continue
                sid = student['student_id']
                row = indexed.get(sid)
                if row is None:
                    issues.append(f'{sid} {student["name"]}：未获取学习数据')
                elif row['姓名'] != student['name']:
                    issues.append(f'{sid}：与班期名单姓名不一致')
                elif any(str(row.get(f'{p}{i}', row.get(f'{p.lower()}{i}', 'U'))).upper() == 'U' for p in ('C','Z') for i in range(1,33)):
                    issues.append(f'{sid} {student["name"]}：完课或作业数据缺失')
            self.repo.set_setting('last_fetch_issues', json.dumps(issues, ensure_ascii=False))
            self.fetchIssuesChanged.emit()
            if issues and self._create_after_fetch:
                raise ValueError(f'有 {len(issues)} 名在读学员数据不完整，未新建催办，原学习数据保留。请核对平台名单并重新获取。\n' + '\n'.join(issues[:5]))
            result = import_rows(self.db, rows)
            if not result['rows']:
                raise ValueError("本次没有获取到学员，保留原名单")
            if not result['matched']:
                raise ValueError('获取完成，但没有学员与班期名单匹配；未创建催办，请检查学号和姓名')
            self.repo.set_setting('class_name', self._class_name)
            self.refresh()
            self.workflow.refresh_live()
            self.toast.emit(f"获取完成：匹配 {result['matched']} 人，姓名不符 {result['mismatched']} 人，名单外 {result['unknown']} 人，未获取 {result['missing']} 人；两平台在读匹配 {source_stats['双方在读并导出']} 人")
            create_campaign = self._create_after_fetch
        except Exception as exc:
            self.toast.emit(str(exc))
        finally:
            self._create_after_fetch = False
            self._finish_fetch()
        if create_campaign:
            self.workflow.createBatch()

    def _refresh_statistics(self):
        snapshot = json.loads(self.repo.get_setting('snapshot', '[]'))
        students = {r['student_id']: r for r in self.repo.list_students()}
        snapshot = [r for r in snapshot if r['student_id'] in students]
        eligible = [r for r in snapshot if not (
            students.get(r['student_id'], {}).get('status') == '请假'
            and (students[r['student_id']].get('exemption_end') or '9999-12-31') >= date.today().isoformat()
        )]
        count = len(eligible)
        lines = [f"{self.repo.get_setting('class_name', '当前班级')} · 统计 {count} 人 · 请假排除 {len(snapshot)-count} 人"]
        if self.repo.profile_columns():
            lines.append(f"画像总名单 {len(students)} 人 · 本次匹配 {len(snapshot)} 人 · 未匹配 {len(students)-len(snapshot)} 人（不计入本次统计）")
        for prefix, label in [('c', '完课'), ('z', '作业')]:
            lessons = [i for i in range(1,33) if any(r['flags'].get(f'{prefix}{i}', 'N') in ('T','F') for r in snapshot)]
            if not lessons or not count:
                lines.append(f"{label}率：暂无可统计数据")
                continue
            total = sum(all(r['flags'].get(f'{prefix}{i}') == 'T' for i in lessons) for r in eligible)
            rates = [f"第{i}节 {sum(r['flags'].get(f'{prefix}{i}') == 'T' for r in eligible)/count:.0%}" for i in lessons]
            lines.append(f"整体{label}率 {total/count:.1%}（{total}/{count}） · " + ' / '.join(rates))
        self._statistics = '\n'.join(lines)
        self.statisticsChanged.emit()

    @Property("QVariantMap", notify=selectedStudentChanged)
    def selectedStudent(self):
        return self._selected

    @Slot()
    def refresh(self):
        columns = self.repo.profile_columns() or STUDENT_COLUMNS
        if columns != self.studentModel.columns:
            self.studentModel.beginResetModel()
            self.studentModel.columns = columns
            self.studentModel.endResetModel()
            self.columnsChanged.emit()
        self.studentModel.set_rows(self.repo.list_students(self._view, self._search))
        self._refresh_statistics()
        if self._selected:
            self._selected = self.repo.get(self._selected["student_id"]) or {}
            self.selectedStudentChanged.emit()
            self.feedbackChanged.emit()
        if hasattr(self, '_profiles_module'):
            self._profiles_module.refresh()

    @Slot(str)
    def setView(self, view):
        self._view = view
        self.refresh()

    @Slot(str)
    def setSearch(self, search):
        self._search = search
        self.refresh()

    @Slot(int)
    def selectRow(self, row):
        if not 0 <= row < len(self.studentModel.rows):
            return
        if self.studentModel.rows[row]['student_id'] == self.selectedStudentId:
            return
        self._selected = self.studentModel.get(row)
        self._notice('修改后自动保存')
        self.selectedStudentChanged.emit()
        self.feedbackChanged.emit()

    @Slot()
    def chooseImport(self):
        path, _ = QFileDialog.getOpenFileName(None, "导入每日 CSV", "", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            result = import_csv(self.db, path)
            self.refresh()
            self.toast.emit(f"导入完成：新增 {result['inserted']}，更新 {result['updated']}")
        except Exception as exc:
            self.toast.emit(f"导入失败：{exc}")

    @Slot("QVariantMap")
    def saveStudent(self, values):
        if not self._selected:
            self.toast.emit("请先选择学员")
            return
        try:
            self._selected = self.repo.update_manual(self._selected["student_id"], dict(values))
            self.refresh()
            self.toast.emit("状态已保存，名单已重新计算")
        except Exception as exc:
            self.toast.emit(f"保存失败：{exc}")

    @Slot("QVariantList")
    def exportXlsx(self, hidden_columns):
        path, _ = QFileDialog.getSaveFileName(
            None, "导出当前主名单", f"主名单_{date.today().isoformat()}.xlsx", "Excel 工作簿 (*.xlsx)"
        )
        if not path:
            return
        if not path.lower().endswith('.xlsx'):
            path += '.xlsx'
        try:
            count = export_table(self.studentModel, path, set(hidden_columns))
            self.toast.emit(f"已按当前显示导出 {count} 人")
        except PermissionError:
            self.toast.emit("无法写入文件，请关闭已打开的 Excel 文件或选择其他保存位置")
        except Exception as exc:
            self.toast.emit(f"导出失败：{exc}")
