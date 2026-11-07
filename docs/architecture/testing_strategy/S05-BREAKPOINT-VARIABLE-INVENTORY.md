# S-05 Breakpoint Variable Inventory

## Purpose

This is the durable inventory for S-05 breakpoint maturity after the
hosted-green runtime split into:

- `S-05A schema_backfill`
- `S-05B verification_replay`
- `S-05C read_to_write_chaining`

The inventory decides which independent weakness variables deserve breakpoint
ladders. Rows stay `planned/0` until their own fixtures or harnesses exist.

## Benchmark Question

Which S-05 stage-owned, seam-owned, and bottom-up variables can lose, distort,
overtrust, undertrust, widen, narrow, defer, or misclassify enrichment and
verification evidence, and which variables should receive the first
deterministic breakpoint fixtures?

## Inventory Fields

Every row must include:

| Field | Meaning |
| --- | --- |
| `owner_scope` | Stage, seam, or bottom-up window under pressure. |
| `ownership_type` | `stage-owned`, `seam-owned`, or `bottom-up window`. |
| `breakpoint_family` | Named independent weakness family. |
| `weakness_variable` | The exact variable that could invalidate the stage claim. |
| `current_tier` | Current evidence level. |
| `target_tier` | Next honest target tier from `BREAKPOINT-TIER-RUBRIC.md`. |
| `fixture_shape` | Minimum product-shaped fixture or harness needed. |
| `claim_ceiling` | Strongest legal claim if the fixture passes. |
| `false_progress_risk` | What would make the result look stronger than it is. |
| `next_gap` | The next concrete suite or harness needed. |

## Inventory Dashboard

| Category | Count | Current state | Next gap |
| --- | ---: | --- | --- |
| Stage-owned breakpoint families | 16 | 12 are `Tier 2`, 3 are `blocked_at_tier2`, 1 is `deferred_as_tier3_shaped` | fix state-effect replay harness, retry containment widening, or bridge/degradation harness |
| Seam-owned breakpoint families | 4 | 3 are `Tier 2`, 1 is `blocked_at_tier2` | add explicit S-05C decision consumer surface for S-06 |
| Bottom-up window candidates | 3 | 2 are `Tier 2`, 1 is `blocked_at_tier2` | unblock S-05C -> S-06 before claiming the last window |
| Total S-05 proving families/windows | 23 | 17 are `Tier 2`, 5 are `blocked_at_tier2`, 1 is `deferred_as_tier3_shaped` | use this as the S-05 hard01 prediction surface |

## Stage-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-05A schema_backfill` | `stage-owned` | `schema provenance` | backfilled descriptions remain linked to synthesis evidence and are not presented as verified truth | `Tier 2` | `Tier 3` | schema snapshot plus synthesis-derived descriptions with mixed evidence strength | S-05A records schema-backfill provenance under medium evidence pressure without proof laundering | treating any filled description as proof | Tier 3 mixed-provenance fixture after prose-as-proof prevention |
| `S-05A schema_backfill` | `stage-owned` | `prose-as-proof prevention` | synthesized prose does not become executable or verified evidence | `Tier 2` | `Tier 3` | synthesis packet with confident prose, weak evidence, and unsupported description candidates | S-05A keeps prose-derived enrichment separate from proof | using S-05B verification success to excuse S-05A overclaiming | Tier 3 mixed-provenance ambiguity |
| `S-05A schema_backfill` | `stage-owned` | `partial-backfill honesty` | partial schema enrichment remains explicit rather than looking complete | `Tier 2` | `Tier 3` | schema with some supported, unsupported, and absent parameter descriptions | S-05A preserves partial-backfill boundaries | counting no crash as schema completeness | Tier 3 larger partial-schema fixture |
| `S-05A schema_backfill` | `stage-owned` | `schema compatibility preservation` | backfill does not corrupt callable schema, parameter names, or legacy paths | `Tier 2` | `Tier 3` | schema with optional fields, existing descriptions, and unsupported fields | S-05A backfills additively without schema corruption | checking only artifact existence | Tier 3 compatibility guard fixture |
| `S-05B verification_replay` | `stage-owned` | `direct replay truth` | replayed working-call evidence records actual replay result, not inherited confidence | `Tier 2` | `Tier 3` | deterministic compiled fixture with true replay success, state-drift rejection, unsupported replay, and typed argument preservation | S-05B distinguishes replayed truth from inherited success claims under deterministic compiled replay pressure | treating this as state-effect verification or weak-positive non-promotion proof | Tier 3 hard replay fixture with noisier mixed evidence after local S-05B families advance |
| `S-05B verification_replay` | `stage-owned` | `state-effect verification` | state-changing claims verify the effect lineage, not just call success | `blocked_at_tier2` | `Tier 2` | stateful compiled fixture with before/after read and write-like mutation | No Tier 2 claim; local DLL replay does not preserve same-session state effects strongly enough yet | treating return success as effect proof | build trustworthy same-session state-effect harness |
| `S-05B verification_replay` | `stage-owned` | `weak-positive non-promotion` | weak positives and partial successes stay separate from verified evidence | `Tier 2` | `Tier 3` | mixed verification packet with inferred, verified, failed, partial, and state-drift cases | S-05B keeps weak-positive replay outcomes separate from verified evidence under deterministic medium replay pressure | collapsing inferred and verified rows | Tier 3 hard mixed-status replay fixture |
| `S-05B verification_replay` | `stage-owned` | `bridge/degradation classification` | bridge or harness degradation is not blamed on product behavior | `blocked_at_tier2` | `Tier 2` | deterministic bridge-degradation harness plus product-call failure fixture | No Tier 2 claim until deterministic harness separates infra failure from product failure | treating flaky bridge failures as verified product results | build deterministic infra-versus-product failure harness |
| `S-05B verification_replay` | `stage-owned` | `finding-patch honesty` | patched findings preserve original, replay result, and reason for change | `Tier 2` | `Tier 3` | findings packet with verified, failed, unchanged, and partial patches | S-05B patches findings with reviewable provenance | only checking final finding count | Tier 3 mixed-status patch fixture |
| `S-05B verification_replay` | `stage-owned` | `partial verification coverage` | partial replay coverage is durable and does not imply full DLL proof | `Tier 2` | `Tier 3` | verification report with skipped, blocked, verified, and failed rows | S-05B reports partial coverage honestly | treating Medium01 pass as local verification coverage | Tier 3 partial-coverage fixture |
| `S-05C read_to_write_chaining` | `stage-owned` | `verified-read extraction` | only verified read evidence is used as a value source for write retry | `Tier 2` | `Tier 3` | verification report with verified read, inferred read, failed read, partial read, and irrelevant read | S-05C extracts write-retry values only from verified read evidence under medium MC-5 pressure | allowing inferred reads into retry inputs | Tier 3 hard verified-read extraction fixture |
| `S-05C read_to_write_chaining` | `stage-owned` | `read-to-write dependency honesty` | read-to-write dependency remains a bounded hypothesis, not proof of write success | `Tier 2` | `Tier 3` | MC-5 packet with matching, weak, and absent read/write relationships | S-05C records dependency decisions with caveats | claiming chained retry correctness without execution | Tier 3 hard dependency ambiguity |
| `S-05C read_to_write_chaining` | `stage-owned` | `retry containment` | MC-5 retry plan does not widen beyond admitted unresolved write targets | `blocked_at_tier2` | `Tier 2` | unresolved write set with distractor writes and verified read values | No Tier 2 claim; medium harness exposes retry widening to distractor writes | broadening retries because a read value exists | fix containment or add explicit admitted-write scope |
| `S-05C read_to_write_chaining` | `stage-owned` | `weak-ID/value overtrust` | weak IDs, ambiguous values, or stale reads are deferred rather than forced | `deferred_as_tier3_shaped` | `Tier 3` | hard ambiguous fixture with conflicting IDs, stale values, and repeated candidates | No Tier 2 claim; meaningful overtrust pressure is hard/ambiguous | making ambiguity too obvious in a shallow Tier 2 | Tier 3 only after containment blocker is resolved |
| `S-05C read_to_write_chaining` | `stage-owned` | `MC-5 decision durability` | MC-5 decisions persist inputs, caveats, and selected targets for review | `Tier 2` | `Tier 3` | MC-5 decision artifact with chosen, deferred, and rejected candidates | S-05C writes reviewable MC-5 decisions | checking only that a file exists | Tier 3 durability under conflicting decision inputs |
| `S-05C read_to_write_chaining` | `stage-owned` | `unresolved deferral` | unresolved or unsafe retry cases remain visible for S-06 | `Tier 2` | `Tier 3` | MC-5 packet with unsafe, missing, and unresolved retry cases | S-05C defers unresolved cases without hiding them | treating no retry as success | S-05C -> S-06 seam consumer surface |

## Seam-Owned Variables

| owner_scope | ownership_type | breakpoint_family | weakness_variable | current_tier | target_tier | fixture_shape | claim_ceiling | false_progress_risk | next_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `S-04 -> S-05A` | `seam-owned` | `synthesis-to-backfill provenance` | synthesized claims enter S-05A with provenance and uncertainty intact | `Tier 2` | `Tier 3` | S-04-shaped synthesis output with supported, weak, and unsupported schema descriptions | S-05A consumes synthesis without treating prose as proof | testing S-05A with hand-authored trusted schema only | Tier 3 mixed synthesis pressure |
| `S-05A -> S-05B` | `seam-owned` | `enrichment-to-verification boundary` | backfilled schema informs replay without becoming verification proof | `Tier 2` | `Tier 3` | S-05A backfill artifact plus S-05B replay candidates with mixed provenance | S-05B keeps enriched schema separate from replay evidence | claiming verification because a backfilled description exists | Tier 3 enrichment/replay ambiguity |
| `S-05B -> S-05C` | `seam-owned` | `verified-to-chaining boundary` | verified, inferred, failed, partial, and state-drift replay statuses reach MC-5 distinctly | `Tier 2` | `Tier 3` | S-05B compiled seam fixture with verified read output, weak rows, and state-drift row feeding S-05C MC-5 selection | S-05C chains only from S-05B-verified read evidence under medium seam pressure | allowing inferred, partial, failed, or state-drift evidence to drive retries | Tier 3 ambiguous verified/inferred handoff fixture |
| `S-05C -> S-06` | `seam-owned` | `chaining-to-gaps deferral` | unresolved retry outcomes and caveats remain visible to gap handling | `blocked_at_tier2` | `Tier 2` | MC-5 decision artifact with selected, deferred, unsafe, and unresolved outcomes | No Tier 2 claim; S-06 does not yet expose an explicit S-05C decision consumer boundary | counting S-06 fallback as S-05C seam maturity | add explicit S-05C decision consumer surface |

## Bottom-Up Window Candidates

| owner_scope | ownership_type | breakpoint_family | current_tier | target_tier | when_to_build |
| --- | --- | --- | --- | --- | --- |
| `S-05A -> S-05B -> S-05C` | `bottom-up window` | enriched schema becomes verification input and bounded MC-5 decision | `Tier 2` | `Tier 3` | Built in `s05_full_family_tier2_baseline_v1`; Tier 3 waits for harder mixed provenance and chaining pressure. |
| `S-04 -> S-05A -> S-05B` | `bottom-up window` | synthesis claim becomes backfill then replay verification | `Tier 2` | `Tier 3` | Built in `s05_full_family_tier2_baseline_v1`; Tier 3 waits for harder synthesis/proof-laundering ambiguity. |
| `S-05B -> S-05C -> S-06` | `bottom-up window` | verification and chaining outcomes become gap decisions | `blocked_at_tier2` | `Tier 2` | Blocked until `S-05C -> S-06` has an explicit decision-consumer surface. |

## First Fixture Ranking

| Rank | Candidate | diagnostic_value | downstream_poison_risk | run_completion_risk | fixture_cost | dependency_ordering | Recommendation |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `S-05B verification_replay: direct replay truth` | 10 | 10 | 7 | 6 | 10 | Built as `s05_breakpoint_tier1_tier2_execution_v1`; false verification poisons MC-5, S-06, and final claims. |
| 2 | `S-05B verification_replay: weak-positive non-promotion` | 9 | 10 | 6 | 6 | 8 | Built as `s05_stage_anchor_tier2_grounding_v1`; weak positives are now compared against anchored replay facts. |
| 3 | `S-05A schema_backfill: schema provenance` | 8 | 8 | 5 | 8 | 7 | Built as `s05_stage_anchor_tier2_grounding_v1`; prose-derived enrichment now carries a proof-boundary surface. |
| 4 | `S-05C read_to_write_chaining: verified-read extraction` | 8 | 9 | 7 | 6 | 6 | Built as `s05_stage_anchor_tier2_grounding_v1`; verified input boundary is now locally anchored. |
| 5 | `S-05B verification_replay: finding-patch honesty` | 8 | 9 | 6 | 5 | 7 | Build next if S-05B patch provenance remains the highest-risk local gap. |
| 6 | `S-05B -> S-05C: verified-to-chaining boundary` | 9 | 9 | 7 | 5 | 5 | Built as `s05b_s05c_verified_to_chaining_seam_tier2_v1`; verified replay output now feeds MC-5 without weak-row promotion. |

## Questions This Suite Can Answer

- Which S-05A/B/C variables deserve stage-owned breakpoint ladders.
- Which S-05 seams deserve seam-owned breakpoint ladders.
- Which S-05 bottom-up windows should wait for prerequisite stage/seam anchors.
- Which S-05 variables are too risky to test through broad Easy/Medium/Hard
  runs alone.
- Which first S-05 fixture is likely to produce the most diagnostic value.

## Questions This Suite Cannot Answer

- Whether S-05A/B/C have broad Tier 1 or Tier 2 maturity beyond the named
  implemented rows.
- Whether verification replay is correct.
- Whether MC-5 chaining is correct.
- Whether S-05 seams into S-06 are mature.
- Whether Easy01, Medium01, hard01, or hard02 behavior is broadly non-regressed.

## What The Next Suite In This Category Should Add

- A narrow S-05B finding-patch honesty anchor or S-05A prose-as-proof
  prevention anchor.
- Deterministic fixture expectations that preserve original status, replay
  result, verification reason, and patch provenance.
- S-05 seams only after enough local S-05A/B/C anchors exist.

## Constraints

- No arbitrary synthetic or Python-only helper can promote a row above Tier 0.
- No broad hosted baseline pass can replace S-05 stage-owned evidence.
- No S-05 fixture may broaden S-04 synthesis, S-06 gap handling, MC-5, bridge,
  lane, model, or verification semantics.
- Each fixture must pressure one breakpoint family first.

## Assumptions And Defaults

- S-05 runtime split is hosted-green at commit `5c9d9579`.
- `S-05A/B/C` are full runtime-visible stages under the `s05_enrichment`
  compatibility parent.
- Current S-05 breakpoint maturity is `Tier 2` for 17 S-05 rows, with
  `blocked_at_tier2` rows for state-effect verification, bridge/degradation
  classification, retry containment, S-05C -> S-06 handoff, and the dependent
  S-05B -> S-05C -> S-06 bottom-up window.
- `S-05C weak-ID/value overtrust` is `deferred_as_tier3_shaped`; a shallow
  Tier 2 fixture would be false progress.
- The next implementation campaign should target one blocked row or freeze this
  S-05 baseline for hard01 comparison.

## Implemented Breakpoint Suites

### S-05B Direct Replay Truth Tier 2 Anchor

Campaign: `s05_breakpoint_tier1_tier2_execution_v1`

Check: `s05b_verification_replay_breakpoint_suite`

Ownership type: `stage-owned`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-05B distinguishes replayed truth from inherited working-call confidence under deterministic compiled replay pressure`.

Questions this suite can answer:

- Whether S-05B replays an inherited working call against a compiled DLL.
- Whether replay success is recorded as replayed truth rather than inherited
  confidence.
- Whether state-drift replay rejects an inherited success instead of preserving
  a stale working call.
- Whether unsupported replay candidates avoid silent promotion.
- Whether typed argument values survive into the verification report and patch.

Questions this suite cannot answer:

- Whether S-05B state-effect verification is mature.
- Whether S-05B weak-positive non-promotion is mature.
- Whether bridge/degradation classification is mature.
- Whether S-05C uses verified read evidence correctly.
- Whether S-05 seams or bottom-up windows compose.

### S-05 Stage Anchor Tier 2 Grounding

Campaign: `s05_stage_anchor_tier2_grounding_v1`

Implemented rows:

| Suite | Scope | Breakpoint family | Ownership type | Current tier | Claim ceiling |
| --- | --- | --- | --- | --- | --- |
| `s05b_weak_positive_breakpoint_suite` | `S-05B verification_replay` | `weak-positive non-promotion` | `stage-owned` | `Tier 2` | S-05B keeps weak-positive replay outcomes separate from verified evidence under deterministic medium replay pressure. |
| `s05a_schema_provenance_breakpoint_suite` | `S-05A schema_backfill` | `schema provenance` | `stage-owned` | `Tier 2` | S-05A records schema-backfill provenance under medium evidence pressure without proof laundering. |
| `s05c_verified_read_extraction_breakpoint_suite` | `S-05C read_to_write_chaining` | `verified-read extraction` | `stage-owned` | `Tier 2` | S-05C extracts write-retry values only from verified read evidence under medium MC-5 pressure. |

Questions this suite can answer:

- Whether S-05B skips explicitly weak replay rows even when a compiled export
  would return success.
- Whether S-05A emits a reviewable enrichment-not-verification provenance
  boundary.
- Whether S-05C chains only from verified read evidence rather than inherited
  success, inferred, partial, failed, or irrelevant read rows.

Questions this suite cannot answer:

- Whether S-05B finding-patch provenance is complete.
- Whether S-05A prevents all prose-as-proof leakage.
- Whether S-05C retry containment, MC-5 decision durability, or unresolved
  deferral are mature.
- Whether S-05 seams or bottom-up windows compose.

### S-05B -> S-05C Verified-To-Chaining Seam Tier 2 Anchor

Campaign: `s05b_s05c_verified_to_chaining_seam_tier2_v1`

Suite: `s05b_s05c_verified_to_chaining_seam_breakpoint_suite`

Ownership type: `seam-owned`

Current tier: `Tier 2`

Target tier: `Tier 3`

Claim ceiling:

`S-05C chains only from S-05B-verified read evidence under medium seam pressure`.

Questions this suite can answer:

- Whether S-05B verified replay output can become S-05C MC-5 chaining input.
- Whether inferred, partial, failed, and state-drift replay rows stay non-chaining evidence.
- Whether the live handoff shape is patched findings rather than a hidden MC-5-only shortcut.

Questions this suite cannot answer:

- Whether S-05 bottom-up windows compose.
- Whether S-05C retry execution succeeds.
- Whether S-05C -> S-06 deferral is mature.
- Whether S-05B finding-patch honesty is broadly mature.

What the next suite in this category should add:

- S-05A -> S-05B enrichment-to-verification seam proof.
- S-05C -> S-06 chaining-to-gaps deferral proof.
- First S-05 bottom-up window only after adjacent seams are anchored.

### S-05 Full Family Tier 2 Baseline

Campaign: `s05_full_family_tier2_baseline_v1`

Suite: `s05_full_family_tier2_baseline_suite`

Ownership type: `mixed stage/seam/bottom-up`

Current tier: `mixed Tier 2 with blocked_at_tier2 and deferred rows`

Claim ceiling:

`Family-specific S-05 Tier 2 evidence only; blocked and deferred rows are not promoted`.

Tier 2 rows added by this suite:

| Scope | Breakpoint family |
| --- | --- |
| `S-05A schema_backfill` | `prose-as-proof prevention` |
| `S-05A schema_backfill` | `partial-backfill honesty` |
| `S-05A schema_backfill` | `schema compatibility preservation` |
| `S-05B verification_replay` | `finding-patch honesty` |
| `S-05B verification_replay` | `partial verification coverage` |
| `S-05C read_to_write_chaining` | `read-to-write dependency honesty` |
| `S-05C read_to_write_chaining` | `MC-5 decision durability` |
| `S-05C read_to_write_chaining` | `unresolved deferral` |
| `S-04 -> S-05A` | `synthesis-to-backfill provenance` |
| `S-05A -> S-05B` | `enrichment-to-verification boundary` |
| `S-05A -> S-05B -> S-05C` | `enriched schema becomes verification input and bounded MC-5 decision` |
| `S-04 -> S-05A -> S-05B` | `synthesis claim becomes backfill then replay verification` |

Blocked or deferred rows from this suite:

| Scope | Breakpoint family | Classification | Reason |
| --- | --- | --- | --- |
| `S-05B verification_replay` | `state-effect verification` | `blocked_at_tier2` | local DLL replay does not preserve same-session state effects strongly enough yet |
| `S-05B verification_replay` | `bridge/degradation classification` | `blocked_at_tier2` | deterministic infra-versus-product failure harness is absent |
| `S-05C read_to_write_chaining` | `retry containment` | `blocked_at_tier2` | MC-5 retry planning widens to distractor writes under medium harness pressure |
| `S-05C read_to_write_chaining` | `weak-ID/value overtrust` | `deferred_as_tier3_shaped` | meaningful pressure requires hard conflicting or ambiguous value signals |
| `S-05C -> S-06` | `chaining-to-gaps deferral` | `blocked_at_tier2` | S-06 lacks an explicit S-05C decision-consumer surface |
| `S-05B -> S-05C -> S-06` | `verification and chaining outcomes become gap decisions` | `blocked_at_tier2` | blocked by the missing S-05C -> S-06 consumer surface |

Questions this suite can answer:

- Whether the remaining S-05A schema-boundary rows stay separate from proof.
- Whether S-05B patch provenance and partial coverage boundaries remain
  reviewable under compiled replay pressure.
- Whether S-05C records MC-5 dependency, durability, and unresolved deferral
  decisions under medium harness pressure.
- Which S-05 rows are blocked before hard01 comparison.

Questions this suite cannot answer:

- Whether blocked rows are solved.
- Whether S-05 is Tier 3-ready.
- Whether broad hard-family behavior is non-regressed.

What the next suite in this category should add:

- A deterministic same-session S-05B state-effect harness, an explicit S-05C
  retry-scope containment fix, or an S-05C-to-S-06 consumer surface before
  claiming those rows.
