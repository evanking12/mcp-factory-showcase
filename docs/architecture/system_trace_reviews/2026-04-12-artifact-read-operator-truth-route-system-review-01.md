# Artifact Read And Operator Truth Route System Review 01

- `system_name`
  - `artifact-read-operator-truth-route-system`
- `broader_goal_served`
  - keep route-level operator truth honest when artifacts are missing, degraded,
    or partially available across blob and saved-session surfaces
- `code_entrypoints`
  - `api/routes/main.py`
    - `_load_job_artifact_json`
    - `_load_job_artifact_text`
    - `_native_route_artifact_status`
    - route handlers such as `/validation-status`, `/diagnostics`,
      `/verdict-hierarchy`, and `/artifacts`
  - `api/infra/storage.py`
    - `_download_blob`
- `stage_or_module_path`
  - storage backend read
  - route artifact loader
  - route-specific operator projection
  - operator-facing JSON response
- `expected_artifacts`
  - `validation-report.json`
  - `macro_verdict.json`
  - `run-validity.json`
  - `cohesion-report.json`
  - `stage-index.json`
  - `transition-index.json`
  - `artifact-index.json`
  - saved-session fallbacks for the same artifact family when blob reads miss
- `expected_status_or_checkpoint_transitions`
  - normal absence should remain `partial` or `unknown`, not `degraded`
  - real read or parse failures should surface as degraded artifact truth
  - route summaries should preserve provenance through `source_artifacts`,
    `derived_from`, and `artifact_read_issues`
- `operator_or_ui_surfaces`
  - `/api/jobs/{job_id}/validation-status`
  - `/api/jobs/{job_id}/diagnostics`
  - `/api/jobs/{job_id}/verdict-hierarchy`
  - `/api/jobs/{job_id}/artifacts`
- `tests_covering_path`
  - `tests/test_native_diagnostic_hooks.py`
- `observed_implementation_evidence`
  - shared route helpers now distinguish normal missing-artifact cases from true
    blob read and parse failures in `api/routes/main.py`
  - `_download_blob` in `api/infra/storage.py` is backend-agnostic and can
    raise local or provider-native exceptions
  - route tests cover local absence, parse failure, and non-`FileNotFoundError`
    cloud-miss classification in `tests/test_native_diagnostic_hooks.py`
  - route payloads already expose `source_artifacts`, `derived_from`, and
    `artifact_read_issues`
- `mismatches`
  - none found that require an immediate local code repair inside the bounded
    review surface
- `missing_links`
  - there is no single canonical operator-truth artifact retrieval contract
    shared across all native route families and downstream UI consumers
  - `artifact_read_issues` and native status projection are still route-local
    conventions rather than a reusable schema with one owner
- `overclaims`
  - it would be an overclaim to say the repo has one durable
    artifact-read/operator-truth system contract; the current repo has a useful
    implementation cluster with shared helpers, but not yet one named reusable
    system contract
- `confidence`
  - `medium`
- `classification`
  - `missing_system`
- `smallest_next_repair`
  - define one canonical artifact retrieval verdict schema and shared
    projection contract for operator-facing route families so artifact absence,
    degraded reads, parse failures, and provenance fields are owned in one
    reusable place instead of remaining a route-local convention
- `prompt_refinement`
  - future traces should explicitly separate:
    - a local code defect inside the traced path
    - a reusable contract or schema missing above that path
  - otherwise the tracer could overclassify every rough edge as a
    `missing_system`
