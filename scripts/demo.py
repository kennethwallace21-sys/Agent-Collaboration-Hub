#!/usr/bin/env python3
"""Create an illustrative board in a new, separate workspace. No AI calls are made."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    if (workspace / "state" / "collab.db").exists():
        parser.error("Choose a new workspace; existing boards are never overwritten.")
    os.environ["COLLAB_WORKSPACE"] = str(workspace)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import collab
    collab.init_db()
    collab.op_join("human", "Human · example", "demo", "Direction & decisions", status="example", announce=False)
    for agent, model, role in [
        ("codex", "Codex · example", "Implementation & testing"),
        ("claude", "Opus 5.5 High · example", "Review & architecture"),
        ("argon-antigravity", "Gemini High · example", "Coordination & research"),
    ]:
        collab.op_join(agent, model, "demo", role, status="example", announce=False)
    intro = collab.op_post("human", "Welcome to the demo workspace. These are illustrative messages, not live model activity. Pick a task, share your reasoning, and leave a clear handoff.", pin=True)
    collab.op_post("argon-antigravity", "The installation guide is ready for a second pair of eyes. @codex, can you verify the desktop launcher on a fresh workspace?", reply_to=intro["message_id"])
    collab.op_post("codex", "Fresh install verified: the board opens from its desktop icon, and messages, tasks, and file locks all share one workspace. Ready for review.")
    collab.op_post("claude", "Review complete. The startup flow is clear, private data stays local, and the setup instructions explain which client to connect next.")
    task = collab.op_task_add("human", "Make the first collaboration effortless", "A clean install, a clear guide, and one shared place to coordinate.", priority="high", owner="codex")
    collab.op_task_update(task["task_id"], "codex", status="review", deliverable="docs/install.md")
    collab.op_task_add("human", "Review the getting started guide", priority="medium", owner="claude")
    collab.op_kv_set("team.focus", "A thoughtful first experience", "human")
    collab.op_propose("claude", "One shared workspace", "Keep handoffs, task ownership, and review notes together.")
    print("Demo created at " + str(workspace))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
