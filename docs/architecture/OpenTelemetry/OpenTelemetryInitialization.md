# OpenTelemetry Initialization Notes

## GM Standing

OpenTelemetry is worth adopting as a local trace spine before it becomes an
observability platform. The immediate value is not dashboards or vendor tooling.
The immediate value is making long MCP Factory runs answer:

- am I waiting
- am I stuck
- am I stale
- am I invalid
- am I comparable
- am I product-red

The first implementation should use OpenTelemetry-shaped concepts while keeping
the default output local and cheap:

- `run-trace.json`
- `run-trace.md`
- `run-metrics.json`
- trace and span ids in API, worker, bridge, runner, and dashboard logs

An OTLP exporter, collector, Jaeger, Grafana, or hosted backend can come later.
They should not be required infrastructure for local proving, CI, or dashboard
triage.

## Thread Model

The useful parallel model is not many threads constantly coordinating. It is one
main product/proving thread plus a small set of artifact-bound side threads.

| Thread | Owns | Communicates Through | Should Not Own |
| --- | --- | --- | --- |
| Main working thread | Product fixes, proving runs, regression gates, commits | Run outputs, checkpoint artifacts, closeout notes | Observability platform design |
| Live telemetry thread | Trace spine, metric schema, local trace artifacts | `run-trace.json`, `run-metrics.json`, trace/span ids | Pipeline behavior changes |
| Operator/dashboard thread | Human-readable diagnosis and decision surfaces | Native dashboard routes, trace artifacts, checkpoint artifacts | Semantic truth itself |
| Harness/run-control thread | Startup, ports, run lifecycle, replay, reproducible commands | Launch metadata, run ids, lane status, gate artifacts | Product semantics |
| Evidence index/search thread | Queryable history across completed artifacts | Read-only artifact and ledger ingestion | Live run mutation |
| Bridge pool/queue thread | Scheduling, bridge lanes, backpressure, retries | Lane status, queue status, trace spans | Product proof claims |

The communication rule should be artifact-first. Threads should read and write
stable surfaces instead of relying on constant chat synchronization.

## Priority 1 Metrics

These are the first metrics to build because they directly reduce waiting,
rerun ambiguity, stale-lane confusion, and false product-red conclusions.

| Metric | Labels | Source Surface | Development Question |
| --- | --- | --- | --- |
| `mcp_factory.run.status_staleness` | `job_id`, `phase`, `stage`, `span` | `status.json.updated_at`, live checkpoint observations | Is the run actually moving or are we waiting on stale status? |
| `mcp_factory.pipeline.stage_span.duration` | `job_id`, `stage`, `span`, `span_state` | runner status span fields, later `stage-index.json` | Which internal stage span is slow or stuck? |
| `mcp_factory.runtime.discovery_child_wait.duration` | `job_id`, `analysis_profile`, `startup_env_mode`, `api_reload_mode`, `child_returncode` | analyzer-runtime authority phases | Is the slow part analyzer wait, bridge wait, prelaunch, or closeout? |
| `mcp_factory.runtime.subprocess_interrupts.total` | `job_id`, `phase`, `subreason_code`, `owner`, `startup_env_mode`, `api_reload_mode` | subprocess interrupt diagnostics, worker investigation artifacts | Are failures clustering in runtime/lane infrastructure instead of product behavior? |
| `mcp_factory.artifacts.required_emission_lag.duration` | `job_id`, `artifact_name`, `producing_stage`, `terminal_status` | `artifact-index.json`, `session-manifest.json`, `stage-index.json`, `transition-index.json` | After a stage says it is done, how long until required evidence is readable? |
| `mcp_factory.pipeline.checkpoint.save.duration` | `job_id`, `checkpoint_kind`, `stage_id`, `source_job_id` | checkpoint save path for `checkpoints/latest.json` and stage snapshots | Is checkpoint persistence cheap enough for fast iteration? |
| `mcp_factory.pipeline.checkpoint.resume_seeded_findings` | `job_id`, `source_job_id`, `checkpoint_stage`, `cluster_id` | checkpoint resume seed path, findings, checkpoint metadata | How much real downstream work did checkpoint resume skip? |
| `first_failed_boundary` | `case_id`, `tier`, `checkpoint`, `phase`, `failure_kind`, `failure_domain` | regression triage, checkpoint reports | Did failure occur in lane setup, analyze/explore, capture, compare, or semantics? |
| `candidate_comparability_state` | `case_id`, `candidate_root`, `safe_to_compare`, `authoritative_proving`, `product_green_eligible`, `blocking_signal` | compiled ingest summary, compare report, gate artifacts | Is this run legally comparable or only diagnostic? |
| `root_blocker` | `job_id`, `diagnosis_id`, `severity`, `owner_layer`, `first_failing_stage`, `family_id`, `native_status` | native diagnostics route, dashboard overview fallback | What broke first, and which layer owns the fix? |

## Priority 2 Metrics

These are useful after the trace spine exists. They help route proof work,
dashboard work, and baseline comparison without overloading the first tranche.

| Metric | Labels | Source Surface | Development Question |
| --- | --- | --- | --- |
| `gate_surface_elapsed_sec` | `gate_id`, `surface`, `runner_id`, `verdict`, `fail_fast` | regression gate summaries, runner results | Which gate surface consumes wall time? |
| `checkpoint_skip_savings_count` | `case_id`, `first_failed_checkpoint`, `skipped_checkpoint`, `reason` | checkpoint reports | How much work did fail-fast ordering avoid? |
| `baseline_resolution_status` | `surface_id`, `case_id`, `active`, `pinned_root`, `missing_file`, `registry_updated_at` | baseline registry, baseline access artifacts | Is this product regression or stale/missing baseline state? |
| `session_capture_outcome` | `job_id`, `component`, `snapshot_profile`, `save_session_exit`, `save_session_timed_out`, `valid_run` | runner result, run validity, collector output | Did product execution finish but capture make proof unusable? |
| `run_validity_gate_failure_count` | `component`, `profile`, `gate_name`, `reason` | `run-validity.json`, human verification reports | Which validity gate repeatedly blocks comparable evidence? |
| `ledger_comparable_profile_drift` | `component`, `dll_fingerprint`, `config_fingerprint`, `comparable_profile_key`, `git_sha`, `valid_run` | `sessions/ledger/run_ledger.jsonl` | Are we comparing compatible runs? |
| `checkpoint_replay_delta` | `source_session`, `blocking_signal`, `safe_to_compare`, `authority_delta_field`, `claim_ceiling` | checkpoint replay result artifacts | Can a downstream repair be proven without a full end-to-end rerun? |
| `artifact_authority_status` | `job_id`, `artifact`, `tier`, `present`, `read_status`, `source`, `evidence_type` | artifact route, artifact index, session manifest | Is the UI claim backed by real emitted evidence or fallback? |
| `trustworthiness_frontier` | `job_id`, `verified`, `inferred`, `unresolved`, `contradictory`, `validation_incomplete`, `safe_to_expose` | trust frontier route, validation status route | What can be trusted now versus what is speculative? |
| `next_action_confidence` | `job_id`, `recommended_action`, `confidence`, `basis`, `blocking_missing_hook` | diagnostics, decision basis, hook catalog | Should Codex fix, rerun, inspect, or refuse to compare? |

## Operator Decision Metrics

Dashboard-facing metrics should preserve root cause, provenance, and next
action. They should not degrade into raw counters.

| Metric | Operator Decision Supported |
| --- | --- |
| `first_failure_vs_downstream_absence` | Prevents downstream missing artifacts from outranking the real root blocker. |
| `blast_radius_scope` | Decides whether to do a local fix, rerun a slice, or stop broader comparison. |
| `chain_continuity` | Shows where process continuation honestly stopped. |
| `family_blocker_leverage` | Identifies which recurring blocker deserves the next engineering cycle. |
| `stage_evidence_quality` | Distinguishes strong stage truth from weak or inferred coordinates. |
| `operator_agent_alignment` | Checks whether dashboard and Codex are steering from the same evidence. |
| `coverage_progress_by_capability` | Presents progress in product terms such as surface coverage, workflow coherence, lineage reuse, branch truth, and freshness control. |

## Shared Identity Labels

Every trace, metric, and log event should carry a small shared identity set when
available:

- `trace_id`
- `span_id`
- `job_id`
- `run_id`
- `suite_id`
- `case_id`
- `target_name`
- `stage`
- `span`
- `checkpoint_id`
- `bridge_port`
- `api_port`
- `git_sha`
- `source_artifact`
- `claim_ceiling`

Without these labels, metrics become detached numbers and cannot shorten the
debugging loop.

## Claim Ceiling

Telemetry is diagnostic evidence only.

These metrics can accelerate diagnosis, rerun routing, lane classification, and
operator review. They cannot by themselves prove:

- semantic correctness
- `safe_to_compare`
- authoritative proving
- product green
- compiled-suite non-regression

Those claims still require the regression ladder, baseline comparison, run
validity, compiled proof artifacts, and proving-authority review surfaces.

## First Implementation Slice

The first separate implementation thread should own only the trace spine:

- define the event and metric schema
- add local `run-trace.json`, `run-trace.md`, and `run-metrics.json`
- attach trace/span ids to status, stage, bridge, subprocess, model, artifact,
  and checkpoint boundaries
- emit no required external traffic
- keep all behavior no-op when telemetry is disabled

The first dashboard follow-up should consume those local artifacts and answer:

- what broke first
- why it matters
- whether the run is still moving
- whether the evidence is comparable
- what the next bounded move should be
