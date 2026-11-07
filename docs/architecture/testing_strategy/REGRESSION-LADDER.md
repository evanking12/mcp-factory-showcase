# Regression Ladder

## Purpose

This document defines the additive regression ladder for MCP Factory.

The ladder is durable policy, not a temporary list of current suite names.
Current named suites are ladder members. Future harder suites extend this
ladder additively rather than replacing cheaper trusted tiers by default.

## Current Ladder

### Tier 0

- surface:
  - unit and contract tests
- cadence class:
  - frequent gate
- required when:
  - local logic, contract, schema, or helper behavior changes
- proves:
  - small logic and contract surfaces still hold
- does not prove:
  - lane trust
  - compiled-suite behavior
  - end-to-end proving health

### Tier 1

- surface:
  - lane trust
- cadence class:
  - frequent gate
- required when:
  - runtime, startup, bridge, lane, or harness trust changed
- proves:
  - the managed local lane is trustworthy enough to attempt bounded suite work
- does not prove:
  - suite semantics
  - non-regression of `easy01` or higher suites

### Tier 2

- surface:
  - `easy01`
- cadence class:
  - bounded local gate
- required when:
  - bounded compiled-suite behavior may have changed and a cheap end-to-end
    proving surface is needed
- proves:
  - the cheapest current compiled-ingest proving surface still behaves within
    preserved contract
- does not prove:
  - medium or hard family non-regression
  - broader product realism

### Tier 3

- surface:
  - `medium01`
- cadence class:
  - bounded local gate
- required when:
  - a change is strong enough that `easy01` alone is an incomplete pressure
    surface
- proves:
  - current medium-tier compiled-ingest behavior for the first restored medium
    proving family
- does not prove:
  - `medium02`
  - hard-family pressure
  - every proving family

### Tier 4

- surface:
  - `medium02`
- cadence class:
  - heavy gate
- required when:
  - a change touches surfaces known to affect the second medium family or when
    the current proving target explicitly depends on it
- proves:
  - non-regression across the second medium family once restored
- does not prove:
  - hard-family pressure
  - future heavier suites

### Tier 5

- surface:
  - `hard01`
- cadence class:
  - heavy gate
- required when:
  - the work touches the first hard-family pressure seam or when the branch is
    attempting to reopen hard-family progress
- proves:
  - preserved contract on the first hard-family proving surface
- does not prove:
  - `hard02`
  - future harder suites

### Tier 6

- surface:
  - `hard02`
- cadence class:
  - heavy gate
- required when:
  - the branch is reopening or claiming progress on the second hard family
- proves:
  - preserved contract on the second hard-family proving surface
- does not prove:
  - future heavier or broader proving families

## Extension Rule

- future suites are added to this ladder, not substituted silently
- lower trusted tiers remain unless policy explicitly deprecates them
- named suites such as `medium01` or `hard02` are current ladder members, not
  the whole abstraction
- a future suite must declare:
  - tier
  - cadence class
  - what it proves
  - what it does not prove

## Current Practical Cadence

- Tier 0 and Tier 1:
  - cheapest and most frequent
- Tier 2 and Tier 3:
  - current local-first regression gate family
- Tier 4 through Tier 6:
  - heavier or later-pressure gates that join the ladder when restored or when
    the product reopens those proving bands

## Stage Migration Claim Rule

Stage migration checks are not flat. A stage-local green result proves only
the local contract it covers.

- red/yellow/gray/green ownership markers in stage `TRACE.md` select the local
  blast radius
- this ladder selects the maximum non-regression claim
- broad compiled-suite non-regression requires the matching compiled-suite tier
- medium or hard recovery claims require their named tier, even when cheaper
  stage, artifact, or handoff checks are green
