# Repo Principle Audits

## Purpose

This folder holds the repo-governed principle audit system for MCP Factory.

It exists to make the repo's governing principles reviewable as concrete
implementation and workflow questions rather than leaving them as diffuse
doctrine in many files.

This is a markdown-only v1 surface.

It is intentionally:

- repo-tracked
- read-heavy
- audit-oriented
- GM-synthesized after family-level review

It is not:

- a runtime system
- a dynamic campaign
- a replacement for prompt reviews or campaign closeouts

## Structure

- `PRINCIPLE-INVENTORY.md`
  - canonical principle list for this audit system
- `PRINCIPLE-AUDIT-SCHEMA.md`
  - fixed per-principle scoring and writeback shape
- `family_audits/`
  - one markdown audit per principle family
- `GM-PRINCIPLE-AUDIT-SUMMARY.md`
  - parent-thread synthesis of only red and yellow findings

## Family Split

Wave 1 uses six bounded audit families:

1. `contract_coherence`
2. `proving_economics`
3. `dynamic_campaign_governance`
4. `repo_hygiene_and_canonical_surfaces`
5. `observability_and_truth_surfaces`
6. `agentic_workflow_governance`

## Escalation Rule

- scores `<7` escalate to the GM summary
- scores `>=7` stay recorded in the family audit and do not need GM escalation

## Canonical Sources

The inventory is grounded primarily in:

- `AGENTS.md`
- `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
- `docs/architecture/DIRECTOR-OPERATING-RULES.md`
- `docs/architecture/ARCHITECT-OPERATING-GUIDE.md`
- `docs/architecture/SYSTEM-VETTING-AND-MINIMIZATION.md`
- `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`

The family audits may cite additional repo surfaces when needed to score
honestly.

## Post-Audit Canonical Follow-Up Surfaces

When audit findings are tightened into doctrine, prefer these surfaces before
relying on prompt archaeology:

- `SETUP.md`
  - canonical startup and launcher-facing operator guidance
- `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - canonical event-bound dispatch metadata for calibrated roles
- `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - canonical rerun-gate and expensive-loop economics doctrine
- `docs/architecture/agentic_ecosystem/prompts/templates/`
  - canonical tranche writeback fields for rerun legality, truth authority,
    continuation, and dispatch accountability
- `AGENTS.md` and `docs/architecture/CODEX-GOVERNANCE-SURFACES.md`
  - canonical overlap-resolution writeback expectations
