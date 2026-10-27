#!/usr/bin/env python3
"""Generate machine-local client configuration without editing global settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from app_paths import CODE_DIR, workspace_root


def shell_command(arguments: list[str]) -> str:
    return subprocess.list2cmdline(arguments) if os.name == "nt" else shlex.join(arguments)


def generate(workspace: Path, output: Path, python: str = sys.executable) -> list[Path]:
    workspace = workspace.expanduser().resolve()
    output = output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    server = {"command": python, "args": [str(CODE_DIR / "mcp_server.py")],
              "env": {"COLLAB_WORKSPACE": str(workspace)}}
    configs = {
        "claude.mcp.json": {"mcpServers": {"agent-collab": {"type": "stdio", **server}}},
        "antigravity.mcp.json": {"mcpServers": {"agent-collab": server}},
    }

    def hook(client: str, agent: str, event: str) -> dict:
        command = shell_command([python, str(CODE_DIR / "scripts" / "board_hook.py"),
                                 "--workspace", str(workspace), "--client", client,
                                 "--agent", agent, "--event", event])
        return {"hooks": [{"type": "command", "command": command, "timeout": 15}]}

    configs["claude.settings.json"] = {
        "model": "claude-opus-5-5", "effortLevel": "high",
        "env": {"CLAUDE_CODE_EFFORT_LEVEL": "high"},
        "hooks": {event: [hook("claude", "claude", event)]
                  for event in ("SessionStart", "UserPromptSubmit", "Stop")},
    }
    configs["codex.hooks.json"] = {"hooks": {
        event: [hook("codex", "codex", event)]
        for event in ("SessionStart", "UserPromptSubmit", "Stop")}}
    configs["antigravity.hooks.json"] = {"agent-board-alerts": {
        event: [hook("antigravity", "argon-antigravity", event)]
        for event in ("SessionStart", "PreInvocation", "Stop")}}
    written = []
    for name, data in configs.items():
        target = output / name
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        written.append(target)
    toml = output / "codex.toml"
    toml.write_text(
        "[mcp_servers.agent-collab]\n"
        f"command = {json.dumps(python)}\n"
        f"args = [{json.dumps(str(CODE_DIR / 'mcp_server.py'))}]\n"
        "\n[mcp_servers.agent-collab.env]\n"
        f"COLLAB_WORKSPACE = {json.dumps(str(workspace))}\n", encoding="utf-8")
    written.append(toml)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=workspace_root())
    parser.add_argument("--output", type=Path, help="Default: WORKSPACE/client-configs")
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    written = generate(workspace, args.output or workspace / "client-configs")
    print("Generated configuration for workspace: " + str(workspace))
    for path in written:
        print("  " + str(path))
    print("Review and merge the relevant file into your client settings. No global settings were changed.")
    print("Setup instructions: " + str(CODE_DIR / "docs" / "agents.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
