# Systems And Agentic Ecosystem Plan

## Purpose

This document defines the canonical high-level system map for MCP Factory and
the next-layer agentic ecosystem that should govern it.

It exists to answer four questions clearly:

1. what systems already exist
2. what each system owns
3. what control systems are still missing
4. how to scale the project without collapsing modularity

This is a contract-first plan. It is not permission to move code into new
folders casually. The first goal is explicit ownership and boundaries. Physical
reorganization should follow only when the documentation and public contracts
are already stable enough to support it.

## Current Position

The project is already an ecosystem, even if not all parts have been named
explicitly.

Current real systems:

- `execution_system`
- `reasoning_system`
- `evidence_system`
- `operator_system`
- `governance_system`
- `verification_system`

The correct near-term move is not `pipeline_v1`, `pipeline_v2`, and so on.
That would encode chronology into runtime layout and make stale intentions look
current.

The correct move is:

- one live runtime
- one canonical set of public contracts
- explicit system ownership
- prompt-chain and iteration history kept in docs and run artifacts

## Architectural Rule

Use `docs/architecture/systems/` for:

- system purpose
- ownership
- contracts
- dependencies
- invariants
- failure modes
- observability
- agent guidance

Do not use it as a code dump, scratch pad, or parallel implementation tree.

## Canonical System Map

### 1. Execution System

Owns the real ingestion and runtime execution boundary:

- route entrypoints
- upload and analyze surfaces
- bridge communication
- worker launch behavior
- DLL execution plumbing

Primary question:

- can the product ingest and execute the requested binary or target correctly
  enough for the rest of the stack to matter

### 2. Reasoning System

Owns the pipeline intelligence layer:

- stage-by-stage analysis
- evidence ranking
- prereq inference
- gap resolution
- semantic checkpoint comparison
- blocker and diagnosis shaping

Primary question:

- given a working execution lane, can the product reason honestly about what
  happened and what should happen next

### 3. Evidence System

Owns all durable truth surfaces:

- session artifacts
- checkpoints
- run ledger
- artifact stores
- compare-run outputs
- roadblock records
- campaign attribution surfaces

Primary question:

- what reusable evidence exists, how trustworthy is it, and can later work rely
  on it without hidden-variable contamination

### 4. Operator System

Owns human-facing control and review surfaces:

- dashboard
- UI
- lab/status surfaces
- operator-facing summaries
- product-facing capability views

Primary question:

- can a human understand what is broken, what is proven, what changed, and what
  to do next without reading raw artifacts

### 5. Governance System

Owns execution law for agents and architecture programs:

- `AGENTS.md`
- task and skill registries
- skill surfaces
- architectural doctrine
- dynamic prompt-chain discipline
- subagent rules

Primary question:

- what are agents allowed to do, what surfaces are canonical, and what must be
  updated when the architecture evolves

### 6. Verification System

Owns confidence gates:

- tests
- sync checks
- harness runs
- regression checks
- system-specific verification discipline

Primary question:

- what evidence is required before a change can be trusted

## Why This System Map Matters

Without explicit systems, the repo drifts toward:

- code organized by convenience instead of ownership
- mixed contracts across runtime and tooling
- weak review boundaries
- poor handoff between agents
- UI and backend truth drifting apart

With explicit systems, the project can evolve toward:

- modular changes
- better commit handoffs
- review bots that know their scope
- verification gates tied to touched systems
- more reliable agentic delegation

## Recommended Agentic Ecosystem

The next missing layer is not more raw implementation. It is control systems
around implementation.

### Core Agent Roles To Add Or Formalize

#### 1. Change Review Agent

Purpose:

- review bounded changes for correctness, risk, boundary drift, and missing
  tests

Should focus on:

- public boundary violations
- hidden cross-system coupling
- semantic overclaim
- unverified new logic

#### 2. Verification Gate Agent

Purpose:

- decide which checks are required from the touched systems and confirm they
  actually ran

Should focus on:

- touched-system-aware test selection
- missing sync checks
- lane restart requirements
- invalid claims without comparable runs

#### 3. Handoff Formatter Agent

Purpose:

- turn code changes into structured machine- and human-readable handoffs

Recommended handoff schema:

- `systems_touched`
- `contracts_touched`
- `evidence_artifacts`
- `tests_run`
- `known_residual_risks`
- `next_reviewer`

#### 4. Run Auditor Agent

Purpose:

- confirm run validity before promotion or architectural claims

Should focus on:

- ledger completeness
- comparable profile integrity
- lane identity
- attribution coherence

#### 5. UI Truth Auditor Agent

Purpose:

- detect when backend truth changed enough that operator surfaces are now stale
  or misleading

#### 6. Architecture Drift Auditor Agent

Purpose:

- detect when implementation no longer matches documented system boundaries

## Current Missing Controls

The ecosystem is still incomplete in these important ways:

- no strict post-change review gate dedicated to cross-system regressions
- no containerized or strongly reproducible review environment
- no consistent commit handoff convention for follow-on agents
- no system-aware regression gate that maps touched files to required tests
- weak operator observability into function coverage, blocker-family coverage,
  and state/lineage coverage
- dashboard still not strong enough to stand alone as the primary human review
  tool

## Recommended Rollout Order

### Phase 1: System Documentation

Done by adopting `docs/architecture/systems/` as the contract-first system map.

This must precede a major physical repo reorg.

### Phase 2: Handoff And Review Contracts

Add a structured handoff convention and a dedicated review agent workflow.

Goal:

- make changes legible to multiple specialized agents without forcing each one
  to rediscover context from scratch

### Phase 3: Verification Routing

Tie touched systems to required checks.

Goal:

- avoid under-testing and also avoid wasting time on irrelevant checks

### Phase 4: Operator Observability

Add missing product-facing coverage surfaces:

- surface coverage
- workflow coherence
- lineage reuse
- branch truth
- freshness / stale-state control

### Phase 5: Deeper Physical Modularity

Only once the contracts are stable:

- consider physical layout changes that reflect actual system ownership
- do not split runtime by iteration number
- do not duplicate live systems under versioned folders

## Rules For Future Physical Reorganization

Before a folder move or large code ownership split:

1. the system must already exist as a documented contract surface
2. its public inputs and outputs must be named
3. verification expectations must be known
4. boundary imports must be explicit
5. the move must reduce ambiguity, not create a second truth home

If a proposed folder split cannot satisfy those conditions, it is too early.

## Dynamic Prompt Chains In This Ecosystem

Dynamic prompts should remain the architecture iteration mechanism.

Use them to:

- isolate the dominant blocker
- execute one bounded tranche
- record evidence
- construct the next prompt from actual results

Do not treat prompt chains as a substitute for system ownership documentation.

Prompt chains answer:

- what we are changing now

System docs answer:

- what this part of the product is for

Both are required.

## Success Standard

This ecosystem is working when:

- each major repo area maps clearly to one system
- other agents can determine ownership before editing
- required tests follow from touched systems rather than guesswork
- handoffs between agents are structured and reviewable
- operator surfaces reflect backend truth without stale narrative drift
- architectural iteration can continue without turning the repo into a
  chronology museum

## Related Surfaces

- AGENTS.md
- [CODEX-GOVERNANCE-SURFACES.md](../CODEX-GOVERNANCE-SURFACES.md)
- [systems/README.md](../systems/README.md)
