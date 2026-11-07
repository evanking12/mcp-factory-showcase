# S-00 Live Contract

## Guarantees Today

- Runs sentinel calibration and vocab seeding through the `s00_setup_baseline`
  checkpoint while preserving `s00_setup` as a compatibility parent, static
  analysis/enrichment through the `s00_static_evidence` checkpoint, then S-00
  to S-01 packet construction through the `s00_admission_handoff` checkpoint
  before S-01.
- Preserves legacy S-00 artifacts while adding `s01_handoff_packet.json`.
- Owns the setup baseline boundary through `setup_baseline.py` while
  `baseline_truth.py` and `vocab_prior_hints.py` remain internal seams and the
  current implementations remain in `calibration.py` and `vocab_seed.py`.
- Owns the static evidence boundary through `static_evidence.py` while the
  current extractor implementation remains in `static_analysis.py` and
  `static_surface_extraction.py` remains a compatibility wrapper.
- Marks `s00_static_evidence` as a runtime checkpoint boundary while preserving
  legacy static artifact paths.
- Owns additive static enrichment through `static_enrichment.py`, emitted as
  `static_enrichment.json` after static analysis.
- Marks `s00_setup_baseline`, `s00_static_evidence`, and
  `s00_admission_handoff` as runtime checkpoint boundaries while preserving
  `s00_setup` as the parent compatibility gate.
- Owns the admission/handoff boundary through `admission_handoff.py` while the
  shared builder remains in `api/pipeline/core/s00_s01_handoff.py` and
  `s01_handoff_packet.py` remains a compatibility wrapper.
- Marks `s00_admission_handoff` as a runtime checkpoint boundary and preserves
  checkpoint static context so resume can rebuild the packet if needed.
- Emits a packet with `baseline_truth`, `surface_inventory`, `prior_hints`, `deferred_static`, `ambiguity_register`, `s01_targets`, `review_verdict`, and `coordination_decision`.
- Keeps static evidence decision-preparatory; it is prior evidence, not runtime truth.
- Admits selected bounded `static_enrichment.json` fields into
  `s01_handoff_packet.json` while keeping raw decompile/xref material deferred.

## Semantic Obligation

S-00 must produce trustworthy setup/static priors and an organized S-01 handoff
packet. It prepares decisions for downstream stages; it does not prove runtime
semantic truth.

## Handoff Rule

S-00 must hand S-01 organized, decision-bearing structure rather than raw
richness. The admitted slice is the part S-01 should actively use; deferred
static material remains available but should not drive S-01 as equal-weight
input.

## Advance Stay Fail

| Outcome | Current meaning |
| --- | --- |
| Advance | Packet can be built from any credible setup/static surface and `coordination_decision.flow_outcome` is `advance`. |
| Stay | Static/setup surfaces are too thin or missing and the packet records admission risk. |
| Fail | Required setup artifacts cannot be emitted or binary/static setup fails in a way that breaks legacy compatibility. |

## Compatibility Notes

- The packet is additive and does not replace the canonical seven-stage pipeline.
- `s00_setup_baseline`, `s00_static_evidence`, and `s00_admission_handoff` are
  runtime checkpoint boundaries; `s00_setup` remains a compatibility parent.
- Legacy artifacts must remain readable during the migration.
- `static_analysis.json` is expected when binary bytes are available; missing static analysis is a regression for the current seam.
- `static_enrichment.json` is additive and fallback-safe. It must still
  serialize when Ghidra extras are absent.
- S-01 must consume static enrichment only through the admitted packet surface,
  not by reading `static_enrichment.json` directly.

## Known Blocker Families

See `FAMILY-BLOCKERS.md` for S-00 blocker families classified as `handles`,
`detects_and_defers`, `unknown_or_not_owned`, and `architecture_gap`.
