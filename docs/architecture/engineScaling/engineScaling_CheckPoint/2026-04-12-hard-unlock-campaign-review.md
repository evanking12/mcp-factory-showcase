# Hard Unlock Campaign Review

Date: 2026-04-12

Review update:

- the initial post-campaign review found one critical and several high-severity
  risks
- a bounded local repair tranche has since addressed the merge-blocking set
- focused validation passed after those repairs:
  - `tests/test_gui_bridge_upload_paths.py`
  - `tests/test_nightly_preflight.py`
  - `tests/test_native_diagnostic_hooks.py`
  - `tests/test_mc_evidence_consumption.py`
  - `tests/test_validation_report.py`
  - `python scripts/verify_sync.py --tier A`

## Summary

The hard-unlock dynamic campaign produced a real proving jump:

- `medium-01` closed green
- `medium-02` closed green
- `hard-01` closed green
- `hard-02` closed green

This is a meaningful product and proving milestone, not a cosmetic cleanup
result.

The repo also now contains:

- a complete dynamic prompt chain for the campaign under
  `cleanup/hard_unlock_dynamic_campaign_prompts/`
- a long-form execution ledger in `cleanup/CAMPAIGN-LOG.md`
- tightened architectural weakness writeback in
  `.agents/ARCHITECTURAL-WEAKNESSES.md`
- new hard-suite runners under `scripts/runs/`
- wider compiled-ingest test coverage

## What Actually Improved

### Product / Proving

The campaign advanced the repo from "hard blocked" to "hard green on this
branch."

That happened through a sequence of narrower repairs, not one vague engine
"upgrade."

Important families repaired during the campaign included:

- operator and artifact-read truthfulness
- startup and bridge readiness
- medium-01 semantic entry and trusted-predecessor handoff
- medium-01 green output buffer and MC-3 closeout truth
- medium-01 validator observer truth alignment
- medium-02 checkpoint progression and package-scale reproof
- hard-01 release-commit validity
- hard-01 predecessor admission and package closeout truth
- hard-01 MC-6 unlock persistence ordering
- hard-01 validation observer false mismatches
- hard-02 stale invalidation materialization
- hard-02 support-target omission2

### Workflow

The campaign also proved that dynamic prompt generation can carry a long branch
to a meaningful technical outcome.

The following workflow elements are now real rather than theoretical:

- governed dynamic campaign prompts
- tranche-based progression
- blocker reranking
- weakness writeback during execution
- explicit prompt-chain closeout

## What Still Looks Weak

The product frontier improved faster than the workflow frontier.

The main workflow weaknesses exposed by this run are:

1. commit granularity was too coarse at the end
2. campaign narrative quality exceeded campaign reviewability
3. ecosystem evaluation writeback lagged behind actual role usage
4. repeated local repairs did not always become explicit system proposals
5. CI and regression automation are still weaker than the proving milestone
   now justifies
6. some secondary review questions still remain open even after the bounded
   repair tranche:
   - whether route-level `status` should degrade alongside `native_status`
   - whether hard-case compiled-ingest binary proof should trust-gate more
     aggressively
   - whether hard-02 negative-path coverage should match hard-01 parity

The headline example is commit `d00cacd`.

It is meaningful and likely correct in direction, but it is too large for ideal
human or agent review:

- 100+ changed files
- 30 prompt artifacts
- large code movement across pipeline, bridge, route, and test surfaces

That is a useful campaign closeout artifact, but not a good default operating
shape for the future.

## How Big The Jump Was

This was a large proving jump and a moderate workflow jump.

### Large proving jump

Because:

- both medium proving families closed green
- both hard families closed green
- the branch moved from "unlock needed" to "unlock achieved"

### Moderate workflow jump

Because:

- the dynamic campaign structure worked
- but the repo still needs better discipline for:
  - smaller commits
  - higher-signal review packets
  - explicit system extraction
  - agent-eval writeback
  - CI gating

## Review Surface Ranking

If the goal is to review what matters without drowning, start here.

### Highest-signal files

- `cleanup/hard_unlock_dynamic_campaign_prompts/ACTIVE-PROMPT.md`
- `cleanup/CAMPAIGN-LOG.md`
- `api/pipeline/core/spectrum_compiled_ingest.py`
- `api/routes/main.py`
- `api/pipeline/s02_probe/probe_loop.py`
- `api/pipeline/s03_reconcile/mc3_write_analysis.py`
- `api/pipeline/s05_enrichment/verify.py`
- `api/pipeline/s06_gaps/mc6_final_unlock.py`
- `scripts/harness_lib/validation_report.py`
- `scripts/runs/run_spectrum_compiled_hard01.py`
- `scripts/runs/run_spectrum_compiled_hard02.py`
- `tests/test_spectrum_compiled_ingest.py`
- `tests/test_nightly_preflight.py`
- `tests/test_validation_report.py`

### Lower-signal but still useful artifacts

- intermediate prompt notes under
  `cleanup/hard_unlock_dynamic_campaign_prompts/`
- roadblock JSON files under `bugs/`
- fixture overlay truth manifests under
  `tests/fixtures/spectrum_transaction_release_settlement_suite/*_contract_overlay/`

## Reporting And Prompt Output

The per-prompt reporting was useful, but it needs compression.

The useful stable fields are:

- blocker family
- ownership surface
- chosen bounded slice
- validation result
- resulting state change
- next prompt
- commit SHA
- whether the result changed blocker ranking

The current campaign produced too much narrative for first-pass review.

Better future rule:

- keep the rich prompt artifacts for auditability
- also emit a thinner machine-and-human summary row per tranche

## Commit Discipline

We should not mechanically commit after every prompt.

We should commit after every meaningful code-bearing tranche or blocker-ranking
change.

Better rule:

- one bounded code-bearing tranche = one commit
- docs/log-only tranches may be batched if they do not change truth
- do not allow campaign closeout to accumulate dozens of meaningful repairs
  into one giant final commit unless there is no better recovery path

## Agent Ecosystem Writeback

The campaign used agentic workflow ideas, but the ecosystem itself was not
updated enough after the run.

That is now a workflow gap.

Better rule:

- when role usefulness, trust ceiling, or failure mode materially changes,
  update the relevant ecosystem artifacts
- do not require ceremonial updates after every prompt
- do require at least campaign-closeout evaluation after a run of this size

## Containers, CI, GitHub Actions, And Push Cadence

### Push cadence

Do not use a blind "push every five commits" rule.

Better rule:

- push every clean, reviewable tranche commit
- treat the remote as a checkpoint trail, not a dump sink

### GitHub Actions

The next honest step is focused CI, not broad CI theater.

Recommended first CI gate:

- `tests/test_spectrum_compiled_ingest.py`
- `tests/test_nightly_preflight.py`
- `tests/test_validation_report.py`
- `python scripts/verify_sync.py --tier A`

Do not start with full expensive end-to-end package reruns as a PR gate.

Use heavier proving as:

- a nightly gate
- a manual gate
- or a promotion gate

### Containers

Containers should come after the CI contract is sharper.

Recommended order:

1. high-signal GitHub Actions checks
2. clearer regression contract
3. then containerization and environment normalization

## Copilot Review

GitHub Copilot review is worth using as a secondary reviewer.

Recommended policy:

- use the repo's `code_review_bot` logic as the contract-first primary review
- use Copilot review as a second independent pass
- do not treat Copilot as authoritative

Best use cases:

- maintainability smells
- missed edge cases
- alternative simplifications
- broad diff triage on pushed tranches

## Systems We Still Need

The campaign identified some system-shaped needs, but not enough were elevated
into explicit implementation proposals.

The next system candidates are:

1. campaign tranche summarization system
   - one stable summary record per tranche
   - compact enough for later review
2. proving promotion / confidence system
   - decide when a green proving family is "good enough" to treat as trusted
3. human-readable codebase mapping system
   - ownership and navigation help for humans
4. agent-readable codebase mapping system
   - machine-routable ownership and boundary map for specialist agents
5. focused regression CI system
   - fast checks on every pushed tranche

## Human And Agent Mapping

If a new enterprise system landed in the repo today, both humans and agents
would benefit from stronger mapping surfaces.

We should build both:

### Human-readable mapping

- architecture / ownership map
- dangerous surfaces
- public vs internal boundaries
- where new code should live
- proving and verification routes

### Agent-readable mapping

- machine-readable ownership surface registry
- specialist-role routing hints
- forbidden edit zones
- canonical commands
- proving surface inventory
- contract owner mapping

This should become a real system, not just scattered prose.

## What The Operator Should Do Now

The next steps are clear enough to act, but the branch should not be merged
blindly.

Recommended operator sequence:

1. do a structured post-campaign review on this branch
2. fix the merge-blocking and high-severity findings from that review
3. rerun the focused validation surface
4. then decide whether the branch is trusted enough to merge into `main`
5. if yes, merge it
6. then review the old friend PR against the new baseline instead of letting
   it keep aging against stale repo reality

## Post-Campaign Code Review Findings

The high-signal post-campaign review found several real risks.

### 1. Critical: isolated DLL execution breaks the documented in-memory state contract

The bridge now executes every `dll_import` in a fresh worker process:

- `scripts/bridge/gui_bridge.py:2412`
- `scripts/bridge/gui_bridge.py:2540`

But the same file still documents that DLL state must persist across `/execute`
calls:

- `scripts/bridge/gui_bridge.py:1644`

That is a behavioral regression risk for any flow that depends on in-memory
handles, cached state, or mutable DLL session state across calls.

Current test coverage only proves single-call worker behavior:

- `tests/test_gui_bridge_upload_paths.py:196`
- `tests/test_gui_bridge_upload_paths.py:244`

There is no regression test for multi-call state continuity.

### 2. High: `run_one` can false-green after a save-session timeout

The nightly runner now tolerates `save-session` timeout if a small set of files
already exists:

- `scripts/ops/nightly_groundtruth.py:103`
- `scripts/ops/nightly_groundtruth.py:469`

But the session directory is reused and the timeout path only checks file
existence, not freshness or provenance:

- `scripts/ops/nightly_groundtruth.py:441`
- `scripts/ops/nightly_groundtruth.py:473`

The final record can still be marked `"ok"` even when the save step timed out:

- `scripts/ops/nightly_groundtruth.py:498`

That creates a false-green risk when stale prior artifacts are present.

Current test coverage only proves the tolerated happy path:

- `tests/test_nightly_preflight.py:107`

It does not guard against stale or mismatched artifact reuse.

### 3. High: artifact-read degradation misclassifies normal blob misses on Azure-style backends

The new route helpers treat only `FileNotFoundError` as a normal miss:

- `api/routes/main.py:395`
- `api/routes/main.py:447`

But the real blob reader simply calls the Azure client directly:

- `api/infra/storage.py:96`

On non-local storage, a missing blob is typically not raised as
`FileNotFoundError`, so ordinary absence can be recorded as a degraded
`read_error` instead of a normal `partial` miss.

That would pollute operator truth again on cloud-backed runs even though local
tests pass.

### 4. High: MC-3 now promotes output values parsed from truncated probe excerpts

`mc3_write_analysis.py` now reconstructs preserved success args by parsing
`entry["result_excerpt"]`:

- `api/pipeline/s03_reconcile/mc3_write_analysis.py:72`
- `api/pipeline/s03_reconcile/mc3_write_analysis.py:125`

But probe logs still store `result_excerpt` as only the first 200 characters of
the tool result:

- `api/pipeline/s02_probe/probe_loop.py:3384`

That means partial or truncated output lines can now be merged into patched
`working_call` success findings, which is not trustworthy enough for preserved
write truth.

### 5. Medium: validation placeholder detection can hide legitimate void-return wrappers

Validation now treats any single-statement wrapper method returning `None` as a
placeholder:

- `scripts/harness_lib/validation_report.py:174`
- `scripts/harness_lib/validation_report.py:209`
- `scripts/harness_lib/validation_report.py:268`
- `scripts/harness_lib/validation_report.py:437`

That is correct for empty stubs, but it also downgrades legitimate side-effect
wrappers that intentionally return no value into `wrapper_unavailable`.

The new tests cover `pass`-style placeholders, but not real no-return wrappers.

## Repair Tranche Update

The merge-blocking findings above were addressed locally in one bounded repair
tranche.

Repairs made:

1. restored direct DLL execution for `dll_import` route calls so cross-call
   in-memory DLL state remains intact
2. hardened nightly `save-session` timeout tolerance by:
   - clearing the target session capture directory before save
   - requiring fresh required artifacts, not merely preexisting files
3. treated Azure-style not-found blob exceptions as normal artifact absence
   rather than degraded read failure
4. stopped MC-3 from merging preserved success output values out of truncated
   probe excerpts
5. stopped validation from treating all single-statement `return None` wrapper
   methods as placeholders

Focused validation after repair:

- `python scripts/harness.py test -- tests/test_gui_bridge_upload_paths.py tests/test_nightly_preflight.py tests/test_native_diagnostic_hooks.py tests/test_mc_evidence_consumption.py tests/test_validation_report.py -v --tb=short --ignore=tests/test_mcp_stdio.py`
- `python scripts/verify_sync.py --tier A`

Both passed.

## Merge Recommendation

Merging into `main` is not the best immediate move from this exact state.

Why:

- this branch appears to have closed the current explicit proving frontier
- the proving and workflow baseline has moved materially
- but the post-campaign review found one critical and multiple high-severity
  risks that are strong enough to justify one bounded repair tranche before
  merge

Merge should happen after those findings are repaired or explicitly disproved.

With the bounded repair tranche now applied locally, the branch is materially
closer to merge-ready, but it still deserves one brief re-review on the touched
repair surfaces before the final merge call.

What should happen before or during merge review:

- review the high-signal surfaces listed above
- run or confirm the focused verification surface
- repair or disprove the merge-blocking findings above
- then decide whether the large closeout commit needs any follow-up
  decomposition in documentation rather than in git history

## Friend PR Recommendation

After the merge decision, the old friend PR can still be useful.

Best use:

- review it as a delta against the newly proven baseline
- look for:
  - now-obsolete work
  - conflicting assumptions
  - still-useful pieces
  - ideas that should be re-landed differently

Do not assume the old PR should merge unchanged just because it was once
reasonable.

## Immediate Practical Next Step

If acting now, the best immediate step is:

- inspect the bounded repair tranche diff
- if it looks coherent, merge to `main`
- then review the friend's PR against the new baseline

After that:

- stand up focused GitHub Actions checks
- add the mapping-system work
- then use the updated baseline to review the friend's PR
