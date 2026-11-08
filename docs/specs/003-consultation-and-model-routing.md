# Consultation, advisory, and model routing

Owner: human director (Kenny Wallace)
Status: Draft for owner review
Version: 0.1
Date: November 8, 2026
Companions: [001 Product specification](001-product-spec.md), [002 Project lifecycle](002-project-lifecycle.md)
Origin: owner request of November 8, 2026 for advice on consultation, plus a review of the
GitLab repositories under `caai-main-group` and `kennethwallace21-sys`

## 1. Problem

Three separate designs for reaching a model already exist across this owner's repositories,
and none of them knows about the others. That is the actual problem. "Consultation" is not
one missing feature; it is three competing implementations and one ambiguous word.

The word is the first thing to fix. In this owner's material, "consultation" is used for at
least three different operations with different costs, different lifetimes, and different
evidence value:

| The word means | Implementation that exists | What it actually does |
| --- | --- | --- |
| A fresh single question to one model | `ask.py` in this repository | Starts a headless client process, sends one prompt, posts one answer |
| Several independent perspectives on a decision | `advisory.py` in this repository | Records a session, collects one response per participant, compiles a briefing |
| An adversarial suite run against an artifact | `red_team/` in `caai-agents` | Versioned, schema-validated attack items run against a target |

Calling all three "consultation" is why the requirements keep moving. They have different
trigger conditions, different stopping rules, and different outputs. Document 002 already
separates them by naming only one skill `ach-advisory`; this document separates them
explicitly.

## 2. What already exists

This is the inventory that matters, because the fastest way to waste the next six months is
to build a fourth design.

| Repository | Artifact | What it provides |
| --- | --- | --- |
| Agent Collab Hub (this repo) | `ask.py`, 347 lines | Two adapters only: `run_claude` and `run_codex`, each spawning an installed CLI as a subprocess. Opt-in via `COLLAB_ALLOW_CONSULTS=1`. Limits: 2 concurrent, 10 starts per rolling hour. Prompt cap 32,000 characters, timeout cap 3,600 seconds |
| Agent Collab Hub (this repo) | `advisory.py` | Multi-round collection and compilation with an atomic state file and a corruption guard |
| `caai-ops` | `caai/llm_client/llm_client.py`, 597 lines | A unified chat and embedding client over Ollama, OpenAI-compatible endpoints, NVIDIA NIM Cloud, and Gemini. A documented 4-tier inference chain |
| `caai-ops` | `caai/agents/claude_escalation.py`, 374 lines | Confidence-gated escalation to Claude Code as a subprocess below a 90 percent threshold, with opus, sonnet, and haiku tiering and complexity heuristics. Logs every escalation to a training store |
| `caai-ops` | `caai/trust_layer/` | `guard.py`, `nemo_guard.py`, `confidence.py`, `response_policies.py` |
| `caai-agents` | `config/profiles/*.yaml` | Five declarative agent profiles with per-tier routing enforcement and per-call approval gates |
| `caai-agents` | `agents/_shared/tier_routing_rules.md` and 7 siblings | Tier routing rules, critical-fail codes, anti-hallucination rules, write-safety protocol, NPE identity protocol |
| `caai-agents` | `red_team/`, 6 suites | Prompt injection, citation traps, tool misuse, scope confusion, social-engineered approvals, data exfiltration. Schema-validated with anti-contamination CI |
| `caai-agents` | `caai_prd_and_implementation_checklist.md`, 1,332 lines | A PRD with a revision log, phase structure, certification gates, and a model cutover plan |

**Two of these are substantially the same product as this repository.** `caai-ops` lists as
its first product a "CAAi Agentic Orchestrator App for internal agent mission control,
unified dashboard for managing CAAi's agentic workforce, tracking pipeline, approvals, and
infrastructure health." That is what Agent Collab Hub is. And `caai-agents` contains the
lifecycle model that document 002 specifies, including phases, gates, a revision log, and a
checklist. Both are dormant.

## 3. Separate the three operations

The recommendation is to keep all three, name them differently, and never let one silently
stand in for another.

| Operation | Question it answers | Independence | Cost shape | Output |
| --- | --- | --- | --- | --- |
| **Consultation** | What does a fresh model say about this one question? | Fully independent, no board context | One call | One answer, attributed to one model |
| **Advisory** | What do several perspectives say, and where do they disagree? | Independent first passes, then reconciled | N calls | A briefing with recorded disagreements |
| **Red team** | Does this artifact survive a known class of attack? | Adversarial by construction, reusable | Suite run, mostly local | Pass or fail per item, with a critical-fail code |

| ID | Requirement |
| --- | --- |
| M-1 | The three operations are distinct commands with distinct records. A consultation is never recorded as an advisory session, and a red-team result is never recorded as a review |
| M-2 | Every operation records which model produced which finding, so agreement between two runs of the same model is not mistaken for corroboration |
| M-3 | A consultation states whether the context sent to the model left the machine |

## 4. Which operation to use when

The most common mistake with these tools is reaching for the expensive one. A practical
rule set:

| Situation | Use | Why not the others |
| --- | --- | --- |
| An agent is connected and can answer on the board | The board itself | A consultation burns credits to recreate a conversation the board already has. This repository's own guidance says connected agents exchange reviews on the board without the helper |
| One narrow question with a checkable answer | Consultation | Advisory is overkill for a single question |
| A decision with real tradeoffs and no obvious answer | Advisory | One model's opinion is not a decision input on its own |
| A specification, or a security-sensitive artifact | Red team, then advisory | An advisory asks for opinions. A red-team suite asks whether a known attack class succeeds, which is a different and stronger test |
| Verifying a delivered change against acceptance criteria | A review round on the board | Consultation starts a fresh session with no history, so it cannot see the criteria unless they are pasted in |

| ID | Requirement |
| --- | --- |
| M-4 | The board is the default review path. A consultation is the exception, used when no connected participant can answer or when an independent perspective with no board context is specifically wanted |
| M-5 | A consultation prompt states the question, the artifact, and the criterion for a useful answer. A consultation without a stated criterion cannot be marked as verified evidence |

## 5. Choosing the model pool

Two rules, and the second one is the one people skip.

**Rule one: diversity by provider beats depth within one provider.** Three runs of the same
model, or of two models from the same vendor, are close to one opinion. This repository's
own review guidance already says that agreement between models does not establish that a
claim is true. A pool that can actually disagree is worth more than a pool that is
individually stronger.

**Rule two: order the pool by cost, and escalate on evidence rather than on feel.**
`caai-ops` already implements exactly this: a local model answers first, and escalation to a
larger model happens only when measured confidence falls below a threshold. That is the
right shape and it should not be reinvented.

Recommended pool shape, three tiers:

| Tier | Runs where | Cost | Role in a review |
| --- | --- | --- | --- |
| Local | On the workstation, via Ollama or a local server | No per-call cost, nothing leaves the machine | The bulk of the work, and the default reviewer. Also the only tier allowed to see restricted content |
| Mid cloud | Hosted, one provider | Low per call | Second opinion on anything the local tier was unsure about |
| Frontier cloud | Hosted, a different provider from the mid tier | High per call | Reserved for one-way-door decisions, and always approval gated |

| ID | Requirement |
| --- | --- |
| M-6 | A model pool is named explicitly for each session. The board never silently substitutes a model, and a run records the model it actually used |
| M-7 | The pool is ordered local first, and escalation to a paid tier requires a stated reason or a measured confidence threshold |
| M-8 | A frontier-tier call is approval gated, consistent with the pattern already recorded in `caai-agents` where every such call requires the owner's explicit approval |
| M-9 | Restricted content is answered only by a tier that does not send it off the machine |

## 6. Protecting independence

The value of an adversarial review comes entirely from the reviewers not having coordinated.
This is easy to lose by accident.

| ID | Requirement |
| --- | --- |
| M-10 | A reviewer records its first assessment before it can see another reviewer's assessment for the same artifact and round |
| M-11 | A consultation starts with no board history, and its prompt is not seeded with another reviewer's findings |
| M-12 | Contamination is checked mechanically where it can be. `caai-agents` already has the right pattern: a CI job that fails if a red-team item's text appears in any agent's prompt library |
| M-13 | A review budget is agreed before the round starts, and exhausting it escalates rather than silently continuing |

## 7. Adapter architecture

`ask.py` reaches models by spawning an installed client as a subprocess. There are two
adapters, `run_claude` and `run_codex`. Adding each new model as another subprocess adapter
is the wrong direction: every client has its own command line, its own output shape, and its
own failure modes, so the adapter count grows with the model count.

`caai-ops` already solved this problem correctly. Its `llm_client.py` speaks one protocol
over HTTP and reaches Ollama, OpenAI-compatible endpoints, NVIDIA NIM Cloud, and Gemini
through it. That is the pattern to copy.

**Recommended shape for `ask.py`:**

| Adapter | Reaches | Keeps |
| --- | --- | --- |
| Subprocess, Claude | Claude Code, on the subscription rather than per-token billing | Existing |
| Subprocess, Codex | Codex, on the owner's chosen model | Existing |
| **HTTP, OpenAI-compatible** | Ollama locally, and any hosted or local server exposing that API: NIM, OpenAI, Azure OpenAI, vLLM, llama.cpp, LM Studio | New |

One HTTP adapter covers every local and most hosted models, because the OpenAI chat
completions shape is the de facto interface. That turns "which models can review" from a code
question into a configuration question, which is what the owner asked for.

**One constraint to respect.** This repository's non-functional requirement NFR-3 is Python
3.10 or later with the standard library only. `caai-ops` uses `requests` and `python-dotenv`.
So the adapter must be written with `urllib.request`, not imported. That is roughly sixty
lines, and it is the price of keeping the dependency count at zero.

| ID | Requirement |
| --- | --- |
| M-14 | Adding a model is a configuration change, not a code change, for any model reachable over an OpenAI-compatible endpoint |
| M-15 | The consultation adapter uses the Python standard library only. It does not import a third-party HTTP client or dotenv |
| M-16 | An adapter reports whether a call was billed per token or absorbed by a subscription, so a cost estimate is possible without a currency budget |
| M-17 | A model that fails is reported as failed, with the reason. It is never silently replaced by a different model |

## 8. Reconciliation findings from the GitLab review

The review covered 14 GitLab repositories: 12 under `caai-main-group` and 2 under
`kennethwallace21-sys`. Findings that change the plan:

| # | Finding | Consequence |
| --- | --- | --- |
| G1 | `caai-ops` lists a "CAAi Agentic Orchestrator App for internal agent mission control" as its first product, with `products/agentic_orchestrator/app.py` and `caai/orchestrator/agent_mcp.py` | This is substantially the same product as Agent Collab Hub. Either they are deliberately different audiences, or one is redundant. This needs a decision, not an assumption |
| G2 | `caai-agents` contains a 1,332-line PRD with a revision log, phase structure, certification gates, and a checklist | Document 002 specifies from scratch what this repository already designed. Harvest before building |
| G3 | `caai-agents/red_team/` holds 6 schema-validated attack suites with anti-contamination CI | Genuinely valuable and not duplicated anywhere else. This is the strongest asset found in the review |
| G4 | `caai-agents/schemas/` holds 6 JSON schemas for exam items, few-shots, profiles, red-team items, source registries, and tool recipes | Reusable as-is for any artifact that needs validating |
| G5 | `caai-agents/agents/_shared/` holds 8 protocol documents including tier routing rules, critical-fail codes, and a write-safety protocol | Reusable governance text. Portable to ACH without modification |
| G6 | `caai-ops/caai/llm_client/llm_client.py` and `caai/agents/claude_escalation.py` implement local-first routing with confidence-gated escalation | The consultation design in section 7 should copy this pattern rather than invent another |
| G7 | `caai-agents/red_team/README.md` documents a file, `opus_approval_bypass.yaml`, that is not present on `main` | A documentation-versus-artifact drift of exactly the class document 002 is built to prevent. Worth citing as the motivating example |
| G8 | `caai-agents` was last active 2026-05-22 and `caai-ops` on 2026-10-18 | Both dormant. Neither is being maintained while new work happens elsewhere |

## 9. Time-critical and security findings

These are outside the consultation topic but were found during the same review, and two of
them are dated.

| # | Finding | Why it matters now |
| --- | --- | --- |
| U1 | `caai-agents` records that $5,000 of Azure startup credits expire **2026-12-20**, with a cutover merge request scheduled for Day 230, which its own timeline dates **2026-12-08** | That is **30 days** to the scheduled cutover and **42 days** to expiry, in a repository last touched 2026-05-22. The plan requires replacing the Azure block in each of five agent profiles and re-running the full certification suite. Nobody is tracking this, and after expiry the plan says local Gemma becomes the sole model for routine work |
| U2 | `caai-agents` targeted a Day 60 milestone of **2026-06-18** and went dormant **2026-05-22** | The target was missed by roughly four weeks of activity and then abandoned. Whether it is revived or harvested, the dated commitments inside it are now stale and should not be quoted as live |
| U3 | `caai-ops` has `.env.nim-cloud` and `.env.trt-local` tracked at the repository root, alongside `logs/`, `data/`, `datasets/`, `pyright_output.json`, and `nvidia_output.txt` | Tracked environment files in a repository are a credential exposure pattern. The predecessor project's own lesson `L009` is exactly this: secrets ended up in a place that syncs or publishes. **I did not read the contents of these files.** They should be checked, and if they hold live keys, those keys should be rotated rather than just untracked, because a Git history keeps them |
| U4 | 14 GitLab repositories exist across two namespaces, and no single index states what each one is or whether it is alive | This is the concrete form of the problem document 001 section 1 describes. `caai_website` is public while its 11 siblings are private, which is a distinction worth confirming is deliberate |
| U5 | `caai-ops` and `caai-agents` both contain model-access code, and this repository contains a third | Three implementations of one capability. Without a decision, a fourth will be written |

## 10. Open decisions

| ID | Decision | Recommendation |
| --- | --- | --- |
| MD-1 | Which product owns agent orchestration: Agent Collab Hub, or the Agentic Orchestrator App inside `caai-ops`? | Keep both, but on a stated boundary. ACH is for cross-vendor agent collaboration on a person's own machine. The `caai-ops` orchestrator is for CAAi's own internal agent workforce and its business products. If they genuinely overlap, retire one rather than maintaining both |
| MD-2 | Is `caai-agents` revived, harvested, or retired? | Harvest, then retire. Take the red-team suites, the six schemas, and the eight `_shared` protocols into ACH. The 1,332-line PRD is a design record worth reading and keeping, but its dated commitments are stale and its agent lineup duplicates the `caai-ops` registry |
| MD-3 | Does Agent Collab Hub stay standard-library-only? | Yes. It is what makes installation one command and the dependency count zero. Write the new HTTP adapter with `urllib.request` rather than importing `caai-ops`'s client, which needs `requests` and `dotenv` |
| MD-4 | Is a local model a required tier or an optional one? | Required. It is the only tier that can review restricted content, it removes per-call cost for routine review, and it is the one thing that makes the consultation feature usable at volume. `caai-ops` already runs a local model on the workstation |
| MD-5 | What is the default review budget for an adversarial round? | Two rounds, matching what `docs/reviews.md` already states, with escalation when the budget is exhausted rather than a silent continuation |
| MD-6 | Who approves a frontier-tier model call? | The owner, per call, in a structured request. `caai-agents` already specifies exactly this for its highest tier, so the pattern exists and should be reused rather than redefined |
| MD-7 | Do tracked environment files in `caai-ops` hold live credentials? | Needs a check by the owner. If yes, rotate first, then untrack. Untracking alone does not remove a secret from Git history |

## 11. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 8, 2026 | First draft. Separates consultation, advisory, and red team; inventories the three existing model-access designs; recommends a single OpenAI-compatible HTTP adapter under the standard-library constraint; records 8 reconciliation findings and 5 time-critical or security findings from the GitLab review |
