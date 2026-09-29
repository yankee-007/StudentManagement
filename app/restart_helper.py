"""Standalone restart helper: no Qt, database or business dependencies."""
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import time
import traceback


LOG_PATH = Path(tempfile.gettempdir()) / 'student-management-restart.log'


def wait_for_exit(pid):
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # Process already exited.
                return
            raise ctypes.WinError(error)
        try:
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) != 0:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)
    else:
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)


def launch(entry, arguments):
    entry = Path(entry).resolve()
    os.chdir(entry.parent)
    sys.path.insert(0, str(entry.parent))
    sys.argv = [str(entry), *arguments]
    # A new cache location also avoids same-size edits within one timestamp tick.
    sys.dont_write_bytecode = True
    os.environ['QML_DISABLE_DISK_CACHE'] = '1'
    with tempfile.TemporaryDirectory(prefix='student-management-code-') as cache:
        sys.pycache_prefix = cache
        runpy.run_path(str(entry), run_name='__main__')


def main():
    mode, *arguments = sys.argv[1:]
    if mode == '--launch':
        launch(arguments[0], arguments[1:])
    elif mode == '--wait':
        pid, entry, *forwarded = arguments
        wait_for_exit(int(pid))
        command = [sys.executable, '-B', str(Path(__file__).resolve()), '--launch', entry, *forwarded]
        options = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
        with LOG_PATH.open('w', encoding='utf-8') as log:
            subprocess.Popen(command, cwd=str(Path(entry).parent), stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, **options)
    else:
        raise ValueError('Unknown restart mode')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        with LOG_PATH.open('a', encoding='utf-8') as log:
            traceback.print_exc(file=log)
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f'程序重启失败，请检查修改后的代码。\n错误详情：{LOG_PATH}', '重启失败', 0x10)
        raise
