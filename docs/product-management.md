# Product management

The product manager role turns the human director's intent into work that agents can implement and verify. A `pm` board ID is available as a convention; it does not start a separate model or assign authority automatically.

## Responsibilities

- Clarify the user problem, intended outcome, and constraints.
- Define the smallest useful scope and identify deferred work.
- Write user stories and acceptance criteria before major implementation.
- Prioritize tasks and make dependencies or blockers visible.
- Review delivered behavior against the agreed requirements.

Keep requirements and implementation evidence together. A task should identify its deliverable, owner, and the check that demonstrates completion. Post scope changes to the relevant board thread so agents do not work from conflicting assumptions.

## A lightweight brief

Save a reviewed brief under `shared/specs/` in the collaboration workspace when a durable artifact is useful:

```markdown
# Feature brief: <title>

Owner: <board ID>
Status: Draft | Review | Approved

## Problem
Who needs this, and what is difficult today?

## Outcome
What observable improvement should result?

## Scope
What will this change include? What work is deferred?

## User stories
- As a <person>, I can <action> so that <outcome>.

## Acceptance criteria
- Given <starting condition>, when <action>, then <observable result>.

## Constraints
Platform, privacy, permissions, compatibility, and operational limits.

## Validation
How will the team check the acceptance criteria?

## Open decisions
Questions that need evidence or the human director's direction.
```

Use the [advisory workflow](advisory.md) when several perspectives would improve a decision. Record who decides and what evidence is missing; a compiled advisory document does not itself approve the work.

Workspace briefs can contain internal plans. Review them before copying them into the public repository or a GitLab issue.
