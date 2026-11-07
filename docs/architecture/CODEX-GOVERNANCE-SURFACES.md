# Codex Governance Surfaces

## Purpose

This document explains which repo surfaces carry canonical execution law,
governance, and reusable operator guidance.

## Canonical Surfaces

- `AGENTS.md`
- `codex/tasks/governance_inventory.json`
- `codex/tasks/`
- `codex/tasks/_archive/`
- `.agents/skills/`
- `.agents/ARCHITECTURAL-WEAKNESSES.md`
- `SETUP.md`
- `setup.ps1`
- `start.ps1`

## Governance Precedence

When multiple governance surfaces discuss the same concern, use this ranking:

1. `AGENTS.md`
2. governance-surface indexes such as this file
3. registry and role-contract surfaces
4. manifests and skills
5. audits and evaluations

Implications:

- `dynamic_campaigns/` owns live campaign truth
- `docs/architecture/agentic_ecosystem/` owns durable governance and role
  memory
- `.codex/agents/` and `.agents/skills/` are implementation surfaces derived
  from that governance
- `docs/architecture/principle_audits/` is an audit layer, not peer execution
  law

## Skill Taxonomy

Default loop:

- `ledger-auditor`
- `cross-dll-evidence-auditor`
- `triage-next-step`
- `roadblock-handler`

Active but conditional:

- `public-boundary-auditor`
- `ui-sync-auditor`

Optional:

- `baseline-promoter`
- `campaign-output-ledger`
- `progressive-specialization-auditor`
- `intent-prompt-distiller`
- `regression-governor`
- `repo-hygiene-auditor`
- `run-artifact-curator`
- `system-contract-tracer`
- `subagent-orchestrator`
- `agent-ecosystem-governor`
- `scoped-repo-cleanup`
- `test-suite-author`

## Rule Of Use

- repeat execution law belongs in canonical governance surfaces, not only in
  session-local prompts
- recurring weaknesses belong in the weakness register, not only in narrative
  closeouts
- setup and startup surfaces must stay aligned with real local workflow
- every major new system layer should also carry a plain-English reason for
  existence in repo-tracked docs, not only implementation detail
- prompt chains should state why they happen now and what they do not replace
- chained prompt work should include an explicit evaluation closeout so the
  chain can adapt from evidence instead of following a stale static roadmap
- when a new system overlaps an old one, governance should record whether the
  older surface remains active, narrows, is superseded, or should later be
  retired
- overlap writeback should also record:
  - `overlap_resolution_decision`
  - `canonical_surviving_surface`
  - `downgraded_surfaces`
- recurring assumption-audit pressure is useful when architecture programs are
  active so overclaims and suite-specific seams do not become stable by default
- event-bound dispatch rules should live in one canonical registry-backed
  surface rather than only in prompt prose or role notes
- default audit-suite dispatch for high-risk governed work should be explicit
  in canonical law, not left to GM memory
- when delegation is authorized and the work is dynamic-campaign-governed,
  migration-shaped, proving-shaped, system-contract-shaped, or high
  hidden-consumer-risk / high review-cost, Codex should:
  - classify the work into an audit-default category
  - select the matching suite from
    `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - dispatch the required roles before the tranche, plan, or campaign is
    declared decision-complete
  - record any non-dispatch reason explicitly in the owning artifact
- silently keeping qualifying work monolithic is a workflow failure, not an
  acceptable style choice
- subagent audit output remains bounded pressure only:
  - the GM still owns final judgment
  - implementation evidence and runtime validation still outrank audit prose
- product-facing architecture work should always surface the hard-shape intake
  questions explicitly:
  - what is being ingested
  - how it should be split
  - what makes a split valid or misleading
  - what observer surfaces are needed
  - what progression and comparison model will judge success
- proving-suite and benchmark-family design should always include a
  per-obstruction review shape:
  - purpose
  - why it exists
  - what it proves if handled well
  - what it teaches if it fails
  - testing strength
  - testing weakness
  - false-positive / false-negative risk
- proper-named test suites are product-facing proving surfaces only when they
  are embodied as compiled binaries and exercised through the corresponding
  binary-ingest lane
- authored source families, semantic mock systems, and runtime-only harness
  suites still have value, but they count as architecture-proof or design-proof
  surfaces until the compiled binary embodiment exists
- governance and UI/status language should keep those categories separate so
  the repo does not accidentally treat source-authored suite proof as real
  ingestion proof
