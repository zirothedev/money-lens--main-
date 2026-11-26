"""Runs the Node unit tests for the pure JavaScript modules as part of `manage.py test`."""
import shutil
import subprocess
import unittest
from pathlib import Path

JS_DIR = Path(__file__).parent / 'js'


@unittest.skipUnless(shutil.which('node'), 'Node.js is not installed')
class JavaScriptUnitTests(unittest.TestCase):
    def test_node_test_suite_passes(self):
        files = sorted(str(p) for p in JS_DIR.glob('*.test.js'))
        result = subprocess.run(['node', '--test', *files], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout[-3000:] + result.stderr[-2000:])
