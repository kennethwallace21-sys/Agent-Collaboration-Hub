"""Real local-process launcher checks, with all files and ports isolated."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("desktop_launcher", ROOT / "scripts" / "desktop.py")
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)

SERVER = '''import argparse,json,os
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('action');p.add_argument('--host');p.add_argument('--port',type=int);a=p.parse_args()
class H(BaseHTTPRequestHandler):
 def do_GET(self):
  body=json.dumps({'workspace':os.environ['COLLAB_WORKSPACE'],'pid':os.getpid()}).encode()
  self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass
HTTPServer((a.host,a.port),H).serve_forever()
'''


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="collab-desktop-test-")
        self.root = Path(self.temp.name).resolve()
        self.code = self.root / "app with spaces"
        self.code.mkdir()
        (self.code / "collab.py").write_text(SERVER, encoding="utf-8")
        self.workspace = self.root / "workspace with spaces"
        self.port = desktop.free_port(0)
        self.code_patch = patch.object(desktop, "CODE_DIR", self.code)
        self.code_patch.start()
        self.workspaces = []

    def tearDown(self):
        for workspace in self.workspaces:
            try:
                desktop.stop(workspace, self.port)
            except (OSError, RuntimeError):
                pass
        self.code_patch.stop()
        self.temp.cleanup()

    def launch(self, workspace=None):
        workspace = workspace or self.workspace
        self.workspaces.append(workspace)
        return desktop.start(workspace, self.port, open_browser=False, timeout=5)

    def test_start_reuses_matching_server_and_stop_checks_live_identity(self):
        first = self.launch()
        again = self.launch()
        self.assertTrue(first["running"])
        self.assertTrue(first["managed"])
        self.assertEqual(first["pid"], again["pid"])
        self.assertEqual(first["workspace"], str(self.workspace))
        stopped = desktop.stop(self.workspace, self.port)
        self.assertTrue(stopped["stopped"])
        self.assertFalse(desktop.status(self.workspace, self.port)["running"])

    def test_foreign_workspace_on_preferred_port_gets_separate_server(self):
        first = self.launch()
        other = self.launch(self.root / "other workspace")
        self.assertNotEqual(first["port"], other["port"])
        self.assertNotEqual(first["pid"], other["pid"])
        self.assertEqual(desktop.health(first["port"])["workspace"], str(self.workspace))

    def test_stale_or_forged_manifest_never_kills_unrelated_pid(self):
        first = self.launch()
        record = desktop.load_manifest(self.workspace)
        record["pid"] = os.getpid()
        desktop.write_manifest(self.workspace, record)
        with patch.object(desktop.os, "kill") as kill:
            with self.assertRaisesRegex(RuntimeError, "started elsewhere"):
                desktop.stop(self.workspace, self.port)
            kill.assert_not_called()
        record["pid"] = first["pid"]
        desktop.write_manifest(self.workspace, record)

    def test_status_is_read_only_for_missing_workspace(self):
        self.assertFalse(desktop.status(self.workspace, self.port)["running"])
        self.assertFalse(self.workspace.exists())

    def test_browser_opens_matching_local_url_only(self):
        first = self.launch()
        with patch.object(desktop.webbrowser, "open", return_value=True) as browser:
            result = desktop.start(self.workspace, self.port)
        browser.assert_called_once_with(first["url"])
        self.assertTrue(result["browser_opened"])

    def test_simultaneous_clicks_start_one_process(self):
        # Separate Python launchers exercise the OS file lock, not a thread mock.
        script = self.code / "desktop_test_driver.py"
        script.write_text(
            "import importlib.util,json\n"
            f"s=importlib.util.spec_from_file_location('launcher',{str(ROOT / 'scripts' / 'desktop.py')!r})\n"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
            f"m.CODE_DIR=m.Path({str(self.code)!r})\n"
            f"print(json.dumps(m.start(m.Path({str(self.workspace)!r}),{self.port},False,False,5)))\n", encoding="utf-8")
        self.workspaces.append(self.workspace)
        processes = [subprocess.Popen([sys.executable, str(script)], stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = []
        for process in processes:
            output, error = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, error)
            results.append(json.loads(output))
        self.assertEqual(results[0]["pid"], results[1]["pid"])


class InstalledAppIntegrationTests(unittest.TestCase):
    def test_copied_real_app_keeps_data_separate_and_generates_valid_client_paths(self):
        """Install actual source, then launch and use only that installed copy."""
        spec = importlib.util.spec_from_file_location("real_app_installer", ROOT / "install.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory(prefix="collab-real-install-") as directory:
            base = Path(directory).resolve()
            app, workspace = base / "installed app", base / "private workspace"
            installer.install(app, workspace, None, source=ROOT)
            environment = {**os.environ, "COLLAB_WORKSPACE": str(workspace)}
            port = desktop.free_port(0)

            def run(script, *args):
                result = subprocess.run([sys.executable, str(app / script), *args], cwd=app,
                                        env=environment, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                return result.stdout

            launched = False
            try:
                output = run("scripts/desktop.py", "--workspace", str(workspace), "--port", str(port), "--no-browser")
                result = json.loads(output)
                launched = True
                info = desktop.health(result["port"])
                self.assertEqual(info["workspace"], str(workspace))
                self.assertEqual(info["pid"], result["pid"])
                self.assertTrue(result["managed"])
                run("collab.py", "init")
                run("collab.py", "post", "--from", "install-test", "--msg", "Installed board roundtrip")
                self.assertIn("Installed board roundtrip", run("collab.py", "read"))
                self.assertTrue((workspace / "state" / "collab.db").is_file())
                self.assertFalse((app / "state").exists())

                run("setup_clients.py", "--workspace", str(workspace))
                configs = workspace / "client-configs"
                for filename in ("claude.mcp.json", "antigravity.mcp.json"):
                    config = json.loads((configs / filename).read_text())
                    server = config["mcpServers"]["agent-collab"]
                    self.assertEqual(server["env"]["COLLAB_WORKSPACE"], str(workspace))
                    self.assertEqual(Path(server["args"][0]), app / "mcp_server.py")
                    self.assertTrue(Path(server["args"][0]).is_file())
                for filename in ("claude.settings.json", "codex.hooks.json", "antigravity.hooks.json"):
                    config = json.loads((configs / filename).read_text())
                    def commands(value):
                        if isinstance(value, dict):
                            for key, item in value.items():
                                if key == "command":
                                    yield item
                                else:
                                    yield from commands(item)
                        elif isinstance(value, list):
                            for item in value:
                                yield from commands(item)
                    hook_commands = list(commands(config))
                    self.assertTrue(hook_commands)
                    for command in hook_commands:
                        self.assertIn(str(app / "scripts" / "board_hook.py"), command)
                        self.assertIn(str(workspace), command)
                    self.assertTrue((app / "scripts" / "board_hook.py").is_file())
                self.assertTrue((app / "assets" / "dashboard.html").is_file())
                self.assertTrue((app / "examples" / "README.md").is_file())
            finally:
                if launched:
                    stopped = json.loads(run("scripts/desktop.py", "stop", "--workspace", str(workspace), "--port", str(port)))
                    self.assertTrue(stopped["stopped"])


if __name__ == "__main__":
    unittest.main()
