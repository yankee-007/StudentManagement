"""UI adapter for restarting the process; independent of Backend."""
import os
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, Slot


class RestartController(QObject):
    def __init__(self, entry, arguments=(), parent=None):
        super().__init__(parent)
        self.entry = str(Path(entry).resolve())
        self.arguments = list(arguments)
        self.window = None
        self.requested = False

    @Slot()
    def requestRestart(self):
        if self.requested or self.window is None:
            return
        self.requested = True
        # QWindow.close() runs the normal QML closing handler and may be refused.
        if not self.window.close():
            self.requested = False

    def start_helper(self):
        helper = str(Path(__file__).with_name('restart_helper.py').resolve())
        started, _ = QProcess.startDetached(sys.executable,
            ['-B', helper, '--wait', str(os.getpid()), self.entry, *self.arguments],
            str(Path(self.entry).parent))
        return started
