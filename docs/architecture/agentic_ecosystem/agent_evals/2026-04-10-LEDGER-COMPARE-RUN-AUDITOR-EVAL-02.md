# Ledger / Compare-Run Auditor Eval 02

- `evaluation_id`
  - `ledger-compare-run-auditor-eval-02`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `ledger_compare_run_auditor`
- `role_family`
  - `evidence`
- `prompt_version`
  - `manifest_aligned_contract_v1`
- `task_id`
  - `spectrum-medium02-compare-truth-slice-02`
- `task_type`
  - `artifact_audit`
- `task_input`
  - determine whether the `medium-02` progression claim is fully compare-backed
    or only directionally positive under AGENTS comparison-truth rules
- `repo_surfaces_used`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-02/20260410-110753/compiled-ingest-compare-report.json`
  - `sessions/ledger/run_ledger.jsonl`
  - `AGENTS.md`
- `output_produced`
  - a bounded compare-truth audit with explicit comparable-profile failure,
    ledger completeness gaps, attribution failure, `partially_supported`
    verdict, and a per-job-matrix refinement
- `what_it_got_right`
  - cleanly separated compare-truth from raw run trust
  - correctly downgraded the claim to `partially_supported`
  - clearly distinguished what the compare artifact proves from what the ledger
    proves
- `what_it_missed`
  - the role should emit a standardized per-job field matrix by default
- `what_it_overclaimed`
  - none materially; it refused to treat the cohort as fully supported
- `signal_to_noise_assessment`
  - very strong and decision-bearing
- `citation_quality_assessment`
  - strong, with direct citations into both AGENTS and the compare/ledger
    surfaces
- `boundedness_assessment`
  - stayed within comparison truth
- `usefulness_for_next_branch_choice`
  - very useful; it can now reliably bound compare-backed claims before
    promotion or readiness language is written
- `refinement_needed`
  - require an explicit per-job field matrix in every cohort audit
  - hard-cap verdicts at `partially_supported` whenever campaign fields are
    blank or comparable-profile values diverge
- `decision`
  - `refine`
