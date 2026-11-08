# Azure cutover: answer and plan

Owner: human director (Kenny Wallace)
Status: Draft for owner review
Version: 0.1
Date: November 8, 2026
Origin: dated finding U1 in [document 003](003-consultation-and-model-routing.md)
Verified against: `caai-main-group/caai-agents` at `main`, and the Azure subscription
`Azure subscription 1` (`fed1baa1-135f-428f-81c0-b776c15459e8`, state Enabled) through the
`az` CLI on November 8, 2026

## 1. The question

`caai-agents` records that $5,000 of Azure startup credits expire **2026-12-20**, with a
cutover merge request scheduled for **2026-12-08**. That is 30 and 42 days away. The
question was whether this is an urgent live migration.

## 2. Answer

**The deadline is real. The migration is not.** There is nothing to cut over.

The platform that the cutover plan protects was never built. The Azure resource the plan
swaps away from does not exist. And the certification suite the plan says to re-run before
promoting has no runner.

This is a **document obligation, not a live migration**. Acting on it as written would mean
migrating a non-existent deployment off a non-existent endpoint.

## 3. Evidence

Every row below was checked directly rather than inferred from the PRD's own description.

| What the PRD or a profile claims | Verified state on November 8, 2026 |
| --- | --- |
| Endpoint `https://catalyst-applied-ai-openai.openai.azure.com/`, in all five profiles | **Not present.** Six AI resources exist in the subscription and none is named `catalyst-applied-ai-openai`. The names present are `Openaiapforcaii`, `openaicaii05022026`, `speech`, `kenny-mqmynvh6-eastus2`, `kenny-mqmyn2vy-eastus2`, and `ai-kennywallace3840ai711782889954` |
| Deployments `gpt-5.4-pro` and `gpt-5.3-codex` | **Do not exist.** The subscription's actual deployments are `gpt-5` (version 2025-08-07) and `text-embedding-3-small` (version 1) |
| Key Vault for NPE identity and the Azure API key | **Never configured.** Every URI is a literal placeholder: `https://<YOUR-KEY-VAULT-NAME>.vault.azure.net/...` |
| Platform operational on non-CUI workloads by Day 60, 2026-06-18 | **Not met.** `agents/compliance`, `agents/engineering`, `agents/evaluation`, and `agents/security` each contain a single `.gitkeep`. Only `agents/architect` has content, and that content is exams, few-shots, prompts, a syllabus, and tool recipes, not runtime code |
| Runtime implementation | **Does not exist.** The entire repository contains three CI shell hooks, one Python recipe-frontmatter validator, and one test for it. There is no router, no Hermes adapter, no certification engine, no portal |
| Cutover merge request scheduled for Day 230, 2026-12-08 | **Never opened.** The project has three merge requests in its history, all closed or merged, the most recent on 2026-05-22 and it was a scaffold fix adding a deny-list to the security profile |
| Re-run the full certification suite on cutover to catch model drift | **Not executable.** Exams exist as YAML data with a JSON schema. Nothing runs them, scores them, or writes a certification ledger |
| Promote to production only if all agents re-pass at 90 percent or better | **No production exists** to promote to |
| Every profile already routes local by default, so Azure is only an escalation | **Confirmed.** `routing.default: "local"` in the profiles that were read |
| No Azure vendor lock-in artifacts | **Confirmed.** No Azure SDK usage exists in the repository |

Timeline arithmetic, for context: the first commit is dated 2026-04-18, so the repository
went dormant on 2026-05-22 at roughly **Day 33 of a 60-day plan**, with one of five agents
partially authored and no runtime code.

## 4. What the cutover actually reduces to

| Step as written in the PRD | What it actually is |
| --- | --- |
| Replace the Azure block with an Anthropic block in each profile | **Five YAML files.** `architect.yaml` already contains an `anthropic` block, so it is four additions plus one review |
| Re-run the full certification suite to catch model drift | **Not possible.** No runner exists. This step is a plan for a system that was never assembled |
| Promote to production only on two consecutive clean passes | **Not applicable.** There is no production |
| Verify no Azure vendor lock-in was introduced | **Already true**, and verifiable by inspection in minutes |

So the migration itself is a small documentation edit. The 30-day window is more than
sufficient for it. It is not sufficient to build four agents, a router, a certification
engine, and a Hermes adapter, and it should not be spent trying.

## 5. What actually needs attention, in order

| Priority | Action | Why |
| --- | --- | --- |
| P1, this week | Establish what the subscription is actually costing, and whether the $5,000 credits are still available | The subscription is live with **12 resources in `caai-ops-rg`** plus resources in three other groups, including six AI resources on standard-tier SKUs. Those bill. If credits are being consumed by something other than the platform the PRD describes, then the real deadline belongs to a different project and nobody is watching it |
| P2, this week | Decide what `catalyst-applied-ai-openai` was meant to be | The cutover plan is written against a resource that does not exist. Either it was never created, or it was renamed and the plan is stale. Until this is answered, the plan cannot be executed as written |
| P3, before 2026-12-08 | Correct the document, or mark the plan not applicable | Either perform the five-file edit, or record that the plan does not apply and why. Leaving a dated, unexecutable obligation in a dormant repository is how it gets discovered later as a false emergency, which is what happened here |
| P4, before 2026-12-08 | Make the real decision: revive, harvest, or retire `caai-agents` | This is decision MD-2 in document 003. The deadline is not a migration deadline, it is a "decide what this platform is" deadline |

## 6. Decisions

| ID | Decision | Recommendation |
| --- | --- | --- |
| AD-1 | Is the cutover executed as written, or marked not applicable? | Mark it not applicable, and record the reason. Then, separately, apply the Anthropic block to the four profiles as a correctness fix rather than a migration, so the profiles describe a coherent design instead of a dead endpoint |
| AD-2 | Does the `catalyst-applied-ai-openai` resource need to exist? | No. The profiles should point at a resource that is actually deployed, or at the local default that already exists. Referencing an invented endpoint is worse than referencing none, because it reads as configured |
| AD-3 | Is the platform revived to meet the credit deadline? | No. The deadline does not require a platform. Reviving it is a scope decision on its own merits, and 30 days is not a plausible schedule for four agents plus a router plus a certification engine |
| AD-4 | What is the disposition of the `caai-agents` assets? | Harvest the red-team suites, the six schemas, and the eight `_shared` protocols into the active product, keep the PRD as a design record, and retire the empty agent directories. This is MD-2, restated with a date attached |

## 7. What I did not do

No Azure resource was created, modified, or deleted. No cost or budget query was run beyond
listing resources, so no spend figure is claimed here. No secret value was read, including
the contents of the tracked `.env` files in `caai-ops`. No repository was written to. No
model call was made.

## 8. Change log

| Version | Date | Change |
| --- | --- | --- |
| 0.1 | November 8, 2026 | First draft. Establishes that the Azure cutover is a document obligation rather than a live migration, with the subscription and repository evidence for each claim, and four decisions |
