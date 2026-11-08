"""Generate a local portfolio index from the repositories reachable on this machine.

An operator tool, not part of the shipped board. It is not in the installer's file list.

Why generated rather than hand-written: the predecessor project recorded a lesson (L001)
that a status written by hand in a table drifts from reality. This reads the facts from the
hosting APIs and the filesystem, and takes human judgements, such as which product is
primary, from a local config file.

No private namespace, owner, or folder is written into this file. Sources come from the
command line or a local config, so the tool itself is portable and safe to publish.

Usage:
    python3 scripts/portfolio_index.py --gitlab-namespace <group> \
        --github-owner <owner> --local-folder <path> \
        --config <local config.json> --output <local output.md> --json <local output.json>

Every source is optional. A source that cannot be reached is reported as unreachable
rather than treated as empty, because "no repositories" and "could not ask" differ.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DORMANT_AFTER_DAYS = 60


def run_json(command: list[str], timeout: int = 60):
    """Run a CLI and parse its JSON output. Returns (ok, payload_or_error)."""
    if shutil.which(command[0]) is None:
        return False, f"{command[0]} is not installed"
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"{command[0]} failed: {error}"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        return False, f"{command[0]} exited {result.returncode}: {detail[0] if detail else 'no output'}"
    try:
        return True, json.loads(result.stdout)
    except ValueError as error:
        return False, f"{command[0]} did not return JSON: {error}"


def days_since(stamp: str | None):
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).days


def _gitlab_rows(payload: list[dict]) -> list[dict]:
    return [{
        "host": "gitlab",
        "name": item.get("path_with_namespace", ""),
        "visibility": item.get("visibility", "unknown"),
        "last_activity": item.get("last_activity_at", "") or "",
        "days_dormant": days_since(item.get("last_activity_at")),
        "description": (item.get("description") or "").strip(),
    } for item in payload]


def collect_gitlab(namespace: str) -> tuple[list[dict], str | None]:
    """A GitLab namespace is either a group or a user, and the APIs differ.

    Asking only the group API silently omits every repository under a personal
    namespace, which is the failure this fallback exists to prevent.
    """
    group_query = f"groups/{namespace}/projects?per_page=100&simple=true&include_subgroups=true"
    ok, payload = run_json(["glab", "api", group_query])
    if ok:
        return _gitlab_rows(payload), None
    group_problem = payload

    ok, payload = run_json(["glab", "api", f"users/{namespace}/projects?per_page=100&simple=true"])
    if ok:
        return _gitlab_rows(payload), None
    return [], f"not a group ({group_problem}) and not a user ({payload})"


def collect_github(owner: str) -> tuple[list[dict], str | None]:
    ok, payload = run_json(["gh", "api", f"users/{owner}/repos?per_page=100&sort=updated"])
    if not ok:
        return [], payload
    return [{
        "host": "github",
        "name": item.get("full_name", ""),
        "visibility": "private" if item.get("private") else "public",
        "last_activity": item.get("pushed_at", "") or "",
        "days_dormant": days_since(item.get("pushed_at")),
        "description": (item.get("description") or "").strip(),
    } for item in payload], None


def collect_folders(folders: list[str]) -> tuple[list[dict], list[str]]:
    """Index local working folders by their most recent file modification."""
    skip = {"__pycache__", ".git", "node_modules", ".venv", ".ruff_cache"}
    rows, problems = [], []
    for folder in folders:
        path = Path(folder).expanduser()
        if not path.is_dir():
            problems.append(f"local folder {folder}: not a directory")
            continue
        newest, count = None, 0
        for entry in path.rglob("*"):
            if any(part in skip for part in entry.parts) or not entry.is_file():
                continue
            count += 1
            try:
                stamp = entry.stat().st_mtime
            except OSError:
                continue
            newest = stamp if newest is None else max(newest, stamp)
        when = datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else ""
        rows.append({
            "host": "local",
            "name": path.name,
            "visibility": "local",
            "last_activity": when,
            "days_dormant": days_since(when),
            "description": f"{count} files",
        })
    return rows, problems


def render(rows: list[dict], problems: list[str], status: dict, generated: str) -> str:
    lines = [
        "# Portfolio index",
        "",
        f"Generated {generated} by `scripts/portfolio_index.py`. Do not edit by hand; rerun it.",
        "",
        "Local only. This names private repositories, so it is gitignored.",
        "",
    ]
    if problems:
        lines += [
            "## Unreachable sources", "",
            "A source that could not be reached is not the same as a source with nothing in it.", "",
        ]
        lines += [f"- {item}" for item in problems] + [""]

    dormant = [r for r in rows if r["days_dormant"] is None
               or r["days_dormant"] > DORMANT_AFTER_DAYS]
    lines += [
        "## Summary", "",
        "| Measure | Count |", "| --- | --- |",
        f"| Sources indexed | {len(rows)} |",
        f"| Named primary | {sum(1 for r in rows if status.get(r['name']) == 'primary')} |",
        f"| Named parked | {sum(1 for r in rows if status.get(r['name']) == 'parked')} |",
        f"| Dormant beyond {DORMANT_AFTER_DAYS} days | {len(dormant)} |",
        f"| Sources unreachable | {len(problems)} |",
        f"| Sources with no stated status | {sum(1 for r in rows if r['name'] not in status)} |",
        "",
        "## Index", "",
        "| Source | Host | Visibility | Last activity | Days dormant | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    ordered = sorted(rows, key=lambda r: (r["days_dormant"] is None, -(r["days_dormant"] or 0)))
    for row in ordered:
        when = (row["last_activity"] or "unknown")[:10]
        age = "unknown" if row["days_dormant"] is None else str(row["days_dormant"])
        note = (row["description"] or "").replace("|", "/")[:70]
        lines.append(
            f"| `{row['name']}` | {row['host']} | {row['visibility']} | {when} | {age} | "
            f"{status.get(row['name'], 'unstated')} | {note} |")

    unnamed = sorted(r["name"] for r in rows if r["name"] not in status)
    if unnamed:
        lines += [
            "", "## Sources with no stated status", "",
            "Every source should be named primary or parked, which is measure 2 of the "
            "portfolio assessment.", "",
        ]
        lines += [f"- `{name}`" for name in unnamed]
    lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Generate a local portfolio index.")
    parser.add_argument("--gitlab-namespace", action="append", default=[],
                        help="GitLab group to index. Repeatable.")
    parser.add_argument("--github-owner", action="append", default=[],
                        help="GitHub user or org to index. Repeatable.")
    parser.add_argument("--local-folder", action="append", default=[],
                        help="Local folder to index. Repeatable.")
    parser.add_argument("--config", type=Path,
                        help="Local JSON with sources and status_overrides. Command-line "
                             "values are added to it.")
    parser.add_argument("--output", type=Path, help="Markdown output path.")
    parser.add_argument("--json", type=Path, dest="json_out", help="JSON output path.")
    args = parser.parse_args(argv)

    config = {}
    if args.config:
        if not args.config.is_file():
            print(json.dumps({"ok": False, "error": f"Config not found: {args.config}"}))
            return 1
        config = json.loads(args.config.read_text(encoding="utf-8"))

    namespaces = list(config.get("gitlab_namespaces", [])) + args.gitlab_namespace
    owners = list(config.get("github_owners", [])) + args.github_owner
    folders = list(config.get("local_folders", [])) + args.local_folder
    status = dict(config.get("status_overrides", {}))

    if not (namespaces or owners or folders):
        print(json.dumps({"ok": False, "error": "No sources. Pass a namespace, owner, or folder."}))
        return 1

    rows, problems = [], []
    for namespace in namespaces:
        found, problem = collect_gitlab(namespace)
        rows += found
        if problem:
            problems.append(f"gitlab group {namespace}: {problem}")
    for owner in owners:
        found, problem = collect_github(owner)
        rows += found
        if problem:
            problems.append(f"github owner {owner}: {problem}")
    found, folder_problems = collect_folders(folders)
    rows += found
    problems += folder_problems

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(
            {"generated": generated, "count": len(rows), "unreachable": problems,
             "sources": rows}, indent=2) + "\n", encoding="utf-8")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render(rows, problems, status, generated), encoding="utf-8")

    print(json.dumps({"ok": True, "count": len(rows), "unreachable": len(problems),
                      "output": str(args.output) if args.output else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
