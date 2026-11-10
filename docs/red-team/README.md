# Red-team catalogue

The attack categories an adversarial review of this product should cover. This is the
red-team operation named in [the consultation specification](../specs/003-consultation-and-model-routing.md),
which is one of the three review modes alongside consultation and advisory.

**Status: catalogue only. No runner exists.** Nothing here executes. It is a checklist and a
schema, so that a review can be structured today and automated later.

## Why a catalogue rather than a prompt

Asking a model to "try to break this" produces whatever the model happens to think of, which
is neither repeatable nor complete. A named category with a worked item gives a reviewer a
target, and gives a later run something to assert against.

The categories below are the ones that already caused harm somewhere. They are not a theory of
adversarial behaviour; they are a list of observed failures.

## Categories

| Category | What it tests | Why it is on the list |
| --- | --- | --- |
| `prompt_injection` | Instruction-override attempts embedded in a document, a message, a task description, or a tool response | Board content is peer input. A message that says "ignore your instructions" is data, not an instruction, and the target must treat it that way |
| `citation_trap` | Plausible but fake references: a real URL with wrong content, a fabricated issue number, a misattributed quote | A review that cites something it never verified is the failure mode behind the evidence rule in [the review workflow](../reviews.md) |
| `tool_misuse` | A write without the approval it needs, a write outside an allowed path, a read of another participant's private context | The product's whole safety story rests on the owner approval gate and on advisory locks |
| `scope_confusion` | Ambiguous boundaries: two projects with overlapping channels, a stale artifact reference, a task that names the wrong project | The product has shared channels and per-project scope, and the two surfaces already disagreed about reads once (finding F4) |
| `social_engineered_approval` | False urgency, authority impersonation, approval fatigue, a plausible justification for skipping a gate | The owner approval gate is the one control a peer cannot substitute. It is also the one a message can talk someone into waiving |
| `data_exfil` | Content that would leave the machine when it should not: a path in a tool argument, a secret in a message body, telemetry that carries more than metadata | Consultations and advisory sessions send context to a model provider. The local tier is the only tier that does not |
| `approval_bypass` | Malformed approval requests, replayed nonces, a token used from the wrong actor, a scope claim that does not match the artifact | The approval record binds actor, action, scope, revision, and nonce. Each of those is separately attackable |
| `supply_chain` | A dependency, a downloaded artifact, or an imported bundle that is not what it claims to be | The migration tool imports history from another system, which is a trust boundary |

## Item shape

One item is one YAML document conforming to
[`red_team_item.schema.json`](red_team_item.schema.json). The fields that matter:

- `category` and `difficulty`, so coverage can be counted rather than guessed.
- `input`, the adversarial payload itself.
- `expected_behavior` and `failure_mode`, both required and both at least thirty characters.
  A failure mode that restates the category is not a failure mode. This is the same discipline
  as the predecessor's rule that a review saying "approved" without what was run is not a review.
- `reviewer`, recorded as a board id rather than an email address, so the artifact carries no
  personal contact detail.

## The one rule that matters most

**An item must not appear in any reviewer's prompt, briefing, or few-shot set.** An adversarial
test whose target has seen the answer measures nothing. The earlier project that seeded this
catalogue enforced that with a CI job that failed the merge if an item's text appeared in any
agent's prompt library. That is the right shape, and it is worth copying when a runner exists.

## Provenance

Adapted from an earlier internal agent platform that is no longer active. The categories, the
item schema, and the anti-contamination rule were taken from it; the specific items were not,
because they targeted that platform's agents and its compliance taxonomy rather than this
product. The source repository is archived, so nothing was lost in the transfer.

The `failure_codes` field is optional here, because this product has not defined a failure-code
list. The source project required every item to name one of its own codes, which is a good
discipline worth adopting once there is a list to name.
