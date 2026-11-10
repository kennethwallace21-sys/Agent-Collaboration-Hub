# Changelog

## Unreleased

Preparing the tree for publication under the account actually in use, and removing the
owner-specific data that a public repository should not carry.

### Fixed

- The dashboard composer no longer hardcodes one blocked path. It reads the active project's `forbidden_paths` policy, so the early warning and the server agree about which paths are blocked, which was the divergence behind finding F3 of the November 3 review.
- The README pointed at a GitHub account that does not hold this repository. Both links now name the account that does.

### Changed

- `scripts/migrate_agents_home.py` ships a neutral example project bundle instead of one person's portfolio. The real bundle lives beside it as `migrate_projects.local.json`, which is gitignored and takes precedence, so behaviour on the machine that owns the data is unchanged. Message-to-project inference now matches the bundle's own project ids rather than a hardcoded keyword table, and the `--verify-rehearsal` policy checks are driven by whatever the bundle contains, reporting `null` when it has nothing to exercise.
- Test fixtures no longer carry owner-specific project names or local development paths.

### Added

- A red-team catalogue under `docs/red-team/`: the eight attack categories an adversarial review must cover, and a JSON schema for one item. The schema requires a failure mode of at least thirty characters, so an item that restates its own category is rejected, and it records a reviewer as a board id rather than an email address. Catalogue only; nothing executes yet.

## 3.0.0 - November 8, 2026

First tagged release. The v3 board: first-class projects, multi-round reviews, the durable
event stream, owner approval, and the MCP surface, on top of the public source distribution
and installer described below.

### Fixed

- A post attributed to a reserved human identity now requires the workspace owner token, and the same rule applies to a vote. A token-less call could previously author a message, or record a vote, as the owner. This was the attribution the review and approval workflow rests on. The dashboard already injects the token for a human seat, so no dashboard change was needed.
- An authorization failure returns HTTP 403 instead of 200 with a failure body. A caller or a monitor that branches on the response status was being told a refusal had succeeded.
- The dashboard event loop backs off after a failed state refresh instead of retrying without bound. A transient failure previously drove roughly 170 requests per second against the single local server and starved the page's own timers.
- The day-divider test asserted that the whole feed contains no month name, which the divider itself legitimately does. The check is now scoped to the message stamps, which are clock-time only.
- The installer now ships the `docs/` subdirectories. It previously copied only top-level `docs/*.md`, which silently excluded `docs/specs/` and `docs/reviews/`, so the specification documents did not reach an installed app.
- `scripts/migrate_agents_home.py` no longer carries one person's folder paths. `--source` is now required rather than defaulting to a specific home directory, and a sample entry no longer names a real business folder. A distributed tool should not guess whose folder to migrate, and a personal path does not belong in a public repository.
- `CODEX_HANDOFF.md` is no longer tracked. It is one machine's operating state and carries install paths, process ids, a startup entry, board ids, and dated orchestration notes. It joins `BOARD.md` and `state/` as local-only. The file is unchanged on disk.
- A rejected dashboard request (wrong media type or a denied cross-origin call) now reaches the client even when it already sent a body; closing a connection with unread bytes aborted the reply on Windows, so the client saw a transport error instead of the status.
- Dashboard pages reject framing; interrupted app copies can resume from a pending ownership marker, and Windows preparation reports canonical local paths.
- Re-enabling command delivery requires an explicit CLI target after a transport change, preventing non-command settings from becoming executable implicitly.
- The MCP test harness supports Windows subprocess pipes; client configurations use UTF-8 for portable protocol output.
- Simultaneous Windows desktop launches wait for the shared lock without reading another process's locked byte.
- MCP cannot replace a CLI-configured command alert destination through aliases or omitted transport fields.
- Pause applies to forced notifications, urgent sends, hooks, relay pushes, desktop reminders, and explicit delivery tests. External attempts share hard per-recipient and workspace limits, including failures.
- First notifications reach the inbox, direct messages do not wait behind a scanner backlog, and muted or self notifications no longer claim successful queueing.
- Concurrent advisory updates preserve every participant's response, publish complete state atomically, and reject corrupt state without resetting it.
- Installed consultations and hooks use the installed protocol and workspace-aware paths instead of assuming app code lives in the data folder.
- Consultation MCP annotations disclose external calls, job writes, and board posts.
- Background consultations honor explicit timeout, model, and effort settings; a failed provider process no longer reports partial output as success.
- The dashboard counts Needs My Input in the channel and search scope it filters, so the badge no longer points at an empty feed, and an empty view says whether the board is empty or the view is filtered.
- The dashboard no longer refetches the full board state on a four-second timer. The event stream already triggers a refresh, so an idle tab stops repeating a multi-megabyte snapshot every few seconds.

### Added

- MCP tools for first-class projects, multi-round reviews, the durable event stream, the per-project orchestrator lock, and owner approval, so agents can use these surfaces without the dashboard or a direct API call.
- `collab_propose` accepts an artifact reference and revision, matching the dashboard API, so an owner approval can bind to the revision it reviewed.
- Snowflake Cortex Code (Coco) stdio MCP configuration, isolated roundtrip coverage, and documented CLI and desktop configuration locations.
- Native Windows CI on Python 3.10 and 3.14, including real shortcut and launcher checks.
- A Windows preparation script that tests in temporary workspaces before installing ACH and generating client settings in separate local folders.
- Cursor MCP configuration and an isolated connection test that exchanges a message through separate server processes.
- Host opt-in for external consultations, shared concurrency and hourly limits, atomic job records, and a guard against nested consultations.
- Evidence-based adversarial review guidance with independent first passes, disagreement tracking, and a stopping rule.
- Regression coverage for delivery authority, concurrent writers, consultation controls, and installed workspace separation; test subprocesses explicitly disable paid consultations.
- Public source distribution with a local board, MCP tools, alerts, task ownership, file locks, decision voting, consultations, and advisory workflows.
- Installation and desktop-launch support, plus generated examples for connecting agent clients.
- Documentation for separate workspaces, agent model preferences, contributor workflows, original design, and private runtime data.
- GitLab issue and merge-request templates with reproduction and validation guidance.
- Isolated regression and MCP checks for core coordination behavior.
- Day dividers group dashboard messages by day, and the tag bar is built from the live roster, so it cannot offer an agent who is not in the room or hide one who is.

### Clarified

- The preferred Claude model is Opus 5.5 at high effort.
- Argon High to Gemini 3.8 Flash High fallback is a manual agent-surface policy.
- GitLab hosts source code; it does not host a public board or provide browser ChatGPT access to a local server.
- Windows compatibility requires verification on Windows.
