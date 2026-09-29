import os
from pathlib import Path
import subprocess
import sys
import unittest


class EditorIdentityTests(unittest.TestCase):
    def test_real_qml_editors(self):
        result=subprocess.run([sys.executable,'-m','tests.smoke_editor_identity'],
            cwd=Path(__file__).resolve().parents[1],env={**os.environ,'PYTHONIOENCODING':'utf-8'},
            capture_output=True,text=True,encoding='utf-8',timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
