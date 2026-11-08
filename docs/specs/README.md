# Specifications

Normative product and system specifications for Agent Collaboration Hub (ACH).

## Why this folder exists

Before these files, the product definition was distributed across four places that
disagree in detail:

| Place | What it stated | Why it is not sufficient |
| --- | --- | --- |
| `README.md` | Public framing and capability table | Marketing register, no requirement IDs, no acceptance criteria |
| `docs/architecture.md` | What the code currently does | Descriptive, not normative. It cannot say a behavior is wrong |
| `CODEX_HANDOFF.md` | One machine's operating state on one date | Operational and machine-specific. Local only since 3.0.0 and no longer in the repository, because it carries install paths, process ids, board ids, and dated orchestration notes |
| The predecessor protocol | A predecessor PowerShell protocol (v2) | Different system, different stack, still in daily use for other projects |

A specification states what the product must do. When code and a specification
disagree, that disagreement is a defect in one of them and must be resolved
deliberately, not by whichever file a reader happened to open.

## Documents

Two of these are public product documentation. Three describe the owner's private
portfolio and infrastructure and are deliberately local-only.

### Public, tracked in the repository

| ID | Document | Status | Scope |
| --- | --- | --- | --- |
| 001 | [Product specification](001-product-spec.md) | Draft for owner review | The board as a product: problem, scope, requirements, constraints, open decisions |
| 002 | [Project lifecycle and spec control](002-project-lifecycle.md) | Draft for owner review | Phases and gates, living specifications, the change-control loop, memory, skills |
| 006 | Reconciliation with prior work | Not yet written | Inventory of every prior iteration and its disposition |

### Local only, not committed

These name private repositories, account identifiers, and infrastructure. They live in the
workspace and must not reach a public repository. See
[security and privacy](../security.md).

| ID | Document | Status | Why it is local |
| --- | --- | --- | --- |
| 003 | Consultation, advisory, and model routing | Draft for owner review | Its reconciliation section names private repositories and their internal contents |
| 004 | Azure cutover | Draft for owner review | Carries a subscription identifier, resource group names, and resource names |
| 005 | Portfolio assessment | Draft for owner review | Enumerates every private repository and its state |
| 006 | Commitments register | Living | Every dated obligation, standing prohibition, and open decision, so none becomes a false emergency |
| n/a | `portfolio-index.md` | Generated | A live index of every repository and working folder. Rerun the tool; do not edit by hand |

### Tools

`scripts/portfolio_index.py` generates the portfolio index. It is an operator tool rather
than part of the board, but it ships with the app so that this reference resolves. It reads
its sources from a local config (`portfolio-sources.json`, which is local only), so no
private namespace or owner is written into the tool itself.

```sh
py -3.12 scripts/portfolio_index.py --config docs/specs/portfolio-sources.json \
    --output docs/specs/portfolio-index.md --json docs/specs/portfolio-index.json
```

An unreachable source is reported as unreachable rather than counted as empty, because "no
repositories" and "could not ask" are different facts.

If a private document needs a public counterpart, write the public one separately and leave
the identifiers behind. Do not redact in place, because a later edit reintroduces them.

## Conventions

- Requirement IDs are permanent. `FR-` is a functional requirement, `NFR-` a
  non-functional requirement, `D-` an open decision, `AC-` an acceptance criterion.
  A requirement that stops applying is marked `retired` with a date and reason. It is
  never deleted and its ID is never reused.
- Each document prefixes its IDs so two documents cannot collide: document 001 uses
  `FR-`, `NFR-`, `AC-`, and `D-`; document 002 uses `L-` and `LD-`.
- Every requirement names the surface that satisfies it and its current state, so a
  reader can tell a promise from a shipped behavior.
- Open decisions name the evidence needed to close them and who decides. An open
  decision is not a task and does not authorize implementation.
- Specs carry no live board content, no private workspace paths, no credentials, and
  no personal identifiers. See [security and privacy](../security.md).
- Written in the brief format already prescribed by
  [product management](../product-management.md), extended with requirement IDs.
