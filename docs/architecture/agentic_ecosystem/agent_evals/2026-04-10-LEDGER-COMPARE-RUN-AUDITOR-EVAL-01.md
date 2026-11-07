# Ledger / Compare-Run Auditor Eval 01

- `evaluation_id`
  - `ledger-compare-run-auditor-eval-01`
- `evaluated_at`
  - `2026-04-10`
- `role_name`
  - `ledger_compare_run_auditor`
- `role_family`
  - `evidence`
- `prompt_version`
  - `initial_prompt_contract_v1`
- `task_id`
  - `spectrum-compiled-ingest-compare-truth-slice-01`
- `task_type`
  - `artifact_audit`
- `task_input`
  - determine whether compare-backed progression claims across `easy-01`,
    `medium-01`, and `medium-02` are fully supported by ledger-backed identity
    and attribution surfaces
- `repo_surfaces_used`
  - `docs/architecture/agentic_ecosystem/prompts/02-run-evidence-core-calibration.md`
  - `sessions/ledger/run_ledger.jsonl`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/easy-01/20260409-224304/compiled-ingest-compare-report.json`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-01/20260410-084431/compiled-ingest-compare-report.json`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-02/20260410-110753/compiled-ingest-compare-report.json`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/easy-01/20260409-224304/runs/03-release_commit/session/cohesion-report.json`
  - `sessions/design_suite/compiled_ingest/spectrum_transaction_release_settlement_suite/medium-02/20260410-110753/runs/08-settlement_reconcile/session/cohesion-report.json`
  - `AGENTS.md`
- `output_produced`
  - identified the candidate role as a comparison-truth gate and produced a
    supported/partially-supported/unsupported verdict shape tied to comparable
    profile, ledger completeness, and attribution agreement
- `what_it_got_right`
  - correctly separated compare-truth from raw run trust
  - correctly emphasized that semantic alignment alone does not prove promotion
    or readiness
  - correctly identified `campaign_id` gaps and mixed validity as reasons to
    downgrade claim strength
- `what_it_missed`
  - initial framing needed a stricter refusal rule for unresolved cohort
    mismatches
  - needed a more explicit boundary against owning blocker classification
- `what_it_overclaimed`
  - an unrefined version of this role would be too willing to call a compare
    claim supported when the compare artifact is green but the ledger-backed
    cohort is still mixed
- `signal_to_noise_assessment`
  - high signal with a real recurring use case
- `citation_quality_assessment`
  - good artifact grounding, especially around compare + cohesion contrast
- `boundedness_assessment`
  - stayed within comparison truth and did not absorb adjacent roles
- `usefulness_for_next_branch_choice`
  - very useful; this role determines whether compare-backed statements can be
    promoted, deferred, or qualified
- `refinement_needed`
  - make the role a strict comparison-truth gate
  - require explicit refusal of `supported` when identity or attribution is
    unresolved
  - require separate statements for what compare proves vs what ledger proves
- `decision`
  - `refine`
