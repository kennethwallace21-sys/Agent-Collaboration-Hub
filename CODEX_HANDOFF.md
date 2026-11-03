# Agent Collaboration Hub (ACH) - Codex Driver Handoff

## Current operating scope: November 2, 2026

This section supersedes the migration and runtime statements in the historical November 1 handoff below. The owner's new direction is to move **only Agent Collab Hub project conversations** to ACH and remove unrelated preloaded content. It is not authorization to move any other project's agents, tasks, or workflows.

- Live dashboard/API: `http://127.0.0.1:8765`, restored through the detached desktop launcher. Health, state, and dashboard returned HTTP 200 on November 2. Startup logs and the managed process record now live under the workspace's `state/` directory. This is a checked-at-time status, not an uptime guarantee or a Windows login service.
- Installed app: `C:\Users\kenne\AppData\Local\ACH\app`.
- Private workspace: `C:\Users\kenne\AppData\Local\ACH\workspace`.
- One project remains: **Agent Collab Hub**, API `project_id: default`. Use this for ACH posts and tasks; the former `agents-home` project ID is no longer present.
- Ten ACH history records were preserved with their original message IDs. Message #1254 contains only the explicitly labeled ACH excerpt of a mixed-project reply. Review links #1253 -> #1367 -> #1368 -> #1369 are intact. ACH task #167 remains open; #168 records this cleanup and service restoration.
- Removed from the active ACH workspace: unrelated imported projects and all 166 imported tasks, unrelated messages, demo posts, imported audits/lessons, stale sessions, and old alert contents. This is not merely a UI filter.
- Original `C:\Users\kenne\OneDrive\Desktop\Agents Home Folder` is unchanged by this cleanup and remains in use for unrelated projects. Do not replay the full migration/import script or execute the historical full-cutover checklist below without new owner direction.
- Recovery backup of the previous installed app and complete workspace: `C:\Users\kenne\AppData\Local\ACH\backups\20261102-ach-only-cutover`. Its rehearsal and applied reports record the exact retained IDs and counts.
- Kimi's UI changes were preserved and deployed. Independently rerun on Windows: 13/13 Node behavior tests; 121 Python tests OK (2 skipped); 49/49 isolated MCP checks. Served HTML contains the new roster chips, day dividers, visibility catch-up, and 60-second safety timer. The Apple redesign was not installed. A live interactive browser inspection was unavailable; HTTP and automated DOM checks were used.
- Kimi's owner-supplied delivery is relayed by Codex as #1373, threaded under #1368, not impersonated as a new Kimi post. Original text: `shared/kimi-delivery-2026-11-02.txt`. Pinned scope/connection notice: #1374.
- No global client settings, paid consultations, or external wakes were enabled. Alert delivery remains persistently paused. Historical contributor roster entries do not assert current model or online presence.

For direct CLI access, explicitly select the private workspace (do not initialize a second board in the source checkout):

```powershell
$env:COLLAB_WORKSPACE = "$env:LOCALAPPDATA\ACH\workspace"
$env:COLLAB_DISABLE_EXTERNAL_DELIVERY = "1"
$env:COLLAB_ALERTS_AUTOSTART = "0"
$env:COLLAB_ALLOW_CONSULTS = "0"
py -3.12 "$env:LOCALAPPDATA\ACH\app\collab.py" read --limit 20
# The local CLI still works if the HTTP dashboard is stopped.
py -3.12 "$env:LOCALAPPDATA\ACH\app\scripts\desktop.py" start --workspace "$env:LOCALAPPDATA\ACH\workspace"
```

## Historical handoff (November 1, retained for provenance)

**Date**: November 1, 2026  
**Target Driver**: OpenAI Codex  
**Repo**: `https://github.com/kwallace12-chwy/Agent-Collaboration-Hub`  
**Working Branch**: `feat/ach-v3-foundation`  
**Owner**: Kenny Wallace (`human` / `human-director`)  

---

## 1. Executive Summary & Current Operating State

Codex, you are taking the driver's seat for **Agent Collaboration Hub (ACH)**.

The project mission is to replace Kenny's existing file-based **Agents Home Folder** (`C:\Users\kenne\OneDrive\Desktop\Agents Home Folder`) with a fast, reliable, consumer-grade, project-based multi-agent collaboration application.

### Current Verified Status (All 5 Implementation Slices Complete)
1. **Repository & Architecture**:
   - Branch `feat/ach-v3-foundation` contains the full v3 architecture (`projects`, `project_members`, `agent_sessions`, `outbox_events`, `task_events`, `reviews`, `approvals`, `orchestrator_locks`, and `lessons` SQLite tables).
   - All **120 / 120 unit tests pass** (`py -3.12 -m unittest discover -s tests -p "test_*.py"`).
   - All **49 / 49 MCP smoke tests pass** (`py -3.12 tests/smoke_mcp.py mcp_server.py --cases tests/v2_cases.json`).
2. **Windows Desktop Staging**:
   - Staged to `%LOCALAPPDATA%\ACH\app` and `%LOCALAPPDATA%\ACH\workspace` via `scripts/prepare_windows.ps1`.
   - Windows command-line quoting is hardened against `cmd.exe` metacharacters (`&`, spaces).
3. **Migration Rehearsal**:
   - Executed via `scripts/migrate_agents_home.py --verify-rehearsal` against `C:\Users\kenne\OneDrive\Desktop\Agents Home Folder`.
   - Imported **5 projects**, **5 agent seats**, **166 tasks**, **1,361 messages**, **2 audits**, and **25 lessons**.
   - Two-pass idempotency verified (0 duplicates on Pass 2).
   - Zero historical wakes verified (`alerts.scan()` generated 0 alerts).
4. **Live Dashboard Running Right Now**:
   - Live staged server is running on **`http://127.0.0.1:8765`** against `%LOCALAPPDATA%\ACH\workspace`.
   - Safe sandbox mode enabled: `COLLAB_DISABLE_EXTERNAL_DELIVERY=1` and `COLLAB_ALERTS_AUTOSTART=0`.
   - Verified in real Chrome at 1440x900 via `chrome-devtools-mcp` with **0 console errors or warnings**.
   - Verified 3-column Live-Chat-First layout: 80-message DOM windowing, `#chat-search` instant filter across all 1,361 messages, `@mention` composer with pre-flight guardrails, and project switching.

---

## 2. Critical Safety Boundaries & Active Rules

As driver, you must strictly follow these rules:

1. **DO NOT MOVE LIVE AGENTS YET**:
   - Per Kenny's directive: *"do not have agents move there until you've fully tested it out."*
   - Keep `COLLAB_DISABLE_EXTERNAL_DELIVERY=1` on the staged server.
   - Do **NOT** modify Kenny's global client configuration files (`~/.claude/settings.json`, `~/.codex/config.json`, etc.).
   - `C:\Users\kenne\OneDrive\Desktop\Agents Home Folder` must remain 100% intact and untouched.
2. **STRICT EM-DASH BAN (`U+2014`)**:
   - Never output or commit em dashes (`—`). Use standard hyphens (`-`), colons, or parentheses. Both `collab.py` and the UI enforce this.
3. **FORBIDDEN PATHS**:
   - Never reference or create paths pointing to `D:\va`.
4. **PROJECT HOLDS**:
   - `virtual-assistant` and `hcm-platform` are currently `on_hold`. Creating active tasks under these projects is blocked by policy.

---

## 3. Keeping Kimi Straight (Dual-Context Management)

Kenny wants **Kimi** (Moonshot AI K3 via Fireworks AI in Cline) to inspect ACH and read the code.

**Crucial Context**:
- In `Agents Home Folder`, **Fable** is actively orchestrating tasks for the `virtual-assistant` project and recently assigned T169-T173 to Kimi in `inbox\kimi`.
- When assigning work to Kimi for **ACH**, Kimi must NOT get confused between Fable's VA queue and ACH review.

### How to Keep Kimi Straight
1. **Explicit Project Headers**: Always prefix Kimi's assignments with:
   `[PROJECT: AGENT-COLLAB-HUB (ACH)]` and `[ORCHESTRATOR: KENNY / CODEX]`.
2. **Explicit Workspace Path**: Direct Kimi strictly to `C:\Users\kenne\OneDrive\Desktop\Agent Collab Hub`.
3. **No Cross-Posting**: Tell Kimi: *"Do NOT post updates to Agents Home Folder or modify T169-T173."*
4. **Scope**: Kimi is read-only on the codebase, reviewing architecture, test coverage, and the live UI at `http://127.0.0.1:8765`.

---

## 4. Key Architecture & File Map

| File | Purpose & Responsibilities |
| :--- | :--- |
| `collab.py` | SQLite engine, table schemas, forward cursors (`op_read_messages`), HTTP server (`/api/*`), lock management, token authentication, guardrails. |
| `assets/dashboard.html` | Production UI: 100% offline vanilla JS/CSS, 3-column Live-Chat-First layout, dark/light theme, 80-message windowing, instant search, pre-flight composer guardrails. |
| `mcp_server.py` | Stdio MCP server exposing 25+ tools (`t_read`, `t_post`, `collab_project_*`, `collab_review_*`, `collab_lock_*`, `collab_owner_approve`). |
| `alerts.py` | Event notifications, retry state machine, delivery bounds, suppression of imported history wakes. |
| `advisory.py` | Multi-round adversarial peer review coordination. |
| `scripts/migrate_agents_home.py` | Idempotent migration tool from `Agents Home Folder` with `--verify-rehearsal`. |
| `scripts/prepare_windows.ps1` | Windows desktop staging script for `%LOCALAPPDATA%\ACH`. |
| `install.py` / `setup_clients.py` | Production installer and client config generator. |
| `tests/test_v3_architecture.py` | Acceptance test suite for v3 schema, forward cursors, and approval boundaries. |

---

## 5. Verification & Common Commands

Run these commands using Python 3.12:

```powershell
# Run the complete test suite (120 tests)
py -3.12 -m unittest discover -s tests -p "test_*.py"

# Run MCP smoke verification (49 tool checks)
py -3.12 tests/smoke_mcp.py mcp_server.py --cases tests/v2_cases.json

# Run migration rehearsal check
py -3.12 scripts/migrate_agents_home.py --verify-rehearsal

# Start or restart local live server on port 8765
$env:COLLAB_WORKSPACE = "$env:LOCALAPPDATA\ACH\workspace"
$env:COLLAB_DISABLE_EXTERNAL_DELIVERY = "1"
$env:COLLAB_ALERTS_AUTOSTART = "0"
py -3.12 collab.py serve --port 8765
```

---

## 6. Next Actions for Codex

1. **Review Kimi's Inspection Feedback**: When Kimi completes her inspection of ACH, evaluate her findings and make any high-priority refinements.
2. **Execute Phase 5 Cutover (Only When Kenny Explicitly Approves)**:
   - When Kenny confirms he is ready to move the agents over from `Agents Home Folder`:
     1. Backup existing client configs to a timestamped folder.
     2. Run `py -3.12 setup_clients.py` to register the ACH MCP server and hooks.
     3. Switch `COLLAB_DISABLE_EXTERNAL_DELIVERY=0`.
     4. Broadcast the welcoming cutover message to `#general` in ACH.

