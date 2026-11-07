# Principle Family Audit: `agentic_workflow_governance`

- strongest_principle: `AW-01 GM of active truth`
- weakest_principle: `AW-07 event-bound dispatch law`
- recurring_failure_pattern: `the doctrine and role boundaries are strong, but dispatch-trigger enforcement is less canonical than the branch-choice and role-boundary law`
- count_of_escalations: `1`

## `AW-01`: `GM of active truth`

- principle_id: `AW-01`
- principle_name: `GM of active truth`
- score_1_to_10: `9`
- why: `The repo states this principle repeatedly and concretely, and backs it with a dedicated parent-thread-only role with explicit ownership over branch choice, stop gates, synthesis, and workflow scoring.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/GM-ORCHESTRATOR.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-GM-ORCHESTRATOR-EVAL-01.md`
- evidence_missing:
  - `No single repo-wide enforcement surface proves every governed campaign wrote GM workflow scoring and live-writeback truth at each tranche without retrofit review.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/GM-ORCHESTRATOR.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-GM-ORCHESTRATOR-EVAL-01.md`
- main_failure_mode: `The GM remains doctrinally authoritative, but workflow-quality truth can still lag in campaign artifacts and be reconstructed after the fact.`
- recommended_tightening: `Add one canonical governed-campaign gate artifact or verifier that marks GM scoring, dispatch accountability, and live writeback as satisfied or unsatisfied per tranche.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-02`: `bounded specialist roles`

- principle_id: `AW-02`
- principle_name: `bounded specialist roles`
- score_1_to_10: `8`
- why: `The repo defines recurring roles through contracts, registry entries, lifecycle state, evaluation artifacts, and disallowed behaviors, which makes specialist boundaries unusually explicit.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/SYSTEM-CONTRACT-TRACER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
- evidence_missing:
  - `No single family-level matrix shows role overlap, non-owned seams, and blocking status across the whole ecosystem in one place.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/GM-ORCHESTRATOR.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/SYSTEM-CONTRACT-TRACER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
- main_failure_mode: `Boundary drift appears when nearby reviewer roles overlap and the distinction must be recovered from several contracts and evals instead of one map.`
- recommended_tightening: `Add a family-level ownership table listing each role’s owned seam, non-owned seam, blocking mode, and nearest neighboring roles.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-03`: `default dispatch when authorized`

- principle_id: `AW-03`
- principle_name: `default dispatch when authorized`
- score_1_to_10: `7`
- why: `The law exists clearly, but it is still mostly doctrinal and template-driven rather than represented as structured dispatch metadata in the registry.`
- evidence_found:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
- evidence_missing:
  - `The registry does not carry explicit default_dispatch_when_authorized or mandatory_when_triggered fields.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
- main_failure_mode: `The parent thread can still stay monolithic on a non-trivial tranche and justify the skip later because the dispatch law is not encoded in one canonical machine-checkable surface.`
- recommended_tightening: `Extend AGENT-REGISTRY.json with structured dispatch metadata such as default_dispatch_conditions, mandatory_triggers, and skip_requires_reason.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-04`: `branch choice stays in parent thread`

- principle_id: `AW-04`
- principle_name: `branch choice stays in parent thread`
- score_1_to_10: `9`
- why: `This is one of the clearest principles in the repo. The GM is explicitly the branch selector, while reviewer and sidecar roles are additive and non-authoritative.`
- evidence_found:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/GM-ORCHESTRATOR.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
- evidence_missing:
  - `No explicit standard header on reviewer artifacts marks them as non-authoritative relative to the GM truth surface.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/GM-ORCHESTRATOR.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
- main_failure_mode: `Reviewer artifacts can become implicitly branch-shaping if the GM does not explicitly record the truth-authority surface and final branch decision nearby.`
- recommended_tightening: `Require all reviewer-owned artifacts to include a fixed authority_scope or non_authoritative_relative_to_gm field that points back to the GM-owned decision surface.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-05`: `roles continuously evaluated`

- principle_id: `AW-05`
- principle_name: `roles continuously evaluated`
- score_1_to_10: `9`
- why: `Continuous evaluation is first-class doctrine, backed by lifecycle triggers in the registry and governance doc, with a substantial body of real evaluation artifacts.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-GM-ORCHESTRATOR-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-SYSTEM-CONTRACT-TRACER-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-13-CAMPAIGN-REVIEWER-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md`
- evidence_missing:
  - `No obvious stale-role index or automated reminder surface flags which registry roles are overdue for re-evaluation.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/agent_evals/`
- main_failure_mode: `Roles can remain calibrating or provisional for too long without a visible repo-wide signal that fresh evaluation is due.`
- recommended_tightening: `Add a small ROLE-EVAL-STATUS.md or derived registry report that flags stale evaluations and upcoming promotion or degradation checkpoints.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-06`: `monolithic-bias correction`

- principle_id: `AW-06`
- principle_name: `monolithic-bias correction`
- score_1_to_10: `7`
- why: `The repo explicitly names monolithic bias as a failure mode and adds rituals and dispatch-accountability fields to counter it, but the correction is still stronger in doctrine than in measurable enforcement.`
- evidence_found:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
- evidence_missing:
  - `Lifecycle and evaluation-loop docs do not make monolithic-bias incidents a first-class scored field outside campaign templates.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `.agents/skills/agent-ecosystem-governor/SKILL.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
- main_failure_mode: `Non-trivial work can still be kept local by default and only justified after the fact.`
- recommended_tightening: `Add a canonical monolithic_bias_correction_result field to campaign closeout and role-evaluation doctrine so repeated local-only choices become reviewable data rather than style.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `AW-07`: `event-bound dispatch law`

- principle_id: `AW-07`
- principle_name: `event-bound dispatch law`
- score_1_to_10: `6`
- why: `The law is explicit and detailed in dynamic-campaign templates, but it is not yet anchored as a single structured canonical dispatch matrix in lifecycle governance or the registry.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/role_contracts/SYSTEM-CONTRACT-TRACER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-SYSTEM-CONTRACT-TRACER-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md`
  - `docs/architecture/agentic_ecosystem/agent_evals/2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md`
- evidence_missing:
  - `AGENT-LIFECYCLE-GOVERNANCE.md and AGENT-EVALUATION-LOOP.md do not encode event-triggered mandatory dispatch as structured governance data; the registry also lacks one clear mandatory_on_event schema.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/AGENT-LIFECYCLE-GOVERNANCE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-EVALUATION-LOOP.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/SYSTEM-CONTRACT-TRACER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/CAMPAIGN-OUTPUT-LEDGER.md`
  - `docs/architecture/agentic_ecosystem/role_contracts/PROVING-AUTHORITY-REVIEWER.md`
- main_failure_mode: `Mandatory reviewer or sidecar dispatch can be skipped, delayed, or justified inconsistently because the trigger law is spread across templates and role notes rather than one canonical governance table.`
- recommended_tightening: `Add a structured dispatch-matrix artifact or extend AGENT-REGISTRY.json with mandatory_event_triggers, blocking_mode, and skip_conditions; then require campaign closeout to audit trigger satisfaction against actual dispatches.`
- escalate_to_gm: `yes`
- escalation_reason: `The family’s weakest principle is enforceability, not intent. Until event-bound dispatch is represented canonically outside prompt templates, governed campaigns can still drift on when mandatory reviewers and sidecars actually fire.`
