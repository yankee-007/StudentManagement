"""Qt-facing dispatch lifecycle, global F11 pause and durable result reporting."""
import ctypes
import os
import threading
from PySide6.QtCore import QObject, Property, Signal, Slot, QThread, QCoreApplication, QAbstractNativeEventFilter
from . import sending_store as receipts
from .wecom_sender import DispatchError


class F11Hotkey(QAbstractNativeEventFilter):
    KEY_ID=0x5A31
    def __init__(self,callback):
        super().__init__()
        self.callback=callback
        self.registered=False

    def start(self):
        if os.name!='nt':raise RuntimeError('正式发送仅支持 Windows')
        if not ctypes.windll.user32.RegisterHotKey(None,self.KEY_ID,0x4000,0x7A):
            raise RuntimeError('无法注册全局 F11（可能已被其他程序占用），未开始发送')
        self.registered=True
        QCoreApplication.instance().installNativeEventFilter(self)

    def nativeEventFilter(self,event_type,message):
        from ctypes.wintypes import MSG
        msg=MSG.from_address(int(message))
        if msg.message==0x0312 and msg.wParam==self.KEY_ID:
            self.callback()
            return True,0
        return False,0

    def close(self):
        if self.registered:
            QCoreApplication.instance().removeNativeEventFilter(self)
            ctypes.windll.user32.UnregisterHotKey(None,self.KEY_ID)
            self.registered=False


class SendWorker(QThread):
    progress=Signal(str)
    rowFinished=Signal()
    paused=Signal()
    def __init__(self,store,batch,tasks,driver_factory,parent=None,adapter=None,options=None,continue_on_failure=False):
        super().__init__(parent)
        self.store,self.batch,self.tasks,self.driver_factory=store,batch,tasks,driver_factory
        self.receipts=adapter or receipts
        self.options=options or {}
        # Group-center rounds keep going after a per-contact failure; the campaign
        # sender keeps stopping the round so the operator can inspect the desktop.
        self.continue_on_failure=continue_on_failure
        self.pause_requested=threading.Event()
        self.stop_requested=threading.Event()
        self.wake=threading.Event()

    def pause(self):self.pause_requested.set();self.wake.set()
    def resume(self):self.pause_requested.clear();self.wake.set()
    def stop(self):self.stop_requested.set();self.wake.set()

    def run(self):
        try:
            driver=self.driver_factory()
            driver.pause_requested=self.pause_requested.is_set
            failed=0;uncertain=0
            for index,task in enumerate(self.tasks):
                if self.pause_requested.is_set() and not self.stop_requested.is_set():
                    self.paused.emit()
                    while self.pause_requested.is_set() and not self.stop_requested.is_set():
                        self.wake.wait(.2);self.wake.clear()
                if self.stop_requested.is_set():
                    self.progress.emit('本轮已结束，未处理的学员可重新预览后发送');return
                attempt=self.receipts.claim(self.store,self.batch,task)
                if attempt is None:
                    self.progress.emit(f'{index+1}/{len(self.tasks)} · 学员条件或消息已变更，跳过：{task["name"]}')
                    continue
                self.progress.emit(f'{index+1}/{len(self.tasks)} · 正在处理：{task["contact"]}')
                try:
                    result=driver.send(task['contact'],task.get('content',task['message']))
                except DispatchError as exc:
                    result=receipts.UNKNOWN if exc.uncertain else receipts.FAILED
                    self.receipts.finish(self.store,self.batch,task,attempt,result,str(exc))
                    self.rowFinished.emit()
                    if not self.continue_on_failure:
                        self.progress.emit(f'{task["name"]}：{result}，{exc}。本轮停止，请检查后重新预览。')
                        return
                    # The failure stays in the pending list; the round keeps its order.
                    if exc.uncertain:uncertain+=1
                    else:failed+=1
                    self.progress.emit(f'{index+1}/{len(self.tasks)} · {task["name"]}：{result}，{exc}。已记录，继续下一位')
                    self.wake.wait(self.options.get('interval',0));self.wake.clear()
                    continue
                except Exception as exc:
                    self.receipts.finish(self.store,self.batch,task,attempt,receipts.UNKNOWN,str(exc))
                    self.rowFinished.emit()
                    self.progress.emit('发送阶段异常，结果待人工确认；本轮停止：'+str(exc));return
                state='仅粘贴未发送' if result=='仅粘贴未发送' else receipts.SENT
                self.receipts.finish(self.store,self.batch,task,attempt,state,'仅粘贴，未执行回车' if state!='已发送' else '已发送')
                self.rowFinished.emit()
                self.wake.wait(self.options.get('interval',0));self.wake.clear()
            if failed or uncertain:
                summary=[]
                if failed:summary.append(f'{failed} 人发送失败仍在待处理，可重新预览后重试')
                if uncertain:summary.append(f'{uncertain} 人结果待确认，需人工核实')
                self.progress.emit('本轮处理完成；'+'；'.join(summary))
            else:
                self.progress.emit('本轮处理完成，发送结果已自动记录')
        except Exception as exc:
            self.progress.emit('发送停止：'+str(exc)+'；如有发送中记录，请人工确认，勿直接重发')


class SendController(QObject):
    changed=Signal()
    def __init__(self,workflow):
        super().__init__(workflow)
        self.wf=workflow
        self._worker=None
        self._paused=False
        self._pause_requested=False
        self._status='配置话术和前缀后，预览并确认正式发送'
        self._preview=[]
        self._context=None
        self._test_mode=False
        self._dispatch_store=None
        self._dispatch_batch=0
        self._hotkey=F11Hotkey(self.pause)
        app=QCoreApplication.instance()
        if app:app.aboutToQuit.connect(self.shutdown)

    @Property(bool,notify=changed)
    def active(self):return self._worker is not None
    @Property(bool,notify=changed)
    def isPaused(self):return self._paused
    @Property(bool,notify=changed)
    def pauseRequested(self):return self._pause_requested
    @Property(str,notify=changed)
    def status(self):return self._status
    @Property('QVariantList',notify=changed)
    def preview(self):return self._preview
    @Property(bool,notify=changed)
    def testMode(self):return self._test_mode
    @Property('QVariantList',notify=changed)
    def testResults(self):
        if not self._test_mode or not self._dispatch_store:return []
        return self._dispatch_store.rows(self._dispatch_batch)
    @Property(str,notify=changed)
    def prefix(self):return receipts.config(self.wf.store,self.wf._batch)['prefix'] if self.wf._batch else ''
    @Property(str,notify=changed)
    def template(self):return receipts.config(self.wf.store,self.wf._batch)['template'] if self.wf._batch else self.wf.template

    @Slot(str,str,result=bool)
    def prepare(self,prefix,template):
        if self.active or not self.wf.canEdit:return False
        try:
            self._test_mode=False
            self._dispatch_store=self.wf.store
            self._dispatch_batch=self.wf._batch
            receipts.recover(self.wf.store.db)
            receipts.save_config(self.wf.store,self.wf._batch,prefix,template)
            self._preview=receipts.plan(self.wf.store,self.wf._batch)
            self._context=(str(self.wf.store.db.path),self.wf._batch)
            self.wf.reload_rows(keep_query=True)
            self._status=f'本轮将发送 {len(self._preview)} 人；不受表格搜索或列筛选影响'
            self.changed.emit()
            return bool(self._preview)
        except Exception as exc:
            self._preview=[];self._context=None
            self._status='准备失败：'+str(exc);self.changed.emit();return False

    @Slot('QVariantList',str,str,result=bool)
    def prepareTest(self,people,prefix,template):
        if self.active:return False
        self._preview=[];self._context=None
        try:
            from .test_dispatch_data import build_test_campaign
            path=self.wf.registry.db.path.parent/'send_test.db'
            from pathlib import Path
            if path.resolve() in {Path(e['path']).resolve() for e in self.wf._classes}:
                raise ValueError('测试库路径与真实班级数据库冲突，未生成测试数据')
            store,batch=build_test_campaign(path,people,prefix,template)
            self._test_mode=True
            self._dispatch_store,self._dispatch_batch=store,batch
            self._preview=receipts.plan(store,batch)
            self._context=(str(store.db.path),batch)
            self._status=f'测试群发：将真实发送给 {len(self._preview)} 位测试人员，不写入真实班级；每次重新生成是新一轮测试'
            self.changed.emit();return bool(self._preview)
        except Exception as exc:
            self._status='测试数据无效：'+str(exc);self.changed.emit();return False

    @Slot(result=bool)
    def start(self):
        if self.active or (not self._test_mode and not self.wf.canEdit) or not self._preview:return False
        try:
            if self.wf.owner.busy or self.wf.owner.termsModule.busy:raise ValueError('请等待数据获取完成')
            if self.wf.owner.groupCenter.active:raise ValueError('群发中心正在处理，请先结束本轮')
            if self.wf.owner.contactOpener.active:raise ValueError('正在打开画像联系人，请等待完成')
            if self.wf.owner.profilesModule.wechatVerifier.active:raise ValueError('正在批量验证微信，请等待完成')
            store=self._dispatch_store if self._test_mode else self.wf.store
            batch=self._dispatch_batch if self._test_mode else self.wf._batch
            if self._context!=(str(store.db.path),batch) or receipts.plan(store,batch)!=self._preview:
                raise ValueError('名单、话术或班期已变化，请重新预览并确认')
            # Dependencies are checked before any attempt is claimed or desktop keys sent.
            from .wecom_sender import WeComSender
            driver=WeComSender()
            self._hotkey.start()
            self._worker=SendWorker(store,batch,list(self._preview),lambda:driver,self)
            self._worker.progress.connect(self._on_progress)
            self._worker.rowFinished.connect(self._on_row_finished)
            self._worker.paused.connect(self._on_paused)
            self._worker.finished.connect(self._on_finished)
            self._paused=self._pause_requested=False
            self._status='发送已启动，请勿操作鼠标键盘；F11 在当前联系人处理完后暂停'
            self._worker.start();self.changed.emit();return True
        except Exception as exc:
            self._hotkey.close()
            self._status='未开始发送：'+str(exc);self.changed.emit();return False

    @Slot()
    def pause(self):
        if self._worker and not self._paused:
            self._pause_requested=True;self._worker.pause()
            self._status='已请求暂停，等待当前联系人处理完成';self.changed.emit()

    @Slot()
    def resume(self):
        if self._worker and self._paused:
            self._paused=self._pause_requested=False
            self._status='继续处理剩余名单，请勿操作鼠标键盘'
            self._worker.resume();self.changed.emit()

    @Slot()
    def stop(self):
        if self._worker:
            self._worker.stop();self._status='当前联系人处理完后结束本轮';self.changed.emit()

    @Slot(str,bool,result=bool)
    def resolve(self,editor_key,was_sent):
        if self.active or editor_key!=self.wf.editorKey or not self.wf.canEdit:return False
        try:
            receipts.resolve(self.wf.store,self.wf._batch,self.wf.selected['student_id'],was_sent)
            self.wf.reload_rows(keep_query=True)
            self._status='已保存人工核实结果';self.changed.emit();return True
        except Exception as exc:
            self._status=str(exc);self.changed.emit();return False

    @Slot(str)
    def _on_progress(self,text):self._status=text;self.changed.emit()
    @Slot()
    def _on_row_finished(self):
        if not self._test_mode:self.wf.reload_rows(keep_query=True)
        self.changed.emit()
    @Slot()
    def _on_paused(self):
        self._paused=True;self._status='已暂停，可以操作电脑；点击继续发送处理剩余名单';self.changed.emit()
    @Slot()
    def _on_finished(self):
        worker=self._worker
        self._worker=None
        self._paused=self._pause_requested=False
        self._hotkey.close()
        if worker:worker.deleteLater()
        receipts.recover(self._dispatch_store.db)
        if not self._test_mode:self.wf.reload_rows(keep_query=True)
        self.changed.emit()

    def shutdown(self):
        if self._worker:
            self._worker.stop()
            self._worker.wait()
        self._hotkey.close()
