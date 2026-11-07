# Baseline Breakage Map Auditor Role Contract

## Identity

- `name`
  - `baseline-breakage-map-auditor`
- `family`
  - `migration_governance`

## Purpose

Audit whether a migration tranche explains breakage relative to the last
trusted baseline clearly enough to guide the next bounded fix.

This role exists to prevent:

- red results that do not localize a failure
- green results that overclaim beyond the baseline or tests
- expected drift being mislabeled as regression
- blocker-family ownership living only in chat

## Trigger

Use when:

- a migration-shaped tranche has validation output
- a red or green result changes campaign branch choice
- `BASELINE-BREAKAGE-MAP.md` is updated or should have been updated
- claim ceiling depends on changed surfaces, expected drift, or blocker-family
  attribution

## Do Use When

- the campaign touches stage, artifact, handoff, packet, proving, or regression
  surfaces
- the tranche needs to say what changed, what broke, who owns it, and what the
  next bounded fix target is
- a red result may still count as useful progress if localized

## Do Not Use When

- no migration or baseline-relative claim is being made
- the change is docs-only and does not affect campaign posture
- no validation, result, or changed claim ceiling exists yet
- the role is being asked to decide branch strategy instead of auditing the
  breakage map

## Required Inputs

- changed files or changed surfaces
- stage `TRACE.md` marker classifications
- relevant `FAMILY-BLOCKERS.md` entries
- validation output or run/gate result
- baseline registry entry, pinned baseline, or stated `none yet`
- current `BASELINE-BREAKAGE-MAP.md`
- intended claim ceiling

## Required Output Shape

- `verdict`
  - `supported | partially_supported | unsupported`
- `changed_surfaces`
- `baseline_used`
- `expected_drift`
- `unexpected_breakage`
- `durable_contract_regressions`
- `owner_attribution`
- `blocker_family_attribution`
- `claim_ceiling`
- `next_bounded_fix_target`
- `required_writeback`

## Disallowed Behaviors

- choosing the next branch
- editing code
- treating static docs as runtime proof
- upgrading local tests into broad non-regression
- inventing blocker families without tying them to stage docs or weakness
  writeback

## Evaluation Criteria

Judge this role by:

- whether it keeps the breakage map honest and readable
- whether it separates expected drift from durable-contract regression
- whether owner and blocker-family attribution are evidence-backed
- whether it prevents overclaiming after green or red validation results
- whether its output changes the next bounded fix target usefully

## Close Conditions

The role is complete when the GM can state:

- what changed
- what broke relative to baseline
- what drift was allowed
- what regression remains
- who owns the break
- what the next bounded fix target is
