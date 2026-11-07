# Principle Family Audit: `proving_economics`

- strongest_principle: `PE-01 cheapest trusted loop first`
- weakest_principle: `PE-03 rerun gate law`
- recurring_failure_pattern: `the doctrine is strong, but expensive rerun legality and single-job rerun discipline are not durably written as first-class decision artifacts`
- count_of_escalations: `2`

## `PE-01`: `cheapest trusted loop first`

- principle_id: `PE-01`
- principle_name: `cheapest trusted loop first`
- score_1_to_10: `8`
- why: `The doctrine is explicit and real campaign behavior often follows it. The repo-state baseline and hard-family campaigns frequently chose diagnostic-only prompts and bounded fixes before reopening proving.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/01-classify-hard01-late-branch-truth-next-move-summary.md`
- evidence_missing:
  - `Compact tranche summaries do not consistently record cheapest_trusted_validation_surface in the exact schema language.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/01-classify-hard01-late-branch-truth-next-move-summary.md`
- main_failure_mode: `The repo often behaves according to this principle, but the cheapest trusted loop is still sometimes inferred from campaign prose rather than enforced as a compact per-tranche control field.`
- recommended_tightening: `Require every code-bearing or rerun-bearing tranche summary to include explicit cheapest_trusted_validation_surface and why_harder_loop_still_deferred_or_now_justified lines.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `PE-02`: `strict lane-trust gate`

- principle_id: `PE-02`
- principle_name: `strict lane-trust gate`
- score_1_to_10: `7`
- why: `The lane-trust gate is now clearly recognized as real workflow law. Hard-family V2 rejected stale and stalled rerun packets before accepting a fresh authoritative rerun.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/14-diagnose-fresh-lane-hard01-rerun-validity-and-run-control-reliability-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- evidence_missing:
  - `No single durable lane-trust packet is consistently attached to each proving action.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/14-diagnose-fresh-lane-hard01-rerun-validity-and-run-control-reliability-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- main_failure_mode: `Lane trust is enforced reactively after suspicious proving packets, but the lane-trust decision surface is still more distributed than it should be.`
- recommended_tightening: `Add one required lane_trust_verdict block before every authoritative rerun with fields for freshness, readiness, route-around status, and whether the packet is legally decision-bearing.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `PE-03`: `rerun gate law`

- principle_id: `PE-03`
- principle_name: `rerun gate law`
- score_1_to_10: `6`
- why: `The five-gate rerun law is doctrinally strong, but operational evidence is weaker than it should be. Exact evidence/control/decision/trust/scope gates are rarely written as a first-class decision block in actual campaign artifacts.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- evidence_missing:
  - `Hard-family tranche summaries do not consistently record the five rerun gates explicitly.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/outputs/tranche_summaries/04-hard01-baseline-rerun-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/01-classify-hard01-late-branch-truth-next-move-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/14-diagnose-fresh-lane-hard01-rerun-validity-and-run-control-reliability-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- main_failure_mode: `Reruns are substantively gated, but the gate decision is not durably written in a normalized five-gate packet, weakening auditability.`
- recommended_tightening: `Before every hard-family rerun, require one durable rerun_gate_result block with all five gate fields populated and cited, and treat omission as governance failure even if the rerun later proves useful.`
- escalate_to_gm: `yes`
- escalation_reason: `The governing law is strong, but repo-tracked execution evidence is still inconsistent enough that proving-spend legality is harder to audit than it should be.`

## `PE-04`: `blocker localization below suite level`

- principle_id: `PE-04`
- principle_name: `blocker localization below suite level`
- score_1_to_10: `8`
- why: `This principle is both well stated and visibly active in campaign behavior. The repo repeatedly localized blockers to sub-suite seams before rerunning.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
- evidence_missing:
  - `No standard sub-suite blocker taxonomy is reused across campaigns.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/CAMPAIGN.md`
  - `dynamic_campaigns/repo_state_baseline_after_hard_unlock/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/CAMPAIGN.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
- main_failure_mode: `The repo localizes well in practice, but the resulting blocker taxonomy is still campaign-specific enough that cross-campaign reuse remains harder than necessary.`
- recommended_tightening: `Standardize one owner_seam_layer field in campaign logs and tranche summaries with values like lane, runner, artifact, truth_promotion, lineage_admission, observer/report, or missing_system.`
- escalate_to_gm: `no`
- escalation_reason: `none`

## `PE-05`: `no expensive loop doing multiple jobs at once`

- principle_id: `PE-05`
- principle_name: `no expensive loop doing multiple jobs at once`
- score_1_to_10: `6`
- why: `The doctrine is correct, but hard-family campaigns still show expensive reruns being used to validate a fix, expose the next blocker, re-establish lane authority, and sometimes diagnose proving-control defects.`
- evidence_found:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/14-diagnose-fresh-lane-hard01-rerun-validity-and-run-control-reliability-summary.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/outputs/tranche_summaries/04-hard01-baseline-rerun-summary.md`
- evidence_missing:
  - `No durable per-rerun field states which single job the rerun was legally allowed to do.`
- repo_surfaces_reviewed:
  - `docs/architecture/agentic_ecosystem/DYNAMIC-CAMPAIGN-ECONOMICS-LAW.md`
  - `AGENTS.md`
  - `dynamic_campaigns/hard01_hard02_baseline_trust_repair/outputs/tranche_summaries/04-hard01-baseline-rerun-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/tranche_summaries/14-diagnose-fresh-lane-hard01-rerun-validity-and-run-control-reliability-summary.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/evaluations/CAMPAIGN-LOG.md`
  - `dynamic_campaigns/hard01_hard02_trust_repair_v2/outputs/closeout/CAMPAIGN-CLOSEOUT.md`
- main_failure_mode: `A rerun still too often becomes a combined validity check, blocker discovery surface, and proving decision packet.`
- recommended_tightening: `Add one mandatory single_decision_job_of_this_rerun field before every expensive rerun and treat additional truths discovered by that rerun as spillover requiring a new diagnostic tranche.`
- escalate_to_gm: `yes`
- escalation_reason: `The doctrine names this failure mode directly, and hard-family execution still shows repeated pressure for reruns to serve multiple jobs at once.`
