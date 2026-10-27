"""Create a per-user desktop shortcut. Never changes agent/client settings."""
from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

APP_NAME = "AI Agent Collab Space"


def launch_args(code_dir: Path, workspace: Path, python: str, alerts: bool = False) -> list[str]:
    return [python, str(code_dir / "scripts" / "desktop.py"), "--workspace", str(workspace)] + (
        ["--alerts"] if alerts else [])


def shell_launcher(args: list[str]) -> str:
    return "#!/bin/sh\nexec " + shlex.join(args) + "\n"


def mac_launcher(args: list[str], workspace: Path) -> str:
    """Capture Finder-launched errors, including a missing Python runtime."""
    return ("#!/bin/sh\n"
            "log_dir=" + shlex.quote(str(workspace / "state")) + "\n"
            '/bin/mkdir -p "$log_dir" || exit 1\n'
            'exec >> "$log_dir/desktop-launch.log" 2>&1\n'
            "printf '\\nAI Agent Collab Space launch: '\n"
            "/bin/date -u '+%Y-%m-%dT%H:%M:%SZ'\n"
            "exec " + shlex.join(args) + "\n")


def cmd_launcher(args: list[str]) -> str:
    command = subprocess.list2cmdline(args).replace("%", "%%")
    return "@echo off\r\nsetlocal DisableDelayedExpansion\r\n" + command + "\r\nif errorlevel 1 pause\r\n"


def desktop_exec(args: list[str]) -> str:
    return " ".join('"' + str(a).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`")
                    .replace("$", "\\$").replace("%", "%%") + '"' for a in args)


def _safe_text(paths):
    if any("\n" in str(p) or "\r" in str(p) for p in paths):
        raise ValueError("Installation paths cannot contain line breaks")


def _write(path: Path, content: str, executable=False):
    path.write_text(content, encoding="utf-8", newline="")
    if executable:
        path.chmod(0o755)


def create_shortcut(code_dir: Path, workspace: Path, desktop_dir: Path, python: str,
                    platform: str | None = None, alerts: bool = False) -> dict:
    platform = platform or sys.platform
    _safe_text([code_dir, workspace, desktop_dir, python])
    desktop_dir.mkdir(parents=True, exist_ok=True)
    args = launch_args(code_dir, workspace, python, alerts)
    assets = code_dir / "assets"
    if platform == "darwin":
        bundle = desktop_dir / f"{APP_NAME}.app"
        contents = bundle / "Contents"
        executable = contents / "MacOS" / "launch"
        resources = contents / "Resources"
        executable.parent.mkdir(parents=True, exist_ok=True)
        resources.mkdir(parents=True, exist_ok=True)
        _write(executable, mac_launcher(args, workspace), True)
        icon = assets / "app-icon.icns"
        if icon.exists():
            shutil.copy2(icon, resources / "app-icon.icns")
        with (contents / "Info.plist").open("wb") as handle:
            plistlib.dump({"CFBundleName": APP_NAME, "CFBundleDisplayName": APP_NAME,
                          "CFBundleIdentifier": "org.aiagentcollab.desktop", "CFBundleVersion": "0.1.0",
                          "CFBundleShortVersionString": "0.1.0", "CFBundlePackageType": "APPL",
                          "CFBundleExecutable": "launch", "CFBundleIconFile": "app-icon.icns",
                          "NSDesktopFolderUsageDescription": "Read and save the collaboration workspace you chose in your Desktop folder.",
                          "NSDocumentsFolderUsageDescription": "Read and save the collaboration workspace you chose in your Documents folder.",
                          "NSDownloadsFolderUsageDescription": "Read and save the collaboration workspace you chose in your Downloads folder.",
                          "NSHighResolutionCapable": True}, handle)
        return {"path": str(bundle), "kind": "macOS app", "note": "Requires the installed Python runtime."}
    if platform == "win32":
        pythonw = Path(python).with_name("pythonw.exe")
        if pythonw.exists():
            args[0] = str(pythonw)
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        shortcut = desktop_dir / f"{APP_NAME}.lnk"
        if powershell:
            def ps(value):
                return "'" + str(value).replace("'", "''") + "'"
            script = ("$ErrorActionPreference='Stop';$w=New-Object -ComObject WScript.Shell;"
                      f"$s=$w.CreateShortcut({ps(shortcut)});$s.TargetPath={ps(args[0])};"
                      f"$s.Arguments={ps(subprocess.list2cmdline(args[1:]))};"
                      f"$s.WorkingDirectory={ps(code_dir)};$s.IconLocation={ps(assets / 'app-icon.ico')};$s.Save()")
            try:
                completed = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                                           capture_output=True, text=True, timeout=20)
                if completed.returncode == 0 and shortcut.exists():
                    return {"path": str(shortcut), "kind": "Windows shortcut"}
            except (OSError, subprocess.SubprocessError):
                pass
        shortcut = desktop_dir / f"{APP_NAME}.cmd"
        # A console remains available for errors when COM shortcuts are unavailable.
        args[0] = python
        _write(shortcut, cmd_launcher(args))
        return {"path": str(shortcut), "kind": "Windows command shortcut",
                "note": "Custom icon needs Windows PowerShell/COM; this fallback uses the command-file icon."}
    shortcut = desktop_dir / f"{APP_NAME}.desktop"
    _write(shortcut, "[Desktop Entry]\nType=Application\nName=" + APP_NAME +
           "\nComment=Open the local multi-agent collaboration board\nExec=" + desktop_exec(args) +
           "\nIcon=" + str(assets / "app-icon-256.png") + "\nTerminal=false\nStartupNotify=true\n", True)
    return {"path": str(shortcut), "kind": "Linux desktop shortcut",
            "note": "Your desktop may ask you to choose Allow Launching or Trust before the first use."}
