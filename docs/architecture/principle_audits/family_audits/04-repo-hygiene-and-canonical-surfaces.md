# Principle Family Audit: `repo_hygiene_and_canonical_surfaces`

- strongest_principle: `RH-03 weakness register discipline`
- weakest_principle: `RH-04 setup/startup alignment`
- recurring_failure_pattern: `the repo names canonical surfaces explicitly, but explanatory or startup-adjacent surfaces can still drift from the live source of truth`
- count_of_escalations: `1`

## `RH-01`: `canonical governance surfaces`

- principle_id: `RH-01`
- principle_name: `canonical governance surfaces`
- score_1_to_10: `8`
- why: `The repo names its governance homes explicitly and reuses them consistently enough that a human can find the intended control surfaces without archaeology.`
- evidence_found:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `codex/tasks/governance_inventory.json`
  - `codex/tasks/README.md`
  - `docs/architecture/systems/governance_system/README.md`
  - `AGENTS.md`
- evidence_missing:
  - `No explicit precedence note says how to resolve wording drift between AGENTS.md and secondary governance summaries if they disagree.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `docs/architecture/systems/governance_system/README.md`
  - `codex/tasks/governance_inventory.json`
  - `codex/tasks/README.md`
- main_failure_mode: `Secondary summary docs can become quasi-canonical and drift from AGENTS.md.`
- recommended_tightening: `Add one short precedence block to docs/architecture/CODEX-GOVERNANCE-SURFACES.md saying AGENTS.md is the final execution-law surface while other docs are explanatory derivatives.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `RH-02`: `recurring law belongs in repo doctrine`

- principle_id: `RH-02`
- principle_name: `recurring law belongs in repo doctrine`
- score_1_to_10: `7`
- why: `The principle is clearly understood in doctrine and the repo has promoted a meaningful amount of recurring workflow law into durable surfaces.`
- evidence_found:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `docs/architecture/systems/governance_system/README.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/principle_audits/PRINCIPLE-INVENTORY.md`
  - `AGENTS.md`
- evidence_missing:
  - `No small canonical law-promotion procedure says when a repeated prompt-local rule must be promoted into doctrine, where it should land, and how wording should be retired or superseded.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `docs/architecture/systems/governance_system/README.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `docs/architecture/principle_audits/PRINCIPLE-INVENTORY.md`
  - `AGENTS.md`
- main_failure_mode: `Repeated operational law can still live too long inside campaign-local prompt prose before being promoted, narrowed, or retired in repo doctrine.`
- recommended_tightening: `Add one lightweight doctrine-writeback rule to docs/architecture/CODEX-GOVERNANCE-SURFACES.md or governance_system/README.md covering trigger, destination surface, and retirement expectation for recurring laws promoted from campaigns.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `RH-03`: `weakness register discipline`

- principle_id: `RH-03`
- principle_name: `weakness register discipline`
- score_1_to_10: `8`
- why: `The weakness register is a real living control surface, not a symbolic file. It has usage rules, current-state narratives, and explicit narrowing and resolution behavior.`
- evidence_found:
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
  - `AGENTS.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
- evidence_missing:
  - `The register is still a long manual markdown list with no obvious structured index, owner field, or last-reviewed field.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `.agents/ARCHITECTURAL-WEAKNESSES.md`
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
- main_failure_mode: `The register can become a museum of thoughtful entries that are increasingly hard to filter, sort, or retire cleanly.`
- recommended_tightening: `Keep the markdown register, but add minimal metadata per entry or a companion index keyed by weakness id, status, and last-reviewed date.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `RH-04`: `setup/startup alignment`

- principle_id: `RH-04`
- principle_name: `setup/startup alignment`
- score_1_to_10: `5`
- why: `This is the clearest red seam in the family. The repo claims SETUP.md, setup.ps1, and start.ps1 are canonical startup surfaces, but the human-facing doc and the live launcher no longer describe the same workflow.`
- evidence_found:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `SETUP.md`
  - `setup.ps1`
  - `start.ps1`
- evidence_missing:
  - `SETUP.md still describes start.ps1 as opening three windows and auto-opening :8080, while start.ps1 now documents a fourth dashboard lane on :8081 and different browser behavior.`
- repo_surfaces_reviewed:
  - `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - `SETUP.md`
  - `setup.ps1`
  - `start.ps1`
- main_failure_mode: `A new operator follows SETUP.md, forms the wrong mental model of the local stack, and cannot tell whether the scripts changed, the docs are stale, or the canonical-surface claim is false.`
- recommended_tightening: `Make start.ps1 the runtime source of truth and update SETUP.md to match it immediately, especially on service count, browser target, dashboard behavior, and launcher flags.`
- escalate_to_gm: `yes`
- escalation_reason: `Score < 7; this is a direct canonical-surface trust break, not a cosmetic docs issue.`

## `RH-05`: `prompt/output separation and reviewable folder shape`

- principle_id: `RH-05`
- principle_name: `prompt/output separation and reviewable folder shape`
- score_1_to_10: `8`
- why: `Inside the dynamic-campaign system, this principle is implemented well. The templates, top-level campaign root, live campaign README, and actual folder trees all preserve a readable split between prompt execution and review outputs.`
- evidence_found:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/README.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/README.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/`
- evidence_missing:
  - `Sibling campaign naming is less clean than intra-campaign shape; the + variant and neighboring names are not fully explained in dynamic_campaigns/README.md.`
- repo_surfaces_reviewed:
  - `AGENTS.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-CAMPAIGN-PROMPT-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/prompts/templates/DYNAMIC-TRANCHE-PROMPT-TEMPLATE.md`
  - `dynamic_campaigns/README.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/README.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/prompts/ACTIVE-PROMPT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/`
- main_failure_mode: `The operator can understand one campaign cleanly, but campaign-family lineage becomes ambiguous when sibling folder names multiply faster than family-level canonical indexing.`
- recommended_tightening: `Tighten family-level naming and lineage discipline in dynamic_campaigns/README.md and explicitly state whether sibling variants are active, frozen, or obsolete.`
- escalate_to_gm: `no`
- escalation_reason: `none`
