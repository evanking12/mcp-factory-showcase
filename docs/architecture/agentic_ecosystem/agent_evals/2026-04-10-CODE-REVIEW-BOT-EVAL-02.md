# Code Review Bot Eval 02

- `evaluation_id`
  - `code-review-bot-eval-02`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `code_review_bot`
- `role_family`
  - `review`
- `prompt_version`
  - `manifest_aligned_contract_v1`
- `task_id`
  - `commit-3bd368b-vs-ff0fdae`
- `task_type`
  - `real_diff`
- `task_input`
  - review the governance and handoff tranche for correctness, contract drift,
    and commit-handoff integrity using the raw commit bodies for `57ece98` and
    `ff0fdae`
- `repo_surfaces_used`
  - `git diff 3bd368b..ff0fdae`
  - `git log --format=fuller 57ece98 ff0fdae`
  - `AGENTS.md`
  - `docs/architecture/COMMIT-HANDOFF-TEMPLATE.md`
  - `docs/architecture/agentic_ecosystem/AGENT-REGISTRY.json`
  - `docs/architecture/agentic_ecosystem/AGENTIC-ECOSYSTEM-IMPLEMENTATION-PACK.md`
- `output_produced`
  - two governance/contract findings, a handoff-contract assessment, residual
    risks, and a prompt refinement focused on reviewed-tree comparison and raw
    commit-body inspection
- `what_it_got_right`
  - caught a real machine-parseability defect in commit `57ece98`
  - stayed bounded to governance/contract review instead of inventing code
    findings
  - correctly treated commit handoff structure as part of the review surface
- `what_it_missed`
  - the registry-readiness finding is partly time-sensitive and needs clearer
    separation between the reviewed commit tree and the current workspace state
- `what_it_overclaimed`
  - the deployment-readiness finding bundled future-skill rollout ambiguity
    with the reviewed commit range more broadly than necessary
- `signal_to_noise_assessment`
  - strong signal; the role stayed sharp and did not pad with weak findings
- `citation_quality_assessment`
  - strong; the role cited the governing docs and the exact commit-body defect
- `boundedness_assessment`
  - stayed within review scope
- `usefulness_for_next_branch_choice`
  - very useful; it proved the role can guard both governance drift and commit
    handoff integrity in one bounded review pass
- `refinement_needed`
  - require explicit comparison against the reviewed commit tree when registry
    deployment claims are part of the review
  - require raw `%B` commit-body inspection whenever handoff validity is in
    scope
- `decision`
  - `refine`
