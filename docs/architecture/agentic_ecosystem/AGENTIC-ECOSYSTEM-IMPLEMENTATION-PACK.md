# Agentic Ecosystem Implementation Pack

> Non-canonical synthesis surface.
> Keep for implementation context and historical handoff only.
> `AGENTS.md`, `dynamic_campaigns/`, and
> `docs/architecture/agentic_ecosystem/` role governance surfaces outrank this
> file when they disagree.

## Purpose

This is the final program-level deliverable for the `agentic_ecosystem`
prompt-chain.

It is the handoff artifact that makes the ecosystem implementation-ready for
the user.

## Program Status

This pack is populated from three executed prompt families:

- Prompt 01: `review + gate core`
- Prompt 02: `run/evidence core`
- Prompt 03: `product/observability core`

Each family produced:

- role contracts
- evaluation artifacts
- first refined prompt contracts

Wave 1 rollout status now includes:

- five read-only custom-agent manifests under `.codex/agents/` for the
  original Wave 1 set
- one supervised manifest-aligned proving cycle using an existing commit range
  and existing Spectrum evidence artifacts
- second-round evaluation artifacts for all five Wave 1 roles


## Role Hierarchy

### Layer 0: Human Authority

- user
  - product lead
  - architecture lead
  - proving-suite designer
  - acceptance authority

### Layer 1: General Manager / Orchestrator

- main Codex thread
  - sole branch selector
  - sole synthesis layer
  - dynamic prompt-chain operator
  - dispatch owner
  - critical-path implementer
- authoritative workflow-quality scorer
  - authoritative dispatch-accountability recorder

This remains `parent-thread-only`.

### Layer 2: Specialist Role Families

- `review + gate core`
  - `code_review_bot`
  - `verification_gate_bot`
  - `handoff_formatter_bot`
- `run/evidence core`
  - `run_auditor`
  - `ledger_compare_run_auditor`
  - `roadblock_classifier`
- `product/observability core`
  - `ui_truth_auditor`
  - `coverage_summarizer`
  - `dashboard_contract_checker`
- `campaign governance core`
  - `campaign-output-ledger`
  - `campaign-reviewer`
  - `proving-authority-reviewer`
- `architecture/traceability core`
  - `system-contract-tracer`

### Layer 3: Bounded Support Threads

- read-only investigator subagents
- narrow workers only when the parent thread assigns a disjoint write boundary

## Main-Thread / GM Responsibilities

The main thread keeps:

- wider goal
- minimum floor
- broader horizon
- current stop gate
- dominant blocker or role-gap
- branch choice
- next-prompt construction
- final synthesis
- authoritative workflow-quality scoring
- escalation to roadblock or human judgment

The main thread does not delegate:

- product intent
- proving horizon selection
- stop-gate choice
- final branch selection

## Specialist Output Contract

All specialist roles inherit the GM-consumable top-block contract at
`docs/architecture/agentic_ecosystem/role_contracts/GM-CONSUMABLE-SPECIALIST-OUTPUT.md`.

The intended workflow is:

- specialist returns one compact YAML block first
- GM consumes that block for branch choice, closeout, or dispatch accounting
- specialist may include bounded evidence details after the block
- narrative-only specialist output is useful evidence but incomplete role
  performance


## Role Family Grouping

### Review + Gate Core

- `code_review_bot`
  - contract: [CODE-REVIEW-BOT.md](role_contracts/CODE-REVIEW-BOT.md)
  - eval: [2026-04-10-CODE-REVIEW-BOT-EVAL-01.md](agent_evals/2026-04-10-CODE-REVIEW-BOT-EVAL-01.md)
  - eval: [2026-04-10-CODE-REVIEW-BOT-EVAL-02.md](agent_evals/2026-04-10-CODE-REVIEW-BOT-EVAL-02.md)
  - decision: `refine`
  - note: validate commit handoff structure when commit metadata is part of the
    review surface
- `verification_gate_bot`
  - contract: [VERIFICATION-GATE-BOT.md](role_contracts/VERIFICATION-GATE-BOT.md)
  - eval: [2026-04-10-VERIFICATION-GATE-BOT-EVAL-01.md](agent_evals/2026-04-10-VERIFICATION-GATE-BOT-EVAL-01.md)
  - eval: [2026-04-10-VERIFICATION-GATE-BOT-EVAL-02.md](agent_evals/2026-04-10-VERIFICATION-GATE-BOT-EVAL-02.md)
  - decision: `refine`
- `handoff_formatter_bot`
  - contract: [HANDOFF-FORMATTER-BOT.md](role_contracts/HANDOFF-FORMATTER-BOT.md)
  - eval: [2026-04-10-HANDOFF-FORMATTER-BOT-EVAL-01.md](agent_evals/2026-04-10-HANDOFF-FORMATTER-BOT-EVAL-01.md)
  - decision: `refine`

### Run / Evidence Core

- `run_auditor`
  - contract: [RUN-AUDITOR.md](role_contracts/RUN-AUDITOR.md)
  - eval: [2026-04-10-RUN-AUDITOR-EVAL-01.md](agent_evals/2026-04-10-RUN-AUDITOR-EVAL-01.md)
  - eval: [2026-04-10-RUN-AUDITOR-EVAL-02.md](agent_evals/2026-04-10-RUN-AUDITOR-EVAL-02.md)
  - decision: `refine`
- `ledger_compare_run_auditor`
  - contract: [LEDGER-COMPARE-RUN-AUDITOR.md](role_contracts/LEDGER-COMPARE-RUN-AUDITOR.md)
  - eval: [2026-04-10-LEDGER-COMPARE-RUN-AUDITOR-EVAL-01.md](agent_evals/2026-04-10-LEDGER-COMPARE-RUN-AUDITOR-EVAL-01.md)
  - eval: [2026-04-10-LEDGER-COMPARE-RUN-AUDITOR-EVAL-02.md](agent_evals/2026-04-10-LEDGER-COMPARE-RUN-AUDITOR-EVAL-02.md)
  - decision: `refine`
- `roadblock_classifier`
  - contract: [ROADBLOCK-CLASSIFIER.md](role_contracts/ROADBLOCK-CLASSIFIER.md)
  - eval: [2026-04-10-ROADBLOCK-CLASSIFIER-EVAL-01.md](agent_evals/2026-04-10-ROADBLOCK-CLASSIFIER-EVAL-01.md)
  - eval: [2026-04-10-ROADBLOCK-CLASSIFIER-EVAL-02.md](agent_evals/2026-04-10-ROADBLOCK-CLASSIFIER-EVAL-02.md)
  - decision: `refine`

### Product / Observability Core

- `ui_truth_auditor`
  - contract: [UI-TRUTH-AUDITOR.md](role_contracts/UI-TRUTH-AUDITOR.md)
  - eval: [2026-04-10-UI-TRUTH-AUDITOR-EVAL-01.md](agent_evals/2026-04-10-UI-TRUTH-AUDITOR-EVAL-01.md)
  - decision: `refine`
- `coverage_summarizer`
  - contract: [COVERAGE-SUMMARIZER.md](role_contracts/COVERAGE-SUMMARIZER.md)
  - eval: [2026-04-10-COVERAGE-SUMMARIZER-EVAL-01.md](agent_evals/2026-04-10-COVERAGE-SUMMARIZER-EVAL-01.md)
  - decision: `refine`
- `dashboard_contract_checker`
  - contract: [DASHBOARD-CONTRACT-CHECKER.md](role_contracts/DASHBOARD-CONTRACT-CHECKER.md)
  - eval: [2026-04-10-DASHBOARD-CONTRACT-CHECKER-EVAL-01.md](agent_evals/2026-04-10-DASHBOARD-CONTRACT-CHECKER-EVAL-01.md)
  - decision: `refine`

### Architecture / Traceability Core

- `system-contract-tracer`
  - contract: [SYSTEM-CONTRACT-TRACER.md](role_contracts/SYSTEM-CONTRACT-TRACER.md)
  - eval: [2026-04-12-SYSTEM-CONTRACT-TRACER-EVAL-01.md](agent_evals/2026-04-12-SYSTEM-CONTRACT-TRACER-EVAL-01.md)
  - decision: `refine`
  - note: use as a non-blocking sidecar reviewer for one named system at a
    time; do not let it become its own GM

### Campaign Governance Core

- `campaign-output-ledger`
  - contract: [CAMPAIGN-OUTPUT-LEDGER.md](role_contracts/CAMPAIGN-OUTPUT-LEDGER.md)
  - eval: [2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md](agent_evals/2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md)
  - decision: `refine`
  - note: dynamic-campaign sidecar for preserving tranche memory; GM remains
    the authoritative writer of campaign artifacts
- `campaign-reviewer`
  - contract: [CAMPAIGN-REVIEWER.md](role_contracts/CAMPAIGN-REVIEWER.md)
  - eval: [2026-04-13-CAMPAIGN-REVIEWER-EVAL-01.md](agent_evals/2026-04-13-CAMPAIGN-REVIEWER-EVAL-01.md)
  - decision: `refine`
  - note: default parallel reviewer for prompt-close review, campaign review
    summary, and morning principles review
- `proving-authority-reviewer`
  - contract: [PROVING-AUTHORITY-REVIEWER.md](role_contracts/PROVING-AUTHORITY-REVIEWER.md)
  - eval: [2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md](agent_evals/2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md)
  - decision: `refine`
  - note: default gate-bearing review after reruns and proving commands
- `campaign-workflow-auditor`
  - contract: [CAMPAIGN-WORKFLOW-AUDITOR.md](role_contracts/CAMPAIGN-WORKFLOW-AUDITOR.md)
  - eval: [2026-04-12-CAMPAIGN-WORKFLOW-AUDITOR-EVAL-01.md](agent_evals/2026-04-12-CAMPAIGN-WORKFLOW-AUDITOR-EVAL-01.md)
  - eval: [2026-04-13-CAMPAIGN-WORKFLOW-AUDITOR-MERGE-01.md](agent_evals/2026-04-13-CAMPAIGN-WORKFLOW-AUDITOR-MERGE-01.md)
  - decision: `merge`
  - note: historical role now merged into `campaign-reviewer`

## Keep / Refine / Split / Merge / Retire

- `keep` unchanged now
  - none
- `refine` now
  - all active specialist roles, including the new campaign workflow auditor
- `split` now
  - none
- `merge` now
  - merge `ui_truth_auditor` implementation into the existing
    ui-sync-auditor
    skill surface instead of creating a duplicate skill
  - merge `campaign-workflow-auditor` into `campaign-reviewer` so workflow
    review has one clear default owner
- `retire` now
  - none

Reason no role is a pure `keep` yet:

- every role proved useful
- none are sharp enough to trust unchanged after only two supervised
  evaluations

## Wave 1 Supervised Cycle Outcome

Immediately useful in supervised recurring use:

- `verification_gate_bot`
- `run_auditor`
- `ledger_compare_run_auditor`
- `roadblock_classifier`

Useful but still noisier or more review-sensitive:

- `code_review_bot`

Not yet worth heavier use:

- none of the Wave 1 roles failed the first supervised cycle

Lifecycle interpretation after the first supervised cycle:

- all five Wave 1 roles are now strong enough for `provisional` supervised use
- none are `stable`
- all five still carry a `refine` decision for the next cycle

## Skill vs Agent vs Prompt-Only Recommendation

### Parent-Thread-Only

- `gm_orchestrator`
  - recommendation: `parent-thread-only`
  - contract: [GM-ORCHESTRATOR.md](role_contracts/GM-ORCHESTRATOR.md)
  - eval: [2026-04-12-GM-ORCHESTRATOR-EVAL-01.md](agent_evals/2026-04-12-GM-ORCHESTRATOR-EVAL-01.md)
  - note: remains parent-thread-only; now requires authoritative per-tranche workflow scoring

### Custom Agents Implemented In Wave 1

- `code_review_bot`
  - status: `implemented`
- `verification_gate_bot`
  - status: `implemented`
- `run_auditor`
  - status: `implemented`
- `ledger_compare_run_auditor`
  - status: `implemented`
- `roadblock_classifier`
  - status: `implemented`

### Custom Agent Implemented After Wave 1

- `system-contract-tracer`
  - status: `implemented`
  - initial review artifact:
    [2026-04-12-artifact-read-operator-truth-route-system-review-01.md](../system_trace_reviews/2026-04-12-artifact-read-operator-truth-route-system-review-01.md)
- `campaign-output-ledger`
  - status: `implemented`
  - initial evaluation:
    [2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md](agent_evals/2026-04-12-CAMPAIGN-OUTPUT-LEDGER-EVAL-01.md)
- `campaign-reviewer`
  - status: `implemented`
  - initial evaluation:
    [2026-04-13-CAMPAIGN-REVIEWER-EVAL-01.md](agent_evals/2026-04-13-CAMPAIGN-REVIEWER-EVAL-01.md)
- `proving-authority-reviewer`
  - status: `implemented`
  - initial evaluation:
    [2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md](agent_evals/2026-04-13-PROVING-AUTHORITY-REVIEWER-EVAL-01.md)
- `campaign-workflow-auditor`
  - status: `merged_historical`
  - merge note:
    [2026-04-13-CAMPAIGN-WORKFLOW-AUDITOR-MERGE-01.md](agent_evals/2026-04-13-CAMPAIGN-WORKFLOW-AUDITOR-MERGE-01.md)

### Skill-First Roles

- `ui_truth_auditor`
  - recommendation: `skill`
  - implement by refining the existing
    ui-sync-auditor
- `dashboard_contract_checker`
  - recommendation: `skill`
  - current status: `not yet instantiated`

### Prompt-Only Or Deferred Roles

- `handoff_formatter_bot`
  - recommendation: `prompt-only` first
- `coverage_summarizer`
  - recommendation: `prompt-only` first

## Recommended Model And Reasoning Effort

- `code_review_bot`
  - model: `gpt-5.4`
  - reasoning: `high`
- `verification_gate_bot`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`
- `run_auditor`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`
- `ledger_compare_run_auditor`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `roadblock_classifier`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `ui_truth_auditor`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`
- `dashboard_contract_checker`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`
- `handoff_formatter_bot`
  - model: `gpt-5.4-mini`
  - reasoning: `low`
- `coverage_summarizer`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `system-contract-tracer`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `campaign-output-ledger`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`
- `campaign-reviewer`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `proving-authority-reviewer`
  - model: `gpt-5.4`
  - reasoning: `medium`
- `campaign-workflow-auditor`
  - model: `gpt-5.4-mini`
  - reasoning: `medium`

## Recommended Sandbox / Write Boundary

All current specialist review roles should start as:

- `read-only`

Reason:

- they are audit, review, gate, or framing roles
- the main thread should stay responsible for synthesis and most edits

## Expected Context Inputs

Every specialist should receive only:

- exact question
- exact files or artifacts
- exact output shape
- exact boundary of what it should not solve

Family-specific context:

- `review + gate`
  - diff / commit range
  - commit subject/body when available
  - touched systems
  - AGENTS doctrine
  - commit handoff template and handoff rules
  - recorded verification if any
- `run/evidence`
  - compare artifacts
  - ledger rows
  - roadblock records
  - run-validity and cohesion artifacts
  - AGENTS doctrine
- `product/observability`
  - README contract docs
  - implementation files
  - compare artifacts when coverage framing is needed
  - UI skill doctrine

## Required Output Contracts

All roles should output:

- bounded verdict
- citations
- missing or blocking gaps
- one prompt refinement recommendation

Canonical role-specific shapes live in the linked role contracts.

## Repo Locations For Setup

- custom agent manifests
  - `.codex/agents/<role-name>.toml`
- reusable skills
  - `.agents/skills/<skill-name>/SKILL.md`
- role contracts
  - `docs/architecture/agentic_ecosystem/role_contracts/`
- evaluation artifacts
  - `docs/architecture/agentic_ecosystem/agent_evals/`
- dynamic ecosystem prompts
  - `docs/architecture/agentic_ecosystem/prompts/`

## Implemented Agent Filenames

- `.codex/agents/code-review-bot.toml`
- `.codex/agents/verification-gate-bot.toml`
- `.codex/agents/run-auditor.toml`
- `.codex/agents/ledger-compare-run-auditor.toml`
- `.codex/agents/roadblock-classifier.toml`
- `.codex/agents/campaign-output-ledger.toml`
- `.codex/agents/campaign-reviewer.toml`
- `.codex/agents/proving-authority-reviewer.toml`
- `.codex/agents/campaign-workflow-auditor.toml`

Suggested skill homes:

- refine `.agents/skills/ui-sync-auditor/SKILL.md`
- add `.agents/skills/dashboard-contract-checker/SKILL.md` when ready

## Rollout Order

### Wave 1: Core Execution Support

Implemented:

- `code_review_bot`
- `verification_gate_bot`
- `run_auditor`
- `ledger_compare_run_auditor`
- `roadblock_classifier`

### Wave 2: Review Packaging

Implement next:

- `handoff_formatter_bot`

### Wave 3: Product / Observability Support

Implement next:

- refine `ui-sync-auditor` into `ui_truth_auditor`
- `dashboard_contract_checker`
- `coverage_summarizer`

## Dispatch Law

Use the ecosystem like this:

- main thread chooses the dominant blocker or role-gap
- if the task is single-threaded or critical-path, stay local
- if there are 2-3 clearly separate read-only questions, spawn up to 3
  specialists
- specialists return bounded findings
- when commit metadata is available, `code_review_bot` also validates the
  review handoff contract rather than only code risk
- main thread integrates results and chooses one next move:
  - implement
  - investigate
  - rerun
  - classify roadblock
  - stop

Do not let specialists choose:

- proving horizon
- stop gate
- product intent
- the next program branch

For dynamic campaigns specifically:

- the GM always scores:
  - `gm_control_quality`
  - `context_pressure_result`
  - `delegation_effectiveness`
  - `operator_reviewability`
- the GM always records:
  - `roles_considered`
- `roles_dispatched`
- `why_not_dispatched`
- `campaign-output-ledger` preserves the raw deltas that feed those scores
- `campaign-output-ledger` also preserves dispatch-accountability deltas
- `campaign-reviewer` owns prompt-close review, campaign review summary, and
  morning principles review
- `proving-authority-reviewer` owns rerun-authority review before a run may
  steer the next branch
- review topology remains star-shaped under the GM with no recursive reviewer
  delegation
- reviewers never replace GM authority

## Context-Management Rules

Main thread keeps:

- long-horizon goal
- current stop gate
- dominant blocker
- current trusted lane
- system ownership map
- latest construction note

Specialists keep only:

- one bounded question
- a small evidence slice
- one output shape

Long-lived context should live in:

- role contracts
- skills
- construction notes
- this implementation pack
- run artifacts
- system docs

## What The User Must Create

Minimum concrete implementation steps:

1. create the recommended `.codex/agents/*.toml` files for Wave 1 roles
2. copy the role-contract logic into those TOML files as the developer
   instructions base
3. refine `ui-sync-auditor` with the `ui_truth_auditor` contract
4. add `dashboard-contract-checker` skill when ready
5. keep new evaluations under
   `docs/architecture/agentic_ecosystem/agent_evals/`
6. for any new role:
   - define contract
   - evaluate on real repo work
   - refine
   - only then promote to custom agent or skill

## Residual Risks

- all roles are still first-pass calibrated, not final
- none should be treated as “set and forget” yet
- `handoff_formatter_bot` and `coverage_summarizer` are not ready to promote
  beyond prompt-only use yet
- `ui_truth_auditor` should merge with the current UI skill surface instead of
  forking doctrine into duplicate homes
- `dashboard_contract_checker` should be re-evaluated after the next meaningful
  dashboard contract change
- the ecosystem now has per-tranche workflow scoring, but the new campaign
  workflow auditor still needs more live evaluations before it should be
  trusted as more than calibrating governance support
- dispatch accountability is now durable, but it still needs repeated live use
  before role underuse and overuse can be treated as strongly measured rather
  than newly visible

## Honest End State

The ecosystem is now ready to implement in waves.

What is trustworthy now:

- the hierarchy
- the original calibrated role families plus the added campaign-governance and
  traceability roles
- the per-role boundaries
- the rollout order
- the dispatch law
- the file locations and recommended model / sandbox defaults

What is not yet final:

- any role’s prompt contract without another real-use eval
- broad autonomous execution without the main thread as GM
- promoting the weakest roles to custom agents immediately
