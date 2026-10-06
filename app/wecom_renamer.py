"""Batch enterprise-WeChat remark revision: search by name, read the float window
title, then hand the contact to ``app/wecom_remark.change_wecom_remark``.

The module owns no desktop logic beyond sequencing: ``WeComSender`` performs the
search and ``change_wecom_remark`` performs the OCR-driven edit.
"""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot, QThread, QCoreApplication

from . import remark_scan as scan
from . import remark_storage as storage
from .send_controller import F11Hotkey
from .send_options import normalize as normalize_options
from .qt_models import DictTableModel
from .wecom_sender import WeComSender

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TITLE_WAIT = 0.5
DEFAULT_TIMEOUT = 3.0
EVIDENCE_DIR = 'wecom_remark_evidence'
COLUMNS = [('student_id', '学号'), ('name', '姓名'), ('observed', '浮窗备注'),
           ('desired', '目标备注'), ('state', '状态'), ('detail', '说明'), ('mark', '标记')]


class RemarkRenameError(RuntimeError):
    """The remark could not be changed; the desktop was left untouched when raised."""


def _option_values(options):
    """Coerce parameters coming from QML or a script into a mapping.

    ``options`` may arrive as a mapping, a JSON string, or None; a missing value
    keeps the default instead of becoming an invalid number.
    """
    if options is None or options == '':
        return {}
    if isinstance(options, str):
        try:
            loaded = json.loads(options)
        except (TypeError, ValueError) as exc:
            raise ValueError('参数格式无效，需为 JSON 对象') from exc
        options = loaded
    if not isinstance(options, dict):
        raise ValueError('参数格式无效，需为对象')
    return options


def _option_number(options, key, default):
    value = options.get(key, default)
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{key} 必须为数字') from exc


def load_change_remark():
    """The OCR-driven editor, imported lazily so the GUI never needs OCR at start-up.

    ``wecom_remark`` pulls in pyautogui/Pillow/RapidOCR; importing it only here keeps
    headless tests and non-Windows environments working, and turns a missing desktop
    dependency into the module's own error type instead of a raw ImportError.
    """
    try:
        from .wecom_remark import change_wecom_remark
    except Exception as exc:
        raise RemarkRenameError(f'备注修改脚本加载失败：{exc}') from exc
    return change_wecom_remark


class RemarkDriver:
    """Locate one contact by 姓名 and read or revise its real remark."""

    def __init__(self, sender, *, options=None, evidence_dir=EVIDENCE_DIR):
        self.sender = sender
        self.options = normalize_options(options)
        self.evidence_dir = Path(evidence_dir)

    def read_remark(self, name):
        """Return the float window title (the real remark), or None when the
        opened contact does not match the searched name."""
        contact = str(name or '').strip()
        if not contact:
            raise RemarkRenameError('姓名为空，无法定位联系人')
        options = dict(self.options, substring_mode=True, verify_contact=True)
        handle, pid, title = self.sender.search_contact_v2(
            contact, options, close_on_success=False, capture_title=True)
        self._close_float(handle, pid)
        return title if scan.remark_contains_name(title, contact) else None

    def change_remark(self, observed, desired):
        """``observed`` must be the title just read from the float window."""
        if scan.remark_matches(observed, desired):
            return observed
        changer = load_change_remark()
        result = changer(str(observed), str(desired), evidence_dir=str(self.evidence_dir))
        if not getattr(result, 'success', False):
            raise RemarkRenameError(getattr(result, 'message', '备注修改未成功'))
        return str(desired)

    def _activate_main_window(self, sender, wait):
        """Bring the enterprise-WeChat main window back to the foreground.

        ``change_wecom_remark`` captures whatever the main window shows, so the
        leftover float must be gone and the main window verified before typing.
        """
        windows = [w for w in sender.keys.getWindowsWithTitle('企业微信') if w.title == '企业微信']
        if not windows:
            raise RemarkRenameError('企业微信主窗口已关闭')
        windows[0].activate()
        time.sleep(wait)
        hwnd = sender.gui.GetForegroundWindow()
        found = sender.process.GetWindowThreadProcessId(hwnd)
        pid = found[1] if isinstance(found, (tuple, list)) else found
        sender._check(hwnd, '企业微信', pid)
        return hwnd, pid

    def _close_float(self, handle, pid):
        # Closing the float returns to the contact's main-window chat, which is the
        # state change_wecom_remark requires. Nothing is typed before this succeeds.
        try:
            self.sender.keys.hotkey('ctrl', 'w')
        except Exception as exc:
            raise RemarkRenameError(f'无法关闭联系人浮窗：{exc}') from exc
        time.sleep(self.options['wait'])
        try:
            return self._activate_main_window(self.sender, self.options['wait'])
        except RemarkRenameError:
            raise
        except Exception as exc:
            raise RemarkRenameError(f'关闭浮窗后未能回到企业微信主窗口：{exc}') from exc


class RemarkWorker(QThread):
    progress = Signal(str)
    rowState = Signal(str, str, str, str)  # student_id, state, observed, detail
    paused = Signal()
    countsChanged = Signal()

    def __init__(self, db, tasks, driver_factory, parent=None):
        super().__init__(parent)
        self.db = db
        self.tasks = list(tasks)
        self.driver_factory = driver_factory
        self.pause_requested = False
        self.stop_requested = False
        self.counts = {scan.COMPLIANT: 0, scan.CHANGED: 0, scan.REVIEW: 0,
                       scan.NOT_FOUND: 0, scan.FAILED: 0, scan.SKIPPED: 0}

    def _tick(self):
        self.countsChanged.emit()

    def run(self):
        try:
            driver = self.driver_factory()
        except Exception as exc:
            self.progress.emit('无法启动：' + str(exc))
            return
        total = len(self.tasks)
        for index, task in enumerate(self.tasks):
            if self.stop_requested:
                self.progress.emit('本轮已结束，未处理的学员可稍后继续')
                return
            if self.pause_requested:
                self.paused.emit()
                while self.pause_requested and not self.stop_requested:
                    self.msleep(200)
                if self.stop_requested:
                    self.progress.emit('本轮已结束，未处理的学员可稍后继续')
                    return
            self.progress.emit(f'{index + 1}/{total} · 正在处理：{task["name"]}')
            try:
                self._process(driver, task)
            except Exception as exc:
                self._record(task, scan.FAILED, '', f'{type(exc).__name__}：{exc}')
                self.progress.emit(f'{index + 1}/{total} · {task["name"]}：失败，已记录并继续下一位（{exc}）')
                continue
        self.progress.emit(self.summary_text())

    def _process(self, driver, task):
        name, desired = task['name'], task['desired']
        if task.get('action') == 'force':
            observed = driver.read_remark(name)
            if observed is None:
                self._record(task, scan.NOT_FOUND, '', '浮窗标题与姓名不匹配，未改名')
                return
            self.progress.emit(f'正在修改备注：{observed} → {desired}')
            saved = driver.change_remark(observed, desired)
            self._record(task, scan.CHANGED, saved, task.get('detail', ''))
            return
        self._scan(driver, task)

    def _scan(self, driver, task):
        name, desired = task['name'], task['desired']
        observed = driver.read_remark(name)
        if observed is None:
            self._record(task, scan.NOT_FOUND, '', '浮窗标题与姓名不匹配，未改名')
            return
        state, detail = scan.classify(observed, name, desired)
        if state == scan.COMPLIANT:
            self._record(task, scan.COMPLIANT, observed, detail)
            return
        if state == scan.REVIEW:
            self._record(task, scan.REVIEW, observed, detail)
            return
        self.progress.emit(f'正在修改备注：{observed} → {desired}')
        saved = driver.change_remark(observed, desired)
        self._record(task, scan.CHANGED, saved, '')

    def _record(self, task, state, observed, detail):
        detail = detail or task.get('detail', '')
        try:
            storage.save_scan(self.db, task['student_id'], observed=observed,
                              desired=task['desired'], state=state, detail=detail)
        except Exception as exc:
            detail = f'{detail}（状态未写入：{exc}）'
        if state in self.counts:
            self.counts[state] += 1
        self.rowState.emit(task['student_id'], state, observed, detail)
        self._tick()

    def summary_text(self):
        parts = [f'本轮完成 {sum(self.counts.values())} 人']
        for state in (scan.CHANGED, scan.COMPLIANT, scan.REVIEW, scan.NOT_FOUND, scan.FAILED):
            if self.counts[state]:
                parts.append(f'{state} {self.counts[state]}')
        if self.counts[scan.REVIEW] or self.counts[scan.NOT_FOUND] or self.counts[scan.FAILED]:
            parts.append('未完成项可稍后重跑或人工处理')
        return '；'.join(parts)


class RemarkRenamer(QObject):
    changed = Signal()
    rowsChanged = Signal()
    selectionChanged = Signal()
    activityChanged = Signal()
    noticeChanged = Signal()
    prefixChanged = Signal()
    modelInfoChanged = Signal()
    pickChanged = Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._rows = []
        self._visible = []
        self._scan_cache = {}
        self._notice = '选择班期并确认前缀后，点击「扫描并批改」；已符合「前缀+姓名」的联系人会直接入库跳过'
        self._prefix = ''
        self._prefix_term = None
        self._options = dict(wait=DEFAULT_TITLE_WAIT, timeout=3.0)
        self._worker = None
        self._paused = False
        self._pause_requested = False
        self._driver = None
        self._hotkey = F11Hotkey(self.pause)
        self._model = DictTableModel(COLUMNS, self)
        self._selected = {}
        self.reload()
        app = QCoreApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    # ---------------------------------------------------------------- properties
    @Property(QObject, constant=True)
    def tableModel(self): return self._model
    @Property('QVariantList', notify=rowsChanged)
    def rows(self):
        """Current persisted rows; QML uses tableModel instead of transferring all rows."""
        return [dict(r) for r in self._rows]
    @Property(str, notify=noticeChanged)
    def notice(self): return self._notice
    @Property(str, notify=prefixChanged)
    def prefix(self): return self._prefix
    @Property(bool, notify=activityChanged)
    def active(self): return self._worker is not None
    @Property(bool, notify=activityChanged)
    def isPaused(self): return self._paused
    @Property(bool, notify=activityChanged)
    def pauseRequested(self): return self._pause_requested
    @Property(bool, notify=activityChanged)
    def busy(self):
        """True while this module or the contact opener owns the desktop."""
        return self._worker is not None or (hasattr(self.owner, '_contact_opener') and self.owner.contactOpener.active)
    @Property(int, notify=changed)
    def total(self): return len(self._rows)
    @Property(int, notify=changed)
    def visibleCount(self): return len(self._visible)
    @Property(int, notify=changed)
    def pendingCount(self): return sum(1 for r in self._rows if scan.needs_work(r['state']))
    @Property(int, notify=changed)
    def doneCount(self): return sum(1 for r in self._rows if r['state'] in (scan.COMPLIANT, scan.CHANGED, scan.SKIPPED))
    @Property(int, notify=changed)
    def changedCount(self): return sum(1 for r in self._rows if r['state'] == scan.CHANGED)
    @Property(int, notify=changed)
    def compliantCount(self): return sum(1 for r in self._rows if r['state'] == scan.COMPLIANT)
    @Property(int, notify=changed)
    def reviewCount(self): return sum(1 for r in self._rows if r['state'] == scan.REVIEW)
    @Property(int, notify=changed)
    def issueCount(self): return sum(1 for r in self._rows if r['state'] in (scan.NOT_FOUND, scan.FAILED))
    @Property(int, notify=changed)
    def duplicateCount(self): return sum(1 for r in self._rows if r['duplicate'])
    @Property(str, notify=changed)
    def summary(self):
        return (f'名单 {len(self._rows)} 人 · 已符合 {self.compliantCount} · 已修改 {self.changedCount} · '
                f'待确认 {self.reviewCount} · 未找到或失败 {self.issueCount} · 存在重名 {self.duplicateCount}')
    @Property(str, notify=changed)
    def className(self):
        try:
            return self.owner.workflow._classes[self.owner.workflow.class_index].get('name', '')
        except Exception:
            return ''
    @Property(str, notify=selectionChanged)
    def cursorText(self):
        row = self._selected
        if not row:
            return ''
        index = next((i for i, r in enumerate(self._visible) if r['student_id'] == row['student_id']), -1)
        return f'选中 第 {index + 1} / {len(self._visible)} 条 · {row["name"]}' if index >= 0 else ''
    @Property(int, notify=pickChanged)
    def pickRevision(self):
        """Bumped by the UI when its local selection changes, so pick marks repaint."""
        return getattr(self, '_pick_revision', 0)

    @Slot()
    def notifyPicked(self):
        self._pick_revision = getattr(self, '_pick_revision', 0) + 1
        self.pickChanged.emit()
    @Property(str, notify=changed)
    def optionsSummary(self):
        return f"浮窗超时 {self._options['timeout']} 秒 · 每步等待 {self._options['wait']} 秒"

    # ------------------------------------------------------------------- roster
    def _scope_people(self):
        db = self.owner.db
        students = storage.load_students(db, require_wechat=True)
        everybody = storage.load_students(db, require_wechat=False)
        duplicates = scan.duplicate_names(everybody or students)
        return students, duplicates

    def _build_row(self, student, duplicates, prefix):
        state_row = student.get('scan') or {}
        name = student['name']
        duplicate = name in duplicates
        return dict(student_id=student['student_id'], name=name,
                    observed=state_row.get('observed', '') or '',
                    desired=scan.desired_remark(prefix, name) if prefix else '',
                    state=state_row.get('state', '') or '',
                    detail=state_row.get('detail', '') or '',
                    duplicate=duplicate, mark='存在重名' if duplicate else '',
                    scanned_at=state_row.get('scanned_at', '') or '')

    @Slot(result=bool)
    def reload(self):
        if self.active:
            self._notice = '正在处理，不能重新读取名单'
            self._notice_changed()
            return False
        try:
            entry = self.owner.workflow._classes[self.owner.workflow.class_index]
            term_no = entry.get('term_no', '')
            term_id = str(entry.get('term_id', ''))
            # The backend builds this module before the term binding is aligned, so the
            # prefix is recomputed whenever the class or its term binding changes.
            if self._prefix_term != (entry.get('path'), term_id) or not self._prefix:
                saved = storage.load_prefix(self.owner.db, term_no)
                self._prefix = saved or scan.term_prefix(term_no)
                self._prefix_term = (entry.get('path'), term_id)
            students, duplicates = self._scope_people()
            self._rows = [self._build_row(s, duplicates, self._prefix) for s in students]
            self._apply_filter(reset_selection=True)
            self._notice = (f'当前班期 {entry.get("name", "")} · 画像「微信=是」{len(self._rows)} 人；'
                            + ('前缀为空，请先填写前缀' if not self._prefix else '已符合目标格式的学员会自动跳过'))
            self.prefixChanged.emit()
            self._notice_changed()
            return True
        except Exception as exc:
            self._notice = '读取名单失败：' + str(exc)
            self._notice_changed()
            return False

    def _apply_filter(self, reset_selection=False):
        rows = [dict(r) for r in self._rows]
        if not rows:
            self._visible = []
            self._model.set_rows([])
            self._selected = {}
            self.rowsChanged.emit()
            self.changed.emit()
            self.selectionChanged.emit()
            return
        rows.sort(key=lambda r: ((r['state'] in (scan.COMPLIANT, scan.CHANGED, scan.SKIPPED)), r['student_id']))
        self._visible = rows
        self._model.set_rows(rows)
        keys = {r['student_id'] for r in rows}
        if reset_selection or self._selected.get('student_id') not in keys:
            self._selected = rows[0]
        else:
            self._selected = next(r for r in rows if r['student_id'] == self._selected['student_id'])
        self.rowsChanged.emit()
        self.changed.emit()
        self.selectionChanged.emit()

    @Slot(int)
    def selectRow(self, index):
        if 0 <= index < len(self._visible):
            self._selected = self._visible[index]
            self.selectionChanged.emit()

    # -------------------------------------------------------------------- tasks
    def _task(self, row, action, detail=''):
        return dict(student_id=row['student_id'], name=row['name'], action=action,
                    desired=row['desired'] or scan.desired_remark(self._prefix, row['name']),
                    detail=detail)

    def _selected_rows(self, keys):
        wanted = {str(k) for k in (keys or [])}
        return [r for r in self._rows if r['student_id'] in wanted]

    @Slot('QVariantList', result=bool)
    def start(self, keys=None):
        """Scan (and revise) the given students; without keys the whole pending scope."""
        if self.active:
            return False
        try:
            if self.owner.workflow.send_busy:
                raise ValueError('其他自动化任务正在运行，请等待完成')
            if not self._prefix:
                raise ValueError('请先填写前缀，例如 py175')
            rows = self._selected_rows(keys) if keys else [r for r in self._rows if scan.needs_work(r['state'])]
            rows = [r for r in rows if r['name'].strip()]
            if not rows:
                raise ValueError('没有需要处理的学员')
            tasks = [self._task(r, 'scan') for r in rows]
            self._launch(tasks, f'本轮将处理 {len(tasks)} 人；已符合「前缀+姓名」的会自动跳过')
            return True
        except Exception as exc:
            self._notice = str(exc)
            self._notice_changed()
            return False

    @Slot('QVariantList', result=bool)
    def forceSelected(self, keys):
        """Rewrite the selected contacts to 前缀+姓名 even when the format is unexpected."""
        if self.active:
            return False
        try:
            if self.owner.workflow.send_busy:
                raise ValueError('其他自动化任务正在运行，请等待完成')
            if not self._prefix:
                raise ValueError('请先填写前缀，例如 py175')
            rows = [r for r in self._selected_rows(keys) if r['name'].strip()]
            if not rows:
                raise ValueError('请先选择要强制修改的学员')
            tasks = [self._task(r, 'force', '人工确认后强制改为目标格式') for r in rows]
            self._launch(tasks, f'强改 {len(tasks)} 人：不论当前格式，统一改为「前缀+姓名」')
            return True
        except Exception as exc:
            self._notice = str(exc)
            self._notice_changed()
            return False

    @Slot(result=bool)
    def retryFailed(self):
        rows = [r for r in self._rows if r['state'] in (scan.FAILED, scan.NOT_FOUND)]
        if not rows:
            self._notice = '没有失败的学员'
            self._notice_changed()
            return False
        return self.start([r['student_id'] for r in rows])

    @Slot(str, result=bool)
    def skip(self, student_id):
        row = next((r for r in self._rows if r['student_id'] == student_id), None)
        if not row:
            return False
        try:
            storage.save_scan(self.owner.db, student_id, observed=row['observed'],
                              desired=row['desired'], state=scan.SKIPPED, detail='人工跳过')
            row.update(state=scan.SKIPPED, detail='人工跳过')
            self._apply_filter()
            self._notice = f'{row["name"]} 已标记跳过，重跑时不再处理'
            self._notice_changed()
            return True
        except Exception as exc:
            self._notice = '跳过失败：' + str(exc)
            self._notice_changed()
            return False

    @Slot(str, 'QVariantMap', result=bool)
    def saveOptions(self, prefix, options):
        if self.active:
            return False
        try:
            values = _option_values(options)
            self._options = normalize_options({
                'wait': _option_number(values, 'wait', DEFAULT_TITLE_WAIT),
                'timeout': _option_number(values, 'timeout', DEFAULT_TIMEOUT)})
            if prefix is not None:
                self._prefix = storage.save_prefix(self.owner.db, prefix)
                # Typing may trigger a debounced save, so only the derived target
                # remark is recomputed here; the roster is re-read on reload().
                for row in self._rows:
                    row['desired'] = scan.desired_remark(self._prefix, row['name']) if self._prefix else ''
                self._apply_filter()
                self.prefixChanged.emit()
            self._notice = f'前缀已保存为「{self._prefix}」；参数：{self.optionsSummary}'
            self._notice_changed()
            return True
        except Exception as exc:
            self._notice = '保存失败：' + str(exc)
            self._notice_changed()
            return False

    def _driver_factory(self):
        sender = WeComSender()
        return RemarkDriver(sender, options=self._options)

    @Slot(result=str)
    def openEvidenceDir(self):
        """Open the screenshot folder kept by change_wecom_remark."""
        path = (ROOT / EVIDENCE_DIR).resolve()
        path.mkdir(parents=True, exist_ok=True)
        try:
            import os
            os.startfile(str(path))
            return str(path)
        except Exception as exc:
            self._notice = f'无法打开留证目录 {path}：{exc}'
            self._notice_changed()
            return str(path)

    def _launch(self, tasks, status):
        driver = self._driver_factory()
        self._hotkey.start()
        self._worker = RemarkWorker(self.owner.db, tasks, lambda: driver, parent=self)
        self._worker.progress.connect(self._progress)
        self._worker.rowState.connect(self._row_state)
        self._worker.paused.connect(self._on_paused)
        self._worker.finished.connect(self._finished)
        self._paused = self._pause_requested = False
        self._notice = status + '；请勿操作电脑，F11 可在当前联系人结束后暂停'
        self._worker.start()
        self.activityChanged.emit()
        self._notice_changed()

    # -------------------------------------------------------------- worker glue
    @Slot(str)
    def _progress(self, message):
        self._notice = message
        self._notice_changed()

    @Slot(str, str, str, str)
    def _row_state(self, student_id, state, observed, detail):
        row = next((r for r in self._rows if r['student_id'] == student_id), None)
        if row:
            row.update(state=state, observed=observed, detail=detail or row['detail'])
        self._apply_filter()

    @Slot()
    def _on_paused(self):
        self._paused = True
        self._notice = '已暂停，可以操作电脑；F11 或「继续」恢复'
        self.activityChanged.emit()
        self._notice_changed()

    @Slot()
    def _finished(self):
        worker, self._worker = self._worker, None
        self._paused = self._pause_requested = False
        self._hotkey.close()
        if worker:
            worker.deleteLater()
        self.reload()
        self.activityChanged.emit()
        self._notice_changed()

    @Slot()
    def pause(self):
        if not self._worker:
            return
        self._pause_requested = True
        self._worker.pause_requested = True
        self._notice = '等待当前联系人处理完成后暂停'
        self.activityChanged.emit()
        self._notice_changed()

    @Slot()
    def resume(self):
        if not self._worker:
            return
        self._paused = self._pause_requested = False
        self._worker.pause_requested = False
        self._notice = '继续处理剩余学员，请勿操作电脑'
        self.activityChanged.emit()
        self._notice_changed()

    @Slot()
    def stop(self):
        if not self._worker:
            return
        self._worker.stop_requested = True
        self._notice = '当前联系人处理完后结束本轮'
        self._notice_changed()

    def shutdown(self):
        if self._worker:
            self._worker.stop_requested = True
            self._worker.pause_requested = False
            self._worker.wait()
        self._hotkey.close()

    def _notice_changed(self):
        self.noticeChanged.emit()
        self.changed.emit()
