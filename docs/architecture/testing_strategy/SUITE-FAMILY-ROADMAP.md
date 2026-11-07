# Suite Family Roadmap

## Purpose

This document records the emerging test-suite families for MCP Factory as a
product, not just as a proving repo.

The goal is to keep distinct product risks separated into distinct suite
families so one suite does not become a confused mixture of:

- semantic proving
- proving-lane trust
- efficiency
- package realism
- interwoven state reasoning
- observability

The product needs separate pressure families with clear questions, clear
acceptance criteria, and clear failure attribution.

## Preserve

These families are already justified and should remain distinct:

- `hard01/hard02`
  - semantic and proving pressure
- pre-hard-family proving-lane trust work
  - API, bridge, runner, authority, and terminalization trust
- separate realism benches for different product risks

Do not collapse those into one giant suite.

## Current and Emerging Suite Families

### 1. Proving-lane trust

Question:

- can the API, bridge, runner, terminalization, and authority surfaces be
  trusted before expensive suite work begins

This family owns:

- lane identity
- lane readiness
- canaries
- authority packets
- failure-domain classification

### 2. Semantic and proving pressure

Question:

- can the system actually recover callable meaning and clear hard semantic
  cases under trustworthy proving conditions

This family owns:

- `hard01`
- `hard02`
- later `hard03+` semantic pressure families

### 3. Efficiency and intake planning

Question:

- can the system produce a useful first-pass operational picture quickly enough
  to guide deeper work instead of deeply probing everything immediately

Canonical spec:

- `EFFICIENCY-ACTIVATION-DESIGN-SUITE-V1.md`

This family is not a shallow “easy suite.”

It is a product-shaping family because it should improve workflow economics
for every later campaign and every larger customer intake.

This family should answer:

- what the first iteration activates
- what gets inventoried versus deeply probed
- what gets deferred
- what findings seed the second iteration
- how the product keeps improving developmental speed from here on out

This is the planning-phase family.

Its current concrete v1 shape is:

- `efficiency_activation_design_suite_v1`
  - Spectrum-medium-derived
  - planning-first
  - selective deepening
  - pass-one / pass-two reuse

### 4. Cross-DLL interwoven state and initialization

Question:

- can the system infer ordering, prerequisites, and shared state across
  multiple DLLs and avoid treating every function as independently callable

This family should remain distinct from generic efficiency.

It is a stateful-system reasoning family.

### 5. Package realism and noisy archive intake

Question:

- can the system handle inherited real-world packages with clutter,
  dependencies, duplicates, partial artifacts, and irrelevant binaries

### 6. Unexpected binary shape and robustness

Question:

- can the system remain useful and non-fragile when binaries are malformed,
  sparse, oddly exported, or otherwise unlike the cleaner fixtures

### 7. Observability and failure localization

Question:

- when something breaks, can the system identify where it broke and leave a
  trustworthy operator-facing packet explaining the failure domain

### 8. Incremental reuse and second-pass improvement

Question:

- does the second iteration reuse first-pass findings and context well enough
  to deepen selectively instead of restarting cold

### 9. Operator usefulness

Question:

- does the first pass produce something a human operator can act on quickly:
  inventory, dependency map, likely high-value surfaces, trust packet, and the
  next deepening frontier

### 10. Regression and non-regression

Question:

- when one family improves, do other families silently regress

This family should also cover governed migration comparison when architecture
changes are intentionally allowed to improve internals without breaking
preserved contracts.

## Efficiency-First Product Principle

Efficiency should be treated as a first-class product family, not as cleanup
to do after semantic pressure is solved.

Reason:

- a product that can only reason deeply but cannot organize large intakes is
  not yet shaped like a usable product
- the planning and intake phase determines how all later work is activated,
  ranked, deferred, and seeded
- improving this family should make later proving and development faster across
  the board

The efficiency family should therefore be framed as:

- workflow and product economics
- staged activation
- first-pass operational map
- selective deepening

not merely:

- “easy suite that runs faster”

## Activation Principle

Not all systems need to be active on the first pass.
Not everything needs to be probed.

The product needs an activation policy.

Recommended staged shape:

- `Floor 0`
  - package admission
  - dependency grouping
  - duplicate and noise rejection
- `Floor 1`
  - inventory
  - callable surface map
  - rough ranking
  - likely stateful or high-value hubs
- `Floor 2`
  - selective deepening of the best frontier
- `Floor 3`
  - stateful and interwoven escalation only when first-pass evidence demands it

This staged activation model is a product capability.

It should be tested explicitly.

## Ordering View

Current recommendation:

- keep semantic and proving pressure alive through `hard01/hard02`
- keep the proving-lane trust campaign separate
- treat efficiency and intake planning as the next major product-shaping suite
  family
- treat cross-DLL interwoven state as another major suite family that should
  not be absorbed into efficiency

The current missing pressure families most likely to matter soon are:

- `efficiency / intake planning`
- `cross-DLL interwoven state`

## Constraint

Do not create one giant benchmark that mixes:

- proving-lane trust
- semantic truth
- efficiency
- stateful interwoven reasoning
- noisy package realism

That will destroy clean failure attribution and slow down learning again.
