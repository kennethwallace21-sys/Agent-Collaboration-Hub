# Portfolio assessment

Owner: human director (Kenny Wallace)
Status: Draft for owner review
Version: 0.1
Date: November 8, 2026
Method: direct inspection of local folders, the GitLab API through `glab`, the GitHub API
through `gh`, and the Azure subscription through `az`, on November 8, 2026

## 1. Scope

This assesses the state of the owner's AI product portfolio, not the correctness of any
individual product. It covers every repository and working folder that was reachable from
this machine. It does not assess code quality inside `caai-ops` or the Virtual Assistant in
depth, because neither was read line by line. Where a claim rests on a file listing, a
commit date, or a resource listing rather than on reading the implementation, that is stated.

## 2. Inventory

| Asset | Kind | Last active | Real state |
| --- | --- | --- | --- |
| `Agents Home Folder` (local) | File-based agent board, v2 | Active, daily | **Working.** 5 projects, 26 lessons each with a named enforcement, an audit loop, a roster, an atomic lock. This is the most mature coordination system the owner has, and it runs on PowerShell and files |
| `Agent Collab Hub` (local, GitHub, GitLab) | Python and SQLite agent board, v3 | Active | **Working but unshipped.** 121 Python tests, 13 dashboard tests, 49 MCP checks, a live board on loopback. Unmerged branch, and two files have been modified but uncommitted since November 3 |
| `virtual-assistant` (GitLab) | Local voice assistant | Active, today | **Active.** The only repository with activity this week |
| `caai-agents` (GitLab) | Agent platform design | 2026-05-22 | **Designed, not built.** 1,332-line PRD, 6 JSON schemas, 8 governance protocols, 6 red-team suites, 1 of 5 agents authored, zero runtime code. Stopped around Day 33 of a 60-day plan |
| `caai-ops` (GitLab) | Multi-product operations platform | 2026-10-18 | **Large and dormant.** 6 products listed including an "Agentic Orchestrator App for internal agent mission control", a trust layer, a RAG stack, and a local NVIDIA model pipeline. Azure AD integration for Teams. Two tracked `.env` files at the repository root |
| `VIrtual Agent Files` (local) | Build records | 2026-10-30 | **Archive.** Task briefs, eval gold sets, evidence, launcher material |
| 10 further `caai-main-group` repos | Products and infrastructure | Mixed | **Unassessed in depth.** hcm-platform and caai-hcm-platform both exist, angie, caai-infrastructure, caai-multimodal-rag, agent-hr-assistant, caai-social-media-manager, scooters-command-center, caai_website, angie-security-policy-project |
| Azure subscription | Infrastructure | Live | **Live and billing.** 4 resource groups, 20 resources, 6 AI resources on standard-tier SKUs. The resource that `caai-agents` is designed against does not exist |

## 3. The pattern

This is the finding that matters more than any individual row above.

**The owner builds a new system to solve a coordination problem, and the new system becomes
another thing that needs coordinating.** Five iterations of one idea now exist: a
file-based board, a Python board, an agent platform PRD, an orchestrator app inside a larger
repo, and a design for a lifecycle and memory layer. Two of them contain substantially the
same product. Three of them contain model-access code.

**Design consistently outruns implementation, and the gap is large.** The evidence is not
ambiguous:

| Artifact | Design produced | Implementation produced |
| --- | --- | --- |
| `caai-agents` | 83 KB PRD, 6 schemas, 8 protocols, 6 red-team suites, 5 agent profiles | 3 CI shell hooks, 1 Python validator, 1 test |
| `Agent Collab Hub` | 12 documents, a changelog, a public README | Real working code, on an unmerged branch with stale uncommitted edits |
| `caai-ops` | 6 products, a trust-layer positioning document, a NVIDIA strategy document | Present but dormant since mid-October |
| `Agents Home Folder` | A protocol, a roster, an audit checklist, 26 lessons | Working, and the only system with a genuine self-improvement loop |

**Dated commitments are made and then not tracked.** `caai-agents` committed to Day 60 as
2026-06-18, a cutover on 2026-12-08, and credit expiry on 2026-12-20. It went dormant on
2026-05-22. Nobody has been watching any of those dates, which is why a six-week-old
document produced an apparent emergency this week.

**Duplication goes undetected because nothing indexes what exists.** Fourteen GitLab
repositories, three GitHub repositories, and four local working folders. No single page
states what each one is, whether it is alive, or who owns it. That is precisely the problem
document 001 section 1 describes, and it is the reason a from-scratch lifecycle
specification was written on Saturday for something `caai-agents` had already designed in
April.

## 4. What is genuinely working

Three things, and they are not small:

1. **`Agents Home Folder` has a real learning loop.** Twenty-six lessons, each naming an
   enforcement mechanism, an audit that re-verifies every lesson, and a rule that a lesson
   is unfinished until it names its enforcement. That is more disciplined than most
   commercial engineering organizations, and it is the single most valuable asset found in
   this assessment.
2. **`Agent Collab Hub` actually runs.** It has tests that pass, a live board, a working
   installer, a desktop launcher, and a migration tool with verified idempotency. It is
   close to shippable.
3. **The design work is high quality.** The `caai-agents` red-team suite and the
   `_shared` protocols are genuinely good, and the Agent Collab Hub documents are accurate
   about their own limits in a way that is rare.

## 5. What is at risk

| Risk | Evidence | Consequence if unaddressed |
| --- | --- | --- |
| Nothing ships, and the portfolio keeps growing | Five iterations of one idea. Two contain the same product | Effort keeps being spent on parallel versions of one thing, and none of them reaches a user |
| A dated obligation is missed and discovered as a false emergency | The Azure cutover, discovered 30 days before its date, in a repository dormant for six months | Time is spent responding to deadlines that were never real, which is exactly what happened this week |
| A live system is unmaintained while attention moves elsewhere | `virtual-assistant` is the only repo active this week. `caai-ops` has 6 products and 20 live Azure resources and has been dormant since mid-October | Live infrastructure bills and drifts with nobody watching. The six AI resources on standard SKUs bill whether or not anything uses them |
| A credential is exposed | Two `.env` files tracked at the `caai-ops` root, plus `logs/`, `data/`, and `datasets/` | The predecessor project's lesson `L009` is exactly this failure. It was recorded as a lesson and it has recurred in a different repository |
| The coordination problem blocks its own solution | Agent Collab Hub is the fix for the coordination problem, and the coordination problem is why Agent Collab Hub has not shipped | The product that would make everything else easier stays unfinished because everything else is hard |

## 6. Root cause

The failure is not capability. The design output here is better than most teams produce. The
failure is **focus and closure**.

Four specific mechanisms produce it:

1. **No primary product.** Every repository is worked on as if it were the main one. There
   is no stated order that says "this one ships first and the others wait."
2. **Design is more rewarding than shipping.** A design document can be produced in a
   session and feels complete. Shipping requires closing a branch, fixing known defects,
   tagging a version, and installing it somewhere. That is less satisfying, and it is where
   the work stops.
3. **Starting is cheaper than reconciling.** Starting a new board, PRD, or platform avoids
   the harder question of whether an existing one already covers it. `caai-agents` and
   `caai-ops` were both started while `Agents Home Folder` was already running.
4. **No register of commitments.** Dates are written into documents that nobody reopens. A
   commitment in a dormant repository is indistinguishable from no commitment at all, until
   it becomes urgent.

## 7. Recommendations

Ordered by value per unit of effort. The first three are small and are the ones that matter.

| # | Recommendation | Effort | Why this first |
| --- | --- | --- | --- |
| 1 | **Name one primary product and ship it.** Recommended: Agent Collab Hub, because it is closest to working and because it is the coordination layer every other project needs | Small | It breaks the pattern with the least new work. Merge the branch, fix the three confirmed defects, tag a version, install it on both stations |
| 2 | **Write one portfolio index page.** Every repository and folder, its purpose, its state, its owner, and its last activity date | Small | This is the fix for duplication going undetected. It is one page, and it prevents the next `caai-agents` |
| 3 | **Create one commitments register.** Every dated obligation across all repositories, with the date, the source, and whether it is real | Small | It converts an untracked risk into a list. The Azure cutover would have been answered in five minutes instead of surfacing as an emergency |
| 4 | **Harvest the `caai-agents` assets into the primary product.** The red-team suites, the six schemas, and the eight `_shared` protocols | Medium | High value, low risk, and it makes the dormant repository worth something without reviving it |
| 5 | **Explicitly park or retire the dead repositories.** Mark each with a status so a future session does not mistake it for active | Small | Prevents an agent from treating a dormant design as current guidance, which has already happened |
| 6 | **Check and rotate anything in the tracked `.env` files** | Small, but requires care | Security, and it is dated by nature |
| 7 | **Freeze new design work until recommendation 1 is done** | Zero cost, high discipline | Directly addresses mechanism 3. A new design document cannot be started until one product has a tagged release |

## 8. The risk in this document set

An honest note about the work in this folder. Five specification documents were written on
November 8. That is **the same pattern** described in section 3, performed in the space of
one day: high-quality design produced quickly, ahead of any implementation.

The documents are only worth their cost if something gets built. Concretely, that means:

- Documents 001 through 005 should not grow further until recommendation 1 is complete.
- Every open decision now carries a recommendation, so the owner can answer them in one
  pass rather than commissioning more analysis.
- The measures below are the point of this assessment. If they are not met, the documents
  made the problem worse rather than better.

## 9. Measures

| Measure | Target |
| --- | --- |
| Products with a tagged, installable release | At least 1, up from 0 |
| Products with a stated primary or parked status | All of them, up from 0 |
| Dated commitments tracked in a register | All of them, up from 0 |
| Repositories indexed on one page | All 17, up from 0 |
| New design documents started while the first product is unreleased | 0 |
| Confirmed defects fixed before the primary product is released | All 3 |

## 10. Decisions

| ID | Decision | Recommendation |
| --- | --- | --- |
| PA-1 | Which product is primary until it ships? | Agent Collab Hub, because it is closest to working and because it is the coordination layer the rest of the portfolio needs |
| PA-2 | Is new design work frozen until the primary product ships? | Yes. This is the highest-leverage discipline available and it costs nothing |
| PA-3 | Is the portfolio index a document, or a view inside the board? | A view inside the board, generated from the repositories themselves, once the board supports it. A static document will drift within a month, which is the lesson from the predecessor's hand-written status table |
| PA-4 | Are the dormant repositories parked or deleted? | Parked, with a status and a reason. Deletion destroys the `caai-agents` design record and the `caai-ops` history, both of which have value |

## 11. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 8, 2026 | First draft. Inventory of 17 repositories and 4 local folders, the recurring pattern of design outrunning implementation, root cause, 7 recommendations, 6 measures, and 4 decisions |
