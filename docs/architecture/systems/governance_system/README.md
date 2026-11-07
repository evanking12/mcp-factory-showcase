# Governance System

## Purpose

The governance system owns execution law for agents and architecture programs.

Its job is to keep the repo coherent as multiple prompts, skills, and agents
interact with fragile systems.

Without this system, the project drifts into:

- duplicated law
- conflicting prompts
- uncontrolled delegation
- weak ownership boundaries

## Owned Surfaces

Canonical governance surfaces:

- `AGENTS.md`
- `codex/tasks/governance_inventory.json`
- `codex/tasks/`
- `codex/tasks/_archive/`
- `.agents/skills/`
- governance and operating docs under `docs/architecture/`

Related surfaces:

- dynamic prompt chains that drive architecture execution
- subagent delegation rules
- weakness and roadblock tracking conventions

## Primary Inputs

- repo architecture changes
- new tasks or skills
- recurring failure patterns
- new prompt-chain programs
- delegation needs

## Primary Outputs

- canonical rules for agent execution
- skill taxonomy
- active vs archived task surfaces
- dynamic prompt-chain discipline
- system documentation expectations

## Public Contracts

Critical contracts include:

- execution law in `AGENTS.md`
- task and skill registry semantics
- triggers and do-not-use boundaries for tasks and skills
- prompt-chain expectations for dynamic next-prompt construction

## Invariants

- canonical law belongs in repo-tracked governance surfaces, not only in
  conversation memory
- a new task or skill needs a distinct trigger and distinct output
- prompt chains should adapt from evidence rather than follow stale static
  roadmaps
- subagent use must be explicit, bounded, and ownership-aware

## Common Failure Modes

- duplicated governance in multiple stale docs
- skills added without a real reusable trigger
- prompt programs outgrowing their documented purpose
- subagents spawned without clear ownership or integration order
- architecture intent living only in local conversation, not in the repo

## Observability Gaps

Current recurring gaps include:

- commit handoff structure is still too weak for a larger agentic ecosystem
- change review and regression gate bots are not yet formalized
- system-aware review routing is still implicit rather than documented as an
  enforced workflow

## Typical Tests And Checks

When this system changes, likely checks include:

- governance inventory tests
- governance audit tests
- `python scripts/verify_sync.py --tier A`

## Agent Guidance

Use this doc before editing when the task involves:

- new skills
- new task surfaces
- prompt-chain architecture
- delegation law
- changes to canonical execution rules

Default related skills:

- `subagent-orchestrator`
- `roadblock-handler`
- `repo-hygiene-auditor`

## Do Not Own

The governance system does not own:

- live execution behavior
- semantic comparison logic
- UI layout

It owns the rules by which agents may safely work on those systems.
