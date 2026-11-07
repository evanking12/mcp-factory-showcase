# Principle Family Audit: `dynamic_campaign_governance`

- strongest_principle: `DCG-01 active prompt canonical`
- weakest_principle: `DCG-04 compact reviewability required`
- recurring_failure_pattern: `the doctrine is strong, but seeded prompt scaffolds and preinitialized compact artifacts can still create static-roadmap or premature-completion pressure`
- count_of_escalations: `0`

## `DCG-01`: `active prompt canonical`

- principle_id: `DCG-01`
- principle_name: `active prompt canonical`
- score_1_to_10: `9`
- why: `The repo consistently treats prompts/ACTIVE-PROMPT.md as the canonical live execution pointer rather than the campaign scaffold or seed sequence.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/efficiency_activation_system_build_v1/prompts/ACTIVE-PROMPT.md`
- evidence_missing:
  - `No repo-level automated guard proves that ACTIVE-PROMPT.md and campaign logs cannot drift apart.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/efficiency_activation_system_build_v1/prompts/ACTIVE-PROMPT.md`
- main_failure_mode: `Canonicality is socially enforced and file-based, so stale pointer risk still exists if writeback discipline slips.`
- recommended_tightening: `Add a lightweight verification rule that current active prompt must match the latest active prompt named in the campaign log and architect brief frontier line.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `DCG-02`: `next prompt provisional`

- principle_id: `DCG-02`
- principle_name: `next prompt provisional`
- score_1_to_10: `8`
- why: `The doctrine is clear and recent campaign artifacts explicitly restate it, but seeded prompt sequences are still visually prominent enough to create mild static-list gravity.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
- evidence_missing:
  - `No broad sample of campaigns where a pre-seeded next prompt was durably recorded as displaced.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
- main_failure_mode: `Seed sequences can still look like quasi-commitments even when doctrine says they are provisional.`
- recommended_tightening: `Require each campaign log tranche entry to state whether the pre-seeded next prompt was kept, displaced, or retired using one fixed field.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `DCG-03`: `prompt completion vs program continuation`

- principle_id: `DCG-03`
- principle_name: `prompt completion vs program continuation`
- score_1_to_10: `8`
- why: `This distinction is one of the strongest parts of the doctrine, and recent hard-family campaigns implement it credibly by continuing after prompt-local success instead of stopping at local completion.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- evidence_missing:
  - `No single compact machine-readable surface distinguishes prompt done from campaign stop condition met without reading multiple artifacts.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- main_failure_mode: `Initialized closeout or summary artifacts can be misread as end-state completion when the program is only mid-continuation.`
- recommended_tightening: `Add a required program_stop_gate_met yes/no field to campaign log and closeout surfaces, distinct from prompt result.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `DCG-04`: `compact reviewability required`

- principle_id: `DCG-04`
- principle_name: `compact reviewability required`
- score_1_to_10: `7`
- why: `The repo clearly takes compact reviewability seriously and has built the right surfaces, but some compact artifacts are initialized early and then accumulate truth over time, which creates mild overclaim risk.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-CLOSEOUT-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/architect_briefs/ARCHITECT-BRIEF.md`
- evidence_missing:
  - `No strict anti-overclaim guard ensures initialized closeout and architect brief surfaces cannot present milestone language more final than the active prompt state.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-SUMMARY-SCHEMA.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-CLOSEOUT-SCHEMA.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/architect_briefs/ARCHITECT-BRIEF.md`
- main_failure_mode: `Compact surfaces exist, but they can still require cross-reading and occasionally overstate maturity before the stop gate is met.`
- recommended_tightening: `Stamp all initialized compact artifacts with a mandatory lifecycle_state field such as initialized, in_progress, or finalized, and require the first line of closeout and architect brief surfaces to reflect it.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `DCG-05`: `explicit stop gate`

- principle_id: `DCG-05`
- principle_name: `explicit stop gate`
- score_1_to_10: `9`
- why: `This is one of the clearest and best-enforced principles in the family. The doctrine, templates, and recent campaigns all name explicit stop gates and use them to resist premature stopping.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/CAMPAIGN.md`
  - `dynamic_campaigns/efficiency_activation_system_build_v1/CAMPAIGN.md`
- evidence_missing:
  - `No validator was inspected that fails a campaign artifact set when stop-gate language is missing.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/CAMPAIGN.md`
  - `dynamic_campaigns/efficiency_activation_system_build_v1/CAMPAIGN.md`
- main_failure_mode: `The stop gate is explicit, but enforcement is still doctrinal rather than mechanically validated.`
- recommended_tightening: `Add a governance audit check that campaigns without an explicit Stop Gate section or equivalent fail template compliance.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `DCG-06`: `dynamic campaigns not static prompt lists`

- principle_id: `DCG-06`
- principle_name: `dynamic campaigns not static prompt lists`
- score_1_to_10: `7`
- why: `The repo has the right law and recent campaign artifacts repeat it consistently. The residual risk is presentation-level: numbered seed sequences still exert static-roadmap pressure even when formally demoted to scaffolding.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/CAMPAIGN.md`
- evidence_missing:
  - `No formal field named prompt_displaced or seed_sequence_retired was found, so dynamic behavior is still partly inferred from prose.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_quasi_terminal_clarify_repair_v1/CAMPAIGN.md`
- main_failure_mode: `A campaign may behave dynamically while still reading like a numbered roadmap, which weakens operator intuition and invites mechanical continuation.`
- recommended_tightening: `Demote seed sequences visually by moving them below active-law sections and require a seed_sequence_status block stating scaffold_only.`
- escalate_to_gm: `no`
- escalation_reason: `none`
