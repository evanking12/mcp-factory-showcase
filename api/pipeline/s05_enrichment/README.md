# S-05 Package Notes

`context.py`, `checkpoint_hooks.py`, and `session_artifacts.py` in this package are metadata-only scaffolding unless this README says otherwise.

Runtime owner files:

- `api/pipeline/s05_enrichment/__init__.py`
- `api/pipeline/s05_enrichment/status.py`
- `api/pipeline/s05_enrichment/schema_backfill.py`
- `api/pipeline/s05_enrichment/verification_replay.py`
- `api/pipeline/s05_enrichment/read_to_write_chaining.py`
- `api/pipeline/s05_enrichment/backfill.py`
- `api/pipeline/s05_enrichment/mc5_chain_reads.py`
- `api/pipeline/s05_enrichment/verify.py`

Runtime-visible stage IDs:

- `s05_schema_backfill`
- `s05_verification_replay`
- `s05_read_to_write_chaining`

`s05_enrichment` remains the compatibility parent.

`verify.py` now owns two verification paths:

- direct replay of already-successful `working_call` evidence
- stateful mutator verification that promotes setter or writer calls only when a same-session downstream effect is observed

This keeps custom positive returns from being treated as proof by themselves while still letting S-05 upgrade real state-changing calls discovered during probing.

Sticky docs:

- `PURPOSE.md`
- `FLOW.md`
- `ARTIFACTS.md`
- `SYSTEMS.md`
- `LIVE-CONTRACT.md`
- `TRACE.md`
- `FAMILY-BLOCKERS.md`
