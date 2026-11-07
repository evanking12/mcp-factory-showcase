# Team Roles

## Purpose

This document explains:

- what human team roles are typically needed for a product like MCP Factory
- what the equivalent agentic roles can help with
- what changes when the practical team is one human plus an agentic ecosystem
- what workflow habits matter most for actually turning the project into a
  product

This is not a hiring fantasy document. It is an operating model document.

## What Agentic Ecosystems Are Commonly Used For

People usually use agentic ecosystems for recurring work that is:

- parallelizable
- bounded
- reviewable
- repetitive enough to benefit from consistent structure

Common use cases:

- parallel investigation
  - one agent maps code paths, one inspects logs and artifacts, one checks
    risk or boundary violations
- bounded implementation
  - one agent owns a narrow fix, another verifies, another prepares a handoff
- review and gating
  - correctness review, regression review, boundary review, release readiness
- repetitive repo operations
  - triage, artifact comparison, status summaries, audit scripts, issue shaping
- long-running architecture programs
  - dynamic prompt chains, blocker isolation, migration programs, proving-suite
    campaigns

The important point is that agentic ecosystems work best when they amplify a
clear operating loop. They do not replace the need for one.

## Common Human Team Roles For This Product

For a system like MCP Factory, the common real team roles are:

### 1. Product / Architecture Lead

Owns:

- north-star direction
- proving-suite design
- product boundaries
- stop or go decisions
- what counts as real progress

Typical questions:

- what are we trying to prove
- what blocker matters most now
- what should the product surface to a human operator

### 2. Platform / Runtime Engineer

Owns:

- API surfaces
- worker lifecycle
- bridge integration
- lane stability
- upload and execution behavior

Typical questions:

- can the product ingest and execute reliably
- is the trusted lane actually stable

### 3. Reasoning / Pipeline Engineer

Owns:

- stage logic
- evidence ranking
- prereq inference
- semantic checkpoint comparison
- blocker-family shaping

Typical questions:

- what happened semantically
- what should be promoted or demoted
- what evidence actually justifies the diagnosis

### 4. Evidence / Verification Engineer

Owns:

- run ledger
- artifact persistence
- compare-run discipline
- regression gates
- reproducibility and attribution

Typical questions:

- is this claim trustworthy
- are these runs comparable
- did we improve or only move the noise

### 5. Operator Product / UI Engineer

Owns:

- dashboard
- UI contracts
- observability surfaces
- operator-facing coverage and proof views

Typical questions:

- can a human understand the system without reading raw artifacts
- does the UI reflect actual backend truth

### 6. Infra / DevEx Engineer

Owns:

- CI
- environment consistency
- startup and deployment ergonomics
- reproducible dev and review environments

Typical questions:

- can the team run and review safely
- does the environment help or hinder trust

### 7. Reviewer / Quality Owner

Owns:

- cross-system code review
- regression review
- boundary enforcement
- handoff quality

Typical questions:

- is this change coherent
- what did it risk
- what was not tested

## Ideal Human Team Size

### Strong Ideal

Five people is a very good shape:

- 1 product / architecture lead
- 1 platform / runtime engineer
- 1 reasoning / pipeline engineer
- 1 evidence / verification engineer
- 1 operator UI / DevEx engineer

### Lean But Realistic

Three people can still work well:

- 1 product + architecture
- 1 backend runtime + reasoning
- 1 verification + UI / DevEx

### Below That

Below three, the work is still possible, but role collisions become constant.
That is exactly where a well-run agentic ecosystem becomes useful.

## What Makes A Team Deliver A Product

Delivery does not come from raw activity. It comes from a stable loop.

The loop needs:

- clear short-term goals
  - one dominant blocker
  - one bounded cycle
- clear long-term goals
  - what the horizon is
  - what counts as baseline, medium, and hard progress
- explicit system boundaries
  - who owns what
  - what each system emits and depends on
- verification gates
  - the right checks tied to touched systems
- regression discipline
  - improvements must not silently break earlier gains
- observability
  - humans can see progress and residual debt
- structured handoff
  - work does not live only in one person’s memory
- stop conditions
  - when to rerun
  - when to fix
  - when to narrow
  - when to stop

## Anti-Wheel-Spin Principles

The most important principles for forward progress are:

- one trustworthy lane
- one dominant blocker at a time
- one bounded fix tranche per cycle
- compare against evidence, not memory
- do not do deeper intelligence work if execution, state, contract, or capture
  is still too weak
- write down why the chosen branch beat the alternatives
- define fruitful progress concretely

Fruitful means:

- more verified or aligned coverage
- fewer contradictions
- stronger capability coverage
- no meaningful regressions
- better evidence reuse

## What Changes If It Is Just You Plus The Agentic Ecosystem

This is the most important section for the real operating model.

If the practical team is:

- you
- me
- dynamic prompt generation
- bounded subagents
- reusable skills
- other future review and audit agents

then the team shape changes, but the role needs do not disappear.

They compress.

### Your Real Role

You are primarily:

- product lead
- architecture lead
- proving-suite designer
- acceptance authority

Your highest-value contributions are:

- deciding what matters
- deciding what counts as real progress
- defining the next proving horizon
- naming the product-facing gaps
- preventing the project from drifting into technically impressive but
  strategically useless work

You should not spend most of your energy rediscovering local code details that
agents can inspect for you.

### My Real Role

I am primarily:

- principal execution partner
- architecture synthesizer
- bounded implementer
- investigation orchestrator
- dynamic prompt-chain operator

My highest-value contributions are:

- narrowing blockers
- writing and executing bounded repair tranches
- synthesizing evidence into next steps
- coordinating subagents when useful
- preserving coherence across systems

### What Subagents Become

Subagents are not co-equal decision-makers.

They are best used as:

- investigators
- reviewers
- auditors
- narrow workers with explicit ownership

They are useful when the work is separable. They are harmful when they create
parallel confusion in fragile systems.

## Biggest Workflow Wins In A Solo + Agentic Model

If the practical team is you plus the ecosystem, the biggest wins are:

### 1. Keep The Product Horizon Explicit

Always know:

- the minimum goal
- the broader horizon
- the current stop gate

Without this, the ecosystem will produce motion without product progress.

### 2. Use Dynamic Prompt Chains For Real Execution

This is one of the strongest workflow multipliers available to you.

Good pattern:

- choose one dominant blocker
- write one bounded prompt
- execute it
- record evidence
- write the next prompt from that evidence
- execute again

Bad pattern:

- predeclare a huge static roadmap
- keep following it after the evidence changed

### 3. Treat System Ownership As A First-Class Tool

Before larger changes:

- identify the system
- identify the contract
- identify the likely tests
- identify what other system might drift

This keeps the ecosystem modular instead of chaotic.

### 4. Build Review And Handoff As Products

You are right to worry about this.

The ecosystem gets much stronger once each meaningful checkpoint includes:

- `systems_touched`
- `contracts_touched`
- `evidence_artifacts`
- `tests_run`
- `known_residual_risks`
- `next_reviewer`

That turns one-agent progress into a multi-agent reviewable workflow.

### 5. Make Observability Product-Facing

You personally should not have to ask me for every important truth.

The product should gradually expose:

- surface coverage
- workflow coherence
- lineage reuse
- branch truth
- freshness / stale-state control

Those are strategic leverage surfaces, not optional polish.

### 6. Add Gating Agents Around The Core Loop

As the project grows, you will get outsized value from adding:

- strict change-review agent
- verification gate agent
- handoff formatter agent
- run auditor agent
- UI truth auditor agent

These do not replace the main loop. They keep it honest.

## Your Highest Priorities As The User

To get the most out of this ecosystem, your top priorities should be:

### 1. Protect The Product North Star

Keep stating:

- what the product is supposed to become
- what a good specimen looks like
- what counts as meaningful progress

This is the highest-leverage human role.

### 2. Define Horizons And Stop Gates

For every active program, keep the following explicit:

- minimum success floor
- next proving band
- broader horizon
- stop gate

That prevents the ecosystem from wandering.

### 3. Push For Better Observability, Not Just More Work

When you cannot see progress, say so directly.

That pressure is valuable. It forces the system to become a product instead of
remaining an engineer-only toolchain.

### 4. Invest In Review, Verification, And Handoff

If you want a real product, not a clever solo codebase, these are among the
highest-return investments:

- regression discipline
- structured handoff
- system-aware review
- operator observability

### 5. Let Agents Handle Detail, But Not Product Intent

Agents can inspect, compare, summarize, patch, and audit.

But they should not be the sole source of:

- product taste
- architecture horizon
- proving target choice
- success criteria

That is your role.

## Practical Summary

If this project stays as you plus an agentic ecosystem, the path to a product
is still viable.

But success depends on treating the ecosystem as:

- a disciplined operating system for progress

not as:

- a pile of clever autonomous helpers

The most important combination is:

- your product direction
- explicit system ownership
- dynamic prompt execution
- strong verification and handoff
- gradual operator observability

That combination is what makes the project scalable.
