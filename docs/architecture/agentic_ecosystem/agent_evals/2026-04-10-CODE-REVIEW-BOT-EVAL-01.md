# Code Review Bot Eval 01

- `evaluation_id`
  - `code-review-bot-eval-01`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `code_review_bot`
- `role_family`
  - `review`
- `prompt_version`
  - `initial_prompt_contract_v1`
- `task_id`
  - `commit-3bd368b-vs-72a6846`
- `task_type`
  - `real_diff`
- `task_input`
  - review the overnight checkpoint commit for correctness, regressions,
    missing tests, and boundary/trust issues
- `repo_surfaces_used`
  - `git diff 72a6846..3bd368b`
  - `api/routes/main.py`
  - `api/infra/worker.py`
  - `api/services/discovery.py`
  - `scripts/harness_lib/validation_report.py`
  - `api/pipeline/s02_probe/probe_loop.py`
  - `api/pipeline/core/prompts.py`
- `output_produced`
  - four findings with file references and one refinement section
- `what_it_got_right`
  - surfaced a real missing-direct-tests risk for execution-path changes
  - found two plausible code-level correctness/regression risks in replay and
    wrapper handling
  - kept the output focused on risk rather than style
- `what_it_missed`
  - did not include repro scenario or failure-mode impact consistently per
    finding
  - did not explicitly separate runtime findings from governance/policy
    findings
- `what_it_overclaimed`
  - the `_INIT_RE` coupling finding is weaker than the others because the file
    already depended on underscore-prefixed helper internals and the output did
    not prove that the commit newly introduced the coupling
- `signal_to_noise_assessment`
  - high-signal overall, with one lower-confidence policy-oriented finding
- `citation_quality_assessment`
  - good file-level citation quality; no line ranges beyond the direct finding
    anchor were needed
- `boundedness_assessment`
  - stayed within review scope and did not drift into implementation
- `usefulness_for_next_branch_choice`
  - useful; it shows the role can surface real review risk, but it still needs
    better finding structure to be reusable
- `refinement_needed`
  - require each finding to include one of:
    - repro scenario
    - failure mode
    - false-positive or false-negative impact
  - classify findings as:
    - runtime correctness
    - regression risk
    - governance/contract coupling
  - require an explicit test-gap check when execution-path code changes
  - if fewer than two strong findings exist, require a residual-risk statement
    rather than padded weak findings
- `decision`
  - `refine`
