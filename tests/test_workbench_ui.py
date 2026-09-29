import os
from pathlib import Path
import subprocess
import sys
import unittest


class WorkbenchUiTests(unittest.TestCase):
    def test_revised_workbench(self):
        result=subprocess.run([sys.executable,'-B','-m','tests.smoke_workbench_revision'],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ,'QT_QPA_PLATFORM':'offscreen','PYTHONIOENCODING':'utf-8'},
            capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
