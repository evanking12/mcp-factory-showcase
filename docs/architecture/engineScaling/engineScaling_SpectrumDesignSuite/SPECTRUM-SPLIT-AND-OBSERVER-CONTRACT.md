# Spectrum Split And Observer Contract

## Summary

The spectrum suite is meant to prove that intake and decomposition are part of
the architecture problem, not an implementation afterthought.

This contract defines:

- which split boundaries are plausible
- which split boundaries are misleading
- how to tell whether a split preserved meaning
- which observer outputs are required before hard is informative

## Candidate Split Boundaries

### Lifecycle-stage split

Units:

- bootstrap
- stage
- consumer fanout
- release
- reconcile/audit

Value:

- easy to explain to a human

Risk:

- can detach late truth from the artifact lineage that actually determines
  trust

### Producer-consumer split

Units:

- state producers
- direct consumers
- late validators

Value:

- strongest first candidate for medium because it keeps shared-state reuse
  visible

Risk:

- can still split away a validator that determines whether the shared state was
  trustworthy

### Interwoven-cluster split

Units:

- one cluster per artifact lineage family
- includes both producers and validating consumers for that lineage

Value:

- strongest hard-mode candidate when two plausible branches exist

Risk:

- harder to author and harder to review without strong observer support

## Right And Wrong Split Table

| Case | Likely Wrong Split | Why Wrong | More Honest Split | Why Better |
| --- | --- | --- | --- | --- |
| `medium-01` | Separate the reservation producer from the validating consumer that confirms whether the reservation handle remained trustworthy | A locally green consumer can hide that the shared handle was never preserved correctly | Keep the reservation producer, first fanout consumer, and first validator in one reasoning unit | Preserves the first meaningful lineage seam and keeps false-green visible |
| `medium-02` | Split by shallow module ownership so the same blocker family appears in disconnected modules | The blocker can appear to "change" only because the authored boundary changed | Keep the producer, reused artifact, and late validator in one comparison unit | Lets the same blocker family reappear honestly in a different transactional shape |
| `hard-01` | Split by lifecycle stage and treat each replay branch as an independent clean path | Ambiguity is flattened and the wrong branch can look locally successful | Keep competing lineage branches grouped with the late reconciliation and audit truth that chooses the trusted branch | Preserves ambiguity and stops local green from masquerading as global correctness |

## Bad Split Symptoms

- blocker family disappears only because the seam was cut away
- local green rises while late truth becomes harder to attribute
- lineage appears duplicated or cleaner than it really is
- one consumer goes green while another silently drifts from the shared cause
- the case becomes easier to read only because the hard dependency was detached

## Good Split Signals

- blocker family remains visible after the split
- lineage still maps back to the correct producer
- late truth still lands on the right upstream artifact family
- expected-versus-observed becomes clearer without flattening ambiguity
- recomposition still tells a coherent global story

## Decomposition Success Rubric

A valid split must:

- preserve blocker family
- preserve lineage
- prevent false-green
- preserve recomposability

A split should be treated as misleading even if local coverage rises when any
of those four conditions fail.

## Observer Contract

### Split-quality observer

Must answer:

- did the split preserve the primary blocker family?
- did the split remove the main hard seam instead of clarifying it?

Decision-bearing outputs:

- `split_verdict`
- `preserved_primary_blocker`
- `false_clarity_risk`
- `next_action`

### Lineage-preservation observer

Must answer:

- did the produced runtime artifact survive into the downstream reasoning unit?
- can late truth still map back to the correct artifact?

Decision-bearing outputs:

- `lineage_verdict`
- `missing_lineage_edges`
- `trusted_artifact_family`
- `next_action`

### False-green observer

Must answer:

- is any locally green path contradicted by later truth?
- did decomposition make a misleading local success look acceptable?

Decision-bearing outputs:

- `false_green_verdict`
- `affected_paths`
- `late_truth_conflict`
- `next_action`

### Decomposition-cohesion observer

Must answer:

- are the reasoning units still recomposable?
- can a human still explain the global transaction story after the split?

Decision-bearing outputs:

- `cohesion_verdict`
- `recomposition_gaps`
- `human_review_risk`
- `next_action`

### Blocker-stability observer

Must answer:

- is the same blocker family still present across medium cases?
- did the family drift because of a structural difference or because the
  doctrine was too broad?

Decision-bearing outputs:

- `blocker_stability_verdict`
- `same_family_confidence`
- `candidate_doctrine_split`
- `next_action`

## Product Lesson / Next System Implication

If split quality is weak:

- the product likely needs a first-class split-quality evaluation system before
  broader hard intake work

If observer coverage is weak:

- the product likely needs stronger lineage and false-green observers before
  hard diagnostic claims are trustworthy

## Evaluation

### What This Prompt Proved

- the suite now has explicit right and wrong split examples for every non-easy
  case
- the observer contract now includes decision-bearing outputs rather than names
  alone

### What Remains Unproven

- whether the concrete cases are authored sharply enough to trigger these
  observers meaningfully

### What Changed In The Spectrum Design

- decomposition quality is now a reviewable proof surface
- observer outputs can now drive later implementation rather than merely
  describe it

### Is The Planned Next Prompt Still Correct

- yes

### If Not, Write The Replacement Next Prompt Now

- not needed
