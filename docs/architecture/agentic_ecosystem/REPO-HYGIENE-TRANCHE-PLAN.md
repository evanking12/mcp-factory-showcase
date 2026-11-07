# Repo Hygiene Tranche Plan

## Goal

Reduce the repo friction that wastes iteration time for the main thread and
specialist roles without turning cleanup into a broad rewrite.

This tranche exists to make future engine, coverage, and ecosystem work
cheaper by improving legibility, ownership clarity, and search quality.

## Scope

This is a bounded cleanup tranche focused on:

- duplicated concept homes
- active truth mixed with prompt/history clutter
- ambiguous folder ownership
- dead, misleading, or badly placed artifacts
- search noise that slows the main thread and specialist roles

This tranche is not for:

- major runtime reorganization
- cross-system code motion without a clear owner
- large archival passes without a reviewed keep/clarify/archive decision
- deleting historical material just because it is old

## Success Criteria

This tranche is successful only if it produces at least one of:

- fewer competing homes for one concept
- clearer distinction between active and historical prompt material
- clearer ownership for ambiguous folders
- reduced search noise for common analysis paths
- a smaller, safer next cleanup order for follow-on work

## GM And Specialist Role Structure

### Parent thread

The main Codex thread remains the GM of active truth and owns:

- wider goal
- tranche stop gate
- branch choice
- final keep / clarify / archive / move / delete-candidate decisions
- synthesis of specialist-role outputs
- any actual file edits that follow

### Specialist roles to use by default in this tranche

Use these roles when their boundaries apply:

1. `repo-hygiene-auditor`
- classify ambiguous folders and duplicated concept homes
- propose the smallest cleanup order first

2. `run-artifact-curator`
- inspect session and artifact surfaces for transient-output clutter
- separate durable review surfaces from noisy run residue

3. `code_review_bot`
- review proposed cleanup edits for risk, accidental coupling, or hidden
  boundary violations
- validate commit-handoff structure if cleanup is committed

4. `verification_gate_bot`
- decide which checks are required versus optional for the cleanup tranche
- prevent over-testing and under-testing

### Optional specialist roles

Use only if the trigger appears during the tranche:

- `roadblock_classifier`
  - if cleanup stalls because a folder or artifact problem is actually a
    deeper architecture blocker
- `dashboard_contract_checker`
  - if cleanup touches operator-facing artifact locations or documentation

## Tranche Sequence

### Phase 1: repo legibility audit

Run `repo-hygiene-auditor` on the high-noise surfaces first.

Audit targets:

- `codex/tasks/`
- `docs/architecture/`
- `docs/architecture/agentic_ecosystem/`
- `docs/architecture/engineScaling/`
- `sessions/`
- `artifacts/`
- repo root source-adjacent clutter if present

Required output:

- high-signal folder classification
- top ambiguity seams
- concepts needing one canonical home
- lowest-risk cleanup order

### Phase 2: transient-artifact audit

Run `run-artifact-curator` on the run-heavy surfaces.

Audit targets:

- `sessions/`
- `artifacts/`
- any root or near-root transient outputs

Required output:

- durable versus transient artifact split
- mislocated run outputs
- archive or relocation candidates
- no-delete-until-reviewed list

### Phase 3: GM synthesis and tranche selection

The parent thread should combine both audits and pick one low-risk cleanup
slice only.

Allowed cleanup slice types:

- clarify one concept home
- move a small set of misplaced transient artifacts
- add or improve one ownership or README clarifier
- separate active versus historical prompt material in one bounded area

Do not select more than one primary cleanup slice in the first execution pass.

### Phase 4: bounded cleanup edits

Perform only the chosen low-risk slice.

Edit constraints:

- prefer clarification before motion
- prefer motion before deletion
- archive before delete when history may still matter
- avoid touching runtime behavior in a repo-hygiene tranche

### Phase 5: safety review and validation

Before closeout:

- run `code_review_bot` on the cleanup diff
- run `verification_gate_bot` to confirm required checks
- run only the required checks

Expected required checks for a docs / organization-only tranche:

- `python scripts/verify_sync.py --tier A`

Add broader checks only if touched surfaces justify them.

## Decision Rules

### Keep

Choose `keep` when:

- the folder or artifact has a clear owner
- it is active truth
- it is in the correct place

### Clarify

Choose `clarify` when:

- the content is still useful
- the main problem is missing explanation or ownership labeling

### Archive

Choose `archive` when:

- the material is historical
- still potentially useful for provenance
- but should not compete with active truth

### Move

Choose `move` when:

- the material is active
- but clearly lives in the wrong place
- and the move does not create broad dependency risk

### Delete candidate

Choose `delete candidate` only when:

- the artifact is clearly transient or obsolete
- no current workflow depends on it
- archival value is low
- and the parent thread explicitly confirms the deletion path

## Stop Gate

Stop this tranche when all are true:

- one bounded cleanup slice is completed
- the resulting ownership or noise improvement is explicit
- required checks pass
- the next cleanup slice is clearer than it was before

Do not broaden the tranche into a repo-wide reorganization in one pass.

## What This Tranche Should Improve For Future Work

If successful, the next engine or coverage iteration should gain:

- faster file targeting
- less stale-doc confusion
- cleaner specialist-role dispatch
- fewer false starts caused by mixed active/historical surfaces
- lower context cost for the parent thread

## Expected Outputs

This tranche should produce:

- one audit-backed cleanup decision
- one bounded cleanup diff
- one short closeout stating:
  - what was clarified
  - what remains noisy
  - what the next cleanup slice should be
