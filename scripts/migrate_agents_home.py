#!/usr/bin/env python3
"""Parse an Agents Home Folder workspace and import its history inertly into ACH."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import collab  # noqa: E402


STATUS_MAP = {
    "OPEN": "open",
    "ASSIGNED": "assigned",
    "STARTED": "in_progress",
    "IN_PROGRESS": "in_progress",
    "DELIVERED": "delivered",
    "REVIEW": "review",
    "ACCEPTED": "done",
    "DONE": "done",
    "BLOCKED": "blocked",
    "RETURNED": "returned",
    "CANCELLED": "canceled",
    "CANCELED": "canceled",
}

CHANNEL_MAP = {
    "review": "reviews",
    "decision": "architecture",
    "retro": "general",
    "task": "tasks",
    "blocker": "tasks",
    "question": "general",
    "note": "general",
}


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse simple YAML frontmatter delimited by --- lines."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text.strip()
    meta: dict[str, str] = {}
    end_idx = -1
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break
        if ":" in lines[idx]:
            k, v = lines[idx].split(":", 1)
            meta[k.strip()] = v.strip()
    if end_idx == -1:
        return {}, text.strip()
    body = "\n".join(lines[end_idx + 1 :]).strip()
    return meta, body


# Site-specific project metadata is kept out of the repository. A public checkout carries a
# neutral example; the real bundle lives beside this file as migrate_projects.local.json,
# which is gitignored and takes precedence when it exists. This keeps one person's project
# portfolio and local working paths out of a published tree.
LOCAL_PROJECTS_FILE = Path(__file__).resolve().parent / "migrate_projects.local.json"


def default_projects_bundle() -> list[dict]:
    """A neutral example, so the tool works without carrying anybody's portfolio."""
    return [
        {
            "id": "example-product",
            "name": "Example Product",
            "description": "Placeholder project. Provide a real bundle to migrate yours.",
            "repo_path": r"C:\path\to\example-product",
            "status": "active",
            "hold_reason": "",
            "policy": {"forbid_em_dash": True, "require_independent_review": True},
            "shared_channels": ["general", "reviews", "tasks", "architecture"],
        },
        {
            "id": "example-parked",
            "name": "Example Parked Project",
            "description": "Placeholder, to show a non-active status in the bundle.",
            "repo_path": r"C:\path\to\example-parked",
            "status": "parked",
            "hold_reason": "",
            "policy": {"forbid_em_dash": True},
            "shared_channels": ["general", "reviews", "tasks"],
        },
    ]


def build_projects_bundle() -> list[dict]:
    """Prefer the local bundle, and fall back to the neutral example."""
    if LOCAL_PROJECTS_FILE.is_file():
        try:
            data = json.loads(LOCAL_PROJECTS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if isinstance(data, list) and data:
            return data
    return default_projects_bundle()


def build_agents_bundle(source_dir: Path) -> list[dict]:
    roster_file = source_dir / "roster.json"
    raw_agents = []
    if roster_file.is_file():
        data = json.loads(roster_file.read_text(encoding="utf-8", errors="replace"))
        raw_agents = data.get("agents", [])

    defaults = {
        "fable": ("claude-opus-4-6", "claude-code", "Anthropic", "Claude Code", ["orchestration", "synthesis"]),
        "opus-bedrock": ("us.anthropic.claude-opus-5-5", "bedrock-cli", "AWS Bedrock", "Claude Code", ["implementation", "adversarial-review"]),
        "codex": ("gpt-5.4", "codex", "OpenAI", "Codex CLI", ["implementation", "testing", "windows-scripting"]),
        "gemini": ("gemini-3.8-flash", "antigravity", "Google DeepMind", "Antigravity IDE", ["ux-design", "independent-review"]),
        "kimi": ("kimi-k3", "clinebot", "Moonshot AI / Fireworks", "Cline VS Code", ["research", "product-design", "diff-triage"]),
    }

    agents_out = []
    seen = set()
    for entry in raw_agents:
        aid = entry.get("id", "").strip()
        if not aid:
            continue
        seen.add(aid)
        model, surface, provider, runtime, caps = defaults.get(
            aid, ("unknown", "cli", "unknown", "cli", ["collaboration"])
        )
        agents_out.append(
            {
                "id": aid,
                "model": model,
                "surface": surface,
                "role": entry.get("role", "Collaborator"),
                "status": "online",
                "provider": provider,
                "runtime": runtime,
                "model_provenance": "agent_declared",
                "capabilities": caps,
                "responsibilities": entry.get("runs", ""),
                "contact_method": "pull",
                "availability": "online",
            }
        )
    for aid, (model, surface, provider, runtime, caps) in defaults.items():
        if aid not in seen:
            agents_out.append(
                {
                    "id": aid,
                    "model": model,
                    "surface": surface,
                    "role": "Collaborator",
                    "status": "online",
                    "provider": provider,
                    "runtime": runtime,
                    "model_provenance": "agent_declared",
                    "capabilities": caps,
                    "responsibilities": "",
                    "contact_method": "pull",
                    "availability": "online",
                }
            )
    return agents_out


def parse_tasks(source_dir: Path) -> tuple[list[dict], dict[str, str]]:
    tasks_dir = source_dir / "tasks"
    tasks_out: list[dict] = []
    task_project_map: dict[str, str] = {}

    if tasks_dir.is_dir():
        for tf in sorted(tasks_dir.glob("T*.md")):
            raw = tf.read_text(encoding="utf-8", errors="replace")
            meta, body = parse_frontmatter(raw)
            tid = meta.get("id") or tf.stem
            proj = meta.get("project", "agents-home").strip() or "agents-home"
            task_project_map[tid.upper()] = proj
            raw_status = meta.get("status", "DONE").upper().strip()
            mapped_status = STATUS_MAP.get(raw_status, "done")
            tasks_out.append(
                {
                    "external_id": tid,
                    "project_id": proj,
                    "title": f"[{tid}] {meta.get('title', tid)}",
                    "description": meta.get("acceptance", body[:500]),
                    "status": mapped_status,
                    "priority": "high" if raw_status == "BLOCKED" else "medium",
                    "owner": meta.get("lane", ""),
                    "created_by": "fable",
                    "deliverable": meta.get("link", ""),
                    "created_at": meta.get("created", ""),
                    "updated_at": meta.get("updated", ""),
                }
            )
    return tasks_out, task_project_map


def infer_message_project(meta: dict[str, str], body: str, task_project_map: dict[str, str],
                          candidates: list[str] | None = None,
                          default_project: str = "default") -> str:
    """Match a message to a project by its task reference, then by the bundle's own ids.

    The candidate list comes from the bundle rather than a hardcoded keyword table, so the
    tool carries no particular project's vocabulary into a published tree.
    """
    re_val = meta.get("re", "").upper()
    for match in re.findall(r"\bT\d{3,4}\b", re_val + " " + meta.get("subject", "").upper()):
        if match in task_project_map:
            return task_project_map[match]
    combined = (meta.get("subject", "") + " " + body[:300]).lower()
    for candidate in candidates or []:
        if candidate and candidate.lower() in combined:
            return candidate
    return default_project


def parse_board_messages(source_dir: Path, task_project_map: dict[str, str],
                         project_ids: list[str] | None = None) -> list[dict]:
    board_dir = source_dir / "board"
    inbox_dir = source_dir / "inbox"
    msgs_out: list[dict] = []
    seen_ids: set[str] = set()

    candidate_files: list[Path] = []
    if board_dir.is_dir():
        candidate_files.extend(sorted(board_dir.glob("*.md")))
    if inbox_dir.is_dir():
        candidate_files.extend(sorted(inbox_dir.rglob("*.md")))

    for mf in candidate_files:
        raw = mf.read_text(encoding="utf-8", errors="replace")
        meta, body = parse_frontmatter(raw)
        ext_id = meta.get("id") or mf.stem
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        sender = meta.get("from", "unknown").strip() or "unknown"
        msg_type = meta.get("type", "note").lower().strip()
        channel = CHANNEL_MAP.get(msg_type, "general")
        subject = meta.get("subject", "").strip()
        re_field = meta.get("re", "").strip()
        header_prefix = f"**{subject}**" + (f" ({re_field})" if re_field else "")
        content = f"{header_prefix}\n{body}".strip() if subject else body
        if not content:
            content = f"(Imported note {ext_id})"
        proj = infer_message_project(
            meta, body, task_project_map,
            candidates=project_ids,
            default_project=(project_ids or ["default"])[0],
        )
        msgs_out.append(
            {
                "external_id": ext_id,
                "project_id": proj,
                "channel": channel,
                "sender": sender,
                "model": "imported-history",
                "model_provenance": "unknown",
                "content": content,
                "pinned": False,
                "created_at": meta.get("posted", ""),
            }
        )
    return msgs_out


def parse_audits(source_dir: Path) -> list[dict]:
    audits_dir = source_dir / "audits"
    decisions_out: list[dict] = []
    if not audits_dir.is_dir():
        return decisions_out
    for af in sorted(audits_dir.glob("*.md")):
        raw = af.read_text(encoding="utf-8", errors="replace")
        first_line = raw.splitlines()[0].lstrip("# ").strip() if raw.splitlines() else af.stem
        decisions_out.append(
            {
                "project_id": "agents-home",
                "topic": f"Audit Record: {first_line}",
                "proposal": raw[:600].strip(),
                "proposed_by": "fable",
                "status": "approved",
                "peer_status": "approved",
                "owner_status": "approved",
                "artifact_ref": f"audits/{af.name}",
                "created_at": f"{af.stem[:10]}T00:00:00Z" if len(af.stem) >= 10 else "",
            }
        )
    return decisions_out


def parse_lessons(source_dir: Path) -> list[dict]:
    lessons_file = source_dir / "LESSONS.md"
    lessons_out: list[dict] = []
    if not lessons_file.is_file():
        return lessons_out

    for line in lessons_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line_str = line.strip()
        if not line_str.startswith("| L"):
            continue
        parts = [p.strip() for p in line_str.strip("|").split("|")]
        if len(parts) < 5:
            continue
        lid, date_str, source_ref, rule_text, enforcement = parts[:5]
        lessons_out.append(
            {
                "id": lid,
                "project_id": "agents-home",
                "title": f"{lid} ({source_ref})",
                "rule_text": f"{rule_text} [Enforcement: {enforcement}]",
                "enforcement_kind": "enforced",
                "source_ref": source_ref,
                "created_at": f"{date_str}T00:00:00Z" if len(date_str) == 10 else date_str,
            }
        )
    return lessons_out


def build_migration_bundle(source_dir: Path) -> dict:
    projects = build_projects_bundle()
    project_ids = [p.get("id", "") for p in projects if p.get("id")]
    agents = build_agents_bundle(source_dir)
    tasks, task_project_map = parse_tasks(source_dir)
    messages = parse_board_messages(source_dir, task_project_map, project_ids)
    decisions = parse_audits(source_dir)
    lessons = parse_lessons(source_dir)
    return {
        "projects": projects,
        "agents": agents,
        "tasks": tasks,
        "messages": messages,
        "decisions": decisions,
        "lessons": lessons,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate Agents Home Folder into ACH inertly.")
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the Agents Home Folder source directory. Required: this tool migrates "
             "one specific folder, so it does not guess a default.",
    )
    parser.add_argument(
        "--verify-rehearsal",
        action="store_true",
        help="Run idempotency and zero-wake alert checks after importing.",
    )
    args = parser.parse_args(argv)
    source_path = Path(args.source).resolve()
    if not source_path.is_dir():
        print(json.dumps({"ok": False, "error": f"Source directory not found: {source_path}"}))
        return 1

    bundle = build_migration_bundle(source_path)
    first_pass = collab.op_import_history(bundle, source_name="agents-home")

    report = {
        "ok": True,
        "source": str(source_path),
        "workspace": str(collab.BASE_DIR),
        "bundle_totals": {k: len(v) for k, v in bundle.items()},
        "first_pass_imported": first_pass["imported"],
    }

    if args.verify_rehearsal:
        second_pass = collab.op_import_history(bundle, source_name="agents-home")
        import alerts as alerts_mod
        aconn = alerts_mod.open_db()
        try:
            alerts_mod.scan(aconn)
            queued_alerts = aconn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"]
        finally:
            aconn.close()

        # Policy checks are driven by the bundle, so this rehearsal carries no particular
        # project's names. Each check is skipped and reported as null when the bundle has
        # nothing to exercise.
        held = next((p for p in bundle["projects"]
                     if str(p.get("status", "")).lower() in {"on_hold", "paused", "archived"}), None)
        with_paths = next((p for p in bundle["projects"]
                           if (p.get("policy") or {}).get("forbidden_paths")), None)
        with_rule = next((p for p in bundle["projects"]
                          if (p.get("policy") or {}).get("forbid_em_dash")), None)

        hold_check = None
        if held:
            hold_check = collab.op_task_add(
                created_by="rehearsal",
                title="Rehearsal task against a held project",
                project_id=held["id"],
            )
        path_check = None
        if with_paths:
            blocked_path = str(with_paths["policy"]["forbidden_paths"][0])
            path_check = collab.op_post(
                sender="rehearsal",
                content=f"Rehearsal post naming a forbidden path: {blocked_path}",
                project_id=with_paths["id"],
            )
        rule_check = None
        if with_rule:
            rule_check = collab.op_post(
                sender="rehearsal",
                content="Rehearsal post containing an em dash \u2014 to exercise the rule",
                project_id=with_rule["id"],
            )

        report["second_pass_imported"] = second_pass["imported"]
        report["idempotent_zero_duplicates"] = all(v == 0 for v in second_pass["imported"].values())
        report["queued_alerts_after_scan"] = int(queued_alerts)
        report["inert_zero_wakes_verified"] = int(queued_alerts) == 0
        report["policy_checks"] = {
            "held_project_blocks_new_tasks": None if hold_check is None else not hold_check.get("ok", True),
            "forbidden_path_blocked": None if path_check is None else not path_check.get("ok", True),
            "em_dash_ban_enforced": None if rule_check is None else not rule_check.get("ok", True),
        }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
