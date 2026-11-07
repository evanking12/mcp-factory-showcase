# Stage Split Migration Comparison Suite v1

## Purpose

`stage_split_migration_comparison_suite_v1` exists to judge a migration slice
by preserved contracts plus justified improvements, not by naive artifact
identity.

Its purpose is to keep Phase 1 honest when the new pipeline gets cleaner or
more decomposed:

- preserved contracts must still hold
- real improvements must not be mislabeled as regressions
- changed surfaces must be explicitly classified instead of waved through

## Benchmark Question

For the first `S-02` dual-write migration slice:

- can the repo preserve the contracts it promised to preserve while allowing
  additive `N-03` / `N-04` / `N-06` outputs and sharper attribution or reuse

## Fixture Shape

This suite compares one bounded pre-change baseline capture against one bounded
post-change candidate capture for the same Phase 1 migration target.

Required fixture properties:

- unique output root for both baseline and candidate
- same bounded `S-02` pressure family
- contract artifacts emitted:
  - `stage-index.json`
  - `transition-index.json`
  - root-integrity validation summary
- first-wave reader evidence available
- explicit difference and improvement claims authored before final verdict

## Required Outputs

- baseline snapshot artifact
- preserved-contract matrix
- explicit-difference claims register
- improvement evidence packet
- final comparison result

## Acceptance Criteria

The suite passes only if all are true:

- every changed surface is classified
- no preserved-contract row is red
- no unclassified difference remains
- additive `N-03` / `N-04` / `N-06` outputs are present and explicitly
  classified as improvements or claimed differences
- 7-stage operator truth remains canonical during Phase 1
- first-wave reader compatibility remains green
- root-integrity evidence for baseline and candidate is trusted

The suite fails if any of these are true:

- old alias surfaces stop being readable
- `stage-index.json` or `transition-index.json` drift in meaning
- `S-04R` semantics change
- first-wave readers stop functioning
- root-integrity evidence is stale, mixed, or missing
- a changed surface appears with no bucket assignment

## Constraints

- this suite does not replace `compare-runs`
- this suite does not prove hard-family semantic progress
- this suite does not authorize alias shrink
- this suite is only for bounded migration slices where operator truth must
  stay stable while internal ownership changes

## Assumptions And Defaults

- baseline truth comes from one fresh pre-change bounded local capture, not
  from prompt memory
- candidate truth comes from one post-change bounded local capture with the
  same bounded pressure family
- Phase 1 retains 7-stage operator truth as canonical
- internal routing, additive outputs, and decomposition are allowed to change
  only when classified

## Comparison Buckets

### Must Remain Equivalent

- old `S-02` alias surfaces still readable
- `stage-index.json` and `transition-index.json` still express 7-stage
  operator truth
- `S-04R` semantics unchanged
- first-wave readers still function
- root-integrity rules still hold

### Allowed To Improve

- sharper failure attribution
- better checkpoint reuse boundaries
- additive `N-03` / `N-04` / `N-06` outputs
- more localized diagnostics
- less conflated ownership

### Allowed To Differ Only With Explicit Claim

- decomposed artifact contents
- clearer ranking or probe summaries
- richer intermediate outputs
- internal routing changes that preserve reader and operator truth

## Verdict Model

- `preserved_contract_pass`
- `improvement_confirmed`
- `explicit_difference_accepted`
- `blocked_regression`
- `unclassified_difference`

## Questions This Suite Can Answer

- did the migration break a preserved contract
- did the migration produce additive improvements without poisoning operator
  truth
- is a changed surface explicitly classified and justified
- is the slice safe enough to continue without recovery archaeology

## Questions This Suite Cannot Answer

- whether the broader 11-stage architecture is fully correct
- whether later stage splits are safe
- whether hard-family semantic proving should reopen
- whether the migration improved every downstream workflow cost

## What The Next Suite In This Category Should Add

- real multi-slice migration comparison across Phase 1 and Phase 2
- stronger reader-compatibility coverage beyond the first-wave reader set
- compare-time checkpoint reuse economics instead of only contract
  preservation
