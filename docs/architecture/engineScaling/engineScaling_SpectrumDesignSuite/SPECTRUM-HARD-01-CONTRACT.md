# Spectrum Hard-01 Contract

## Case Name

`hard-01` = `branching_replay_settlement`

## Role In The Ladder

This is the first real-world-hard case.

It exists to teach:

- how the architecture should ingest a difficult shape
- how it should avoid dishonest decomposition
- what missing observers or runtime evidence systems are exposed first

It is local-only in v1.

## Transaction Story

The operator stages a release and two plausible branches exist:

- the primary release branch
- a replay or retry branch that emits artifacts that look locally valid

Both branches can produce:

- reservation-like handles
- attestation-like packets
- local consumer success

Only one branch is actually trusted once late reconciliation and audit arrive.

The late truth surfaces are:

- `settlement_reconcile.select_trusted_branch`
- `audit_trace.invalidate_untrusted_branch`

## Intake Pressure

This case should not be treated as one flat blob because:

- the wrong branch can look locally healthy
- the artifact lineage can be replayed in misleading ways
- the late truth must remain attached to the right upstream branch

## Competing Splits

Likely wrong split:

- split by lifecycle stage and treat each replay branch as independent clean
  stage output

Why wrong:

- it hides branch ambiguity
- it lets one locally green replay path escape late-truth attribution

More honest split:

- keep competing lineage branches grouped with the late reconciliation and
  audit truth that chooses the trusted branch

Why better:

- ambiguity stays visible
- false local green remains attributable

## Useful Failure Vs Dangerous Failure

| Type | Example | What It Teaches |
| --- | --- | --- |
| Useful failure | The pipeline keeps both branches visible, reports uncertainty, and points to missing branch-trust evidence | A branch-trust observer or replay-provenance evidence system is needed |
| Useful failure | The pipeline narrows to one likely bad split and explains why recomposition is weak | Split-quality evaluation needs strengthening |
| Dangerous failure | One replay branch goes locally green and the pipeline presents it as global success | False-green detection is too weak |
| Dangerous failure | The pipeline collapses both branches into one clean story too early | Ambiguity preservation is too weak |
| Dangerous failure | The blocker is mislabeled as generic setup trouble | Hard-mode doctrine is flattening under pressure |

## Expected Current Loss

Expected current failure mode:

- locally plausible replay artifacts are likely to outrank late branch-truth too
  early

Likely missing observer candidate:

- branch-trust or replay-conflict observer

Likely missing runtime evidence candidate:

- replay provenance artifact linking late truth back to the correct branch

Likely wrong split boundary:

- lifecycle-stage split that separates branch output from late reconciliation

## What Hard Should Teach Before Unlock Work Matters

Before hard unlock counts matter, `hard-01` should teach:

- whether ambiguity is preserved
- whether false-green is detected
- whether the wrong split is visible
- whether the next missing system is an observer problem, a runtime evidence
  problem, or a doctrine split problem

## Product Lesson / Next System Implication

If hard is informative while mostly red:

- the product is learning what missing evidence and observer systems to build
  next, which is the correct v1 outcome

If hard is too vague to steer from:

- the authored case is still underdesigned and should be tightened before any
  serious implementation claim

## Evaluation

### What This Prompt Proved

- the hard case is now defined by useful-vs-dangerous failure, not just higher
  complexity

### What Remains Unproven

- whether the current suite contract is ready to move into fixture authoring

### What Changed In The Spectrum Design

- hard now has a concrete branch-ambiguity and replay-trust story

### Is The Planned Next Prompt Still Correct

- yes

### If Not, Write The Replacement Next Prompt Now

- not needed
