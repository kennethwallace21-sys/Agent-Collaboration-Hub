#!/usr/bin/env python3
"""
Ask another model a one-off question headlessly, and optionally post the answer to the board.

  ./ask claude "Review shared/specs/prd.md for gaps"       # Claude Opus 5.5 at effort high, read-only
  ./ask codex  "Propose a test plan for collab.py"         # Codex with your default model, read-only sandbox
  ./ask claude "..." --from codex --reply-to 31 --post     # also post the answer as a board reply
  ./ask claude "..." --from codex --post --async           # return at once; the answer arrives as an alert

Answers come from fresh headless sessions (`claude -p`, `codex exec`) started in this folder.
They cannot edit files unless --write is given on the command line. Posted answers use the
board IDs claude-headless and codex-headless so nobody mistakes them for the live agents.
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from app_paths import CODE_DIR, workspace_root

BASE_DIR = workspace_root()
sys.path.insert(0, str(CODE_DIR))

import alerts  # noqa: E402

JOBS_DIR = BASE_DIR / "state" / "asks"
ANSWERS_DIR = BASE_DIR / "shared" / "asks"
HOME = Path.home()
MAX_POST_CHARS = 6000

AGENTS = {
    "claude": {"board_id": "claude-headless", "badge": "Claude Opus 5.5 (High) · headless", "timeout": 900},
    "codex": {"board_id": "codex-headless", "badge": "Codex (your default model) · headless", "timeout": 1200},
}
READ_ONLY_CLAUDE_TOOLS = "Read,Grep,Glob,WebFetch,WebSearch"
# Variables that tie a process to the Claude Code session that launched it.
SESSION_ENV_PREFIXES = ("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID", "CLAUDE_AGENT_SDK", "CLAUDE_EFFORT")


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def claude_version(path: str) -> tuple[int, ...]:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=20,
                             env={**os.environ, "PATH": f"{Path(path).parent}:{os.environ.get('PATH', '')}"}).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ()
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(n) for n in match.groups()) if match else ()


def find_claude() -> str | None:
    """COLLAB_CLAUDE_BIN if set, else the newest installed Claude Code (old builds reject new models)."""
    if os.environ.get("COLLAB_CLAUDE_BIN"):
        return os.environ["COLLAB_CLAUDE_BIN"]
    candidates = [shutil.which("claude")]
    for pattern in (".nvm/versions/node/*/bin/claude",
                    ".antigravity-ide/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                    ".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                    ".cursor/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                    ".local/bin/claude", ".claude/local/claude"):
        candidates += glob.glob(str(HOME / pattern))
    candidates += ["/opt/homebrew/bin/claude", "/usr/local/bin/claude"]
    found = {os.path.realpath(p): p for p in candidates if p and os.path.isfile(p) and os.access(p, os.X_OK)}
    versions = {p: claude_version(p) for p in found.values()}
    best = max(versions, key=lambda p: versions[p], default=None)
    return best if best and versions[best] else None


def claude_model() -> str:
    """The exact Opus 5.5 ID rather than the moving `opus` alias (also resolves on Bedrock)."""
    return os.environ.get("COLLAB_CLAUDE_MODEL") or "claude-opus-5-5"


def framing(requester: str) -> str:
    who = f"@{requester}" if requester else "a teammate"
    return (f"You are answering a one-off consult from {who} on the multi-agent Agent Collaboration "
            f"board in {BASE_DIR} (protocol: AGENTS.md; history: ./collab read). Answer directly and "
            "concisely in Markdown. Do not post to the board; your final answer is relayed for you.")


def run_claude(prompt: str, requester: str, write: bool, timeout: int) -> tuple[bool, str]:
    exe = find_claude()
    if not exe:
        return False, "claude CLI not found (set COLLAB_CLAUDE_BIN)"
    cmd = [exe, "-p", "--model", claude_model(), "--effort", "high", "--output-format", "text",
           "--append-system-prompt", framing(requester)]
    if write:
        cmd += ["--permission-mode", "acceptEdits"]
    else:
        cmd += ["--tools", READ_ONLY_CLAUDE_TOOLS, "--permission-mode", "default"]
    env = {k: v for k, v in os.environ.items() if not k.startswith(SESSION_ENV_PREFIXES)}
    env["COLLAB_HEADLESS"] = "1"
    env["CLAUDE_CODE_EFFORT_LEVEL"] = "high"  # the user's settings pin max; consults run at high
    env["PATH"] = f"{Path(exe).parent}:{env.get('PATH', '/usr/bin:/bin')}"  # npm installs need node alongside
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                           cwd=str(BASE_DIR), env=env)
    except subprocess.TimeoutExpired:
        return False, f"claude timed out after {timeout}s"
    except OSError as exc:
        return False, f"claude failed to start: {exc}"
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip()[-1500:] or f"claude exited {r.returncode}"
    return True, r.stdout.strip()


def run_codex(prompt: str, requester: str, write: bool, timeout: int, model: str = "",
              effort: str = "") -> tuple[bool, str]:
    exe = alerts.find_executable("COLLAB_CODEX_BIN", "codex", alerts.CODEX_CANDIDATES)
    if not exe:
        return False, "codex CLI not found (set COLLAB_CODEX_BIN)"
    with tempfile.TemporaryDirectory(prefix="collab-ask-") as tmp:
        out = Path(tmp) / "answer.md"
        cmd = [exe, "exec", "-C", str(BASE_DIR), "-s", "workspace-write" if write else "read-only",
               "--skip-git-repo-check", "--ephemeral", "--color", "never", "-o", str(out)]
        if model:
            cmd += ["-m", model]
        if effort:
            cmd += ["-c", f'model_reasoning_effort="{effort}"']
        cmd.append("-")
        try:
            r = subprocess.run(cmd, input=f"{framing(requester)}\n\n{prompt}", capture_output=True, text=True,
                               timeout=timeout, cwd=str(BASE_DIR), env={**os.environ, "COLLAB_HEADLESS": "1"})
        except subprocess.TimeoutExpired:
            return False, f"codex timed out after {timeout}s"
        except OSError as exc:
            return False, f"codex failed to start: {exc}"
        answer = out.read_text(encoding="utf-8").strip() if out.exists() else ""
    if r.returncode != 0 and not answer:
        return False, (r.stderr or r.stdout).strip()[-1500:] or f"codex exited {r.returncode}"
    return True, answer or r.stdout.strip()


def post_answer(agent: str, requester: str, prompt: str, ok: bool, answer: str, reply_to: int | None,
                channel: str) -> int | None:
    import collab  # the board backend

    spec = AGENTS[agent]
    mention = f"@{requester} " if requester else ""
    if not ok:
        content = f"{mention}⚠️ Headless {agent} consult failed: {answer[:800]}"
    else:
        content = f"{mention}**Answer from headless {agent}** to: _{alerts.flatten(prompt, 160)}_\n\n"
        if len(answer) > MAX_POST_CHARS:
            ANSWERS_DIR.mkdir(parents=True, exist_ok=True)
            path = ANSWERS_DIR / f"{datetime.datetime.now():%Y%m%d-%H%M%S}-{agent}.md"
            path.write_text(f"# Question\n\n{prompt}\n\n# Answer ({spec['badge']})\n\n{answer}\n", encoding="utf-8")
            content += f"{answer[:1500]}…\n\n(Full answer: `{path.relative_to(BASE_DIR)}`)"
        else:
            content += answer
    res = collab.op_post(sender=spec["board_id"], content=content, channel=channel, reply_to=reply_to,
                         model=spec["badge"])
    return res.get("message_id")


def write_job(job: dict) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / f"{job['job']}.json").write_text(json.dumps(job, indent=2), encoding="utf-8")


def start_job(agent: str, prompt: str, requester: str = "", reply_to: int | None = None,
              channel: str = "general") -> dict:
    """Run a read-only consult in the background; its answer is posted to the board when done."""
    if agent not in AGENTS:
        raise ValueError(f"agent must be one of {', '.join(AGENTS)}")
    job = {"job": f"{time.strftime('%Y%m%d-%H%M%S')}-{agent}-{uuid.uuid4().hex[:6]}", "agent": agent,
           "requester": requester, "status": "running", "started_at": now_iso(), "reply_to": reply_to}
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(Path(__file__).resolve()), agent, prompt, "--post", "--job", job["job"],
           "--channel", channel]
    if requester:
        cmd += ["--from", requester]
    if reply_to:
        cmd += ["--reply-to", str(reply_to)]
    with open(JOBS_DIR / f"{job['job']}.log", "w", encoding="utf-8") as logf:
        proc = subprocess.Popen(cmd, cwd=str(BASE_DIR), stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                                start_new_session=True)
    job["pid"] = proc.pid
    write_job(job)
    return job


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Headless consults with Claude or Codex")
    parser.add_argument("agent", nargs="?", choices=sorted(AGENTS))
    parser.add_argument("prompt", nargs="?", help="Question; use - to read it from stdin")
    parser.add_argument("--from", dest="requester", default="", help="Your board ID (the answer @mentions you)")
    parser.add_argument("--post", action="store_true", help="Post the answer to the board")
    parser.add_argument("--reply-to", type=int, default=None)
    parser.add_argument("--channel", default="general")
    parser.add_argument("--async", dest="run_async", action="store_true", help="Run in the background (implies --post)")
    parser.add_argument("--write", action="store_true", help="Allow the consulted model to edit files")
    parser.add_argument("--timeout", type=int, default=0)
    parser.add_argument("--model", default="", help="Codex only: model override")
    parser.add_argument("--effort", default="", help="Codex only: reasoning effort override")
    parser.add_argument("--jobs", action="store_true", help="List recent background consults")
    parser.add_argument("--job", default="", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.jobs:
        for path in sorted(JOBS_DIR.glob("*.json"))[-20:]:
            job = json.loads(path.read_text(encoding="utf-8"))
            print(f"{job['job']}  {job['status']:<8} reply msg #{job.get('message_id') or '-'}")
        return 0
    if not args.agent or args.prompt is None:
        parser.error("agent and prompt are required")
    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt
    if not prompt.strip():
        parser.error("prompt is empty")
    if args.run_async:
        if args.write:
            parser.error("--write is not allowed with --async")
        print(json.dumps(start_job(args.agent, prompt, args.requester, args.reply_to, args.channel), indent=2))
        return 0

    timeout = args.timeout or AGENTS[args.agent]["timeout"]
    if args.agent == "claude":
        ok, answer = run_claude(prompt, args.requester, args.write, timeout)
    else:
        ok, answer = run_codex(prompt, args.requester, args.write, timeout, args.model, args.effort)
    message_id = post_answer(args.agent, args.requester, prompt, ok, answer, args.reply_to, args.channel) if args.post else None
    if args.job:
        write_job({"job": args.job, "agent": args.agent, "requester": args.requester,
                   "status": "done" if ok else "failed", "finished_at": now_iso(), "message_id": message_id,
                   "reply_to": args.reply_to})
    print(answer)
    if message_id:
        print(f"\n[posted to the board as message #{message_id}]")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
