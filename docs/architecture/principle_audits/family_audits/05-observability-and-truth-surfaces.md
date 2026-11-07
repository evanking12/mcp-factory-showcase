# Principle Family Audit: `observability_and_truth_surfaces`

- strongest_principle: `OT-02 explicit authority surfaces`
- weakest_principle: `OT-01 progress must be visible`
- recurring_failure_pattern: `the doctrine is strong, but writeback lag and authority-surface handoff still make some progress visible only after reconstruction`
- count_of_escalations: `0`

## `OT-01`: `progress must be visible`

- principle_id: `OT-01`
- principle_name: `progress must be visible`
- score_1_to_10: `8`
- why: `The repo has strong visibility scaffolding through campaign logs, tranche summaries, closeouts, and active prompt pointers.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-CLOSEOUT-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/CAMPAIGN-REVIEW-SUMMARY.md`
- evidence_missing:
  - `Some visibility still lands late; campaign closeout and architect brief can show writeback lag rather than immediate synchronization.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-CLOSEOUT-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/CAMPAIGN-REVIEW-SUMMARY.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/architect_briefs/ARCHITECT-BRIEF.md`
- main_failure_mode: `Visibility exists but can lag behind branch-shaping truth, forcing the operator to read multiple surfaces to reconstruct the latest state.`
- recommended_tightening: `Make the campaign log, tranche summary, and architect brief update as a synchronized set whenever branch-shaping facts appear.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `OT-02`: `explicit authority surfaces`

- principle_id: `OT-02`
- principle_name: `explicit authority surfaces`
- score_1_to_10: `9`
- why: `The repo is unusually explicit about which surface is authoritative for which decision.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/MORNING-PRINCIPLES-REVIEW.md`
- evidence_missing:
  - `Authority is explicit, but stale or invalid reruns still need explicit rejection, so the model is clear yet still easy to violate operationally.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/MORNING-PRINCIPLES-REVIEW.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/HARD-FAMILY-STATUS-MATRIX.md`
- main_failure_mode: `Authority confusion comes from stale or invalid reruns being produced and then needing explicit rejection, not from missing doctrine.`
- recommended_tightening: `Require rejected reruns to be named as rejected, with the rejection reason, in the active prompt pointer and campaign log.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `OT-03`: `operator truth vs code truth vs proving truth separation`

- principle_id: `OT-03`
- principle_name: `operator truth vs code truth vs proving truth separation`
- score_1_to_10: `8`
- why: `The repo does separate these layers in doctrine and in hard-family review artifacts.`
- evidence_found:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/REPAIR-FINDINGS.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- evidence_missing:
  - `The separation still depends on disciplined writeback; compact review artifacts can lag.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-CLOSEOUT-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/REPAIR-FINDINGS.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/architect_briefs/ARCHITECT-BRIEF.md`
- main_failure_mode: `The layers are separate in doctrine, but review lag can collapse them back into one conversation thread if compact surfaces are not refreshed promptly.`
- recommended_tightening: `Require any rerun rejection, authority change, or blocker rerank to be reflected in compact operator surfaces before the next prompt or rerun is authorized.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `OT-04`: `compiled-binary proving vs architecture-proof separation`

- principle_id: `OT-04`
- principle_name: `compiled-binary proving vs architecture-proof separation`
- score_1_to_10: `9`
- why: `This separation is stated directly in governance and reinforced by proving-surface artifacts.`
- evidence_found:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/HARD-FAMILY-STATUS-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/REPAIR-FINDINGS.md`
- evidence_missing:
  - `Architecture-proof prose can still be overread as product proof unless the compiled-binary boundary is restated in operator-facing summaries.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `AGENTS.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/PROVING-SURFACE-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/HARD-FAMILY-STATUS-MATRIX.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/reviews/REPAIR-FINDINGS.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- main_failure_mode: `Architecture-proof prose can be mistaken for product proof if the compiled-binary boundary is not restated in operator-facing summaries.`
- recommended_tightening: `Require every operator-facing review packet to state whether it is architecture-proof, design-proof, or compiled-binary proving truth before listing outcomes.`
- escalate_to_gm: `no`
- escalation_reason: `none`
