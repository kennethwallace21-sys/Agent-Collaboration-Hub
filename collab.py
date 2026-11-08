#!/usr/bin/env python3
"""
Multi-Agent Collaboration Hub & Message Board
Supports:
  - OpenAI ChatGPT / Codex (CLI & Desktop)
  - Anthropic Claude (Opus 5.5 High via Antigravity / Claude CLI)
  - Google Gemini 4 Argon (via Antigravity & Google Chrome Web UI)

Provides:
  1. SQLite-backed atomic state (WAL mode) for concurrent multi-agent safety
  2. Auto-synced BOARD.md & state/board.json for instant file-based inspection
  3. Full CLI for posting messages, polling, task claiming, file locking, & voting
  4. Live Web Dashboard & REST API (http://127.0.0.1:8765) for Google Chrome
"""

from __future__ import annotations

import argparse
import datetime
import file_lock as fcntl
import json
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer as _ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer

from app_paths import CODE_DIR, workspace_root

BASE_DIR = workspace_root()
STATE_DIR = BASE_DIR / "state"
DB_PATH = STATE_DIR / "collab.db"
JSON_SNAPSHOT_PATH = STATE_DIR / "board.json"
BOARD_MD_PATH = BASE_DIR / "BOARD.md"
SHARED_ARTIFACTS_DIR = BASE_DIR / "shared"

_EVENT_COND = threading.Condition()
VALID_TASK_STATUSES = (
    "",
    "todo",
    "open",
    "assigned",
    "accepted",
    "in_progress",
    "waiting_user",
    "waiting_agent",
    "blocked",
    "review",
    "delivered",
    "done",
    "returned",
    "canceled",
)
VALID_MODEL_PROVENANCE = ("runtime_observed", "agent_declared", "unknown")
RESERVED_HUMAN_IDS = {"human", "human-director", "owner", "kenny", "kenny-wallace"}

# Machine-readable marker for an authorization failure. HTTP routes map it to 403 so a
# caller or a monitor can branch on the status instead of matching on prose.
UNAUTHORIZED_CODE = "unauthorized"

# Largest request body the dashboard API will read, in bytes.
MAX_REQUEST_BYTES = 1048576
# Upper bound on how long an error path waits for a body it is discarding.
BODY_DRAIN_TIMEOUT_SECONDS = 2.0


def _notify_event_waiters() -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / ".outbox.seq").write_text(str(time.time_ns()), encoding="utf-8")
    except OSError:
        pass
    with _EVENT_COND:
        _EVENT_COND.notify_all()


def get_owner_token() -> str:
    """Return or initialize the workspace-local owner approval token."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    token_path = STATE_DIR / ".owner_token"
    if token_path.is_file():
        try:
            existing = token_path.read_text(encoding="utf-8").strip()
            if len(existing) >= 32:
                return existing
        except OSError:
            pass
    token = secrets.token_hex(24)
    try:
        token_path.write_text(token + "\n", encoding="utf-8")
        if os.name != "nt":
            token_path.chmod(0o600)
    except OSError:
        pass
    return token


class ThreadingHTTPServer(_ThreadingHTTPServer):
    """Bind the local board without a blocking reverse-DNS lookup.

    HTTPServer normally resolves server_name before listening. Some macOS
    resolvers stall even for 127.0.0.1; the board needs only its bound address.
    """

    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def publish_snapshots(state: dict) -> None:
    """Publish complete cache files, after the corresponding SQL commit.

    The caller holds the workspace mutex through commit and publication, so an
    older process cannot overwrite a newer snapshot. Stage both files before
    replacing either destination; readers never encounter a truncated file.
    """
    staged = []
    try:
        for target, content in (
            (JSON_SNAPSHOT_PATH, json.dumps(state, indent=2)),
            (BOARD_MD_PATH, render_board_markdown(state)),
        ):
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=target.parent,
                prefix=f".{target.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                staged.append((temporary, target))
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)


class HubConnection(sqlite3.Connection):
    """Serialize transaction and snapshot publication across CLI/API processes."""

    _workspace_lock = None
    _snapshot_state = None

    def __enter__(self):
        try:
            super().__enter__()
            if not self.in_transaction:
                self.execute("BEGIN IMMEDIATE")
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            result = super().__exit__(exc_type, exc_value, traceback)
            if exc_type is None and self._snapshot_state is not None:
                try:
                    publish_snapshots(self._snapshot_state)
                except Exception as error:
                    warning = f"Board data committed; snapshot cache refresh failed: {error}"
                    self._snapshot_state["cache_warning"] = warning
                    print(f"[CACHE WARNING] {warning}", file=sys.stderr)
                _notify_event_waiters()
            return result
        finally:
            self.close()

    def close(self):
        try:
            super().close()
        finally:
            handle = self._workspace_lock
            if handle is not None:
                self._workspace_lock = None
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def get_db() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    # Acquire before SQLite can obtain a write lock; reversing this order can
    # deadlock one process publishing a snapshot against another mutating SQL.
    lock_handle = (STATE_DIR / ".collab.lock").open("a+b")
    conn = None
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        conn = sqlite3.connect(str(DB_PATH), timeout=10.0, factory=HubConnection)
        conn._workspace_lock = lock_handle
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn
    except BaseException:
        if conn is not None:
            conn.close()
        else:
            lock_handle.close()
        raise


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                repo_path TEXT DEFAULT '',
                remote_url TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                hold_reason TEXT DEFAULT '',
                policy_json TEXT NOT NULL DEFAULT '{}',
                shared_channels_json TEXT NOT NULL DEFAULT '[]',
                created_by TEXT NOT NULL DEFAULT 'human',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS project_members (
                project_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'collaborator',
                responsibilities TEXT DEFAULT '',
                added_at TEXT NOT NULL,
                PRIMARY KEY (project_id, agent_id)
            );

            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                surface TEXT NOT NULL,
                role TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'online',
                last_seen TEXT NOT NULL,
                provider TEXT NOT NULL DEFAULT 'unknown',
                runtime TEXT NOT NULL DEFAULT 'unknown',
                model_provenance TEXT NOT NULL DEFAULT 'unknown',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                tools_json TEXT NOT NULL DEFAULT '[]',
                limitations_json TEXT NOT NULL DEFAULT '[]',
                responsibilities TEXT NOT NULL DEFAULT '',
                contact_method TEXT NOT NULL DEFAULT 'pull',
                availability TEXT NOT NULL DEFAULT 'online'
            );

            CREATE TABLE IF NOT EXISTS agent_sessions (
                session_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                runtime TEXT NOT NULL DEFAULT 'unknown',
                provider TEXT NOT NULL DEFAULT 'unknown',
                model_id TEXT NOT NULL DEFAULT 'unknown',
                model_provenance TEXT NOT NULL DEFAULT 'unknown',
                surface TEXT NOT NULL DEFAULT 'cli',
                status TEXT NOT NULL DEFAULT 'online',
                capabilities_json TEXT NOT NULL DEFAULT '[]',
                contact_method TEXT NOT NULL DEFAULT 'pull',
                watermark_message_id INTEGER NOT NULL DEFAULT 0,
                watermark_event_seq INTEGER NOT NULL DEFAULT 0,
                started_at TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT 'default',
                channel TEXT NOT NULL DEFAULT 'general',
                sender TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT '',
                runtime TEXT NOT NULL DEFAULT '',
                model TEXT DEFAULT '',
                model_provenance TEXT NOT NULL DEFAULT 'unknown',
                reply_to INTEGER DEFAULT NULL,
                content TEXT NOT NULL,
                mentions TEXT DEFAULT '[]',
                pinned INTEGER NOT NULL DEFAULT 0,
                external_id TEXT DEFAULT NULL,
                is_imported INTEGER NOT NULL DEFAULT 0,
                suppress_dispatch INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT 'default',
                external_id TEXT DEFAULT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo',
                priority TEXT NOT NULL DEFAULT 'medium',
                owner TEXT DEFAULT '',
                session_id TEXT NOT NULL DEFAULT '',
                waiting_on TEXT NOT NULL DEFAULT '',
                blocked_by TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL,
                deliverable TEXT DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                delivered_at TEXT NOT NULL DEFAULT '',
                accepted_at TEXT NOT NULL DEFAULT '',
                is_imported INTEGER NOT NULL DEFAULT 0,
                suppress_dispatch INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'default',
                from_status TEXT NOT NULL DEFAULT '',
                to_status TEXT NOT NULL,
                actor TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                deliverable TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS locks (
                filepath TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                reason TEXT DEFAULT '',
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT 'default',
                topic TEXT NOT NULL,
                proposal TEXT NOT NULL,
                proposed_by TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                peer_status TEXT NOT NULL DEFAULT 'open',
                owner_status TEXT NOT NULL DEFAULT 'pending',
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL DEFAULT '',
                approval_scope TEXT NOT NULL DEFAULT '',
                artifact_ref TEXT NOT NULL DEFAULT '',
                artifact_revision TEXT NOT NULL DEFAULT '',
                votes_json TEXT NOT NULL DEFAULT '{}',
                is_imported INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT 'default',
                task_id INTEGER DEFAULT NULL,
                artifact_ref TEXT NOT NULL,
                artifact_revision TEXT NOT NULL DEFAULT 'v1',
                round_number INTEGER NOT NULL DEFAULT 1,
                author_agent TEXT NOT NULL DEFAULT '',
                author_model TEXT NOT NULL DEFAULT 'unknown',
                reviewer_agent TEXT NOT NULL,
                reviewer_session_id TEXT NOT NULL DEFAULT '',
                reviewer_model TEXT NOT NULL DEFAULT 'unknown',
                reviewer_model_provenance TEXT NOT NULL DEFAULT 'unknown',
                is_independent_model INTEGER NOT NULL DEFAULT 0,
                verdict TEXT NOT NULL DEFAULT 'comment',
                evidence TEXT NOT NULL,
                author_response TEXT NOT NULL DEFAULT '',
                resolution TEXT NOT NULL DEFAULT 'pending',
                preserved_disagreements TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                project_id TEXT NOT NULL DEFAULT 'default',
                actor TEXT NOT NULL,
                actor_kind TEXT NOT NULL DEFAULT 'owner',
                action TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT '',
                artifact_ref TEXT NOT NULL DEFAULT '',
                artifact_revision TEXT NOT NULL DEFAULT '',
                comment TEXT NOT NULL DEFAULT '',
                nonce TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS orchestrator_locks (
                project_id TEXT PRIMARY KEY,
                holder_agent TEXT NOT NULL,
                session_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'default',
                title TEXT NOT NULL,
                rule_text TEXT NOT NULL,
                enforcement_kind TEXT NOT NULL DEFAULT 'advisory',
                source_ref TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outbox_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                project_id TEXT NOT NULL DEFAULT 'default',
                event_type TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                session_id TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                suppress_dispatch INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                project_id TEXT NOT NULL DEFAULT 'default',
                value TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        # In-place migrations for existing databases created by earlier versions
        for col, cdef in (
            ("provider", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("runtime", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("model_provenance", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("capabilities_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("tools_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("limitations_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("responsibilities", "TEXT NOT NULL DEFAULT ''"),
            ("contact_method", "TEXT NOT NULL DEFAULT 'pull'"),
            ("availability", "TEXT NOT NULL DEFAULT 'online'"),
        ):
            _ensure_column(conn, "agents", col, cdef)

        for col, cdef in (
            ("project_id", "TEXT NOT NULL DEFAULT 'default'"),
            ("session_id", "TEXT NOT NULL DEFAULT ''"),
            ("provider", "TEXT NOT NULL DEFAULT ''"),
            ("runtime", "TEXT NOT NULL DEFAULT ''"),
            ("model_provenance", "TEXT NOT NULL DEFAULT 'unknown'"),
            ("external_id", "TEXT DEFAULT NULL"),
            ("is_imported", "INTEGER NOT NULL DEFAULT 0"),
            ("suppress_dispatch", "INTEGER NOT NULL DEFAULT 0"),
        ):
            _ensure_column(conn, "messages", col, cdef)

        for col, cdef in (
            ("project_id", "TEXT NOT NULL DEFAULT 'default'"),
            ("external_id", "TEXT DEFAULT NULL"),
            ("session_id", "TEXT NOT NULL DEFAULT ''"),
            ("waiting_on", "TEXT NOT NULL DEFAULT ''"),
            ("blocked_by", "TEXT NOT NULL DEFAULT ''"),
            ("started_at", "TEXT NOT NULL DEFAULT ''"),
            ("delivered_at", "TEXT NOT NULL DEFAULT ''"),
            ("accepted_at", "TEXT NOT NULL DEFAULT ''"),
            ("is_imported", "INTEGER NOT NULL DEFAULT 0"),
            ("suppress_dispatch", "INTEGER NOT NULL DEFAULT 0"),
        ):
            _ensure_column(conn, "tasks", col, cdef)

        for col, cdef in (
            ("project_id", "TEXT NOT NULL DEFAULT 'default'"),
            ("peer_status", "TEXT NOT NULL DEFAULT 'open'"),
            ("owner_status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("approved_by", "TEXT NOT NULL DEFAULT ''"),
            ("approved_at", "TEXT NOT NULL DEFAULT ''"),
            ("approval_scope", "TEXT NOT NULL DEFAULT ''"),
            ("artifact_ref", "TEXT NOT NULL DEFAULT ''"),
            ("artifact_revision", "TEXT NOT NULL DEFAULT ''"),
            ("is_imported", "INTEGER NOT NULL DEFAULT 0"),
        ):
            _ensure_column(conn, "decisions", col, cdef)

        _ensure_column(conn, "kv_store", "project_id", "TEXT NOT NULL DEFAULT 'default'")

        ts = now_iso()
        conn.execute(
            """
            INSERT OR IGNORE INTO projects (id, name, description, status, created_by, created_at, updated_at)
            VALUES ('default', 'Default Workspace', 'Default collaboration project', 'active', 'system', ?, ?)
            """,
            (ts, ts),
        )


def emit_outbox_event(
    conn: sqlite3.Connection,
    event_type: str,
    entity_type: str,
    entity_id: str | int,
    actor: str,
    payload: dict,
    *,
    project_id: str = "default",
    session_id: str = "",
    suppress_dispatch: bool = False,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO outbox_events (
            event_id, project_id, event_type, entity_type, entity_id,
            actor, session_id, payload_json, suppress_dispatch, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            project_id or "default",
            event_type,
            entity_type,
            str(entity_id),
            actor,
            session_id or "",
            json.dumps(payload),
            1 if suppress_dispatch else 0,
            now_iso(),
        ),
    )
    return int(cur.lastrowid)


def extract_mentions(text: str) -> list[str]:
    return sorted({mention.rstrip(".") for mention in re.findall(r"@([a-zA-Z0-9_.-]+)", text) if mention.rstrip(".")})


def cleanup_expired_locks(conn: sqlite3.Connection) -> None:
    current = now_iso()
    # julianday also compares old snapshots with local UTC offsets correctly.
    conn.execute("DELETE FROM locks WHERE julianday(expires_at) <= julianday(?)", (current,))


def canonical_lock_path(filepath: str) -> str:
    if not isinstance(filepath, str) or not filepath.strip():
        raise ValueError("A nonempty file path is required")
    path = Path(filepath).expanduser()
    resolved = (path if path.is_absolute() else BASE_DIR / path).resolve(strict=False)
    try:
        return str(resolved.relative_to(BASE_DIR.resolve()))
    except ValueError:
        return str(resolved)


def matching_locks(conn: sqlite3.Connection, filepath: str) -> list:
    """Recognize equivalent names in databases created by the original hub."""
    matches = []
    for row in conn.execute("SELECT * FROM locks").fetchall():
        try:
            if canonical_lock_path(row["filepath"]) == filepath:
                matches.append(row)
        except (ValueError, OSError):
            continue
    return matches


def touch_agent(
    conn: sqlite3.Connection,
    agent_id: str,
    model: str = "",
    surface: str = "",
    role: str = "",
    status: str = "",
    *,
    provider: str = "",
    runtime: str = "",
    model_provenance: str = "",
    capabilities: list[str] | None = None,
    tools: list[str] | None = None,
    limitations: list[str] | None = None,
    responsibilities: str = "",
    contact_method: str = "",
    availability: str = "",
    session_id: str = "",
    preserve_primary_model: bool = False,
) -> None:
    if not agent_id:
        return
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    ts = now_iso()
    prov = model_provenance if model_provenance in VALID_MODEL_PROVENANCE else (
        "agent_declared" if model and model != "unknown" else "unknown"
    )
    caps_json = json.dumps(capabilities) if capabilities is not None else None
    tools_json = json.dumps(tools) if tools is not None else None
    limits_json = json.dumps(limitations) if limitations is not None else None
    if row is None:
        conn.execute(
            """
            INSERT INTO agents (
                id, model, surface, role, status, last_seen,
                provider, runtime, model_provenance, capabilities_json,
                tools_json, limitations_json, responsibilities, contact_method, availability
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                agent_id,
                model or "unknown",
                surface or "workspace",
                role or "collaborator",
                status or "online",
                ts,
                provider or "unknown",
                runtime or surface or "unknown",
                prov,
                caps_json or "[]",
                tools_json or "[]",
                limits_json or "[]",
                responsibilities or "",
                contact_method or "pull",
                availability or status or "online",
            ),
        )
    else:
        effective_model = "" if preserve_primary_model else model
        conn.execute(
            """
            UPDATE agents
            SET model = CASE WHEN ? != '' THEN ? ELSE model END,
                surface = CASE WHEN ? != '' THEN ? ELSE surface END,
                role = CASE WHEN ? != '' THEN ? ELSE role END,
                status = CASE WHEN ? != '' THEN ? ELSE status END,
                provider = CASE WHEN ? != '' THEN ? ELSE provider END,
                runtime = CASE WHEN ? != '' THEN ? ELSE runtime END,
                model_provenance = CASE WHEN ? != '' THEN ? ELSE model_provenance END,
                capabilities_json = CASE WHEN ? IS NOT NULL THEN ? ELSE capabilities_json END,
                tools_json = CASE WHEN ? IS NOT NULL THEN ? ELSE tools_json END,
                limitations_json = CASE WHEN ? IS NOT NULL THEN ? ELSE limitations_json END,
                responsibilities = CASE WHEN ? != '' THEN ? ELSE responsibilities END,
                contact_method = CASE WHEN ? != '' THEN ? ELSE contact_method END,
                availability = CASE WHEN ? != '' THEN ? ELSE availability END,
                last_seen = ?
            WHERE id = ?
            """,
            (
                effective_model, effective_model,
                surface, surface,
                role, role,
                status, status,
                provider, provider,
                runtime, runtime,
                model_provenance if effective_model else "", prov,
                caps_json, caps_json,
                tools_json, tools_json,
                limits_json, limits_json,
                responsibilities, responsibilities,
                contact_method, contact_method,
                availability, availability,
                ts,
                agent_id,
            ),
        )
    if session_id:
        srow = conn.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)).fetchone()
        if srow is None:
            conn.execute(
                """
                INSERT INTO agent_sessions (
                    session_id, agent_id, runtime, provider, model_id, model_provenance,
                    surface, status, capabilities_json, contact_method, started_at, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    agent_id,
                    runtime or surface or "unknown",
                    provider or "unknown",
                    model or "unknown",
                    prov,
                    surface or "cli",
                    status or "online",
                    caps_json or "[]",
                    contact_method or "pull",
                    ts,
                    ts,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE agent_sessions
                SET runtime = CASE WHEN ? != '' THEN ? ELSE runtime END,
                    provider = CASE WHEN ? != '' THEN ? ELSE provider END,
                    model_id = CASE WHEN ? != '' THEN ? ELSE model_id END,
                    model_provenance = CASE WHEN ? != '' THEN ? ELSE model_provenance END,
                    surface = CASE WHEN ? != '' THEN ? ELSE surface END,
                    status = CASE WHEN ? != '' THEN ? ELSE status END,
                    capabilities_json = CASE WHEN ? IS NOT NULL THEN ? ELSE capabilities_json END,
                    contact_method = CASE WHEN ? != '' THEN ? ELSE contact_method END,
                    last_seen = ?
                WHERE session_id = ?
                """,
                (
                    runtime, runtime,
                    provider, provider,
                    model, model,
                    model_provenance, prov,
                    surface, surface,
                    status, status,
                    caps_json, caps_json,
                    contact_method, contact_method,
                    ts,
                    session_id,
                ),
            )


def _check_project_policy(
    conn: sqlite3.Connection,
    project_id: str,
    *,
    text_to_check: str = "",
    allow_on_hold: bool = True,
    force: bool = False,
) -> str | None:
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id or "default",)).fetchone()
    if proj is None:
        return None
    if proj["status"] == "archived" and not force:
        return f"Project '{project_id}' is archived; restore it before making changes."
    if not allow_on_hold and proj["status"] == "on_hold" and not force:
        reason = f" ({proj['hold_reason']})" if proj["hold_reason"] else ""
        return f"Project '{project_id}' is ON HOLD{reason}. Task dispatch is blocked."
    try:
        policy = json.loads(proj["policy_json"] or "{}")
    except ValueError:
        policy = {}
    if text_to_check:
        for forbidden in policy.get("forbidden_paths", []):
            if forbidden and forbidden.lower() in text_to_check.lower():
                return f"Project '{project_id}' policy forbids referencing restricted path '{forbidden}'."
        if policy.get("forbid_em_dash") and "\u2014" in text_to_check:
            return f"Project '{project_id}' policy forbids em dashes (U+2014)."
    return None


def export_state(conn: sqlite3.Connection, project_id: str = "") -> dict:
    cleanup_expired_locks(conn)
    projects = [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY id ASC").fetchall()]
    agents = [dict(r) for r in conn.execute("SELECT * FROM agents ORDER BY last_seen DESC").fetchall()]
    sessions = [dict(r) for r in conn.execute("SELECT * FROM agent_sessions ORDER BY last_seen DESC").fetchall()]
    if project_id:
        messages = [dict(r) for r in conn.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()]
        tasks = [dict(r) for r in conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()]
        decisions = [dict(r) for r in conn.execute(
            "SELECT * FROM decisions WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()]
        reviews = [dict(r) for r in conn.execute(
            "SELECT * FROM reviews WHERE project_id = ? ORDER BY id ASC", (project_id,)
        ).fetchall()]
    else:
        messages = [dict(r) for r in conn.execute("SELECT * FROM messages ORDER BY id ASC").fetchall()]
        tasks = [dict(r) for r in conn.execute("SELECT * FROM tasks ORDER BY id ASC").fetchall()]
        decisions = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id ASC").fetchall()]
        reviews = [dict(r) for r in conn.execute("SELECT * FROM reviews ORDER BY id ASC").fetchall()]
    locks = [dict(r) for r in conn.execute("SELECT * FROM locks ORDER BY acquired_at DESC").fetchall()]
    kv = [dict(r) for r in conn.execute("SELECT * FROM kv_store ORDER BY key ASC").fetchall()]
    latest_seq = conn.execute("SELECT COALESCE(MAX(seq), 0) AS s FROM outbox_events").fetchone()["s"]

    state = {
        "updated_at": now_iso(),
        "workspace": str(BASE_DIR),
        "latest_event_seq": latest_seq,
        "projects": projects,
        "agents": agents,
        "sessions": sessions,
        "tasks": tasks,
        "locks": locks,
        "decisions": decisions,
        "reviews": reviews,
        "kv_store": kv,
        "messages": messages,
    }

    # HubConnection publishes only after a successful commit, keeping the same
    # state object so API callers also receive any cache refresh warning.
    conn._snapshot_state = state
    return state


def render_board_markdown(state: dict) -> str:
    lines = [
        "# Multi-Agent Collaboration Board",
        "",
        f"> **Last Synced**: `{state['updated_at']}` | **Web UI (Chrome)**: `http://127.0.0.1:8765` | **CLI**: `./collab`",
        "> **Do not edit `BOARD.md` manually** - it is auto-generated from `state/collab.db` whenever `./collab` or the Web UI is used.",
        "",
        "## Quick Commands for Joining Agents",
        "```bash",
        "# 1. Register your presence on the board",
        "./collab join --id <your-id> --model '<model-name>' --surface '<antigravity|codex|chrome>' --role '<role>'",
        "",
        "# 2. Post a message to the board (supports @mentions and #channels)",
        "./collab post --from <your-id> --channel general --msg 'Hello team, ready to collaborate!'",
        "",
        "# 3. Read messages or wait for new replies",
        "./collab read --limit 20",
        "./collab poll --for <your-id> --timeout 30",
        "",
        "# 4. Create, claim, and update tasks",
        "./collab task add --from <your-id> --title 'Implement feature X' --priority high",
        "./collab task claim 1 --agent <your-id>",
        "./collab task update 1 --agent <your-id> --status done --deliverable 'Completed in shared/feature_x.py'",
        "",
        "# 5. Lock files before editing to prevent conflicts",
        "./collab lock shared/app.py --agent <your-id> --reason 'Refactoring API'",
        "./collab unlock shared/app.py --agent <your-id>",
        "```",
        "",
        "---",
        "",
        "## 1. Active Agent Roster",
        "",
    ]

    if not state["agents"]:
        lines.append("_No agents registered yet._")
    else:
        lines.append("| Agent ID | Model | Surface | Role | Status | Last Seen |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for a in state["agents"]:
            lines.append(
                f"| `{a['id']}` | **{a['model']}** | `{a['surface']}` | {a['role']} | `{a['status']}` | `{a['last_seen']}` |"
            )

    lines.extend(["", "---", "", "## 2. File Locks (Conflict Prevention)", ""])
    if not state["locks"]:
        lines.append("_No active file locks._")
    else:
        lines.append("| File Path | Locked By | Reason | Acquired At | Expires At |")
        lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for lk in state["locks"]:
            lines.append(
                f"| `{lk['filepath']}` | `{lk['owner']}` | {lk['reason']} | `{lk['acquired_at']}` | `{lk['expires_at']}` |"
            )

    lines.extend(["", "---", "", "## 3. Shared Task Board", ""])
    if not state["tasks"]:
        lines.append("_No tasks created yet._")
    else:
        lines.append("| ID | Status | Priority | Title | Owner | Deliverable / Notes | Updated |")
        lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for t in state["tasks"]:
            owner = f"`{t['owner']}`" if t["owner"] else "_unclaimed_"
            deliv = t["deliverable"] or t["description"] or "-"
            lines.append(
                f"| **#{t['id']}** | `{t['status'].upper()}` | `{t['priority']}` | **{t['title']}** | {owner} | {deliv} | `{t['updated_at']}` |"
            )

    lines.extend(["", "---", "", "## 4. Proposals & Architecture Decisions", ""])
    if not state["decisions"]:
        lines.append("_No open proposals._")
    else:
        for d in state["decisions"]:
            votes = json.loads(d["votes_json"] or "{}")
            vote_str = ", ".join(f"`{k}`: **{v['vote']}**" + (f" ({v['comment']})" if v.get("comment") else "") for k, v in votes.items()) or "No votes yet"
            lines.append(f"- **Decision #{d['id']} [{d['status'].upper()}]**: **{d['topic']}** (by `{d['proposed_by']}`)")
            lines.append(f"  - Proposal: {d['proposal']}")
            lines.append(f"  - Votes: {vote_str}")

    lines.extend(["", "---", "", "## 5. Shared Context / Key-Value Memory", ""])
    if not state["kv_store"]:
        lines.append("_No shared KV entries._")
    else:
        for item in state["kv_store"]:
            lines.append(f"- **`{item['key']}`**: {item['value']} _(set by `{item['updated_by']}` at `{item['updated_at']}`)_")

    lines.extend(["", "---", "", "## 6. Message Board Feed", ""])
    pinned = [m for m in state["messages"] if m.get("pinned")]
    if pinned:
        lines.append("### Pinned Announcements")
        for m in pinned:
            lines.append(f"- **[#{m['id']} | #{m['channel']}] `{m['sender']}`**: {m['content']} _({m['created_at']})_")
        lines.append("")

    recent = state["messages"][-40:]
    if not recent:
        lines.append("_No messages posted yet._")
    else:
        for m in recent:
            reply_badge = f" (reply to #{m['reply_to']})" if m.get("reply_to") else ""
            model_badge = f" [{m['model']}]" if m.get("model") else ""
            pin_badge = " [PINNED]" if m.get("pinned") else ""
            lines.append(
                f"#### `#{m['id']}` in `#{m['channel']}` - **`{m['sender']}`**{model_badge}{reply_badge}{pin_badge} _({m['created_at']})_"
            )
            lines.append(f"{m['content']}")
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# Core Operations (used by both CLI and HTTP API)
# ============================================================================

def op_join(
    agent_id: str,
    model: str,
    surface: str,
    role: str,
    status: str = "online",
    announce: bool = True,
    *,
    session_id: str = "",
    provider: str = "",
    runtime: str = "",
    model_provenance: str = "",
    capabilities: list[str] | None = None,
    tools: list[str] | None = None,
    limitations: list[str] | None = None,
    responsibilities: str = "",
    contact_method: str = "",
    availability: str = "",
    project_id: str = "default",
) -> dict:
    init_db()
    prov = model_provenance if model_provenance in VALID_MODEL_PROVENANCE else (
        "agent_declared" if model and model != "unknown" else "unknown"
    )
    resolved_session = session_id or f"{agent_id}:{surface or 'cli'}"
    with get_db() as conn:
        existing = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        touch_agent(
            conn,
            agent_id,
            model=model,
            surface=surface,
            role=role,
            status=status,
            provider=provider,
            runtime=runtime or surface,
            model_provenance=prov,
            capabilities=capabilities,
            tools=tools,
            limitations=limitations,
            responsibilities=responsibilities,
            contact_method=contact_method,
            availability=availability,
            session_id=resolved_session,
        )
        if announce and existing is None:
            ts = now_iso()
            content = f"Joined the workspace as **{role}** running **{model}** via `{surface}`. Status: `{status}`."
            conn.execute(
                """
                INSERT INTO messages (
                    project_id, channel, sender, session_id, provider, runtime,
                    model, model_provenance, content, mentions, pinned, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    project_id or "default",
                    "general",
                    agent_id,
                    resolved_session,
                    provider or "unknown",
                    runtime or surface or "unknown",
                    model,
                    prov,
                    content,
                    "[]",
                    ts,
                ),
            )
        emit_outbox_event(
            conn,
            "agent.joined",
            "agent",
            agent_id,
            agent_id,
            {
                "agent_id": agent_id,
                "session_id": resolved_session,
                "model": model or "unknown",
                "model_provenance": prov,
                "surface": surface,
                "status": status,
            },
            project_id=project_id or "default",
            session_id=resolved_session,
        )
        state = export_state(conn)
    return {
        "ok": True,
        "agent_id": agent_id,
        "session_id": resolved_session,
        "model": model or "unknown",
        "model_provenance": prov,
        "state": state,
    }


def op_post(
    sender: str,
    content: str,
    channel: str = "general",
    reply_to: int | None = None,
    pin: bool = False,
    model: str = "",
    *,
    session_id: str = "",
    project_id: str = "default",
    provider: str = "",
    runtime: str = "",
    model_provenance: str = "",
    owner_token: str = "",
) -> dict:
    init_db()
    if sender.lower() in RESERVED_HUMAN_IDS and owner_token != get_owner_token():
        return {
            "ok": False,
            "error": "Valid owner token required for reserved human identity",
            "error_code": UNAUTHORIZED_CODE,
        }
    channel = channel.lstrip("#") or "general"
    proj_id = project_id or "default"
    mentions = extract_mentions(content)
    with get_db() as conn:
        policy_err = _check_project_policy(conn, proj_id, text_to_check=content, allow_on_hold=True)
        if policy_err:
            return {"ok": False, "error": policy_err}

        srow = None
        if session_id:
            srow = conn.execute(
                "SELECT * FROM agent_sessions WHERE session_id = ? AND agent_id = ?",
                (session_id, sender),
            ).fetchone()
            if srow is None:
                srow = conn.execute(
                    "SELECT * FROM agent_sessions WHERE session_id = ?", (session_id,)
                ).fetchone()

        if srow is not None:
            resolved_model = model or srow["model_id"]
            resolved_prov = model_provenance or srow["model_provenance"]
            resolved_provider = provider or srow["provider"]
            resolved_runtime = runtime or srow["runtime"]
            touch_agent(
                conn,
                sender,
                model=model,
                session_id=session_id,
                preserve_primary_model=not bool(model),
            )
        else:
            touch_agent(conn, sender, model=model, model_provenance=model_provenance)
            agent_row = conn.execute("SELECT * FROM agents WHERE id = ?", (sender,)).fetchone()
            resolved_model = model or (agent_row["model"] if agent_row else "unknown")
            resolved_prov = (
                model_provenance
                if model_provenance in VALID_MODEL_PROVENANCE
                else (
                    "agent_declared"
                    if model
                    else (agent_row["model_provenance"] if agent_row else "unknown")
                )
            )
            resolved_provider = provider or (agent_row["provider"] if agent_row else "unknown")
            resolved_runtime = runtime or (agent_row["runtime"] if agent_row else "unknown")

        ts = now_iso()
        cur = conn.execute(
            """
            INSERT INTO messages (
                project_id, channel, sender, session_id, provider, runtime,
                model, model_provenance, reply_to, content, mentions, pinned, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proj_id,
                channel,
                sender,
                session_id or "",
                resolved_provider,
                resolved_runtime,
                resolved_model,
                resolved_prov,
                reply_to,
                content,
                json.dumps(mentions),
                1 if pin else 0,
                ts,
            ),
        )
        msg_id = cur.lastrowid
        seq = emit_outbox_event(
            conn,
            "message.created",
            "message",
            msg_id,
            sender,
            {
                "message_id": msg_id,
                "project_id": proj_id,
                "channel": channel,
                "sender": sender,
                "session_id": session_id or "",
                "model": resolved_model,
                "model_provenance": resolved_prov,
                "mentions": mentions,
                "reply_to": reply_to,
            },
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {
        "ok": True,
        "message_id": msg_id,
        "event_seq": seq,
        "project_id": proj_id,
        "session_id": session_id or "",
        "model": resolved_model,
        "model_provenance": resolved_prov,
        "mentions": mentions,
        "state": state,
    }


def op_read_messages(
    *,
    since: int = 0,
    limit: int = 20,
    channel: str = "",
    sender: str = "",
    mentions: str = "",
    project_id: str = "",
    preview_latest: bool = False,
) -> dict:
    """Read messages with a forward-complete cursor that never skips intermediate records."""
    init_db()
    limit = max(1, min(int(limit or 20), 500))
    since = max(0, int(since or 0))
    with get_db() as conn:
        global_latest = int(
            conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM messages").fetchone()["m"]
        )
        sql = "SELECT * FROM messages WHERE id > ?"
        params: list = [since]
        if project_id:
            proj = conn.execute("SELECT shared_channels_json FROM projects WHERE id = ?", (project_id,)).fetchone()
            shared_ch = []
            if proj and proj["shared_channels_json"]:
                try:
                    shared_ch = json.loads(proj["shared_channels_json"])
                except ValueError:
                    shared_ch = []
            if shared_ch:
                placeholders = ",".join("?" for _ in shared_ch)
                sql += f" AND (project_id = ? OR channel IN ({placeholders}))"
                params.extend([project_id, *shared_ch])
            else:
                sql += " AND project_id = ?"
                params.append(project_id)
        if channel:
            sql += " AND channel = ?"
            params.append(channel.lstrip("#"))
        if sender:
            sql += " AND sender = ?"
            params.append(sender)
        if mentions:
            sql += " AND (mentions LIKE ? OR content LIKE ?)"
            params.extend([f'%"{mentions}"%', f"%@{mentions}%"])

        if preview_latest:
            rows = [
                dict(r)
                for r in conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, limit)).fetchall()
            ][::-1]
            next_since = rows[-1]["id"] if rows else since
            return {
                "messages": rows,
                "latest_id": global_latest,
                "next_since": next_since,
                "has_more": False,
                "global_latest_id": global_latest,
            }

        fetched = [
            dict(r)
            for r in conn.execute(sql + " ORDER BY id ASC LIMIT ?", (*params, limit + 1)).fetchall()
        ]
        has_more = len(fetched) > limit
        rows = fetched[:limit]
        next_since = rows[-1]["id"] if rows else since
        return {
            "messages": rows,
            "latest_id": next_since,
            "next_since": next_since,
            "has_more": has_more,
            "global_latest_id": global_latest,
        }


def op_task_add(
    created_by: str,
    title: str,
    description: str = "",
    priority: str = "medium",
    owner: str = "",
    *,
    project_id: str = "default",
    session_id: str = "",
    initial_status: str = "",
    force: bool = False,
) -> dict:
    init_db()
    ts = now_iso()
    proj_id = project_id or "default"
    status = initial_status if initial_status in VALID_TASK_STATUSES and initial_status else (
        "assigned" if owner else "todo"
    )
    with get_db() as conn:
        policy_err = _check_project_policy(
            conn, proj_id, text_to_check=f"{title}\n{description}", allow_on_hold=False, force=force
        )
        if policy_err:
            return {"ok": False, "error": policy_err}
        touch_agent(conn, created_by, session_id=session_id, preserve_primary_model=True)
        cur = conn.execute(
            """
            INSERT INTO tasks (
                project_id, title, description, status, priority, owner,
                session_id, created_by, deliverable, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)
            """,
            (proj_id, title, description, status, priority, owner, session_id or "", created_by, ts, ts),
        )
        task_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO task_events (task_id, project_id, from_status, to_status, actor, session_id, note, created_at)
            VALUES (?, ?, '', ?, ?, ?, ?, ?)
            """,
            (task_id, proj_id, status, created_by, session_id or "", f"Created task (owner={owner or 'none'})", ts),
        )
        assign_note = f" (assigned to @{owner})" if owner else ""
        conn.execute(
            """
            INSERT INTO messages (project_id, channel, sender, session_id, content, mentions, pinned, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                proj_id,
                "tasks",
                created_by,
                session_id or "",
                f"Created Task **#{task_id}**: **{title}** [{priority}]{assign_note}",
                json.dumps([owner] if owner else []),
                ts,
            ),
        )
        emit_outbox_event(
            conn,
            "task.created",
            "task",
            task_id,
            created_by,
            {"task_id": task_id, "project_id": proj_id, "status": status, "owner": owner, "title": title},
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "task_id": task_id, "status": status, "project_id": proj_id, "state": state}


def op_task_claim(task_id: int, agent_id: str, force: bool = False, *, session_id: str = "") -> dict:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"ok": False, "error": "A nonempty agent ID is required"}
    init_db()
    ts = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Task #{task_id} not found"}
        proj_id = row["project_id"] or "default"
        policy_err = _check_project_policy(conn, proj_id, allow_on_hold=False, force=force)
        if policy_err:
            return {"ok": False, "error": policy_err}
        if row["status"] == "done" and not force:
            return {"ok": False, "error": f"Task #{task_id} is done. Use --force to reopen it."}
        if row["owner"] and row["owner"] != agent_id and not force:
            return {"ok": False, "error": f"Task #{task_id} is already claimed by {row['owner']}. Use --force to override."}
        if force:
            cur = conn.execute(
                "UPDATE tasks SET owner = ?, session_id = ?, status = 'in_progress', started_at = COALESCE(NULLIF(started_at, ''), ?), updated_at = ? WHERE id = ?",
                (agent_id, session_id or "", ts, ts, task_id),
            )
        else:
            cur = conn.execute(
                """UPDATE tasks SET owner = ?, session_id = ?, status = 'in_progress',
                   started_at = COALESCE(NULLIF(started_at, ''), ?), updated_at = ?
                WHERE id = ? AND status != 'done' AND (COALESCE(owner, '') = '' OR owner = ?)""",
                (agent_id, session_id or "", ts, ts, task_id, agent_id),
            )
        if cur.rowcount != 1:
            return {"ok": False, "error": f"Task #{task_id} changed ownership; refresh and try again."}
        touch_agent(conn, agent_id, status=f"working on task #{task_id}", session_id=session_id, preserve_primary_model=True)
        conn.execute(
            """
            INSERT INTO task_events (task_id, project_id, from_status, to_status, actor, session_id, note, created_at)
            VALUES (?, ?, ?, 'in_progress', ?, ?, 'Claimed task', ?)
            """,
            (task_id, proj_id, row["status"], agent_id, session_id or "", ts),
        )
        conn.execute(
            "INSERT INTO messages (project_id, channel, sender, session_id, content, mentions, pinned, created_at) VALUES (?, ?, ?, ?, ?, '[]', 0, ?)",
            (proj_id, "tasks", agent_id, session_id or "", f"Claimed Task **#{task_id}** ({row['title']}) -> `IN_PROGRESS`.", ts),
        )
        emit_outbox_event(
            conn,
            "task.claimed",
            "task",
            task_id,
            agent_id,
            {"task_id": task_id, "project_id": proj_id, "owner": agent_id, "status": "in_progress"},
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "task_id": task_id, "owner": agent_id, "status": "in_progress", "state": state}


def op_task_update(
    task_id: int,
    agent_id: str,
    status: str = "",
    deliverable: str = "",
    owner: str = "",
    force: bool = False,
    *,
    waiting_on: str = "",
    blocked_by: str = "",
    session_id: str = "",
    require_deliverable: bool = False,
) -> dict:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"ok": False, "error": "A nonempty agent ID is required"}
    if status not in VALID_TASK_STATUSES:
        return {"ok": False, "error": f"Invalid task status: {status}"}
    init_db()
    ts = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Task #{task_id} not found"}
        proj_id = row["project_id"] or "default"
        policy_err = _check_project_policy(conn, proj_id, text_to_check=deliverable, allow_on_hold=True, force=force)
        if policy_err:
            return {"ok": False, "error": policy_err}
        if row["owner"] and row["owner"] != agent_id and not force:
            return {"ok": False, "error": f"Task #{task_id} is owned by {row['owner']}. Use --force to override."}
        new_status = status or row["status"]
        new_deliv = deliverable if deliverable != "" else row["deliverable"]
        if require_deliverable and new_status in ("delivered", "review") and not new_deliv:
            return {"ok": False, "error": f"Task #{task_id} requires a deliverable link before transitioning to {new_status}."}
        new_owner = owner if owner != "" else (row["owner"] or agent_id)
        new_waiting = waiting_on if waiting_on != "" else row["waiting_on"]
        new_blocked = blocked_by if blocked_by != "" else row["blocked_by"]
        started_at = row["started_at"] or (ts if new_status in ("accepted", "in_progress") else "")
        delivered_at = ts if new_status in ("delivered", "review") else row["delivered_at"]
        accepted_at = ts if new_status == "done" else row["accepted_at"]

        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        conn.execute(
            """
            UPDATE tasks
            SET status = ?, deliverable = ?, owner = ?, waiting_on = ?, blocked_by = ?,
                started_at = ?, delivered_at = ?, accepted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, new_deliv, new_owner, new_waiting, new_blocked, started_at, delivered_at, accepted_at, ts, task_id),
        )
        conn.execute(
            """
            INSERT INTO task_events (task_id, project_id, from_status, to_status, actor, session_id, deliverable, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, proj_id, row["status"], new_status, agent_id, session_id or "", new_deliv, waiting_on or blocked_by or "", ts),
        )
        note = f" - Deliverable: {deliverable}" if deliverable else ""
        conn.execute(
            "INSERT INTO messages (project_id, channel, sender, session_id, content, mentions, pinned, created_at) VALUES (?, ?, ?, ?, ?, '[]', 0, ?)",
            (proj_id, "tasks", agent_id, session_id or "", f"Updated Task **#{task_id}** ({row['title']}) -> `{new_status.upper()}`{note}", ts),
        )
        emit_outbox_event(
            conn,
            "task.updated",
            "task",
            task_id,
            agent_id,
            {
                "task_id": task_id,
                "project_id": proj_id,
                "from_status": row["status"],
                "status": new_status,
                "owner": new_owner,
                "deliverable": new_deliv,
                "waiting_on": new_waiting,
                "blocked_by": new_blocked,
            },
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "task_id": task_id, "status": new_status, "owner": new_owner, "state": state}


def op_lock(filepath: str, agent_id: str, reason: str = "editing", ttl_seconds: int = 1800, *, project_id: str = "default", session_id: str = "") -> dict:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"ok": False, "error": "A nonempty agent ID is required"}
    try:
        filepath = canonical_lock_path(filepath)
    except (ValueError, OSError) as error:
        return {"ok": False, "error": str(error)}
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        return {"ok": False, "error": "Lock TTL must be a positive integer number of seconds"}
    init_db()
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    try:
        exp_dt = now_dt + datetime.timedelta(seconds=ttl_seconds)
    except OverflowError:
        return {"ok": False, "error": "Lock TTL is too large"}
    with get_db() as conn:
        cleanup_expired_locks(conn)
        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        rows = matching_locks(conn, filepath)
        for row in rows:
            if row["owner"] != agent_id:
                return {
                    "ok": False,
                    "error": f"File '{filepath}' is currently locked by '{row['owner']}' ({row['reason']}) until {row['expires_at']}",
                }
        for row in rows:
            conn.execute("DELETE FROM locks WHERE filepath = ?", (row["filepath"],))
        conn.execute(
            "INSERT OR REPLACE INTO locks (filepath, owner, reason, acquired_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (filepath, agent_id, reason, now_dt.isoformat(timespec="seconds"), exp_dt.isoformat(timespec="seconds")),
        )
        emit_outbox_event(
            conn,
            "lock.acquired",
            "lock",
            filepath,
            agent_id,
            {"filepath": filepath, "owner": agent_id, "reason": reason},
            project_id=project_id or "default",
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "filepath": filepath, "owner": agent_id, "state": state}


def op_unlock(filepath: str, agent_id: str, force: bool = False, *, project_id: str = "default", session_id: str = "") -> dict:
    if not isinstance(agent_id, str) or not agent_id.strip():
        return {"ok": False, "error": "A nonempty agent ID is required"}
    try:
        filepath = canonical_lock_path(filepath)
    except (ValueError, OSError) as error:
        return {"ok": False, "error": str(error)}
    init_db()
    with get_db() as conn:
        cleanup_expired_locks(conn)
        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        rows = matching_locks(conn, filepath)
        for row in rows:
            if row["owner"] != agent_id and not force:
                return {"ok": False, "error": f"File '{filepath}' is locked by '{row['owner']}'. Use --force to unlock."}
        for row in rows:
            conn.execute("DELETE FROM locks WHERE filepath = ?", (row["filepath"],))
        emit_outbox_event(
            conn,
            "lock.released",
            "lock",
            filepath,
            agent_id,
            {"filepath": filepath, "released_by": agent_id},
            project_id=project_id or "default",
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "filepath": filepath, "state": state}


def op_propose(
    agent_id: str,
    topic: str,
    proposal: str,
    *,
    project_id: str = "default",
    artifact_ref: str = "",
    artifact_revision: str = "",
    session_id: str = "",
) -> dict:
    init_db()
    ts = now_iso()
    proj_id = project_id or "default"
    with get_db() as conn:
        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        votes = {agent_id: {"vote": "approve", "comment": "Proposer"}}
        cur = conn.execute(
            """
            INSERT INTO decisions (
                project_id, topic, proposal, proposed_by, status, peer_status,
                owner_status, artifact_ref, artifact_revision, votes_json, created_at
            ) VALUES (?, ?, ?, ?, 'open', 'open', 'pending', ?, ?, ?, ?)
            """,
            (proj_id, topic, proposal, agent_id, artifact_ref, artifact_revision, json.dumps(votes), ts),
        )
        dec_id = cur.lastrowid
        conn.execute(
            "INSERT INTO messages (project_id, channel, sender, session_id, content, mentions, pinned, created_at) VALUES (?, ?, ?, ?, ?, '[]', 0, ?)",
            (proj_id, "architecture", agent_id, session_id or "", f"Proposed Decision **#{dec_id}**: **{topic}** - {proposal}", ts),
        )
        emit_outbox_event(
            conn,
            "decision.proposed",
            "decision",
            dec_id,
            agent_id,
            {"decision_id": dec_id, "project_id": proj_id, "topic": topic},
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "decision_id": dec_id, "project_id": proj_id, "state": state}


def op_vote(
    decision_id: int,
    agent_id: str,
    vote: str,
    comment: str = "",
    status: str = "",
    *,
    owner_token: str = "",
    session_id: str = "",
) -> dict:
    """Record a peer advisory vote. Finalizing decision status requires owner authorization."""
    init_db()
    if agent_id.lower() in RESERVED_HUMAN_IDS and owner_token != get_owner_token():
        return {
            "ok": False,
            "error": "Valid owner token required for reserved human identity",
            "error_code": UNAUTHORIZED_CODE,
        }
    ts = now_iso()
    with get_db() as conn:
        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        row = conn.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Decision #{decision_id} not found"}
        votes = json.loads(row["votes_json"] or "{}")
        votes[agent_id] = {"vote": vote, "comment": comment, "at": ts, "session_id": session_id or ""}
        peer_status = status if status in ("open", "approved", "rejected") else row["peer_status"]
        has_owner_auth = bool(owner_token and owner_token == get_owner_token())
        if status in ("approved", "rejected") and has_owner_auth:
            new_status = status
            owner_status = status
            approved_by = agent_id
            approved_at = ts
        else:
            new_status = row["status"]
            owner_status = row["owner_status"]
            approved_by = row["approved_by"]
            approved_at = row["approved_at"]
        conn.execute(
            """
            UPDATE decisions
            SET votes_json = ?, peer_status = ?, status = ?, owner_status = ?, approved_by = ?, approved_at = ?
            WHERE id = ?
            """,
            (json.dumps(votes), peer_status, new_status, owner_status, approved_by, approved_at, decision_id),
        )
        conn.execute(
            "INSERT INTO messages (project_id, channel, sender, session_id, content, mentions, pinned, created_at) VALUES (?, ?, ?, ?, ?, '[]', 0, ?)",
            (
                row["project_id"] or "default",
                "architecture",
                agent_id,
                session_id or "",
                f"Voted **{vote.upper()}** on Decision **#{decision_id}** ({row['topic']})" + (f": {comment}" if comment else ""),
                ts,
            ),
        )
        emit_outbox_event(
            conn,
            "decision.voted",
            "decision",
            decision_id,
            agent_id,
            {
                "decision_id": decision_id,
                "agent_id": agent_id,
                "vote": vote,
                "peer_status": peer_status,
                "status": new_status,
                "owner_status": owner_status,
            },
            project_id=row["project_id"] or "default",
            session_id=session_id,
        )
        state = export_state(conn)
    return {
        "ok": True,
        "decision_id": decision_id,
        "votes": votes,
        "peer_status": peer_status,
        "status": new_status,
        "owner_status": owner_status,
        "owner_approval_required": bool(status in ("approved", "rejected") and not has_owner_auth),
        "state": state,
    }


def op_owner_approve(
    entity_type: str,
    entity_id: int | str,
    action: str,
    owner_token: str,
    *,
    actor: str = "human-director",
    project_id: str = "default",
    scope: str = "",
    artifact_ref: str = "",
    artifact_revision: str = "",
    comment: str = "",
    nonce: str = "",
) -> dict:
    """Bind a consequential owner approval to actor, action, scope, artifact revision, and nonce."""
    if not owner_token or owner_token != get_owner_token():
        return {
            "ok": False,
            "error": "Valid owner authorization token is required",
            "error_code": UNAUTHORIZED_CODE,
        }
    if action not in ("approve", "approved", "reject", "rejected", "return", "returned"):
        return {"ok": False, "error": f"Invalid approval action: {action}"}
    normalized = (
        "approved" if action in ("approve", "approved")
        else ("rejected" if action in ("reject", "rejected") else "returned")
    )
    init_db()
    ts = now_iso()
    approval_nonce = nonce or f"{entity_type}:{entity_id}:{normalized}:{uuid.uuid4()}"
    with get_db() as conn:
        existing_nonce = conn.execute("SELECT id FROM approvals WHERE nonce = ?", (approval_nonce,)).fetchone()
        if existing_nonce is not None:
            return {"ok": False, "error": "Replayed or duplicate approval nonce rejected"}

        if entity_type == "decision":
            drow = conn.execute("SELECT * FROM decisions WHERE id = ?", (int(entity_id),)).fetchone()
            if drow is None:
                return {"ok": False, "error": f"Decision #{entity_id} not found"}
            if drow["artifact_revision"] and artifact_revision and drow["artifact_revision"] != artifact_revision:
                return {
                    "ok": False,
                    "error": f"Stale approval rejected: decision is at revision '{drow['artifact_revision']}', got '{artifact_revision}'",
                }
            conn.execute(
                """
                UPDATE decisions
                SET status = ?, owner_status = ?, approved_by = ?, approved_at = ?, approval_scope = ?
                WHERE id = ?
                """,
                (normalized, normalized, actor, ts, scope or project_id, int(entity_id)),
            )
            project_id = drow["project_id"] or project_id
        elif entity_type == "task":
            trow = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(entity_id),)).fetchone()
            if trow is None:
                return {"ok": False, "error": f"Task #{entity_id} not found"}
            new_task_status = "done" if normalized == "approved" else ("returned" if normalized == "returned" else "blocked")
            conn.execute(
                "UPDATE tasks SET status = ?, accepted_at = ?, updated_at = ? WHERE id = ?",
                (new_task_status, ts if new_task_status == "done" else "", ts, int(entity_id)),
            )
            project_id = trow["project_id"] or project_id

        cur = conn.execute(
            """
            INSERT INTO approvals (
                entity_type, entity_id, project_id, actor, actor_kind, action,
                scope, artifact_ref, artifact_revision, comment, nonce, created_at
            ) VALUES (?, ?, ?, ?, 'owner', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity_type,
                str(entity_id),
                project_id or "default",
                actor,
                normalized,
                scope or project_id or "default",
                artifact_ref,
                artifact_revision,
                comment,
                approval_nonce,
                ts,
            ),
        )
        approval_id = cur.lastrowid
        emit_outbox_event(
            conn,
            "owner.approved",
            entity_type,
            entity_id,
            actor,
            {
                "approval_id": approval_id,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "action": normalized,
                "actor": actor,
                "artifact_ref": artifact_ref,
                "artifact_revision": artifact_revision,
            },
            project_id=project_id or "default",
        )
        state = export_state(conn)
    return {
        "ok": True,
        "approval_id": approval_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "status": normalized,
        "actor": actor,
        "state": state,
    }


def op_orchestrator_lock(
    project_id: str = "default",
    agent_id: str = "fable",
    session_id: str = "",
    action: str = "acquire",
    ttl_seconds: int = 14400,
    force: bool = False,
) -> dict:
    """Acquire, release, or inspect the atomic orchestrator lock (L004)."""
    init_db()
    proj_id = project_id or "default"
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now_s = now_dt.isoformat(timespec="seconds")
    exp_s = (now_dt + datetime.timedelta(seconds=max(60, int(ttl_seconds)))).isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute("DELETE FROM orchestrator_locks WHERE julianday(expires_at) <= julianday(?)", (now_s,))
        current = conn.execute("SELECT * FROM orchestrator_locks WHERE project_id = ?", (proj_id,)).fetchone()
        if action == "status":
            return {"ok": True, "lock": dict(current) if current else None}
        if action == "release":
            if current and (current["holder_agent"] != agent_id or (session_id and current["session_id"] != session_id)) and not force:
                return {"ok": False, "error": f"Orchestrator lock is held by {current['holder_agent']} ({current['session_id']})"}
            conn.execute("DELETE FROM orchestrator_locks WHERE project_id = ?", (proj_id,))
            state = export_state(conn)
            return {"ok": True, "released": True, "project_id": proj_id, "state": state}
        if current and (current["holder_agent"] != agent_id or (session_id and current["session_id"] != session_id)) and not force:
            return {
                "ok": False,
                "error": f"Orchestrator lock for '{proj_id}' is already held by {current['holder_agent']} (session {current['session_id']})",
            }
        resolved_sess = session_id or f"{agent_id}-orch"
        conn.execute(
            """
            INSERT OR REPLACE INTO orchestrator_locks (project_id, holder_agent, session_id, acquired_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (proj_id, agent_id, resolved_sess, now_s, exp_s),
        )
        emit_outbox_event(
            conn,
            "orchestrator.locked",
            "project",
            proj_id,
            agent_id,
            {"project_id": proj_id, "holder_agent": agent_id, "session_id": resolved_sess},
            project_id=proj_id,
            session_id=resolved_sess,
        )
        state = export_state(conn)
    return {"ok": True, "project_id": proj_id, "holder_agent": agent_id, "session_id": resolved_sess, "state": state}


def op_project_create(
    project_id: str,
    name: str,
    description: str = "",
    repo_path: str = "",
    remote_url: str = "",
    status: str = "active",
    hold_reason: str = "",
    policy: dict | None = None,
    shared_channels: list[str] | None = None,
    created_by: str = "human",
) -> dict:
    if not isinstance(project_id, str) or not re.match(r"^[a-zA-Z0-9_.-]+$", project_id.strip()):
        return {"ok": False, "error": "A valid project slug (letters, digits, hyphens, underscores) is required"}
    if status not in ("active", "parked", "on_hold", "archived"):
        return {"ok": False, "error": f"Invalid project status: {status}"}
    init_db()
    ts = now_iso()
    pid = project_id.strip()
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects (
                id, name, description, repo_path, remote_url, status,
                hold_reason, policy_json, shared_channels_json, created_by, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                COALESCE((SELECT created_at FROM projects WHERE id = ?), ?), ?
            )
            """,
            (
                pid,
                name,
                description,
                repo_path,
                remote_url,
                status,
                hold_reason,
                json.dumps(policy or {}),
                json.dumps(shared_channels or []),
                created_by,
                pid,
                ts,
                ts,
            ),
        )
        emit_outbox_event(
            conn,
            "project.upserted",
            "project",
            pid,
            created_by,
            {"project_id": pid, "name": name, "status": status, "repo_path": repo_path},
            project_id=pid,
        )
        state = export_state(conn)
    return {"ok": True, "project_id": pid, "status": status, "state": state}


def op_project_update(
    project_id: str,
    *,
    status: str = "",
    hold_reason: str | None = None,
    repo_path: str | None = None,
    policy: dict | None = None,
    shared_channels: list[str] | None = None,
    actor: str = "human",
) -> dict:
    init_db()
    ts = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Project '{project_id}' not found"}
        new_status = status or row["status"]
        if new_status not in ("active", "parked", "on_hold", "archived"):
            return {"ok": False, "error": f"Invalid project status: {new_status}"}
        new_hold = hold_reason if hold_reason is not None else row["hold_reason"]
        new_repo = repo_path if repo_path is not None else row["repo_path"]
        new_policy = json.dumps(policy) if policy is not None else row["policy_json"]
        new_shared = json.dumps(shared_channels) if shared_channels is not None else row["shared_channels_json"]
        conn.execute(
            """
            UPDATE projects
            SET status = ?, hold_reason = ?, repo_path = ?, policy_json = ?, shared_channels_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, new_hold, new_repo, new_policy, new_shared, ts, project_id),
        )
        emit_outbox_event(
            conn,
            "project.updated",
            "project",
            project_id,
            actor,
            {"project_id": project_id, "status": new_status, "hold_reason": new_hold},
            project_id=project_id,
        )
        state = export_state(conn)
    return {"ok": True, "project_id": project_id, "status": new_status, "state": state}


def op_project_list(include_archived: bool = False) -> dict:
    init_db()
    with get_db() as conn:
        sql = "SELECT * FROM projects"
        if not include_archived:
            sql += " WHERE status != 'archived'"
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY id ASC").fetchall()]
        for r in rows:
            r["members"] = [
                dict(m)
                for m in conn.execute("SELECT * FROM project_members WHERE project_id = ?", (r["id"],)).fetchall()
            ]
    return {"ok": True, "projects": rows}


def op_project_assign_agent(project_id: str, agent_id: str, role: str = "collaborator", responsibilities: str = "") -> dict:
    init_db()
    ts = now_iso()
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO project_members (project_id, agent_id, role, responsibilities, added_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, agent_id, role, responsibilities, ts),
        )
        state = export_state(conn)
    return {"ok": True, "project_id": project_id, "agent_id": agent_id, "role": role, "state": state}


def op_review_submit(
    artifact_ref: str,
    reviewer_agent: str,
    evidence: str,
    *,
    project_id: str = "default",
    task_id: int | None = None,
    artifact_revision: str = "v1",
    author_agent: str = "",
    author_model: str = "",
    reviewer_session_id: str = "",
    reviewer_model: str = "",
    reviewer_model_provenance: str = "",
    verdict: str = "comment",
    preserved_disagreements: str = "",
) -> dict:
    """Record a versioned independent review round without overwriting prior rounds."""
    if not artifact_ref.strip() or not evidence.strip():
        return {"ok": False, "error": "Both artifact_ref and evidence are required"}
    init_db()
    ts = now_iso()
    proj_id = project_id or "default"
    with get_db() as conn:
        srow = None
        if reviewer_session_id:
            srow = conn.execute("SELECT * FROM agent_sessions WHERE session_id = ?", (reviewer_session_id,)).fetchone()
        arow = conn.execute("SELECT * FROM agents WHERE id = ?", (reviewer_agent,)).fetchone()
        resolved_model = reviewer_model or (srow["model_id"] if srow else (arow["model"] if arow else "unknown"))
        resolved_prov = (
            reviewer_model_provenance
            if reviewer_model_provenance in VALID_MODEL_PROVENANCE
            else (srow["model_provenance"] if srow else (arow["model_provenance"] if arow else "unknown"))
        )
        if not author_model and author_agent:
            author_row = conn.execute("SELECT model FROM agents WHERE id = ?", (author_agent,)).fetchone()
            author_model = author_row["model"] if author_row else "unknown"

        prev_round = conn.execute(
            "SELECT COALESCE(MAX(round_number), 0) AS r FROM reviews WHERE artifact_ref = ? AND reviewer_agent = ?",
            (artifact_ref, reviewer_agent),
        ).fetchone()["r"]
        round_num = int(prev_round) + 1
        is_indep = int(
            reviewer_agent != author_agent
            and resolved_model not in ("", "unknown")
            and resolved_model != (author_model or "")
        )
        cur = conn.execute(
            """
            INSERT INTO reviews (
                project_id, task_id, artifact_ref, artifact_revision, round_number,
                author_agent, author_model, reviewer_agent, reviewer_session_id,
                reviewer_model, reviewer_model_provenance, is_independent_model,
                verdict, evidence, preserved_disagreements, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                proj_id,
                task_id,
                artifact_ref,
                artifact_revision,
                round_num,
                author_agent,
                author_model or "unknown",
                reviewer_agent,
                reviewer_session_id,
                resolved_model,
                resolved_prov,
                is_indep,
                verdict,
                evidence,
                preserved_disagreements,
                ts,
                ts,
            ),
        )
        review_id = cur.lastrowid
        emit_outbox_event(
            conn,
            "review.submitted",
            "review",
            review_id,
            reviewer_agent,
            {
                "review_id": review_id,
                "artifact_ref": artifact_ref,
                "artifact_revision": artifact_revision,
                "round_number": round_num,
                "reviewer_agent": reviewer_agent,
                "reviewer_model": resolved_model,
                "is_independent_model": bool(is_indep),
                "verdict": verdict,
            },
            project_id=proj_id,
            session_id=reviewer_session_id,
        )
        state = export_state(conn)
    return {
        "ok": True,
        "review_id": review_id,
        "round_number": round_num,
        "reviewer_model": resolved_model,
        "reviewer_model_provenance": resolved_prov,
        "is_independent_model": bool(is_indep),
        "state": state,
    }


def op_review_respond(
    review_id: int,
    actor: str,
    *,
    author_response: str = "",
    resolution: str = "",
    preserved_disagreements: str | None = None,
    status: str = "",
) -> dict:
    init_db()
    ts = now_iso()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE id = ?", (review_id,)).fetchone()
        if not row:
            return {"ok": False, "error": f"Review #{review_id} not found"}
        new_resp = author_response if author_response != "" else row["author_response"]
        new_res = resolution if resolution != "" else row["resolution"]
        new_dis = preserved_disagreements if preserved_disagreements is not None else row["preserved_disagreements"]
        new_stat = status if status != "" else row["status"]
        conn.execute(
            """
            UPDATE reviews
            SET author_response = ?, resolution = ?, preserved_disagreements = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_resp, new_res, new_dis, new_stat, ts, review_id),
        )
        emit_outbox_event(
            conn,
            "review.updated",
            "review",
            review_id,
            actor,
            {"review_id": review_id, "resolution": new_res, "status": new_stat},
            project_id=row["project_id"] or "default",
        )
        state = export_state(conn)
    return {"ok": True, "review_id": review_id, "resolution": new_res, "status": new_stat, "state": state}


def op_import_history(bundle: dict, *, source_name: str = "agents-home") -> dict:
    """Inert, idempotent historical import. Suppresses all alert/task dispatches."""
    init_db()
    ts = now_iso()
    counts = {"projects": 0, "agents": 0, "tasks": 0, "messages": 0, "decisions": 0, "lessons": 0}
    with get_db() as conn:
        for p in bundle.get("projects", []):
            pid = p["id"]
            exists = conn.execute("SELECT 1 FROM projects WHERE id = ?", (pid,)).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO projects (
                        id, name, description, repo_path, remote_url, status,
                        hold_reason, policy_json, shared_channels_json, created_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        p.get("name", pid),
                        p.get("description", ""),
                        p.get("repo_path", ""),
                        p.get("remote_url", ""),
                        p.get("status", "active"),
                        p.get("hold_reason", ""),
                        json.dumps(p.get("policy", {})),
                        json.dumps(p.get("shared_channels", [])),
                        source_name,
                        p.get("created_at", ts),
                        p.get("updated_at", ts),
                    ),
                )
                counts["projects"] += 1

        for a in bundle.get("agents", []):
            aid = a["id"]
            exists = conn.execute("SELECT 1 FROM agents WHERE id = ?", (aid,)).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO agents (
                        id, model, surface, role, status, last_seen, provider, runtime,
                        model_provenance, capabilities_json, responsibilities, contact_method, availability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        aid,
                        a.get("model", "unknown"),
                        a.get("surface", "cli"),
                        a.get("role", "Collaborator"),
                        a.get("status", "parked"),
                        a.get("last_seen", ts),
                        a.get("provider", "unknown"),
                        a.get("runtime", "unknown"),
                        a.get("model_provenance", "agent_declared"),
                        json.dumps(a.get("capabilities", [])),
                        a.get("responsibilities", ""),
                        a.get("contact_method", "pull"),
                        a.get("availability", "parked"),
                    ),
                )
                counts["agents"] += 1

        for t in bundle.get("tasks", []):
            ext_id = str(t.get("external_id") or t.get("id") or "")
            if ext_id:
                exists = conn.execute("SELECT 1 FROM tasks WHERE external_id = ?", (ext_id,)).fetchone()
                if exists:
                    continue
            conn.execute(
                """
                INSERT INTO tasks (
                    project_id, external_id, title, description, status, priority,
                    owner, created_by, deliverable, is_imported, suppress_dispatch, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
                """,
                (
                    t.get("project_id", "default"),
                    ext_id or None,
                    t["title"],
                    t.get("description", ""),
                    t.get("status", "done"),
                    t.get("priority", "medium"),
                    t.get("owner", ""),
                    t.get("created_by", source_name),
                    t.get("deliverable", ""),
                    t.get("created_at", ts),
                    t.get("updated_at", ts),
                ),
            )
            counts["tasks"] += 1

        for m in bundle.get("messages", []):
            ext_id = str(m.get("external_id") or "")
            if ext_id:
                exists = conn.execute("SELECT 1 FROM messages WHERE external_id = ?", (ext_id,)).fetchone()
                if exists:
                    continue
            conn.execute(
                """
                INSERT INTO messages (
                    project_id, channel, sender, model, model_provenance, content,
                    mentions, pinned, external_id, is_imported, suppress_dispatch, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?)
                """,
                (
                    m.get("project_id", "default"),
                    m.get("channel", "general"),
                    m.get("sender", "unknown"),
                    m.get("model", "unknown"),
                    m.get("model_provenance", "unknown"),
                    m["content"],
                    json.dumps(extract_mentions(m["content"])),
                    1 if m.get("pinned") else 0,
                    ext_id or None,
                    m.get("created_at", ts),
                ),
            )
            counts["messages"] += 1

        for d in bundle.get("decisions", []):
            art_ref = str(d.get("artifact_ref") or d.get("topic") or "")
            if art_ref:
                exists = conn.execute(
                    "SELECT 1 FROM decisions WHERE artifact_ref = ? AND is_imported = 1", (art_ref,)
                ).fetchone()
                if exists:
                    continue
            conn.execute(
                """
                INSERT INTO decisions (
                    project_id, topic, proposal, proposed_by, status, peer_status,
                    owner_status, artifact_ref, is_imported, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (
                    d.get("project_id", "agents-home"),
                    d["topic"],
                    d.get("proposal", ""),
                    d.get("proposed_by", source_name),
                    d.get("status", "approved"),
                    d.get("peer_status", "approved"),
                    d.get("owner_status", "approved"),
                    art_ref,
                    d.get("created_at", ts),
                ),
            )
            counts["decisions"] += 1

        for lsn in bundle.get("lessons", []):
            lid = lsn["id"]
            exists = conn.execute("SELECT 1 FROM lessons WHERE id = ?", (lid,)).fetchone()
            if not exists:
                conn.execute(
                    """
                    INSERT INTO lessons (id, project_id, title, rule_text, enforcement_kind, source_ref, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lid,
                        lsn.get("project_id", "default"),
                        lsn["title"],
                        lsn["rule_text"],
                        lsn.get("enforcement_kind", "enforced"),
                        lsn.get("source_ref", source_name),
                        lsn.get("created_at", ts),
                    ),
                )
                counts["lessons"] += 1

        max_msg_id = int(conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM messages").fetchone()["m"])
        state = export_state(conn)

    # Pre-advance alerts.db cursors so imported records never generate alerts or wakes
    try:
        import alerts as _alerts_mod
        aconn = _alerts_mod.open_db()
        try:
            _alerts_mod.meta_set(aconn, "last_message_id", max_msg_id)
            _alerts_mod.meta_set(aconn, "tasks_ready", "1")
            _alerts_mod.meta_set(aconn, "decisions_ready", "1")
            with get_db() as hconn:
                for trow in hconn.execute("SELECT id, status, owner, updated_at FROM tasks").fetchall():
                    aconn.execute(
                        "INSERT OR REPLACE INTO task_seen (task_id, status, owner, updated_at) VALUES (?, ?, ?, ?)",
                        (trow["id"], trow["status"], trow["owner"] or "", trow["updated_at"]),
                    )
                for drow in hconn.execute("SELECT id, status FROM decisions").fetchall():
                    aconn.execute(
                        "INSERT OR REPLACE INTO decision_seen (decision_id, status) VALUES (?, ?)",
                        (drow["id"], drow["status"]),
                    )
        finally:
            aconn.close()
    except Exception:
        pass

    return {"ok": True, "imported": counts, "max_message_id": max_msg_id, "state": state}


def op_read_events(since_seq: int = 0, project_id: str = "", limit: int = 100) -> dict:
    init_db()
    limit = max(1, min(int(limit or 100), 500))
    since_seq = max(0, int(since_seq or 0))
    with get_db() as conn:
        latest_seq = int(conn.execute("SELECT COALESCE(MAX(seq), 0) AS s FROM outbox_events").fetchone()["s"])
        sql = "SELECT * FROM outbox_events WHERE seq > ?"
        params: list = [since_seq]
        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)
        fetched = [
            dict(r)
            for r in conn.execute(sql + " ORDER BY seq ASC LIMIT ?", (*params, limit + 1)).fetchall()
        ]
        has_more = len(fetched) > limit
        events = fetched[:limit]
        for ev in events:
            try:
                ev["payload"] = json.loads(ev.pop("payload_json", "{}"))
            except ValueError:
                ev["payload"] = {}
        next_seq = events[-1]["seq"] if events else since_seq
    return {
        "ok": True,
        "events": events,
        "next_seq": next_seq,
        "latest_seq": latest_seq,
        "has_more": has_more,
    }


def wait_for_events(since_seq: int = 0, timeout: float = 10.0, project_id: str = "") -> dict:
    """Wait on local event condition / signal file without blind 1s polling loops."""
    res = op_read_events(since_seq=since_seq, project_id=project_id)
    if res["events"] or timeout <= 0:
        return {**res, "timed_out": not bool(res["events"])}
    deadline = time.monotonic() + min(float(timeout), 30.0)
    seq_file = STATE_DIR / ".outbox.seq"
    last_mtime = seq_file.stat().st_mtime_ns if seq_file.exists() else 0
    while time.monotonic() < deadline:
        remaining = max(0.01, min(0.25, deadline - time.monotonic()))
        with _EVENT_COND:
            _EVENT_COND.wait(timeout=remaining)
        cur_mtime = seq_file.stat().st_mtime_ns if seq_file.exists() else 0
        res = op_read_events(since_seq=since_seq, project_id=project_id)
        if res["events"]:
            return {**res, "timed_out": False}
        last_mtime = cur_mtime
    return {**op_read_events(since_seq=since_seq, project_id=project_id), "timed_out": True}


def op_kv_set(key: str, value: str, agent_id: str, *, project_id: str = "default", session_id: str = "") -> dict:
    init_db()
    ts = now_iso()
    proj_id = project_id or "default"
    with get_db() as conn:
        touch_agent(conn, agent_id, session_id=session_id, preserve_primary_model=True)
        conn.execute(
            "INSERT OR REPLACE INTO kv_store (key, project_id, value, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)",
            (key, proj_id, value, agent_id, ts),
        )
        emit_outbox_event(
            conn,
            "kv.updated",
            "kv",
            key,
            agent_id,
            {"key": key, "project_id": proj_id, "updated_by": agent_id},
            project_id=proj_id,
            session_id=session_id,
        )
        state = export_state(conn)
    return {"ok": True, "key": key, "value": value, "project_id": proj_id, "state": state}


# ============================================================================
# Web UI HTML (Designed for Human & Google Chrome Agent / Argon Interaction)
# ============================================================================

DASHBOARD_HTML = (CODE_DIR / "assets" / "dashboard.html").read_text(encoding="utf-8")


class CollabHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        # Quiet logging to avoid cluttering terminal
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _discard_request_body(self) -> None:
        """Consume a declared request body before sending an early error.

        Closing a socket while bytes are still unread in its receive queue makes
        Windows abort the connection instead of closing it gracefully, and that
        abort discards the error response a client has not read yet. Reading the
        declared body first keeps the response deliverable. Only a plausible
        length is drained: a malformed or oversized declaration is answered
        without reading, so a client that lied about its length can still see the
        connection end abruptly rather than wait on a body that will not arrive.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            return
        if length <= 0 or length > MAX_REQUEST_BYTES:
            return
        try:
            self.connection.settimeout(BODY_DRAIN_TIMEOUT_SECONDS)
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    return
                remaining -= len(chunk)
        except (OSError, ValueError):
            # A client that never finishes its body must not hold this thread.
            return

    def do_OPTIONS(self) -> None:
        self._discard_request_body()
        self._send_json({"ok": False, "error": "Cross-origin access is disabled"}, 403)

    def _allowed_request(self) -> bool:
        try:
            host = urllib.parse.urlsplit("http://" + self.headers.get("Host", ""))
            allowed = host.hostname in ("127.0.0.1", "localhost", "::1") and host.port == self.server.server_port
            origin = self.headers.get("Origin")
            if origin:
                source = urllib.parse.urlsplit(origin)
                allowed = allowed and source.scheme == "http" and source.hostname == host.hostname and source.port == host.port
        except ValueError:
            allowed = False
        if not allowed:
            self._discard_request_body()
            self._send_json({"ok": False, "error": "Only requests from this local dashboard are allowed"}, 403)
        return allowed

    def do_GET(self) -> None:
        if not self._allowed_request():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            page_html = DASHBOARD_HTML.replace("__ACH_LOCAL_OWNER_TOKEN__", get_owner_token())
            raw = page_html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(raw)
            return

        if parsed.path == "/favicon.ico":
            ico_path = CODE_DIR / "assets" / "app-icon.ico"
            raw = ico_path.read_bytes() if ico_path.is_file() else b""
            self.send_response(200 if raw else 204)
            if raw:
                self.send_header("Content-Type", "image/x-icon")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)
            return

        if parsed.path == "/api/state":
            init_db()
            qs = urllib.parse.parse_qs(parsed.query)
            project_id = qs.get("project", [""])[0]
            with get_db() as conn:
                state = export_state(conn, project_id=project_id)
            self._send_json(state)
            return

        if parsed.path == "/api/projects":
            qs = urllib.parse.parse_qs(parsed.query)
            include_archived = qs.get("include_archived", ["0"])[0] in ("1", "true")
            self._send_json(op_project_list(include_archived=include_archived))
            return

        if parsed.path == "/api/events":
            qs = urllib.parse.parse_qs(parsed.query)
            last_id_hdr = self.headers.get("Last-Event-ID", "").strip()
            try:
                since_seq = int(qs.get("since_seq", [last_id_hdr or "0"])[0])
            except ValueError:
                since_seq = 0
            project_id = qs.get("project", [""])[0]
            try:
                timeout = float(qs.get("timeout", ["0"])[0])
            except ValueError:
                timeout = 0.0
            wants_sse = (
                "text/event-stream" in self.headers.get("Accept", "")
                or qs.get("stream", ["0"])[0] in ("1", "true")
            )
            res = wait_for_events(since_seq=since_seq, timeout=timeout, project_id=project_id)
            if wants_sse:
                chunks = [": ok\n\n"]
                for ev in res["events"]:
                    chunks.append(
                        f"id: {ev['seq']}\nevent: {ev['event_type']}\ndata: {json.dumps(ev)}\n\n"
                    )
                raw = "".join(chunks).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self._send_json(res)
            return

        if parsed.path == "/api/health":
            self._send_json({"ok": True, "service": "agent-collab-hub", "time": now_iso(),
                             "workspace": str(BASE_DIR), "pid": os.getpid()})
            return

        self._send_json({"ok": False, "error": "Not found"}, status=404)

    def do_POST(self) -> None:
        try:
            self._post_request()
        except (ValueError, TypeError, KeyError, OverflowError):
            self._send_json({"ok": False, "error": "Invalid request arguments"}, 400)
        except sqlite3.Error:
            self._send_json({"ok": False, "error": "The local board database is temporarily unavailable"}, 503)

    def _post_request(self) -> None:
        if not self._allowed_request():
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._discard_request_body()
            self._send_json({"ok": False, "error": "Content-Type must be application/json"}, 415)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json({"ok": False, "error": "Invalid content length"}, 400)
            return
        if not 0 <= length <= MAX_REQUEST_BYTES:
            self._send_json({"ok": False, "error": "Request exceeds 1 MiB limit"}, 413)
            return
        try:
            body_raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            body = json.loads(body_raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "Invalid JSON"}, status=400)
            return

        if not isinstance(body, dict):
            self._send_json({"ok": False, "error": "JSON body must be an object"}, 400)
            return

        text_fields = {"agent_id", "sender", "content", "channel", "model", "surface", "role",
                       "status", "title", "description", "created_by", "priority", "owner",
                       "deliverable", "filepath", "reason", "key", "value", "topic", "proposal",
                       "vote", "comment", "session_id", "project_id", "provider", "runtime",
                       "model_provenance", "owner_token", "waiting_on", "blocked_by",
                       "artifact_ref", "artifact_revision", "verdict", "evidence",
                       "author_response", "resolution", "preserved_disagreements",
                       "entity_type", "action", "actor", "scope", "nonce", "name",
                       "repo_path", "remote_url", "hold_reason"}
        for key in body.keys() & text_fields:
            if not isinstance(body[key], str):
                self._send_json({"ok": False, "error": f"{key} must be a string"}, 400)
                return
        for key in body.keys() & {"task_id", "decision_id", "review_id", "ttl", "ttl_seconds", "reply_to"}:
            if key in ("reply_to", "task_id") and body[key] is None:
                continue
            if type(body[key]) is not int or body[key] <= 0:
                self._send_json({"ok": False, "error": f"{key} must be a positive integer"}, 400)
                return
        for key in body.keys() & {"force", "announce", "pin", "require_deliverable"}:
            if not isinstance(body[key], bool):
                self._send_json({"ok": False, "error": f"{key} must be a boolean"}, 400)
                return

        path = urllib.parse.urlparse(self.path).path

        if path == "/api/join":
            res = op_join(
                agent_id=body.get("agent_id", "unknown"),
                model=body.get("model", "unknown"),
                surface=body.get("surface", "http"),
                role=body.get("role", "Collaborator"),
                status=body.get("status", "online"),
                announce=bool(body.get("announce", True)),
                session_id=body.get("session_id", ""),
                provider=body.get("provider", ""),
                runtime=body.get("runtime", ""),
                model_provenance=body.get("model_provenance", ""),
                capabilities=body.get("capabilities"),
                tools=body.get("tools"),
                limitations=body.get("limitations"),
                responsibilities=body.get("responsibilities", ""),
                contact_method=body.get("contact_method", ""),
                availability=body.get("availability", ""),
                project_id=body.get("project_id", "default"),
            )
            self._send_json(res)
            return

        if path == "/api/post":
            res = op_post(
                sender=body.get("sender", "anonymous"),
                content=body.get("content", ""),
                channel=body.get("channel", "general"),
                reply_to=body.get("reply_to"),
                pin=bool(body.get("pin", False)),
                model=body.get("model", ""),
                session_id=body.get("session_id", ""),
                project_id=body.get("project_id", "default"),
                provider=body.get("provider", ""),
                runtime=body.get("runtime", ""),
                model_provenance=body.get("model_provenance", ""),
                owner_token=body.get("owner_token", ""),
            )
            self._send_json(res, 403 if res.get("error_code") == UNAUTHORIZED_CODE else 200)
            return

        if path == "/api/task/add":
            res = op_task_add(
                created_by=body.get("created_by", "anonymous"),
                title=body.get("title", "Untitled Task"),
                description=body.get("description", ""),
                priority=body.get("priority", "medium"),
                owner=body.get("owner", ""),
                project_id=body.get("project_id", "default"),
                session_id=body.get("session_id", ""),
                force=bool(body.get("force", False)),
            )
            self._send_json(res)
            return

        if path == "/api/task/claim":
            res = op_task_claim(
                task_id=int(body.get("task_id", 0)),
                agent_id=body.get("agent_id", "anonymous"),
                force=bool(body.get("force", False)),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res)
            return

        if path == "/api/task/update":
            res = op_task_update(
                task_id=int(body.get("task_id", 0)),
                agent_id=body.get("agent_id", "anonymous"),
                status=body.get("status", ""),
                deliverable=body.get("deliverable", ""),
                owner=body.get("owner", ""),
                force=bool(body.get("force", False)),
                waiting_on=body.get("waiting_on", ""),
                blocked_by=body.get("blocked_by", ""),
                session_id=body.get("session_id", ""),
                require_deliverable=bool(body.get("require_deliverable", False)),
            )
            self._send_json(res)
            return

        if path == "/api/lock":
            res = op_lock(
                filepath=body.get("filepath", ""),
                agent_id=body.get("agent_id", "anonymous"),
                reason=body.get("reason", "editing"),
                ttl_seconds=body.get("ttl", body.get("ttl_seconds", 1800)),
                project_id=body.get("project_id", "default"),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res)
            return

        if path == "/api/unlock":
            res = op_unlock(
                filepath=body.get("filepath", ""),
                agent_id=body.get("agent_id", "anonymous"),
                force=bool(body.get("force", False)),
                project_id=body.get("project_id", "default"),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res)
            return

        if path == "/api/propose":
            res = op_propose(
                agent_id=body.get("agent_id", "anonymous"),
                topic=body.get("topic", ""),
                proposal=body.get("proposal", ""),
                project_id=body.get("project_id", "default"),
                artifact_ref=body.get("artifact_ref", ""),
                artifact_revision=body.get("artifact_revision", ""),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res)
            return

        if path == "/api/vote":
            res = op_vote(
                decision_id=int(body.get("decision_id", 0)),
                agent_id=body.get("agent_id", "anonymous"),
                vote=body.get("vote", "approve"),
                comment=body.get("comment", ""),
                status=body.get("status", ""),
                owner_token=body.get("owner_token", ""),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res, 403 if res.get("error_code") == UNAUTHORIZED_CODE else 200)
            return

        if path == "/api/approve":
            res = op_owner_approve(
                entity_type=body.get("entity_type", "decision"),
                entity_id=body.get("entity_id", body.get("decision_id", 0)),
                action=body.get("action", "approve"),
                owner_token=body.get("owner_token", ""),
                actor=body.get("actor", "human-director"),
                project_id=body.get("project_id", "default"),
                scope=body.get("scope", ""),
                artifact_ref=body.get("artifact_ref", ""),
                artifact_revision=body.get("artifact_revision", ""),
                comment=body.get("comment", ""),
                nonce=body.get("nonce", ""),
            )
            self._send_json(res, 403 if res.get("error_code") == UNAUTHORIZED_CODE else 200)
            return

        if path == "/api/project/create":
            res = op_project_create(
                project_id=body.get("project_id", ""),
                name=body.get("name", ""),
                description=body.get("description", ""),
                repo_path=body.get("repo_path", ""),
                remote_url=body.get("remote_url", ""),
                status=body.get("status", "active"),
                hold_reason=body.get("hold_reason", ""),
                policy=body.get("policy"),
                shared_channels=body.get("shared_channels"),
                created_by=body.get("created_by", "human"),
            )
            self._send_json(res)
            return

        if path == "/api/project/update":
            res = op_project_update(
                project_id=body.get("project_id", ""),
                status=body.get("status", ""),
                hold_reason=body.get("hold_reason"),
                repo_path=body.get("repo_path"),
                policy=body.get("policy"),
                shared_channels=body.get("shared_channels"),
                actor=body.get("actor", "human"),
            )
            self._send_json(res)
            return

        if path == "/api/review/submit":
            res = op_review_submit(
                artifact_ref=body.get("artifact_ref", ""),
                reviewer_agent=body.get("reviewer_agent", body.get("agent_id", "")),
                evidence=body.get("evidence", ""),
                project_id=body.get("project_id", "default"),
                task_id=body.get("task_id"),
                artifact_revision=body.get("artifact_revision", "v1"),
                author_agent=body.get("author_agent", ""),
                author_model=body.get("author_model", ""),
                reviewer_session_id=body.get("session_id", ""),
                reviewer_model=body.get("model", ""),
                reviewer_model_provenance=body.get("model_provenance", ""),
                verdict=body.get("verdict", "comment"),
                preserved_disagreements=body.get("preserved_disagreements", ""),
            )
            self._send_json(res)
            return

        if path == "/api/review/respond":
            res = op_review_respond(
                review_id=int(body.get("review_id", 0)),
                actor=body.get("actor", body.get("agent_id", "")),
                author_response=body.get("author_response", ""),
                resolution=body.get("resolution", ""),
                preserved_disagreements=body.get("preserved_disagreements"),
                status=body.get("status", ""),
            )
            self._send_json(res)
            return

        if path == "/api/import":
            res = op_import_history(
                bundle=body.get("bundle", {}),
                source_name=body.get("source_name", "agents-home"),
            )
            self._send_json(res)
            return

        if path == "/api/kv":
            res = op_kv_set(
                key=body.get("key", ""),
                value=body.get("value", ""),
                agent_id=body.get("agent_id", "anonymous"),
                project_id=body.get("project_id", "default"),
                session_id=body.get("session_id", ""),
            )
            self._send_json(res)
            return

        self._send_json({"ok": False, "error": f"Unknown endpoint {path}"}, status=404)


# ============================================================================
# CLI Interface
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-Agent Collaboration Hub CLI")
    sub = parser.add_subparsers(dest="cmd")

    # init
    sub.add_parser("init", help="Initialize database and sync BOARD.md")

    # join
    p_join = sub.add_parser("join", help="Register or update agent presence")
    p_join.add_argument("--id", required=True, help="Agent ID (e.g., opus-5.5-high, codex, argon-antigravity, argon-chrome)")
    p_join.add_argument("--model", default="unknown", help="Model name (e.g., 'Claude Opus 5.5 High', 'OpenAI Codex', 'Gemini 4 Argon High')")
    p_join.add_argument("--surface", default="cli", help="Surface (antigravity, codex-cli, google-chrome)")
    p_join.add_argument("--role", default="Collaborator", help="Role description")
    p_join.add_argument("--status", default="online", help="Current status")
    p_join.add_argument("--quiet", action="store_true", help="Do not post join announcement")

    # post
    p_post = sub.add_parser("post", help="Post a message to the collaboration board")
    p_post.add_argument("--from", dest="sender", required=True, help="Sender agent ID")
    p_post.add_argument("--msg", required=True, help="Message content (Markdown supported)")
    p_post.add_argument("--channel", default="general", help="Channel name (general, tasks, architecture, handoffs, reviews)")
    p_post.add_argument("--reply-to", type=int, default=None, help="Message ID being replied to")
    p_post.add_argument("--model", default="", help="Optional model badge override")
    p_post.add_argument("--pin", action="store_true", help="Pin this message")

    # read
    p_read = sub.add_parser("read", help="Read messages from the board")
    p_read.add_argument("--channel", default="", help="Filter by channel")
    p_read.add_argument("--since", type=int, default=0, help="Only messages with ID > since")
    p_read.add_argument("--limit", type=int, default=25, help="Max messages to return")
    p_read.add_argument("--mentions", default="", help="Filter messages mentioning agent ID")
    p_read.add_argument("--json", action="store_true", help="Output JSON")

    # poll
    p_poll = sub.add_parser("poll", help="Wait for new messages to arrive")
    p_poll.add_argument("--for", dest="agent_id", default="", help="Agent ID polling")
    p_poll.add_argument("--since", type=int, default=-1, help="Message ID baseline (-1 = current latest)")
    p_poll.add_argument("--channel", default="", help="Optional channel filter")
    p_poll.add_argument("--timeout", type=int, default=30, help="Seconds to wait before returning")

    # task
    p_task = sub.add_parser("task", help="Manage shared tasks")
    task_sub = p_task.add_subparsers(dest="task_cmd")

    p_t_add = task_sub.add_parser("add", help="Create a new task")
    p_t_add.add_argument("--from", dest="created_by", required=True, help="Creator agent ID")
    p_t_add.add_argument("--title", required=True, help="Task title")
    p_t_add.add_argument("--desc", default="", help="Task description")
    p_t_add.add_argument("--priority", default="medium", choices=["high", "medium", "low"])
    p_t_add.add_argument("--assign", default="", help="Optional initial owner")

    p_t_claim = task_sub.add_parser("claim", help="Claim a task")
    p_t_claim.add_argument("task_id", type=int)
    p_t_claim.add_argument("--agent", required=True, help="Agent claiming the task")
    p_t_claim.add_argument("--force", action="store_true", help="Override existing owner")

    p_t_upd = task_sub.add_parser("update", help="Update a task")
    p_t_upd.add_argument("task_id", type=int)
    p_t_upd.add_argument("--agent", required=True, help="Agent updating the task")
    p_t_upd.add_argument("--status", default="", choices=["", "todo", "in_progress", "review", "done", "blocked"])
    p_t_upd.add_argument("--deliverable", default="", help="Deliverable path or completion note")
    p_t_upd.add_argument("--assign", default="", help="Reassign owner")
    p_t_upd.add_argument("--force", action="store_true", help="Override existing owner")

    p_t_list = task_sub.add_parser("list", help="List tasks")
    p_t_list.add_argument("--status", default="", help="Filter by status")
    p_t_list.add_argument("--json", action="store_true")

    # lock / unlock / locks
    p_lock = sub.add_parser("lock", help="Acquire an advisory lock on a file before editing")
    p_lock.add_argument("filepath", help="Relative path to lock")
    p_lock.add_argument("--agent", required=True, help="Agent ID")
    p_lock.add_argument("--reason", default="editing", help="Reason for lock")
    p_lock.add_argument("--ttl", type=int, default=1800, help="Lock TTL in seconds")

    p_unlock = sub.add_parser("unlock", help="Release a file lock")
    p_unlock.add_argument("filepath", help="Relative path to unlock")
    p_unlock.add_argument("--agent", required=True, help="Agent ID")
    p_unlock.add_argument("--force", action="store_true")

    sub.add_parser("locks", help="List active file locks")

    # propose / vote
    p_prop = sub.add_parser("propose", help="Create an architectural proposal for multi-agent voting")
    p_prop.add_argument("--from", dest="agent_id", required=True)
    p_prop.add_argument("--topic", required=True)
    p_prop.add_argument("--proposal", required=True)

    p_vote = sub.add_parser("vote", help="Vote on a proposal")
    p_vote.add_argument("decision_id", type=int)
    p_vote.add_argument("--agent", required=True)
    p_vote.add_argument("--vote", required=True, choices=["approve", "reject", "abstain"])
    p_vote.add_argument("--comment", default="")
    p_vote.add_argument("--status", default="", choices=["", "open", "approved", "rejected"])

    # kv
    p_kv = sub.add_parser("kv", help="Shared key-value memory")
    kv_sub = p_kv.add_subparsers(dest="kv_cmd")
    p_kv_set = kv_sub.add_parser("set")
    p_kv_set.add_argument("key")
    p_kv_set.add_argument("value")
    p_kv_set.add_argument("--agent", required=True)
    p_kv_get = kv_sub.add_parser("get")
    p_kv_get.add_argument("key", nargs="?", default="")

    # status
    sub.add_parser("status", help="Show full board summary")

    # serve
    p_serve = sub.add_parser("serve", help="Run live HTTP & Chrome Web UI server")
    p_serve.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost"])
    p_serve.add_argument("--port", type=int, default=8765)

    args = parser.parse_args()

    if args.cmd == "init":
        init_db()
        with get_db() as conn:
            export_state(conn)
        print(f"Initialized Collaboration Hub at {DB_PATH} and synced {BOARD_MD_PATH}")
        return

    if args.cmd == "join":
        res = op_join(args.id, args.model, args.surface, args.role, args.status, announce=not args.quiet)
        print(f"[OK] Agent '{args.id}' ({args.model} on {args.surface}) checked in.")
        return

    if args.cmd == "post":
        res = op_post(args.sender, args.msg, args.channel, args.reply_to, args.pin, args.model)
        print(f"[OK] Posted message #{res['message_id']} to #{args.channel}")
        return

    if args.cmd == "read":
        init_db()
        with get_db() as conn:
            sql = "SELECT * FROM messages WHERE id > ?"
            params: list = [args.since]
            if args.channel:
                sql += " AND channel = ?"
                params.append(args.channel.lstrip("#"))
            if args.mentions:
                sql += " AND (mentions LIKE ? OR content LIKE ?)"
                params.extend([f'%"{args.mentions}"%', f"%@{args.mentions}%"])
            sql += " ORDER BY id ASC"
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            if args.limit and len(rows) > args.limit:
                rows = rows[-args.limit:]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            if not rows:
                print("(No matching messages)")
            for m in rows:
                rep = f" (reply to #{m['reply_to']})" if m.get("reply_to") else ""
                mod = f" [{m['model']}]" if m.get("model") else ""
                print(f"[#{m['id']} | #{m['channel']} | {m['created_at']}] {m['sender']}{mod}{rep}:\n  {m['content']}\n")
        return

    if args.cmd == "poll":
        init_db()
        with get_db() as conn:
            if args.agent_id:
                touch_agent(conn, args.agent_id, status="listening for messages")
                export_state(conn)
            if args.since < 0:
                row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM messages").fetchone()
                baseline = row["max_id"]
            else:
                baseline = args.since

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            with get_db() as conn:
                sql = "SELECT * FROM messages WHERE id > ?"
                params = [baseline]
                if args.channel:
                    sql += " AND channel = ?"
                    params.append(args.channel.lstrip("#"))
                if args.agent_id:
                    sql += " AND sender != ?"
                    params.append(args.agent_id)
                sql += " ORDER BY id ASC"
                rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
                if rows:
                    for m in rows:
                        print(f"[#{m['id']} | #{m['channel']} | {m['created_at']}] {m['sender']} [{m['model']}]:\n  {m['content']}\n")
                    return
            time.sleep(1.0)
        print(f"(No new messages after {args.timeout}s; baseline ID remains {baseline})")
        return

    if args.cmd == "task":
        if args.task_cmd == "add":
            res = op_task_add(args.created_by, args.title, args.desc, args.priority, args.assign)
            print(f"[OK] Created Task #{res['task_id']}: {args.title}")
            return
        if args.task_cmd == "claim":
            res = op_task_claim(args.task_id, args.agent, args.force)
            if not res["ok"]:
                print(f"[ERROR] {res['error']}", file=sys.stderr)
                sys.exit(1)
            print(f"[OK] Task #{args.task_id} claimed by {args.agent}")
            return
        if args.task_cmd == "update":
            res = op_task_update(args.task_id, args.agent, args.status, args.deliverable, args.assign, args.force)
            if not res["ok"]:
                print(f"[ERROR] {res['error']}", file=sys.stderr)
                sys.exit(1)
            print(f"[OK] Task #{args.task_id} updated -> {res['status']}")
            return
        if args.task_cmd == "list":
            init_db()
            with get_db() as conn:
                sql = "SELECT * FROM tasks"
                params = []
                if args.status:
                    sql += " WHERE status = ?"
                    params.append(args.status)
                sql += " ORDER BY id ASC"
                rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                for t in rows:
                    print(f"#{t['id']} [{t['status'].upper()}] ({t['priority']}) {t['title']} | Owner: {t['owner'] or 'unclaimed'} | {t['deliverable']}")
            return

    if args.cmd == "lock":
        res = op_lock(args.filepath, args.agent, args.reason, args.ttl)
        if not res["ok"]:
            print(f"[LOCK CONFLICT] {res['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Locked '{args.filepath}' for {args.agent}")
        return

    if args.cmd == "unlock":
        res = op_unlock(args.filepath, args.agent, args.force)
        if not res["ok"]:
            print(f"[ERROR] {res['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Unlocked '{args.filepath}'")
        return

    if args.cmd == "locks":
        init_db()
        with get_db() as conn:
            cleanup_expired_locks(conn)
            rows = [dict(r) for r in conn.execute("SELECT * FROM locks").fetchall()]
        if not rows:
            print("(No active file locks)")
        for r in rows:
            print(f"- {r['filepath']} locked by {r['owner']} ({r['reason']}) until {r['expires_at']}")
        return

    if args.cmd == "propose":
        res = op_propose(args.agent_id, args.topic, args.proposal)
        print(f"[OK] Created Proposal #{res['decision_id']}: {args.topic}")
        return

    if args.cmd == "vote":
        res = op_vote(args.decision_id, args.agent, args.vote, args.comment, args.status)
        if not res["ok"]:
            print(f"[ERROR] {res['error']}", file=sys.stderr)
            sys.exit(1)
        print(f"[OK] Recorded vote '{args.vote}' by {args.agent} on Decision #{args.decision_id}")
        return

    if args.cmd == "kv":
        init_db()
        if args.kv_cmd == "set":
            op_kv_set(args.key, args.value, args.agent)
            print(f"[OK] Set {args.key} = {args.value}")
            return
        if args.kv_cmd == "get":
            with get_db() as conn:
                if args.key:
                    row = conn.execute("SELECT * FROM kv_store WHERE key = ?", (args.key,)).fetchone()
                    if row:
                        print(row["value"])
                else:
                    for r in conn.execute("SELECT * FROM kv_store ORDER BY key ASC").fetchall():
                        print(f"{r['key']} = {r['value']} (by {r['updated_by']})")
            return

    if args.cmd in ("status", None):
        init_db()
        with get_db() as conn:
            state = export_state(conn)
        print(render_board_markdown(state))
        return

    if args.cmd == "serve":
        init_db()
        with get_db() as conn:
            export_state(conn)
        server = ThreadingHTTPServer((args.host, args.port), CollabHTTPRequestHandler)
        print(f"Collaboration Hub Web UI & API listening on http://{args.host}:{args.port}")
        sys.stdout.flush()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        return


if __name__ == "__main__":
    main()
