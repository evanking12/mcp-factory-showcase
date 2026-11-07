# S-00 Package Notes

`context.py`, `checkpoint_hooks.py`, and `session_artifacts.py` in this package are metadata-only scaffolding unless this README says otherwise.

Runtime owner files:

- `api/pipeline/s00_setup/__init__.py`
- `api/pipeline/s00_setup/admission_handoff.py`
- `api/pipeline/s00_setup/baseline_truth.py`
- `api/pipeline/s00_setup/calibration.py`
- `api/pipeline/s00_setup/s01_handoff_packet.py`
- `api/pipeline/s00_setup/setup_baseline.py`
- `api/pipeline/s00_setup/status.py`
- `api/pipeline/s00_setup/static_analysis.py`
- `api/pipeline/s00_setup/static_evidence.py`
- `api/pipeline/s00_setup/static_enrichment.py`
- `api/pipeline/s00_setup/static_surface_extraction.py`
- `api/pipeline/s00_setup/vocab_prior_hints.py`
- `api/pipeline/s00_setup/vocab_seed.py`

Current orchestration shape:

- `__init__.py` preserves the S-00 parent compatibility wrapper.
- `setup_baseline.py` owns the setup baseline boundary and is now invoked by
  the runner as the `s00_setup_baseline` checkpoint before static evidence.
- `status.py` owns runtime-visible S-00 substage status/checkpoint labels while
  preserving `s00_setup` as the parent compatibility stage.
- `baseline_truth.py` preserves the calibration/baseline seam inside setup.
- `vocab_prior_hints.py` preserves the vocab/prior-hints seam inside setup.
- `static_evidence.py` owns the static evidence boundary and is now invoked by
  the runner as the `s00_static_evidence` checkpoint before admission handoff.
- `static_surface_extraction.py` preserves the legacy static surface seam name.
- `static_enrichment.py` owns the normalized static-enrichment artifact emitted
  after static analysis.
- `admission_handoff.py` owns the S-01 admission/handoff boundary and is now
  invoked by the runner as the `s00_admission_handoff` checkpoint before S-01.
- `s01_handoff_packet.py` preserves the legacy packet-producer wrapper name.
- implementation helpers remain local until a later quality or extraction
  campaign proves they should move.

Sticky docs:

- `PURPOSE.md`
- `FLOW.md`
- `ARTIFACTS.md`
- `SYSTEMS.md`
- `LIVE-CONTRACT.md`
- `TRACE.md`
- `FAMILY-BLOCKERS.md`
