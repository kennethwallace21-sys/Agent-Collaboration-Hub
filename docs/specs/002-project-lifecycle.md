# Project lifecycle and spec control

Owner: human director
Status: Draft for owner review
Version: 0.1
Date: November 8, 2026
Companion to: [001 Product specification](001-product-spec.md)
Origin: owner direction of November 8, 2026, describing long-term product building with AI

## 1. Problem

Document 001 specifies a board where humans and agents coordinate on work. It does not
specify how a product moves through its life, or how a change to what a product *is* stays
connected to what the product *does*.

That gap appears in four ways, and none of them is fixed by tracking tasks:

| # | Failure | Why a task board alone does not prevent it |
| --- | --- | --- |
| Q1 | Nobody can say which stage a product is in, or what must be true to leave that stage | A board tracks tasks, not stages. Tasks complete without the product advancing |
| Q2 | A specification and a build drift apart | Requirements live in a document nobody is obliged to revise when behavior changes |
| Q3 | An agent changes behavior without knowing it changed a requirement | There is no link from a requirement to the code and tests that satisfy it |
| Q4 | A long-running product loses the reasoning behind earlier choices | Decisions are recorded but not recalled when a new session starts |

The predecessor project already recorded the first and third of these. Its lesson `L001`
was a hand-written status table drifting from the real messages, and lesson `L008` was an
unevidenced review sign-off. Both are symptoms of a build whose record is not bound to the
work.

## 2. Outcome

A product moves through named phases. Each phase has an exit gate that is a statement about
the artifact, not about elapsed time. The specification stays alive and is revised
deliberately. Every change that alters observable behavior passes through one defined loop
that updates the specification, the build, and the record together.

Observable improvements:

| # | Outcome | How a person notices |
| --- | --- | --- |
| R1 | A person or agent can see which phase a product is in and what is left to leave it | One view answers "where are we" without reading a transcript |
| R2 | A specification change is a visible, versioned event | No requirement changes silently, and the reason survives |
| R3 | Every delivered change can be traced from requirement to code to evidence | A reviewer follows the chain in both directions |
| R4 | A new session recovers the reasoning behind an earlier choice without being told | The board recalls it rather than a human re-explaining it |
| R5 | The process costs little on small changes | A one-line correction does not trigger a seven-step ceremony |

## 3. The model

Three concepts, deliberately separate, because collapsing them is what makes such systems
unusable:

| Concept | Answers | Changes |
| --- | --- | --- |
| **Phase** | What stage of work are we in, and what is the exit gate? | Moves through a defined order, and can return when a later phase reveals a gap |
| **Status** | Is this product being built, in use, or done? | Changes rarely, and describes the product's life rather than its current activity |
| **Requirement state** | Is this specific requirement built, partial, missing, or unverified? | Changes as work lands |

A phase is not a status, and a status is not a phase. A live product can be in a design
phase for its next capability, and that is normal rather than a contradiction.

### 3.1 Default phase set

The set is configurable per product. This is the default, adapted from the phase vocabulary
in [spec-kit](https://github.com/github/spec-kit) and the predecessor project's own practice.

| # | Phase | Purpose | Exit gate | Primary artifact |
| --- | --- | --- | --- | --- |
| 0 | Intake | Decide whether this is worth building at all | A recorded decision of **go**, **needs-clarification**, or **kill**, with the reasoning. A kill is a successful outcome, not a failure | Assessment with a decision |
| 1 | Design | Establish the problem, outcome, scope, and people | Problem, outcome, in-scope list, and deferred list agreed by the owner | Brief |
| 2 | Spec | State requirements and acceptance criteria | Every requirement has a permanent ID, a state, and either an acceptance criterion or a recorded reason it has none | Specification |
| 3 | Plan | Sequence the work | Every in-scope requirement maps to at least one task, and every task names the requirement IDs it serves | Plan and task set |
| 4 | Build | Implement | Every delivered task cites its requirement IDs and carries reproducible evidence | Deliverable and tasks |
| 5 | Verify | Confirm against the criteria | Every in-scope acceptance criterion is walked and reported verified, false, or unverified, with no criterion silently skipped | Verification report |
| 6 | Release | Put it into use | A release record names the revision, the requirements included, and the known limits | Release record |
| 7 | Support | Keep it correct | Changes flow through the change loop, and retired requirements are marked with a date and reason | Change log and revisions |

Three properties matter more than the phase names:

- **Phases can be skipped, but not silently.** A small product can pass through Intake,
  Design, and Spec in one session. Skipping is allowed; failing to record that it was
  skipped is not, because the next agent cannot distinguish a skipped gate from a passed one.
- **Phases can overlap.** Support for a live product and Design for its next capability run
  at the same time, on the same board.
- **A phase can be re-entered.** Verify discovering a missing requirement returns the work
  to Spec, and that return is recorded rather than treated as a failure.

### 3.2 Product status vocabulary

| Status | Meaning | New work allowed? |
| --- | --- | --- |
| `concept` | Being assessed, not committed | Intake only |
| `active` | In a build phase | Yes |
| `paused` | Deliberately stopped, with the reason and the resume condition recorded | No |
| `live` | Released and in use | Only through the change loop |
| `support` | In use with change control only, no new capability | Only through the change loop |
| `retired` | No longer maintained, kept for reference | No |

The board already has `active`, `on_hold`, and `archived`. This vocabulary extends it, so
the migration has to be explicit: `on_hold` maps to `paused`, and `archived` maps to
`retired` unless a product is genuinely still in use, in which case it maps to `support`.
Mapping the existing rows is a task, not an assumption.

## 4. The change-control loop

This is the requirement the owner described as "each feature change along the way will go
through a strong process to ensure our build is updated correctly." It is the heart of this
document.

The rule: **a change that alters observable behavior, an acceptance criterion, or a
constraint passes through all seven steps, in order, and each step leaves a record.**

| Step | Name | What it produces | Who can do it |
| --- | --- | --- | --- |
| 1 | Request | A change request naming what should change and why, and which requirement IDs it touches | Any participant |
| 2 | Impact | An analysis naming the requirements, acceptance criteria, tasks, phases, and code the change touches, including what it breaks | Any participant, reviewed before step 3 |
| 3 | Decide | Approve, reject, or defer, with the reasoning. A change to scope needs the owner's approval, and a peer vote cannot substitute for it | The owner for scope; an orchestrator for the rest |
| 4 | Revise the spec | A new specification version. The revision is explicit, dated, and carries a change-log line. The old clause is never silently overwritten | The owner or a delegated author |
| 5 | Create the work | Tasks linked to the changed requirement IDs, with the acceptance criteria that will close them | An orchestrator |
| 6 | Verify | The changed clauses are walked against their acceptance criteria and reported per clause | A reviewer who did not write the change |
| 7 | Trace | The delivered change cites the requirement IDs and the specification revision it satisfies | The implementer |

Step 2 is the step that is usually missing from such processes, and it is the one that
prevents the failure the predecessor project recorded as `L026`: a claim that was true as
an observation but wrong as a classification, because nobody checked what it superseded.
Impact analysis is where "what does this break" gets answered before the change, not after.

Step 4 is why a specification is a versioned artifact rather than a wiki page. A
requirement ID is permanent, but the clause behind it can be revised. Both facts have to
hold at once, which means the revision history is part of the requirement, not separate
from it.

## 5. The small-change path

The loop above will be abandoned if it applies to everything. Two pieces of evidence, one
from the owner's own recorded operating rule and one from the references:

- The predecessor project records the owner's direction: "make sure as an operating rule we
  are not over complicating simple things" and "this costs me time."
- `claude-mem` ships a `code--chill` mode that "records fewer observations, keeping only
  what would be painful to rediscover," because capturing everything was too much.
- spec-kit's own guidance is to "start with the smallest change that meets your needs."

So the loop has a threshold, and the threshold is about **observable behavior**, not size
or effort:

| Change | Path |
| --- | --- |
| Alters observable behavior, an acceptance criterion, or a constraint | Full loop, all seven steps |
| Alters what the product is for, who it serves, or what is out of scope | Full loop, and step 3 requires the owner |
| Corrects a typo, a link, a formatting error, or a stale example | Direct edit with a change-log line. No loop |
| Adds a test, a comment, or a clarification that changes no behavior and no criterion | Direct edit with a change-log line. No loop |
| Refactors internals with behavior provably unchanged | Direct edit, provided the evidence that behavior is unchanged is stated |

The judgement call is deliberately narrow: if a person cannot tell whether behavior
changed, the change takes the full loop. Guessing "probably just a cleanup" is exactly how
a specification drifts from a build.

A project can also record its own threshold, and a project's own rule wins inside that
project.

## 6. Traceability

The loop is only worth running if the chain can be walked. The chain has four links:

```
requirement ID  ->  task  ->  deliverable or revision  ->  acceptance evidence
```

Requirements for the chain:

| ID | Requirement |
| --- | --- |
| L-1 | Every task can name the requirement IDs it serves, and a task that serves no requirement says so explicitly |
| L-2 | Every deliverable can name the specification revision it was built against |
| L-3 | Every acceptance criterion can be walked and reported as verified, false, or unverified, per clause |
| L-4 | A requirement that no task serves is visible as uncovered rather than assumed to be done |
| L-5 | The chain is walkable in both directions: from a requirement to its evidence, and from a delivered change back to the requirement it satisfies |
| L-6 | A requirement that stops applying is marked retired with a date and a reason. It is never deleted, and its ID is never reused |

## 7. Memory and logging

The owner described this as "smart logging," with
[claude-mem](https://github.com/thedotmack/claude-mem) as the reference. That project's
approach is to capture what an agent does during a session, compress it, and inject the
relevant part into a future session.

The failure this solves is the one the predecessor project recorded as `L002`: work posted
to a shared log is invisible to an agent that is not running, and a returned deliverable sat
unread for about 13 hours. A board with an inbox fixes delivery. It does not fix *recall*,
which is what a new session needs when it asks "why is this requirement shaped this way?"

Memory is three tiers, and conflating them is what makes such systems either useless or
unaffordable:

| Tier | What it holds | Retention | Present in ACH today |
| --- | --- | --- | --- |
| **Raw** | Messages, events, task history, review rounds, lock records | Kept, with an archive threshold | Yes |
| **Distilled** | Decisions, lessons, findings, phase records, specification revisions | Kept permanently, because these are the expensive ones to rediscover | Partial: decisions exist, lessons do not |
| **Recalled** | The selected subset handed to a new session | Ephemeral, bounded by a budget | No |

Requirements:

| ID | Requirement |
| --- | --- |
| L-7 | A durable observation can be recorded during work without a separate ceremony. Recording is not the same act as posting a message |
| L-8 | An observation records where it came from, so any recalled item can be traced back to its source message, decision, or review |
| L-9 | Distillation happens when the observation is recorded, not when it is read, so a new session does not pay the compression cost |
| L-10 | Recall is scoped by project, phase, requirement ID, participant, and keyword, and it is bounded by an explicit budget rather than by "as much as fits" |
| L-11 | Recall never presents an unverified claim as established fact. An item's verification state travels with it |
| L-12 | A participant can select how much is recorded, including a mode that records only what would be painful to rediscover |
| L-13 | Retention is an explicit policy with a stated archive point, and deleting or archiving raw records never deletes distilled ones |
| L-14 | Logging never captures a secret, a credential, or a personal path. The prohibition in document 001 applies to the memory layer too |

Two honest limits to state now rather than discover later:

- **This is the largest new subsystem in this document.** The board is SQLite and the
  standard library. Recall by meaning, rather than by keyword, needs either an embedding
  model (which means a dependency and possibly a local model server) or a deliberate
  decision to accept keyword and structured retrieval only. That choice is decision LD-3.
- **Automatic capture is a privacy decision, not a convenience feature.** A hook that
  records session activity is reading a person's working session. It must be off by default
  and enabled deliberately per client, consistent with how consultations are already handled.

## 8. Skills

The owner described this as each section being "cleanly written for quick reference," with
[jakubkrehel/skills](https://github.com/jakubkrehel/skills) as the reference. In that
repository a skill is a named procedure with a defined output: `better-accessibility`
reviews keyboard and focus behavior, `interface-review` reviews a change for regressions,
and each one states what it consumes and what it returns. Some are model-invoked and some
are explicitly user-invoked.

Applied here, a skill is the executable form of a phase gate or a loop step. It is what
turns a specification into something an agent can actually run, which is the difference
between a document and a process.

| Skill | Purpose | Consumes | Returns | Invoked by |
| --- | --- | --- | --- | --- |
| `ach-intake` | Assess whether an idea is worth building | An idea and its constraints | A go, needs-clarification, or kill decision with reasoning | Human or agent |
| `ach-brief` | Produce or revise a design brief | Owner intent and open questions | A brief in the house format | Agent |
| `ach-spec` | Produce or revise requirements | A brief | Requirements with IDs, states, and acceptance criteria | Agent |
| `ach-plan` | Sequence the work | A specification | Tasks mapped to requirement IDs | Agent |
| `ach-impact` | Analyse what a proposed change touches | A change request and the current specification | A written impact analysis, including what breaks | Agent |
| `ach-change` | Run the full change loop | An approved change request | A revision, tasks, and a trace line | Agent |
| `ach-verify` | Walk acceptance criteria | A specification revision and a build | Per-clause verified, false, or unverified | A reviewer who did not write the change |
| `ach-gate` | Test a phase exit gate | A phase and its artifacts | Pass, or the specific unmet clause | Agent |
| `ach-advisory` | Convene an adversarial review | An artifact and a named model pool | Independent findings and a compiled result | Human or agent |
| `ach-release` | Record a release | A verified build | A release record with revision, requirements, and limits | Human |

Requirements:

| ID | Requirement |
| --- | --- |
| L-15 | A skill states its name, purpose, input, output, and who may invoke it, in a form an agent can discover without being told |
| L-16 | A skill that changes state says so, and a skill that spends money or calls an external model says so |
| L-17 | Skills are versioned with the product, so a skill's behavior can be tied to a specification revision |
| L-18 | A skill is user-invocable when it makes a decision a model must not make alone, such as approving a scope change or recording a release |

## 9. What already exists, and what is genuinely new

This section exists because five iterations of this project already exist, and the fastest
way to waste the next six months is to rebuild something that is already running.

| Capability | State today | Size of the gap | What is actually missing |
| --- | --- | --- | --- |
| Chatboard, agent names, model badges | Built | None | Nothing |
| Projects and project scoping | Built | None | Nothing |
| Project status | Partial | Small | Three values exist. Extend to the six-value vocabulary and migrate the existing rows |
| Phases with exit gates | Missing | Medium | Phase records, gate definitions, and a view that shows the current phase and what remains |
| Living specification per project | Missing | Medium | Requirements as board records with permanent IDs, states, and revisions |
| Checklist through the build | Missing | Small to medium | Derived from requirements and tasks rather than maintained by hand, or it will drift like the predecessor's status table did |
| Traceability links | Missing | Small | A task names its requirement IDs, and a deliverable names the revision it was built against |
| Change-control loop | Partial | Medium | Review rounds exist. The change request type, the impact step, and the revision step do not |
| Raw record keeping | Built | None | Messages, events, reviews, and locks are already durable |
| Distilled memory (lessons) | Partial | Small | Decisions exist. The predecessor's `LESSONS.md` pattern with enforced ids has not been ported |
| Recall into a new session | Missing | Large | This is the biggest single item in this document |
| Skills | Missing | Medium | Authoring the procedures and making them discoverable |
| Multi-workstation collaboration | Missing | Medium to large | Decision D1 in document 001. The owner's direction makes this required rather than optional |
| Advisory review | Built | None | Adversarial review rounds and the advisory module already work |
| Choosing the model pool, including local models | Partial | Large | Advisory exists, but model selection is a documented non-goal today, and only two cloud clients are wired |
| Per-project file space | Missing | Small | A shared folder per project with a defined layout |
| Easy dashboard access to projects and reviews | Partial | Medium | Decision D5 in document 001 |

Two conclusions follow, and both matter more than the list:

- **Roughly half of this is already built.** Phases, specifications, traceability, and
  recall are the real work. The board, the projects, the reviews, and the advisory are done.
- **The recall layer is the one item large enough to threaten the schedule of everything
  else.** It should be sequenced deliberately rather than assumed.

## 10. What to borrow from the references, and what to leave

Each reference is good at one thing. Copying any of them wholesale would import more
process than this product needs, which is the failure mode named in section 5.

| Reference | Borrow | Leave behind |
| --- | --- | --- |
| **spec-kit** | The phase vocabulary. The three-way assess decision of go, needs-clarification, or kill. Living specifications that evolve with the product. A per-project constitution. Its own guidance to start with the smallest change that meets the need | The full command surface, and the presets, extensions, overlays, bundles, and workflow layer. That is process for a team maintaining a process, and it is far beyond what one person and a few agents need. Also leave the per-agent duplication of every command |
| **claude-mem** | The capture, compress, then inject pipeline shape. Provenance on every remembered item. The record-less mode as a first-class setting. Its doctor command, which is a good pattern for diagnosing a broken hook | The plugin-per-client matrix. The embedding dependency before keyword retrieval has been shown to be insufficient. Its scale of storage is for an organization, not one person's workstations |
| **jakubkrehel/skills** | A skill as a named procedure with one job and a defined output. The distinction between model-invoked and user-invoked. The discipline of writing each skill so a reader knows what it consumes and returns | The plugin marketplace distribution. Keeping skills in the product repository is sufficient at this scale |

One deliberate difference from all three: this product must also serve a **human director
who approves scope**, which none of the references model. Owner approval is a first-class
step here, not an afterthought.

## 11. Open decisions

Recommendations are the spec author's advice, so the owner can accept or overrule rather
than start from a blank page.

| ID | Decision | Why it matters | Recommendation |
| --- | --- | --- | --- |
| LD-1 | Is the phase set fixed, or configurable per product? | A fixed set is simpler and comparable across products. A configurable set fits projects that genuinely differ | Configurable, shipping the default set in section 3.1. Start fixed in the data model and make it configurable only when a real project needs a different order |
| LD-2 | Does a specification live in the board, in the repository, or in both? | Traceability needs queries across requirements, tasks, and evidence. A document cannot be joined | The board holds the normative requirement rows and their states, because that is what makes traceability queryable. The repository holds the rendered document, generated from the board. One source of truth, and it is the board |
| LD-3 | Is recall keyword and structured only, or does it use embeddings? | Embeddings mean a new dependency, and possibly a local model server, which touches the standard-library-only constraint in document 001 | Keyword and structured retrieval first. Add embeddings only if keyword retrieval is shown to be insufficient on real work. This keeps the dependency count at zero until evidence demands otherwise |
| LD-4 | Does the advisory model pool include local models, and does that formally reverse the stated non-goal? | `docs/architecture.md:58` currently states that model selection is not a product capability, and only two cloud clients are wired in `ask.py` | Allow a named pool per advisory session, including local models, but record it as an explicit reversal of that non-goal. Keep the board out of choosing: the person names the pool, the board runs it and records which model produced which finding. Local models need their own adapter, which is real work |
| LD-5 | Who may author a specification revision? | Step 4 of the change loop changes what the product is. An agent that can revise a specification unreviewed can redefine its own acceptance criteria | The owner, or an agent acting under a recorded delegation. Never an unreviewed agent, and never the same participant who then verifies it |
| LD-6 | What is the archive threshold for raw records? | Retention drives storage, recall quality, and how much history a new session can see | Keep distilled records forever. Archive raw message bodies after a stated period in `live` and `support` products, with the number chosen by the owner. Needs a number before it can be implemented |

## 12. Relationship to document 001

| Topic | Document 001 | This document |
| --- | --- | --- |
| Scope | The board as a product: messages, tasks, projects, reviews, approval, install | The lifecycle of the products that board is used to build |
| Requirement prefix | `FR-`, `NFR-`, `AC-`, `D-` | `L-`, `LD-` |
| Owner of the work | The human director | The human director |
| Decisions that overlap | D1 (multi-workstation) and D5 (surface parity) are resolved in the direction this document assumes | Sections 9 and 11 depend on D1 and D5 |

The one thing this document changes in document 001: **D1 is no longer a question of
whether.** The owner's direction is that humans and agents collaborate from one or more
workstations, which makes multi-workstation support a requirement. D1 narrows to how it is
achieved, and the recommendation there remains option B.

## 13. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 8, 2026 | First draft. Phase model, status vocabulary, change-control loop with a small-change threshold, traceability requirements, the three-tier memory model, the skill set, and a gap analysis against what already exists |
