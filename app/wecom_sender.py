"""Original v2 flow: search, optionally verify/close float, paste into main chat."""
import time
import os
import struct
from .send_options import normalize
from .message_content import prepare_content


class ContactNotFoundError(RuntimeError):
    """Search did not open a contact float with the requested identity."""


class DispatchError(RuntimeError):
    def __init__(self,message,uncertain=False):
        super().__init__(message)
        self.uncertain=uncertain


class WeComSender:
    def __init__(self,options=None):
        self.options=normalize(options)
        import pyautogui
        import win32gui
        import win32process
        import win32clipboard
        import win32con
        self.keys=pyautogui
        self.gui=win32gui
        self.process=win32process
        self.clip=win32clipboard
        self.constants=win32con
        self.pause_requested=lambda:False

    def _clipboard(self,fmt,data):
        for attempt in range(5):
            try:self.clip.OpenClipboard();break
            except Exception:
                if attempt==4:raise
                time.sleep(.1)
        try:
            self.clip.EmptyClipboard()
            self.clip.SetClipboardData(fmt,data)
        finally:self.clip.CloseClipboard()

    def _copy(self,text):self._clipboard(self.constants.CF_UNICODETEXT,text)

    def copy_chat_item(self,item):
        if item['type']=='text':self._copy(item['text'])
        else:
            data=struct.pack('<IiiII',20,0,0,0,1)+(item['path']+'\0\0').encode('utf-16le')
            self._clipboard(self.constants.CF_HDROP,data)

    def _check(self,hwnd,title,pid):
        foreground=self.gui.GetForegroundWindow()
        if foreground!=hwnd and self.gui.IsWindow(foreground) and self.process.GetWindowThreadProcessId(foreground)[1]==os.getpid():
            time.sleep(.2)
            if self.pause_requested() and self.gui.IsWindow(hwnd) and self.gui.GetWindowText(hwnd).strip()==title and self.process.GetWindowThreadProcessId(hwnd)[1]==pid:
                self.gui.SetForegroundWindow(hwnd);time.sleep(.2)
        if (not self.gui.IsWindow(hwnd) or self.gui.GetForegroundWindow()!=hwnd
                or self.gui.GetWindowText(hwnd).strip()!=title
                or self.process.GetWindowThreadProcessId(hwnd)[1]!=pid):
            raise RuntimeError('企业微信窗口或焦点已变化，停止操作')

    def search_contact_v2(self,contact,options,*,close_on_success=True,activate_on_close=False,capture_title=False):
        windows=self.keys.getWindowsWithTitle('企业微信')
        main=next((w for w in windows if w.title=='企业微信'),None)
        if main is None:raise RuntimeError('请先打开并登录企业微信主窗口')
        if main.isMinimized:main.restore()
        main.activate();time.sleep(options['wait'])
        main_hwnd=self.gui.GetForegroundWindow()
        pid=self.process.GetWindowThreadProcessId(main_hwnd)[1]
        self._check(main_hwnd,'企业微信',pid)
        self.keys.hotkey('ctrl','f');time.sleep(options['wait'])
        self._check(main_hwnd,'企业微信',pid)
        self.keys.hotkey('ctrl','a');self._copy(contact)
        self.keys.hotkey('ctrl','v');time.sleep(options['wait'])
        self._check(main_hwnd,'企业微信',pid)
        self.keys.press('enter');time.sleep(options['wait'])
        self._check(main_hwnd,'企业微信',pid)
        if options['verify_contact'] or not close_on_success:
            self.keys.hotkey('ctrl','o')
            deadline=time.monotonic()+options['timeout']
            hwnd=None
            while time.monotonic()<deadline:
                candidate=self.gui.GetForegroundWindow()
                if candidate!=main_hwnd and self.gui.IsWindow(candidate) and self.process.GetWindowThreadProcessId(candidate)[1]==pid:
                    hwnd=candidate;break
                time.sleep(.1)
            if hwnd is None:raise ContactNotFoundError('未打开联系人浮窗，未发送')
            time.sleep(options['wait'])
            title=self.gui.GetWindowText(hwnd).strip()
            self._check(hwnd,title,pid)
            matched=(contact in title if options['substring_mode'] else title==contact)
            if matched and not close_on_success:
                # capture_title returns the real remark read from the float window
                # and keeps the float open so the caller decides what happens next.
                return (hwnd,pid,title) if capture_title else (hwnd,pid)
            # close_on_success=True: the verified float is never used for sending.
            self.keys.hotkey('ctrl','w');time.sleep(options['wait'])
            if not matched:raise ContactNotFoundError('联系人浮窗标题不匹配，未发送')
            self._check(main_hwnd,'企业微信',pid)
            if activate_on_close:
                # The caller continues in the main window (remark revision needs the
                # foreground main window, not the float it just closed).
                main.activate();time.sleep(options['wait'])
                self._check(main_hwnd,'企业微信',pid)
        return main_hwnd,pid

    def open_contact(self,contact,*,keep_float=True,verify_contact=True):
        """Search, verify the contact and optionally retain the independent chat."""
        if not contact.strip():raise ValueError('联系人姓名不能为空')
        options=dict(self.options,verify_contact=verify_contact)
        return self.search_contact_v2(contact,options,close_on_success=not (verify_contact and keep_float))

    def send(self,contact,content):
        started=False;submitted=0;pasted=0
        options=getattr(self,'options',normalize())
        try:
            items=prepare_content(content)
            main_hwnd,pid=self.search_contact_v2(contact,options)
            time.sleep(options['focus_delay'])
            for index,item in enumerate(items):
                self._check(main_hwnd,'企业微信',pid)
                self.copy_chat_item(item)
                self._check(main_hwnd,'企业微信',pid)
                started=True
                self.keys.hotkey('ctrl','v');pasted+=1
                time.sleep(options['paste_delay'])
                if options['confirm_send'] and (options['single_send'] or index==len(items)-1):
                    self._check(main_hwnd,'企业微信',pid)
                    self.keys.press('enter');submitted+=1
                    time.sleep(options['paste_delay'])
            return '已发送' if options['confirm_send'] else '仅粘贴未发送'
        except Exception as exc:
            raise DispatchError(f'{exc}（已粘贴 {pasted} 项，已执行发送 {submitted} 次）',uncertain=started) from exc
