# Principle Inventory

This inventory is the canonical starting principle set for the repo principle
audit system.

Each principle includes:

- `principle_id`
- `principle_name`
- `audit_family`
- `canonical_source`
- `review_question`
- `scoring_rubric`
- `evidence_surfaces`

## Contract Coherence

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `CC-01` | contract-first coherence | `contract_coherence` | `AGENTS.md` | Does the repo preserve contract-first coherence when making bounded changes? | Score by whether contract boundaries outrank local convenience in doctrine and implementation. | `AGENTS.md`, pipeline contracts, recent bounded fixes |
| `CC-02` | explicit overlap resolution | `contract_coherence` | `docs/architecture/ARCHITECT-OPERATING-GUIDE.md` | When new systems overlap older ones, does the repo explicitly decide keep, narrow, supersede, or retire? | Score by whether overlap is resolved in doctrine and current system docs rather than left ambiguous. | architecture docs, overlapping system docs, campaign writebacks |
| `CC-03` | distinct truth surfaces | `contract_coherence` | `docs/architecture/ARCHITECT-OPERATING-GUIDE.md` | Does the repo keep different truth surfaces distinct instead of letting them carry the same meaning indefinitely? | Score by whether code truth, artifact truth, operator truth, and proving truth stay differentiated. | dynamic templates, proving artifacts, operator surfaces |
| `CC-04` | system minimization before expansion | `contract_coherence` | `docs/architecture/SYSTEM-VETTING-AND-MINIMIZATION.md` | Are new systems added only when they are distinct, reusable, and cheaper than prompt memory? | Score by whether system additions are justified by clear triggers, outputs, and reuse. | minimization doctrine, new system docs, recent campaigns |

## Proving Economics

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `PE-01` | cheapest trusted loop first | `proving_economics` | `docs/architecture/DIRECTOR-OPERATING-RULES.md` | Does the repo choose the cheapest trusted proving surface before more expensive loops? | Score by whether lower-cost trusted routes are used first in doctrine and recent campaigns. | director rules, campaign artifacts, proving traces |
| `PE-02` | strict lane-trust gate | `proving_economics` | `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md` | Does hard-family or other expensive proving remain blocked until lane trust is green enough? | Score by whether lane-trust is explicit, enforced, and reflected in campaign behavior. | economics law, canary artifacts, hard-family campaigns |
| `PE-03` | rerun gate law | `proving_economics` | `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md` | Are reruns justified through evidence, control, decision, trust, and scope gates? | Score by whether reruns show concrete gate reasoning instead of vague retry logic. | economics law, proving-authority reviews, prompt evaluations |
| `PE-04` | blocker localization below suite level | `proving_economics` | `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md` | Does the repo localize blockers below suite level before spending expensive end-to-end proving budget? | Score by whether campaigns narrow blockers below suite level before hard-family spend. | economics law, campaign logs, blocker writebacks |
| `PE-05` | no expensive loop doing multiple jobs | `proving_economics` | `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md` | Does the repo avoid using one expensive run to diagnose trust, localize blocker, validate fix, and prove outcome all at once? | Score by whether loop roles stay separated in practice. | economics law, tranche summaries, proving artifacts |

## Dynamic Campaign Governance

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `DC-01` | active prompt canonical | `dynamic_campaign_governance` | `AGENTS.md` | Do active prompt pointers behave as the canonical live execution surface? | Score by whether campaigns keep `ACTIVE-PROMPT.md` truthful and current. | campaign folders, active prompt files, logs |
| `DC-02` | next prompt provisional | `dynamic_campaign_governance` | `AGENTS.md` | Does the repo treat the next prompt as provisional until current evidence keeps it alive? | Score by whether live prompt mutation follows evidence rather than seed order. | AGENTS, templates, prompt histories |
| `DC-03` | prompt completion vs program continuation | `dynamic_campaign_governance` | `AGENTS.md` | Does the repo distinguish finishing one prompt from continuing the wider program? | Score by whether campaigns continue correctly instead of pausing at prompt boundaries. | AGENTS, campaign logs, prompt reviews |
| `DC-04` | compact reviewability required | `dynamic_campaign_governance` | `AGENTS.md` | Do campaigns leave compact review surfaces that avoid prompt archaeology? | Score by whether summaries, reviews, closeout, and architect brief stay live and useful. | templates, campaign outputs, review summaries |
| `DC-05` | explicit stop gate | `dynamic_campaign_governance` | `AGENTS.md` | Are campaign stops controlled by explicit gates rather than convenience or fatigue? | Score by whether stop conditions are stated and obeyed. | AGENTS, campaign closeouts, architect briefs |
| `DC-06` | dynamic campaigns not static prompt lists | `dynamic_campaign_governance` | `AGENTS.md` | Does the repo actually run dynamic campaigns as evidence-led chains rather than static seed scripts? | Score by whether later prompts are replaced, narrowed, or extended from evidence. | AGENTS, dynamic templates, live campaigns |

## Repo Hygiene And Canonical Surfaces

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `RH-01` | canonical governance surfaces | `repo_hygiene_and_canonical_surfaces` | `docs/architecture/CODEX-GOVERNANCE-SURFACES.md` | Are the repo’s execution and governance rules anchored in canonical tracked surfaces? | Score by whether recurring law lives in canonical files instead of scattered prompts. | governance docs, AGENTS, codex/tasks |
| `RH-02` | recurring law belongs in repo doctrine | `repo_hygiene_and_canonical_surfaces` | `docs/architecture/CODEX-GOVERNANCE-SURFACES.md` | Does repeated workflow law get promoted into repo doctrine instead of staying session-local? | Score by whether repeated rules are written back into durable docs. | governance docs, templates, weaknesses |
| `RH-03` | weakness register discipline | `repo_hygiene_and_canonical_surfaces` | `AGENTS.md` | Is the weakness register maintained as a living, narrowed architecture/governance memory? | Score by whether weaknesses are added, tightened, superseded, and resolved honestly. | `.agents/ARCHITECTURAL-WEAKNESSES.md`, campaigns, docs |
| `RH-04` | setup/startup alignment | `repo_hygiene_and_canonical_surfaces` | `docs/architecture/CODEX-GOVERNANCE-SURFACES.md` | Do setup and startup surfaces stay aligned with real local workflow? | Score by whether setup/startup docs and scripts match actual lane behavior. | `SETUP.md`, `setup.ps1`, `start.ps1`, lane docs |
| `RH-05` | prompt/output separation and reviewable folder shape | `repo_hygiene_and_canonical_surfaces` | `AGENTS.md` | Are prompts and outputs separated in a way that keeps campaigns operator-reviewable? | Score by whether folder shape and output homes stay legible. | dynamic campaigns tree, templates, README |

## Observability And Truth Surfaces

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `OT-01` | progress must be visible | `observability_and_truth_surfaces` | `AGENTS.md` | If progress is real, can the operator see it without asking for translation? | Score by whether repo surfaces make current state visible enough for review. | AGENTS, campaign outputs, operator artifacts |
| `OT-02` | explicit authority surfaces | `observability_and_truth_surfaces` | `AGENTS.md` | Does the repo make authority-bearing surfaces explicit instead of leaving them inferential? | Score by whether authoritative proving and truth surfaces are named and reviewable. | proving reviews, templates, run bundles |
| `OT-03` | operator truth vs code truth vs proving truth separation | `observability_and_truth_surfaces` | `docs/architecture/ARCHITECT-OPERATING-GUIDE.md` | Does the repo keep operator, code, artifact, status, and proving truth distinct? | Score by whether truth surfaces are separated in doctrine and outputs. | templates, architect briefs, proving artifacts |
| `OT-04` | compiled-binary proving vs architecture-proof separation | `observability_and_truth_surfaces` | `docs/architecture/CODEX-GOVERNANCE-SURFACES.md` | Does the repo keep compiled-binary proving distinct from architecture-proof and source-authored proof? | Score by whether proving categories stay clearly separated. | governance docs, testing strategy, suite artifacts |

## Agentic Workflow Governance

| principle_id | principle_name | audit_family | canonical_source | review_question | scoring_rubric | evidence_surfaces |
| --- | --- | --- | --- | --- | --- | --- |
| `AW-01` | GM of active truth | `agentic_workflow_governance` | `AGENTS.md` | Does the parent thread actually operate as GM of active truth rather than a passive executor? | Score by whether branch choice, blocker ranking, and synthesis stay parent-owned. | AGENTS, campaign artifacts, agentic docs |
| `AW-02` | bounded specialist roles | `agentic_workflow_governance` | `AGENTS.md` | Are specialist roles bounded, decision-distinct, and kept inside real ownership surfaces? | Score by whether role boundaries are explicit and reused honestly. | role contracts, registry, evals |
| `AW-03` | default dispatch when authorized | `agentic_workflow_governance` | `AGENTS.md` | When delegation is authorized, does the repo use fitting specialist roles by default? | Score by whether real work uses existing roles instead of regressing to monolithic execution. | AGENTS, agent registry, live tasks |
| `AW-04` | branch choice stays in parent thread | `agentic_workflow_governance` | `AGENTS.md` | Does the parent thread keep branch choice and final synthesis instead of delegating them away? | Score by whether sidecars stay bounded and synthesis remains local. | AGENTS, role contracts, campaign artifacts |
| `AW-05` | roles continuously evaluated | `agentic_workflow_governance` | `AGENTS.md` | Are specialist roles treated as continuously evaluated workflow components instead of static prompt ideas? | Score by whether contracts, evals, registry state, and lifecycle updates stay current. | registry, eval loop, role contracts |
| `AW-06` | monolithic-bias correction | `agentic_workflow_governance` | `AGENTS.md` | Does repo doctrine explicitly counter Codex’s bias toward keeping too much work local? | Score by whether the bias is named and corrected in operational law. | AGENTS, templates, dispatch records |
| `AW-07` | event-bound dispatch law | `agentic_workflow_governance` | `AGENTS.md` | Are key specialist roles triggered by concrete events instead of vague “fit” language alone? | Score by whether event-bound dispatch is stated and can be audited. | AGENTS, dynamic templates, audit surfaces |
