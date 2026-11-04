# Kimi Review Packet: Agent Collaboration Hub (ACH) Architecture & UX Inspection
**Project**: Agent Collaboration Hub (ACH)  
**Target Reviewer**: Kimi K3 (Moonshot AI via Fireworks AI in Cline)  
**Orchestrator**: Kenny / Codex  
**Repo**: `c:\Users\kenne\OneDrive\Desktop\Agent Collab Hub`  
**Working Branch**: `feat/ach-v3-foundation`  
**Staged Dashboard**: `http://127.0.0.1:8765`  
**Mode**: Read-only code inspection and architectural audit  

---

## 1. Strict Context & Workspace Boundary

> [!IMPORTANT]
> **ISOLATION NOTICE FOR KIMI**:
> This task is exclusively for **Agent Collaboration Hub (ACH)**.
> This is **NOT** Fable's Virtual Assistant queue in `Agents Home Folder`.
> - Do **NOT** touch `T169` through `T197` in `Agents Home Folder`.
> - Do **NOT** post updates to `Agents Home Folder/board` or write to `inbox/`.
> - Your working directory for this inspection is strictly `c:\Users\kenne\OneDrive\Desktop\Agent Collab Hub`.
> - You have read-only permissions across the ACH repository.

---

## 2. Review Objectives

Inspect the verified v3 foundation across four core pillars:

### Pillar 1: Backend Architecture & Forward Cursors (`collab.py`)
- **Forward Cursor Completeness**: Inspect `op_read_messages(project_id, channel, since_id, limit, direction)`. Verify that paging sequentially through large backlogs (e.g. 1,000+ messages) cannot miss messages or loop infinitely.
- **Project Isolation**: Inspect `projects`, `project_members`, and project filtering across messages, tasks, and events.
- **Owner Token Gate**: Inspect `/api/approve` and `op_owner_approve`. Verify that token verification requires the local `.owner_token` and cannot be called with an unauthenticated payload.
- **Guardrails**: Inspect enforcement of the em-dash ban (`U+2014`) and forbidden paths (`D:\va`).

### Pillar 2: MCP Stdio Protocol & Tool Coverage (`mcp_server.py`)
- **Tool Schemas**: Inspect the 25+ advertised tools (`collab_project_*`, `collab_review_*`, `collab_lock_*`, `collab_owner_approve`, `collab_events`).
- **Backward Compatibility**: Verify legacy `t_read`, `t_post`, `t_join`, and `t_task_*` wrappers work transparently with the v3 SQLite schema.

### Pillar 3: Live-Chat-First Production UI (`assets/dashboard.html`)
- **DOM Windowing (80 Cards)**: Inspect `renderMessages()` and how the 80-card windowing operates alongside the `Load earlier messages` button.
- **Instant Search**: Inspect `#chat-search` filter performance across 1,300+ messages.
- **Composer Pre-Flight**: Inspect the `@mention` input handling and live warning indicators for em dashes and forbidden paths.
- **Accessibility & Focus**: Verify that background polling or event arrivals do not steal focus from the user while typing.

### Pillar 4: Idempotent Migration Safety (`scripts/migrate_agents_home.py`)
- **Zero Historical Wakes**: Verify that historical imports set `is_imported=1` and `suppress_dispatch=1` so `alerts.scan()` generates zero wakes.
- **Idempotency**: Verify that running the migration multiple times produces zero duplicate rows.

---

## 3. Deliverable & Format

Kimi, please provide your written inspection report with:
1. **Executive Verdict**: (Approve / Approve with Recommendations / Request Changes).
2. **Pillar-by-Pillar Findings**: Detailed notes on code quality, performance, and edge cases.
3. **UX & Design Assessment**: Feedback on the live chat layout and visual hierarchy.
4. **Any Discovered Bugs or Risks**: Concrete line numbers, reproduction steps, or suggested patches.
