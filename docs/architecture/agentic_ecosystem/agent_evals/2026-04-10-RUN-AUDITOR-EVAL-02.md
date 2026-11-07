# Run Auditor Eval 02

- `evaluation_id`
  - `run-auditor-eval-02`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `run_auditor`
- `role_family`
  - `evidence`
- `prompt_version`
  - `manifest_aligned_contract_v1`
- `task_id`
  - `spectrum-medium02-run-trust-slice-02`
- `task_type`
  - `artifact_audit`
- `task_input`
  - determine whether the existing `medium-02` compare packet is trustworthy
    enough to support its current claim ceiling after compare-to-ledger
    reconciliation
- `repo_surfaces_used`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-02/20260410-110753/compiled-ingest-compare-report.json`
  - `sessions/ledger/run_ledger.jsonl`
  - `AGENTS.md`
- `output_produced`
  - scope, lane identity, compare-to-ledger reconciliation, `not_trustworthy`
    verdict, explicit claim ceiling, blocking gaps, bounded next actions, and a
    fail-closed prompt refinement
- `what_it_got_right`
  - correctly refused to treat the compare packet as trustworthy in the face of
    mixed comparable profiles and blank trust fields
  - emitted a strong claim ceiling instead of a vague caution
  - stayed bounded to raw run trust rather than compare-truth or roadblock work
- `what_it_missed`
  - it could be even stronger if the output always emits a compact per-job
    identity matrix
- `what_it_overclaimed`
  - none materially; the role failed closed
- `signal_to_noise_assessment`
  - very strong and concise
- `citation_quality_assessment`
  - strong artifact grounding
- `boundedness_assessment`
  - stayed within run trust
- `usefulness_for_next_branch_choice`
  - very useful; this is now a real gate for whether run-backed claims can be
    made safely
- `refinement_needed`
  - add a compact per-job identity matrix when the audited cohort is larger than
    one run
- `decision`
  - `refine`
