# Verification Gate Bot Eval 01

- `evaluation_id`
  - `verification-gate-bot-eval-01`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `verification_gate_bot`
- `role_family`
  - `gate`
- `prompt_version`
  - `initial_prompt_contract_v1`
- `task_id`
  - `commit-3bd368b-vs-72a6846`
- `task_type`
  - `real_diff`
- `task_input`
  - determine required verification for the overnight checkpoint and whether
    the repo evidence supports a pass
- `repo_surfaces_used`
  - `git diff 72a6846..3bd368b`
  - `AGENTS.md`
  - recorded prior verification outputs for the same checkpoint
  - run and compare artifacts under `sessions/design_suite/compiled_ingest/...`
- `output_produced`
  - required verification set, satisfaction assessment, weaknesses in the role,
    and prompt refinements
- `what_it_got_right`
  - correctly derived required checks from touched systems and AGENTS doctrine
  - correctly marked Tier B as not required
  - correctly identified weak evidence around lane recycle/health proof
- `what_it_missed`
  - did not separate required checks from recommended checks in the output
  - did not force each check to cite a concrete evidence artifact path
- `what_it_overclaimed`
  - `pass with medium confidence` is directionally right but still too generous
    without explicit post-change recycle/health evidence attached to the
    checkpoint
- `signal_to_noise_assessment`
  - strong signal, but too checklist-oriented
- `citation_quality_assessment`
  - good doctrine citation quality, weaker artifact citation discipline than
    desired for a reusable gate role
- `boundedness_assessment`
  - stayed within verification scope
- `usefulness_for_next_branch_choice`
  - very useful; clearly shows this role can guard confidence claims if its
    schema is tightened
- `refinement_needed`
  - require this output structure:
    - `required_checks`
    - `recommended_checks`
    - `evidence_found`
    - `missing_evidence`
    - `verdict`
    - `confidence`
  - map touched surfaces to required checks before issuing a verdict
  - require explicit evidence citation for every required check
  - forbid `pass` on lane-sensitive changes without explicit recycle + health
    evidence
- `decision`
  - `refine`
