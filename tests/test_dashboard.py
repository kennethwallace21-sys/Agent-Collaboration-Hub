"""Optional Node behavior tests for the shipped dashboard, without a live board."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required for dashboard behavior tests")
    def test_shipped_dashboard_behavior(self):
        result = subprocess.run(
            [shutil.which("node"), "--test", str(ROOT / "tests" / "dashboard_behavior.test.js")],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
