# Verification System

## Purpose

The verification system owns confidence gates.

Its job is to decide whether a change is trustworthy enough to keep.

This includes both local correctness and architecture-specific proof that a
change did not silently invalidate contracts, lanes, or comparison logic.

## Owned Surfaces

Primary owned areas:

- `tests/`
- `scripts/harness.py`
- `scripts/verify_sync.py`
- test fixtures and suite runners used for architecture proving

Related surfaces:

- focused run scripts
- compare-run discipline
- required-check policy tied to touched systems

## Primary Inputs

- changed files
- claimed outcomes
- run artifacts
- suite results
- system boundaries and contract expectations

## Primary Outputs

- test results
- sync-check results
- pass/fail confidence gates
- regression detection
- evidence that a claimed improvement is real

## Public Contracts

Critical contracts include:

- required commands in `AGENTS.md`
- sync tier semantics
- fixture validity
- compare-run and proving-run discipline

## Invariants

- required checks must reflect the touched systems
- no claim should outrun the evidence actually produced
- reproducible proof outranks intuition
- architecture changes should be accompanied by the tests that prove the new
  contract

## Common Failure Modes

- tests green but the wrong live lane was trusted
- broad changes merged with only focused tests
- regression masked by incomparable runs
- architecture docs drift from what the tests actually enforce
- suite progress claimed without meaningful authored checkpoint alignment

## Observability Gaps

Current recurring gaps include:

- no dedicated post-change review gate bot yet
- no stronger handoff format binding claims to exact evidence and checks
- no full system-aware verification router yet, even though the repo is now
  large enough to benefit from one

## Typical Tests And Checks

Common verification surfaces:

- `python scripts/verify_sync.py --tier A`
- `python scripts/verify_sync.py --tier B` when classification changes
- `python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py`
- focused suite tests for touched components
- bounded proving runs on the trusted local lane

## Agent Guidance

Use this doc before editing when the task involves:

- selecting the right checks
- proving an architecture change
- validating suite progress
- deciding whether a run is promotable

Default related skills:

- `ledger-auditor`
- `cross-dll-evidence-auditor`
- `triage-next-step`
- `baseline-promoter`

## Do Not Own

The verification system does not own the runtime or reasoning implementation
itself.

It owns the rules and evidence by which those systems are trusted.
