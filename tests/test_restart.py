import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import time
import unittest

from app.restart import RestartController


HELPER = Path(__file__).resolve().parents[1] / 'app' / 'restart_helper.py'


class RestartTests(unittest.TestCase):
    def test_refused_close_does_not_schedule_restart(self):
        class Window:
            def close(self):
                return False
        controller = RestartController('main.py')
        controller.window = Window()
        controller.requestRestart()
        self.assertFalse(controller.requested)

    def test_launch_reads_changed_source_even_with_valid_old_bytecode(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module = root / 'restart_fixture.py'
            module.write_text("VALUE = 'old'\n", encoding='utf-8')
            stamp = module.stat().st_mtime
            py_compile.compile(str(module), doraise=True)
            module.write_text("VALUE = 'new'\n", encoding='utf-8')
            os.utime(module, (stamp, stamp))
            entry = root / 'entry.py'
            output = root / 'result.json'
            entry.write_text('import json,sys,os\nfrom pathlib import Path\nimport restart_fixture\n'
                'Path(sys.argv[1]).write_text(json.dumps([restart_fixture.VALUE,sys.argv[2],os.getcwd()]))\n', encoding='utf-8')
            subprocess.run([sys.executable, '-B', str(HELPER), '--launch', str(entry), str(output), 'argument with spaces'], check=True, timeout=15)
            self.assertEqual(json.loads(output.read_text()), ['new', 'argument with spaces', str(root)])

    def test_helper_waits_for_old_process_then_starts_new_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'started'
            ready = root / 'ready'
            release = root / 'release'
            entry = root / 'entry.py'
            entry.write_text('from pathlib import Path\nimport sys,os\nPath(sys.argv[1]).write_text(str(os.getpid()))\n', encoding='utf-8')
            parent = root / 'parent.py'
            parent.write_text('import sys,time\nfrom pathlib import Path\n'
                f'sys.path.insert(0, {str(HELPER.parent.parent)!r})\n'
                'from app.restart import RestartController\n'
                'controller=RestartController(sys.argv[2],[sys.argv[3]])\n'
                'assert controller.start_helper()\n'
                'Path(sys.argv[4]).touch()\n'
                'deadline=time.monotonic()+10\n'
                'while not Path(sys.argv[5]).exists() and time.monotonic()<deadline: time.sleep(.02)\n', encoding='utf-8')
            process = subprocess.Popen([sys.executable, str(parent), str(HELPER), str(entry), str(output), str(ready), str(release)])
            try:
                deadline = time.monotonic() + 8
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(ready.exists())
                time.sleep(.2)
                self.assertFalse(output.exists())
                release.touch()
                process.wait(timeout=10)
                deadline = time.monotonic() + 8
                while not output.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(output.exists())
                self.assertNotEqual(int(output.read_text()), process.pid)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    unittest.main()
