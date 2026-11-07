# SoundTouch Handoff

Workspace:
- `.`

Primary goal:
- Continue the external real-DLL `SoundTouchDLL_x64.dll` investigation.
- Try to move verified coverage from about `8/29` (`~27.6%`) toward `40%`.
- Use only generic pipeline improvements, not SoundTouch-specific hardcoding.

## Current status

Latest trusted external SoundTouch result before this handoff:
- prior job: `c9b15b08`
- verified surface effectively: `8/29`

Latest local lane status right now:
- API: `http://127.0.0.1:8201`
- bridge: `http://127.0.0.1:8090`
- current lab status: valid
- current active recent run:
  - job `ef19f959`
  - component `SoundTouchDLL_x64`
  - status `error`
  - explore phase `error`

Important artifact dirs:
- `local-data/artifacts/c9b15b08`
- `local-data/artifacts/f6a63d66`
- `local-data/artifacts/a2bc05f0`
- `local-data/artifacts/ef19f959`

Current SoundTouch upload source restored for reruns:
- `.\.tmp\soundtouch_rerun\SoundTouchDLL_x64.dll`

## What was changed

Bounded generic changes were made in:
- `api/services/executor.py`
- `scripts/bridge/gui_bridge.py`
- `api/pipeline/core/helpers.py`
- `api/pipeline/s02_probe/probe_loop.py`
- `tests/test_structured_argument_scaffolder.py`
- `tests/test_executor_dll_uint.py`

Temporary local bootstrap helpers were added under `.tmp`:
- `.tmp/start_local_api_8201.py`
- `.tmp/start_local_bridge_8090.py`

Those temp scripts are only for local process control during this lane.

## What the code changes were trying to do

Generic improvements implemented:
- treat pointer-like creator returns as candidate success, not only `Returned: 0`
- promote creator returns into opaque-handle artifacts
- route those artifacts into downstream consumers
- preserve float and double scalar coercion instead of truncating through `int(...)`
- allow no-arg creator/open/init write probes through policy
- retag likely first-param handle consumers from false output pointers to input handle slots
- retag version-string style `char* + size` params as output text buffers
- add bounded generic numeric candidate families for media-like setters

The key new helpers live in `api/pipeline/s02_probe/probe_loop.py`:
- `_retag_runtime_probe_roles`
- `_is_runtime_success_value`
- `_runtime_return_artifacts`
- `_merge_runtime_success_values`

The repeated hard-coded success checks in the probe loop were replaced with those helpers in the major success paths.

## What passed

After the code edits, these passed:
- `python scripts/verify_sync.py --tier A`
- `python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py`

Focused tests added/updated also passed:
- `tests/test_structured_argument_scaffolder.py`
- `tests/test_executor_dll_uint.py`

Do not assume runtime improvement from that alone. The runtime lane remained noisy because of process/auth issues.

## What we learned from SoundTouch

Confirmed recurring failure families:
- creator returns are pointer/handle-like and were being undercounted
- downstream consumers often want the first param to be a live opaque handle
- version string functions likely need output-buffer treatment
- float/double setters were likely being harmed by integer coercion before the fix

The verified functions that keep showing up:
- `soundtouch_getVersionId`
- `soundtouch_destroyInstance`
- `soundtouch_flush`
- `soundtouch_setSetting`
- `soundtouch_numSamples`
- `soundtouch_numUnprocessedSamples`
- `soundtouch_receiveSamples_i16`
- `soundtouch_receiveSamples`

The latest three artifact sets:
- `f6a63d66`
- `a2bc05f0`
- `ef19f959`
all still show the same effective verified set:
- `8` verified
- `22` failure

So as of this handoff, the code changes have not yet produced a measured runtime gain on SoundTouch.

## Critical blocker at handoff

The latest SoundTouch rerun failed for an environmental reason, not a clean semantic comparison:
- `ef19f959` ended in `error`
- probe log excerpts show repeated:
  - `Bridge /execute error: Client error '401 Unauthorized' for url 'http://127.0.0.1:8090/execute'`

That means:
- health checks succeeded
- but the API and bridge still were not actually sharing execution auth consistently for `/execute`

So the last rerun is not a trustworthy semantic regression/improvement signal.

This is the immediate blocker to clear before making more SoundTouch conclusions.

## Current local process state

At handoff time:
- `8090` is up and answers `/health`
- `8201` is up and reports valid lab status

But the last runtime evidence shows `/execute` auth still failed during the SoundTouch run.

That means the next agent should verify auth end-to-end, not just health.

## Recommended next steps

Do these in order:

1. Confirm the current local API and bridge pair is the intended fresh pair.
- check port owners for `8090` and `8201`
- inspect `.tmp/runtime-logs/bridge-8090.err.log`
- inspect `.tmp/runtime-logs/api-8201.err.log`

2. Verify bridge auth end-to-end, not only `/health`.
- confirm the API process has:
  - `GUI_BRIDGE_URL=http://127.0.0.1:8090`
  - `GUI_BRIDGE_SECRET` matching the bridge `BRIDGE_SECRET`
- run one bounded execute-path sanity call if needed before a full SoundTouch rerun

3. Only after auth is confirmed, rerun SoundTouch once more.
- upload source:
  - `.tmp/soundtouch_rerun/SoundTouchDLL_x64.dll`
- use the prior SoundTouch context:
  - `prior_job_id = c9b15b08`

4. Compare against:
- `c9b15b08`
- `f6a63d66`
- `a2bc05f0`
- `ef19f959` only as a failed/auth-broken run, not as a semantic baseline

5. If coverage still stays at `8/29` after a clean auth-valid rerun:
- stop the lane
- report that the generic changes did not move SoundTouch materially
- say the next blocker is likely deeper than easy generic handle/output fixes

## What not to do

- do not hardcode SoundTouch names/params into shared logic
- do not revert unrelated dirty files
- do not trust the stale `8202 -> 8810` app lane for this work
- do not assume `/health` implies `/execute` auth is good

## Repo constraints to follow

Required after code changes:
- `python scripts/verify_sync.py --tier A`
- `python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py`
- run Tier B only if canonical classification/status logic changed

Use:
- `apply_patch` for manual edits

One run at a time:
- one bridge+API pair only

## Dirty worktree warning

The repo has many unrelated dirty files outside this lane.
Do not clean the worktree globally.
Stay bounded to the SoundTouch-related files unless explicitly asked otherwise.

## Suggested prompt for the next agent

Use this repo and read this file first.

Goal:
- Resume the SoundTouch external DLL investigation from `HANDOFF-SOUNDTOUCH.md`.
- First clear the local API/bridge `/execute` auth issue.
- Then rerun SoundTouch on the clean `8201 -> 8090` lane with prior job `c9b15b08`.
- Report whether verified coverage moves beyond `8/29`, whether `40%` is reachable, and whether further bounded generic gains still look plausible.

---

## 2026-04-02 follow-up: stateful mutator verifier

Work completed after the original handoff:

- Implemented a bounded generic stateful mutator verification lane in:
  - `api/pipeline/s05_enrichment/verify.py`
- Added tests in:
  - `tests/test_verify_enrichment_stateful.py`
- Updated docs in:
  - `api/pipeline/s05_enrichment/FLOW.md`
  - `api/pipeline/s05_enrichment/README.md`
  - `docs/architecture/charts/01-engineering-overview-4/01-system-overview-dataflow.md`
  - `docs/architecture/charts/01-engineering-overview-4/02-stage-model.md`

What the new verifier does:

- preserves the old direct replay lane for existing success findings
- adds a second S-05 lane that:
  - reads `explore_probe_log.json`
  - finds near-success mutator candidates with real same-session probe args
  - rebuilds a fresh same-session lineage
  - replays candidate prerequisite chains
  - compares control vs treatment using downstream consumers and same-family observers
  - promotes only when a deterministic downstream effect is observed

Important design constraint:

- custom positive returns are **not** treated as success by themselves
- promotion is gated by observed effect only

Repo checks after the implementation:

- `python scripts/verify_sync.py --tier A` passed
- `python scripts/harness.py test -- tests/ -v --tb=short --ignore=tests/test_mcp_stdio.py` passed
- focused verifier tests passed:
  - `tests/test_verify_enrichment_bridge_guard.py`
  - `tests/test_verify_enrichment_stateful.py`

Local lane state at this later checkpoint:

- `/health` on `8201` passed
- `/health` on `8090` passed
- `/api/lab/status` reported valid
- `/api/execute` sanity call through the API succeeded on the bridge-backed lane

Latest SoundTouch live investigation results:

1. Job `9032359d`
- analyze-path target:
  - `C:\mcp-factory\runtime-dlls\g3\SoundTouchDLL_x64-540c24b39cc8-g6-e9b572a48b0e-g3.dll`
- this run is **not trustworthy for semantic comparison**
- every probe and verifier call hit:
  - `Could not find module ... (or one of its dependencies)`
- artifact to inspect:
  - `local-data/artifacts/9032359d/verification-report.json`
- the verifier code executed, but the DLL/runtime copy was bad, so no SoundTouch semantic conclusion should be drawn from this run

2. Runtime-path triage done after `9032359d`
- direct `/api/execute` sanity checks showed these paths load successfully:
  - `C:\mcp-factory\runtime-dlls\g0\SoundTouchDLL_x64-540c24b39cc8-g0.dll`
  - `C:\mcp-factory\runtime-dlls\g2\SoundTouchDLL_x64-540c24b39cc8-g2.dll`
  - `C:\mcp-factory\runtime-dlls\g2\SoundTouchDLL_x64-540c24b39cc8-g6-e9b572a48b0e-g2.dll`
- this path fails to load and should be avoided:
  - `C:\mcp-factory\runtime-dlls\g3\SoundTouchDLL_x64-540c24b39cc8-g6-e9b572a48b0e-g3.dll`

3. Job `cde9e0f3`
- second targeted rerun started against:
  - `C:\mcp-factory\runtime-dlls\g2\SoundTouchDLL_x64-540c24b39cc8-g6-e9b572a48b0e-g2.dll`
- it was interrupted by a user stop before result review
- current status when switching tasks:
  - cancellation requested
- do not assume success or failure until its artifacts/status are inspected

Current stop point before switching to desktop-demo work:

- the stateful verifier implementation is in the repo and tested
- the first proving run was contaminated by a bad runtime DLL copy
- the second proving run on a known-good `g2` path was started but interrupted before review
- both interrupted jobs were sent `/explore-cancel`:
  - `9032359d`
  - `cde9e0f3`

Recommended resume point later:

1. Confirm `9032359d` and `cde9e0f3` are fully stopped.
2. Re-check `http://127.0.0.1:8201/api/jobs/recent`.
3. Resume only on a known-good runtime path:
   - prefer `g2`, not `g3`.
4. Inspect whether `cde9e0f3` produced:
   - `verification-report.json`
   - `findings.json`
   - `explore_probe_log.json`
5. If `cde9e0f3` is incomplete, run one fresh focused SoundTouch rerun on the known-good `g2` copy and evaluate:
   - whether `soundtouch_setSampleRate` was promoted via observed effect
   - whether `soundtouch_setTempo` produced observer evidence or a clean “unverifiable” result
   - whether `soundtouch_putSamples_i16` stayed non-regressed
