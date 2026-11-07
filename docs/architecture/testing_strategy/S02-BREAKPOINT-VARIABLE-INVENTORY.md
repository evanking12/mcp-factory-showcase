# S-02 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-02 breakpoint maturity after the hosted-green
runtime split into:

- `S-02A probe_ordering`
- `S-02B invocation_execution`
- `S-02C evidence_capture`

The inventory decides which independent weakness variables deserve breakpoint
ladders. S-02A ordering quality, S-02B raw observation integrity, S-02B
argument construction, S-02B functional precondition handling, S-02C
probe-log durability, S-02C finding-status persistence, the S-02A -> S-02B
ordering-to-execution seam, the S-02B -> S-02C raw-observation durability
seam, and the S-02C -> S-03 probe-evidence consumability seam now have Tier 2
anchors. The remaining Tier 2 grounding campaign added Tier 2 evidence for
S-02A prerequisite DAG honesty, S-02A pass-scope containment, S-01 -> S-02A
unlock-to-ordering, S-02C state-effect preservation, S-02C post-probe
recalibration honesty, and S-02C -> S-03 missing-observation deferral. It also
recorded `blocked_at_tier2` for lane/runtime failure classification, S-02B
overtrust prevention, and the S-02A -> S-02B -> S-02C ordered evidence window.
All other S-02 rows remain `planned/0` until their own fixtures exist.

## Benchmark Question

Which S-02 stage-owned and seam-owned variables can lose, distort, overtrust,
undertrust, widen, narrow, or defer runtime probe evidence incorrectly, and
which variables should receive the first deterministic compiled breakpoint
fixtures?

## Inventory Fields

Every row must include:

| Field | Meaning |
| --- | --- |
| `owner_scope` | Stage, seam, or bottom-up window under pressure. |
| `ownership_type` | `stage-owned`, `seam-owned`, or `bottom-up window`. |
| `breakpoint_family` | Named independent weakness family. |
| `weakness_variable` | The exact variable that could invalidate the stage claim. |
| `target_tier` | Next honest target tier from `BREAKPOINT-TIER-RUBRIC.md`. |
| `fixture_shape` | Minimum product-shaped fixture needed to test the variable. |
| `claim_ceiling` | Strongest legal claim if the fixture passes. |
| `false_progress_risk` | What would make the result look stronger than it is. |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | target_tier | fixture_shape | claim_ceiling | false_progress_risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `S-02A probe_ordering` | `stage-owned` | `ordering quality` | dependency-like callables are ordered after setup/unlock context without executing calls | `Tier 2` | compiled DLL with clear init/read/write families, distractor exports, and deterministic expected order | S-02A can produce a useful ordered probe plan under medium naming pressure | treating broad Easy01 ordering success as local S-02A maturity |
| `S-02A probe_ordering` | `stage-owned` | `prerequisite DAG honesty` | prerequisite relationships are recorded as bounded guidance, not proven truth | `Tier 2` | compiled DLL with names/strings implying prerequisites plus false prerequisite distractors | S-02A records prerequisite guidance and uncertainty without overclaiming | asserting a perfect DAG when evidence is only static or name-derived |
| `S-02A probe_ordering` | `stage-owned` | `pass-scope containment` | probe plan keeps intended candidates ahead of broader fallback candidates without dropping fallback | `Tier 2` | compiled DLL with many candidate-looking exports and a small admitted probe scope | S-02A contains pass scope as ordering/budget guidance under moderate pressure | pretending S-02A filters runtime execution scope when it only orders/labels candidates |
| `S-02A probe_ordering` | `stage-owned` | `repeated-probe classification` | repeated probes that add no new evidence are classified for later handling | `Tier 3` | hard fixture or replay harness with repeated equivalent candidates and deterministic no-new-evidence expectation | S-02A can expose repeated-probe waste as a blocker family | pretending repeated broad-run slowness proves ordering classification |
| `S-02B invocation_execution` | `stage-owned` | `argument construction` | selected arguments match callable shape and available setup/unlock evidence | `Tier 2` | compiled DLL with simple typed exports, sentinel strings, and deterministic argument expectations | S-02B constructs usable arguments for medium-pressure simple exports | passing only zero-arg calls and calling argument construction mature |
| `S-02B invocation_execution` | `stage-owned` | `lane/runtime failure classification` | lane failures are separated from product-call failures | `blocked_at_tier2` | requires a deterministic lane-failure harness plus compiled product-call failure fixture | No Tier 2 claim; blocked because current local harness cannot separate infrastructure failure from compiled product-call failure without instability | allowing lane instability to masquerade as product behavior |
| `S-02B invocation_execution` | `stage-owned` | `functional precondition handling` | unmet preconditions are recorded as observations, not final semantic truth | `Tier 3` | hard stateful fixture with ambiguous/conflicting precondition signals after the Tier 2 blocked-before-init anchor | S-02B records blocked calls without pretending final semantics are known | scoring success only because a later stage repaired the interpretation |
| `S-02B invocation_execution` | `stage-owned` | `overtrust prevention` | static/unlock guidance does not force unsafe or unsupported invocations | `blocked_at_tier2` | hard ambiguity fixture with misleading names and weak static hints that should be deferred or tried conservatively | No Tier 2 claim; meaningful overtrust proof is Tier 3-shaped, so a shallow Tier 2 fixture would be theater | making the fixture too easy by using obviously bad names only |
| `S-02B invocation_execution` | `stage-owned` | `raw observation integrity` | return codes, side effects, exceptions, and call metadata remain intact | `Tier 3` | hard compiled fixture with ambiguous raw statuses, repeated observations, and deterministic non-rewrite expectations | S-02B preserves raw observations under hard single-family pressure | checking only that a probe log exists, not that it contains correct observations |
| `S-02C evidence_capture` | `stage-owned` | `probe-log durability` | raw observations survive persistence and session capture | `Tier 3` | hard S-02B-shaped packet with ambiguous, repeated, and conflicting-looking observations plus deterministic preservation expectations | S-02C persists probe logs under hard single-family durability pressure | checking only runtime memory, not durable artifacts |
| `S-02C evidence_capture` | `stage-owned` | `finding status persistence` | finding status updates preserve unresolved, blocked, ambiguous, and observed distinctions | `Tier 3` | hard fixture with repeated status changes, conflicting-looking status signals, and deterministic non-collapse expectations | S-02C keeps status distinctions reviewable under hard single-family pressure | collapsing all non-success into one generic unresolved bucket |
| `S-02C evidence_capture` | `stage-owned` | `state-effect preservation` | observed state effects remain linked to the calls that caused them | `Tier 2` | S-02B-shaped packet with state-effect trace metadata from a compiled stateful fixture shape | S-02C preserves state-effect lineage under medium preservation pressure | relying on final docs instead of durable probe evidence |
| `S-02C evidence_capture` | `stage-owned` | `downstream consumability` | S-03 can ingest S-02C evidence without hidden schema assumptions | `Tier 2` | persisted S-02C artifact packet consumed by a focused S-03 input check | S-02C emits evidence consumable by reconciliation | treating S-03 success as proof that S-02C artifacts are complete |
| `S-02C evidence_capture` | `stage-owned` | `post-probe recalibration honesty` | recalibration updates are recorded without rewriting probe truth | `Tier 2` | fixture with probe results that should adjust sentinel/write-unlock hints without changing raw observations | S-02C recalibration is additive and reviewable | hiding recalibration as an unobservable side effect |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | target_tier | fixture_shape | claim_ceiling | false_progress_risk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `S-01 -> S-02A` | `seam-owned` | `unlock-to-ordering handoff` | unlock evidence changes ordering but bad unlock evidence is contained | `Tier 2` | compiled fixture with one valid unlocked path, one blocked write path, and fallback candidates | handoff preserves unlock guidance without poisoning ordering or dropping fallback | blaming S-02A when S-01 emitted malformed unlock evidence |
| `S-02A -> S-02B` | `seam-owned` | `ordering-to-execution preservation` | ordered queue reaches execution without falling back to original scrambled input order | `Tier 3` | harder S-02A ordered plan replayed into execution with ambiguous prerequisite-looking distractors | execution preserves ordered-plan intake under hard seam pressure | testing S-02B directly and skipping the handoff |
| `S-02A -> S-02B` | `seam-owned` | `prerequisite overtrust` | execution treats prerequisite plan as guidance, not proof | `Tier 3` | hard fixture with misleading prerequisite-looking names and deterministic conservative execution expectation | the seam prevents prerequisite guidance from becoming unsafe execution truth | encoding the expected execution order directly in the test harness |
| `S-02B -> S-02C` | `seam-owned` | `raw-observation durability` | raw observation stream is persisted without loss or semantic rewriting | `Tier 2` | multiple raw results passed through S-02C with exact expected durable artifact rows | capture preserves execution truth across the boundary | asserting only final finding count |
| `S-02B -> S-02C` | `seam-owned` | `persistence mismatch` | persisted findings match probe log observations and status classes | `Tier 2` | fixture with success, blocked, exception, and ambiguous return cases | S-02B and S-02C agree on observation/status boundaries | accepting mismatch because downstream reconciliation still passes |
| `S-02C -> S-03` | `seam-owned` | `probe evidence consumability` | reconciliation receives enough evidence to classify contradictions without inventing truth | `Tier 2` | S-02C artifact packet with one contradiction-ready and one missing-observation case | S-03 can consume S-02C evidence boundaries | making S-03 read internal S-02 memory instead of durable artifacts |
| `S-02C -> S-03` | `seam-owned` | `missing-observation deferral` | missing observations remain visible rather than becoming false negatives | `Tier 2` | persisted packet with intentionally missing/blocked probe evidence | missing probe evidence is deferred honestly into reconciliation | counting absence of failure as success |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | target_tier | when_to_build |
| --- | --- | --- | --- | --- |
| `S-01 -> S-02A -> S-02B` | `bottom-up window` | unlock guidance becomes safe execution | `Tier 2` | Build only after S-02A ordering and S-02B argument construction have Tier 1 anchors. |
| `S-02A -> S-02B -> S-02C` | `bottom-up window` | ordered work becomes durable evidence | `blocked_at_tier2` | Attempted in `s02_remaining_tier2_grounding_v1`; current S-02B execution duplicated the read target and dropped the write target under ordered S-02A scope, so no Tier 2 claim is legal yet. |
| `S-02B -> S-02C -> S-03` | `bottom-up window` | raw runtime evidence becomes reconciliation input | `Tier 2` | Implemented as the first bottom-up window after adjacent S-02B, S-02C, S-02B -> S-02C, and S-02C -> S-03 anchors stayed green. |

## First Fixture Ranking

| Rank | Candidate | diagnostic_value | downstream_poison_risk | fixture_cost | blocker_family_relevance | Recommendation |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `S-02B invocation_execution: raw observation integrity` | 10 | 10 | 6 | 10 | Build first as `s02b_invocation_execution_tier1_anchor_v1`; it anchors whether execution truth is preserved before durability or reconciliation can be trusted. |
| 2 | `S-02B invocation_execution: lane/runtime failure classification` | 10 | 10 | 4 | 10 | Build after raw observation integrity unless a cheap controlled lane failure harness already exists. |
| 3 | `S-02C evidence_capture: probe-log durability` | 9 | 9 | 8 | 9 | Build after S-02B raw observation integrity so capture has known input truth. |
| 4 | `S-02A probe_ordering: ordering quality` | 8 | 8 | 8 | 8 | Build if execution fixtures need a trustworthy ordered queue first. |
| 5 | `S-02C -> S-03: probe evidence consumability` | 8 | 9 | 6 | 8 | Build after S-02C durability if reconciliation still masks S-02 evidence weakness. |

## Completed Tier 2 Grounding Campaign

Completed campaign: `s02_tier2_grounding_priority_v1`.

Campaign goal: ground S-02 in Tier 2 truth by priority, one breakpoint family
at a time. This does not mean all of S-02 becomes Tier 2 at once. It means each
promoted family must have its own fixture or harness, registry metadata,
proving-map row, inventory writeback, and hosted Stage Breakpoint evidence.

Priority criteria:

- downstream poison risk
- run-completion risk
- diagnostic value
- fixture cost
- dependency ordering

Current priority sequence:

| Priority | Scope | Breakpoint family | Target | Why now |
| ---: | --- | --- | --- | --- |
| 1 | `S-02A probe_ordering` | `ordering quality` | `Tier 2` | Implemented; S-02A can now produce a useful ordered probe plan under medium naming pressure. |
| 2 | `S-02B invocation_execution` | `argument construction` | `Tier 2` | Implemented; S-02B constructs usable typed arguments for medium-pressure simple exports. |
| 3 | `S-02B invocation_execution` | `functional precondition handling` | `Tier 2` | Implemented; blocked-before-init and allowed-after-init calls remain observations rather than final semantic truth. |
| 4 | `S-02C evidence_capture` | `finding status persistence` | `Tier 2` | Implemented; observed, blocked, ambiguous, and unresolved status distinctions remain reviewable in an S-02C-owned status artifact. |
| 5 | `S-02A -> S-02B` | `ordering-to-execution preservation` | `Tier 2` | Implemented; S-02B receives the S-02A ordered plan and preserves execution order under medium compiled seam pressure. |
| 6 | `S-02B -> S-02C` | `raw-observation durability` | `Tier 2` | Implemented; S-02B raw observations survive the live S-02C durability handoff under medium compiled pressure. |
| 7 | `S-02C -> S-03` | `probe evidence consumability` | `Tier 2` | Implemented; S-03 prefers the S-02C durable probe-log alias and reconciles only evidence-justified success. |
| 8 | `S-02B -> S-02C -> S-03` | `raw runtime evidence becomes reconciliation input` | `Tier 2` | Implemented; raw S-02B compiled observations pass through S-02C durable capture into S-03 reconciliation without false success. |

High-risk deferred family:

- `S-02B lane/runtime failure classification` remains one of the highest
  downstream-poison risks, but it is currently Tier 3-shaped and needs a
  deterministic failure-classification harness before implementation. Do not
  force it into the Tier 2 grounding sequence as a fake medium fixture.

## Implemented S-02A Anchor

Implemented campaign: `s02_tier2_grounding_priority_v1`.

Anchor name: S-02A ordering quality Tier 2 anchor.

Implemented minimum:

- Added one medium-pressure product-shaped compiled fixture:
  `tests/fixtures/s02a_probe_ordering_tier2/`.
- Proved S-02A preserves the full compiled callable inventory while moving
  setup/read-like work ahead of write/commit-like work under medium naming
  pressure.
- Proved the prerequisite-state artifact remains reviewable without claiming
  prerequisite DAG truth or downstream execution correctness.
- Registered `s02a_probe_ordering_breakpoint_suite` in Stage Breakpoint Checks.

Current claim ceiling:

- `S-02A can produce a useful ordered probe plan under medium naming pressure`.

Not claimed:

- prerequisite DAG semantic truth
- S-02B execution correctness
- S-02C durability
- S-01 unlock guidance quality
- Tier 3 ambiguous or hard ordering pressure

## Implemented First Anchor

Implemented campaign: `s02b_invocation_execution_tier1_anchor_v1`.

Anchor name: S-02B raw observation integrity Tier 1 anchor.

Implemented minimum:

- Added one product-shaped compiled fixture:
  `tests/fixtures/s02b_invocation_raw_observation_tier1/`.
- Proved S-02B preserves raw observations for one easy compiled invocation
  case through `s02b_invocation_execution_breakpoint_suite`.
- Registered the first S-02B stage-breakpoint suite in Stage Breakpoint
  Checks.

Current claim ceiling:

- `S-02B preserves raw observations for one easy compiled invocation case`.

Not claimed:

- lane/runtime failure classification
- medium argument pressure
- S-02C durability
- S-03 semantic interpretation

## Implemented Third Anchor

Implemented campaign:
`s02b_invocation_execution_tier2_raw_observation_pressure_v1`.

Anchor name: S-02B raw observation integrity Tier 2 anchor.

Implemented minimum:

- Added one medium-pressure product-shaped compiled fixture:
  `tests/fixtures/s02b_invocation_raw_observation_tier2/`.
- Proved S-02B preserves multiple deterministic raw observations, including
  success, blocked/precondition-like, warning-like, state-style, and typed
  argument-bearing calls.
- Kept the claim bounded to S-02B raw observation integrity; lane/runtime
  failure classification and S-02C durability remain separate variables.

Current claim ceiling:

- `S-02B preserves raw observations under medium compiled invocation pressure`.

Not claimed:

- lane/runtime failure classification
- Tier 3 ambiguous or hard raw-observation pressure
- S-02C durability
- S-03 semantic interpretation

## Implemented Fifth Anchor

Implemented campaign: `s02_tier2_grounding_priority_v1`.

Anchor name: S-02B argument construction Tier 2 anchor.

Implemented minimum:

- Added one medium-pressure product-shaped compiled fixture:
  `tests/fixtures/s02b_argument_construction_tier2/`.
- Proved S-02B constructs visible typed fallback arguments for quantity,
  amount, mode, and combined integer exports through the deterministic
  probe-loop seam.
- Proved compiled DLL return values encode the arguments actually received,
  so the suite tests argument use rather than only probe-log shape.
- Registered `s02b_argument_construction_breakpoint_suite` in Stage
  Breakpoint Checks.

Current claim ceiling:

- `S-02B constructs usable typed arguments for medium-pressure simple exports`.

Not claimed:

- raw observation integrity beyond the separate raw-observation suite
- lane/runtime failure classification
- functional precondition handling
- S-02C durability
- S-03 semantic interpretation

## Implemented Sixth Anchor

Implemented campaign: `s02_tier2_grounding_priority_v1`.

Anchor name: S-02B functional precondition handling Tier 2 anchor.

Implemented minimum:

- Added one medium-pressure stateful compiled fixture:
  `tests/fixtures/s02b_functional_precondition_tier2/`.
- Proved S-02B records a write-like call blocked before init, an init call,
  an allowed write-like call after init, and a status read without semantic
  rewriting.
- Preserved raw function names, args, result text, trace metadata, and
  classification boundaries for both blocked and successful observations.
- Registered `s02b_functional_precondition_breakpoint_suite` in Stage
  Breakpoint Checks.

Current claim ceiling:

- `S-02B records blocked calls without pretending final semantics are known`.

Not claimed:

- lane/runtime failure classification
- S-02A ordering-to-execution seam preservation
- S-02C durability
- S-03 semantic interpretation
- Tier 3 ambiguous or hard precondition pressure

## Implemented Seventh Anchor

Implemented campaign: `s02_tier2_grounding_priority_v1`, Prompt 05.

Anchor name: S-02C finding-status persistence Tier 2 anchor.

Implemented minimum:

- Added an S-02C-owned status artifact:
  `evidence/stage-02c-evidence-capture/finding-status.json`.
- Extended `tests/test_s02c_evidence_capture_breakpoint_suite.py` with a
  medium-pressure status-distinction test using observed, blocked, ambiguous,
  and unresolved S-02B-shaped rows.
- Proved S-02C preserves status, boundary, function, args, result excerpt,
  phase, and trace metadata without collapsing all non-success rows into one
  unresolved bucket.
- Registered `s02c_finding_status_persistence_breakpoint_suite` in Stage
  Breakpoint Checks.

Current claim ceiling:

- `S-02C preserves observed, blocked, ambiguous, and unresolved finding-status
  distinctions under medium pressure`.

Not claimed:

- S-02B execution correctness
- S-03 semantic interpretation
- S-02B -> S-02C seam agreement
- session ZIP capture
- Tier 3 hard status-distinction pressure

## Implemented Eighth Anchor

Implemented campaign: `s02_tier2_grounding_priority_v1`, Prompt 06.

Anchor name: S-02A -> S-02B ordering-to-execution seam Tier 2 anchor.

Implemented minimum:

- Added one seam-owned breakpoint test:
  `tests/test_s02a_s02b_seam_breakpoint_suite.py`.
- Reused the medium-pressure compiled ordering fixture:
  `tests/fixtures/s02a_probe_ordering_tier2/`.
- Proved S-02B consumes the S-02A ordered invocable plan in order rather than
  silently reverting to the original scrambled invocable order.
- Registered `s02a_s02b_ordering_execution_seam_breakpoint_suite` in Stage
  Breakpoint Checks.

Current claim ceiling:

- `S-02B receives the S-02A ordered plan and preserves execution order under
  medium compiled seam pressure`.

Not claimed:

- S-02A prerequisite DAG semantic truth
- S-02B broad execution correctness
- S-02B prerequisite overtrust handling
- S-02C durability
- bottom-up S-02A -> S-02B -> S-02C maturity
- Tier 3 hard seam pressure

## Implemented Ninth Anchor

Implemented campaign:
`s02b_s02c_raw_observation_durability_seam_tier2_v1`.

Anchor name: S-02B -> S-02C raw-observation durability seam Tier 2 anchor.

Implemented minimum:

- Added one seam-owned breakpoint test:
  `tests/test_s02b_s02c_seam_breakpoint_suite.py`.
- Reused the medium-pressure compiled S-02B raw-observation fixture:
  `tests/fixtures/s02b_invocation_raw_observation_tier2/`.
- Proved S-02B deterministic probe rows pass through the legacy
  `explore_probe_log.json` handoff into S-02C-owned durable aliases.
- Registered
  `s02b_s02c_raw_observation_durability_seam_breakpoint_suite` in Stage
  Breakpoint Checks.

Claim ceiling:

- `S-02B raw observations survive the live S-02C durability handoff under
  medium compiled pressure`.

Does not prove:

- S-02C -> S-03 consumability
- lane/runtime failure classification
- persistence mismatch beyond raw-observation durability
- bottom-up S-02A -> S-02B -> S-02C maturity
- Tier 3 hard seam pressure

## Implemented Second Anchor

Implemented campaign: `s02c_evidence_capture_tier1_anchor_v1`.

Anchor name: S-02C probe-log durability Tier 1 anchor.

Implemented minimum:

- Added one focused S-02C breakpoint test:
  `tests/test_s02c_evidence_capture_breakpoint_suite.py`.
- Proved S-02C persists one S-02B-shaped raw observation packet into the
  S-02C-owned probe-log alias without losing or semantically rewriting raw
  fields.
- Registered the first S-02C stage-breakpoint suite in Stage Breakpoint
  Checks.

Current claim ceiling:

- `S-02C persists one easy raw observation packet without loss or semantic rewriting`.

Not claimed:

- S-02B execution correctness
- multiple-observation or mixed-status durability pressure
- S-03 semantic interpretation
- session ZIP capture
- Easy01, Medium01, or hard-family non-regression

## Implemented Fourth Anchor

Implemented campaign: `s02c_evidence_capture_tier2_probe_log_durability_v1`.

Anchor name: S-02C probe-log durability Tier 2 anchor.

Implemented minimum:

- Added medium-pressure S-02C breakpoint coverage using multiple
  S-02B Tier-2-shaped raw observation packets.
- Proved S-02C preserves row order, function/tool names, args, raw result
  text, trace backend/function/raw-result metadata, argument counts, and
  classification/status boundaries.
- Kept the claim bounded to S-02C probe-log durability; S-02B execution,
  S-03 interpretation, finding-status persistence, and session ZIP capture
  remain separate variables.

Current claim ceiling:

- `S-02C persists multiple raw observation packets under medium durability pressure without loss or semantic rewriting`.

Not claimed:

- S-02B execution correctness
- S-02C finding-status persistence
- S-03 semantic interpretation
- session ZIP capture
- Tier 3 hard durability pressure

## Recommended Next Campaign

Completed active S-02 proving campaign:

- `s02_tier2_grounding_priority_v1`

Completed follow-on S-02 proving campaign:

- `s02b_s02c_raw_observation_durability_seam_tier2_v1`
- `s02c_s03_probe_evidence_consumability_tier2_v1`
- `s02c_s03_probe_evidence_consumability_breakpoint_suite`
- Claim ceiling: S-03 consumes S-02C durable probe evidence boundaries under medium focused seam pressure.

Current S-02 bottom-up proving campaign:

- `s02b_s02c_s03_bottom_up_evidence_window_tier2_v1`
- Registered suite:
  `s02b_s02c_s03_bottom_up_evidence_window_breakpoint_suite`
- Claim ceiling: S-02B raw observations pass through S-02C durable capture into S-03 reconciliation under medium focused bottom-up pressure.

Rationale:

- S-02B now has Tier 2 anchors for raw observations, argument construction, and
  functional precondition handling.
- S-02C now has Tier 2 anchors for probe-log durability and finding-status
  persistence.
- S-02A -> S-02B now has a Tier 2 ordering-to-execution seam anchor.
- S-02B -> S-02C now has a Tier 2 raw-observation durability seam anchor.
- S-02C -> S-03 now has a Tier 2 probe-evidence consumability seam anchor.
- The first bottom-up window now composes those adjacent anchors across
  S-02B -> S-02C -> S-03.

Completed remaining Tier 2 grounding campaign:

- `s02_remaining_tier2_grounding_v1`
- Registered suite:
  `s02_remaining_tier2_grounding_breakpoint_suite`
- Promoted families:
  - `S-01 -> S-02A unlock-to-ordering handoff`: Tier 2.
  - `S-02A prerequisite DAG honesty`: Tier 2.
  - `S-02A pass-scope containment`: Tier 2.
  - `S-02C state-effect preservation`: Tier 2.
  - `S-02C post-probe recalibration honesty`: Tier 2.
  - `S-02C -> S-03 missing-observation deferral`: Tier 2.
- Blocked rows:
  - `S-02B lane/runtime failure classification`: `blocked_at_tier2` until a deterministic lane-failure harness exists.
  - `S-02B overtrust prevention`: `blocked_at_tier2`; meaningful evidence is Tier 3-shaped.
  - `S-02A -> S-02B -> S-02C ordered evidence window`: `blocked_at_tier2`; attempted fixture exposed duplicate read execution and dropped write execution under ordered scope.

Deferred candidates:

- `s02b_lane_runtime_failure_classification_tier1_anchor_v1` after a
  deterministic failure-classification harness exists.
- `s02c_s03_missing_observation_deferral_tier2_v1` if absence handling becomes
  the next blocker.
- `s02a_s02b_s02c_bottom_up_ordered_evidence_window_tier2_v1` if the next
  short-chain claim needs S-02A ordering participation.

Completed Tier 2 durability pattern:

- Use upstream compiled/product-shaped S-02B Tier 2 evidence as the packet
  shape when S-02C is proving preservation rather than execution.
- Preserve function, args, raw result text, trace, argument count, row order,
  and status classification under moderate pressure.
- Keep lane/runtime failure classification separate unless a deterministic
  lane-failure harness is available.

## Questions This Suite Can Answer

- Which S-02A/B/C variables deserve stage-owned breakpoint ladders.
- Which S-02 seams deserve seam-owned breakpoint ladders.
- Which S-02 variables are too risky to test through broad Easy/Medium runs.
- Which first S-02 fixture is likely to produce the most diagnostic value.
- Whether S-02A ordering quality can preserve all candidate invocables and move
  setup/read-like work ahead of write/commit-like work under medium compiled
  naming pressure.
- Whether the first S-02B raw-observation Tier 1 anchor exists and where its
  claim ceiling stops.
- Whether the S-02B raw-observation Tier 2 anchor preserves multiple
  deterministic raw observations, typed arguments, raw results, trace metadata,
  and classification boundaries under medium compiled pressure.
- Whether S-02B functional precondition handling preserves blocked-before-init
  and allowed-after-init observations without turning them into final semantic
  truth.
- Whether the first S-02C probe-log durability Tier 1 anchor exists and where
  its claim ceiling stops.
- Whether S-02C probe-log durability preserves multiple mixed raw observations
  under medium pressure without loss or semantic rewriting.
- Whether S-02C finding-status persistence preserves observed, blocked,
  ambiguous, and unresolved distinctions under medium pressure.
- Whether the S-02A -> S-02B seam preserves S-02A ordered-plan intake into
  S-02B execution order under medium compiled seam pressure.
- Whether the S-02C -> S-03 seam lets S-03 consume S-02C durable probe evidence
  and avoid false success for blocked or missing observations under medium
  focused seam pressure.
- Whether raw S-02B compiled observations can flow through S-02C durable
  capture into S-03 reconciliation under medium focused bottom-up pressure.
- Whether S-01 unlock output can guide S-02A ordering without dropping fallback
  candidates under medium compiled pressure.
- Whether S-02A records prerequisite guidance and pass-scope containment as
  bounded ordering metadata rather than proven runtime truth.
- Whether S-02C preserves state-effect lineage and additive recalibration hints
  without rewriting raw probe evidence.
- Whether S-02C -> S-03 missing/blocked observations defer honestly instead of
  becoming false success.
- Whether S-02A -> S-02B -> S-02C ordered composition is currently blocked at
  Tier 2.

## Questions This Suite Cannot Answer

- Whether S-02A has maturity outside ordering quality, prerequisite DAG
  honesty, and pass-scope containment.
- Whether S-02A has Tier 3 ordering-quality maturity.
- Whether S-02B has Tier 1+ maturity outside raw observation integrity.
- Whether S-02B has Tier 3 raw-observation or functional-precondition maturity.
- Whether S-02C has Tier 1+ maturity outside probe-log durability and
  finding-status persistence.
- Whether S-02C has Tier 3 probe-log durability maturity.
- Whether S-02A -> S-02B has Tier 3 ordering-to-execution seam maturity or
  prerequisite-overtrust maturity.
- Whether S-01 -> S-02A -> S-02B is green as a bottom-up window.
- Whether S-02A -> S-02B -> S-02C is green as a bottom-up window; the first
  attempt is explicitly `blocked_at_tier2`.
- Whether S-03 has local contradiction-maturity breakpoint coverage.
- Whether lane/executor reliability is solved.
- Whether S-03 reconciliation correctly interprets all S-02 evidence.
- Whether Easy01, Medium01, or hard-family behavior is broadly non-regressed.
- Whether S-05 should be split.

## What The Next Suite In This Category Should Add

- A deterministic fixture or harness rule that separates product-call failure
  from lane/runtime failure.
- Fix or classify the S-02A -> S-02B -> S-02C ordered evidence duplication/drop
  before any Tier 2 bottom-up claim with ordering participation.
- Tier 3 S-02A -> S-02B seam pressure only after deterministic hard fixture
  expectations exist.

## Constraints

- No arbitrary synthetic or Python-only helper can promote a row above Tier 0.
- A stage-preservation harness packet may support Tier 1 or Tier 2 when it is
  shaped from an already compiled/product-shaped upstream anchor of matching
  tier and the stage under test owns persistence rather than execution.
- No broad hosted baseline pass can replace S-02 stage-owned evidence.
- No S-02 fixture may broaden S-01 unlock semantics, S-03 reconciliation
  semantics, or lane/executor behavior.
- Each fixture must pressure one breakpoint family first.

## Assumptions And Defaults

- `S-02A/B/C` runtime split is hosted-green at commit `180b6e8d`.
- Current S-02 breakpoint maturity is `Tier 2` for S-02A ordering quality,
  S-02B raw observation integrity, S-02B argument construction, S-02B
  functional precondition handling, S-02C probe-log durability, and S-02C
  finding-status persistence, S-02C state-effect preservation, S-02C
  post-probe recalibration honesty, plus S-01 -> S-02A, the S-02A -> S-02B
  ordering-to-execution seam and the S-02B -> S-02C raw-observation
  durability seam, the S-02C -> S-03 probe-evidence consumability seam, and
  missing-observation deferral seam, and the first S-02B -> S-02C -> S-03
  bottom-up evidence window.
- Current S-02 `blocked_at_tier2` rows are lane/runtime failure classification,
  overtrust prevention, and S-02A -> S-02B -> S-02C ordered evidence
  composition.
- The next implementation tranche is a decision gate: choose one Tier 3
  candidate, one remaining Tier 2 seam, the next bottom-up window, or S-05
  split-readiness only if hosted evidence stays green.
