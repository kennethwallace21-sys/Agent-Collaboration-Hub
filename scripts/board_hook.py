#!/usr/bin/env python3
"""Client hook entrypoint with safely quoted workspace arguments."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--client", choices=("claude", "codex", "antigravity"), required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "COLLAB_WORKSPACE": str(Path(args.workspace).expanduser().resolve())}
    result = subprocess.run([sys.executable, str(root / "alerts.py"), "hook", args.client,
                             "--agent", args.agent, "--event", args.event], env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
