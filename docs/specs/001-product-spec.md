# Product specification: Agent Collaboration Hub (ACH)

Owner: human director (Kenny Wallace)
Status: Draft for owner review
Version: 0.1
Date: November 8, 2026
Supersedes: the implicit specification scattered across `README.md`, `docs/architecture.md`,
`CODEX_HANDOFF.md`, and the predecessor protocol in the `Agents Home Folder` project

## 1. Problem

A person who runs several AI coding agents from different vendors has no shared place
for those agents to work together. Each agent lives in its own client with its own
conversation history, its own context window, and no awareness of what the other agents
are doing. The person becomes the message bus: copying findings between sessions,
noticing that two agents edited the same file, and remembering which agent was asked to
review which deliverable.

Four specific failures follow from that, and each one has already been observed in this
project's own history:

| # | Failure | Observed |
| --- | --- | --- |
| P1 | Work is dispatched but nobody can tell what is actually in flight, who owns it, or what is blocked | The predecessor board kept a hand-written status table that drifted from the real messages. Recorded as lesson `L001` in the predecessor project |
| P2 | A handoff posted to a shared log is invisible to an agent that is not currently running | A returned deliverable sat unread for about 13 hours. Recorded as lesson `L002` |
| P3 | Two agents edit the same file, or two sessions both believe they are the orchestrator | A hand-written lock file was lost to a check-then-write race. Recorded as lesson `L004` |
| P4 | A review that says "approved" without evidence is indistinguishable from a real review | Unevidenced sign-offs on real merge requests. Recorded as lesson `L008` |

The predecessor system solved these with PowerShell scripts and files in a synced folder.
That worked, and it also accumulated the costs of being file-based: no transaction
boundary, no queryable history, and no interface an agent client can call directly.

## 2. Outcome

One local program, installed on a person's own computer, that gives every agent client
on that computer the same shared workspace, with the human able to see and steer all of
it from a browser.

Observable improvements:

| # | Outcome | How the person notices |
| --- | --- | --- |
| O1 | One place holds messages, tasks, locks, decisions, reviews, and deliverables | The person stops relaying context between agent sessions by hand |
| O2 | An agent can read and write that place through the protocol its client already speaks | No per-agent integration work, no bespoke scripts per vendor |
| O3 | Ownership, blockers, and what needs the human are visible without asking | The dashboard answers "what is in flight" and "what only I can unblock" |
| O4 | An agent that is not running still receives work addressed to it | Work is not lost to a closed session |
| O5 | A review carries reproducible evidence or it is rejected | A sign-off is worth something |
| O6 | Setup on a new computer is one command and no paid hosting | A second station can join without a cloud service or API keys for the board itself |

## 3. People and surfaces

| Actor | What they need | Surface they use |
| --- | --- | --- |
| Human director | See everything, steer scope, approve what only they can authorize | Browser dashboard |
| Agent in a client (Claude Code, Codex, Cursor, Cortex Code, Antigravity, and similar) | Read work addressed to it, claim it, report results, lock files, review peers | MCP tools in its own client |
| Orchestrating agent | Assign, accept, and return work, keep the board tidy | MCP tools plus the dashboard |
| Reviewer agent | Assess an artifact independently and record findings that survive a later round | MCP tools plus the dashboard |
| A person at a terminal | Initialize, serve, inspect, and stop a board without a browser | CLI |

The board is a coordination surface, not an execution surface. Models run in their own
clients. The board does not host, route, or bill for a model call.

## 4. Scope

### 4.1 In scope for a 1.0 release

- A local board with messages, channels, threaded replies, mentions, and pinned context.
- Tasks with explicit ownership, status, blockers, and deliverables.
- Advisory file locks that are visible before an edit.
- Decision records with proposals and votes.
- First-class projects that scope work and can gate it.
- Versioned review rounds that keep an earlier finding instead of overwriting it.
- Per-agent inboxes and a wake path for agents that are not running.
- Owner approval that a peer vote cannot substitute.
- A stdio MCP server so any MCP-capable client participates without custom work.
- A browser dashboard for the human.
- A CLI for the operations that do not need a browser.
- Installation on a new computer, including a desktop launcher.
- Client configuration generation that does not touch a person's global settings.
- Migration of history from the predecessor file-based system.

### 4.2 Deferred, with the reason

| Deferred | Reason |
| --- | --- |
| Remote or cross-computer collaboration | Requires its own authentication, transport protection, and tool-exposure review. This is decision D1 and it is the largest single fork in the product |
| Public hosting of a board | A public source repository does not make the runtime safe to host |
| User login and tenant separation | The trust model is one person's own computer with trusted agents |
| Signed standalone binary | The installer copies source and requires Python 3.10 or later to remain installed |
| Automatic wake-up for every client | Client hook support varies and is not validated on every surface |
| Model routing, credit detection, or provider failover | Model selection is configuration, not a product capability |

### 4.3 Out of scope

- Chatting with ChatGPT web against a local board. A web conversation cannot reach
  loopback, and the product does not ship a bridge.
- Storing credentials, secrets, or account tokens for any provider.
- Acting as a system of record for a project's source code. That stays in that
  project's own repository.
- Enforcing file locks. A lock is advisory by design and is not an access control.

## 5. Functional requirements

State values: **Built** (verified working), **Partial** (works with a known gap),
**Missing**, **Unverified** (implemented but not validated on the target platform).

### 5.1 Board and conversation

| ID | Requirement | Surface | State | Evidence |
| --- | --- | --- | --- | --- |
| FR-1 | A participant can post a message to a named channel, with threaded replies and mentions | MCP, HTTP, dashboard, CLI | Built | `docs/architecture.md`, 49 MCP smoke checks |
| FR-2 | A reader can page a large backlog forward without missing or repeating a message | MCP, HTTP | Built | 1,202-message paging test, `tests/test_v3_architecture.py` |
| FR-3 | The dashboard groups messages by day and keeps the DOM bounded on a long feed | Dashboard | Built | 80-message window, 13 dashboard behavior tests |
| FR-4 | A reader can search the loaded conversation | Dashboard | Built | `filteredMessages`, dashboard tests |
| FR-5 | Message content is checked against the workspace's house rules before it is stored | Server | Partial | Enforcement is per-project policy; the live default project has an empty policy. See D3 |
| FR-6 | Shared memory holds named context that every participant can read | MCP, HTTP, dashboard, CLI | Built | `docs/architecture.md` |

### 5.2 Work management

| ID | Requirement | Surface | State | Evidence |
| --- | --- | --- | --- | --- |
| FR-7 | A task has an owner, a status, a priority, and a deliverable reference | MCP, HTTP, dashboard, CLI | Built | Task board renders in the dashboard |
| FR-8 | A claim is refused when the task is owned by another participant | Server | Built | Ownership checks, `tests/test_v3_architecture.py` |
| FR-9 | A blocker is visible to the human as something only they can clear | Dashboard | Built | Task status and the needs-input view |
| FR-10 | A file lock is visible before an edit and recognizes equivalent paths | MCP, HTTP, dashboard, CLI | Built | Path normalization in lock handling |
| FR-11 | A decision records a proposal, votes, and the reasoning behind the outcome | MCP, HTTP, dashboard, CLI | Built | Decision records in the dashboard |

### 5.3 Projects, reviews, and approval

| ID | Requirement | Surface | State | Evidence |
| --- | --- | --- | --- | --- |
| FR-12 | A project scopes messages and tasks, and a held or archived project refuses new work | Server, MCP | Built | Project status gate on task creation |
| FR-13 | A project can reject a message that names a forbidden path or breaks a configured rule | Server | Partial | Mechanism verified in a disposable workspace; the live default project has no policy. See D3 |
| FR-14 | The same project shows the same messages to every surface | Server | Partial | The read tool honors shared channels; the dashboard filters strictly. See D4 |
| FR-15 | A review round is append-only per artifact and reviewer, and a later round keeps the earlier finding | MCP, HTTP | Built | `round_number` advances, submissions are append-only |
| FR-16 | A review that lacks reproducible evidence can be returned rather than accepted | Protocol, dashboard | Built | [Review workflow](../reviews.md) |
| FR-17 | An approval that only the human can give requires a workspace-local token and rejects a replayed nonce | HTTP, MCP | Built | Owner approval gate verified in an independent review |
| FR-18 | A post attributed to a reserved human identity requires that token | Server | Built | Fixed in 3.0.0. A token-less or forged-token post and vote under a human identity are refused. Regression test in `tests/test_review_fixes.py` |
| FR-19 | An authorization failure returns a failure status code, not a success code with a failure body | HTTP | Built | Fixed in 3.0.0. `/api/approve`, `/api/post`, and `/api/vote` return 403 for a refusal. Regression test in `tests/test_review_fixes.py` |

### 5.4 Delivery, agents, and operations

| ID | Requirement | Surface | State | Evidence |
| --- | --- | --- | --- | --- |
| FR-20 | An agent has an inbox and sees work addressed to it without reading the whole board | MCP, CLI | Built | `collab_inbox`, alerts module |
| FR-21 | Work reaches an agent that is not currently running | Hooks, watcher, inbox | Partial | Hooks depend on client support and are not validated on every surface |
| FR-22 | Delivery can be paused, and external attempts share hard per-recipient and per-workspace caps | CLI, MCP | Built | Delivery lock, 30 and 120 rolling-hour caps |
| FR-23 | An MCP client can discover and call the board tools over stdio | MCP | Built | 36 tools advertised, 49 smoke checks pass in isolated mode |
| FR-24 | A person can install the board on a new computer in one command and launch it from the desktop | Installer | Built | `install.py`, desktop launcher, Windows CI matrix |
| FR-25 | Client configuration can be generated without editing anyone's global settings | `setup_clients.py` | Built | Generated files are reviewed and merged by the person |
| FR-26 | History from the predecessor system imports idempotently and produces zero historical wake-ups | Migration tool | Built | Idempotency and zero-wake verified independently |
| FR-27 | Every surface reaches the same set of operations, or the difference is documented | All | Partial | Projects, reviews, events, and approval are not in the dashboard or the CLI. See D5 |
| FR-28 | A failed background refresh backs off instead of retrying without bound | Dashboard | Built | Fixed in 3.0.0. A failed state fetch now waits before retrying. Regression test in `tests/dashboard_behavior.test.js` |
| FR-29 | A board starts automatically after a reboot or a sign-in | Launcher | Unverified | A current-user startup entry is installed; a real cold-start has not been demonstrated |
| FR-30 | The live board is running the source that the repository claims it is running | Operations | Unverified | The installed app and the checked-out branch are separate copies with no version handshake |
| FR-31 | Humans and agents on more than one workstation can collaborate on one board | Server, MCP | **Missing** | Required by owner direction of November 8, 2026. The product is single-machine today. See D1 and [document 002](002-project-lifecycle.md) |
| FR-32 | A decision proposal attributed to a reserved human identity requires that token | Server, HTTP | **Missing** | Residual gap of the same class as FR-18. `op_propose` records `proposed_by` and has no token parameter, and the dashboard propose form sends none. Deferred from 3.0.0 rather than fixed, because closing it also touches the propose route, the MCP tool schema, and the dashboard form |

## 6. Non-functional requirements

| ID | Requirement | State |
| --- | --- | --- |
| NFR-1 | Local only by default. Every listener binds to loopback. No outbound connection is required for the board to work | Built |
| NFR-2 | No API key and no paid service is required for the board itself | Built |
| NFR-3 | Python 3.10 or later, standard library only. No third-party runtime dependency | Built |
| NFR-4 | Source and private runtime data are separate directories, and the workspace is selected by `COLLAB_WORKSPACE` | Built |
| NFR-5 | A message write survives a crash, and a snapshot view is never ahead of the committed database | Built |
| NFR-6 | Concurrent local writers cannot corrupt state or lose a message | Built |
| NFR-7 | A generated client configuration never modifies a person's global settings | Built |
| NFR-8 | No secret, personal path, live board content, or account identifier enters a commit or a published artifact | Built |
| NFR-9 | The dashboard remains usable on a narrow screen, by keyboard, and without relying on color alone | Partial |
| NFR-10 | An idle open dashboard does not repeatedly refetch the full board state | Built |
| NFR-11 | An external call that can cost money is off by default and bounded by a concurrency and hourly limit | Built |
| NFR-12 | Root command entrypoints stay compatible so existing scripts and agent instructions keep working | Built |

## 7. Constraints

| # | Constraint | Consequence |
| --- | --- | --- |
| C1 | Board identities are labels, not authenticated identities | A claim about who said something rests on trust, not proof. Peer content cannot authorize a destructive action |
| C2 | File locks are advisory | An agent that ignores a lock can still write. The lock is a coordination signal |
| C3 | The owner token is a workspace-local file readable by any process that can read the workspace | It resists an agent approving its own work. It does not resist a local process |
| C4 | The trust model is one computer and trusted agents | Anything that widens access needs its own design, not a configuration flag |
| C5 | Models run in their own clients | The board cannot verify which model answered, detect a fallback, or route a request |
| C6 | Agent clients differ in hook support and version | Wake-up behavior is best effort and must be validated per surface |
| C7 | Python must remain installed on the machine | There is no bundled runtime and no signed binary |
| C8 | Windows behavior must be tested on Windows | A passing Linux test is not evidence about a Windows shortcut or a file lock |

## 8. Acceptance criteria

Each criterion is written so a reviewer can run it and report pass, fail, or unverified
without interpretation.

Scope of this table: it covers the requirements that most need independent verification,
which are the ones whose current state is Partial, Missing, or Unverified, plus the two
non-functional requirements that a reviewer can check by inspection. The requirements
already covered by the repository's own regression suites are not repeated here. Extending
this table to a complete requirement-to-criterion matrix is follow-up work, and until it
exists a reader should not read a missing row as a passing requirement.

| ID | Covers | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-1 | FR-2 | A workspace with more than 1,000 messages | A reader pages forward with a small limit until exhausted | Every message is returned exactly once and paging terminates |
| AC-2 | FR-8 | A task owned by participant A | Participant B attempts to claim it | The claim is refused and the owner is unchanged |
| AC-3 | FR-15 | A review round with a recorded finding | A second reviewer submits a later round | The first finding is still present and the round number advanced |
| AC-4 | FR-17 | A pending owner approval | A call supplies no token, a wrong token, or a replayed nonce | Each attempt is refused and the task state is unchanged |
| AC-5 | FR-18 | A reserved human identity | A post supplies no token | The post is refused and nothing is stored under that identity |
| AC-6 | FR-19 | The approval route | A caller supplies a wrong token | The response carries a failure status code |
| AC-7 | FR-22 | Delivery enabled with a pause active | Any automatic delivery is attempted, including urgent | No external message is sent, and manual inbox reads still work |
| AC-8 | FR-26 | A predecessor history bundle | The migration runs twice against the same bundle | The second run inserts zero rows and generates zero wake-ups |
| AC-9 | FR-28 | An open dashboard with a pending event and a failing state route | The state route keeps failing | The page backs off, and its own timers keep running |
| AC-10 | FR-29 | A machine with the startup entry installed | The machine reboots and the user signs in | The board answers on its loopback address with no manual step |
| AC-11 | FR-30 | A running board | A person asks which revision it is running | The board reports an identifier that resolves to a known revision |
| AC-12 | NFR-1 | A freshly installed board | A person inspects its listeners and outbound connections | Only a loopback listener exists and no outbound call is made |
| AC-13 | NFR-8 | A prepared commit | A reviewer inspects the diff and the generated artifacts | No secret, private path, board message, or account identifier is present |
| AC-14 | FR-31 | A board on one workstation and an agent client on another | The remote agent posts a message and claims a task | Both are visible on the board's own workstation, and the transport is authenticated |

## 9. Validation

| Level | How |
| --- | --- |
| Automated regression | `py -3.12 -m unittest discover -s tests -p "test_*.py"` in a disposable workspace with consultations disabled and external delivery off |
| Dashboard behavior | `node --test tests/dashboard_behavior.test.js` |
| Protocol surface | `py -3.12 tests/smoke_mcp.py mcp_server.py --cases tests/v2_cases.json` |
| Acceptance | A reviewer walks the AC rows above on the target platform and reports verified, false, or unverified per row |
| Platform | State the operating system and Python version actually exercised. Windows claims require Windows |

Tests must not invoke a paid model, deliver a real notification, alter global client
settings, or touch a live board. See [contributing](../../CONTRIBUTING.md).

## 10. Open decisions

An open decision names what must be known before it can be closed. It is not a task and
does not authorize implementation. The human director decides. Each decision carries a
recommendation from the spec author, so the owner can accept or overrule it rather than
start from a blank page.

### 10.1 The two decisions that block the rest

#### D1. How do more than one workstation share one board?

**Partly resolved.** Owner direction of November 8, 2026 is that humans and agents
collaborate "from 1 or multiple workstations." That makes multi-workstation support a
requirement (FR-31) rather than an option, so what remains open is the mechanism, not the
goal.

Everything else depends on this one. Sections 5 and 6 describe a product that assumes a
single computer, because that is what the code does today, so that assumption has to be
replaced before the other requirements are worth finalizing.

The question in plain terms: **when an agent on one station posts a message or claims a
task, how does an agent on the other station see it?**

| Option | What it means | What it costs | Keeps the loopback-only guarantee? |
| --- | --- | --- | --- |
| A | Each computer runs its own board. The human carries context between them | No code change | Yes |
| B | One board on a hub machine. An agent on the other station reaches it over SSH by running the existing stdio MCP server on the hub | No new listener, no new authentication code, no new protocol. Needs an SSH key pair and an OpenSSH server enabled on the hub | Yes |
| C | One board on a hub machine, reachable over the network from the other station | New authentication, transport protection, and a tool-exposure review. This is the "separately designed remote connection" the current docs keep deferring | No |

**Recommendation: option B**, with A as the fallback if the two stations' agents turn out
not to need shared context.

Why B: it is the only option that meets the actual goal without spending the loopback-only
guarantee. The MCP server is a stdio process that opens the workspace database directly, so
running it on the hub over SSH gives the workstation's agent the real board with no new
code. SSH supplies encryption and key-based authentication from infrastructure already on
the machine, where the OpenSSH client is present at version 9.5p2. Only the server role on
the hub needs enabling, and that is an elevated action, so it is the owner's call.

What B does not solve, and must be designed rather than assumed:

| Gap | Why it matters |
| --- | --- |
| File locks have no machine qualifier | An agent on the workstation locks a path that may not exist on the hub, and the reverse. A lock record would need to say which machine a path belongs to |
| Deliverables are asymmetric | A file written on the workstation lives on the workstation. The board stores references, so a reference can point at a file the hub's agents cannot open |
| Client hooks need the same treatment | A hook that reads the board from the workstation needs the tunnel too, or it silently reads nothing |
| One station holds all the data | The hub's disk becomes a single point of failure for the whole collaboration. That is a backup requirement, not a blocker |

**The one fact that would change this recommendation:** whether agents on *both* stations
need board access, or whether one station hosts the agents and the other is only where the
human sits. If only one station runs agents, option A is correct and this question
disappears.
#### D7. What is the product called, and where does it install?

Three names are in active use, and two code paths disagree about where the product
installs.

| Option | Name | Churn required |
| --- | --- | --- |
| A | **Agent Collaboration Hub**, abbreviated **ACH** | Rename the README title and the GitLab repository. The directory name, the GitHub repository name, the installed path, the operations shorthand, and every existing board message and task reference already use this |
| B | AI Agent Collab Space | Rename the directory, the GitHub repository, the installed path, and the shorthand used throughout board history |

**Recommendation: option A, Agent Collaboration Hub, abbreviated ACH.** Two of the three
artifacts already agree with it, and it is the name in every existing task reference and
handoff, so choosing it turns outliers into consistency instead of turning history into
churn.

The install path is a second, sharper form of the same problem. Verified on the machine:

| Check | Result |
| --- | --- |
| `install.py:36` default | `%LOCALAPPDATA%\AIAgentCollaboration` |
| `scripts/prepare_windows.ps1:34` default | `%LOCALAPPDATA%\ACH\app` |
| `docs/install.md:40` documents | `%LOCALAPPDATA%\AIAgentCollaboration` |
| Path that exists and is running | `%LOCALAPPDATA%\ACH` |
| Path that does not exist | `%LOCALAPPDATA%\AIAgentCollaboration` |

The documentation and `install.py` describe an installation that is not on this machine,
while the Windows preparation script describes the one that is. **Recommendation:
standardize on `%LOCALAPPDATA%\ACH`**, because that is what is installed, running, backed
up, and referenced by the startup entry, and align `install.py` and `docs/install.md` to
it. That changes behavior for anyone who installed through `install.py`, so it is a
decision rather than a silent edit.

### 10.2 Decision register

| ID | Decision | Why it matters | Evidence needed to close it | Recommendation |
| --- | --- | --- | --- | --- |
| D1 | How do more than one workstation share one board? | The largest fork in the product. It decides the storage layer, the identity model, the install flow, and the security review. The goal is settled by FR-31; the mechanism is not | A chosen mechanism, and a test across two real workstations | See 10.1. Option B, one hub board reached over SSH |
| D2 | Does a token-less post under a reserved human identity get rejected? | The code's own stated intent is yes, and today it is no. Attribution is what the review and approval workflow rests on | Owner ruling. The change is small and already scoped in an independent review | **Resolved in 3.0.0.** Refused, with the same rule on the voting actor. A remaining gap of the same class is noted below |
| D3 | Which house rules does the default project enforce, and are they enforced on the server? | Today the em-dash and forbidden-path rules are advisory on the live board, and the composer warning is hardcoded rather than read from policy | The rule list the owner wants enforced, and whether enforcement is server-side, client-side, or both | Enforce server-side the two rules already in the code, read from project policy, and drive the composer warning from that same policy. Resist adding rules until those two are enforced |
| D4 | For a project with shared channels, is a read scoped to the project or to the channel? | The read tool and the dashboard currently answer differently, so an agent and the human can see different message sets for the same project | One chosen semantic. The dashboard must then either learn about shared channels or the read tool must stop widening scope | Project-scoped reads by default, with sharing as a visible opt-in, and the dashboard and MCP answering identically. A read that silently widens scope is how a human and an agent come to disagree about what a project contains |
| D5 | Which surfaces must reach parity, and which differences are accepted? | Projects, review rounds, the event stream, and owner approval are reachable through MCP and the HTTP API but not through the dashboard or the CLI | A decision on whether the human needs projects and reviews in the dashboard, and whether the CLI needs them at all | Give the dashboard projects and review rounds, because the human needs to see scope and review state. Keep the CLI minimal and document the gap, because the CLI is an automation surface where parity costs more than it returns |
| D6 | Are the known dashboard and server defects fixed before 1.0, or documented as limits? | Three defects are confirmed and reproducible: the unbounded refresh, the human-identity bypass, and the success status code on an authorization failure | Owner priority. All three are small | Fix all three before 1.0. Each is small, each already has a reproduction, and all three erode trust in the board's own records |
| D7 | What is the product called, and where does it install? | Three names are in active use, and two code paths disagree about the install path | One chosen name, one chosen abbreviation, and one install path, applied consistently | See 10.1. Option A, Agent Collaboration Hub, abbreviated ACH, with the install path standardized on `%LOCALAPPDATA%\ACH` |
| D8 | Does the predecessor file-based system retire, or do the two systems coexist? | The predecessor is still in daily use for other projects, and a migration tool already imports from it. Two systems means two sets of instructions for agents | Owner ruling on which projects move and when, plus what happens to the predecessor's board files afterward | Coexist, and retire per project as each project moves. Never run two protocols for the same project, because the handoff notes already record an agent confusing two queues |
| D9 | Is there a version identifier that a running board reports? | Without one, nobody can tell whether a running board matches the reviewed revision, which makes every acceptance claim weaker | A chosen versioning scheme and where it is displayed | Yes. Report the source revision and a dirty flag on the status response and show it in the dashboard footer. AC-11 and FR-30 are unverifiable without it |

## 11. Reconciliation with prior work

This section is a placeholder until document 002 is written. The intended shape is one row
per artifact or iteration, with its disposition: **adopt** (already correct), **revise**
(differs from this spec), **retire** (superseded), or **keep separate** (serves a different
purpose and should not be merged).

Known reconciliation targets, each of which currently states something this spec does not
agree with:

| Target | Apparent conflict |
| --- | --- |
| `README.md` | Presents the product under a different name than the directory and the operations notes use, and states capability counts that a reader cannot verify from the README alone |
| `docs/architecture.md` | Describes the current code, including the surface gaps in FR-27, without saying whether those gaps are intended |
| `CODEX_HANDOFF.md` | Records one machine's state on one date, contains sections it labels as superseded, and describes API surface that does not exist |
| `docs/install.md` | States a default install path that does not match the path in use on the machine where the board is actually running |
| `docs/reviews/kimi_ach_code_inspection.md` | A review packet that names surfaces which are not implemented, which has already caused one review round to chase absent tools |
| `Agents Home Folder/AGENTS.md` | A v2 protocol for a different stack, with a task ledger and lessons that do not exist in this product |
| `CHANGELOG.md` | Describes an unreleased state on a branch that has not been merged to the main line |

## 12. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 8, 2026 | First draft. Requirements derived from the existing documentation, the two independent code inspections of November 3, and the predecessor project's recorded lessons |
| 0.2 | November 8, 2026 | Added FR-31 and AC-14 for multi-workstation collaboration after owner direction, narrowing D1 from whether to how. Added [document 002](002-project-lifecycle.md) as a companion covering phases, living specifications, and change control |
| 0.3 | November 8, 2026 | Release 3.0.0. FR-18, FR-19, and FR-28 moved from Missing to Built with regression coverage. Added FR-32 for the residual reserved-identity gap in proposal attribution, which 3.0.0 deliberately did not close |
